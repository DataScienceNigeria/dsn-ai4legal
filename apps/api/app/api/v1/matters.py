"""Triage and matters, M02."""

from __future__ import annotations

import uuid
from datetime import UTC, datetime
from typing import Any

from fastapi import APIRouter, Query, Request
from sqlalchemy import select

from app.core import audit
from app.core.deps import CurrentUser, Db, WorkingEntity, client_ip
from app.core.errors import Conflict, Forbidden, NotFound, ValidationFailed
from app.db.models.counterparty import Counterparty
from app.db.models.intake import Request as RequestRecord
from app.db.models.matter import (
    DecisionRecord,
    Matter,
    MatterAccess,
    MatterLink,
    MatterTransition,
)
from app.db.models.organisation import User
from app.domain import tiering
from app.domain.enums import AUTHORITY_MATRIX, AuthorityLevel, MatterState, RiskTier, Role
from app.domain.sla import ClockSegment, evaluate
from app.domain.state_machine import IllegalTransition, assert_transition, permitted_next
from app.schemas.common import Ack, DecisionOut, DecisionRequest, TransitionRequest
from app.schemas.intake import (
    AcceptRequest,
    AttachmentBrief,
    CloseRequest,
    RequestAnswer,
    RequestDetail,
    ReturnRequest,
    TriageProposal,
)
from app.schemas.matters import (
    CounterpartyLink,
    LinkRequest,
    MatterListItem,
    MatterOut,
    MatterUpdate,
    ReassignRequest,
    RestrictRequest,
    SlaOut,
    TierOverride,
)
from app.services import notifications, sequences

MATTER_NOT_FOUND = "That matter was not found."
REQUEST_NOT_FOUND = "That request was not found."

router = APIRouter(tags=["matters"])


def _tier_inputs(record: RequestRecord, counterparty: Counterparty | None) -> tiering.TierInputs:
    request_type = record.request_type
    return tiering.TierInputs(
        agreement_type=request_type.agreement_type,
        value_amount=float(record.value_amount) if record.value_amount else None,
        value_threshold=float(request_type.value_threshold)
        if request_type.value_threshold
        else None,
        counterparty_class=counterparty.relationship_class if counterparty else None,
        personal_data=record.personal_data,
        special_category_data=record.special_category_data,
        cross_border_transfer=record.leaves_nigeria,
        deviates_from_template=bool(record.answers.get("their_paper")),
        no_approved_position=bool(record.answers.get("no_approved_position")),
        long_term_or_exclusive=bool(record.answers.get("exclusivity")),
    )


def _propose_owner(db, record: RequestRecord, tier: RiskTier) -> tuple[User | None, str]:
    """Propose an owner from workload and specialism (LOP-M02-US-02)."""
    specialism = record.request_type.practice_code.lower()
    needs_counsel = tier in {RiskTier.TIER_3, RiskTier.TIER_4}
    wanted = (
        [Role.COUNSEL.value, Role.HEAD_OF_LEGAL.value]
        if needs_counsel
        else [
            Role.LEGAL_OPS.value,
            Role.COUNSEL.value,
        ]
    )

    candidates = [
        user
        for user in db.execute(select(User).where(User.active.is_(True))).scalars()
        if set(user.roles or []) & set(wanted) and record.entity in user.entity_codes
    ]
    if not candidates:
        return None, "No eligible owner is available in this entity."

    def rank(user: User) -> tuple[int, int]:
        matches_specialism = specialism in [s.lower() for s in (user.specialisms or [])]
        return (0 if matches_specialism else 1, user.workload)

    best = sorted(candidates, key=rank)[0]
    matched = specialism in [s.lower() for s in (best.specialisms or [])]
    reason = f"Workload {best.workload} of {best.workload_ceiling}"
    if matched:
        reason += f", {record.request_type.practice_code} specialism"
    if needs_counsel:
        reason += ", tier requires counsel"
    return best, reason


