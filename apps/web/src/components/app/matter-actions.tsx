"use client";

import Link from "next/link";
import * as React from "react";

import { useRoles } from "@/components/app/session";
import { StepUpGate } from "@/components/app/step-up";
import {
  Actions,
  Button,
  Confirm,
  Field,
  Input,
  MenuItem,
  Modal,
  More,
  Notice,
  Refusal,
  Select,
  Spinner,
  Textarea,
} from "@/components/ui";
import { api, query, upload } from "@/lib/api";
import { useAction, useApi } from "@/lib/hooks";
import type {
  AttachmentBrief,
  CounterpartyRow,
  DocumentRecord,
  Finding,
  Matter,
  Template,
  TemplatePlaceholder,
  UserRow,
} from "@/lib/types";
import { titleCase } from "@/lib/utils";

const TIERS = ["tier_1", "tier_2", "tier_3", "tier_4"];
const LINK_TYPES = ["related", "supersedes", "amends", "parent", "child"];

type Variable = { name: string; label?: string; mandatory?: boolean; type?: string };

/*
  A template declares the variables it needs. The generator supplies the ones
  it can read off the matter, so only the remainder is asked for here. Asking
  for the whole set would invite someone to retype a value the record already
  holds and disagree with it.
*/
const SUPPLIED_BY_THE_MATTER = new Set([
  "matter_number",
  "our_entity",
  "counterparty",
  "counterparty_jurisdiction",
  "effective_date",
  "governing_law",
  "value_amount",
  "value_currency",
  "privacy_flag",
]);

function useTemplates(entity: string) {
  const templates = useApi<Template[]>("/templates", [entity]);
  return (templates.data ?? []).filter(
    (template) => template.current?.status === "approved",
  );
}

/*
  A template authored here declares its merge fields. One that arrived as a
  Word file does not: it was written for a person to fill in, so its blanks
  read [Company Name] rather than {{company_name}}. The API derives those from
  the body and says which the matter already answers, so the two kinds of
  template ask the same way and only the remainder is put to anyone.
*/
function FactFields({
  variables,
  placeholders,
  facts,
  onChange,
}: Readonly<{
  variables: Variable[];
  placeholders: TemplatePlaceholder[];
  facts: Record<string, string>;
  onChange: (name: string, value: string) => void;
}>) {
  const declared = variables
    .filter((variable) => !SUPPLIED_BY_THE_MATTER.has(variable.name))
    .map((variable) => ({
      name: variable.name,
      label: variable.label ?? titleCase(variable.name),
      mandatory: variable.mandatory !== false,
    }));

  const blanks = placeholders
    .filter((placeholder) => !placeholder.supplied)
    .filter((placeholder) => !declared.some((field) => field.name === placeholder.name))
    .map((placeholder) => ({
      name: placeholder.name,
      label: placeholder.label,
      mandatory: true,
    }));

  const answered = placeholders.filter((placeholder) => placeholder.supplied);
  const asked = [...declared, ...blanks];

  if (asked.length === 0) {
    return (
      <Notice tone="good" title="Everything this template needs is already on the matter">
        {answered.length
          ? `${answered.length} blanks fill from the record, so the document assembles as it stands.`
          : "No further facts are required, so the document assembles from the record as it stands."}
      </Notice>
    );
  }

  return (
    <div className="space-y-3">
      {answered.length ? (
        <Notice tone="info" title={`${answered.length} blanks fill from the matter`}>
          {answered.map((placeholder) => placeholder.label).join(", ")}. These are taken from
          the record rather than typed, so the document cannot disagree with it.
        </Notice>
      ) : null}
      <div className="grid gap-3 sm:grid-cols-2">
        {asked.map((field) => (
          <Field
            key={field.name}
            label={field.label}
            required={field.mandatory}
            hint={
              field.mandatory
                ? "The template leaves this blank and the matter does not answer it."
                : "Left blank, this appears as an open item."
            }
          >
            <Input
              value={facts[field.name] ?? ""}
              onChange={(event) => onChange(field.name, event.target.value)}
            />
          </Field>
        ))}
      </div>
    </div>
  );
}

