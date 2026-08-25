"""Obligations, renewals and the compliance calendar, M08 and M12."""

from __future__ import annotations

import uuid
from datetime import UTC, date, datetime

from fastapi import APIRouter, Query, Response
from sqlalchemy import select

from app.core import audit
from app.core.deps import CurrentUser, Db, WorkingEntity
from app.core.errors import Conflict, NotFound, ValidationFailed
from app.db.models.contract import Contract, Obligation
from app.db.models.governance import ComplianceItem
from app.db.models.organisation import User
from app.domain.enums import ObligationStatus, Role
from app.schemas.common import Ack
from app.schemas.governance import ComplianceCompletion, ComplianceItemOut, ComplianceVersion
from app.schemas.matters import (
    ObligationCompletion,
    ObligationDecision,
    ObligationOut,
)
from app.services import notifications, sequences
from app.services import obligations as service
from app.services.obligations import LEGAL_DEADLINES

OBLIGATION_NOT_FOUND = "That obligation was not found."
COMPLIANCE_NOT_FOUND = "That compliance item was not found."

router = APIRouter(tags=["obligations"])


def _decorate(obligation: Obligation) -> ObligationOut:
    model = ObligationOut.model_validate(obligation)
    if obligation.due_date:
        model.days_until_due = (obligation.due_date - date.today()).days
        model.overdue = (
            obligation.due_date < date.today() and obligation.status == ObligationStatus.OPEN.value
        )

    # A duty on its own says nothing about whose contract it is. The agreement
    # travels with it, so the list reads as duties under agreements rather than
    # as a pile of references.
    contract = obligation.contract
    if contract is not None:
        model.contract_reference = contract.reference
        model.counterparty_name = (
            contract.counterparty.legal_name if contract.counterparty else None
        )
        model.matter_number = contract.matter.number if contract.matter else None
    return model


@router.get("/obligations")
def list_obligations(
    db: Db,
    principal: CurrentUser,
    entity: WorkingEntity,
    status: str | None = None,
    owner_id: uuid.UUID | None = None,
    matter_id: uuid.UUID | None = None,
    due_within_days: int | None = None,
    limit: int = Query(default=200, le=500),
) -> list[ObligationOut]:
    stmt = select(Obligation).where(Obligation.entity == entity)
    if status:
        stmt = stmt.where(Obligation.status == status)
    if matter_id:
        stmt = stmt.where(Obligation.matter_id == matter_id)
    if owner_id:
        stmt = stmt.where(Obligation.owner_id == owner_id)
    if due_within_days is not None:
        from datetime import timedelta

        stmt = stmt.where(Obligation.due_date <= date.today() + timedelta(days=due_within_days))
    stmt = stmt.order_by(Obligation.due_date.asc().nulls_last()).limit(limit)
    return [_decorate(o) for o in db.execute(stmt).scalars()]


@router.get("/contracts/{contract_id}/obligations")
def contract_obligations(
    contract_id: uuid.UUID, db: Db, principal: CurrentUser
) -> list[ObligationOut]:
    stmt = (
        select(Obligation)
        .where(Obligation.contract_id == contract_id)
        .order_by(Obligation.due_date.asc().nulls_last())
    )
    return [_decorate(o) for o in db.execute(stmt).scalars()]