@router.get("/triage")
def triage_queue(
    db: Db,
    principal: CurrentUser,
    entity: WorkingEntity,
    _: Any = None,
) -> list[dict]:
    """New requests, sorted by declared deadline then derived urgency."""
    principal.require_role(Role.LEGAL_OPS, Role.COUNSEL, Role.HEAD_OF_LEGAL, Role.ADMIN)

    records = list(
        db.execute(
            select(RequestRecord)
            .where(
                RequestRecord.entity == entity,
                RequestRecord.status.in_(
                    [MatterState.SUBMITTED.value, MatterState.IN_TRIAGE.value]
                ),
            )
            .order_by(RequestRecord.required_date.asc().nulls_last(), RequestRecord.created_at)
        ).scalars()
    )

    queue = []
    for record in records:
        counterparty = (
            db.get(Counterparty, record.counterparty_id) if record.counterparty_id else None
        )
        outcome = tiering.derive_tier(_tier_inputs(record, counterparty))
        age = datetime.now(UTC) - record.created_at
        queue.append(
            {
                "request_id": str(record.id),
                "reference": record.reference,
                "entity": record.entity,
                "request_type": record.request_type.business_label,
                "counterparty": record.proposed_counterparty
                or (counterparty.legal_name if counterparty else None),
                "privacy_flag": record.privacy_flag,
                "age_hours": round(age.total_seconds() / 3600, 1),
                "suggested_tier": outcome.tier.value,
                "required_date": record.required_date,
                "subject": record.subject,
            }
        )
    return queue


@router.get("/triage/{request_id}")
def triage_detail(request_id: uuid.UUID, db: Db, principal: CurrentUser) -> TriageProposal:
    principal.require_role(Role.LEGAL_OPS, Role.COUNSEL, Role.HEAD_OF_LEGAL, Role.ADMIN)
    record = db.get(RequestRecord, request_id)
    if record is None:
        raise NotFound(REQUEST_NOT_FOUND)

    counterparty = db.get(Counterparty, record.counterparty_id) if record.counterparty_id else None
    outcome = tiering.derive_tier(_tier_inputs(record, counterparty))
    owner, owner_reason = _propose_owner(db, record, outcome.tier)

    record.suggested_tier = outcome.tier.value
    record.tier_rationale = outcome.reasons
    record.suggested_owner_id = owner.id if owner else None
    record.owner_rationale = owner_reason
    if record.status == MatterState.SUBMITTED.value:
        _transition_request(db, record, MatterState.IN_TRIAGE, principal, None)

    return TriageProposal(
        tier=outcome.tier.value,
        tier_rationale=outcome.reasons,
        tier_1_eligible=outcome.tier_1_eligible,
        triggers_privacy_assessment=outcome.triggers_privacy_assessment,
        proposed_owner=owner.id if owner else None,
        owner_rationale=owner_reason,
        request=_request_detail(db, record),
    )


def _answer_labels(record: RequestRecord) -> list[RequestAnswer]:
    """The requester's answers, each under the question they were asked.

    A field defined on the type but never answered is left out. A field the
    form no longer defines is still shown, under its own name, because the
    request was made under the form as it stood.
    """
    labels = {
        field.get("name"): field.get("label", field.get("name", ""))
        for field in (record.request_type.fields or [])
        if isinstance(field, dict)
    }
    answers: list[RequestAnswer] = []
    for name, value in (record.answers or {}).items():
        if value in (None, "", []):
            continue
        answers.append(
            RequestAnswer(
                name=name,
                label=labels.get(name) or name.replace("_", " ").capitalize(),
                value=_readable(value),
            )
        )
    return answers


def _readable(value: object) -> str:
    """A stored answer as the requester would recognise it.

    The form posts booleans as the strings "true" and "false", and a triage
    screen reading `False` is asking the reader to translate.
    """
    if isinstance(value, bool):
        return "Yes" if value else "No"
    if isinstance(value, str) and value.lower() in {"true", "false"}:
        return "Yes" if value.lower() == "true" else "No"
    if isinstance(value, list):
        return ", ".join(str(item) for item in value)
    return str(value)