function GenerateDialog({
  matter,
  open,
  onClose,
  onDone,
}: Readonly<{ matter: Matter; open: boolean; onClose: () => void; onDone: () => void }>) {
  const templates = useTemplates(matter.entity);
  const [code, setCode] = React.useState("");
  const [name, setName] = React.useState("");
  const [facts, setFacts] = React.useState<Record<string, string>>({});
  const [autoIssue, setAutoIssue] = React.useState(false);

  const chosen = templates.find((template) => template.code === code);
  const variables = (chosen?.current?.variables ?? []) as unknown as Variable[];

  const generate = useAction(async () => {
    if (!chosen?.current) return;
    const body = {
      template_reference: chosen.current.reference,
      matter_id: matter.id,
      facts,
      name: name || undefined,
    };
    if (autoIssue) {
      await api(`/matters/${matter.id}/auto-issue`, {
        method: "POST",
        body: { template_reference: body.template_reference, facts, name: body.name },
      });
    } else {
      await api("/documents/generate", { method: "POST", body });
    }
    onDone();
    onClose();
  });

  const tierOne = matter.risk_tier === "tier_1";

  return (
    <Modal
      open={open}
      dismissible={!generate.busy}
      title="Generate a document"
      subtitle="Assembly is deterministic. The same template, the same facts and the same clause versions always produce the same bytes and the same hash."
      onClose={onClose}
      footer={
        <>
          <Button onClick={onClose}>Cancel</Button>
          <Button
            variant="primary"
            disabled={!chosen?.current || generate.busy}
            onClick={() => void generate.run()}
          >
            {autoIssue ? "Assemble and issue" : "Assemble the document"}
          </Button>
        </>
      }
    >
      {generate.busy ? <Spinner label="Assembling the document" /> : null}

      <Field label="Template" required hint="Only approved versions can generate.">
        <Select value={code} onChange={(event) => setCode(event.target.value)}>
          <option value="">Choose a template</option>
          {templates.map((template) => (
            <option key={template.code} value={template.code}>
              {template.name}, {template.current?.reference}
            </option>
          ))}
        </Select>
      </Field>

      <Field label="Document name" hint="Left blank, the template name and matter number are used.">
        <Input value={name} onChange={(event) => setName(event.target.value)} />
      </Field>

      {chosen ? (
        <FactFields
          variables={variables}
          placeholders={chosen.current?.placeholders ?? []}
          facts={facts}
          onChange={(key, value) => setFacts((previous) => ({ ...previous, [key]: value }))}
        />
      ) : null}

      {tierOne ? (
        <label className="flex items-start gap-2.5 rounded-md border p-3 text-sm">
          <input
            type="checkbox"
            aria-label="Issue without review"
            checked={autoIssue}
            onChange={(event) => setAutoIssue(event.target.checked)}
            className="mt-0.5"
          />
          <span>
            <span className="font-medium">Issue without review</span>
            <span className="mt-0.5 block text-muted-foreground">
              Tier 1 only, and only when every eligibility condition holds. The API checks them
              again and refuses with reasons if any fails. A sample of issued documents is pulled
              for review each month.
            </span>
          </span>
        </label>
      ) : null}

      {generate.error ? (
        <Refusal
          title="That document was not generated"
          reason={generate.error.message}
          reasons={generate.error.reasons}
        />
      ) : null}
    </Modal>
  );
}

function DraftDialog({
  matterId,
  open,
  onClose,
  onDone,
}: Readonly<{ matterId: string; open: boolean; onClose: () => void; onDone: () => void }>) {
  const [brief, setBrief] = React.useState("");

  const draft = useAction(async () => {
    await api(`/ai/draft/${matterId}${query({ brief })}`, { method: "POST" });
    onDone();
    onClose();
    setBrief("");
  });

  return (
    <Modal
      open={open}
      dismissible={!draft.busy}
      title="Ask for a first draft"
      subtitle="The model drafts from approved clauses and the brief below. Anything it invents is marked novel and cannot be issued without a human decision."
      onClose={onClose}
      footer={
        <>
          <Button onClick={onClose}>Cancel</Button>
          <Button
            variant="primary"
            disabled={brief.trim().length < 10 || draft.busy}
            onClick={() => void draft.run()}
          >
            Draft it
          </Button>
        </>
      }
    >
      {draft.busy ? <Spinner label="Drafting from the approved clause library" /> : null}

      <Field
        label="Brief"
        required
        hint="What the agreement has to achieve, who the parties are, and anything unusual about it."
      >
        <Textarea
          value={brief}
          onChange={(event) => setBrief(event.target.value)}
          className="min-h-[9rem]"
        />
      </Field>
      {draft.error ? (
        <Refusal
          title="The draft was refused"
          reason={draft.error.message}
          reasons={draft.error.reasons}
        />
      ) : null}
    </Modal>
  );
}

