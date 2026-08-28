"use client";

/*
  The two queues that read across every agreement.

  They live in a component rather than on a page because the page they were
  built for is gone: Archive and After signature were one subject read two ways,
  and they are now tabs on Agreements. What survives the merge is exactly this,
  the view that answers what is open across the whole portfolio and who owns it,
  which no arrangement of row actions can answer without opening every row.
*/

import Link from "next/link";
import * as React from "react";

import {
  Button,
  Card,
  CardBody,
  CardHeader,
  DataState,
  Field,
  Input,
  Modal,
  Mono,
  Notice,
  Pill,
  Refusal,
  Row,
  Select,
  Textarea,
} from "@/components/ui";
import { useRoles } from "@/components/app/session";
import { api } from "@/lib/api";
import { useAction, useApi } from "@/lib/hooks";
import type { ChangeRequest, ContractIssue, Term, UserRow, Vocabulary } from "@/lib/types";
import { cn, formatDate } from "@/lib/utils";

const ISSUE_COLS = "minmax(0,1.6fr) 9rem 7rem 10rem 9rem 8rem";
const CHANGE_COLS = "minmax(0,1.6fr) 11rem 10rem 11rem 9rem";

const SEVERITY_TONE: Record<string, "bad" | "warn" | "neutral"> = {
  critical: "bad",
  material: "warn",
  minor: "neutral",
  acceptable: "neutral",
};

const DECISION_TONE: Record<string, "good" | "warn" | "bad" | "neutral"> = {
  pending: "warn",
  approved: "good",
  no_paper_needed: "good",
  declined: "bad",
  withdrawn: "neutral",
};

function say(terms: Term[] | undefined, key: string | null): string {
  if (!key) return "Not set";
  return terms?.find((term) => term.key === key)?.label ?? key;
}

/*
  Legal picking up an issue somebody else raised.

  Two things and no more: who owns it, and how bad it looks on a second read.
  The person who raised it knows what happened and Legal knows what it means,
  and the severity they each pick is often not the same number.
*/
export function Triage({
  issue,
  onDone,
}: Readonly<{ issue: ContractIssue; onDone: () => void }>) {
  const [open, setOpen] = React.useState(false);
  const users = useApi<UserRow[]>(open ? "/users" : null, [open]);
  const vocabulary = useApi<Vocabulary>(open ? "/lifecycle/vocabulary" : null, [open]);

  const [assignee, setAssignee] = React.useState(issue.assignee_id ?? "");
  const [severity, setSeverity] = React.useState(issue.severity);
  const [status, setStatus] = React.useState(issue.status);

  const save = useAction(async () => {
    await api(`/issues/${issue.id}/triage`, {
      method: "POST",
      body: {
        assignee_id: assignee || null,
        severity,
        status: status === issue.status ? null : status,
      },
    });
    setOpen(false);
    onDone();
  });

  const working = (vocabulary.data?.issue_statuses ?? []).filter(
    (term) => term.key === "open" || term.key === "investigating" || term.key === "escalated",
  );

  return (
    <>
      <Button size="sm" onClick={() => setOpen(true)}>
        Triage
      </Button>
      <Modal
        open={open}
        title={issue.title}
        subtitle={`${issue.reference} on ${issue.contract_reference}`}
        onClose={() => setOpen(false)}
        footer={
          <>
            <Button onClick={() => setOpen(false)}>Cancel</Button>
            <Button variant="primary" disabled={save.busy} onClick={() => void save.run()}>
              Record it
            </Button>
          </>
        }
      >
        {save.error ? (
          <Refusal title="That was not recorded" reason={save.error.message} />
        ) : null}

        <div className="rounded-md border p-3 text-sm leading-relaxed">
          {issue.description}
          <div className="mt-2 text-xs text-muted-foreground">
            {`Raised by ${issue.raised_by_name ?? "somebody"}`}
            {issue.occurred_on ? `, happened ${formatDate(issue.occurred_on)}` : ""}
          </div>
        </div>

        <Field label="Who owns it" hint="An issue with no owner is an issue nobody is looking at.">
          <Select value={assignee} onChange={(event) => setAssignee(event.target.value)}>
            <option value="">Nobody yet</option>
            {(users.data ?? [])
              .filter((person) => person.active && person.roles.some((role) =>
                ["counsel", "head_of_legal"].includes(role)))
              .map((person) => (
                <option key={person.id} value={person.id}>
                  {person.name}
                </option>
              ))}
          </Select>
        </Field>

        <div className="grid gap-3 sm:grid-cols-2">
          <Field label="Severity" hint="Theirs was a first impression. This one is the record.">
            <Select value={severity} onChange={(event) => setSeverity(event.target.value)}>
              {(vocabulary.data?.severities ?? []).map((value) => (
                <option key={value} value={value}>
                  {value}
                </option>
              ))}
            </Select>
          </Field>
          <Field label="Where it stands">
            <Select value={status} onChange={(event) => setStatus(event.target.value)}>
              {working.map((term) => (
                <option key={term.key} value={term.key}>
                  {term.label}
                </option>
              ))}
            </Select>
          </Field>
        </div>
      </Modal>
    </>
  );
}