def _request_detail(db, record: RequestRecord) -> RequestDetail:
    requester = db.get(User, record.requester_id)
    return RequestDetail(
        id=record.id,
        reference=record.reference,
        entity=record.entity,
        request_type=record.request_type.business_label,
        subject=record.subject,
        purpose=record.purpose,
        requester_name=requester.name if requester else None,
        requester_email=requester.work_email if requester else None,
        proposed_counterparty=record.proposed_counterparty,
        required_date=record.required_date,
        value_amount=float(record.value_amount) if record.value_amount is not None else None,
        value_currency=record.value_currency,
        personal_data=record.personal_data,
        special_category_data=record.special_category_data,
        third_party_confidential=record.third_party_confidential,
        leaves_nigeria=record.leaves_nigeria,
        status=record.status,
        submitted_at=record.created_at,
        answers=_answer_labels(record),
        attachments=[
            AttachmentBrief(
                id=attachment.id,
                filename=attachment.filename,
                content_type=attachment.content_type,
                size_bytes=attachment.size_bytes,
                scan_status=attachment.scan_status,
            )
            for attachment in record.attachments
        ],
    )


def _transition_request(
    db, record: RequestRecord, target: MatterState, principal, reason: str | None
) -> None:
    record.status = target.value
    audit.record(
        db,
        action="request_transition",
        object_type="request",
        object_id=record.reference,
        actor_id=principal.user_id,
        actor_label=principal.name,
        entity=record.entity,
        after_state={"status": target.value, "reason": reason},
    )


@router.post("/triage/{request_id}/accept", response_model=MatterOut, status_code=201)
def accept_request(
    request_id: uuid.UUID,
    payload: AcceptRequest,
    db: Db,
    principal: CurrentUser,
    http_request: Request,
) -> Matter:
    """Accepting a request generates a matter number and starts the clock.

    A matter number is issued at acceptance, not at submission.
    """
    principal.require_role(Role.LEGAL_OPS, Role.COUNSEL, Role.HEAD_OF_LEGAL, Role.ADMIN)
    record = db.get(RequestRecord, request_id)
    if record is None:
        raise NotFound(REQUEST_NOT_FOUND)
    if record.status not in {MatterState.SUBMITTED.value, MatterState.IN_TRIAGE.value}:
        raise Conflict(f"This request is {record.status.replace('_', ' ')} and cannot be accepted.")

    counterparty = db.get(Counterparty, record.counterparty_id) if record.counterparty_id else None
    outcome = tiering.derive_tier(_tier_inputs(record, counterparty))
    tier = outcome.tier
    rationale = list(outcome.reasons)
    overridden = False

    if payload.tier and payload.tier != outcome.tier.value:
        proposed = RiskTier(payload.tier)
        lowering = proposed.value < outcome.tier.value
        if lowering and not tiering.may_lower_tier(
            principal.is_head_of_legal, payload.tier_change_reason
        ):
            raise Forbidden(
                "A tier may only be lowered by the Head of Legal, with a recorded reason."
            )
        if not payload.tier_change_reason:
            raise ValidationFailed(
                "A tier change must be recorded with a reason.",
                {"tier_change_reason": "State why the derived tier does not apply."},
            )
        tier = proposed
        overridden = True
        rationale.append(
            f"Overridden to {tier.value} by {principal.name}: {payload.tier_change_reason}"
        )

    if payload.restricted:
        principal.require_role(Role.COUNSEL, Role.HEAD_OF_LEGAL, Role.ADMIN)

    practice = (payload.practice_code or record.request_type.practice_code).upper()
    owner_id = payload.owner_id or record.suggested_owner_id

    now = datetime.now(UTC)
    matter = Matter(
        number=sequences.new_matter_number(db, record.entity, practice),
        entity=record.entity,
        request_id=record.id,
        request_type_id=record.request_type_id,
        practice_code=practice,
        title=record.subject,
        counterparty_id=record.counterparty_id,
        requester_id=record.requester_id,
        responsible_lawyer_id=owner_id,
        priority=payload.priority,
        risk_tier=tier.value,
        tier_rationale=rationale,
        tier_overridden=overridden,
        tier_override_reason=payload.tier_change_reason,
        classification="restricted" if payload.restricted else "confidential",
        status=MatterState.ACCEPTED.value,
        next_action="Assign work and begin drafting",
        due_date=record.required_date,
        sla_target_hours=record.request_type.sla_hours,
        sla_started_at=now,
        privacy_flag=record.privacy_flag,
        value_amount=record.value_amount,
        value_currency=record.value_currency,
        restricted=payload.restricted,
    )
    db.add(matter)
    db.flush()

    db.add(
        MatterTransition(
            matter_id=matter.id,
            from_state=None,
            to_state=MatterState.ACCEPTED.value,
            actor_id=uuid.UUID(principal.user_id),
            occurred_at=now,
            clock_running=True,
        )
    )

    if payload.restricted:
        db.add(
            MatterAccess(
                matter_id=matter.id,
                user_id=uuid.UUID(principal.user_id),
                granted_by_id=uuid.UUID(principal.user_id),
            )
        )
        if owner_id:
            db.add(
                MatterAccess(
                    matter_id=matter.id,
                    user_id=owner_id,
                    granted_by_id=uuid.UUID(principal.user_id),
                )
            )

    record.status = MatterState.ACCEPTED.value
    if owner_id:
        owner = db.get(User, owner_id)
        if owner:
            owner.workload += 1

    audit.record(
        db,
        action="matter_created",
        object_type="matter",
        object_id=matter.number,
        actor_id=principal.user_id,
        actor_label=principal.name,
        entity=matter.entity,
        after_state={"tier": tier.value, "owner": str(owner_id), "restricted": payload.restricted},
        ip_address=client_ip(http_request),
        session_id=principal.session_id,
    )
    return matter