/*
  Their paper has to reach the platform before it can be measured against
  anything, and until now there was no way to put it there. The review runs
  over the clauses in a document, and the only documents that existed were the
  ones we generated ourselves, so "Review counterparty paper" was reviewing our
  own draft against our own playbook.

  Two ways in, because paper arrives two ways. Most of it comes attached to the
  original request, so that path copies it across without asking anyone to
  find the file again; the rest arrives later by email and is uploaded here.
*/
function PaperDialog({
  matterId,
  attachments,
  open,
  onClose,
  onDone,
}: Readonly<{
  matterId: string;
  attachments: AttachmentBrief[];
  open: boolean;
  onClose: () => void;
  onDone: () => void;
}>) {
  const [file, setFile] = React.useState<File | null>(null);

  const send = useAction(async () => {
    if (!file) return;
    await upload(`/matters/${matterId}/paper`, file);
    setFile(null);
    onDone();
    onClose();
  });

  const adopt = useAction(async (attachmentId: string) => {
    await api(`/matters/${matterId}/paper/from-attachment/${attachmentId}`, { method: "POST" });
    onDone();
    onClose();
  });

  const word = attachments.filter((a) => a.filename.toLowerCase().endsWith(".docx"));
  const failed = send.error ?? adopt.error;

  return (
    <Modal
      open={open}
      title="Add the counterparty's paper"
      subtitle="Their draft is held for comparison only. Nothing in it is house position, and it cannot be approved or signed."
      onClose={onClose}
      footer={
        <>
          <Button onClick={onClose}>Cancel</Button>
          <Button variant="primary" disabled={!file || send.busy} onClick={() => void send.run()}>
            {send.busy ? "Reading" : "Add the paper"}
          </Button>
        </>
      }
    >
      {word.length ? (
        <Field
          label="It came with the request"
          hint="Copied across as it arrived, so you are reading the bytes the requester sent."
        >
          <div className="space-y-1.5">
            {word.map((attachment) => (
              <Button
                key={attachment.id}
                className="w-full justify-start"
                disabled={adopt.busy}
                onClick={() => void adopt.run(attachment.id)}
              >
                {attachment.filename}
              </Button>
            ))}
          </div>
        </Field>
      ) : null}

      <Field
        label="Or upload it"
        required={word.length === 0}
        hint="Word only. The review reads it clause by clause, so it needs the document rather than a picture of one."
      >
        <Input
          type="file"
          accept=".docx"
          onChange={(event) => setFile(event.target.files?.[0] ?? null)}
        />
      </Field>

      {failed ? (
        <Refusal
          title="That paper was not added"
          reason={failed.message}
          reasons={Object.values(failed.fieldErrors ?? {})}
        />
      ) : null}
    </Modal>
  );
}

/*
  The step that was missing. A document could be generated and a signature
  could be requested, and nothing in between offered to route it for approval,
  which is the act every one of those approvals binds to. It was reachable only
  by knowing the endpoint existed.
*/
function ApprovalDialog({
  matterId,
  documents,
  open,
  onClose,
  onDone,
}: Readonly<{
  matterId: string;
  documents: DocumentRecord[];
  open: boolean;
  onClose: () => void;
  onDone: () => void;
}>) {
  const [documentId, setDocumentId] = React.useState("");

  const route = useAction(async () => {
    await api(`/matters/${matterId}/approvals`, {
      method: "POST",
      body: { document_id: documentId },
    });
    onDone();
    onClose();
  });

  /*
    Ours only. Counterparty paper is held for comparison and the API refuses
    it, so offering it here would be offering a refusal.
  */
  const ours = documents.filter((document) => document.document_type !== "counterparty");
  const chosen = ours.find((document) => document.id === documentId);

  return (
    <Modal
      open={open}
      title="Route for approval"
      subtitle="The chain is resolved from configuration, not chosen: entity, agreement type, value band and risk tier decide it, and the chain applied is recorded on the matter."
      onClose={onClose}
      footer={
        <>
          <Button onClick={onClose}>Cancel</Button>
          <Button
            variant="primary"
            disabled={!documentId || route.busy}
            onClick={() => void route.run()}
          >
            {route.busy ? "Routing" : "Open the chain"}
          </Button>
        </>
      }
    >
      {ours.length === 0 ? (
        <Notice tone="warn" title="Nothing to route yet">
          Generate a document from an approved template first. Approval binds to a document,
          and there is not one on this matter.
        </Notice>
      ) : (
        <Field
          label="Document"
          required
          hint="Approval binds to this document's exact content hash."
        >
          <Select value={documentId} onChange={(event) => setDocumentId(event.target.value)}>
            <option value="">Choose the document</option>
            {ours.map((document) => (
              <option key={document.id} value={document.id}>
                {document.name}, v{document.version}
              </option>
            ))}
          </Select>
        </Field>
      )}

      {chosen ? (
        <Notice tone="info" title="What routing does">
          Every approver decides against{" "}
          <span className="font-mono text-xs">{chosen.content_hash.slice(0, 12)}</span>.
          Regenerating or editing the document changes that hash and invalidates every approval
          already given, so nobody can approve one version and issue another.
        </Notice>
      ) : null}

      {route.error ? (
        <Refusal
          title="No approval chain was opened"
          reason={route.error.message}
          reasons={route.error.reasons}
        />
      ) : null}
    </Modal>
  );
}

