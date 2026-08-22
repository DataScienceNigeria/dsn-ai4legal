"""Tier 1 auto-issue, LOP-M04-US-04.

A tier 1 request type with no deviation from the approved template is generated,
routed for signature and filed without a drafting cycle. What makes that
defensible is that nothing generative touches it: the merge is deterministic, so
the same facts and the same template version always produce the same file.

Every auto-issued document joins the monthly quality sample. Automation that
issues without review needs assurance somewhere, and this is where it sits.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date

from app.domain.enums import RiskTier, VersionStatus


@dataclass(frozen=True)
class Eligibility:
    permitted: bool
    reasons: tuple[str, ...]

    def as_dict(self) -> dict:
        return {"permitted": self.permitted, "reasons": list(self.reasons)}


def assess(
    *,
    auto_issue_configured: bool,
    risk_tier: str | None,
    template_status: str,
    template_effective_date: date | None,
    novel_clause_count: int,
    open_items: list[str],
    outstanding_approvals: int,
    counterparty_complete: bool,
    today: date | None = None,
) -> Eligibility:
    """Decide whether a document may issue without a human in the loop.

    Every condition here is a reason to stop. The function collects all of them
    rather than returning on the first, because counsel deciding whether to
    unblock an auto-issue needs the whole list, not the first item on it.
    """
    today = today or date.today()
    reasons: list[str] = []

    if not auto_issue_configured:
        reasons.append("This request type is not configured for tier 1 auto-issue.")
    if risk_tier != RiskTier.TIER_1.value:
        reasons.append(
            f"Auto-issue is limited to tier 1, and this matter is {risk_tier or 'untiered'}."
        )
    if template_status != VersionStatus.APPROVED.value:
        reasons.append(f"The template version is {template_status}, not approved.")
    if template_effective_date and template_effective_date > today:
        reasons.append(
            f"The template version does not take effect until {template_effective_date}."
        )
    if novel_clause_count:
        reasons.append(
            f"{novel_clause_count} clauses deviate from the approved template. "
            "Deviation ends auto-issue."
        )
    if open_items:
        reasons.append(f"{len(open_items)} open items remain on the document.")
    if outstanding_approvals:
        reasons.append(f"{outstanding_approvals} approvals are still outstanding.")
    if not counterparty_complete:
        reasons.append("The counterparty record is incomplete.")

    return Eligibility(permitted=not reasons, reasons=tuple(reasons))


def sample_period(moment: date | None = None) -> str:
    moment = moment or date.today()
    return f"{moment.year:04d}-{moment.month:02d}"