@router.post("/obligations/{obligation_id}/decision")
def decide_proposal(
    obligation_id: uuid.UUID,
    payload: ObligationDecision,
    db: Db,
    principal: CurrentUser,
) -> ObligationOut:
    """Legal confirms, edits or rejects a proposal, and confirmation creates a
    tracked task (LOP-M08-US-02)."""
    principal.require_role(Role.COUNSEL, Role.HEAD_OF_LEGAL, Role.ADMIN)

    obligation = db.get(Obligation, obligation_id)
    if obligation is None:
        raise NotFound(OBLIGATION_NOT_FOUND)
    if obligation.status != ObligationStatus.PROPOSED.value:
        raise Conflict("That obligation has already been decided.")

    if payload.decision == "reject":
        obligation.status = ObligationStatus.REJECTED.value
    else:
        obligation.status = ObligationStatus.OPEN.value
        if payload.edited_name:
            obligation.name = payload.edited_name
        if payload.edited_due_date:
            obligation.due_date = payload.edited_due_date
        if payload.owner_id:
            obligation.owner_id = payload.owner_id

    if obligation.interaction_id:
        from app.ai.gateway import record_human_decision

        record_human_decision(
            db,
            obligation.interaction_id,
            "accepted" if payload.decision == "confirm" else payload.decision,
            uuid.UUID(principal.user_id),
            payload.reason,
        )

    audit.record(
        db,
        action="obligation_decided",
        object_type="obligation",
        object_id=obligation.reference,
        actor_id=principal.user_id,
        actor_label=principal.name,
        entity=obligation.entity,
        after_state={"decision": payload.decision, "status": obligation.status},
    )
    return _decorate(obligation)


@router.post("/obligations/{obligation_id}/complete")
def complete(
    obligation_id: uuid.UUID,
    payload: ObligationCompletion,
    db: Db,
    principal: CurrentUser,
) -> ObligationOut:
    """Completion is timestamped, attributable and, where configured, evidenced."""
    obligation = db.get(Obligation, obligation_id)
    if obligation is None:
        raise NotFound(OBLIGATION_NOT_FOUND)

    evidence = payload.evidence_reference or obligation.evidence_reference
    allowed, reason = service.can_complete(
        obligation.status, obligation.evidence_required, evidence
    )
    if not allowed:
        raise ValidationFailed(reason, {"evidence_reference": reason})

    obligation.status = ObligationStatus.COMPLETED.value
    obligation.completed_at = datetime.now(UTC)
    obligation.completed_by_id = uuid.UUID(principal.user_id)
    obligation.evidence_reference = evidence
    obligation.evidence_note = payload.evidence_note
    obligation.decision_taken = payload.decision_taken

    if obligation.recurrence != "none" and obligation.due_date:
        following = service.next_occurrence(obligation.due_date, obligation.recurrence)
        if following:
            db.add(
                Obligation(
                    reference=f"{obligation.reference}-r",
                    contract_id=obligation.contract_id,
                    matter_id=obligation.matter_id,
                    entity=obligation.entity,
                    name=obligation.name,
                    description=obligation.description,
                    obligation_type=obligation.obligation_type,
                    source_clause=obligation.source_clause,
                    owner_id=obligation.owner_id,
                    due_date=following,
                    recurrence=obligation.recurrence,
                    lead_time_days=obligation.lead_time_days,
                    evidence_required=obligation.evidence_required,
                    escalation_rule=obligation.escalation_rule,
                    status=ObligationStatus.OPEN.value,
                )
            )

    audit.record(
        db,
        action="obligation_completed",
        object_type="obligation",
        object_id=obligation.reference,
        actor_id=principal.user_id,
        actor_label=principal.name,
        entity=obligation.entity,
        after_state={"evidence": evidence},
    )
    return _decorate(obligation)