/*
  Settling an issue, which requires saying what was done about it.

  The refusal behind this is the point of the table. An issue closed with a tick
  is the spreadsheet this replaced, and the next person to ask about the
  contract would have nothing to read.
*/
export function Resolve({
  issue,
  onDone,
}: Readonly<{ issue: ContractIssue; onDone: () => void }>) {
  const [open, setOpen] = React.useState(false);
  const [status, setStatus] = React.useState("resolved");
  const [resolution, setResolution] = React.useState("");

  const save = useAction(async () => {
    await api(`/issues/${issue.id}/resolve`, {
      method: "POST",
      body: { status, resolution },
    });
    setOpen(false);
    onDone();
  });

  return (
    <>
      <Button size="sm" variant="primary" onClick={() => setOpen(true)}>
        Resolve
      </Button>
      <Modal
        open={open}
        title="Settle this issue"
        subtitle={`${issue.reference}. ${issue.title}`}
        onClose={() => setOpen(false)}
        footer={
          <>
            <Button onClick={() => setOpen(false)}>Cancel</Button>
            <Button
              variant="primary"
              disabled={resolution.trim().length < 15 || save.busy}
              onClick={() => void save.run()}
            >
              Record the resolution
            </Button>
          </>
        }
      >
        {save.error ? (
          <Refusal
            title="That was not recorded"
            reason={save.error.message}
            reasons={save.error.reasons}
          />
        ) : null}

        <Field label="Outcome" required>
          <Select value={status} onChange={(event) => setStatus(event.target.value)}>
            <option value="resolved">Resolved</option>
            <option value="closed_no_action">Closed, no action needed</option>
          </Select>
        </Field>

        <Field
          label="What was done"
          required
          hint="The person who raised it reads this, and so does whoever asks about the contract next year."
        >
          <Textarea
            value={resolution}
            onChange={(event) => setResolution(event.target.value)}
            className="min-h-[6rem] leading-relaxed"
          />
        </Field>
      </Modal>
    </>
  );
}

