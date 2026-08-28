"use client";

import * as React from "react";

import {
  Button,
  Card,
  CardBody,
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
  Select,
  Spinner,
  Textarea,
} from "@/components/ui";
import { api } from "@/lib/api";
import { useAction, useApi } from "@/lib/hooks";
import type {
  ChangeRequest,
  Contract,
  ContractIssue,
  Term,
  Vocabulary,
} from "@/lib/types";
import { formatDate } from "@/lib/utils";

const STATUS_TONE: Record<string, "good" | "info" | "warn" | "neutral"> = {
  active: "good",
  executed: "good",
  in_closure: "warn",
  closed: "neutral",
  terminated: "neutral",
  lapsed: "neutral",
  superseded: "neutral",
};

function say(terms: Term[] | undefined, key: string | null): string {
  if (!key) return "Not set";
  return terms?.find((term) => term.key === key)?.label ?? key;
}

/*
  Telling Legal something has gone wrong.

  Section 15 of the guide makes the department running a contract responsible
  for performance and requires it to notify Legal promptly of breaches,
  disputes, material changes and performance concerns. Before this there was no
  channel: the department that noticed had an email address and Legal had a
  memory.
*/
function RaiseIssue({
  contract,
  vocabulary,
  onDone,
}: Readonly<{ contract: Contract; vocabulary: Vocabulary | null; onDone: () => void }>) {
  const [open, setOpen] = React.useState(false);
  const [issueType, setIssueType] = React.useState("delay");
  const [severity, setSeverity] = React.useState("material");
  const [title, setTitle] = React.useState("");
  const [description, setDescription] = React.useState("");
  const [occurredOn, setOccurredOn] = React.useState("");
  const [evidenceNote, setEvidenceNote] = React.useState("");

  const raise = useAction(async () => {
    await api(`/contracts/${contract.id}/issues`, {
      method: "POST",
      body: {
        issue_type: issueType,
        severity,
        title: title.trim(),
        description: description.trim(),
        occurred_on: occurredOn || null,
        evidence_note: evidenceNote.trim() || null,
      },
    });
    setTitle("");
    setDescription("");
    setEvidenceNote("");
    setOpen(false);
    onDone();
  });

  const ready = title.trim().length >= 5 && description.trim().length >= 20;

  return (
    <>
      <Button size="sm" onClick={() => setOpen(true)}>
        Report a problem
      </Button>
      <Modal
        open={open}
        title="Tell Legal something has gone wrong"
        subtitle={`${contract.reference}. Legal reads this and decides what to do about it.`}
        width="lg"
        onClose={() => setOpen(false)}
        footer={
          <>
            <Button onClick={() => setOpen(false)}>Cancel</Button>
            <Button variant="primary" disabled={!ready || raise.busy} onClick={() => void raise.run()}>
              Send it to Legal
            </Button>
          </>
        }
      >
        {raise.error ? (
          <Refusal
            title="That was not sent"
            reason={raise.error.message}
            reasons={raise.error.reasons}
          />
        ) : null}

        <div className="grid gap-3 sm:grid-cols-2">
          <Field label="What kind of problem" required>
            <Select value={issueType} onChange={(event) => setIssueType(event.target.value)}>
              {(vocabulary?.issue_types ?? []).map((term) => (
                <option key={term.key} value={term.key}>
                  {term.label}
                </option>
              ))}
            </Select>
          </Field>
          <Field
            label="How serious"
            hint="Your first impression. Legal will make its own assessment."
          >
            <Select value={severity} onChange={(event) => setSeverity(event.target.value)}>
              {(vocabulary?.severities ?? []).map((value) => (
                <option key={value} value={value}>
                  {value}
                </option>
              ))}
            </Select>
          </Field>
        </div>

        <Field label="In one line" required>
          <Input
            value={title}
            onChange={(event) => setTitle(event.target.value)}
            placeholder="The second milestone was not delivered on the agreed date"
          />
        </Field>

        <Field
          label="What happened"
          required
          hint="Dates, what was expected, what actually happened, and what you have already done about it."
        >
          <Textarea
            value={description}
            onChange={(event) => setDescription(event.target.value)}
            className="min-h-[7rem] leading-relaxed"
          />
        </Field>

        <div className="grid gap-3 sm:grid-cols-2">
          <Field label="When it happened">
            <Input
              type="date"
              value={occurredOn}
              onChange={(event) => setOccurredOn(event.target.value)}
            />
          </Field>
          <Field label="Evidence" hint="Where the proof is. Legal will ask for the file.">
            <Input
              value={evidenceNote}
              onChange={(event) => setEvidenceNote(event.target.value)}
              placeholder="Email thread of 3 August"
            />
          </Field>
        </div>
      </Modal>
    </>
  );
}

