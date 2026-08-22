"""Matter state model, PRD section 8.2."""

import pytest

from app.domain.enums import MatterState as S
from app.domain.state_machine import (
    IllegalTransition,
    assert_transition,
    permitted_next,
)


def test_a_hold_returns_to_the_state_it_paused_and_needs_a_reason():
    """On hold is the one state whose exit depends on where it came from, and
    both entering it and reversing out of approval must state why."""
    rules = assert_transition(S.IN_REVIEW, S.ON_HOLD, reason=None) if False else None

    with pytest.raises(IllegalTransition, match="reason is required"):
        assert_transition(S.ESCALATED, S.ON_HOLD)

    rules = assert_transition(S.ESCALATED, S.ON_HOLD, reason="Awaiting the funder")
    assert rules.pauses_clock is True

    assert permitted_next(S.ON_HOLD, previous=S.ESCALATED) == {
        S.ESCALATED,
        S.CLOSED_WITHOUT_MATTER,
    }

    resume = assert_transition(S.ON_HOLD, S.ESCALATED, previous=S.ESCALATED)
    assert resume.resumes_clock is True


def test_dropping_out_of_approval_invalidates_approvals_and_illegal_jumps_are_refused():
    rules = assert_transition(S.IN_APPROVAL, S.IN_REVIEW, reason="Counsel reopened clause 11")
    assert rules.invalidates_approvals is True

    with pytest.raises(IllegalTransition, match="cannot move to"):
        assert_transition(S.SUBMITTED, S.EXECUTED)