export function Issues({ entity }: Readonly<{ entity: string }>) {
  const { has } = useRoles();
  // An auditor reads the queue and acts on nothing, which is what an auditor
  // does everywhere else. The buttons are absent rather than disabled, because
  // a control that refuses is worse than one that is not offered.
  const canAct = has("counsel", "head_of_legal", "admin");
  const [scope, setScope] = React.useState("");
  const issues = useApi<ContractIssue[]>(`/issues?status=${scope}`, [entity, scope]);
  const vocabulary = useApi<Vocabulary>("/lifecycle/vocabulary");
  const rows = issues.data ?? [];

  return (
    <div className="space-y-4">
      <Notice tone="info" title="Where these come from">
        The department running a contract tells Legal when something goes wrong, from the
        agreement's own page in the portal. Legal decides what it means.
      </Notice>

      <Card>
        <CardHeader
          title={`${rows.length} ${rows.length === 1 ? "issue" : "issues"}`}
          actions={
            <Select
              value={scope}
              onChange={(event) => setScope(event.target.value)}
              className="w-44"
            >
              <option value="">All</option>
              <option value="open">Still open</option>
              <option value="resolved">Resolved</option>
            </Select>
          }
        />
        <div className="table-scroll">
          <div className="min-w-[62rem]">
            <Row cols={ISSUE_COLS} head>
              <div>Issue</div>
              <div>Kind</div>
              <div>Severity</div>
              <div>Agreement</div>
              <div>Owner</div>
              <div className="text-right">Actions</div>
            </Row>
            <DataState
              loading={issues.loading}
              errorMessage={issues.error?.message}
              errorTitle="Issues are not available to you"
              isEmpty={rows.length === 0}
              emptyTitle={
                scope === "open"
                  ? "Nothing is open"
                  : scope === "resolved"
                    ? "Nothing has been resolved yet"
                    : "No issue has been raised in this entity"
              }
            >
              {rows.map((issue) => (
                <Row key={issue.id} cols={ISSUE_COLS}>
                  <div className="min-w-0">
                    <div className="line-clamp-2 font-medium leading-snug">{issue.title}</div>
                    <div className="mt-0.5 flex flex-wrap items-center gap-x-2 text-xs text-muted-foreground">
                      <Mono>{issue.reference}</Mono>
                      <span>{issue.raised_by_name}</span>
                      <span>{formatDate(issue.created_at)}</span>
                    </div>
                  </div>
                  <div className="text-sm">{say(vocabulary.data?.issue_types, issue.issue_type)}</div>
                  <div>
                    <Pill tone={SEVERITY_TONE[issue.severity] ?? "neutral"}>{issue.severity}</Pill>
                  </div>
                  <div className="min-w-0">
                    <Mono>{issue.contract_reference}</Mono>
                    <div className="truncate text-xs text-muted-foreground">
                      {issue.counterparty_name}
                    </div>
                  </div>
                  <div className="min-w-0 truncate text-sm">
                    {issue.assignee_name ?? <span className="text-warning">Nobody</span>}
                  </div>
                  <div className="flex items-center justify-end gap-2">
                    {issue.settled || !canAct ? (
                      <Pill tone={issue.settled ? "good" : "warn"}>
                        {say(vocabulary.data?.issue_statuses, issue.status)}
                      </Pill>
                    ) : (
                      <>
                        <Triage issue={issue} onDone={issues.reload} />
                        <Resolve issue={issue} onDone={issues.reload} />
                      </>
                    )}
                  </div>
                </Row>
              ))}
            </DataState>
          </div>
        </div>
      </Card>
    </div>
  );
}

/*
  Legal's determination on a requested change.

  The decision worth reading twice is what approval does: it opens a new matter
  rather than editing the contract. A variation is a document that has to be
  drafted, approved, signed and executed like any other, and the agreement that
  governed last March has to keep saying what it said then.
*/
export function Determine({
  change,
  onDone,
}: Readonly<{ change: ChangeRequest; onDone: () => void }>) {
  const [open, setOpen] = React.useState(false);
  const vocabulary = useApi<Vocabulary>(open ? "/lifecycle/vocabulary" : null, [open]);
  const [decision, setDecision] = React.useState("approved");
  const [instrument, setInstrument] = React.useState("amendment");
  const [reason, setReason] = React.useState("");

  const save = useAction(async () => {
    await api(`/change-requests/${change.id}/determination`, {
      method: "POST",
      body: {
        decision,
        instrument: decision === "approved" ? instrument : null,
        reason,
      },
    });
    setOpen(false);
    onDone();
  });

  const instruments = (vocabulary.data?.instruments ?? []).filter(
    (term) => term.key !== "none",
  );

  return (
    <>
      <Button size="sm" variant="primary" onClick={() => setOpen(true)}>
        Determine
      </Button>
      <Modal
        open={open}
        title="What carries this change"
        subtitle={`${change.reference} on ${change.contract_reference}`}
        width="lg"
        onClose={() => setOpen(false)}
        footer={
          <>
            <Button onClick={() => setOpen(false)}>Cancel</Button>
            <Button
              variant="primary"
              disabled={reason.trim().length < 10 || save.busy}
              onClick={() => void save.run()}
            >
              Record the determination
            </Button>
          </>
        }
      >
        {save.error ? (
          <Refusal
            title="That was not recorded"
            reason={save.error.message}
            reasons={save.error.reasons}
          />
        ) : null}

        <div className="space-y-3 rounded-md border p-3 text-sm leading-relaxed">
          <div>
            <div className="text-xs text-muted-foreground">Why they want it</div>
            {change.rationale}
          </div>
          <div>
            <div className="text-xs text-muted-foreground">What they propose</div>
            {change.proposed_changes}
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
              {change.proposed_end_date ? `, to ${formatDate(change.proposed_end_date)}` : ""}
            </span>
          </div>
        </div>

        <Field label="Determination" required>
          <Select value={decision} onChange={(event) => setDecision(event.target.value)}>
            <option value="approved">Approve it, paper required</option>
            <option value="no_paper_needed">
              Approve it, no paper needed
            </option>
            <option value="declined">Decline it</option>
          </Select>
        </Field>

        {decision === "approved" ? (
          <>
            <Field label="Which instrument" required>
              <Select value={instrument} onChange={(event) => setInstrument(event.target.value)}>
                {instruments.map((term) => (
                  <option key={term.key} value={term.key}>
                    {term.label}
                  </option>
                ))}
              </Select>
            </Field>
            <Notice tone="info" title="This opens a new matter">
              The variation is drafted, approved, signed and executed like any other document.
              Nothing overwrites the original: the agreement that governed last March has to keep
              saying what it said, and the register shows both.
            </Notice>
          </>
        ) : null}

        <Field
          label="Reason"
          required
          hint="Why this instrument, or why not at all. The requester reads it."
        >
          <Textarea
            value={reason}
            onChange={(event) => setReason(event.target.value)}
            className="min-h-[5rem] leading-relaxed"
          />
        </Field>
      </Modal>
    </>
  );
}