@router.post("/triage/{request_id}/return")
def return_for_information(
    request_id: uuid.UUID, payload: ReturnRequest, db: Db, principal: CurrentUser
) -> Ack:
    principal.require_role(Role.LEGAL_OPS, Role.COUNSEL, Role.HEAD_OF_LEGAL, Role.ADMIN)
    record = db.get(RequestRecord, request_id)
    if record is None:
        raise NotFound(REQUEST_NOT_FOUND)

    reason = payload.reason.strip()
    if not reason:
        raise ValidationFailed(
            "Say what is missing.",
            {"reason": "The requester is sent this wording verbatim."},
        )

    record.triage_notes = reason
    _transition_request(db, record, MatterState.RETURNED_FOR_INFORMATION, principal, reason)
    requester = db.get(User, record.requester_id)
    if requester:
        missing = "\n".join(f"- {item}" for item in payload.missing_information)
        notifications.notify(
            db,
            connector_code="mail_administrative",
            recipients=[requester.work_email],
            subject=f"More information needed on {record.reference}",
            body=(
                f"{reason}\n\n{missing}\n\n"
                "No matter number has been issued yet. This message is administrative."
            ),
            record_reference=record.reference,
        )
    return Ack(
        message="Returned for information. The requester has been notified and no "
        "matter number was issued."
    )


@router.post("/triage/{request_id}/close")
def close_without_matter(
    request_id: uuid.UUID, payload: CloseRequest, db: Db, principal: CurrentUser
) -> Ack:
    """A preliminary enquiry may be answered and closed without a matter.

    The reason is demanded rather than defaulted. Closing is the one triage
    outcome that produces no matter to carry an explanation, so if the reason
    is not written here it is not written anywhere.
    """
    principal.require_role(Role.LEGAL_OPS, Role.COUNSEL, Role.HEAD_OF_LEGAL, Role.ADMIN)
    record = db.get(RequestRecord, request_id)
    if record is None:
        raise NotFound(REQUEST_NOT_FOUND)

    reason = payload.reason.strip()
    if not reason:
        raise ValidationFailed(
            "Say why this is being closed.",
            {
                "reason": (
                    "The requester is told, and this is the only place the reason is "
                    "recorded, because closing creates no matter to hold it."
                )
            },
        )

    record.triage_notes = "\n\n".join(part for part in (reason, payload.answer) if part)
    _transition_request(db, record, MatterState.CLOSED_WITHOUT_MATTER, principal, reason)

    requester = db.get(User, record.requester_id)
    if requester:
        answer = f"\n\n{payload.answer}" if payload.answer else ""
        notifications.notify(
            db,
            connector_code="mail_administrative",
            recipients=[requester.work_email],
            subject=f"{record.reference} has been answered and closed",
            body=(
                f"{reason}{answer}\n\n"
                "No matter number was issued. This message is administrative. "
                "Raise a new request if the position changes."
            ),
            record_reference=record.reference,
        )
    return Ack(
        message="Answered and closed without a matter. The reason is on the request "
        "record and the requester has been told."
    )