/*
  Running the comparison, as one deliberate act with three states.

  It used to be a picker that closed the moment the request returned, and a
  reader who clicked the page behind it lost the dialog with no way to tell
  whether anything was still happening. Worse, the findings landed on a screen
  nobody had been sent to, so the work looked like it had simply vanished.

  So: choose the paper, watch it run, and be told where the findings went. The
  dialog cannot be clicked away, because losing it mid-run is exactly the thing
  that left the reader guessing.
*/
function ReviewDialog({
  matterId,
  documents,
  open,
  onClose,
  onDone,
}: Readonly<{
  matterId: string;
  documents: DocumentRecord[];
  open: boolean;
  onClose: () => void;
  onDone: () => void;
}>) {
  const [documentId, setDocumentId] = React.useState("");
  const [raised, setRaised] = React.useState<Finding[] | null>(null);
  const paper = documents.filter((document) => document.document_type === "counterparty");
  const chosen = paper.find((document) => document.id === documentId);

  const review = useAction(async () => {
    const findings = await api<Finding[]>(
      `/ai/review/${matterId}${query({ document_id: documentId })}`,
      { method: "POST" },
    );
    setRaised(findings);
    onDone();
  });

  function finish() {
    setRaised(null);
    setDocumentId("");
    onClose();
  }

  const critical = (raised ?? []).filter((finding) => finding.severity === "critical").length;

  if (raised) {
    return (
      <Modal
        open={open}
        dismissible={false}
        title={
          raised.length
            ? `${raised.length} ${raised.length === 1 ? "finding" : "findings"} raised`
            : "Nothing differs from the playbook"
        }
        subtitle={
          raised.length
            ? "Each carries the authority needed to concede it. Nothing is conceded until a named person accepts it."
            : "Their paper matches the house position on every point the playbook covers."
        }
        onClose={finish}
        footer={
          <>
            <Button onClick={finish}>Stay on the matter</Button>
            {raised.length ? (
              <Link href="/workspace/review" className="no-underline" onClick={finish}>
                <Button variant="primary">Go to Review</Button>
              </Link>
            ) : null}
          </>
        }
      >
        <Notice tone={critical ? "bad" : raised.length ? "warn" : "good"} title="What happens next">
          {raised.length ? (
            <>
              {critical ? `${critical} critical. ` : ""}They are on the{" "}
              <strong>Review</strong> screen, under {chosen?.name ?? "this paper"}, with their
              text beside our house position and a suggested response to send back.
            </>
          ) : (
            "There is nothing to work through. The matter can go on to approval."
          )}
        </Notice>
      </Modal>
    );
  }

  return (
    <Modal
      open={open}
      dismissible={!review.busy}
      title="Review counterparty paper"
      subtitle="Each finding is measured against the house position and its pre-approved fallbacks, and carries the authority needed to concede it."
      onClose={onClose}
      footer={
        review.busy ? (
          <span className="text-xs text-muted-foreground">
            This takes a moment. Leaving now would lose it.
          </span>
        ) : (
          <>
            <Button onClick={onClose}>Cancel</Button>
            <Button variant="primary" disabled={!documentId} onClick={() => void review.run()}>
              Run the review
            </Button>
          </>
        )
      }
    >
      {review.busy ? (
        <div className="space-y-3">
          <Spinner label={`Reading ${chosen?.name ?? "their paper"} against the playbook`} />
          <p className="text-sm leading-relaxed text-muted-foreground">
            Every clause is compared to the house position, and clauses the playbook requires but
            their draft leaves out are reported too. Nothing is conceded here: each difference
            becomes a finding for a named person to decide.
          </p>
        </div>
      ) : paper.length === 0 ? (
        <Notice tone="warn" title="No counterparty paper is on this matter">
          The comparison runs over their draft. Add it first, from the request it came with
          or by uploading it, and the review has something to measure.
        </Notice>
      ) : (
        <Field
          label="Their paper"
          required
          hint="Only counterparty documents are listed. Reviewing our own draft against our own playbook would measure the template against itself."
        >
          <Select value={documentId} onChange={(event) => setDocumentId(event.target.value)}>
            <option value="">Choose the counterparty paper</option>
            {paper.map((document) => (
              <option key={document.id} value={document.id}>
                {document.name}, v{document.version}
              </option>
            ))}
          </Select>
        </Field>
      )}
      {review.error ? (
        <Refusal
          title="The review was refused"
          reason={review.error.message}
          reasons={review.error.reasons}
        />
      ) : null}
    </Modal>
  );
}