@router.get("/obligations/calendar.ics")
def calendar_feed(db: Db, principal: CurrentUser, entity: WorkingEntity) -> Response:
    """A subscribable feed into Microsoft and Google calendars.

    Carries the deadlines that are legal's own: renewal windows, notice periods
    and termination windows. What an agreement requires of the business belongs
    to whoever is doing that work, and putting a consultant's milestones in the
    legal team's calendar filled it with other people's dates.
    """
    lines = [
        "BEGIN:VCALENDAR",
        "VERSION:2.0",
        "PRODID:-//Legal Operations Platform//EN",
        f"X-WR-CALNAME:Legal deadlines, {entity}",
    ]
    obligations = db.execute(
        select(Obligation).where(
            Obligation.entity == entity,
            Obligation.status == ObligationStatus.OPEN.value,
            Obligation.due_date.is_not(None),
            Obligation.obligation_type.in_(LEGAL_DEADLINES),
        )
    ).scalars()

    for obligation in obligations:
        stamp = obligation.due_date.strftime("%Y%m%d")
        lines.extend(
            [
                "BEGIN:VEVENT",
                f"UID:{obligation.reference}@dsn-lai",
                f"DTSTART;VALUE=DATE:{stamp}",
                f"SUMMARY:{obligation.name}",
                f"DESCRIPTION:{obligation.reference}. Source {obligation.source_clause or 'n/a'}.",
                f"BEGIN:VALARM\r\nTRIGGER:-P{obligation.lead_time_days}D\r\n"
                "ACTION:DISPLAY\r\nDESCRIPTION:Reminder\r\nEND:VALARM",
                "END:VEVENT",
            ]
        )
    lines.append("END:VCALENDAR")

    return Response(
        content="\r\n".join(lines),
        media_type="text/calendar",
        headers={"Content-Disposition": 'attachment; filename="obligations.ics"'},
    )


@router.post("/obligations/run-reminders")
def run_reminders(db: Db, principal: CurrentUser, entity: WorkingEntity) -> Ack:
    """Send reminders and escalate breaches. The scheduler calls this."""
    principal.require_role(Role.COUNSEL, Role.HEAD_OF_LEGAL, Role.ADMIN)

    sent = 0
    escalated = 0
    for obligation in db.execute(
        select(Obligation).where(
            Obligation.entity == entity,
            Obligation.status == ObligationStatus.OPEN.value,
            Obligation.due_date.is_not(None),
        )
    ).scalars():
        window = service.ReminderWindow(obligation.due_date, obligation.lead_time_days)
        owner = db.get(User, obligation.owner_id) if obligation.owner_id else None
        if not owner:
            continue

        if window.is_due():
            notifications.notify(
                db,
                connector_code="notification_channel",
                recipients=[owner.work_email],
                subject=f"{obligation.name} is due in {window.days_until()} days",
                body=(
                    f"{obligation.reference}. Source clause "
                    f"{obligation.source_clause or 'not recorded'}."
                ),
                record_reference=obligation.reference,
            )
            sent += 1

        target = service.escalation_due(obligation.due_date, obligation.escalation_rule or {})
        if target:
            notifications.notify(
                db,
                connector_code="notification_channel",
                recipients=[f"{target}@dsn.example"],
                subject=f"Overdue obligation {obligation.reference}",
                body=f"{obligation.name} passed its due date of {obligation.due_date}.",
                record_reference=obligation.reference,
            )
            escalated += 1

    return Ack(message=f"{sent} reminders queued and {escalated} escalations raised.")


@router.get("/compliance", response_model=list[ComplianceItemOut])
def compliance_items(
    db: Db, principal: CurrentUser, entity: WorkingEntity, status: str | None = None
) -> list[ComplianceItem]:
    stmt = select(ComplianceItem).where(ComplianceItem.entity == entity)
    if status:
        stmt = stmt.where(ComplianceItem.status == status)
    return list(
        db.execute(stmt.order_by(ComplianceItem.next_due_date.asc().nulls_last())).scalars()
    )


