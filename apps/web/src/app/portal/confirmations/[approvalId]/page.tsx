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
import type { AwaitingDecision } from "@/lib/types";
import { formatDate, formatMoney } from "@/lib/utils";

const ASKS: Record<string, string> = {
  changes_requested: "Ask for a change",
  rejected: "Reject",
};

export default function ReadForConfirmation() {
  const { approvalId } = useParams<{ approvalId: string }>();
  const router = useRouter();
  const { me } = useSession();

  const waiting = useApi<AwaitingDecision[]>("/approvals/awaiting");
  const [asking, setAsking] = React.useState<string | null>(null);
  const [comment, setComment] = React.useState("");

  const decide = useAction(async (decision: string) => {
    await api(`/approvals/${approvalId}/decision`, {
      method: "POST",
      body: { decision, comments: comment.trim() || undefined },
    });
    router.push("/portal/confirmations");
  });

  if (waiting.loading) return <Spinner label="Opening the draft" />;
  const row = (waiting.data ?? []).find((item) => item.approval_id === approvalId);
  if (waiting.error || !row) {
    return (
      <div className="space-y-4">
        <Refusal
          title="This draft is not waiting on you"
          reason={
            waiting.error?.message ??
            "It may have been decided already, or an earlier step is still open."
          }
        />
        <Link href="/portal/confirmations" className="text-sm">
          Back to confirmations
        </Link>
      </div>
    );
  }

  return (
    <div className="space-y-5">
      <PageTitle
        title={row.document_name}
        subtitle={
          <span className="flex flex-wrap items-center gap-x-3 gap-y-1.5">
            <span>{row.matter_number}</span>
            <span className="text-border">/</span>
            <span>{row.step_name}</span>
            {row.value_amount !== null ? (
              <>
                <span className="text-border">/</span>
                <span>{formatMoney(row.value_amount, row.value_currency ?? "NGN")}</span>
              </>
            ) : null}
            {row.due_at ? (
              <>
                <span className="text-border">/</span>
                <span>Due {formatDate(row.due_at)}</span>
              </>
            ) : null}
          </span>
        }
        actions={
          <>
            <Link href="/portal/confirmations" className="no-underline">
              <Button size="sm">Back</Button>
            </Link>
            <Button size="sm" onClick={() => setAsking("changes_requested")}>
              Ask for a change
            </Button>
            <Button size="sm" variant="destructive" onClick={() => setAsking("rejected")}>
              Reject
            </Button>
            <Button
              size="sm"
              variant="primary"
              loading={decide.busy && asking === null}
              disabled={decide.busy}
              onClick={() => void decide.run("approved")}
            >
              Confirm
            </Button>
          </>
        }
      />

      <Notice tone="warn" title="You are confirming your part, not the drafting">
        Legal has checked the wording separately. Confirm only what is yours to answer, and if
        anything in it is not right, ask for a change and say what it should be.
      </Notice>

      {decide.error && asking === null ? (
        <Refusal
          title="That was not recorded"
          reason={decide.error.message}
          reasons={Object.values(decide.error.fieldErrors ?? {})}
        />
      ) : null}

      <Card>
        <CardBody className="p-0 sm:p-0">
          <SuperDocEditor
            source={`/documents/${row.document_id}/download`}
            documentName={row.document_name}
            mode="viewing"
            exportable={false}
            user={{ name: me?.name ?? "Reviewer", email: me?.email ?? "" }}
            height="min(calc(100vh - 20rem), 78vh)"
          />
        </CardBody>
      </Card>

      <Modal
        open={asking !== null}
        dismissible={!decide.busy}
        title={asking ? ASKS[asking] : ""}
        subtitle="Legal reads this and works from it, so say what should change."
        onClose={() => setAsking(null)}
        footer={
          <>
            <Button onClick={() => setAsking(null)}>Cancel</Button>
            <Button
              variant={asking === "rejected" ? "destructive" : "primary"}
              disabled={!comment.trim()}
              loading={decide.busy}
              onClick={() => asking && void decide.run(asking)}
            >
              {asking ? ASKS[asking] : ""}
            </Button>
          </>
        }
      >
        <Field label="What should change" required>
          <Textarea value={comment} onChange={(event) => setComment(event.target.value)} />
        </Field>
        {decide.error ? (
          <Refusal
            title="That was not recorded"
            reason={decide.error.message}
            reasons={Object.values(decide.error.fieldErrors ?? {})}
          />
        ) : null}
      </Modal>
    </div>
  );
}
