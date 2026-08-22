"use client";

import Link from "next/link";
import { useParams } from "next/navigation";
import * as React from "react";

import { MatterActions } from "@/components/app/matter-actions";
import { useRoles } from "@/components/app/session";
import { DecisionPill, SlaPill, StatusPill, TierPill } from "@/components/app/status";
import {
  Button,
  Card,
  CardBody,
  CardHeader,
  Confirm,
  DataState,
  Empty,
  Field,
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
import type { AiInteraction, Approval, DocumentRecord, Matter } from "@/lib/types";
import { formatDate, formatDateTime, formatMoney, titleCase } from "@/lib/utils";

const APPROVAL_COLS = "minmax(0,1fr) 7.5rem 8.125rem 7.5rem 8.75rem 6.875rem";

function signatureTone(status: string): "good" | "bad" | "warn" {
  if (status === "completed") return "good";
  if (status === "cancelled") return "bad";
  return "warn";
}

type SignatureRow = {
  id: string;
  document_id: string;
  document_hash: string;
  provider: string;
  external_reference: string | null;
  signers: { name?: string; email?: string; party?: string }[];
  status: string;
  completed_at: string | null;
};

type DecisionRow = {
  id: string;
  sequence: number;
  decision: string;
  reason: string;
  authority_level: string;
  residual_risk_accepted: boolean;
  decided_at: string;
  clause_references: string[];
};

/*
  An approval decision is bound to the hash it was taken against. The dialog
  shows that hash so the approver is deciding on the thing in front of them,
  not on whatever the document later became.
*/
function ApprovalDecision({
  approval,
  onDone,
}: Readonly<{ approval: Approval; onDone: () => void }>) {
  const [open, setOpen] = React.useState(false);
  const [decision, setDecision] = React.useState("approved");
  const [comments, setComments] = React.useState("");

  const decide = useAction(async () => {
    await api(`/approvals/${approval.id}/decision`, {
      method: "POST",
      body: { decision, comments: comments || undefined },
    });
    onDone();
    setOpen(false);
    setComments("");
  });

  if (!approval.actionable) return null;

  return (
    <>
      <Button size="sm" variant="primary" onClick={() => setOpen(true)}>
        Decide
      </Button>
      <Modal
        open={open}
        title={approval.step_name}
        subtitle="Approving binds your decision to this exact document hash. Any later edit invalidates it and the step reopens."
        width="sm"
        onClose={() => setOpen(false)}
        footer={
          <>
            <Button onClick={() => setOpen(false)}>Cancel</Button>
            <Button
              variant={decision === "rejected" ? "destructive" : "primary"}
              disabled={decide.busy || (decision === "rejected" && !comments.trim())}
              onClick={() => void decide.run()}
            >
              Record the decision
            </Button>
          </>
        }
      >
        <Field label="Bound hash">
          <Mono>{approval.document_hash}</Mono>
        </Field>
        <Field label="Decision" required>
          <Select value={decision} onChange={(event) => setDecision(event.target.value)}>
            <option value="approved">Approve</option>
            <option value="rejected">Reject</option>
          </Select>
        </Field>
        <Field
          label="Comments"
          required={decision === "rejected"}
          hint="A rejection has to say what would change the answer."
        >
          <Textarea value={comments} onChange={(event) => setComments(event.target.value)} />
        </Field>
        {decide.error ? (
          <Refusal title="That decision was refused" reason={decide.error.message} reasons={decide.error.reasons} />
        ) : null}
      </Modal>
    </>
  );
}

function SignaturePanel({
  matterId,
  onChanged,
}: Readonly<{ matterId: string; onChanged: () => void }>) {
  const requests = useApi<SignatureRow[]>(`/matters/${matterId}/signature-requests`);
  const [cancelling, setCancelling] = React.useState<string | null>(null);
  const { has } = useRoles();

  const cancel = useAction(async (id: string, reason: string) => {
    await api(`/signature/requests/${id}/cancel${query({ reason })}`, { method: "POST" });
    requests.reload();
    onChanged();
    setCancelling(null);
  });

  const rows = requests.data ?? [];
  const cols = "9.375rem 7.5rem minmax(0,1fr) 8.75rem 6.25rem";

  return (
    <Card>
      <CardHeader
        title="Signature requests"
        subtitle="Each is bound to the hash that was approved. Cancelling one voids the counterparty link immediately."
      />
      <div className="table-scroll">
        <div className="min-w-[50rem]">
          <Row cols={cols} head>
            <div>Reference</div>
            <div>Status</div>
            <div>Signers</div>
            <div>Bound hash</div>
            <div>Action</div>
          </Row>
          <DataState
            loading={requests.loading}
            errorMessage={requests.error?.message}
            isEmpty={rows.length === 0}
            emptyTitle="No signature has been requested on this matter"
          >
            {rows.map((row) => (
              <Row key={row.id} cols={cols}>
                <Mono>{row.external_reference ?? row.id.slice(0, 12)}</Mono>
                <div>
                  <Pill tone={signatureTone(row.status)}>
                    {titleCase(row.status)}
                  </Pill>
                </div>
                <div className="min-w-0 truncate text-sm">
                  {row.signers.map((signer) => signer.name ?? signer.email).filter(Boolean).join(", ") ||
                    "None recorded"}
                </div>
                <Mono>{row.document_hash.slice(0, 12)}</Mono>
                <div>
                  {row.status === "sent" && has("counsel", "head_of_legal", "admin") ? (
                    <Button size="sm" variant="destructive" onClick={() => setCancelling(row.id)}>
                      Cancel
                    </Button>
                  ) : (
                    <span className="text-xs text-muted-foreground">
                      {row.completed_at ? formatDate(row.completed_at) : "Closed"}
                    </span>
                  )}
                </div>
              </Row>
            ))}
          </DataState>
        </div>
      </div>
      <Confirm
        open={cancelling !== null}
        title="Cancel this signature request"
        detail="The counterparty link stops working straight away, and the reason is recorded."
        confirmLabel="Cancel the request"
        destructive
        reasonLabel="Reason"
        busy={cancel.busy}
        error={cancel.error?.message}
        onCancel={() => setCancelling(null)}
        onConfirm={(reason) => void cancel.run(cancelling!, reason)}
      />
    </Card>
  );
}

/*
  Every AI output ends in a human decision. Recording it here is what closes
  the loop the register promises, and what the accuracy report later counts.
*/
function InteractionDecision({
  interaction,
  onDone,
}: Readonly<{ interaction: AiInteraction; onDone: () => void }>) {
  const [open, setOpen] = React.useState(false);
  const [decision, setDecision] = React.useState("accepted");
  const [correction, setCorrection] = React.useState("");

  const decide = useAction(async () => {
    await api(
      `/ai/interactions/${interaction.id}/decision${query({ decision, correction })}`,
      { method: "POST" },
    );
    onDone();
    setOpen(false);
  });

  if (interaction.refused || interaction.human_decision !== "pending") return null;

  return (
    <>
      <Button size="sm" onClick={() => setOpen(true)}>
        Record the decision
      </Button>
      <Modal
        open={open}
        title="What happened to this output"
        subtitle="Accepted, edited or rejected. The answer feeds the accuracy figures behind the capability gate."
        width="sm"
        onClose={() => setOpen(false)}
        footer={
          <>
            <Button onClick={() => setOpen(false)}>Cancel</Button>
            <Button variant="primary" disabled={decide.busy} onClick={() => void decide.run()}>
              Record it
            </Button>
          </>
        }
      >
        <Field label="Decision" required>
          <Select value={decision} onChange={(event) => setDecision(event.target.value)}>
            <option value="accepted">Accepted as written</option>
            <option value="edited">Accepted with edits</option>
            <option value="rejected">Rejected</option>
          </Select>
        </Field>
        {decision === "accepted" ? null : (
          <Field label="What it should have said" hint="Optional, and useful for the golden set.">
            <Textarea value={correction} onChange={(event) => setCorrection(event.target.value)} />
          </Field>
        )}
        {decide.error ? (
          <Refusal title="That decision was refused" reason={decide.error.message} />
        ) : null}
      </Modal>
    </>
  );
}

export default function MatterDetail() {
  const { matterId } = useParams<{ matterId: string }>();
  const [tab, setTab] = React.useState("overview");

  const matter = useApi<Matter>(`/matters/${matterId}`);
  const documents = useApi<DocumentRecord[]>(`/matters/${matterId}/documents`);
  const approvals = useApi<Approval[]>(`/matters/${matterId}/approvals`);
  const decisions = useApi<DecisionRow[]>(`/matters/${matterId}/decisions`);
  const trace = useApi<AiInteraction[]>(`/ai/interactions?matter_id=${matterId}`);

  const [target, setTarget] = React.useState("");
  const [reason, setReason] = React.useState("");

  const reloadAll = React.useCallback(() => {
    matter.reload();
    documents.reload();
    approvals.reload();
    decisions.reload();
    trace.reload();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  const transition = useAction(async () => {
    await api(`/matters/${matterId}/transitions`, {
      method: "POST",
      body: { to_state: target, reason: reason || undefined },
    });
    matter.reload();
    approvals.reload();
    setReason("");
  });

  if (matter.loading) return <Spinner />;
  if (matter.error) {
    return <Refusal title="That matter was not found" reason={matter.error.message} />;
  }

  const data = matter.data!;

  return (
    <div className="space-y-6">
      <PageTitle
        title={data.title}
        subtitle={
          <span className="flex flex-wrap items-center gap-2">
            <Mono>{data.number}</Mono>
            <TierPill tier={data.risk_tier} />
            <StatusPill status={data.status} />
            <SlaPill sla={data.sla} />
            {data.restricted ? <Pill tone="bad">&#128274; Restricted</Pill> : null}
            {data.privacy_flag ? <Pill tone="warn">&#9873; Privacy flag</Pill> : null}
          </span>
        }
        actions={
          <MatterActions
            matter={data}
            documents={documents.data ?? []}
            onChanged={reloadAll}
          />
        }
      />

      <Tabs
        tabs={[
          { id: "overview", label: "Overview" },
          { id: "documents", label: "Documents", badge: documents.data?.length },
          { id: "approvals", label: "Approvals", badge: approvals.data?.length },
          { id: "signature", label: "Signature" },
          { id: "decisions", label: "Decision log", badge: decisions.data?.length },
          { id: "ai", label: "AI trace", badge: trace.data?.length },
        ]}
        active={tab}
        onChange={setTab}
      />

      {tab === "overview" ? (
        <div className="grid gap-4 lg:gap-5 lg:grid-cols-[minmax(0,2fr)_minmax(0,1fr)]">
          <div className="space-y-4">
            <Card>
              <CardHeader title="Why this tier" subtitle="Derived by rule, recorded on the matter" />
              <CardBody>
                <ul className="space-y-1.5 text-sm">
                  {(data.tier_rationale ?? []).map((line) => (
                    <li key={line} className="flex gap-2 leading-relaxed">
                      <span aria-hidden className="text-muted-foreground">&bull;</span>
                      <span>{line}</span>
                    </li>
                  ))}
                </ul>
                {data.tier_overridden ? (
                  <Notice tone="warn" title="Tier overridden">
                    {data.tier_override_reason}
                  </Notice>
                ) : null}
              </CardBody>
            </Card>

            <Card>
              <CardHeader
                title="Move this matter"
                subtitle="The state model decides what is reachable from here"
              />
              <CardBody className="space-y-3">
                <div className="grid gap-3 sm:grid-cols-2">
                  <Field label="Next state">
                    <Select value={target} onChange={(event) => setTarget(event.target.value)}>
                      <option value="">Choose a state</option>
                      {(data.permitted_transitions ?? []).map((state) => (
                        <option key={state} value={state}>
                          {titleCase(state)}
                        </option>
                      ))}
                    </Select>
                  </Field>
                  <Field
                    label="Reason"
                    hint="Required for a reversal or a hold, recorded either way."
                  >
                    <Textarea
                      value={reason}
                      onChange={(event) => setReason(event.target.value)}
                      className="min-h-[34px]"
                    />
                  </Field>
                </div>
                {transition.error ? (
                  <Refusal title="That transition was refused" reason={transition.error.message} />
                ) : null}
                <Button
                  variant="primary"
                  disabled={!target || transition.busy}
                  onClick={() => void transition.run()}
                >
                  Record the transition
                </Button>
              </CardBody>
            </Card>
          </div>

          <Card>
            <CardHeader title="Record" />
            <CardBody className="space-y-2.5 text-sm">
              {(
                [
                  ["Counterparty", data.counterparty?.legal_name ?? "Not linked"],
                  ["Practice", data.practice_code],
                  ["Classification", titleCase(data.classification ?? "confidential")],
                  ["Value", formatMoney(data.value_amount ?? null, data.value_currency)],
                  ["Days open", String(data.days_open)],
                  ["Next action", data.next_action ?? "None recorded"],
                  ["Blocker", data.blocker ?? "None"],
                ] as const
              ).map(([label, value]) => (
                <div key={label} className="flex justify-between gap-3">
                  <span className="text-muted-foreground">{label}</span>
                  <span className="text-right font-medium">{value}</span>
                </div>
              ))}
            </CardBody>
          </Card>
        </div>
      ) : null}

      {tab === "documents" ? (
        <Card>
          <CardHeader title="Documents" subtitle="Each carries the template and clause versions it used" />
          <div>
            <Row cols="minmax(0,1fr) 6.875rem 6.875rem 8.125rem 5.625rem" head>
              <div>Name</div>
              <div>Type</div>
              <div>Novel clauses</div>
              <div>Hash</div>
              <div>Version</div>
            </Row>
            {documents.loading ? (
              <Spinner />
            ) : !documents.data?.length ? (
              <Empty title="No document has been generated on this matter yet" />
            ) : (
              documents.data.map((document) => (
                <Link
                  key={document.id}
                  href={`/workspace/documents/${document.id}`}
                  className="block text-foreground no-underline hover:bg-muted/60"
                >
                  <Row cols="minmax(0,1fr) 6.875rem 6.875rem 8.125rem 5.625rem">
                    <div className="truncate">{document.name}</div>
                    <div>
                      <Pill tone={document.immutable ? "good" : "neutral"}>
                        {titleCase(document.document_type)}
                      </Pill>
                    </div>
                    <div>
                      {document.novel_clause_count ? (
                        <Pill tone="novel">{document.novel_clause_count} novel</Pill>
                      ) : (
                        <span className="text-xs text-muted-foreground">All approved</span>
                      )}
                    </div>
                    <Mono>{document.content_hash.slice(0, 16)}</Mono>
                    <div className="text-xs">v{document.version}</div>
                  </Row>
                </Link>
              ))
            )}
          </div>
        </Card>
      ) : null}

      {tab === "approvals" ? (
        <Card>
          <CardHeader
            title="Approval chain"
            subtitle="Approval binds to an exact document hash. Any edit invalidates it."
          />
          <div>
            <Row cols={APPROVAL_COLS} head>
              <div>Step</div>
              <div>Decision</div>
              <div>Bound hash</div>
              <div>Due</div>
              <div>Decided</div>
              <div>Action</div>
            </Row>
            {approvals.loading ? (
              <Spinner />
            ) : !approvals.data?.length ? (
              <Empty
                title="No approval chain is open"
                detail="Generate a document and route it for approval to open one."
              />
            ) : (
              approvals.data.map((approval) => (
                <Row key={approval.id} cols={APPROVAL_COLS}>
                  <div>
                    <div className="font-medium">{approval.step_name}</div>
                    <div className="text-xs text-muted-foreground">
                      {titleCase(approval.approver_role ?? "assigned")}, {approval.step_mode}
                      {approval.actionable ? ", actionable now" : ""}
                    </div>
                  </div>
                  <div>
                    <DecisionPill decision={approval.decision} />
                  </div>
                  <Mono>{approval.document_hash.slice(0, 12)}</Mono>
                  <div className="text-xs text-muted-foreground">
                    {formatDateTime(approval.due_at)}
                  </div>
                  <div className="text-xs text-muted-foreground">
                    {approval.invalidated_by_event ?? formatDateTime(approval.decided_at)}
                  </div>
                  <div>
                    <ApprovalDecision approval={approval} onDone={reloadAll} />
                  </div>
                </Row>
              ))
            )}
          </div>
        </Card>
      ) : null}

      {tab === "signature" ? (
        <SignaturePanel matterId={matterId} onChanged={reloadAll} />
      ) : null}

      {tab === "decisions" ? (
        <Card>
          <CardHeader
            title="Decision log"
            subtitle="Entries cannot be silently deleted, only superseded, and they feed institutional memory."
          />
          <div>
            {decisions.loading ? (
              <Spinner />
            ) : !decisions.data?.length ? (
              <Empty title="No decision has been recorded on this matter" />
            ) : (
              decisions.data.map((decision) => (
                <div key={decision.id} className="border-b p-4 last:border-b-0">
                  <div className="flex flex-wrap items-center gap-2">
                    <Mono>Decision {decision.sequence}</Mono>
                    <Pill tone={decision.authority_level === "house" ? "neutral" : "novel"}>
                      {titleCase(decision.authority_level)}
                    </Pill>
                    {decision.residual_risk_accepted ? (
                      <Pill tone="warn">Residual risk accepted</Pill>
                    ) : null}
                    <span className="ml-auto text-xs text-muted-foreground">
                      {formatDateTime(decision.decided_at)}
                    </span>
                  </div>
                  <div className="mt-2 text-sm font-medium">{decision.decision}</div>
                  <div className="mt-1 text-sm text-muted-foreground">{decision.reason}</div>
                  {decision.clause_references.length ? (
                    <div className="mt-2 flex gap-1.5">
                      {decision.clause_references.map((reference) => (
                        <Mono key={reference}>{reference}</Mono>
                      ))}
                    </div>
                  ) : null}
                </div>
              ))
            )}
          </div>
        </Card>
      ) : null}

      {tab === "ai" ? (
        <Card>
          <CardHeader
            title="AI trace"
            subtitle="Every call on this matter, its route, its sources, and the human decision that followed."
          />
          <div>
            {trace.loading ? (
              <Spinner />
            ) : !trace.data?.length ? (
              <Empty
                title="No AI capability has run on this matter"
                detail="Nothing runs as an unnamed model call, so an empty trace means nothing ran."
              />
            ) : (
              trace.data.map((interaction) => (
                <div key={interaction.id} className="border-b p-4 last:border-b-0">
                  <div className="flex flex-wrap items-center gap-2">
                    <span className="text-sm font-medium">
                      {titleCase(interaction.capability_code)}
                    </span>
                    {interaction.refused ? (
                      <Pill tone="bad">Refused</Pill>
                    ) : (
                      <DecisionPill decision={interaction.human_decision} />
                    )}
                    {interaction.shadow ? <Pill tone="novel">Shadow mode</Pill> : null}
                    {interaction.injection_detected ? (
                      <Pill tone="bad">Injection detected</Pill>
                    ) : null}
                    <span className="ml-auto">
                      <Mono>
                        {interaction.provider} {interaction.model}, {interaction.latency_ms}ms,
                        {" "}
                        {interaction.retrieved_sources.length} sources
                      </Mono>
                    </span>
                  </div>
                  {interaction.refusal_reason ? (
                    <p className="mt-1.5 text-sm text-muted-foreground">
                      {interaction.refusal_reason}
                    </p>
                  ) : null}
                  <div className="mt-2 flex flex-wrap items-center justify-between gap-2">
                    <Mono>{interaction.interaction_id}</Mono>
                    <InteractionDecision interaction={interaction} onDone={reloadAll} />
                  </div>
                </div>
              ))
            )}
          </div>
        </Card>
      ) : null}
    </div>
  );
}
