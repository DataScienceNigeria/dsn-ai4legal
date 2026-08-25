"use client";

import Link from "next/link";
import { useParams } from "next/navigation";
import * as React from "react";

import { LinkCounterparty, MatterActions } from "@/components/app/matter-actions";
import { Rename } from "@/components/app/rename";
import { PlaceFields } from "@/components/app/place-fields";
import { RequestPanel } from "@/components/app/request-panel";
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
  KeyValue,
  Modal,
  Mono,
  Notice,
  PageTitle,
  Pill,
  Refusal,
  Ring,
  Row,
  Select,
  Spinner,
  type Stage,
  Stepper,
  Tabs,
  Textarea,
  Timeline,
  type TimelineStep,
} from "@/components/ui";
import { api, query, view } from "@/lib/api";
import { useAction, useApi } from "@/lib/hooks";
import type {
  AiInteraction,
  Approval,
  Contract,
  DocumentRecord,
  Extraction,
  Obligation,
  Matter,
  RequestDetail,
} from "@/lib/types";
import { formatDate, formatDateTime, formatMoney, titleCase } from "@/lib/utils";

/*
  A chain is a sequence, and the table it used to be did not say so: six equal
  columns, with the bound hash given the same weight as the step name. As a
  timeline the order is the spine, the state is the node, and the only filled
  node is the step waiting on somebody. The hash stays, because an approval
  means nothing without the document it was taken against, but it sits under
  the step rather than beside it.
*/
/*
  The journey, not the state column.

  The first attempt listed the raw states a matter can hold, so a matter whose
  status was "amended" showed Amended as step two of seven, between Accepted
  and In review, which is not a thing that happens. Worse, it answered "where
  are we" from one field when the answer is spread across the record: whether a
  document exists, whether a chain is open, whether anything has been signed.

  So each stage is derived from what is actually there. That also makes the
  track honest about work done outside the expected order, which is most work:
  a matter whose counterparty paper arrived before we drafted anything is past
  the document stage, whatever its status field says.
*/
type Progress = {
  documents: DocumentRecord[];
  approvals: Approval[];
  signatures: SignatureRow[];
  contract: Contract | null;
  obligations: number;
};

function lifecycle(matter: Matter, at: Progress, act: (id: string) => void): Stage[] {
  const ours = at.documents.filter((d) => d.document_type !== "counterparty");
  const paper = at.documents.filter((d) => d.document_type === "counterparty");
  const executed = at.documents.some((d) => d.immutable);
  const openChain = at.approvals.filter((a) => !a.invalidated_by_event);
  const approved = openChain.length > 0 && openChain.every((a) => a.decision === "approved");
  const signed = at.signatures.some((r) => r.status === "completed");
  const sent = at.signatures.some((r) => r.status === "sent");
  // A request that is out but has nowhere to sign is not really out yet.
  const placing = at.signatures.find((r) => r.placement_url)?.placement_url;
  const waitingOn = openChain.find((a) => a.actionable);

  /*
    Each stage says only whether it is finished. Which one is in hand follows
    from that: the first unfinished one, always, and never more than one.

    The first version had each stage decide for itself whether it was current,
    and a stage that was neither finished nor able to name a reason to call
    itself current came out "pending". So a matter with both approvals in and
    nothing sent had no current stage at all: approval was done, signature was
    pending because nothing had been sent, and the track went quiet at exactly
    the point somebody needed the button.
  */
  const stages: (Omit<Stage, "state"> & { done: boolean })[] = [
    {
      id: "created",
      label: "Matter opened",
      done: true,
      detail: `${matter.number}, opened ${formatDate(matter.created_at ?? null)}.`,
    },
    {
      id: "document",
      label: "Drafting",
      done: at.documents.length > 0,
      detail: at.documents.length
        ? `${ours.length} of ours, ${paper.length} of theirs.`
        : "Nothing to work from yet. Assemble ours from a template, or add the draft they sent.",
      action: (
        <>
          <Button variant="primary" onClick={() => act("generate")}>
            Generate a document
          </Button>
          <Button onClick={() => act("paper")}>Add their paper</Button>
        </>
      ),
    },
    {
      id: "approval",
      label: "Approval",
      done: approved,
      detail: approved
        ? "Both parties confirmed."
        : waitingOn
          ? `Waiting on ${waitingOn.approver_name ?? waitingOn.step_name}.`
          : openChain.length
            ? "A chain is open."
            : "Nobody has been asked. Routing binds every approval to one document hash.",
      action: openChain.length ? (
        <Button variant="primary" onClick={() => act("open-approvals")}>
          Open the approvals
        </Button>
      ) : (
        <Button
          variant="primary"
          disabled={ours.length === 0}
          onClick={() => act("approval")}
        >
          Route for approval
        </Button>
      ),
    },
    {
      id: "signature",
      label: "Signature",
      done: signed,
      detail: signed
        ? "Executed by every party."
        : placing
          ? "Requested. Nothing yet says where on the page each party signs."
          : sent
            ? "Out for signature. Execution is recorded when the service reports it back."
            : approved
              ? "Both approvals are in, so this document can be sent."
              : "Only an approved hash can be sent, so approval comes first.",
      action: placing ? (
        <Button variant="primary" onClick={() => act("open-signature")}>
          Place the signature fields
        </Button>
      ) : (
        <>
          <Button variant="primary" disabled={!approved} onClick={() => act("signature")}>
            {sent ? "Send another request" : "Request a signature"}
          </Button>
          <Button disabled={!approved} onClick={() => act("wetink")}>
            Signed on paper
          </Button>
        </>
      ),
    },
    /*
      The last stage, and it is the last on purpose.

      There used to be a "Live" stage after this one, and nothing in the
      platform ever reached it: no code moves a matter to active, so the
      stepper ended on a step that could not complete. Worse, its action was a
      link to the archive, which meant a button naming an action it did not
      perform, and a reader who followed it landed on a screen whose only link
      back was to the matter they had just left.

      Execution ends the legal work. What follows belongs to the agreement, so
      the action here is the handover: extract the duties, then read them where
      duties live.
    */
    {
      id: "executed",
      label: "Executed",
      done: executed,
      detail: executed
        ? at.obligations > 0
          ? `The executed copy is archived. ${at.obligations} ${at.obligations === 1 ? "duty" : "duties"} came out of it.`
          : "The executed copy is archived. Its duties have not been drawn out of it yet."
        : "Recorded when the last signature lands.",
      action:
        executed && at.contract ? (
          <Link
            href={`/workspace/archive/${at.contract.id}/obligations`}
            className="no-underline"
          >
            <Button variant="primary">What the agreement requires</Button>
          </Link>
        ) : undefined,
    },
  ];

  const here = stages.findIndex((stage) => !stage.done);
  return stages.map(({ done, ...stage }, index) => ({
    ...stage,
    state: done ? "done" : index === here ? "current" : "pending",
  }));
}

