"use client";

import * as React from "react";

import { Icon } from "@/components/app/icons";
import { Button, Field, Input, Modal, Refusal, Textarea } from "@/components/ui";
import { api } from "@/lib/api";
import { useAction } from "@/lib/hooks";

/*
  Renaming a matter or a request in triage.

  Requesters describe their own problem, and the description that arrives is
  often the counterparty's name or a sentence of context rather than the piece
  of work. Everything downstream reads that wording, so triage is where it is
  put right, and a matter can be renamed afterwards as the work turns out to be
  something else.

  What never changes is the identifier. The matter number and the request
  reference are the identity; the name is only what people call it, which is
  what makes renaming safe: every document, approval and audit row still
  resolves. The rename itself lands on the audit trail as a rename, so anyone
  reading the history can see the name used to be something else.
*/
export function Rename({
  path,
  field,
  label,
  current,
  askReason = false,
  onDone,
}: Readonly<{
  path: string;
  field: "title" | "subject";
  label: string;
  current: string;
  askReason?: boolean;
  onDone: () => void;
}>) {
  const [open, setOpen] = React.useState(false);
  const [value, setValue] = React.useState(current);
  const [reason, setReason] = React.useState("");

  React.useEffect(() => {
    if (open) {
      setValue(current);
      setReason("");
    }
  }, [open, current]);

  const rename = useAction(async () => {
    const body: Record<string, string> = { [field]: value.trim() };
    if (askReason && reason.trim()) body.reason = reason.trim();
    await api(path, { method: "PATCH", body });
    setOpen(false);
    onDone();
  });

  const trimmed = value.trim();
  const unchanged = trimmed === current.trim();
  const tooShort = trimmed.length < 3;

  return (
    <>
      <Button size="sm" onClick={() => setOpen(true)}>
        <Icon name="rename" className="h-4 w-4" />
        Rename
      </Button>

      <Modal
        open={open}
        title={`Rename this ${label}`}
        subtitle="The identifier does not change, so every document, approval and audit entry still resolves. Only what people call it changes."
        width="sm"
        onClose={() => setOpen(false)}
        footer={
          <>
            <Button onClick={() => setOpen(false)}>Cancel</Button>
            <Button
              variant="primary"
              disabled={rename.busy || unchanged || tooShort}
              onClick={() => void rename.run()}
            >
              {rename.busy ? "Saving" : "Save the name"}
            </Button>
          </>
        }
      >
        <Field
          label="Name"
          required
          hint={
            tooShort
              ? "Give it something a colleague could recognise it by."
              : "What this piece of work is, rather than who it is with."
          }
        >
          <Input value={value} onChange={(event) => setValue(event.target.value)} />
        </Field>
        {askReason ? (
          <Field
            label="Why"
            hint="Optional. The requester wrote the original wording, so a note is worth having when they ask."
          >
            <Textarea value={reason} onChange={(event) => setReason(event.target.value)} />
          </Field>
        ) : null}
        {rename.error ? (
          <Refusal title="That rename was refused" reason={rename.error.message} />
        ) : null}
      </Modal>
    </>
  );
}
