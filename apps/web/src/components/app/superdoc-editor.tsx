"use client";

import * as React from "react";

import { Button, Notice, Spinner } from "@/components/ui";
import { getToken } from "@/lib/api";

export type DocumentMode = "viewing" | "suggesting" | "editing";

/*
  SuperDoc is DOM-bound and ships its own stylesheet, so it is imported at run
  time on the client rather than bundled into the server render. The platform
  keeps the authoritative copy: SuperDoc edits a .docx that the API produced,
  and an export goes back through the API so the content hash is recomputed
  there rather than trusted from the browser.
*/
export function SuperDocEditor({
  documentId,
  documentName,
  mode,
  user,
  onExport,
}: Readonly<{
  documentId: string;
  documentName: string;
  mode: DocumentMode;
  user: { name: string; email: string };
  onExport?: (file: Blob) => void;
}>) {
  const mountRef = React.useRef<HTMLDivElement>(null);
  const toolbarRef = React.useRef<HTMLDivElement>(null);
  const instanceRef = React.useRef<{ destroy?: () => void; export?: (args?: unknown) => Promise<Blob> } | null>(null);

  const [state, setState] = React.useState<"loading" | "ready" | "failed">("loading");
  const [message, setMessage] = React.useState<string | null>(null);

  React.useEffect(() => {
    let cancelled = false;

    async function mount() {
      setState("loading");
      try {
        const base = process.env.NEXT_PUBLIC_API_BASE_URL ?? "http://localhost:8000";
        const response = await fetch(`${base}/api/v1/documents/${documentId}/download`, {
          headers: { Authorization: `Bearer ${getToken() ?? ""}` },
        });
        if (!response.ok) throw new Error(`The document could not be fetched (${response.status}).`);

        const blob = await response.blob();
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
          documentMode: mode,
          role: mode === "editing" ? "editor" : mode === "suggesting" ? "suggester" : "viewer",
          user: { name: user.name, email: user.email },
          onReady: () => {
            if (!cancelled) setState("ready");
          },
        }) as never;
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
  }, [documentId, documentName, mode, user.name, user.email]);

  async function exportDocx() {
    const blob = await instanceRef.current?.export?.({ triggerDownload: false });
    if (blob && onExport) onExport(blob);
  }

  return (
    <div className="space-y-2">
      <div className="flex items-center justify-between gap-3">
        <div ref={toolbarRef} className="min-h-10 flex-1" />
        <Button size="sm" onClick={() => void exportDocx()} disabled={state !== "ready"}>
          Export a copy
        </Button>
      </div>

      {state === "failed" ? (
        <Notice tone="warn" title="The editor could not be started">
          {message} The document itself is unaffected. Download the .docx and work in Word or
          Google Docs, which is the documented manual path for this surface.
        </Notice>
      ) : null}

      {state === "loading" ? <Spinner label="Opening the document" /> : null}

      <div
        ref={mountRef}
        className="min-h-[60vh] overflow-auto rounded-lg border bg-card"
        aria-label="Document editor"
      />
    </div>
  );
}
