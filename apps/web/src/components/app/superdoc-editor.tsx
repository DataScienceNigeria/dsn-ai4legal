"use client";

import * as React from "react";

import { Button, Refusal, Spinner } from "@/components/ui";
import { cn } from "@/lib/utils";
import { download, getToken } from "@/lib/api";

export type DocumentMode = "viewing" | "suggesting" | "editing";

/*
  SuperDoc parses and lays out every document in a module Web Worker, and
  resolves that worker relative to its own file inside node_modules. Next.js
  does not emit worker assets for a dependency reached through a dynamic
  import, so that URL 404s and no document opens at all. These are the same
  workers, copied into public/superdoc at predev by scripts/sync-superdoc-
  workers.mjs and served same-origin, which is the arrangement SuperDoc's
  workerUrls config exists for.
*/
const WORKER_URLS = {
  document: "/superdoc/document-worker.js",
  reviewIndex: "/superdoc/review-index-worker.js",
};

type SuperDocInstance = {
  destroy?: () => void;
  export?: (args?: unknown) => Promise<Blob>;
  on?: (event: string, handler: () => void) => void;
};

/*
  SuperDoc is DOM-bound and ships its own stylesheet, so it is imported at run
  time on the client rather than bundled into the server render. The platform
  keeps the authoritative copy: SuperDoc edits a .docx that the API produced,
  and an export goes back through the API so the content hash is recomputed
  there rather than trusted from the browser.
*/
type SaveStage = "idle" | "pending" | "saving" | "saved" | "failed";

const SAVE_DEBOUNCE_MS = 1_500;

/*
  SuperDoc emits editor-update on every keystroke. Exporting a .docx per
  keystroke would be absurd, so the export waits until the typing stops, and a
  save already in flight defers the next one rather than racing it.
*/
function attachAutosave(
  instance: SuperDocInstance | null,
  cancelled: () => boolean,
  handlers: {
    setSaving: (stage: SaveStage) => void;
    setSavedAt: (at: string | null) => void;
    setSaveError: (message: string | null) => void;
    run: (file: Blob) => Promise<void>;
  },
): void {
  if (!instance?.on) return;

  let timer: ReturnType<typeof setTimeout> | null = null;
  let inFlight = false;
  let again = false;

  async function flush() {
    if (cancelled()) return;
    if (inFlight) {
      again = true;
      return;
    }
    inFlight = true;
    handlers.setSaving("saving");
    try {
      const blob = await instance?.export?.({ triggerDownload: false });
      if (!blob) throw new Error("The editor returned nothing to save.");
      await handlers.run(blob);
      if (cancelled()) return;
      handlers.setSaveError(null);
      handlers.setSavedAt(new Date().toLocaleTimeString());
      handlers.setSaving("saved");
    } catch (exception) {
      if (cancelled()) return;
      handlers.setSaving("failed");
      handlers.setSaveError(
        exception instanceof Error ? exception.message : "That change was not saved.",
      );
    } finally {
      inFlight = false;
      if (again && !cancelled()) {
        again = false;
        void flush();
      }
    }
  }

  instance.on("editor-update", () => {
    if (cancelled()) return;
    handlers.setSaving("pending");
    if (timer) clearTimeout(timer);
    timer = setTimeout(() => void flush(), SAVE_DEBOUNCE_MS);
  });
}

const SAVE_LABELS: Record<SaveStage, string> = {
  idle: "No changes yet",
  pending: "Unsaved changes",
  saving: "Saving",
  saved: "Saved",
  failed: "Not saved",
};

function SaveState({
  state,
  at,
  error,
}: Readonly<{ state: SaveStage; at: string | null; error: string | null }>) {
  if (state === "failed") {
    return (
      <output className="shrink-0 text-xs text-destructive">Not saved. {error}</output>
    );
  }
  const label = state === "saved" && at ? `Saved at ${at}` : SAVE_LABELS[state];
  return <output className="shrink-0 text-xs text-muted-foreground">{label}</output>;
}