/*
  One party's decision, as a card. What the reader wants to know is whose desk
  it is on, what they are being asked, and whether they have answered, and the
  timeline row said none of those: it led with a step name and a role.

  The two steps ask genuinely different questions. The business knows whether
  the draft is the arrangement they agreed; Legal knows whether the wording is
  safe to sign. Saying which is which is most of what this card is for.
*/
const ASKS: Record<string, { who: string; question: string }> = {
  requester: {
    who: "The business",
    question: "Is this the arrangement we asked for?",
  },
  head_of_legal: {
    who: "Head of Legal",
    question: "Is this safe to sign?",
  },
};

function ApprovalCard({
  approval,
  onDone,
}: Readonly<{ approval: Approval; onDone: () => void }>) {
  const asked = ASKS[approval.approver_role ?? ""] ?? {
    who: titleCase(approval.approver_role ?? "Assigned"),
    question: approval.step_name,
  };

  const invalidated = Boolean(approval.invalidated_by_event);
  const decided = approval.decision === "approved" || approval.decision === "rejected";
  const askedForChanges = Boolean(approval.comments) && !decided && !invalidated;

  const tone = invalidated
    ? "bad"
    : approval.decision === "approved"
      ? "good"
      : approval.decision === "rejected"
        ? "bad"
        : askedForChanges
          ? "warn"
          : approval.actionable
            ? "info"
            : "neutral";

  const state = invalidated
    ? "Invalidated"
    : approval.decision === "approved"
      ? "Confirmed"
      : approval.decision === "rejected"
        ? "Rejected"
        : askedForChanges
          ? "Changes asked for"
          : approval.actionable
            ? "Waiting on them"
            : "Not yet asked";

  return (
    <Card className={approval.actionable && !decided ? "border-brand" : undefined}>
      <CardHeader
        title={asked.who}
        subtitle={approval.approver_name ?? "Nobody holds this role in this entity"}
        actions={<Pill tone={tone}>{state}</Pill>}
      />
      <CardBody className="space-y-3">
        <p className="text-sm leading-relaxed text-muted-foreground">{asked.question}</p>

        {approval.comments ? (
          <div className="rounded-md border border-warning/40 bg-warning/10 p-3 text-sm leading-relaxed">
            <div className="text-xs font-semibold uppercase tracking-wide text-muted-foreground">
              {decided ? "They said" : "They asked for"}
            </div>
            <p className="mt-1">{approval.comments}</p>
          </div>
        ) : null}

        <div className="text-xs text-muted-foreground">
          {invalidated
            ? approval.invalidated_by_event
            : decided
              ? `${approval.decision === "approved" ? "Confirmed" : "Rejected"} ${formatDateTime(approval.decided_at)}`
              : approval.due_at
                ? `Expected by ${formatDateTime(approval.due_at)}`
                : "No date set"}
        </div>

        <ApprovalDecision approval={approval} onDone={onDone} />
      </CardBody>
    </Card>
  );
}

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
  placement_url: string | null;
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
  documents,
  onChanged,
}: Readonly<{ matterId: string; documents: DocumentRecord[]; onChanged: () => void }>) {
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
  const waiting = rows.find((row) => row.placement_url);
  const executedCopy = documents.find((document) => document.signed_copy_held);

  const openSigned = useAction(async () => {
    await view(`/documents/${executedCopy!.id}/signed`);
  });
  const cols = "9.375rem 7.5rem minmax(0,1fr) 8.75rem 6.25rem";

  return (
    <Card>
      <CardHeader
        title="Signature requests"
        subtitle="Each is bound to the hash that was approved. Cancelling one voids the counterparty link immediately."
      />
      {/*
        Where the fields go on the page.

        Placing a signature box on a PDF is dragging a box onto a PDF, and the
        signing service already does it: pdf.js on one side, the same code that
        later stamps the signature on the other, so the coordinates are correct
        by construction. Reimplementing it here would mean reverse-engineering
        a coordinate system defined by somebody else's client, and getting the
        page origin subtly wrong puts a signature in the margin of an executed
        agreement, which is not a fault anybody finds before it matters.

        So the platform decides what may be sent, to whom, and against which
        approved hash. The placement screen decides where on the page. The
        handoff is a link rather than an embedded frame, because their screen
        wearing our chrome would be neither.
      */}
      {waiting ? (
        <CardBody className="border-b">
          <Notice tone="warn" title="The fields have not been placed yet">
            Signers were told to expect this, but nothing says where on the page they sign.
            Open the placement screen, drag a signature box onto each party's line, and send
            from there.
            <div className="mt-2.5 flex flex-wrap items-center gap-2">
              <PlaceFields
                requestId={waiting.id}
                fallbackUrl={waiting.placement_url!}
                onClosed={() => requests.reload()}
              />
            </div>
          </Notice>
        </CardBody>
      ) : null}

      {executedCopy ? (
        <CardBody className="border-b">
          <Notice tone="good" title="The signed agreement is held here">
            Signatures appear on the file the signing service stamped, not on the wording
            this platform assembled. That file is in the archive under object lock.
            <div className="mt-2.5">
              <Button size="sm" variant="primary" onClick={() => void openSigned.run()}>
                {openSigned.busy ? "Opening" : "Open the signed agreement"}
              </Button>
            </div>
            {openSigned.error ? (
              <Refusal title="It could not be opened" reason={openSigned.error.message} />
            ) : null}
          </Notice>
        </CardBody>
      ) : null}

      {rows.length ? (
        <CardBody className="border-b">
          <Ring
            done={rows.filter((row) => row.status === "completed").length}
            total={rows.length}
            label="requests executed"
            detail={
              /*
                Requests, not signers. The internal provider reports a request
                as sent or completed and never reports who has signed within
                it, so a signer-by-signer figure would be a number the platform
                does not hold. It is not shown rather than estimated.
              */
              rows.some((row) => row.status === "sent")
                ? "One or more requests are still out. Signer-level progress is not reported by the provider."
                : "Every request on this matter has closed."
            }
          />
        </CardBody>
      ) : null}
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
  /*
    The track reads the record rather than the status field, so it needs to
    know whether anything has been sent for signature.
  */
  const signatures = useApi<SignatureRow[]>(`/matters/${matterId}/signature-requests`);
  /*
    What the track asked for. Most are dialogs the actions component owns; one,
    opening the approvals, is a tab on this page, so it is handled here and
    never reaches the dialogs.
  */
  const [act, setAct] = React.useState("");

  const decisions = useApi<DecisionRow[]>(`/matters/${matterId}/decisions`);
  const trace = useApi<AiInteraction[]>(`/ai/interactions?matter_id=${matterId}`);
  const request = useApi<RequestDetail | null>(`/matters/${matterId}/request`);
  const contracts = useApi<Contract[]>(`/contracts?matter_id=${matterId}`);
  const obligations = useApi<Obligation[]>(`/obligations?matter_id=${matterId}`);

  React.useEffect(() => {
    if (act === "open-approvals") {
      setTab("approvals");
      setAct("");
    } else if (act === "open-signature") {
      setTab("signature");
      setAct("");
    }
  }, [act]);

  const [target, setTarget] = React.useState("");
  const [reason, setReason] = React.useState("");

  const reloadAll = React.useCallback(() => {
    matter.reload();
    documents.reload();
    approvals.reload();
    signatures.reload();
    decisions.reload();
    trace.reload();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  /*
    Everything permitted that the track above does not already offer: a hold,
    an escalation, a reversal. Forward moves belong on the track, and listing
    them twice invites the reader to wonder whether the two do the same thing.
  */
  const detours = matter.data?.permitted_transitions ?? [];

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
        title={
          <span className="inline-flex flex-wrap items-center gap-1.5">
            {data.title}
            <Rename
              inline
              path={`/matters/${matterId}`}
              field="title"
              label="matter"
              current={data.title}
              onDone={reloadAll}
            />
          </span>
        }
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
            attachments={request.data?.attachments ?? []}
            requested={act}
            onRequestHandled={() => setAct("")}
            onChanged={reloadAll}
          />
        }
      />

      {/*
        Where the matter is, and the moves it can make from here. This was a
        status pill and a dropdown of state names, and neither said what came
        next or what had already happened.
      */}
      <Stepper
        stages={lifecycle(
          data,
          {
            documents: documents.data ?? [],
            approvals: approvals.data ?? [],
            signatures: signatures.data ?? [],
            contract: contracts.data?.[0] ?? null,
            obligations: obligations.data?.length ?? 0,
          },
          setAct,
        )}
        note={
          data.next_action ? (
            <span>
              Next: <span className="text-foreground">{data.next_action}</span>
              {data.blocker ? (
                <span className="text-warning-foreground dark:text-warning">
                  {" "}
                  Blocked: {data.blocker}
                </span>
              ) : null}
            </span>
          ) : null
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

      {/*
        One column of what was asked for, one of what the record now says.
        This was four boxes: the request, a card holding a single sentence of
        tier rationale, a form duplicating the moves the spine above already
        offers, and the record. Four headings for one subject, and the reader
        had to assemble the matter from them.

        The forward moves live in the spine. What is left here is the moves
        that are not forward, a hold, an escalation, a reversal, and those
        carry a reason, so they are a deliberate control rather than a
        dropdown of every state name the machine will accept.
      */}
      {tab === "overview" ? (
        <div className="grid gap-4 lg:gap-5 lg:grid-cols-[minmax(0,1.6fr)_minmax(0,1fr)]">
          {request.data ? (
            <RequestPanel
              request={request.data}
              facts={false}
              title="What was asked for"
              subtitle="The request this matter came from, in the requester's own words."
            />
          ) : (
            <Card>
              <CardHeader title="What was asked for" />
              <CardBody>
                <Empty
                  title="No request is linked to this matter"
                  detail="It was raised inside Legal rather than through the portal."
                />
              </CardBody>
            </Card>
          )}

          <Card>
            <CardHeader
              title="This matter"
              subtitle="What the record holds, and what a document is assembled from"
              actions={<LinkCounterparty matter={data} onDone={reloadAll} />}
            />
            <CardBody className="space-y-4">
              <KeyValue
                rows={
                  [
                    [
                      "Counterparty",
                      data.counterparty?.legal_name ?? "Not linked yet",
                    ],
                    ["Value", formatMoney(data.value_amount ?? null, data.value_currency)],
                    ["Classification", titleCase(data.classification ?? "confidential")],
                    ["Practice", data.practice_code],
                    [
                      "Open",
                      `${data.days_open} days, since ${formatDate(data.created_at ?? null)}`,
                    ],
                    ...(data.blocker ? [["Blocked by", data.blocker] as const] : []),
                  ] as [string, React.ReactNode][]
                }
              />

              {/*
                The tier and why it is the tier, together. A rule that produced
                a decision and the decision it produced are one fact, and they
                were a heading apart.
              */}
              <div className="border-t pt-3">
                <div className="flex items-baseline justify-between gap-3">
                  <span className="text-sm text-muted-foreground">Risk tier</span>
                  <TierPill tier={data.risk_tier} />
                </div>
                <ul className="mt-1.5 space-y-1 text-xs leading-relaxed text-muted-foreground">
                  {(data.tier_rationale ?? ["No rationale was recorded."]).map((line) => (
                    <li key={line}>{line}</li>
                  ))}
                </ul>
                {data.tier_overridden ? (
                  <Notice tone="warn" title="Overridden by hand">
                    {data.tier_override_reason}
                  </Notice>
                ) : null}
              </div>

              {detours.length ? (
                <div className="border-t pt-3">
                  <div className="text-sm text-muted-foreground">Other moves</div>
                  <div className="mt-2 flex flex-wrap gap-2">
                    {detours.map((state) => (
                      <Button key={state} size="sm" onClick={() => setTarget(state)}>
                        {titleCase(state)}
                      </Button>
                    ))}
                  </div>
                  <p className="mt-2 text-xs leading-relaxed text-muted-foreground">
                    Forward moves are on the track above. These are the ones that are not
                    forward, and each is recorded with the reason given.
                  </p>
                </div>
              ) : null}
            </CardBody>
          </Card>
        </div>
      ) : null}

      <Modal
        open={Boolean(target)}
        title={`Move to ${titleCase(target || "")}`}
        subtitle="Recorded as a transition against this matter, with the reason and who made it."
        width="sm"
        onClose={() => {
          setTarget("");
          setReason("");
        }}
        footer={
          <>
            <Button
              onClick={() => {
                setTarget("");
                setReason("");
              }}
            >
              Cancel
            </Button>
            <Button
              variant="primary"
              disabled={transition.busy}
              onClick={() => void transition.run()}
            >
              {transition.busy ? "Recording" : "Record the move"}
            </Button>
          </>
        }
      >
        <Field
          label="Reason"
          hint="Required for a reversal or a hold, and recorded either way."
        >
          <Textarea value={reason} onChange={(event) => setReason(event.target.value)} />
        </Field>
        {transition.error ? (
          <Refusal
            title="That move was refused"
            reason={transition.error.message}
            reasons={transition.error.reasons}
          />
        ) : null}
      </Modal>

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
                    <div className="flex min-w-0 items-center gap-2">
                      <span className="truncate">{document.name}</span>
                      {/*
                        The wording and the signed file are two things. The
                        blocks are what the document says, and they say what
                        they said before anybody signed; the signatures exist
                        only on the file the signing service stamped, which is
                        held here rather than linked to, because an archive
                        that is a link into somebody else's service is an
                        archive until that service changes.
                      */}
                      {document.signed_copy_held ? (
                        <Pill tone="good">Signed copy held</Pill>
                      ) : null}
                    </div>
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

      {/*
        Two parties, two cards. It was a ring and a vertical timeline, which is
        the right shape for a chain of four or five and overkill for two: the
        ring said "1 of 2" where the cards say which one, and the timeline
        spent a column on the bound hash that is the same on every row.

        The hash sits once at the top, where it belongs. It is a property of
        the document both parties are deciding about, not of either decision.
      */}
      {tab === "approvals" ? (
        approvals.loading ? (
          <Spinner />
        ) : !approvals.data?.length ? (
          <Card>
            <CardBody>
              <Empty
                title="Nobody has been asked yet"
                detail="Route a document for approval and both parties are asked against the same version of it."
              />
            </CardBody>
          </Card>
        ) : (
          <div className="space-y-3">
            {/*
              Two cards, one row, and nothing above them. A summary card
              restating the count the two cards already show is a third thing
              to read before reading the two things.
            */}
            <div className="grid gap-4 lg:gap-5 md:grid-cols-2">
              {approvals.data.map((approval) => (
                <ApprovalCard key={approval.id} approval={approval} onDone={reloadAll} />
              ))}
            </div>

            {/*
              The hash belongs once, under both. It is a property of the
              document they are both deciding about, not of either decision,
              and it was a column on every row of the table this replaced.
            */}
            <div className="flex flex-wrap items-baseline gap-x-3 gap-y-1 text-xs text-muted-foreground">
              <span>
                Both decide against{" "}
                <Mono>{approvals.data[0].document_hash.slice(0, 16)}</Mono>
              </span>
              <span>Any edit to it invalidates every decision already given.</span>
            </div>

            {approvals.data[0].notes.length ? (
              <ul className="space-y-1 text-xs leading-relaxed text-muted-foreground">
                {approvals.data[0].notes.map((line) => (
                  <li key={line}>{line}</li>
                ))}
              </ul>
            ) : null}
          </div>
        )
      ) : null}

      {tab === "signature" ? (
        <SignaturePanel
          matterId={matterId}
          documents={documents.data ?? []}
          onChanged={reloadAll}
        />
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
