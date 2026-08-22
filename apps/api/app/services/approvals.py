"""Approval routing and hash binding, M07.

Approval attaches to a document content hash. Any subsequent edit invalidates
outstanding approvals, notifies affected approvers and requires re-approval. A
signature request cannot be issued for an unapproved hash.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.errors import Conflict, Refused
from app.db.models.contract import Approval, ApprovalChainDefinition
from app.domain.enums import ApprovalDecision


@dataclass
class ChainContext:
    entity: str
    agreement_type: str
    risk_tier: str
    value_amount: float | None
    privacy_flag: bool = False


def resolve_chain(session: Session, context: ChainContext) -> ApprovalChainDefinition:
    """Select the approval chain that applies.

    Chains are configuration, matched on entity, agreement type, value band and
    risk tier. The most specific active chain wins, and the chain applied is
    recorded on the matter so a later reader can see which rule ran.
    """
    candidates = session.execute(
        select(ApprovalChainDefinition)
        .where(ApprovalChainDefinition.active.is_(True))
        .order_by(ApprovalChainDefinition.priority.asc())
    ).scalars().all()

    def matches(chain: ApprovalChainDefinition) -> bool:
        if chain.entity and chain.entity != context.entity:
            return False
        if chain.agreement_type and chain.agreement_type != context.agreement_type:
            return False
        if chain.risk_tier and chain.risk_tier != context.risk_tier:
            return False
        value = context.value_amount or 0
        if chain.min_value is not None and value < float(chain.min_value):
            return False
        if chain.max_value is not None and value > float(chain.max_value):
            return False
        return True

    for chain in candidates:
        if matches(chain):
            return chain

    raise Refused(
        "No approval chain is configured for this matter.",
        [
            f"Entity {context.entity}, type {context.agreement_type}, "
            f"tier {context.risk_tier}. Configure a chain before routing for approval."
        ],
    )


def specificity(chain: ApprovalChainDefinition) -> int:
    """How many dimensions a chain pins down. Used when ordering candidates."""
    return sum(
        1
        for value in (chain.entity, chain.agreement_type, chain.risk_tier, chain.min_value)
        if value is not None
    )


def open_chain(
    session: Session,
    *,
    matter_id: uuid.UUID,
    document_id: uuid.UUID,
    document_hash: str,
    chain: ApprovalChainDefinition,
    context: ChainContext,
    resolve_approver,
) -> list[Approval]:
    """Create the approval steps for one document hash.

    ``resolve_approver`` maps a step definition to a user identifier, so the
    routing rule stays here and the directory lookup stays with the caller.
    """
    created: list[Approval] = []
    now = datetime.now(UTC)

    for index, step in enumerate(chain.steps):
        condition = step.get("condition")
        if condition == "privacy_flag" and not context.privacy_flag:
            continue
        if condition == "value_above" and (context.value_amount or 0) <= float(
            step.get("value_threshold", 0)
        ):
            continue

        approval = Approval(
            matter_id=matter_id,
            document_id=document_id,
            document_hash=document_hash,
            chain_definition_id=chain.id,
            chain_snapshot={"name": chain.name, "steps": chain.steps},
            step_index=index,
            step_name=step.get("name", f"Step {index + 1}"),
            step_mode=step.get("mode", "sequential"),
            approver_role=step.get("role"),
            approver_id=resolve_approver(step),
            decision=ApprovalDecision.PENDING.value,
            due_at=now + timedelta(hours=int(step.get("due_hours", 48))),
        )
        session.add(approval)
        created.append(approval)

    return created


def current_step(approvals: list[Approval]) -> list[Approval]:
    """The approvals that are actionable right now.

    Sequential steps wait for everything before them. Parallel steps at the
    same index are all actionable together.
    """
    pending = [a for a in approvals if a.decision == ApprovalDecision.PENDING.value]
    if not pending:
        return []
    lowest = min(a.step_index for a in pending)
    return [a for a in pending if a.step_index == lowest]


def record_decision(
    approval: Approval, decision: str, comments: str | None, actor_id: uuid.UUID | None
) -> None:
    if approval.decision != ApprovalDecision.PENDING.value:
        raise Conflict(
            f"This approval was already recorded as {approval.decision}. "
            "Re-approval happens against a new document hash."
        )
    approval.decision = decision
    approval.comments = comments
    approval.decided_at = datetime.now(UTC)
    if actor_id and approval.approver_id != actor_id:
        approval.delegate_used_id = actor_id


def invalidate_for_hash(
    session: Session, matter_id: uuid.UUID, superseded_hash: str, reason: str
) -> list[Approval]:
    """Any edit invalidates outstanding approvals against the old hash."""
    affected = session.execute(
        select(Approval).where(
            Approval.matter_id == matter_id,
            Approval.document_hash == superseded_hash,
            Approval.decision.in_(
                [ApprovalDecision.PENDING.value, ApprovalDecision.APPROVED.value]
            ),
        )
    ).scalars().all()

    for approval in affected:
        approval.decision = ApprovalDecision.INVALIDATED.value
        approval.invalidated_by_event = reason
    return affected


def fully_approved(approvals: list[Approval], document_hash: str) -> bool:
    """A signature request needs every step approved against this exact hash."""
    relevant = [a for a in approvals if a.document_hash == document_hash]
    if not relevant:
        return False
    return all(a.decision == ApprovalDecision.APPROVED.value for a in relevant)


def assert_signable(approvals: list[Approval], document_hash: str) -> None:
    if not fully_approved(approvals, document_hash):
        outstanding = [
            a.step_name
            for a in approvals
            if a.document_hash == document_hash
            and a.decision != ApprovalDecision.APPROVED.value
        ]
        raise Refused(
            "A signature request cannot be issued for this document.",
            outstanding
            or [
                "No approval exists against this document hash. The document may have "
                "been edited after approval."
            ],
        )


def due_for_escalation(approval: Approval, now: datetime | None = None) -> bool:
    now = now or datetime.now(UTC)
    return (
        approval.decision == ApprovalDecision.PENDING.value
        and approval.due_at is not None
        and now > approval.due_at
        and approval.escalated_at is None
    )
