"use client";

import * as React from "react";

import { useRoles } from "@/components/app/session";
import {
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
import type { Assessment, UserRow } from "@/lib/types";
import { titleCase } from "@/lib/utils";

/*
  The fields the API insists on before an assessment can close. Asking for them
  at the stage that owns them beats discovering the whole list at the end.
*/
const REQUIRED_FIELDS = [
  "purpose",
  "intended_users",
  "affected_persons",
  "business_owner",
  "data_categories",
  "data_sources",
  "legal_basis",
  "retention",
  "hosting_locations",
  "transfers",
  "models",
  "vendors",
  "subprocessors",
  "connectors",
  "datasets",
  "material_contractual_terms",
  "potential_harms",
  "bias",
  "security_threats",
  "performance_limits",
  "human_oversight",
];

const STAGE_FIELDS: Record<string, string[]> = {
  product: ["purpose", "intended_users", "affected_persons", "business_owner", "human_oversight"],
  engineering: [
    "data_categories",
    "data_sources",
    "hosting_locations",
    "models",
    "datasets",
    "connectors",
    "security_threats",
    "performance_limits",
  ],
  legal: ["legal_basis", "retention", "transfers", "material_contractual_terms", "subprocessors"],
  business_owner: ["vendors", "potential_harms", "bias"],
};

function CompleteStage({
  assessment,
  onDone,
}: Readonly<{ assessment: Assessment; onDone: () => void }>) {
  const [open, setOpen] = React.useState(false);
  const [notes, setNotes] = React.useState("");
  const [captured, setCaptured] = React.useState<Record<string, string>>({});

  const stage = assessment.stage;
  const fields = STAGE_FIELDS[stage] ?? [];

  React.useEffect(() => {
    if (open) setCaptured({ ...assessment.captured });
  }, [open, assessment.captured]);

  const complete = useAction(async () => {
    await api(`/assessments/${assessment.id}/stages/${stage}/complete`, {
      method: "POST",
      body: { notes: notes || undefined, captured },
    });
    onDone();
    setOpen(false);
    setNotes("");
  });

  if (stage === "closed") return null;

  return (
    <>
      <Button size="sm" variant="primary" onClick={() => setOpen(true)}>
        Complete the {titleCase(stage)} stage
      </Button>
      <Modal
        open={open}
        title={`Complete the ${titleCase(stage)} stage`}
        subtitle="What this stage owns is captured here and carried forward. The assessment then routes to the next owner."
        width="lg"
        onClose={() => setOpen(false)}
        footer={
          <>
            <Button onClick={() => setOpen(false)}>Cancel</Button>
            <Button variant="primary" disabled={complete.busy} onClick={() => void complete.run()}>
              Complete and route on
            </Button>
          </>
        }
      >
        <div className="grid gap-3 sm:grid-cols-2">
          {fields.map((field) => (
            <Field key={field} label={titleCase(field)}>
              <Textarea
                className="min-h-[4.5rem]"
                value={captured[field] ?? ""}
                onChange={(event) =>
                  setCaptured((previous) => ({ ...previous, [field]: event.target.value }))
                }
              />
            </Field>
          ))}
        </div>
        <Field label="Notes" hint="Recorded against this stage with your name and the time.">
          <Textarea value={notes} onChange={(event) => setNotes(event.target.value)} />
        </Field>
        {complete.error ? (
          <Refusal title="That stage was not completed" reason={complete.error.message} />
        ) : null}
      </Modal>
    </>
  );
}

function CloseAssessment({
  assessment,
  onDone,
}: Readonly<{ assessment: Assessment; onDone: () => void }>) {
  const { has } = useRoles();
  const [open, setOpen] = React.useState(false);
  const users = useApi<UserRow[]>(open ? "/users" : null);
  const [decision, setDecision] = React.useState("accept");
  const [reason, setReason] = React.useState("");
  const [owner, setOwner] = React.useState("");
  const [reviewDate, setReviewDate] = React.useState("");

  const close = useAction(async () => {
    await api(`/assessments/${assessment.id}/close`, {
      method: "POST",
      body: {
        residual_risk_decision: decision,
        residual_risk_reason: reason,
        residual_risk_owner_id: owner,
        review_date: reviewDate || undefined,
      },
    });
    onDone();
    setOpen(false);
  });

  const missing = REQUIRED_FIELDS.filter((field) => !assessment.captured?.[field]);

  if (!has("privacy", "head_of_legal", "admin") || assessment.stage === "closed") return null;

  return (
    <>
      <Button size="sm" onClick={() => setOpen(true)}>
        Close with a decision
      </Button>
      <Modal
        open={open}
        title="Close this assessment"
        subtitle="Closure needs a residual-risk decision and a named owner who accepts it. Outstanding conditions become tracked tasks."
        onClose={() => setOpen(false)}
        footer={
          <>
            <Button onClick={() => setOpen(false)}>Cancel</Button>
            <Button
              variant="primary"
              disabled={!owner || reason.trim().length < 10 || close.busy}
              onClick={() => void close.run()}
            >
              Close it
            </Button>
          </>
        }
      >
        {missing.length ? (
          <Notice tone="warn" title={`${missing.length} required fields are still empty`}>
            {missing.map(titleCase).join(", ")}. The API refuses closure until each is captured,
            so complete the stage that owns them first.
          </Notice>
        ) : null}

        <Field label="Residual risk" required>
          <Select value={decision} onChange={(event) => setDecision(event.target.value)}>
            <option value="accept">Accept it</option>
            <option value="mitigate">Mitigate it</option>
            <option value="escalate">Escalate it</option>
          </Select>
        </Field>
        <Field label="Reason" required hint="What the accountable owner is agreeing to.">
          <Textarea value={reason} onChange={(event) => setReason(event.target.value)} />
        </Field>
        <div className="grid gap-3 sm:grid-cols-2">
          <Field label="Accountable owner" required>
            <Select value={owner} onChange={(event) => setOwner(event.target.value)}>
              <option value="">Choose the owner</option>
              {(users.data ?? []).map((user) => (
                <option key={user.id} value={user.id}>
                  {user.name}
                </option>
              ))}
            </Select>
          </Field>
          <Field label="Review due">
            <Input type="date" value={reviewDate} onChange={(event) => setReviewDate(event.target.value)} />
          </Field>
        </div>
        {close.error ? (
          <Refusal
            title="That assessment was not closed"
            reason={close.error.message}
            reasons={Object.values(close.error.fieldErrors)}
          />
        ) : null}
      </Modal>
    </>
  );
}

export function AssessmentActions({
  assessment,
  onChanged,
}: Readonly<{ assessment: Assessment; onChanged: () => void }>) {
  const { readOnly } = useRoles();
  const [reassessing, setReassessing] = React.useState(false);

  const reassess = useAction(async (reason: string) => {
    await api(`/assessments/${assessment.id}/reassess${query({ reason })}`, { method: "POST" });
    onChanged();
    setReassessing(false);
  });

  if (readOnly) return null;

  return (
    <>
      <CompleteStage assessment={assessment} onDone={onChanged} />
      <CloseAssessment assessment={assessment} onDone={onChanged} />
      <Button size="sm" onClick={() => setReassessing(true)}>
        Reassess
      </Button>
      <Confirm
        open={reassessing}
        title="Trigger a reassessment"
        detail="A material change to the purpose, the data, the model, a vendor or a transfer route reopens the assessment at the Product stage."
        confirmLabel="Reopen it"
        reasonLabel="What changed"
        busy={reassess.busy}
        error={reassess.error?.message}
        onCancel={() => setReassessing(false)}
        onConfirm={(reason) => void reassess.run(reason)}
      />
    </>
  );
}
