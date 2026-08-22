"use client";

import { useParams, useRouter } from "next/navigation";
import * as React from "react";

import { TierPill } from "@/components/app/status";
import {
  Button,
  Card,
  CardBody,
  CardHeader,
  Field,
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
import type { Matter, TriageProposal, UserRow } from "@/lib/types";
import { titleCase } from "@/lib/utils";

const TIERS = ["tier_1", "tier_2", "tier_3", "tier_4"];

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

  const returnForInfo = useAction(async () => {
    await api(`/triage/${requestId}/return`, {
      method: "POST",
      body: { reason: reason || "Instructions are incomplete.", missing_information: [] },
    });
    router.push("/workspace/triage");
  });

  const closeIt = useAction(async () => {
    await api(`/triage/${requestId}/close`, {
      method: "POST",
      body: { reason: reason || "Answered as a preliminary enquiry." },
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
    user.roles.some((role) => ["counsel", "head_of_legal", "legal_ops"].includes(role)),
  );

  return (
    <div className="space-y-6">
      <PageTitle
        title="Triage"
        subtitle="Both proposals are editable. Any change is recorded with a reason."
        actions={
          <>
            <Button onClick={() => void closeIt.run()} disabled={closeIt.busy}>
              Answer and close
            </Button>
            <Button onClick={() => void returnForInfo.run()} disabled={returnForInfo.busy}>
              Return for information
            </Button>
            <Button
              variant="primary"
              onClick={() => void accept.run()}
              disabled={accept.busy || (tierChanged && !reason.trim())}
            >
              {accept.busy ? "Creating" : "Accept and create matter"}
            </Button>
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
              hint="A tier may only be lowered by the Head of Legal, and every change needs a reason."
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
    </div>
  );
}