function SignatureDialog({
  documents,
  open,
  onClose,
  onDone,
}: Readonly<{
  documents: DocumentRecord[];
  open: boolean;
  onClose: () => void;
  onDone: () => void;
}>) {
  const [documentId, setDocumentId] = React.useState("");
  const [signers, setSigners] = React.useState([
    { id: crypto.randomUUID(), name: "", email: "", party: "us" },
  ]);

  const send = useAction(async () => {
    await api("/signature/requests", {
      method: "POST",
      body: { document_id: documentId, signers: signers.filter((signer) => signer.email) },
    });
    onDone();
    onClose();
  });

  const update = (index: number, key: string, value: string) =>
    setSigners((previous) =>
      previous.map((signer, position) =>
        position === index ? { ...signer, [key]: value } : signer,
      ),
    );

  return (
    <Modal
      open={open}
      title="Request signature"
      subtitle="A signature request binds to an approved hash. If the document changes afterwards, the request is void."
      onClose={onClose}
      footer={
        <>
          <Button onClick={onClose}>Cancel</Button>
          <Button
            variant="primary"
            disabled={!documentId || send.busy}
            onClick={() => void send.run()}
          >
            Send for signature
          </Button>
        </>
      }
    >
      <Field label="Document" required>
        <Select value={documentId} onChange={(event) => setDocumentId(event.target.value)}>
          <option value="">Choose the approved document</option>
          {documents.map((document) => (
            <option key={document.id} value={document.id}>
              {document.name}, v{document.version}
            </option>
          ))}
        </Select>
      </Field>

      <div className="space-y-3">
        {signers.map((signer, index) => (
          <div key={signer.id} className="grid gap-2 sm:grid-cols-3">
            <Field label={`Signer ${index + 1}`}>
              <Input
                value={signer.name}
                placeholder="Full name"
                onChange={(event) => update(index, "name", event.target.value)}
              />
            </Field>
            <Field label="Email">
              <Input
                type="email"
                value={signer.email}
                onChange={(event) => update(index, "email", event.target.value)}
              />
            </Field>
            <Field label="Party">
              <Select
                value={signer.party}
                onChange={(event) => update(index, "party", event.target.value)}
              >
                <option value="us">Us</option>
                <option value="counterparty">Counterparty</option>
              </Select>
            </Field>
          </div>
        ))}
        <Button
          size="sm"
          onClick={() =>
            setSigners((previous) => [
              ...previous,
              { id: crypto.randomUUID(), name: "", email: "", party: "counterparty" },
            ])
          }
        >
          Add another signer
        </Button>
      </div>

      {send.error ? (
        <Refusal
          title="That request was refused"
          reason={send.error.message}
          reasons={send.error.reasons}
        />
      ) : null}
      <StepUpGate action="Issuing a signature request" state={send} />
    </Modal>
  );
}

