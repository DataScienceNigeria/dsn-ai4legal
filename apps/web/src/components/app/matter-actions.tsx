"use client";

import * as React from "react";

import { useRoles } from "@/components/app/session";
import {
  Actions,
  Button,
  Confirm,
  Field,
  Input,
  Modal,
  Notice,
  Refusal,
  Select,
  Textarea,
} from "@/components/ui";
import { api, query } from "@/lib/api";
import { useAction, useApi } from "@/lib/hooks";
import type { DocumentRecord, Matter, Template, UserRow } from "@/lib/types";
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

function FactFields({
  variables,
  facts,
  onChange,
}: Readonly<{
  variables: Variable[];
  facts: Record<string, string>;
  onChange: (name: string, value: string) => void;
}>) {
  const asked = variables.filter((variable) => !SUPPLIED_BY_THE_MATTER.has(variable.name));
  if (asked.length === 0) {
    return (
      <Notice tone="good" title="Everything this template needs is already on the matter">
        No further facts are required, so the document assembles from the record as it stands.
      </Notice>
    );
  }
  return (
    <div className="grid gap-3 sm:grid-cols-2">
      {asked.map((variable) => (
        <Field
          key={variable.name}
          label={variable.label ?? titleCase(variable.name)}
          required={variable.mandatory}
          hint={variable.mandatory ? null : "Left blank, this appears as an open item."}
        >
          <Input
            value={facts[variable.name] ?? ""}
            onChange={(event) => onChange(variable.name, event.target.value)}
          />
        </Field>
      ))}
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

  const review = useAction(async () => {
    await api(`/ai/review/${matterId}${query({ document_id: documentId })}`, { method: "POST" });
    onDone();
    onClose();
  });

  return (
    <Modal
      open={open}
      title="Review counterparty paper"
      subtitle="Each finding is measured against the house position and its pre-approved fallbacks, and carries the authority needed to concede it."
      onClose={onClose}
      footer={
        <>
          <Button onClick={onClose}>Cancel</Button>
          <Button variant="primary" disabled={!documentId || review.busy} onClick={() => void review.run()}>
            Run the review
          </Button>
        </>
      }
    >
      <Field label="Document" required>
        <Select value={documentId} onChange={(event) => setDocumentId(event.target.value)}>
          <option value="">Choose the counterparty paper</option>
          {documents.map((document) => (
            <option key={document.id} value={document.id}>
              {document.name}, v{document.version}
            </option>
          ))}
        </Select>
      </Field>
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

export function MatterActions({
  matter,
  documents,
  onChanged,
}: Readonly<{ matter: Matter; documents: DocumentRecord[]; onChanged: () => void }>) {
  const { has, readOnly } = useRoles();
  const [dialog, setDialog] = React.useState<string | null>(null);
  const close = React.useCallback(() => setDialog(null), []);

  const restrict = useAction(async (reason: string) => {
    await api(`/matters/${matter.id}/restrict`, {
      method: "POST",
      body: { restricted: !matter.restricted, reason },
    });
    onChanged();
    close();
  });

  if (readOnly || !has("legal_ops", "counsel", "head_of_legal", "privacy", "admin")) return null;

  const canSign = has("counsel", "head_of_legal", "admin");

  return (
    <>
      <Actions>
        <Button variant="primary" onClick={() => setDialog("generate")}>
          Generate
        </Button>
        <Button onClick={() => setDialog("draft")}>First draft</Button>
        <Button onClick={() => setDialog("review")} disabled={documents.length === 0}>
          Review paper
        </Button>
        {canSign ? (
          <>
            <Button onClick={() => setDialog("signature")} disabled={documents.length === 0}>
              Signature
            </Button>
            <Button onClick={() => setDialog("wetink")} disabled={documents.length === 0}>
              Wet ink
            </Button>
          </>
        ) : null}
        <Button onClick={() => setDialog("governance")}>Governance</Button>
        <Button
          variant={matter.restricted ? "default" : "destructive"}
          onClick={() => setDialog("restrict")}
        >
          {matter.restricted ? "Lift the restriction" : "Restrict"}
        </Button>
      </Actions>

      <GenerateDialog
        matter={matter}
        open={dialog === "generate"}
        onClose={close}
        onDone={onChanged}
      />
      <DraftDialog matterId={matter.id} open={dialog === "draft"} onClose={close} onDone={onChanged} />
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
