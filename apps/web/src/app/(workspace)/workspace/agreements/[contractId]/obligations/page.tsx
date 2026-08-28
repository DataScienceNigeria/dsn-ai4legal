"use client";

import Link from "next/link";
import { useParams } from "next/navigation";
import * as React from "react";

import { useRoles } from "@/components/app/session";
import {
  Button,
  Card,
  CardBody,
  CardHeader,
  DataState,
  Mono,
  Input,
  Notice,
  PageTitle,
  Pill,
  Refusal,
  Spinner,
} from "@/components/ui";
import { api, query } from "@/lib/api";
import { useAction, useApi } from "@/lib/hooks";
import type { Contract, Obligation } from "@/lib/types";
import { formatDate, titleCase } from "@/lib/utils";

/*
  What one agreement requires, drawn out of the executed copy.

  This is a record, not a workload. Legal does not chase a consultant's
  milestones; the project manager does, and finance pays against them. What
  legal holds is the list of what the agreement actually says, to put in front
  of both sides when they disagree about it. So there is no owner, no reminder,
  no escalation and no calendar here: those belong to whoever is doing the work,
  and the platform pretending otherwise put a number on the legal team's
  navigation for tasks that were never theirs.

  It is reached from the agreement and from nowhere else, which is why there is
  no obligations entry in the navigation any more.
*/
export default function ContractObligations() {
  const params = useParams<{ contractId: string }>();
  const contractId = params.contractId;
  const { has } = useRoles();
  const canAct = has("counsel", "head_of_legal", "admin");

  const contract = useApi<Contract>(`/contracts/${contractId}`, [contractId]);
  const obligations = useApi<Obligation[]>(`/contracts/${contractId}/obligations`, [contractId]);

  const extract = useAction(async () => {
    await api(`/ai/extract-obligations/${contractId}`, { method: "POST" });
    obligations.reload();
  });

  const held = obligations.data ?? [];
  const record = contract.data;

  return (
    <div className="space-y-6">
      <PageTitle
        title="What this agreement requires"
        subtitle={
          record
            ? `${record.reference}, ${titleCase(record.agreement_type)} with ${record.counterparty?.legal_name ?? "an unlinked counterparty"}, executed ${formatDate(record.executed_at)}.`
            : "Drawn from the executed copy. Each entry quotes the clause it came from."
        }
        actions={
          <div className="flex flex-wrap items-center gap-2">
            <Link href="/workspace/agreements" className="no-underline">
              <Button size="sm">Back to the archive</Button>
            </Link>
            {canAct ? (
              <Button
                size="sm"
                variant={held.length ? "default" : "primary"}
                disabled={extract.busy}
                onClick={() => void extract.run()}
              >
                {held.length ? "Extract again" : "Extract the obligations"}
              </Button>
            ) : null}
          </div>
        }
      />

      {extract.busy ? <Spinner label="Reading the executed agreement" /> : null}

      {extract.error ? (
        <Refusal
          title="Extraction was refused"
          reason={extract.error.message}
          reasons={extract.error.reasons}
        />
      ) : null}

      <Card>
        <CardHeader
          title={`${held.length} ${held.length === 1 ? "obligation" : "obligations"}`}
          subtitle="Each quotes the clause it was drawn from, so the wording is checked rather than remembered."
        />
        <CardBody>
          <DataState
            loading={obligations.loading}
            errorMessage={obligations.error?.message}
            isEmpty={held.length === 0}
            emptyTitle="Nothing has been drawn from this agreement yet"
          >
            <ol className="space-y-3">
              {held.map((obligation) => (
                <li key={obligation.id} className="rounded-lg border p-3.5">
                  <div className="flex flex-wrap items-center gap-2">
                    <Pill tone="neutral">{titleCase(obligation.obligation_type)}</Pill>
                    <span className="min-w-0 font-medium">{obligation.name}</span>
                    {obligation.due_date ? (
                      <span className="text-xs text-muted-foreground">
                        Due {formatDate(obligation.due_date)}
                      </span>
                    ) : (
                      <span className="text-xs text-muted-foreground">
                        No date. It falls due on an event.
                      </span>
                    )}
                  </div>

                  {obligation.description ? (
                    <p className="mt-1.5 text-sm leading-relaxed">{obligation.description}</p>
                  ) : null}

                  {obligation.source_quote ? (
                    <blockquote className="mt-2 border-l-2 pl-3 text-xs italic leading-relaxed text-muted-foreground">
                      {obligation.source_quote}
                    </blockquote>
                  ) : null}

                  <div className="mt-2 flex flex-wrap items-center gap-2 text-xs text-muted-foreground">
                    <Mono>{obligation.reference}</Mono>
                    {obligation.source_clause ? (
                      <span>Clause {obligation.source_clause}</span>
                    ) : null}
                    {obligation.decision_taken ? (
                      <Pill tone="good">{titleCase(obligation.decision_taken)}</Pill>
                    ) : null}
                  </div>

                  {/*
                    The renewal decision, where there is one to make.

                    Opening a renewal task and then having nowhere to record
                    what was decided is the loop this closes. The window either
                    closes on a decision or it closes on its own, and the
                    second is the failure the task exists to prevent.
                  */}
                  {canAct && (obligation.decision_options ?? []).length > 0 &&
                  !obligation.decision_taken ? (
                    <RenewalDecision obligation={obligation} onDone={obligations.reload} />
                  ) : null}
                </li>
              ))}
            </ol>
          </DataState>
        </CardBody>
      </Card>

      <Notice title="What this list is for">
        A record of what the agreement requires, not a set of tasks for the legal team. When
        parties disagree about what was owed, this is what both sides read, beside the clause each
        entry came from. Extracting again replaces the list; the executed copy it is drawn from
        cannot change.
        {/*
          The feed carries renewal, notice and termination windows only. Those
          are legal's own deadlines and nobody else is watching them; a
          consultant's milestone belongs in the project manager's calendar.
        */}
        <div className="mt-2.5">
          <a
            href={`${process.env.NEXT_PUBLIC_API_BASE_URL ?? "http://localhost:8000"}/api/v1/obligations/calendar.ics`}
            className="text-xs"
          >
            Subscribe to the renewal and notice deadlines
          </a>
        </div>
      </Notice>
    </div>
  );
}

