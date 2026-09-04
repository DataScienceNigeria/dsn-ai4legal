"use client";

import * as React from "react";

import { Button, Field, Input, Pill, Refusal } from "@/components/ui";
import { upload } from "@/lib/api";
import { useAction } from "@/lib/hooks";

export type Evidence = { documentId: string | null; reference: string };

export const NO_EVIDENCE: Evidence = { documentId: null, reference: "" };

/*
  Evidence is a file, or a note about where the file is, or nothing.

  It was only ever the note. The column for the document existed, the API
  accepted it, and no screen offered a way to produce one, so "each needs
  evidence" was satisfied by typing "see email" into a box. Both halves are
  offered here and neither is demanded: a bank statement held in the finance
  system is legitimately a reference, and a confirmation whose paper lives
  somewhere else is still worth recording.

  The file becomes a document on the agreement, so it inherits the retention
  schedule, the legal hold and the access rules rather than sitting in an
  attachment nobody can find. Offering the same file twice links the existing
  document instead of storing a second copy.
*/
export function EvidenceField({
  contractId,
  value,
  onChange,
  label = "Evidence",
  hint = "Attach the file that proves it, or say where it is. Either, both, or neither.",
}: Readonly<{
  contractId: string;
  value: Evidence;
  onChange: (next: Evidence) => void;
  label?: string;
  hint?: string;
}>) {
  const chooser = React.useRef<HTMLInputElement>(null);
  const [name, setName] = React.useState<string | null>(null);
  const [reused, setReused] = React.useState(false);

  const send = useAction(async (file: File) => {
    const result = await upload<{ id: string; name: string; reused: boolean }>(
      `/contracts/${contractId}/evidence`,
      file,
    );
    setName(result.name);
    setReused(result.reused);
    onChange({ ...value, documentId: result.id });
  });

  return (
    <Field label={label} hint={hint} error={send.error?.message ?? null}>
      <div className="space-y-2">
        <Input
          value={value.reference}
          placeholder="Where the proof is, if it is not attached"
          onChange={(event) => onChange({ ...value, reference: event.target.value })}
        />
        <div className="flex flex-wrap items-center gap-2">
          <input
            ref={chooser}
            type="file"
            className="hidden"
            onChange={(event) => {
              const chosen = event.target.files?.[0];
              event.target.value = "";
              if (chosen) void send.run(chosen);
            }}
          />
          <Button size="sm" disabled={send.busy} onClick={() => chooser.current?.click()}>
            {send.busy ? "Scanning and storing" : "Attach a file"}
          </Button>
          {value.documentId && name ? (
            <>
              <span className="min-w-0 truncate text-sm">{name}</span>
              {reused ? <Pill tone="neutral">Already held</Pill> : <Pill tone="good">Stored</Pill>}
              <button
                type="button"
                className="text-xs text-muted-foreground underline-offset-2 hover:text-foreground hover:underline"
                onClick={() => {
                  setName(null);
                  setReused(false);
                  onChange({ ...value, documentId: null });
                }}
              >
                Remove
              </button>
            </>
          ) : (
            <span className="text-xs text-muted-foreground">Nothing attached</span>
          )}
        </div>
        {send.error ? (
          <Refusal title="That file was not stored" reason={send.error.message} />
        ) : null}
      </div>
    </Field>
  );
}
