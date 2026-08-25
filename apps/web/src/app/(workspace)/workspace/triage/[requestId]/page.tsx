"use client";

import { useParams, useRouter } from "next/navigation";
import * as React from "react";

import { Rename } from "@/components/app/rename";
import { RequestPanel } from "@/components/app/request-panel";
import { TierPill } from "@/components/app/status";
import {
  Button,
  Card,
  CardBody,
  CardHeader,
  Field,
  MenuItem,
  Modal,
  Mono,
  More,
  Notice,
  PageTitle,
  Pill,
  Refusal,
  Select,
  Spinner,
  Textarea,
} from "@/components/ui";
import { ApiError, api } from "@/lib/api";
import { useAction, useApi } from "@/lib/hooks";
import type { Matter, TriageProposal, UserRow } from "@/lib/types";
import { titleCase } from "@/lib/utils";

const TIERS = ["tier_1", "tier_2", "tier_3", "tier_4"];

/*
  One dialog serves both outcomes that end a request without a matter. Neither
  defaults its note: returning sends the wording to the requester verbatim, and
  closing produces no matter to carry an explanation, so what is written here
  is the only record of why. The API refuses an empty one either way.
*/
function OutcomeDialog({
  outcome,
  note,
  answer,
  missing,
  busy,
  error,
  onNote,
  onAnswer,
  onMissing,
  onCancel,
  onConfirm,
}: Readonly<{
  outcome: "close" | "return" | null;
  note: string;
  answer: string;
  missing: string;
  busy: boolean;
  error: ApiError | null;
  onNote: (value: string) => void;
  onAnswer: (value: string) => void;
  onMissing: (value: string) => void;
  onCancel: () => void;
  onConfirm: () => void;
}>) {
  const closing = outcome === "close";

  return (
    <Modal
      open={outcome !== null}
      title={closing ? "Answer and close" : "Return for information"}
      subtitle={
        closing
          ? "No matter is created, so this note is the only record of why. The requester is sent it."
          : "The requester is sent this wording as it is written. No matter number is issued."
      }
      onClose={onCancel}
      footer={
        <>
          <Button onClick={onCancel}>Cancel</Button>
          <Button variant="primary" disabled={!note.trim() || busy} onClick={onConfirm}>
            {closing ? "Close the request" : "Send it back"}
          </Button>
        </>
      }
    >
      <div className="space-y-4">
        {error ? (
          <Refusal
            title="That did not go through"
            reason={error.message}
            reasons={Object.values(error.fieldErrors)}
          />
        ) : null}

        <Field
          label={closing ? "Why is this being closed" : "What is missing"}
          required
          error={error?.fieldErrors.reason}
          hint={
            closing
              ? "The reason a competent colleague would need to understand the decision in a year."
              : "Say plainly what you need before this can be triaged."
          }
        >
          <Textarea
            value={note}
            onChange={(event) => onNote(event.target.value)}
            placeholder={
              closing
                ? "Covered by the existing framework agreement, so no new paper is needed."
                : "The counterparty's legal name and the value are both missing."
            }
          />
        </Field>

        {closing ? (
          <Field
            label="The answer to send them"
            hint="Optional. It is kept on the request record alongside the reason."
          >
            <Textarea value={answer} onChange={(event) => onAnswer(event.target.value)} />
          </Field>
        ) : (
          <Field label="Each item they must supply" hint="One per line. Optional.">
            <Textarea value={missing} onChange={(event) => onMissing(event.target.value)} />
          </Field>
        )}
      </div>
    </Modal>
  );
}