@router.post("/compliance/{item_id}/complete", response_model=ComplianceItemOut)
def complete_compliance(
    item_id: uuid.UUID,
    payload: ComplianceCompletion,
    db: Db,
    principal: CurrentUser,
) -> ComplianceItem:
    """Completion requires filing evidence where configured."""
    principal.require_role(Role.COUNSEL, Role.HEAD_OF_LEGAL, Role.ADMIN)
    item = db.get(ComplianceItem, item_id)
    if item is None:
        raise NotFound(COMPLIANCE_NOT_FOUND)

    if item.evidence_required and not payload.evidence_reference:
        raise ValidationFailed(
            "Filing evidence is required to complete this item.",
            {"evidence_reference": "Attach the filing evidence."},
        )

    item.evidence_reference = payload.evidence_reference
    item.filing_number = payload.filing_number
    item.filed_by_id = uuid.UUID(principal.user_id)
    item.status = "completed"
    if item.next_due_date:
        following = service.next_occurrence(item.next_due_date, item.recurrence)
        if following:
            item.next_due_date = following
            item.status = "open"

    audit.record(
        db,
        action="compliance_filed",
        object_type="compliance_item",
        object_id=str(item.id),
        actor_id=principal.user_id,
        actor_label=principal.name,
        entity=item.entity,
        after_state={"filing_number": payload.filing_number},
    )
    return item


RENEWAL_OPTIONS = ["renew", "renegotiate", "terminate", "lapse"]


def _contract_sequence(reference: str) -> int:
    return int(reference.split("-")[-1])


@router.post("/contracts/{contract_id}/renewal-task", status_code=201)
def create_renewal_task(
    contract_id: uuid.UUID,
    db: Db,
    principal: CurrentUser,
    lead_time_days: int = 60,
) -> ObligationOut:
    """Renewals stop being surprises, LOP-M08-US-04.

    The task falls due at the notice deadline minus the lead time, and it
    carries the four decisions that are actually available, so the owner records
    a choice rather than letting the window pass by default.
    """
    principal.require_role(Role.COUNSEL, Role.HEAD_OF_LEGAL, Role.ADMIN)

    contract = db.get(Contract, contract_id)
    if contract is None:
        raise NotFound("That contract was not found.")
    if not contract.end_date:
        raise ValidationFailed(
            "This contract has no end date, so a renewal window cannot be computed.",
            {"end_date": "Record the end date on the contract first."},
        )

    deadline = service.notice_deadline(contract.end_date, contract.notice_period_days or 0)
    due = service.renewal_task_date(deadline, lead_time_days)

    existing = db.execute(
        select(Obligation).where(
            Obligation.contract_id == contract.id,
            Obligation.obligation_type == "renewal",
            Obligation.status.in_([ObligationStatus.OPEN.value, ObligationStatus.PROPOSED.value]),
        )
    ).scalar_one_or_none()
    if existing is not None:
        raise Conflict(f"{existing.reference} already tracks this renewal window.")

    obligation = Obligation(
        reference=sequences.new_obligation_reference(db, _contract_sequence(contract.reference)),
        contract_id=contract.id,
        matter_id=contract.matter_id,
        entity=contract.entity,
        name=f"Renewal decision, {contract.reference}",
        description=(
            f"The notice deadline is {deadline} and the agreement ends "
            f"{contract.end_date}. Record the decision before the deadline."
        ),
        obligation_type="renewal",
        owner_id=contract.matter.responsible_lawyer_id if contract.matter else None,
        due_date=due,
        lead_time_days=lead_time_days,
        evidence_required=False,
        decision_options=RENEWAL_OPTIONS,
        status=ObligationStatus.OPEN.value,
    )
    db.add(obligation)
    db.flush()

    audit.record(
        db,
        action="renewal_task_created",
        object_type="obligation",
        object_id=obligation.reference,
        actor_id=principal.user_id,
        actor_label=principal.name,
        entity=contract.entity,
        after_state={
            "contract": contract.reference,
            "notice_deadline": str(deadline),
            "due_date": str(due),
            "options": RENEWAL_OPTIONS,
        },
    )
    return _decorate(obligation)