function WetInkDialog({
  matterId,
  documents,
  open,
  onClose,
  onDone,
}: Readonly<{
  matterId: string;
  documents: DocumentRecord[];
  open: boolean;
  onClose: () => void;
  onDone: () => void;
}>) {
  const [documentId, setDocumentId] = React.useState("");
  const [signatureDate, setSignatureDate] = React.useState("");
  const [signatories, setSignatories] = React.useState("");
  const [reason, setReason] = React.useState("");

  const record = useAction(async () => {
    await api(`/matters/${matterId}/execute-wet-ink`, {
      method: "POST",
      body: {
        document_id: documentId,
        signature_date: signatureDate,
        signatories: signatories
          .split(",")
          .map((name) => name.trim())
          .filter(Boolean),
        reason,
      },
    });
    onDone();
    onClose();
  });

  const ready = documentId && signatureDate && signatories.trim() && reason.trim();

  return (
    <Modal
      open={open}
      title="Record wet-ink execution"
      subtitle="Signing happened outside the platform. The record says so, permanently, and the copy held here is marked as not authoritative."
      onClose={onClose}
      footer={
        <>
          <Button onClick={onClose}>Cancel</Button>
          <Button variant="primary" disabled={!ready || record.busy} onClick={() => void record.run()}>
            Record the execution
          </Button>
        </>
      }
    >
      <Field label="Document" required>
        <Select value={documentId} onChange={(event) => setDocumentId(event.target.value)}>
          <option value="">Choose the executed document</option>
          {documents.map((document) => (
            <option key={document.id} value={document.id}>
              {document.name}, v{document.version}
            </option>
          ))}
        </Select>
      </Field>
      <div className="grid gap-3 sm:grid-cols-2">
        <Field label="Date signed" required>
          <Input
            type="date"
            value={signatureDate}
            onChange={(event) => setSignatureDate(event.target.value)}
          />
        </Field>
        <Field label="Signatories" required hint="Separated by commas.">
          <Input value={signatories} onChange={(event) => setSignatories(event.target.value)} />
        </Field>
      </div>
      <Field label="Why it was signed outside the platform" required>
        <Textarea value={reason} onChange={(event) => setReason(event.target.value)} />
      </Field>
      {record.error ? (
        <Refusal title="That record was refused" reason={record.error.message} reasons={record.error.reasons} />
      ) : null}
      <StepUpGate action="Recording a wet-ink execution" state={record} />
    </Modal>
  );
}

function GovernanceDialog({
  matter,
  open,
  onClose,
  onDone,
}: Readonly<{ matter: Matter; open: boolean; onClose: () => void; onDone: () => void }>) {
  const users = useApi<UserRow[]>(open ? "/users" : null);
  const matters = useApi<{ id: string; number: string; title: string }[]>(open ? "/matters" : null);

  const [tier, setTier] = React.useState(matter.risk_tier);
  const [tierReason, setTierReason] = React.useState("");
  const [owner, setOwner] = React.useState(matter.responsible_lawyer_id ?? "");
  const [ownerReason, setOwnerReason] = React.useState("");
  const [linked, setLinked] = React.useState("");
  const [linkType, setLinkType] = React.useState("related");

  const setTierAction = useAction(async () => {
    await api(`/matters/${matter.id}/tier`, {
      method: "POST",
      body: { tier, reason: tierReason },
    });
    onDone();
    setTierReason("");
  });

  const reassign = useAction(async () => {
    await api(`/matters/${matter.id}/reassign`, {
      method: "POST",
      body: { owner_id: owner, reason: ownerReason },
    });
    onDone();
    setOwnerReason("");
  });

  const link = useAction(async () => {
    await api(`/matters/${matter.id}/links`, {
      method: "POST",
      body: { linked_matter_id: linked, link_type: linkType },
    });
    onDone();
    setLinked("");
  });

  const error = setTierAction.error ?? reassign.error ?? link.error;

  return (
    <Modal
      open={open}
      title="Governance"
      subtitle="Tier, ownership and the links between matters. Each change carries a reason and lands on the audit trail."
      onClose={onClose}
    >
      {error ? <Refusal title="That change was refused" reason={error.message} reasons={error.reasons} /> : null}

      <div className="space-y-3 rounded-md border p-4">
        <div className="text-sm font-semibold">Override the tier</div>
        <p className="text-sm text-muted-foreground">
          The tier is derived by rule. Overriding it is allowed, never silent, and only upward
          without the head of legal.
        </p>
        <div className="grid gap-3 sm:grid-cols-2">
          <Field label="Tier">
            <Select value={tier} onChange={(event) => setTier(event.target.value)}>
              {TIERS.map((value) => (
                <option key={value} value={value}>
                  {titleCase(value)}
                </option>
              ))}
            </Select>
          </Field>
          <Field label="Reason" required>
            <Input value={tierReason} onChange={(event) => setTierReason(event.target.value)} />
          </Field>
        </div>
        <Button
          disabled={!tierReason.trim() || tier === matter.risk_tier || setTierAction.busy}
          onClick={() => void setTierAction.run()}
        >
          Record the override
        </Button>
      </div>

      <div className="space-y-3 rounded-md border p-4">
        <div className="text-sm font-semibold">Reassign</div>
        <div className="grid gap-3 sm:grid-cols-2">
          <Field label="Responsible lawyer">
            <Select value={owner} onChange={(event) => setOwner(event.target.value)}>
              <option value="">Choose a colleague</option>
              {(users.data ?? []).map((user) => (
                <option key={user.id} value={user.id}>
                  {user.name}, {user.workload} of {user.workload_ceiling}
                </option>
              ))}
            </Select>
          </Field>
          <Field label="Reason" required>
            <Input value={ownerReason} onChange={(event) => setOwnerReason(event.target.value)} />
          </Field>
        </div>
        <Button disabled={!owner || !ownerReason.trim() || reassign.busy} onClick={() => void reassign.run()}>
          Reassign the matter
        </Button>
      </div>

      <div className="space-y-3 rounded-md border p-4">
        <div className="text-sm font-semibold">Link a related matter</div>
        <div className="grid gap-3 sm:grid-cols-2">
          <Field label="Matter">
            <Select value={linked} onChange={(event) => setLinked(event.target.value)}>
              <option value="">Choose a matter</option>
              {(matters.data ?? [])
                .filter((row) => row.id !== matter.id)
                .map((row) => (
                  <option key={row.id} value={row.id}>
                    {row.number}, {row.title}
                  </option>
                ))}
            </Select>
          </Field>
          <Field label="Relationship">
            <Select value={linkType} onChange={(event) => setLinkType(event.target.value)}>
              {LINK_TYPES.map((value) => (
                <option key={value} value={value}>
                  {titleCase(value)}
                </option>
              ))}
            </Select>
          </Field>
        </div>
        <Button disabled={!linked || link.busy} onClick={() => void link.run()}>
          Link it
        </Button>
      </div>
    </Modal>
  );
}

