"use client";

import Link from "next/link";
import { useParams, useRouter } from "next/navigation";
import * as React from "react";

import { useSession } from "@/components/app/session";
import { SuperDocEditor } from "@/components/app/superdoc-editor";
import {
  Button,
  Card,
  CardBody,
  Field,
  Modal,
  Notice,
  PageTitle,
  Refusal,
  Spinner,
  Textarea,
} from "@/components/ui";
import { api } from "@/lib/api";
import { useAction, useApi } from "@/lib/hooks";
import type { DraftForConfirmation } from "@/lib/types";
import { formatDate } from "@/lib/utils";

/*
  The requester reading the draft, as the document it is.

  It was a modal listing the assembled blocks, which is a summary of an
  agreement rather than the agreement: the person is being asked whether these
  are the terms they agreed, and paragraphs stacked in a dialog are not how
  anybody reads a contract. This is the same editor Legal uses, in viewing
  mode, on its own page with the room a page has.

  Viewing rather than editing, and not because the mode is set that way. There
  is no autosave handler and no endpoint behind one: the requester's part is to
  say whether this is the arrangement, and a document they could alter is a
  document nobody could say two parties decided against.
*/
export default function ReadDraft() {
  const { requestId } = useParams<{ requestId: string }>();
  const router = useRouter();
  const { me } = useSession();

  const draft = useApi<DraftForConfirmation>(`/requests/${requestId}/draft`);
  const [asking, setAsking] = React.useState(false);
  const [comment, setComment] = React.useState("");

  const decide = useAction(async (decision: string) => {
    await api(`/approvals/${draft.data?.approval_id}/decision`, {
      method: "POST",
      body: { decision, comments: comment.trim() || undefined },
    });
    router.push("/portal/status");
  });

  if (draft.loading) return <Spinner label="Opening the draft" />;
  if (draft.error) {
    return (
      <div className="space-y-4">
        <Refusal title="That draft is not available to you" reason={draft.error.message} />
        <Link href="/portal/status" className="text-sm">
          Back to my requests
        </Link>
      </div>
    );
  }

  const data = draft.data!;

  return (
    <div className="space-y-5">
      <PageTitle
        title={data.document_name}
        subtitle={
          <span className="flex flex-wrap items-center gap-x-3 gap-y-1.5">
            <span>{data.subject}</span>
            <span className="text-border">/</span>
            <span>{data.reference}</span>
            {data.generated_at ? (
              <>
                <span className="text-border">/</span>
                <span>Prepared {formatDate(data.generated_at)}</span>
              </>
            ) : null}
          </span>
        }
        actions={
          <>
            <Link href="/portal/status" className="no-underline">
              <Button size="sm">Back to my requests</Button>
            </Link>
            <Button size="sm" onClick={() => setAsking(true)}>
              Ask for a change
            </Button>
            <Button
              size="sm"
              variant="primary"
              disabled={decide.busy}
              onClick={() => void decide.run("approved")}
            >
              {decide.busy ? "Confirming" : "This is what we asked for"}
            </Button>
          </>
        }
      />

      {data.changes_requested ? (
        <Notice tone="info" title="You already asked for a change">
          Legal is working on it. What you asked for:{" "}
          <span className="italic">{data.changes_requested}</span>
        </Notice>
      ) : (
        <Notice tone="warn" title="You are confirming the terms, not the drafting">
          Legal has separately checked that this is safe to sign. What only you can say is
          whether it is the arrangement you agreed. If anything is not, ask for a change and
          say what it should be.
        </Notice>
      )}

      {decide.error ? (
        <Refusal
          title="That was not recorded"
          reason={decide.error.message}
          reasons={Object.values(decide.error.fieldErrors ?? {})}
        />
      ) : null}

      <Card>
        <CardBody className="p-0 sm:p-0">
          <SuperDocEditor
            source={`/requests/${requestId}/draft/file`}
            documentName={data.document_name}
            mode="viewing"
            exportable={false}
            user={{ name: me?.name ?? "Requester", email: me?.email ?? "" }}
            height="min(calc(100vh - 20rem), 78vh)"
          />
        </CardBody>
      </Card>

      <Modal
        open={asking}
        title="Ask Legal for a change"
        subtitle="This goes to the person drafting, and the matter goes back to drafting until they have a new version for you."
        width="sm"
        onClose={() => setAsking(false)}
        footer={
          <>
            <Button onClick={() => setAsking(false)}>Cancel</Button>
            <Button
              variant="primary"
              disabled={comment.trim().length < 5 || decide.busy}
              onClick={() => void decide.run("changes_requested")}
            >
              {decide.busy ? "Sending" : "Send this to Legal"}
            </Button>
          </>
        }
      >
        <Field
          label="What should change"
          required
          hint="Name the term and what it should say. The drafter works from this."
        >
          <Textarea
            value={comment}
            onChange={(event) => setComment(event.target.value)}
            className="min-h-[8rem]"
          />
        </Field>
      </Modal>
    </div>
  );
}
