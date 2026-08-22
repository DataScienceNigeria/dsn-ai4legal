"""Risk tier derivation, PRD section 14.2."""

from app.domain.enums import RiskTier
from app.domain.tiering import TierInputs, derive_tier, may_lower_tier


def test_the_highest_triggered_tier_wins_and_every_rule_that_fired_is_reported():
    """A standard NDA is tier 1 until a rule says otherwise. Special-category
    data raises it to tier 4 even though other rules only reach tier 3."""
    plain = derive_tier(TierInputs(agreement_type="nda_mutual"))
    assert plain.tier is RiskTier.TIER_1
    assert plain.tier_1_eligible is True

    raised = derive_tier(
        TierInputs(
            agreement_type="nda_mutual",
            personal_data=True,
            special_category_data=True,
            cross_border_transfer=True,
        )
    )
    assert raised.tier is RiskTier.TIER_4
    assert raised.tier_1_eligible is False
    assert raised.triggers_privacy_assessment is True
    assert len(raised.reasons) >= 4


def test_any_deviation_removes_tier_1_eligibility_and_only_the_head_of_legal_may_lower():
    deviating = derive_tier(
        TierInputs(agreement_type="nda_mutual", deviates_from_template=True)
    )
    assert deviating.tier_1_eligible is False

    assert may_lower_tier(role_is_head_of_legal=True, reason="Standard terms restored") is True
    assert may_lower_tier(role_is_head_of_legal=True, reason="") is False
    assert may_lower_tier(role_is_head_of_legal=False, reason="A good reason") is False