def _sla_for(db, matter: Matter) -> SlaOut | None:
    transitions = list(
        db.execute(
            select(MatterTransition)
            .where(MatterTransition.matter_id == matter.id)
            .order_by(MatterTransition.occurred_at)
        ).scalars()
    )
    if not transitions:
        return None

    segments: list[ClockSegment] = []
    for index, transition in enumerate(transitions):
        ends_at = transitions[index + 1].occurred_at if index + 1 < len(transitions) else None
        segments.append(
            ClockSegment(
                state=MatterState(transition.to_state),
                started_at=transition.occurred_at,
                ended_at=ends_at,
            )
        )

    status = evaluate(segments, matter.sla_target_hours, MatterState(matter.status))
    return SlaOut(
        target_hours=matter.sla_target_hours,
        elapsed_hours=round(status.elapsed_hours, 2),
        running=status.running,
        breached=status.breached,
        near_breach=status.near_breach,
        remaining_hours=round(status.remaining.total_seconds() / 3600, 2)
        if status.remaining
        else None,
    )


def _decorate(db, matter: Matter) -> MatterListItem:
    item = MatterListItem.model_validate(matter)
    item.days_open = (datetime.now(UTC) - matter.created_at).days
    item.sla = _sla_for(db, matter)
    return item


@router.get("/matters")
def list_matters(
    db: Db,
    principal: CurrentUser,
    entity: WorkingEntity,
    mine: bool = Query(default=False),
    status: str | None = Query(default=None),
    tier: str | None = Query(default=None),
    limit: int = Query(default=100, le=500),
) -> list[MatterListItem]:
    """Row-level security already scopes this to the caller's entities and
    excludes restricted matters they are not named on."""
    stmt = select(Matter).where(Matter.entity == entity)
    if mine:
        stmt = stmt.where(Matter.responsible_lawyer_id == uuid.UUID(principal.user_id))
    if status:
        stmt = stmt.where(Matter.status == status)
    if tier:
        stmt = stmt.where(Matter.risk_tier == tier)
    stmt = stmt.order_by(Matter.created_at.desc()).limit(limit)

    return [_decorate(db, matter) for matter in db.execute(stmt).scalars()]


@router.get("/matters/{matter_id}")
def get_matter(matter_id: uuid.UUID, db: Db, principal: CurrentUser) -> MatterOut:
    matter = db.get(Matter, matter_id)
    if matter is None:
        raise NotFound(MATTER_NOT_FOUND)

    out = MatterOut.model_validate(matter)
    out.days_open = (datetime.now(UTC) - matter.created_at).days
    out.sla = _sla_for(db, matter)
    previous = MatterState(matter.state_before_hold) if matter.state_before_hold else None
    out.permitted_transitions = sorted(
        state.value for state in permitted_next(MatterState(matter.status), previous)
    )
    if matter.restricted:
        audit.record(
            db,
            action="restricted_matter_read",
            object_type="matter",
            object_id=matter.number,
            actor_id=principal.user_id,
            actor_label=principal.name,
            entity=matter.entity,
        )
    return out


@router.get("/matters/{matter_id}/request")
def matter_request(matter_id: uuid.UUID, db: Db, principal: CurrentUser) -> RequestDetail | None:
    """What the requester actually asked for, on the matter it became.

    A matter carries the legal position. The request carries what a colleague
    said they needed and in what words, and that is what a reader has to check
    the position against. Null where a matter was opened directly rather than
    from a request.
    """
    del principal
    matter = db.get(Matter, matter_id)
    if matter is None:
        raise NotFound(MATTER_NOT_FOUND)
    if matter.request_id is None:
        return None

    record = db.get(RequestRecord, matter.request_id)
    return _request_detail(db, record) if record else None


