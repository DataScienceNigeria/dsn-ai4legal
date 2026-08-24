"use client";

import Link from "next/link";

import { Button, Notice } from "@/components/ui";
import type { AwaitingConfirmation } from "@/lib/types";
import { formatDate } from "@/lib/utils";

/*
  The business confirming that the draft is the deal they asked for.

  Nothing asked them before this. Legal drafted, the platform routed it
  internally, and the requester found out what was in their agreement when it
  was already signed. Legal knows whether wording is safe; only the person who
  negotiated it knows whether it is the arrangement they agreed, and those are
  different questions asked of different people.

  This is the prompt, not the act. Reading a contract in a dialog, as a stack
  of paragraphs, is not reading a contract, so the act is a page of its own
  with the document opened as the document it is.
*/
export function ConfirmDraft({
  requestId,
  waiting,
}: Readonly<{ requestId: string; waiting: AwaitingConfirmation }>) {
  const alreadyAsked = Boolean(waiting.changes_requested);

  return (
    <Notice
      tone={alreadyAsked ? "info" : "warn"}
      title={alreadyAsked ? "You asked for a change" : "A draft is waiting on you"}
    >
      {alreadyAsked ? (
        <>
          Legal is working on it. What you asked for:{" "}
          <span className="italic">{waiting.changes_requested}</span>
        </>
      ) : (
        <>
          Legal has prepared {waiting.document_name}. Read it and confirm it is the
          arrangement you asked for.
          {waiting.due_at ? ` They are expecting an answer by ${formatDate(waiting.due_at)}.` : ""}
        </>
      )}
      <div className="mt-2.5">
        <Link href={`/portal/status/${requestId}`} className="no-underline">
          <Button size="sm" variant="primary">
            {alreadyAsked ? "Read it again" : "Read the draft"}
          </Button>
        </Link>
      </div>
    </Notice>
  );
}
