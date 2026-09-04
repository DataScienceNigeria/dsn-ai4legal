"use client";

import Link from "next/link";
import { useParams } from "next/navigation";
import * as React from "react";

import { AgreementHeader } from "@/components/app/agreement-header";
import { Resolve, Triage } from "@/components/app/lifecycle-queues";
import { useRoles } from "@/components/app/session";
import {
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
import type { ContractIssue, Vocabulary } from "@/lib/types";
import { formatDate } from "@/lib/utils";

const SEVERITY_TONE: Record<string, "bad" | "warn" | "neutral"> = {
  critical: "bad",
  material: "warn",
  minor: "neutral",
  acceptable: "neutral",
};

/*
  What has gone wrong on one agreement.

  The queue across all of them is a tab on Agreements. This is the same records
  narrowed to one row of it, which is what somebody reading that agreement wants
  and cannot get from a portfolio-wide list without filtering it themselves.
*/
export default function AgreementIssues() {
  const { contractId } = useParams<{ contractId: string }>();
  const { has } = useRoles();
  const canAct = has("counsel", "head_of_legal", "admin");

  const issues = useApi<ContractIssue[]>(`/contracts/${contractId}/issues`, [contractId]);
  const vocabulary = useApi<Vocabulary>("/lifecycle/vocabulary");
  const rows = issues.data ?? [];

  if (issues.loading) return <Spinner />;
  if (issues.error) {
    return <Refusal title="That is not available to you" reason={issues.error.message} />;
  }

  function say(key: string | null, list: "issue_types" | "issue_statuses"): string {
    if (!key) return "Not set";
    return vocabulary.data?.[list]?.find((term) => term.key === key)?.label ?? key;
  }

  return (
    <div className="space-y-5">
      <AgreementHeader
        contractId={contractId}
        title="Issues on this agreement"
        subtitle="Raised by the department running it. Legal decides what each one means."
      />

      {rows.length === 0 ? (
        <Empty
          title="Nothing has been reported"
          detail="An issue appears here when the department running this agreement tells Legal something has gone wrong."
        />
      ) : (
        rows.map((issue) => (
          <Card key={issue.id}>
            <CardHeader
              title={issue.title}
              subtitle={
                <span className="flex flex-wrap items-center gap-2">
                  <Mono>{issue.reference}</Mono>
                  <span>{say(issue.issue_type, "issue_types")}</span>
                  <span>{`Raised by ${issue.raised_by_name ?? "somebody"}`}</span>
                  {issue.occurred_on ? (
                    <span>{`Happened ${formatDate(issue.occurred_on)}`}</span>
                  ) : null}
                </span>
              }
              actions={
                <div className="flex flex-wrap items-center gap-2">
                  <Pill tone={SEVERITY_TONE[issue.severity] ?? "neutral"}>{issue.severity}</Pill>
                  <Pill tone={issue.settled ? "good" : "warn"}>
                    {say(issue.status, "issue_statuses")}
                  </Pill>
                </div>
              }
            />
            <CardBody className="space-y-3">
              <p className="whitespace-pre-wrap text-sm leading-relaxed">{issue.description}</p>
              {issue.evidence_note ? (
                <div className="text-xs text-muted-foreground">{`Evidence: ${issue.evidence_note}`}</div>
              ) : null}
              <div className="text-xs text-muted-foreground">
                {issue.assignee_name ? `Owned by ${issue.assignee_name}` : "Nobody owns it yet"}
              </div>

              {issue.resolution ? (
                <div className="rounded-md border p-3">
                  <div className="text-xs text-muted-foreground">
                    {`What was done, ${formatDate(issue.resolved_at)}`}
                  </div>
                  <p className="whitespace-pre-wrap text-sm leading-relaxed">{issue.resolution}</p>
                </div>
              ) : null}

              {/*
                What the issue produced, with somewhere to go and read it. An
                outcome naming a record nobody can open is the same dead end in
                nicer words.
              */}
              {issue.led_to ? (
                <div className="flex flex-wrap items-center gap-2 rounded-md border border-brand/40 bg-brand/5 p-3 text-sm">
                  <span className="text-xs text-muted-foreground">Led to</span>
                  <span>{issue.led_to.label}</span>
                  {issue.led_to.href && issue.led_to.reference ? (
                    <Link href={issue.led_to.href} className="font-medium underline-offset-2 hover:underline">
                      {issue.led_to.reference}
                    </Link>
                  ) : (
                    <Mono>{issue.led_to.reference ?? ""}</Mono>
                  )}
                </div>
              ) : null}

              {canAct && !issue.settled ? (
                <div className="flex flex-wrap gap-2 border-t pt-3">
                  <Triage issue={issue} onDone={issues.reload} />
                  <Resolve issue={issue} vocabulary={vocabulary.data} onDone={issues.reload} />
                </div>
              ) : null}
            </CardBody>
          </Card>
        ))
      )}
    </div>
  );
}