@router.patch("/matters/{matter_id}")
def update_matter(
    matter_id: uuid.UUID, payload: MatterUpdate, db: Db, principal: CurrentUser
) -> MatterOut:
    principal.require_role(Role.LEGAL_OPS, Role.COUNSEL, Role.HEAD_OF_LEGAL, Role.ADMIN)
    matter = db.get(Matter, matter_id)
    if matter is None:
        raise NotFound(MATTER_NOT_FOUND)

    before = {
        "priority": matter.priority,
        "next_action": matter.next_action,
        "due_date": matter.due_date,
        "blocker": matter.blocker,
    }
    for field, value in payload.model_dump(exclude_unset=True).items():
        setattr(matter, field, value)

    audit.record(
        db,
        action="matter_updated",
        object_type="matter",
        object_id=matter.number,
        actor_id=principal.user_id,
        actor_label=principal.name,
        entity=matter.entity,
        before_state=before,
        after_state=payload.model_dump(exclude_unset=True),
    )
    return get_matter(matter_id, db, principal)


@router.post("/matters/{matter_id}/transitions")
def transition_matter(
    matter_id: uuid.UUID, payload: TransitionRequest, db: Db, principal: CurrentUser
) -> MatterOut:
    principal.require_role(Role.LEGAL_OPS, Role.COUNSEL, Role.HEAD_OF_LEGAL, Role.ADMIN)
    matter = db.get(Matter, matter_id)
    if matter is None:
        raise NotFound(MATTER_NOT_FOUND)

    current = MatterState(matter.status)
    target = MatterState(payload.to_state)
    previous = MatterState(matter.state_before_hold) if matter.state_before_hold else None

    try:
        rules = assert_transition(current, target, previous, payload.reason)
    except IllegalTransition as exc:
        raise Conflict(str(exc)) from exc

    invalidated = 0
    if rules.invalidates_approvals:
        from app.services.approvals import invalidate_for_hash

        latest_hash = matter.next_action or ""
        invalidated = len(
            invalidate_for_hash(db, matter.id, latest_hash, f"The matter moved to {target.value}.")
        )

    now = datetime.now(UTC)
    if target is MatterState.ON_HOLD:
        matter.state_before_hold = current.value
    elif current is MatterState.ON_HOLD:
        matter.state_before_hold = None

    matter.status = target.value
    if payload.next_action:
        matter.next_action = payload.next_action

    db.add(
        MatterTransition(
            matter_id=matter.id,
            from_state=current.value,
            to_state=target.value,
            reason=payload.reason,
            actor_id=uuid.UUID(principal.user_id),
            occurred_at=now,
            invalidated_approvals=invalidated,
            clock_running=not rules.pauses_clock,
        )
    )
    audit.record(
        db,
        action="matter_transition",
        object_type="matter",
        object_id=matter.number,
        actor_id=principal.user_id,
        actor_label=principal.name,
        entity=matter.entity,
        before_state={"status": current.value},
        after_state={"status": target.value, "reason": payload.reason},
    )
    return get_matter(matter_id, db, principal)


@router.post("/matters/{matter_id}/decisions", response_model=DecisionOut, status_code=201)
def record_decision(
    matter_id: uuid.UUID, payload: DecisionRequest, db: Db, principal: CurrentUser
) -> DecisionRecord:
    """A decision and its reason, so the memory survives the individual.

    The authority matrix in PRD section 14.3 decides who may record which
    position, and what has to be recorded alongside it.
    """
    matter = db.get(Matter, matter_id)
    if matter is None:
        raise NotFound(MATTER_NOT_FOUND)

    level = AuthorityLevel(payload.authority_level)
    rule = AUTHORITY_MATRIX[level]
    if not principal.has_role(*rule["roles"]):
        raise Forbidden(f"Accepting {level.value.replace('_', ' ')} requires {rule['label']}.")
    if rule["residual_risk"] and not payload.residual_risk_accepted:
        raise ValidationFailed(
            f"Accepting {level.value.replace('_', ' ')} requires explicit residual-risk "
            "acceptance.",
            {"residual_risk_accepted": "Record the residual-risk acceptance."},
        )
    if level is AuthorityLevel.FALLBACK_2 and not payload.commercial_rationale:
        raise ValidationFailed(
            "Fallback 2 requires a commercial rationale alongside the reason.",
            {"commercial_rationale": "State the commercial rationale."},
        )

    record = DecisionRecord(
        sequence=sequences.new_decision_sequence(db),
        matter_id=matter.id,
        entity=matter.entity,
        decision=payload.decision,
        reason=payload.reason,
        alternatives_considered=payload.alternatives_considered,
        clause_references=payload.clause_references,
        authority_level=level.value,
        residual_risk_accepted=payload.residual_risk_accepted,
        commercial_rationale=payload.commercial_rationale,
        decided_by_id=uuid.UUID(principal.user_id),
        decided_at=datetime.now(UTC),
        counterparty_id=payload.counterparty_id or matter.counterparty_id,
    )
    db.add(record)
    db.flush()

    if rule["library_review"]:
        notifications.notify(
            db,
            connector_code="mail_administrative",
            recipients=["headoflegal@dsn.example"],
            subject=f"Clause library review raised by decision {record.sequence}",
            body=(
                "A position outside every approved fallback was accepted on matter "
                f"{matter.number}. The clause library needs review."
            ),
            record_reference=matter.number,
        )

    audit.record(
        db,
        action="decision_recorded",
        object_type="matter",
        object_id=matter.number,
        actor_id=principal.user_id,
        actor_label=principal.name,
        entity=matter.entity,
        after_state={"authority": level.value, "decision": payload.decision},
    )
    return record