/*
  A matter can be opened before anyone knows who the other side is, and until
  it is linked the counterparty record carries none of this matter's history.
  Replacing an existing link asks for a reason, because that is a change of
  fact rather than the filling in of a blank.
*/
export function LinkCounterparty({
  matter,
  onDone,
}: Readonly<{ matter: Matter; onDone: () => void }>) {
  const [open, setOpen] = React.useState(false);
  const [chosen, setChosen] = React.useState("");
  const [reason, setReason] = React.useState("");
  const counterparties = useApi<CounterpartyRow[]>(open ? "/counterparties" : null, [open]);

  const link = useAction(async () => {
    await api(`/matters/${matter.id}/counterparty`, {
      method: "POST",
      body: { counterparty_id: chosen, reason: reason.trim() || null },
    });
    onDone();
    setOpen(false);
    setChosen("");
    setReason("");
  });

  const linked = matter.counterparty !== null;
  const errors = link.error?.fieldErrors ?? {};

  return (
    <>
      <Button size="sm" variant={linked ? "ghost" : "primary"} onClick={() => setOpen(true)}>
        {linked ? "Change" : "Link a counterparty"}
      </Button>
      <Modal
        open={open}
        title={linked ? "Change the counterparty" : "Link a counterparty"}
        subtitle="The counterparty record carries the history, the risk assessment and the positions previously agreed. Until this matter is linked, none of that reaches it."
        width="sm"
        onClose={() => setOpen(false)}
        footer={
          <>
            <Button onClick={() => setOpen(false)}>Cancel</Button>
            <Button
              variant="primary"
              disabled={!chosen || link.busy || (linked && !reason.trim())}
              onClick={() => void link.run()}
            >
              {link.busy ? "Linking" : "Link it"}
            </Button>
          </>
        }
      >
        {link.error ? (
          <Refusal
            title="That link was refused"
            reason={link.error.message}
            reasons={Object.values(errors)}
          />
        ) : null}

        <Field
          label="Counterparty"
          required
          hint="A counterparty is one identity across both organisations. What is separated is the matter, not the company it is with."
          error={errors.counterparty_id}
        >
          <Select value={chosen} onChange={(event) => setChosen(event.target.value)}>
            <option value="">
              {counterparties.loading ? "Loading" : "Choose a counterparty"}
            </option>
            {(counterparties.data ?? []).map((row) => (
              <option key={row.id} value={row.id}>
                {row.legal_name}, {row.reference}
              </option>
            ))}
          </Select>
        </Field>

        {linked ? (
          <Field label="Why it is changing" required error={errors.reason}>
            <Textarea value={reason} onChange={(event) => setReason(event.target.value)} />
          </Field>
        ) : null}
      </Modal>
    </>
  );
}