/*
  Four answers, and no fifth. "Do nothing" is not among them because doing
  nothing is what happens anyway; the task exists so that the window closes on
  a decision somebody made rather than on the calendar.
*/
function RenewalDecision({
  obligation,
  onDone,
}: Readonly<{ obligation: Obligation; onDone: () => void }>) {
  const [choice, setChoice] = React.useState("");
  const [reason, setReason] = React.useState("");

  const decide = useAction(async () => {
    await api(
      `/obligations/${obligation.id}/renewal-decision${query({
        decision: choice,
        reason: reason || undefined,
      })}`,
      { method: "POST" },
    );
    onDone();
  });

  return (
    <div className="mt-3 space-y-2 border-t pt-3">
      {decide.error ? (
        <Refusal title="That decision was not recorded" reason={decide.error.message} />
      ) : null}

      <div className="flex flex-wrap gap-1.5">
        {(obligation.decision_options ?? []).map((option) => (
          <Button
            key={option}
            size="sm"
            variant={choice === option ? "primary" : "default"}
            onClick={() => setChoice(option)}
          >
            {titleCase(option)}
          </Button>
        ))}
      </div>

      {choice ? (
        <div className="flex flex-wrap items-end gap-2">
          <Input
            value={reason}
            onChange={(event) => setReason(event.target.value)}
            placeholder="Why, in a line"
            className="min-w-[16rem] flex-1"
          />
          <Button variant="primary" disabled={decide.busy} onClick={() => void decide.run()}>
            Record it
          </Button>
        </div>
      ) : null}
    </div>
  );
}