@router.get("/matters/{matter_id}/decisions", response_model=list[DecisionOut])
def list_decisions(matter_id: uuid.UUID, db: Db, principal: CurrentUser) -> list[DecisionRecord]:
    return list(
        db.execute(
            select(DecisionRecord)
            .where(DecisionRecord.matter_id == matter_id)
            .order_by(DecisionRecord.decided_at.desc())
        ).scalars()
    )


@router.post("/matters/{matter_id}/counterparty")
def link_counterparty(
    matter_id: uuid.UUID, payload: CounterpartyLink, db: Db, principal: CurrentUser
) -> MatterOut:
    """Attach a counterparty to a matter that has none.

    A matter can be opened before anyone knows who the other side is, and until
    it is linked the counterparty record carries none of this matter's history.
    Replacing an existing link needs a reason, because that is a change of fact
    rather than the filling in of a blank.

    A counterparty is one permanent identity across both organisations rather
    than a per-entity record, so there is no entity to check it against. What
    is separated is the matter, not the company it is with.
    """
    principal.require_role(Role.LEGAL_OPS, Role.COUNSEL, Role.HEAD_OF_LEGAL, Role.ADMIN)
    matter = db.get(Matter, matter_id)
    if matter is None:
        raise NotFound(MATTER_NOT_FOUND)

    counterparty = db.get(Counterparty, payload.counterparty_id)
    if counterparty is None:
        raise NotFound("That counterparty was not found.")

    previous = matter.counterparty_id
    if previous == counterparty.id:
        return get_matter(matter_id, db, principal)
    if previous is not None and not (payload.reason or "").strip():
        raise ValidationFailed(
            "Say why the counterparty is changing.",
            {"reason": "This matter is already linked, so replacing the link is a change of fact."},
        )

    matter.counterparty_id = counterparty.id
    audit.record(
        db,
        action="matter_counterparty_linked",
        object_type="matter",
        object_id=matter.number,
        actor_id=principal.user_id,
        actor_label=principal.name,
        entity=matter.entity,
        before_state={"counterparty_id": str(previous) if previous else None},
        after_state={
            "counterparty_id": str(counterparty.id),
            "reference": counterparty.reference,
            "reason": payload.reason,
        },
    )
    return get_matter(matter_id, db, principal)


@router.post("/matters/{matter_id}/reassign")
def reassign(
    matter_id: uuid.UUID, payload: ReassignRequest, db: Db, principal: CurrentUser
) -> MatterOut:
    """Reassignment records both owners, the reason and the time, and retains
    the full history on the matter (LOP-M02-US-07)."""
    principal.require_role(Role.HEAD_OF_LEGAL, Role.ADMIN)
    matter = db.get(Matter, matter_id)
    if matter is None:
        raise NotFound(MATTER_NOT_FOUND)

    previous_id = matter.responsible_lawyer_id
    previous = db.get(User, previous_id) if previous_id else None
    incoming = db.get(User, payload.owner_id)
    if incoming is None:
        raise NotFound("That user was not found.")

    matter.responsible_lawyer_id = incoming.id
    if previous:
        previous.workload = max(0, previous.workload - 1)
    incoming.workload += 1

    for user in filter(None, [previous, incoming]):
        notifications.notify(
            db,
            connector_code="mail_administrative",
            recipients=[user.work_email],
            subject=f"Matter {matter.number} reassigned",
            body=(
                f"{matter.number} moved from "
                f"{previous.name if previous else 'unassigned'} to {incoming.name}. "
                f"Reason: {payload.reason}"
            ),
            record_reference=matter.number,
            matter_id=matter.id,
        )

    audit.record(
        db,
        action="matter_reassigned",
        object_type="matter",
        object_id=matter.number,
        actor_id=principal.user_id,
        actor_label=principal.name,
        entity=matter.entity,
        before_state={"owner": str(previous_id)},
        after_state={"owner": str(incoming.id), "reason": payload.reason},
    )
    return get_matter(matter_id, db, principal)


