"""Approval binding, PRD LOP-M07-US-03."""

import uuid

import pytest

from app.core.errors import Refused
from app.db.models.contract import Approval
from app.domain.enums import ApprovalDecision
from app.services.approvals import assert_signable, current_step, fully_approved

HASH_A = "a" * 64
HASH_B = "b" * 64


def _approval(step: int, decision: str, document_hash: str = HASH_A) -> Approval:
    return Approval(
        id=uuid.uuid4(),
        matter_id=uuid.uuid4(),
        document_hash=document_hash,
        step_index=step,
        step_name=f"Step {step}",
        decision=decision,
    )


def test_a_signature_request_cannot_be_issued_against_a_hash_that_is_not_fully_approved():
    """An edit produces a new hash, and approvals against the old one do not
    carry across to it."""
    approvals = [
        _approval(0, ApprovalDecision.APPROVED.value),
        _approval(1, ApprovalDecision.APPROVED.value),
    ]
    assert fully_approved(approvals, HASH_A) is True
    assert_signable(approvals, HASH_A)

    assert fully_approved(approvals, HASH_B) is False
    with pytest.raises(Refused):
        assert_signable(approvals, HASH_B)


def test_a_sequential_chain_exposes_only_the_earliest_outstanding_step():
    approvals = [
        _approval(0, ApprovalDecision.APPROVED.value),
        _approval(1, ApprovalDecision.PENDING.value),
        _approval(2, ApprovalDecision.PENDING.value),
    ]
    actionable = current_step(approvals)

    assert len(actionable) == 1
    assert actionable[0].step_index == 1
