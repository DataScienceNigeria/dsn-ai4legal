"""Risk tier derivation, PRD section 14.2.

Tier is computed from configurable inputs and the highest triggered tier wins.
The requester never selects the tier (PRD section 7.1, business rules). It may
be lowered only by the Head of Legal, with a recorded reason.
"""

from dataclasses import dataclass, field

from app.domain.enums import RANK_TIER, TIER_RANK, RiskTier


@dataclass(frozen=True)
class TierInputs:
    """The facts the rules run against. All are optional except the type."""

    agreement_type: str
    value_amount: float | None = None
    value_threshold: float | None = None
    counterparty_class: str | None = None
    personal_data: bool = False
    special_category_data: bool = False
    privileged: bool = False
    deviates_from_template: bool = False
    critical_deviation: bool = False
    no_approved_position: bool = False
    precedent_setting: bool = False
    long_term_or_exclusive: bool = False
    cross_border_transfer: bool = False

@dataclass
class TierRule:
    """One row of PRD section 14.2. Rules are configuration, not code."""

    code: str
    description: str
    floor: RiskTier | None = None
    raise_by: int = 0

@dataclass
class TierOutcome:
    tier: RiskTier
    reasons: list[str] = field(default_factory=list)
    triggers_privacy_assessment: bool = False
    tier_1_eligible: bool = True

DEFAULT_BASE_TIERS: dict[str, RiskTier] = {
    "nda_mutual": RiskTier.TIER_1,
    "nda_one_way": RiskTier.TIER_1,
    "consultant_engagement": RiskTier.TIER_2,
    "vendor_services": RiskTier.TIER_2,
    "event_agreement": RiskTier.TIER_2,
    "reseller_agreement": RiskTier.TIER_2,
    "master_services_agreement": RiskTier.TIER_3,
    "partnership_agreement": RiskTier.TIER_2,
    "data_sharing_agreement": RiskTier.TIER_3,
    "funder_agreement": RiskTier.TIER_3,
    "employment_terms": RiskTier.TIER_3,
    "ip_assignment": RiskTier.TIER_3,
    "litigation": RiskTier.TIER_4,
    "merger_or_acquisition": RiskTier.TIER_4,
    "government_memorandum": RiskTier.TIER_4,
}

ELEVATED_COUNTERPARTY_CLASSES: frozenset[str] = frozenset(
    {"government", "funder", "regulator", "strategic_partner"}
)

def _raise_to(current: RiskTier, floor: RiskTier) -> RiskTier:
    return RANK_TIER[max(TIER_RANK[current], TIER_RANK[floor])]

def _raise_by(current: RiskTier, levels: int) -> RiskTier:
    return RANK_TIER[min(4, TIER_RANK[current] + levels)]

def derive_tier(
    inputs: TierInputs, base_tiers: dict[str, RiskTier] | None = None
) -> TierOutcome:
    """Compute the proposed tier and the rules that produced it."""
    table = base_tiers or DEFAULT_BASE_TIERS
    base = table.get(inputs.agreement_type, RiskTier.TIER_2)
    tier = base
    outcome = TierOutcome(tier=tier)
    outcome.reasons.append(
        f"Base tier {base.value.replace('_', ' ')} for agreement type "
        f"{inputs.agreement_type.replace('_', ' ')}."
    )

    if (
        inputs.value_amount is not None
        and inputs.value_threshold is not None
        and inputs.value_amount > inputs.value_threshold
    ):
        tier = _raise_by(tier, 1)
        outcome.reasons.append(
            f"Contract value {inputs.value_amount:,.0f} is above the configured threshold "
            f"{inputs.value_threshold:,.0f}, which raises the tier by one level."
        )

    if (inputs.counterparty_class or "") in ELEVATED_COUNTERPARTY_CLASSES:
        tier = _raise_to(tier, RiskTier.TIER_3)
        outcome.reasons.append(
            f"Counterparty class {inputs.counterparty_class} raises the matter to tier 3 or above."
        )

    if inputs.personal_data:
        tier = _raise_to(tier, RiskTier.TIER_3)
        outcome.reasons.append("Personal data is involved, which raises the matter to tier 3.")

    if inputs.special_category_data or inputs.privileged:
        tier = _raise_to(tier, RiskTier.TIER_4)
        outcome.reasons.append(
            "Special-category data or privileged content raises the matter to tier 4."
        )

    if inputs.deviates_from_template:
        outcome.tier_1_eligible = False
        tier = _raise_to(tier, RiskTier.TIER_2)
        outcome.reasons.append(
            "Any deviation from the approved template removes tier 1 eligibility."
        )

    if inputs.critical_deviation:
        tier = _raise_to(tier, RiskTier.TIER_3)
        outcome.reasons.append("A critical deviation raises the matter to tier 3.")

    if inputs.no_approved_position:
        tier = _raise_to(tier, RiskTier.TIER_3)
        outcome.reasons.append(
            "No approved template or clause position exists for a required term, "
            "which raises the matter to tier 3 or above."
        )

    if inputs.precedent_setting:
        tier = _raise_to(tier, RiskTier.TIER_4)
        outcome.reasons.append("The matter is likely to set a precedent, which is tier 4.")

    if inputs.long_term_or_exclusive:
        tier = _raise_by(tier, 1)
        outcome.reasons.append(
            "A long term, auto-renewal without notice, or exclusivity raises the tier by one level."
        )

    if inputs.cross_border_transfer:
        tier = _raise_to(tier, RiskTier.TIER_3)
        outcome.triggers_privacy_assessment = True
        outcome.reasons.append(
            "Transfer of personal data outside Nigeria raises the matter to tier 3 "
            "and triggers a privacy assessment."
        )

    if tier is not RiskTier.TIER_1:
        outcome.tier_1_eligible = False

    outcome.tier = tier
    return outcome

def may_lower_tier(role_is_head_of_legal: bool, reason: str | None) -> bool:
    """A tier may only be lowered by the Head of Legal, with a recorded reason."""
    return role_is_head_of_legal and bool((reason or "").strip())
