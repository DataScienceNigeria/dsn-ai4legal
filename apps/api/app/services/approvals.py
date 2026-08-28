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
from app.db.models.contract import Approval
from app.domain.enums import ApprovalDecision


@dataclass
class ChainContext:
    entity: str
    agreement_type: str
    risk_tier: str
    value_amount: float | None
    privacy_flag: bool = False
    #: Who raised the request this matter came from, where one did. They are
    #: the party who says whether the draft is the deal they asked for.
    requester_id: uuid.UUID | None = None
    #: Who assembled the document, and what they may do. A drafter cannot be
    #: their own second pair of eyes.
    drafter_id: uuid.UUID | None = None
    drafter_is_head: bool = False
    #: Their paper rather than ours. It goes straight to Legal: the document
    #: already exists, and what Legal is doing is aligning it, not producing
    #: something the business has not seen.
    counterparty_paper: bool = False

    #: Whether money moves. Section 8 of the guide makes Finance the lead on
    #: confirming contract value, payment structure, milestones, budget
    #: availability and tax, and a draft that reached the counterparty without
    #: it was a draft on which nobody had checked the money.
    has_value: bool = False

    #: Whether a vendor or supplier is being appointed, in which case
    #: Procurement confirms the process, the vendor documentation and the
    #: approvals it requires.
    procurement_route: bool = False


#: Two steps, derived from the matter rather than matched from a table.
#:
#: The old chain was configuration: entity, agreement type, value band and risk
#: tier selected one of four definitions, one of which inserted a Finance step
#: above five million. That is machinery for an organisation with a Finance
#: approval function. This one has a legal team of six, and the two questions
#: that actually get asked are whether the business got what it asked for and
#: whether it is safe to sign.
#:
#: What survives from the old engine is the part that was load-bearing: every
#: approval binds to one document hash, an edit invalidates them all, steps run
#: in order, and the chain applied is snapshotted onto the matter. None of that
#: depended on how many steps there were.
REQUESTER_STEP = {
    "name": "Requester confirms",
    "mode": "sequential",
    "role": "requester",
    "due_hours": 48,
}

FINANCE_STEP = {
    "name": "Finance confirms the money",
    "mode": "sequential",
    "role": "finance",
    "due_hours": 48,
}

PROCUREMENT_STEP = {
    "name": "Procurement confirms the process",
    "mode": "sequential",
    "role": "procurement",
    "due_hours": 48,
}

HEAD_STEP = {
    "name": "Legal lead",
    "mode": "sequential",
    "role": "head_of_legal",
    "due_hours": 24,
}

#: Which agreement types appoint somebody to supply goods or services, and so
#: run through Procurement. A grant received or a research collaboration is not
#: a purchase, and routing one through a vendor process would be theatre.
PROCUREMENT_TYPES = frozenset(
    {"vendor_supplier_agreement", "service_agreement", "consultancy_agreement"}
)


def derive_chain(context: ChainContext) -> tuple[str, list[dict], list[str]]:
    """The steps this matter needs, and anything worth saying about them.

    The notes are part of the record rather than an aside. A matter that never
    went to its requester should say so on its face instead of looking like one
    where the step is outstanding, and a matter the legal lead drafted and
    signed off themselves should say that too, since the step is there and only
    the note distinguishes it from a second pair of eyes.
    """
    steps: list[dict] = []
    notes: list[str] = []

    if context.counterparty_paper:
        notes.append(
            "The requester does not confirm counterparty paper. The document already "
            "exists and Legal is aligning it, not producing something the business "
            "has not seen."
        )
    elif context.requester_id is None:
        notes.append(
            "No requester to confirm. This matter was raised inside Legal rather than "
            "through the portal."
        )
    else:
        steps.append({**REQUESTER_STEP, "user_id": str(context.requester_id)})

    # Sections 8 and 9. The confirmations are conditional because a condition
    # is the honest form: an NDA moves no money and appoints no vendor, and a
    # Finance step on one is a queue nobody reads that everybody learns to
    # click through.
    if context.has_value:
        steps.append(FINANCE_STEP)
    else:
        notes.append(
            "No contract value, so Finance has nothing to confirm. A step here "
            "would be a queue somebody learns to click through."
        )

    if context.procurement_route:
        steps.append(PROCUREMENT_STEP)
    elif context.agreement_type in PROCUREMENT_TYPES:
        notes.append(
            "Procurement has nothing to confirm without a value. This agreement "
            "type usually appoints a supplier, so the absence is worth recording "
            "rather than leaving to be inferred from a missing step."
        )

    if context.drafter_is_head:
        notes.append(
            "The legal lead drafted this, so their step is their own sign-off "
            "rather than a second pair of eyes. Routing it to somebody who did not "
            "read it would look like review and be none."
        )
    steps.append(HEAD_STEP)

    # The lead is always last. Section 9 calls it final internal clearance, and
    # it is only final if everything it is clearing has already happened.
    named = [step["name"] for step in steps]
    name = ", then ".join(named) if len(named) > 1 else named[0]
    return name, steps, notes


def open_chain(
    session: Session,
    *,
    matter_id: uuid.UUID,
    document_id: uuid.UUID,
    document_hash: str,
    name: str,
    steps: list[dict],
    notes: list[str],
    resolve_approver,
) -> list[Approval]:
    """Create the approval steps for one document hash.

    ``resolve_approver`` maps a step to a user, so the rule stays here and the
    directory lookup stays with the caller. The snapshot carries the notes as
    well as the steps, because why a chain looks the way it does is part of the
    record and is unanswerable later from the steps alone.
    """
    del session
    created: list[Approval] = []
    now = datetime.now(UTC)
    snapshot = {"name": name, "steps": steps, "notes": notes}

    for index, step in enumerate(steps):
        created.append(
            Approval(
                matter_id=matter_id,
                document_id=document_id,
                document_hash=document_hash,
                chain_snapshot=snapshot,
                step_index=index,
                step_name=step.get("name", f"Step {index + 1}"),
                step_mode=step.get("mode", "sequential"),
                approver_role=step.get("role"),
                approver_id=resolve_approver(step),
                decision=ApprovalDecision.PENDING.value,
                due_at=now + timedelta(hours=int(step.get("due_hours", 48))),
            )
        )

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

    if decision == ApprovalDecision.CHANGES_REQUESTED.value:
        # The step stays open. Asking for a change is not a decision about the
        # document; it is a statement that this document is not the one to
        # decide about. It closes when a new draft supersedes this hash, which
        # invalidates the whole chain, or when they approve the one in front of
        # them after all.
        approval.comments = comments
        return

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