export function MatterActions({
  matter,
  documents,
  attachments = [],
  /*
    The lifecycle track opens these too, so the dialogs live here and the id to
    open is passed in. Two places offering the same act, one where you are
    reading and one where the acts are listed, and one implementation of it.
  */
  requested = "",
  onRequestHandled,
  onChanged,
}: Readonly<{
  matter: Matter;
  documents: DocumentRecord[];
  attachments?: AttachmentBrief[];
  requested?: string;
  onRequestHandled?: () => void;
  onChanged: () => void;
}>) {
  const { has, readOnly } = useRoles();
  const [dialog, setDialog] = React.useState<string | null>(null);
  const close = React.useCallback(() => {
    setDialog(null);
    onRequestHandled?.();
  }, [onRequestHandled]);

  React.useEffect(() => {
    if (requested) setDialog(requested);
  }, [requested]);

  const restrict = useAction(async (reason: string) => {
    await api(`/matters/${matter.id}/restrict`, {
      method: "POST",
      body: { restricted: !matter.restricted, reason },
    });
    onChanged();
    close();
  });

  if (readOnly || !has("counsel", "head_of_legal", "admin")) return null;

  const canSign = has("counsel", "head_of_legal", "admin");

  /*
    One filled button, and it follows the state the matter is actually in. The
    row used to carry seven of equal weight, which is the same as carrying
    none: nothing among them said which one this matter was waiting for.
  */
  const ours = documents.filter((document) => document.document_type !== "counterparty");

  return (
    <>
      {/*
        No mutating primary button. It became Generate, then Route for
        approval, then Request a signature, which is three buttons wearing one
        position: the reader has to read it each visit to find out what it is
        now, and pressing it from memory does something they did not intend.
        The act that moves the matter on lives on the lifecycle track, where it
        is labelled with the stage it belongs to. This menu holds everything
        else, in one order that does not change.
      */}
      <Actions>
        <More label="Actions">
          <MenuItem onClick={() => setDialog("generate")}>Generate a document</MenuItem>
          <MenuItem onClick={() => setDialog("draft")}>Propose a first draft</MenuItem>
          <MenuItem onClick={() => setDialog("paper")}>Add counterparty paper</MenuItem>
          <MenuItem onClick={() => setDialog("review")}>Review counterparty paper</MenuItem>
          {ours.length ? (
            <MenuItem onClick={() => setDialog("approval")}>Route for approval</MenuItem>
          ) : null}
          {canSign && documents.length > 0 ? (
            <>
              <MenuItem onClick={() => setDialog("signature")}>Request a signature</MenuItem>
              <MenuItem onClick={() => setDialog("wetink")}>Record a wet ink execution</MenuItem>
            </>
          ) : null}
          <MenuItem onClick={() => setDialog("governance")}>Governance</MenuItem>
          <MenuItem
            tone={matter.restricted ? "default" : "destructive"}
            onClick={() => setDialog("restrict")}
          >
            {matter.restricted ? "Lift the restriction" : "Restrict this matter"}
          </MenuItem>
        </More>
      </Actions>

      <GenerateDialog
        matter={matter}
        open={dialog === "generate"}
        onClose={close}
        onDone={onChanged}
      />
      <DraftDialog matterId={matter.id} open={dialog === "draft"} onClose={close} onDone={onChanged} />
      <ApprovalDialog
        matterId={matter.id}
        documents={documents}
        open={dialog === "approval"}
        onClose={close}
        onDone={onChanged}
      />
      <PaperDialog
        matterId={matter.id}
        attachments={attachments}
        open={dialog === "paper"}
        onClose={close}
        onDone={onChanged}
      />
      <ReviewDialog
        matterId={matter.id}
        documents={documents}
        open={dialog === "review"}
        onClose={close}
        onDone={onChanged}
      />
      <SignatureDialog
        documents={documents}
        open={dialog === "signature"}
        onClose={close}
        onDone={onChanged}
      />
      <WetInkDialog
        matterId={matter.id}
        documents={documents}
        open={dialog === "wetink"}
        onClose={close}
        onDone={onChanged}
      />
      <GovernanceDialog
        matter={matter}
        open={dialog === "governance"}
        onClose={close}
        onDone={onChanged}
      />
      <StepUpGate action="Changing the restriction on a matter" state={restrict} />
      <Confirm
        open={dialog === "restrict"}
        title={matter.restricted ? "Lift the restriction on this matter" : "Restrict this matter"}
        detail={
          matter.restricted
            ? "Everyone with the ordinary permission sees this matter again."
            : "Only named users see a restricted matter. Everyone else is told it exists and nothing more."
        }
        confirmLabel={matter.restricted ? "Lift it" : "Restrict it"}
        destructive={!matter.restricted}
        reasonLabel="Reason"
        busy={restrict.busy}
        error={restrict.error?.message}
        onCancel={close}
        onConfirm={(reason) => void restrict.run(reason)}
      />
    </>
  );
}