export default function TriageDetail() {
  const { requestId } = useParams<{ requestId: string }>();
  const router = useRouter();

  const proposal = useApi<TriageProposal>(`/triage/${requestId}`);
  const users = useApi<UserRow[]>("/users");

  const [tier, setTier] = React.useState<string | null>(null);
  const [owner, setOwner] = React.useState<string | null>(null);
  const [reason, setReason] = React.useState("");
  const [restricted, setRestricted] = React.useState(false);
  const [tierAccepted, setTierAccepted] = React.useState(false);
  const [ownerAccepted, setOwnerAccepted] = React.useState(false);
  const [outcome, setOutcome] = React.useState<"close" | "return" | null>(null);
  const [outcomeNote, setOutcomeNote] = React.useState("");
  const [answer, setAnswer] = React.useState("");
  const [missing, setMissing] = React.useState("");

  const accept = useAction(async () => {
    const created = await api<Matter>(`/triage/${requestId}/accept`, {
      method: "POST",
      body: {
        tier: tier ?? undefined,
        tier_change_reason: reason || undefined,
        owner_id: owner ?? undefined,
        restricted,
      },
    });
    router.push(`/workspace/matters/${created.id}`);
    return created;
  });

  /*
    Neither outcome defaults its reason any more. Returning sends the wording
    to the requester verbatim, and closing produces no matter, so the note
    written here is the only record of why. The API refuses an empty one.
  */
  const returnForInfo = useAction(async () => {
    await api(`/triage/${requestId}/return`, {
      method: "POST",
      body: {
        reason: outcomeNote.trim(),
        missing_information: missing
          .split("\n")
          .map((line) => line.trim())
          .filter(Boolean),
      },
    });
    router.push("/workspace/triage");
  });

  const closeIt = useAction(async () => {
    await api(`/triage/${requestId}/close`, {
      method: "POST",
      body: { reason: outcomeNote.trim(), answer: answer.trim() || null },
    });
    router.push("/workspace/triage");
  });

  if (proposal.loading) return <Spinner label="Deriving the tier from the rules" />;
  if (proposal.error) {
    return <Refusal title="This request is not available to you" reason={proposal.error.message} />;
  }

  const data = proposal.data!;
  const effectiveTier = tier ?? data.tier;
  const tierChanged = effectiveTier !== data.tier;
  const proposedOwner = users.data?.find((user) => user.id === (owner ?? data.proposed_owner));
  const eligibleOwners = (users.data ?? []).filter((user) =>
    user.roles.some((role) => ["counsel", "head_of_legal"].includes(role)),
  );

  function openOutcome(next: "close" | "return") {
    setOutcomeNote("");
    setAnswer("");
    setMissing("");
    setOutcome(next);
  }

  const closing = outcome === "close";
  const outcomeError = (closing ? closeIt.error : returnForInfo.error) ?? null;

  return (
    <div className="space-y-6">
      <PageTitle
        title={data.request?.subject ?? "Triage"}
        subtitle={
          <span className="flex flex-wrap items-center gap-x-3 gap-y-1.5">
            {data.request ? <Mono>{data.request.reference}</Mono> : null}
            <span>Both proposals are editable. Any change is recorded with a reason.</span>
          </span>
        }
        actions={
          <>
            <Button
              variant="primary"
              onClick={() => void accept.run()}
              disabled={accept.busy || (tierChanged && !reason.trim())}
            >
              {accept.busy ? "Creating" : "Accept and create matter"}
            </Button>
            <More>
              {/* The subject becomes the matter title at acceptance, so this
                  is the last point at which a description of the counterparty
                  can be turned into a description of the work. */}
              <Rename
                path={`/triage/${requestId}`}
                field="subject"
                label="request"
                current={data.request?.subject ?? ""}
                askReason
                onDone={() => proposal.reload()}
              />
              <MenuItem onClick={() => openOutcome("close")}>Answer and close</MenuItem>
              <MenuItem onClick={() => openOutcome("return")}>
                Return for information
              </MenuItem>
            </More>
          </>
        }
      />

      {accept.error ? (
        <Refusal
          title="The matter was not created"
          reason={accept.error.message}
          reasons={Object.values(accept.error.fieldErrors)}
        />
      ) : null}

      {data.request ? <RequestPanel request={data.request} /> : null}

      <div className="grid gap-4 lg:grid-cols-2">
        <Card>
          <CardHeader
            title="Proposed risk tier"
            subtitle="Derived from configurable rules. The highest triggered tier wins."
            actions={
              tierAccepted ? (
                <Pill tone="good">
                  <span aria-hidden className="mr-1">&#10003;</span>Accepted
                </Pill>
              ) : (
                <Button size="sm" variant="primary" onClick={() => setTierAccepted(true)}>
                  Accept proposal
                </Button>
              )
            }
          />
          <CardBody className="space-y-3">
            <div className="flex flex-wrap items-center gap-2">
              <TierPill tier={effectiveTier} />
              {data.tier_1_eligible ? (
                <Pill tone="good">Eligible for tier 1 auto-issue</Pill>
              ) : (
                <Pill tone="neutral">Not eligible for auto-issue</Pill>
              )}
              {data.triggers_privacy_assessment ? (
                <Pill tone="warn">Triggers a privacy assessment</Pill>
              ) : null}
            </div>

            <div>
              <div className="mb-1.5 text-xs font-medium text-muted-foreground">
                Why the rules landed here
              </div>
              <ul className="space-y-1.5 text-sm">
                {data.tier_rationale.map((line) => (
                  <li key={line} className="flex gap-2 leading-relaxed">
                    <span aria-hidden className="text-muted-foreground">&bull;</span>
                    <span>{line}</span>
                  </li>
                ))}
              </ul>
            </div>

            <Field
              label="Change the tier"
              hint="A tier may only be lowered by the legal lead, and every change needs a reason."
            >
              <Select value={effectiveTier} onChange={(event) => setTier(event.target.value)}>
                {TIERS.map((value) => (
                  <option key={value} value={value}>
                    {titleCase(value)}
                  </option>
                ))}
              </Select>
            </Field>

            {tierChanged ? (
              <Field label="Reason for the change" required error={accept.error?.fieldErrors.tier_change_reason}>
                <Textarea
                  value={reason}
                  onChange={(event) => setReason(event.target.value)}
                  placeholder="State why the derived tier does not apply."
                />
              </Field>
            ) : null}
          </CardBody>
        </Card>

        <Card>
          <CardHeader
            title="Proposed owner"
            subtitle="From workload and specialism"
            actions={
              ownerAccepted ? (
                <Pill tone="good">
                  <span aria-hidden className="mr-1">&#10003;</span>Accepted
                </Pill>
              ) : (
                <Button size="sm" variant="primary" onClick={() => setOwnerAccepted(true)}>
                  Accept proposal
                </Button>
              )
            }
          />
          <CardBody className="space-y-3">
            <div className="text-sm font-medium">{proposedOwner?.name ?? "No eligible owner"}</div>
            <div className="text-sm text-muted-foreground">{data.owner_rationale}</div>

            <Field label="Assign someone else">
              <Select
                value={owner ?? data.proposed_owner ?? ""}
                onChange={(event) => setOwner(event.target.value)}
              >
                <option value="">Leave unassigned</option>
                {eligibleOwners.map((user) => (
                  <option key={user.id} value={user.id}>
                    {user.name}, workload {user.workload} of {user.workload_ceiling}
                  </option>
                ))}
              </Select>
            </Field>

            <label className="flex items-start gap-2 rounded-md border p-3 text-sm">
              <input
                type="checkbox"
                checked={restricted}
                onChange={(event) => setRestricted(event.target.checked)}
                className="mt-0.5"
              />
              <span>
                <span className="font-medium">Open as a restricted matter</span>
                <span className="mt-0.5 block text-xs text-muted-foreground">
                  Restricted matters are excluded from every list, search, retrieval index,
                  dashboard and export for anyone not explicitly named, and access attempts are
                  logged.
                </span>
              </span>
            </label>
          </CardBody>
        </Card>
      </div>

      <Notice title="What happens on acceptance">
        A matter number is generated, the service clock starts, the owner is notified, and the
        request record is linked to the matter. Nothing before this point creates a matter.
      </Notice>

      <OutcomeDialog
        outcome={outcome}
        note={outcomeNote}
        answer={answer}
        missing={missing}
        busy={closeIt.busy || returnForInfo.busy}
        error={outcomeError}
        onNote={setOutcomeNote}
        onAnswer={setAnswer}
        onMissing={setMissing}
        onCancel={() => setOutcome(null)}
        onConfirm={() => void (closing ? closeIt.run() : returnForInfo.run())}
      />
    </div>
  );
}