export function SuperDocEditor({
  source,
  documentName,
  mode,
  user,
  onExport,
  exportable = true,
  onAutosave,
  height = "60vh",
}: Readonly<{
  /* The API path the .docx comes from. A generated matter document, a template
     read as the document it produces, or the Word file an import came from:
     the editor does not care which, it cares that the platform served it. */
  source: string;
  documentName: string;
  mode: DocumentMode;
  user: { name: string; email: string };
  onExport?: (file: Blob) => void;
  exportable?: boolean;
  /* Called with the edited file after the typing stops. Supplying it is what
     turns the editor into an autosaving one; without it nothing is written
     back and the surface is read-only in effect. */
  onAutosave?: (file: Blob) => Promise<void>;
  /* CSS length for the document surface. A page gives it the viewport; a
     dialog gives it what the dialog has. */
  height?: string;
}>) {
  const mountRef = React.useRef<HTMLDivElement>(null);
  const toolbarRef = React.useRef<HTMLDivElement>(null);
  const instanceRef = React.useRef<SuperDocInstance | null>(null);

  const [state, setState] = React.useState<"loading" | "ready" | "failed">("loading");
  const [message, setMessage] = React.useState<string | null>(null);
  const [saving, setSaving] = React.useState<"idle" | "pending" | "saving" | "saved" | "failed">(
    "idle",
  );
  const [savedAt, setSavedAt] = React.useState<string | null>(null);
  const [saveError, setSaveError] = React.useState<string | null>(null);
  const [fullscreen, setFullscreen] = React.useState(false);

  // The callback is held in a ref so a new function identity from the parent
  // does not tear the editor down and remount it mid-sentence.
  const autosaveRef = React.useRef(onAutosave);
  autosaveRef.current = onAutosave;

  React.useEffect(() => {
    let cancelled = false;

    async function mount() {
      setState("loading");
      try {
        const base = process.env.NEXT_PUBLIC_API_BASE_URL ?? "http://localhost:8000";
        const response = await fetch(`${base}/api/v1${source}`, {
          headers: { Authorization: `Bearer ${getToken() ?? ""}` },
        });
        if (!response.ok) throw new Error(`The document could not be fetched (${response.status}).`);

        const blob = await response.blob();

        /*
          SuperDoc edits Word files and nothing else. A signed copy is commonly
          a PDF and their paper sometimes is, and both used to arrive here
          labelled as a DOCX, so the editor tried to unzip a PDF and failed
          with a message about a source it could not prepare. Checked here and
          named, because "could not be prepared" tells the reader nothing they
          can act on.
        */
        const header = new Uint8Array(await blob.slice(0, 5).arrayBuffer());
        const isZip =
          header[0] === 0x50 && header[1] === 0x4b && header[2] === 0x03 && header[3] === 0x04;
        if (!isZip) {
          const isPdf = String.fromCharCode(...header.slice(0, 5)) === "%PDF-";
          throw new Error(
            isPdf
              ? "This is a PDF. The editor works on Word files, so there is nothing here to edit."
              : "This file is not a Word document, so the editor cannot open it.",
          );
        }

        const file = new File([blob], `${documentName}.docx`, { type: blob.type });

        const [{ SuperDoc }] = await Promise.all([
          import("superdoc"),
          // The stylesheet is a side-effect import and must land before mount.
          import("superdoc/style.css" as string).catch(() => undefined),
        ]);

        if (cancelled || !mountRef.current) return;

        instanceRef.current = new SuperDoc({
          selector: mountRef.current,
          toolbar: toolbarRef.current ?? undefined,
          document: file,
          workerUrls: WORKER_URLS,
          documentMode: mode,
          role: mode === "editing" ? "editor" : mode === "suggesting" ? "suggester" : "viewer",
          user: { name: user.name, email: user.email },
          onReady: () => {
            if (!cancelled) setState("ready");
          },
          /*
            SuperDoc fails asynchronously, after the constructor has returned,
            so the try around it never saw the failure: the spinner span for
            ever and the only trace was a console line in the corner of a
            development overlay. This is the callback the library provides for
            exactly that, and not wiring it was the reason a broken document
            looked like a slow one.
          */
          onException: (payload: { error?: unknown } | undefined) => {
            if (cancelled) return;
            const reported =
              payload?.error instanceof Error ? payload.error.message : null;
            setState("failed");
            setMessage(
              reported ??
                "The document could not be prepared for editing. It may be damaged, or it may not be a Word file.",
            );
          },
        }) as never;

        if (autosaveRef.current) {
          attachAutosave(instanceRef.current, () => cancelled, {
            setSaving,
            setSavedAt,
            setSaveError,
            run: (blob) => autosaveRef.current!(blob),
          });
        }
      } catch (exception) {
        if (cancelled) return;
        setState("failed");
        setMessage(
          exception instanceof Error ? exception.message : "The editor could not be started.",
        );
      }
    }

    void mount();

    return () => {
      cancelled = true;
      try {
        instanceRef.current?.destroy?.();
      } catch {
        // A partially mounted editor has nothing to tear down.
      }
      instanceRef.current = null;
    };
  }, [source, documentName, mode, user.name, user.email]);

  /*
    Full screen is a container change rather than the Fullscreen API, because
    the API drops out on any dialog the editor opens and takes the workspace
    chrome with it. Escape leaves, which is what everyone tries first.
  */
  React.useEffect(() => {
    if (!fullscreen) return undefined;
    const onKey = (event: KeyboardEvent) => {
      if (event.key === "Escape") setFullscreen(false);
    };
    document.addEventListener("keydown", onKey);
    const previous = document.body.style.overflow;
    document.body.style.overflow = "hidden";
    return () => {
      document.removeEventListener("keydown", onKey);
      document.body.style.overflow = previous;
    };
  }, [fullscreen]);

  async function exportDocx() {
    const blob = await instanceRef.current?.export?.({ triggerDownload: false });
    if (blob && onExport) onExport(blob);
  }

  return (
    <div
      className={cn(
        "space-y-2 p-3 sm:p-4",
        fullscreen && "fixed inset-0 z-50 overflow-auto bg-background",
      )}
    >
      <div className="flex flex-wrap items-center justify-between gap-3">
        <div ref={toolbarRef} className="superdoc-toolbar-host min-h-10 flex-1 overflow-x-auto" />
        {onAutosave ? <SaveState state={saving} at={savedAt} error={saveError} /> : null}
        <Button
          size="sm"
          onClick={() => setFullscreen((previous) => !previous)}
          title={fullscreen ? "Leave full screen, or press escape" : "Use the whole window"}
        >
          {fullscreen ? "Leave full screen" : "Full screen"}
        </Button>
        {exportable ? (
          <Button size="sm" onClick={() => void exportDocx()} disabled={state !== "ready"}>
            Export a copy
          </Button>
        ) : null}
      </div>

      {/*
        A failure is stated where the document was going to be, at the size of
        the thing that failed. It used to be a line in a console: the surface
        showed a spinner that never resolved, so a broken document and a slow
        one looked identical.
      */}
      {state === "failed" ? (
        <Refusal
          title="This document cannot be opened in the editor"
          reason={message ?? "The editor could not be started."}
          reasons={[
            "The document itself is unaffected, and nothing has been changed.",
            "Download it and open it in Word or Google Docs, which is the documented manual path.",
          ]}
        />
      ) : null}

      {state === "failed" ? (
        <div className="flex flex-wrap gap-2">
          <Button
            variant="primary"
            onClick={() => void download(source, documentName)}
          >
            Download it
          </Button>
        </div>
      ) : null}

      {state === "loading" ? <Spinner label="Opening the document" /> : null}

      <div
        ref={mountRef}
        hidden={state === "failed"}
        style={{ height: fullscreen ? "calc(100vh - 5.5rem)" : height }}
        className="superdoc-surface min-h-[22rem] overflow-auto rounded-lg border"
        aria-label="Document editor"
      />
    </div>
  );
}
