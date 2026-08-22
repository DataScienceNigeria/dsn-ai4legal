"use client";

import * as React from "react";

import { useSession } from "@/components/app/session";
import {
  Button,
  Card,
  CardHeader,
  Empty,
  Field,
  Input,
  Modal,
  Mono,
  Notice,
  PageTitle,
  Pill,
  Refusal,
  Row,
  Select,
  Spinner,
  Tabs,
  Textarea,
} from "@/components/ui";
import { api, query } from "@/lib/api";
import { useAction, useApi } from "@/lib/hooks";
import type { Obligation } from "@/lib/types";
import { formatDate, titleCase } from "@/lib/utils";

function DueCell({ obligation }: Readonly<{ obligation: Obligation }>) {
  if (!obligation.due_date) return <Pill tone="neutral">Event driven</Pill>;
  if (obligation.overdue) {
    return <Pill tone="bad">{`${Math.abs(obligation.days_until_due ?? 0)} days overdue`}</Pill>;
  }
  const days = obligation.days_until_due ?? 0;
  if (days <= obligation.lead_time_days) return <Pill tone="warn">{`In ${days} days`}</Pill>;
  return <span className="text-xs text-muted-foreground">{formatDate(obligation.due_date)}</span>;
}

const RENEWAL_LABEL: Record<string, string> = {
  renew: "Renew on the current terms",
  renegotiate: "Renegotiate before renewal",
  terminate: "Serve notice and terminate",
  lapse: "Allow it to lapse",
};

/*
  A renewal window closes whether or not anyone decides. Recording the choice
  is the point: letting it pass by default is the outcome this replaces.
*/
function RenewalDecision({
  obligation,
  onDone,
}: Readonly<{ obligation: Obligation; onDone: () => void }>) {
  const [open, setOpen] = React.useState(false);
  const options = obligation.decision_options ?? [];
  const [decision, setDecision] = React.useState(options[0] ?? "renew");
  const [reason, setReason] = React.useState("");

  const decide = useAction(async () => {
    await api(
      `/obligations/${obligation.id}/renewal-decision${query({ decision, reason })}`,
      { method: "POST" },
    );
    onDone();
    setOpen(false);
  });

  return (
    <>
      <Button size="sm" variant="primary" onClick={() => setOpen(true)}>
        Decide the renewal
      </Button>
      <Modal
        open={open}
        title={obligation.name}
        subtitle={obligation.description ?? "Record what happens when this term ends."}
        width="sm"
        onClose={() => setOpen(false)}
        footer={
          <>
            <Button onClick={() => setOpen(false)}>Cancel</Button>
            <Button variant="primary" disabled={decide.busy} onClick={() => void decide.run()}>
              Record the decision
            </Button>
          </>
        }
      >
        <Field label="Decision" required>
          <Select value={decision} onChange={(event) => setDecision(event.target.value)}>
            {options.map((option) => (
              <option key={option} value={option}>
                {RENEWAL_LABEL[option] ?? titleCase(option)}
              </option>
            ))}
          </Select>
        </Field>
        <Field label="Reason" hint="Recorded with the decision and visible on the counterparty history.">
          <Textarea value={reason} onChange={(event) => setReason(event.target.value)} />
        </Field>
        {decide.error ? (
          <Refusal title="That decision was refused" reason={decide.error.message} />
        ) : null}
      </Modal>
    </>
  );
}

/*
  What can be done to one obligation depends entirely on where it is. Keeping
  the branch here rather than inside the table body means the table reads as a
  table, and each state's controls sit next to the reason they exist.
*/
function ObligationAction({
  obligation,
  evidence,
  busy,
  onEvidence,
  onDecide,
  onComplete,
  onRenewal,
}: Readonly<{
  obligation: Obligation;
  evidence: string;
  busy: boolean;
  onEvidence: (value: string) => void;
  onDecide: (decision: string) => void;
  onComplete: () => void;
  onRenewal: () => void;
}>) {
  if (obligation.status === "proposed") {
    return (
      <>
        <Button size="sm" variant="primary" disabled={busy} onClick={() => onDecide("confirm")}>
          Confirm
        </Button>
        <Button size="sm" disabled={busy} onClick={() => onDecide("reject")}>
          Reject
        </Button>
      </>
    );
  }

  if (obligation.status !== "open") {
    return (
      <span className="text-xs text-muted-foreground">
        {formatDate(obligation.completed_at)}
      </span>
    );
  }

  if ((obligation.decision_options ?? []).length) {
    return <RenewalDecision obligation={obligation} onDone={onRenewal} />;
  }

  return (
    <>
      {obligation.evidence_required ? (
        <Input
          placeholder="Evidence reference"
          className="h-9 w-full min-w-[9rem] sm:w-40"
          value={evidence}
          onChange={(event) => onEvidence(event.target.value)}
        />
      ) : null}
      <Button
        size="sm"
        variant="primary"
        disabled={busy || (obligation.evidence_required && !evidence)}
        onClick={onComplete}
      >
        Complete
      </Button>
    </>
  );
}

