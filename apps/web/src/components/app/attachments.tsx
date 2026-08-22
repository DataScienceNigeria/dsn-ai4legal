"use client";

import * as React from "react";

import { Button, Card, CardBody, CardHeader, Notice, Pill, Refusal } from "@/components/ui";
import { upload } from "@/lib/api";
import { useAction } from "@/lib/hooks";

type Attached = { name: string; size: number };

function kilobytes(size: number): string {
  return `${Math.max(1, Math.round(size / 1024))} KB`;
}

/*
  Every upload is validated by type and magic bytes, scanned, hashed and stored
  under object lock. A refused file is quarantined rather than silently dropped,
  so the refusal is shown here as a refusal.
*/
export function Attachments({ requestId }: Readonly<{ requestId: string }>) {
  const [attached, setAttached] = React.useState<Attached[]>([]);
  const [justStored, setJustStored] = React.useState<Attached | null>(null);
  const input = React.useRef<HTMLInputElement>(null);

  const send = useAction(async (file: File) => {
    await upload(`/requests/${requestId}/attachments`, file);
    const stored = { name: file.name, size: file.size };
    setAttached((previous) => [...previous, stored]);
    setJustStored(stored);
  });

  return (
    <Card>
      <CardHeader
        title="Attachments"
        subtitle="The paper the other side sent, a term sheet, a scope of work. Anything that saves Legal from asking."
        actions={
          <>
            <input
              ref={input}
              type="file"
              className="hidden"
              onChange={(event) => {
                const file = event.target.files?.[0];
                if (file) void send.run(file);
                event.target.value = "";
              }}
            />
            <Button variant="primary" disabled={send.busy} onClick={() => input.current?.click()}>
              {send.busy ? "Uploading" : "Attach a file"}
            </Button>
          </>
        }
      />
      <CardBody className="space-y-3">
        {send.error ? (
          <Refusal
            title="That file was refused"
            reason={send.error.message}
            reasons={Object.values(send.error.fieldErrors)}
          />
        ) : null}

        {justStored ? (
          <Notice tone="good" title={`${justStored.name} is attached`}>
            {kilobytes(justStored.size)}, scanned and stored under object lock. Legal can see it
            now. Attach another if you have one, or you are done here.
          </Notice>
        ) : null}

        {attached.length === 0 ? (
          <Notice tone="info" title="Nothing attached yet">
            Files are scanned and stored under object lock. Once attached, a file cannot be
            quietly replaced, only superseded.
          </Notice>
        ) : (
          <ul className="space-y-1.5">
            {attached.map((file) => (
              <li key={file.name} className="flex items-center gap-2 text-sm">
                <Pill tone="good">Stored</Pill>
                <span className="min-w-0 truncate">{file.name}</span>
                <span className="ml-auto text-xs text-muted-foreground">
                  {kilobytes(file.size)}
                </span>
              </li>
            ))}
          </ul>
        )}
      </CardBody>
    </Card>
  );
}