@router.post("/obligations/{obligation_id}/renewal-decision")
def record_renewal_decision(
    obligation_id: uuid.UUID,
    decision: str,
    db: Db,
    principal: CurrentUser,
    reason: str | None = None,
) -> ObligationOut:
    """Record renew, renegotiate, terminate or allow to lapse."""
    principal.require_role(Role.COUNSEL, Role.HEAD_OF_LEGAL, Role.ADMIN)

    obligation = db.get(Obligation, obligation_id)
    if obligation is None:
        raise NotFound(OBLIGATION_NOT_FOUND)

    options = obligation.decision_options or RENEWAL_OPTIONS
    if decision not in options:
        raise ValidationFailed(
            "That is not one of the decisions available on this renewal.",
            {"decision": f"Choose one of {', '.join(options)}."},
        )

    obligation.decision_taken = decision
    obligation.status = ObligationStatus.COMPLETED.value
    obligation.completed_at = datetime.now(UTC)
    obligation.completed_by_id = uuid.UUID(principal.user_id)
    obligation.evidence_note = reason

    audit.record(
        db,
        action="renewal_decided",
        object_type="obligation",
        object_id=obligation.reference,
        actor_id=principal.user_id,
        actor_label=principal.name,
        entity=obligation.entity,
        after_state={"decision": decision, "reason": reason},
    )
    return _decorate(obligation)


@router.post("/compliance/{item_id}/versions", response_model=ComplianceItemOut, status_code=201)
def version_requirement(
    item_id: uuid.UUID,
    payload: ComplianceVersion,
    db: Db,
    principal: CurrentUser,
) -> ComplianceItem:
    """A statutory change is a controlled update, LOP-M12-US-04.

    Changing a requirement creates a new version with an effective date and
    leaves the old one in place, so historical compliance is assessed against
    the rule that applied at the time rather than the rule that applies now.
    """
    principal.require_role(Role.HEAD_OF_LEGAL, Role.ADMIN, Role.COUNSEL)

    current = db.get(ComplianceItem, item_id)
    if current is None:
        raise NotFound(COMPLIANCE_NOT_FOUND)
    if current.status == "superseded":
        raise Conflict("That version is already superseded. Version the current one instead.")

    replacement = ComplianceItem(
        entity=current.entity,
        requirement=payload.requirement or current.requirement,
        statutory_reference=payload.statutory_reference or current.statutory_reference,
        jurisdiction=current.jurisdiction,
        filing_date=payload.filing_date or current.filing_date,
        recurrence=payload.recurrence or current.recurrence,
        accountable_owner_id=payload.accountable_owner_id or current.accountable_owner_id,
        evidence_required=(
            current.evidence_required
            if payload.evidence_required is None
            else payload.evidence_required
        ),
        next_due_date=payload.next_due_date or current.next_due_date,
        lead_time_days=payload.lead_time_days or current.lead_time_days,
        version=current.version + 1,
        effective_date=payload.effective_date,
        supersedes_id=current.id,
        status="open",
    )
    db.add(replacement)

    current.status = "superseded"

    audit.record(
        db,
        action="compliance_requirement_versioned",
        object_type="compliance_item",
        object_id=str(current.id),
        actor_id=principal.user_id,
        actor_label=principal.name,
        entity=current.entity,
        before_state={"version": current.version, "requirement": current.requirement},
        after_state={
            "version": replacement.version,
            "requirement": replacement.requirement,
            "effective_date": str(payload.effective_date),
        },
    )
    db.flush()
    return replacement


@router.get("/compliance/{item_id}/history", response_model=list[ComplianceItemOut])
def requirement_history(item_id: uuid.UUID, db: Db, principal: CurrentUser) -> list[ComplianceItem]:
    """Every version of this requirement, newest first."""
    item = db.get(ComplianceItem, item_id)
    if item is None:
        raise NotFound(COMPLIANCE_NOT_FOUND)

    chain = [item]
    cursor = item
    while cursor.supersedes_id:
        previous = db.get(ComplianceItem, cursor.supersedes_id)
        if previous is None:
            break
        chain.append(previous)
        cursor = previous

    forward = db.execute(
        select(ComplianceItem).where(ComplianceItem.supersedes_id == item.id)
    ).scalars()
    return sorted([*chain, *forward], key=lambda row: row.version, reverse=True)