export default function Obligations() {
  const { entity } = useSession();
  const [tab, setTab] = React.useState("open");
  const [evidence, setEvidence] = React.useState<Record<string, string>>({});

  const all = useApi<Obligation[]>("/obligations", [entity]);

  const rows = React.useMemo(() => {
    const items = all.data ?? [];
    if (tab === "proposed") return items.filter((o) => o.status === "proposed");
    if (tab === "completed") return items.filter((o) => o.status === "completed");
    return items.filter((o) => o.status === "open");
  }, [all.data, tab]);

  const decide = useAction(async (id: string, decision: string) => {
    await api(`/obligations/${id}/decision`, { method: "POST", body: { decision } });
    all.reload();
  });

  const complete = useAction(async (id: string, reference: string | undefined) => {
    await api(`/obligations/${id}/complete`, {
      method: "POST",
      body: { evidence_reference: reference },
    });
    all.reload();
  });

  const counts = {
    open: (all.data ?? []).filter((o) => o.status === "open").length,
    proposed: (all.data ?? []).filter((o) => o.status === "proposed").length,
    completed: (all.data ?? []).filter((o) => o.status === "completed").length,
  };

  return (
    <div className="space-y-6">
      <PageTitle
        title="Obligations"
        subtitle={
          "Post-signature duties, extracted from the executed agreement and confirmed by a " +
          "person before they become tracked tasks."
        }
        actions={
          <a
            href={`${process.env.NEXT_PUBLIC_API_BASE_URL ?? "http://localhost:8000"}/api/v1/obligations/calendar.ics`}
            className="text-xs"
          >
            Subscribable calendar feed
          </a>
        }
      />

      {counts.proposed ? (
        <Notice tone="warn" title={`${counts.proposed} proposals await confirmation`}>
          Each proposal shows the clause it came from. Nothing becomes a tracked task, and no
          reminder is sent, until Legal confirms it.
        </Notice>
      ) : null}

      <Tabs
        tabs={[
          { id: "open", label: "Tracked", badge: counts.open },
          { id: "proposed", label: "Proposed", badge: counts.proposed },
          { id: "completed", label: "Completed", badge: counts.completed },
        ]}
        active={tab}
        onChange={setTab}
      />

      {decide.error || complete.error ? (
        <Refusal
          title="That action was refused"
          reason={(decide.error ?? complete.error)?.message}
        />
      ) : null}

      <Card>
        <CardHeader title={`${rows.length} obligations`} subtitle={`Entity ${entity}`} />
        <div className="table-scroll">
          <div className="min-w-[61.25rem]">
            <Row cols="minmax(0,1.4fr) 7.5rem 8.125rem 7.5rem 6.25rem minmax(0,1fr)" head>
              <div>Obligation</div>
              <div>Type</div>
              <div>Due</div>
              <div>Source clause</div>
              <div>Evidence</div>
              <div>Action</div>
            </Row>

            {all.loading ? (
              <Spinner />
            ) : all.error ? (
              <Empty title="Obligations are not available to you" detail={all.error.message} />
            ) : !rows.length ? (
              <Empty title="Nothing in this view" />
            ) : (
              rows.map((obligation) => (
                <Row
                  key={obligation.id}
                  cols="minmax(0,1.4fr) 7.5rem 8.125rem 7.5rem 6.25rem minmax(0,1fr)"
                >
                  <div className="min-w-0">
                    <div className="truncate text-sm font-medium">{obligation.name}</div>
                    <Mono>{obligation.reference}</Mono>
                    {obligation.source_quote && tab === "proposed" ? (
                      <p className="mt-1 text-xs italic leading-relaxed text-muted-foreground">
                        &ldquo;{obligation.source_quote}&rdquo;
                      </p>
                    ) : null}
                  </div>
                  <div className="text-xs">{titleCase(obligation.obligation_type)}</div>
                  <div>
                    <DueCell obligation={obligation} />
                  </div>
                  <Mono>{obligation.source_clause ?? "Not recorded"}</Mono>
                  <div>
                    {obligation.evidence_required ? (
                      <Pill tone={obligation.evidence_reference ? "good" : "warn"}>
                        {obligation.evidence_reference ? "Held" : "Required"}
                      </Pill>
                    ) : (
                      <span className="text-xs text-muted-foreground">Not needed</span>
                    )}
                  </div>
                  <div className="flex flex-wrap items-center gap-1.5">
                    <ObligationAction
                      obligation={obligation}
                      evidence={evidence[obligation.id] ?? ""}
                      busy={decide.busy || complete.busy}
                      onEvidence={(value) =>
                        setEvidence((previous) => ({ ...previous, [obligation.id]: value }))
                      }
                      onDecide={(choice) => void decide.run(obligation.id, choice)}
                      onComplete={() => void complete.run(obligation.id, evidence[obligation.id])}
                      onRenewal={() => all.reload()}
                    />
                  </div>
                </Row>
              ))
            )}
          </div>
        </div>
      </Card>
    </div>
  );
}