export function Changes({ entity }: Readonly<{ entity: string }>) {
  const { has } = useRoles();
  // Determining a change is the lead's: it opens a matter and commits the
  // organisation to producing paper.
  const canDecide = has("head_of_legal", "admin");
  const changes = useApi<ChangeRequest[]>("/change-requests", [entity]);
  const vocabulary = useApi<Vocabulary>("/lifecycle/vocabulary");
  const rows = changes.data ?? [];
  const pending = rows.filter((row) => row.decision === "pending").length;

  return (
    <div className="space-y-4">
      <Notice tone="info" title="No material change is made informally">
        A change that affects contractual rights is a document. Approving one opens a matter that
        drafts it, and the contract it produces points back at the one it changes rather than
        replacing it.
      </Notice>

      <Card>
        <CardHeader
          title={`${rows.length} ${rows.length === 1 ? "request" : "requests"}`}
          subtitle={pending ? `${pending} waiting on Legal` : "Nothing waiting"}
        />
        <div className="table-scroll">
          <div className="min-w-[58rem]">
            <Row cols={CHANGE_COLS} head>
              <div>What they want</div>
              <div>Kind</div>
              <div>Agreement</div>
              <div>Determination</div>
              <div className="text-right">Actions</div>
            </Row>
            <DataState
              loading={changes.loading}
              errorMessage={changes.error?.message}
              errorTitle="Change requests are not available to you"
              isEmpty={rows.length === 0}
              emptyTitle="No change has been asked for in this entity"
            >
              {rows.map((change) => (
                <Row key={change.id} cols={CHANGE_COLS}>
                  <div className="min-w-0">
                    <div className="line-clamp-2 text-sm leading-snug">
                      {change.proposed_changes}
                    </div>
                    <div className="mt-0.5 flex flex-wrap items-center gap-x-2 text-xs text-muted-foreground">
                      <Mono>{change.reference}</Mono>
                      <span>{change.requested_by_name}</span>
                    </div>
                  </div>
                  <div className="text-sm">
                    {say(vocabulary.data?.change_types, change.change_type)}
                  </div>
                  <div className="min-w-0">
                    <Mono>{change.contract_reference}</Mono>
                    <div className="truncate text-xs text-muted-foreground">
                      {change.counterparty_name}
                    </div>
                  </div>
                  <div className="min-w-0">
                    <Pill tone={DECISION_TONE[change.decision] ?? "neutral"}>
                      {say(vocabulary.data?.change_decisions, change.decision)}
                    </Pill>
                    {change.instrument ? (
                      <div className="mt-0.5 text-xs text-muted-foreground">
                        {say(vocabulary.data?.instruments, change.instrument)}
                      </div>
                    ) : null}
                  </div>
                  <div className="flex items-center justify-end gap-2">
                    {change.decision === "pending" && canDecide ? (
                      <Determine change={change} onDone={changes.reload} />
                    ) : change.resulting_matter_number ? (
                      <Link
                        href={`/workspace/matters/${change.resulting_matter_id}`}
                        className="no-underline"
                      >
                        <Button size="sm">{change.resulting_matter_number}</Button>
                      </Link>
                    ) : null}
                  </div>
                </Row>
              ))}
            </DataState>
          </div>
        </div>
      </Card>
    </div>
  );
}

