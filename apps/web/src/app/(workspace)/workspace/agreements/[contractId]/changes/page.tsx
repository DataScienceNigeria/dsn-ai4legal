"use client";

import Link from "next/link";
import { useParams } from "next/navigation";
import * as React from "react";

import { AgreementHeader } from "@/components/app/agreement-header";
import { Determine } from "@/components/app/lifecycle-queues";
import { useRoles } from "@/components/app/session";
import {
  Button,
  Card,
  CardBody,
  CardHeader,
  Empty,
  Mono,
  Pill,
  Refusal,
  Spinner,
} from "@/components/ui";
import { useApi } from "@/lib/hooks";
import type { ChangeRequest, Vocabulary } from "@/lib/types";
import { formatDate } from "@/lib/utils";

const DECISION_TONE: Record<string, "good" | "warn" | "bad" | "neutral"> = {
  pending: "warn",
  approved: "good",
  no_paper_needed: "good",
  declined: "bad",
  withdrawn: "neutral",
};

/*
  Changes asked for on one agreement.

  An approved change opens its own matter rather than editing this contract, so
  the row that carries the determination also carries the way into the matter
  drafting the paper.
*/
export default function AgreementChanges() {
  const { contractId } = useParams<{ contractId: string }>();
  const { has } = useRoles();
  const canDecide = has("head_of_legal", "admin");

  const changes = useApi<ChangeRequest[]>(`/contracts/${contractId}/change-requests`, [
    contractId,
  ]);
  const vocabulary = useApi<Vocabulary>("/lifecycle/vocabulary");
  const rows = changes.data ?? [];

  if (changes.loading) return <Spinner />;
  if (changes.error) {
    return <Refusal title="That is not available to you" reason={changes.error.message} />;
  }

  function say(key: string | null, list: "change_types" | "change_decisions" | "instruments") {
    if (!key) return "Not set";
    return vocabulary.data?.[list]?.find((term) => term.key === key)?.label ?? key;
  }

  return (
    <div className="space-y-5">
      <AgreementHeader
        contractId={contractId}
        title="Changes to this agreement"
        subtitle="No material change is made informally. Legal decides which paper carries it, and an approval opens its own matter."
      />

      {rows.length === 0 ? (
        <Empty
          title="No change has been asked for"
          detail="A request appears here when the department running this agreement wants something in it to change."
        />
      ) : (
        rows.map((change) => (
          <Card key={change.id}>
            <CardHeader
              title={say(change.change_type, "change_types")}
              subtitle={
                <span className="flex flex-wrap items-center gap-2">
                  <Mono>{change.reference}</Mono>
                  <span>{`Asked by ${change.requested_by_name ?? "somebody"}`}</span>
                  <span>{formatDate(change.created_at)}</span>
                </span>
              }
              actions={
                <div className="flex flex-wrap items-center gap-2">
                  <Pill tone={DECISION_TONE[change.decision] ?? "neutral"}>
                    {say(change.decision, "change_decisions")}
                  </Pill>
                  {change.instrument ? (
                    <Pill tone="info">{say(change.instrument, "instruments")}</Pill>
                  ) : null}
                </div>
              }
            />
            <CardBody className="space-y-3">
              <div>
                <div className="text-xs text-muted-foreground">Why they want it</div>
                <p className="whitespace-pre-wrap text-sm leading-relaxed">{change.rationale}</p>
              </div>
              <div>
                <div className="text-xs text-muted-foreground">What they propose</div>
                <p className="whitespace-pre-wrap text-sm leading-relaxed">
                  {change.proposed_changes}
                </p>
              </div>
              <div className="flex flex-wrap gap-4 text-xs text-muted-foreground">
                <span>
                  {`Money: ${change.financial_effect ?? "not stated"}`}
                  {change.value_delta
                    ? `, ${change.value_currency} ${Number(change.value_delta).toLocaleString()}`
                    : ""}
                </span>
                <span>
                  {`Dates: ${change.timeline_effect ?? "not stated"}`}
                  {change.proposed_end_date
                    ? `, to ${formatDate(change.proposed_end_date)}`
                    : ""}
                </span>
              </div>

              {change.decision_reason ? (
                <div className="rounded-md border p-3">
                  <div className="text-xs text-muted-foreground">
                    {`Legal's determination, ${formatDate(change.decided_at)}`}
                  </div>
                  <p className="whitespace-pre-wrap text-sm leading-relaxed">
                    {change.decision_reason}
                  </p>
                </div>
              ) : null}

              <div className="flex flex-wrap gap-2 border-t pt-3">
                {change.decision === "pending" && canDecide ? (
                  <Determine change={change} onDone={changes.reload} />
                ) : null}
                {change.resulting_matter_number ? (
                  <Link
                    href={`/workspace/matters/${change.resulting_matter_id}`}
                    className="no-underline"
                  >
                    <Button size="sm">{`Drafted under ${change.resulting_matter_number}`}</Button>
                  </Link>
                ) : null}
              </div>
            </CardBody>
          </Card>
        ))
      )}
    </div>
  );
}