@router.post("/matters/{matter_id}/restrict")
def set_restricted(
    matter_id: uuid.UUID, payload: RestrictRequest, db: Db, principal: CurrentUser
) -> Ack:
    """A matter can be marked restricted by counsel or above."""
    principal.require_role(Role.COUNSEL, Role.HEAD_OF_LEGAL, Role.ADMIN)
    principal.require_step_up("change the restriction on a matter")

    matter = db.get(Matter, matter_id)
    if matter is None:
        raise NotFound(MATTER_NOT_FOUND)

    matter.restricted = payload.restricted
    matter.classification = "restricted" if payload.restricted else "confidential"

    if payload.restricted:
        named = set(payload.named_users) | {uuid.UUID(principal.user_id)}
        if matter.responsible_lawyer_id:
            named.add(matter.responsible_lawyer_id)
        existing = {
            grant.user_id
            for grant in db.execute(
                select(MatterAccess).where(MatterAccess.matter_id == matter.id)
            ).scalars()
        }
        for user_id in named - existing:
            db.add(
                MatterAccess(
                    matter_id=matter.id,
                    user_id=user_id,
                    granted_by_id=uuid.UUID(principal.user_id),
                )
            )

    audit.record(
        db,
        action="matter_restriction_changed",
        object_type="matter",
        object_id=matter.number,
        actor_id=principal.user_id,
        actor_label=principal.name,
        entity=matter.entity,
        after_state={"restricted": payload.restricted, "reason": payload.reason},
    )
    return Ack(
        message=(
            "The matter is restricted and is now visible only to the named users."
            if payload.restricted
            else "The restriction has been lifted."
        )
    )


@router.post("/matters/{matter_id}/tier")
def override_tier(
    matter_id: uuid.UUID, payload: TierOverride, db: Db, principal: CurrentUser
) -> MatterOut:
    matter = db.get(Matter, matter_id)
    if matter is None:
        raise NotFound(MATTER_NOT_FOUND)

    proposed = RiskTier(payload.tier)
    lowering = proposed.value < matter.risk_tier
    if lowering and not tiering.may_lower_tier(principal.is_head_of_legal, payload.reason):
        raise Forbidden("A tier may only be lowered by the Head of Legal, with a recorded reason.")

    before = matter.risk_tier
    matter.risk_tier = proposed.value
    matter.tier_overridden = True
    matter.tier_override_reason = payload.reason
    matter.tier_rationale = list(matter.tier_rationale) + [
        f"Changed from {before} to {proposed.value} by {principal.name}: {payload.reason}"
    ]

    audit.record(
        db,
        action="matter_tier_changed",
        object_type="matter",
        object_id=matter.number,
        actor_id=principal.user_id,
        actor_label=principal.name,
        entity=matter.entity,
        before_state={"tier": before},
        after_state={"tier": proposed.value, "reason": payload.reason},
    )
    return get_matter(matter_id, db, principal)


@router.post("/matters/{matter_id}/links", status_code=201)
def link_matter(matter_id: uuid.UUID, payload: LinkRequest, db: Db, principal: CurrentUser) -> Ack:
    matter = db.get(Matter, matter_id)
    target = db.get(Matter, payload.linked_matter_id)
    if matter is None or target is None:
        raise NotFound(MATTER_NOT_FOUND)

    db.add(
        MatterLink(
            matter_id=matter.id,
            linked_matter_id=target.id,
            link_type=payload.link_type,
        )
    )
    return Ack(message=f"{matter.number} is now linked to {target.number}.")