/*
  Asking for the paper to change.

  Section 16: no material change is implemented informally where it affects
  contractual rights or obligations. The department says what it wants and why;
  which instrument carries it is a legal question Legal answers.
*/
function RequestChange({
  contract,
  vocabulary,
  onDone,
}: Readonly<{ contract: Contract; vocabulary: Vocabulary | null; onDone: () => void }>) {
  const [open, setOpen] = React.useState(false);
  const [changeType, setChangeType] = React.useState("scope_change");
  const [rationale, setRationale] = React.useState("");
  const [proposed, setProposed] = React.useState("");
  const [financial, setFinancial] = React.useState("none");
  const [valueDelta, setValueDelta] = React.useState("");
  const [timeline, setTimeline] = React.useState("none");
  const [endDate, setEndDate] = React.useState("");

  const send = useAction(async () => {
    await api(`/contracts/${contract.id}/change-requests`, {
      method: "POST",
      body: {
        change_type: changeType,
        rationale: rationale.trim(),
        proposed_changes: proposed.trim(),
        financial_effect: financial,
        value_delta: valueDelta ? Number(valueDelta) : null,
        timeline_effect: timeline,
        proposed_end_date: endDate || null,
      },
    });
    setRationale("");
    setProposed("");
    setValueDelta("");
    setEndDate("");
    setOpen(false);
    onDone();
  });

  const ready = rationale.trim().length >= 20 && proposed.trim().length >= 10;

  return (
    <>
      <Button size="sm" onClick={() => setOpen(true)}>
        Ask for a change
      </Button>
      <Modal
        open={open}
        title="Ask for the agreement to change"
        subtitle={`${contract.reference}. Nothing changes until Legal prepares and both parties sign it.`}
        width="lg"
        onClose={() => setOpen(false)}
        footer={
          <>
            <Button onClick={() => setOpen(false)}>Cancel</Button>
            <Button variant="primary" disabled={!ready || send.busy} onClick={() => void send.run()}>
              Send it to Legal
            </Button>
          </>
        }
      >
        {send.error ? (
          <Refusal
            title="That was not sent"
            reason={send.error.message}
            reasons={send.error.reasons}
          />
        ) : null}

        <Notice tone="warn" title="Do not agree it with them first">
          A change agreed by email and never papered is a change neither side can rely on. Send it
          here, and Legal will tell you whether it needs an amendment.
        </Notice>

        <Field label="What do you want to change" required>
          <Select value={changeType} onChange={(event) => setChangeType(event.target.value)}>
            {(vocabulary?.change_types ?? []).map((term) => (
              <option key={term.key} value={term.key}>
                {term.label}
              </option>
            ))}
          </Select>
        </Field>

        <Field
          label="Why"
          required
          hint="This becomes the reason recorded on the amendment, so it is worth writing properly."
        >
          <Textarea
            value={rationale}
            onChange={(event) => setRationale(event.target.value)}
            className="min-h-[6rem] leading-relaxed"
          />
        </Field>

        <Field label="What specifically should change" required>
          <Textarea
            value={proposed}
            onChange={(event) => setProposed(event.target.value)}
            className="min-h-[5rem] leading-relaxed"
            placeholder="Extend the term by six months and move the final two milestones accordingly."
          />
        </Field>

        <div className="grid gap-3 sm:grid-cols-2">
          <Field label="Effect on the money">
            <Select value={financial} onChange={(event) => setFinancial(event.target.value)}>
              <option value="none">No change</option>
              <option value="increase">It costs more</option>
              <option value="decrease">It costs less</option>
              <option value="unknown">Not known yet</option>
            </Select>
          </Field>
          <Field label="How much, if known" hint={contract.value_currency}>
            <Input
              type="number"
              min={0}
              value={valueDelta}
              onChange={(event) => setValueDelta(event.target.value)}
            />
          </Field>
          <Field label="Effect on the dates">
            <Select value={timeline} onChange={(event) => setTimeline(event.target.value)}>
              <option value="none">No change</option>
              <option value="extends">It runs longer</option>
              <option value="shortens">It ends sooner</option>
              <option value="unknown">Not known yet</option>
            </Select>
          </Field>
          <Field label="Proposed end date">
            <Input
              type="date"
              value={endDate}
              onChange={(event) => setEndDate(event.target.value)}
            />
          </Field>
        </div>
      </Modal>
    </>
  );
}

