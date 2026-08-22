"use client";

import { Pill, type Tone } from "@/components/ui";
import { titleCase } from "@/lib/utils";

/*
  Colour never carries a status on its own. Each of these renders a word, and
  the glyph gives a third channel for anyone who reads neither.
*/

const TIER_TONE: Record<string, Tone> = {
  tier_1: "good",
  tier_2: "info",
  tier_3: "warn",
  tier_4: "bad",
};

const STATUS_TONE: Record<string, Tone> = {
  submitted: "neutral",
  in_triage: "info",
  returned_for_information: "warn",
  accepted: "good",
  drafting: "info",
  in_review: "warn",
  escalated: "bad",
  in_approval: "novel",
  awaiting_signature: "info",
  executed: "good",
  active: "good",
  amended: "info",
  expired: "neutral",
  terminated: "neutral",
  archived: "neutral",
  on_hold: "warn",
  closed_without_matter: "neutral",
};

const SEVERITY_TONE: Record<string, Tone> = {
  critical: "bad",
  material: "warn",
  minor: "neutral",
  acceptable: "good",
};

const SEVERITY_GLYPH: Record<string, string> = {
  critical: "▲",
  material: "◆",
  minor: "●",
  acceptable: "✓",
};

const DECISION_TONE: Record<string, Tone> = {
  pending: "warn",
  accepted: "good",
  approved: "good",
  edited: "info",
  rejected: "neutral",
  invalidated: "bad",
};

export function TierPill({ tier }: Readonly<{ tier: string }>) {
  return <Pill tone={TIER_TONE[tier] ?? "neutral"}>{titleCase(tier)}</Pill>;
}

export function StatusPill({ status }: Readonly<{ status: string }>) {
  return <Pill tone={STATUS_TONE[status] ?? "neutral"}>{titleCase(status)}</Pill>;
}

export function SeverityPill({ severity }: Readonly<{ severity: string }>) {
  return (
    <Pill tone={SEVERITY_TONE[severity] ?? "neutral"}>
      <span aria-hidden className="mr-1">
        {SEVERITY_GLYPH[severity] ?? "●"}
      </span>
      {titleCase(severity)}
    </Pill>
  );
}

export function DecisionPill({ decision }: Readonly<{ decision: string }>) {
  return <Pill tone={DECISION_TONE[decision] ?? "neutral"}>{titleCase(decision)}</Pill>;
}

export function SlaPill({
  sla,
}: Readonly<{
  sla: { target_hours: number | null; running: boolean; breached: boolean; near_breach: boolean; remaining_hours: number | null } | null;
}>) {
  if (!sla || sla.target_hours === null) return <Pill tone="neutral">No clock</Pill>;
  if (!sla.running) return <Pill tone="neutral">Paused</Pill>;
  if (sla.breached) {
    const over = Math.abs(Math.round(sla.remaining_hours ?? 0));
    return <Pill tone="bad">{`Breached by ${over}h`}</Pill>;
  }
  const left = Math.round(sla.remaining_hours ?? 0);
  if (sla.near_breach) return <Pill tone="warn">{`${left}h left`}</Pill>;
  return <Pill tone="good">{`${left}h left`}</Pill>;
}

/*
  Novel text is marked as novel and unapproved wherever it appears, including
  in exports and redline suggestions. This is the visual half of that rule.
*/
export function ProvenancePill({ provenance, reference }: Readonly<{ provenance: string; reference?: string | null }>) {
  if (provenance === "novel") {
    return <Pill tone="novel">Novel, unapproved</Pill>;
  }
  const labels: Record<string, string> = {
    approved_clause: "Approved clause",
    approved_fallback: "Approved fallback",
    prior_agreement: "Prior agreement",
    template_text: "Template text",
  };
  return (
    <Pill tone="good">
      {labels[provenance] ?? titleCase(provenance)}
      {reference ? ` ${reference}` : ""}
    </Pill>
  );
}

export function CapabilityStatePill({ state, passesGate }: Readonly<{ state: string; passesGate: boolean }>) {
  if (state === "disabled") return <Pill tone="bad">Disabled</Pill>;
  if (state === "shadow") return <Pill tone="novel">Shadow mode</Pill>;
  return <Pill tone={passesGate ? "good" : "warn"}>{passesGate ? "Enabled" : "At gate"}</Pill>;
}