function History({ contractId }: Readonly<{ contractId: string }>) {
  const issues = useApi<ContractIssue[]>(`/contracts/${contractId}/issues`, [contractId]);
  const changes = useApi<ChangeRequest[]>(`/contracts/${contractId}/change-requests`, [
    contractId,
  ]);
  const vocabulary = useApi<Vocabulary>("/lifecycle/vocabulary");

  const rows = issues.data ?? [];
  const asks = changes.data ?? [];
  if (issues.loading || changes.loading) return <Spinner />;
  if (rows.length === 0 && asks.length === 0) {
    return (
      <p className="text-sm text-muted-foreground">
        Nothing has been reported on this agreement.
      </p>
    );
  }

  return (
    <div className="space-y-2">
      {rows.map((issue) => (
        <div key={issue.id} className="rounded-md border p-3">
          <div className="flex flex-wrap items-center gap-2">
            <Mono>{issue.reference}</Mono>
            <Pill tone={issue.settled ? "good" : "warn"}>
              {say(vocabulary.data?.issue_statuses, issue.status)}
            </Pill>
            <span className="min-w-0 flex-1 truncate text-sm font-medium">{issue.title}</span>
          </div>
          {issue.resolution ? (
            <p className="mt-1.5 text-sm leading-relaxed">
              <span className="text-xs text-muted-foreground">Legal: </span>
              {issue.resolution}
            </p>
          ) : null}
        </div>
      ))}
      {asks.map((change) => (
        <div key={change.id} className="rounded-md border p-3">
          <div className="flex flex-wrap items-center gap-2">
            <Mono>{change.reference}</Mono>
            <Pill tone={change.decision === "pending" ? "warn" : "good"}>
              {say(vocabulary.data?.change_decisions, change.decision)}
            </Pill>
            <span className="min-w-0 flex-1 truncate text-sm">
              {say(vocabulary.data?.change_types, change.change_type)}
            </span>
          </div>
          {change.decision_reason ? (
            <p className="mt-1.5 text-sm leading-relaxed">
              <span className="text-xs text-muted-foreground">Legal: </span>
              {change.decision_reason}
              {change.resulting_matter_number
                ? ` Legal is preparing it under ${change.resulting_matter_number}.`
                : ""}
            </p>
          ) : null}
        </div>
      ))}
    </div>
  );
}

/*
  A department lead's signed agreements.

  Theirs and nobody else's. The guide makes them responsible for running the
  contract, and a person cannot be accountable for a record they cannot open,
  but the portfolio is not theirs to read either, so the API scopes it to the
  matters they raised.
*/
export default function PortalContracts() {
  const mine = useApi<Contract[]>("/contracts/mine");
  const vocabulary = useApi<Vocabulary>("/lifecycle/vocabulary");
  const rows = mine.data ?? [];

  return (
    <div className="space-y-6">
      <PageTitle
        title="Your agreements"
        subtitle={
          "Once an agreement is signed, your team runs it. Tell Legal when something goes wrong " +
          "and ask them when something needs to change."
        }
      />

      {mine.loading ? (
        <Spinner />
      ) : rows.length === 0 ? (
        <Empty
          title="No signed agreement came from your requests yet"
          detail="Agreements appear here once they have been signed by both parties."
        />
      ) : (
        <div className="space-y-4">
          {rows.map((contract) => (
            <Card key={contract.id}>
              <CardHeader
                title={
                  contract.counterparty?.legal_name ??
                  say(vocabulary.data?.agreement_types, contract.agreement_type)
                }
                subtitle={
                  <span className="flex flex-wrap items-center gap-2">
                    <Mono>{contract.reference}</Mono>
                    <Pill tone={STATUS_TONE[contract.status] ?? "neutral"}>
                      {say(vocabulary.data?.contract_statuses, contract.status)}
                    </Pill>
                    <span>{say(vocabulary.data?.agreement_types, contract.agreement_type)}</span>
                    {contract.end_date ? <span>Ends {formatDate(contract.end_date)}</span> : null}
                  </span>
                }
                actions={
                  contract.status === "closed" ||
                  contract.status === "terminated" ||
                  contract.status === "lapsed" ? undefined : (
                    <div className="flex flex-wrap gap-2">
                      <RaiseIssue
                        contract={contract}
                        vocabulary={vocabulary.data}
                        onDone={mine.reload}
                      />
                      <RequestChange
                        contract={contract}
                        vocabulary={vocabulary.data}
                        onDone={mine.reload}
                      />
                    </div>
                  )
                }
              />
              <CardBody className="space-y-3">
                {contract.termination_deadline ? (
                  <Notice tone="info" title="If you want to end this, say so by">
                    {`${formatDate(contract.termination_deadline)}. After that date the agreement runs to its end.`}
                  </Notice>
                ) : null}
                {contract.key_deliverables ? (
                  <div>
                    <div className="text-xs text-muted-foreground">What it requires</div>
                    <p className="whitespace-pre-wrap text-sm leading-relaxed">
                      {contract.key_deliverables}
                    </p>
                  </div>
                ) : null}
                <History contractId={contract.id} />
              </CardBody>
            </Card>
          ))}
        </div>
      )}
    </div>
  );
}
