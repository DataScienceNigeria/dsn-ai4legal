"""Administration, access control and audit, M15."""

from __future__ import annotations

import csv
import hashlib
import io
import json
import uuid
from datetime import UTC, date, datetime, time, timedelta

from fastapi import APIRouter, Query
from fastapi.responses import StreamingResponse
from sqlalchemy import func, or_, select

from app.core import audit
from app.core.deps import CurrentUser, Db, WorkingEntity
from app.core.errors import Conflict, Forbidden, NotFound, ValidationFailed
from app.core.security import hash_password
from app.db.models.ai import Capability, EvaluationRun
from app.db.models.evaluation import GoldenCase, GoldenSet
from app.db.models.organisation import ConfigSetting, Organisation, User, UserEntity
from app.db.models.platform import (
    AuditEvent,
    Connector,
    DeletionRequest,
    EgressLog,
    ExportRequest,
    RetentionPolicy,
)
from app.domain.enums import CapabilityState, DataClass, Entity, Role
from app.schemas.common import AuditEventOut
from app.schemas.governance import (
    AIInteractionOut,
    CapabilityGateUpdate,
    CapabilityOut,
    CapabilityToggle,
    DeletionRequestCreate,
    EvaluationRunOut,
    ExportRequestCreate,
    GoldenCaseOut,
    GoldenSetImport,
    GoldenSetOut,
    LegalHoldRequest,
    MfaReset,
    OrganisationOut,
    OrganisationUpdate,
    PasswordSet,
    SecondApproval,
    UserCreate,
    UserStatus,
    UserUpdate,
)
from app.services import evaluation

router = APIRouter(tags=["admin"])

CAPABILITY_NOT_FOUND = "That capability is not in the register."


def _decorate(capability: Capability) -> CapabilityOut:
    model = CapabilityOut.model_validate(capability)
    model.passes_gate = capability.passes_gate
    model.gate_status = capability.gate_status
    return model


@router.get("/capabilities")
def list_capabilities(db: Db, principal: CurrentUser) -> list[CapabilityOut]:
    """The capability register. Nothing runs as an unnamed model call."""
    principal.require_role(Role.ADMIN, Role.HEAD_OF_LEGAL, Role.AUDITOR, Role.COUNSEL)
    return [
        _decorate(c)
        for c in db.execute(
            select(Capability).order_by(Capability.module, Capability.name)
        ).scalars()
    ]


@router.post("/capabilities/{code}/state")
def set_capability_state(
    code: str, payload: CapabilityToggle, db: Db, principal: CurrentUser
) -> CapabilityOut:
    """The kill switch. Any capability can be disabled instantly, per capability
    and per agreement type, without a deployment (PRD section 13.5)."""
    principal.require_role(Role.ADMIN, Role.HEAD_OF_LEGAL)
    principal.require_step_up("change a capability state")

    capability = db.execute(
        select(Capability).where(Capability.code == code)
    ).scalar_one_or_none()
    if capability is None:
        raise NotFound(CAPABILITY_NOT_FOUND)

    state = CapabilityState(payload.state)
    before = {"state": capability.state, "disabled_for": list(capability.disabled_for_types or [])}

    if payload.agreement_type:
        types = set(capability.disabled_for_types or [])
        if state is CapabilityState.DISABLED:
            types.add(payload.agreement_type)
        else:
            types.discard(payload.agreement_type)
        capability.disabled_for_types = sorted(types)
    else:
        if state is CapabilityState.ENABLED and capability.blocks_calls:
            raise Conflict(
                f"{capability.name} scores {capability.last_score} against a gate of "
                f"{capability.gate_threshold}, and this gate is set to stop calls. "
                "Measure it again, or change the gate."
            )
        capability.state = state.value
        capability.disabled_reason = payload.reason if state is CapabilityState.DISABLED else None

    audit.record(
        db,
        action="capability_state_changed",
        object_type="capability",
        object_id=capability.code,
        actor_id=principal.user_id,
        actor_label=principal.name,
        before_state=before,
        after_state={
            "state": capability.state,
            "disabled_for": capability.disabled_for_types,
            "reason": payload.reason,
        },
    )
    return _decorate(capability)


def _capability(db, code: str) -> Capability:
    capability = db.execute(
        select(Capability).where(Capability.code == code)
    ).scalar_one_or_none()
    if capability is None:
        raise NotFound(CAPABILITY_NOT_FOUND)
    return capability


def _shape(code: str) -> tuple[dict, str, bool]:
    """The expected answer this capability's scorer reads, published so a set
    can be written without reading the scorer."""
    shape = evaluation.shape_of(code)
    if shape is None:
        return (
            {},
            "This capability has no scorer, so no golden set can be measured against it.",
            False,
        )
    return shape.example, shape.note, True


@router.get("/capabilities/{code}/golden-set")
def get_golden_set(code: str, db: Db, principal: CurrentUser) -> GoldenSetOut:
    """The set the gate is measured against, and every case in it.

    A capability with no set is not an error. It is a capability nobody has
    written cases for yet, and the interface needs the expected shape to let
    somebody start.
    """
    principal.require_role(Role.ADMIN, Role.HEAD_OF_LEGAL, Role.AUDITOR, Role.COUNSEL)
    _capability(db, code)
    example, note, measurable = _shape(code)

    golden = evaluation.active_set(db, code)
    if golden is None:
        return GoldenSetOut(
            id=None,
            name=code,
            version=0,
            capability_code=code,
            description=None,
            active=False,
            cases=[],
            expected_shape=example,
            shape_note=note,
            measurable=measurable,
        )
    return GoldenSetOut(
        id=golden.id,
        name=golden.name,
        version=golden.version,
        capability_code=golden.capability_code,
        description=golden.description,
        active=golden.active,
        cases=[GoldenCaseOut.model_validate(case) for case in golden.cases],
        expected_shape=example,
        shape_note=note,
        measurable=measurable,
    )


@router.post("/capabilities/{code}/golden-set/import", status_code=201)
def import_golden_set(
    code: str, payload: GoldenSetImport, db: Db, principal: CurrentUser
) -> GoldenSetOut:
    """Take a file of cases and land them as the next version of the set.

    A set arrives whole rather than a case at a time, because the cases are
    written together by the people who would otherwise argue about whether an
    answer was right, and a set assembled one box at a time is a set nobody
    reviewed. Each case is checked against the shape its scorer reads before
    anything is stored, so a mistyped key is refused rather than scored zero.
    """
    principal.require_role(Role.ADMIN, Role.HEAD_OF_LEGAL)
    _capability(db, code)

    if evaluation.shape_of(code) is None:
        raise Conflict(
            f"{code} has no scorer, so a golden set could never be measured against it."
        )

    previous = list(
        db.execute(select(GoldenSet).where(GoldenSet.capability_code == code)).scalars()
    )
    current = evaluation.active_set(db, code)
    carried = (
        [case for case in current.cases if case.active]
        if current is not None and payload.keep_existing
        else []
    )

    incoming = [
        (case.reference.strip(), case) for case in payload.cases if case.reference.strip()
    ]
    problems: list[str] = []
    for reference, case in incoming:
        problems.extend(evaluation.check_case(code, reference, case.prompt, case.expected))

    references = [reference for reference, _ in incoming]
    duplicates = sorted({one for one in references if references.count(one) > 1})
    if duplicates:
        problems.append(f"These references appear more than once: {', '.join(duplicates)}.")
    if problems:
        raise ValidationFailed(
            "No case was imported. Every case is checked before any is stored.",
            {"cases": " ".join(problems[:8])},
        )

    replaced = {reference for reference, _ in incoming}
    for existing in previous:
        existing.active = False

    golden = GoldenSet(
        name=payload.name or (current.name if current else code),
        version=max((row.version for row in previous), default=0) + 1,
        capability_code=code,
        description=payload.description or (current.description if current else None),
        owner_id=uuid.UUID(principal.user_id),
        active=True,
    )
    db.add(golden)
    db.flush()

    # A carried case whose reference the import repeats is superseded, not
    # duplicated, so importing a corrected case fixes it rather than leaving
    # both answers in the set.
    for case in carried:
        if case.reference in replaced:
            continue
        db.add(
            GoldenCase(
                set_id=golden.id,
                reference=case.reference,
                prompt=case.prompt,
                context=case.context,
                expected=case.expected,
                notes=case.notes,
                source=case.source,
                active=True,
            )
        )
    for reference, case in incoming:
        db.add(
            GoldenCase(
                set_id=golden.id,
                reference=reference,
                prompt=case.prompt,
                context=case.context,
                expected=case.expected,
                notes=case.notes,
                source=case.source or "Imported",
                active=True,
            )
        )
    db.flush()

    audit.record(
        db,
        action="golden_set_imported",
        object_type="golden_set",
        object_id=f"{golden.name}@v{golden.version}",
        actor_id=principal.user_id,
        actor_label=principal.name,
        before_state={"version": current.version if current else 0},
        after_state={
            "capability": code,
            "version": golden.version,
            "imported": len(incoming),
            "carried": len(golden.cases) - len(incoming),
        },
    )
    example, note, measurable = _shape(code)
    return GoldenSetOut(
        id=golden.id,
        name=golden.name,
        version=golden.version,
        capability_code=code,
        description=golden.description,
        active=True,
        cases=[GoldenCaseOut.model_validate(case) for case in golden.cases],
        expected_shape=example,
        shape_note=note,
        measurable=measurable,
    )


@router.post("/capabilities/{code}/gate")
def set_capability_gate(
    code: str, payload: CapabilityGateUpdate, db: Db, principal: CurrentUser
) -> CapabilityOut:
    """Move the line, or change what crossing it does.

    A threshold written into a seed file is a number. A threshold somebody set,
    against a named metric, with a reason recorded, is a control. Both the old
    and the new gate are written to the audit so a score can always be read
    against the gate that was in force when it was taken.
    """
    principal.require_role(Role.ADMIN, Role.HEAD_OF_LEGAL)
    principal.require_step_up("change a capability gate")
    capability = _capability(db, code)

    if payload.gate_threshold is not None and evaluation.shape_of(code) is None:
        raise ValidationFailed(
            "A threshold cannot be set on this capability.",
            {
                "gate_threshold": (
                    f"{capability.name} has no scorer, so nothing could ever measure it "
                    "against a threshold. Leave the threshold empty."
                )
            },
        )

    before = {
        "metric_name": capability.metric_name,
        "gate_expression": capability.gate_expression,
        "gate_threshold": capability.gate_threshold,
        "gate_enforced": capability.gate_enforced,
    }
    capability.metric_name = payload.metric_name.strip()
    capability.gate_expression = payload.gate_expression.strip()
    capability.gate_threshold = payload.gate_threshold
    capability.gate_enforced = payload.gate_enforced

    audit.record(
        db,
        action="capability_gate_changed",
        object_type="capability",
        object_id=capability.code,
        actor_id=principal.user_id,
        actor_label=principal.name,
        before_state=before,
        after_state={
            "metric_name": capability.metric_name,
            "gate_expression": capability.gate_expression,
            "gate_threshold": capability.gate_threshold,
            "gate_enforced": capability.gate_enforced,
            "reason": payload.reason,
            "last_score": capability.last_score,
        },
    )
    return _decorate(capability)


@router.post("/capabilities/{code}/run-evaluation")
def run_evaluation(
    code: str, db: Db, principal: CurrentUser, entity: WorkingEntity
) -> CapabilityOut:
    """Run the capability over its golden set and record what it scored.

    The run changes nothing but the score. A capability that fails shows as
    failing in the register and waits for somebody to decide, and a disabled
    one is still measurable, so it can be shown to pass before it is turned
    back on.
    """
    principal.require_role(Role.ADMIN, Role.HEAD_OF_LEGAL)
    capability = _capability(db, code)

    try:
        evaluation.run(
            db,
            capability,
            entity=entity,
            actor_id=principal.user_id,
            actor_label=principal.name,
        )
    except evaluation.NotMeasurable as exception:
        raise ValidationFailed(
            "This capability cannot be measured yet.", {"golden_set": str(exception)}
        ) from exception

    return _decorate(capability)


@router.get("/capabilities/{code}/evaluations", response_model=list[EvaluationRunOut])
def list_evaluations(code: str, db: Db, principal: CurrentUser) -> list[EvaluationRun]:
    """Every measurement taken, newest first, so a trend is visible."""
    principal.require_role(Role.ADMIN, Role.HEAD_OF_LEGAL, Role.AUDITOR, Role.COUNSEL)
    capability = _capability(db, code)
    return list(
        db.execute(
            select(EvaluationRun)
            .where(EvaluationRun.capability_id == capability.id)
            .order_by(EvaluationRun.run_at.desc())
            .limit(50)
        ).scalars()
    )


@router.get("/ai/interactions")
def list_interactions(
    db: Db,
    principal: CurrentUser,
    capability: str | None = None,
    matter_id: uuid.UUID | None = None,
    limit: int = Query(default=100, le=500),
) -> list[AIInteractionOut]:
    """The AI trace. Prompt reference, sources, route, cost and the human
    decision that followed."""
    principal.require_role(
        Role.ADMIN, Role.HEAD_OF_LEGAL, Role.AUDITOR, Role.COUNSEL
    )
    from app.db.models.ai import AIInteraction

    stmt = select(AIInteraction)
    if capability:
        stmt = stmt.where(AIInteraction.capability_code == capability)
    if matter_id:
        stmt = stmt.where(AIInteraction.matter_id == matter_id)
    return list(
        db.execute(stmt.order_by(AIInteraction.created_at.desc()).limit(limit)).scalars()
    )


def _audit_filtered(
    stmt,
    *,
    object_type: str | None = None,
    object_id: str | None = None,
    action: str | None = None,
    entity: str | None = None,
    q: str | None = None,
    from_date: date | None = None,
    to_date: date | None = None,
):
    """One filter, applied identically to the screen and to the export.

    An export that does not carry the filter the reader was looking at is a
    different document from the one they asked for, and they have no way to
    tell. Both go through here so they cannot drift.

    ``to_date`` is inclusive. A reader asking for the 14th means the whole of
    the 14th, and an exclusive bound silently drops the day they asked about.
    """
    if object_type:
        stmt = stmt.where(AuditEvent.object_type == object_type)
    if object_id:
        stmt = stmt.where(AuditEvent.object_id == object_id)
    if action:
        stmt = stmt.where(AuditEvent.action == action)
    if entity:
        stmt = stmt.where(AuditEvent.entity == entity)
    if q:
        like = f"%{q.strip().lower()}%"
        stmt = stmt.where(
            or_(
                func.lower(AuditEvent.action).like(like),
                func.lower(AuditEvent.actor_label).like(like),
                func.lower(AuditEvent.object_type).like(like),
                func.lower(AuditEvent.object_id).like(like),
                func.lower(AuditEvent.detail).like(like),
            )
        )
    if from_date:
        stmt = stmt.where(
            AuditEvent.occurred_at >= datetime.combine(from_date, time.min, tzinfo=UTC)
        )
    if to_date:
        stmt = stmt.where(
            AuditEvent.occurred_at
            < datetime.combine(to_date + timedelta(days=1), time.min, tzinfo=UTC)
        )
    return stmt


@router.get("/audit/events", response_model=list[AuditEventOut])
def audit_events(
    db: Db,
    principal: CurrentUser,
    object_type: str | None = None,
    object_id: str | None = None,
    action: str | None = None,
    entity: str | None = None,
    q: str | None = None,
    from_date: date | None = None,
    to_date: date | None = None,
    limit: int = Query(default=200, le=1000),
) -> list[AuditEvent]:
    principal.require_role(Role.ADMIN, Role.AUDITOR, Role.HEAD_OF_LEGAL)

    stmt = _audit_filtered(
        select(AuditEvent),
        object_type=object_type,
        object_id=object_id,
        action=action,
        entity=entity,
        q=q,
        from_date=from_date,
        to_date=to_date,
    )
    return list(
        db.execute(stmt.order_by(AuditEvent.occurred_at.desc()).limit(limit)).scalars()
    )


CSV_FORMULA_LEAD = ("=", "+", "-", "@", "\t", "\r")

AUDIT_CSV_COLUMNS = [
    "sequence",
    "occurred_at",
    "actor_label",
    "entity",
    "object_type",
    "object_id",
    "action",
    "result",
    "detail",
    "previous_digest",
    "digest",
]


def _csv_safe(value: object) -> str:
    """Neutralise a cell a spreadsheet would treat as a formula.

    An audit export is opened in Excel by the people least able to inspect it,
    and a field beginning with = or + is executed there rather than shown.
    Quoting the value keeps it readable and inert. This is a property of the
    export, not of the record: nothing in the audit table is altered.
    """
    if value is None:
        return ""
    text = str(value)
    return f"'{text}" if text.startswith(CSV_FORMULA_LEAD) else text


@router.get("/audit/events.csv")
def audit_events_csv(
    db: Db,
    principal: CurrentUser,
    object_type: str | None = None,
    object_id: str | None = None,
    action: str | None = None,
    entity: str | None = None,
    q: str | None = None,
    from_date: date | None = None,
    to_date: date | None = None,
    limit: int = Query(default=5000, le=50000),
) -> StreamingResponse:
    """The audit trail as a file, for an auditor who works outside the screen.

    The chain columns travel with it. Without ``sequence``, ``previous_digest``
    and ``digest`` the export is a list of assertions that cannot be checked
    against anything, and the whole point of the trail is that it can be. The
    export is itself an audited event, because taking the record out of the
    platform is exactly the kind of act the record exists to capture.
    """
    principal.require_role(Role.ADMIN, Role.AUDITOR, Role.HEAD_OF_LEGAL)

    stmt = _audit_filtered(
        select(AuditEvent),
        object_type=object_type,
        object_id=object_id,
        action=action,
        entity=entity,
        q=q,
        from_date=from_date,
        to_date=to_date,
    )

    rows = list(
        db.execute(stmt.order_by(AuditEvent.sequence.desc()).limit(limit)).scalars()
    )

    audit.record(
        db,
        action="audit_exported",
        object_type="audit_event",
        object_id=None,
        actor_id=principal.user_id,
        actor_label=principal.name,
        entity=entity,
        after_state={
            "rows": len(rows),
            "format": "csv",
            "filters": {
                "object_type": object_type,
                "object_id": object_id,
                "action": action,
                "entity": entity,
                "search": q,
                "from": from_date.isoformat() if from_date else None,
                "to": to_date.isoformat() if to_date else None,
            },
        },
    )

    buffer = io.StringIO()
    writer = csv.writer(buffer, lineterminator="\n")
    writer.writerow(AUDIT_CSV_COLUMNS)
    for row in reversed(rows):
        writer.writerow(
            [_csv_safe(getattr(row, column, None)) for column in AUDIT_CSV_COLUMNS]
        )

    stamp = datetime.now(UTC).strftime("%Y%m%d-%H%M")
    return StreamingResponse(
        io.BytesIO(buffer.getvalue().encode("utf-8-sig")),
        media_type="text/csv",
        headers={
            "Content-Disposition": f'attachment; filename="audit-{stamp}.csv"',
            "X-Row-Count": str(len(rows)),
        },
    )


@router.get("/audit/verify")
def verify_audit(db: Db, principal: CurrentUser) -> dict:
    """Recompute the audit chain and report any row that does not reconcile."""
    principal.require_role(Role.ADMIN, Role.AUDITOR)
    problems = audit.verify_chain(db)
    return {
        "reconciled": not problems,
        "problems": problems,
        "message": (
            "The audit chain reconciles from the first event."
            if not problems
            else "The audit chain does not reconcile. Investigate immediately."
        ),
    }


#: Every particular a template is likely to name us by. Order is the order the
#: form asks in, which is the order they appear in an agreement's preamble.
ORGANISATION_FIELDS = [
    ("legal_name", "Legal name"),
    ("trading_name", "Trading name"),
    ("registration_number", "Registration number"),
    ("tax_identification_number", "Tax identification number"),
    ("registered_address", "Registered address"),
    ("default_jurisdiction", "Governing law"),
    ("contact_email", "Contact email"),
    ("contact_phone", "Contact phone"),
    ("website", "Website"),
    ("signatory_name", "Default signatory"),
    ("signatory_title", "Signatory title"),
]

#: The ones an agreement will not assemble without. The rest are useful and
#: not blocking, and marking everything mandatory would make the warning
#: meaningless.
ORGANISATION_REQUIRED = {
    "legal_name",
    "registration_number",
    "registered_address",
    "default_jurisdiction",
}


def _organisation_out(record: Organisation) -> OrganisationOut:
    model = OrganisationOut.model_validate(record)
    model.incomplete = [
        label
        for field, label in ORGANISATION_FIELDS
        if field in ORGANISATION_REQUIRED and not getattr(record, field, None)
    ]
    return model


@router.get("/organisations")
def current_organisation(
    db: Db, principal: CurrentUser, entity: WorkingEntity
) -> OrganisationOut:
    """The particulars the organisation you are working in is named by.

    One organisation, not both. Every other screen in the workspace shows the
    working entity and nothing else, and this was the one that showed them
    side by side. Two near-identical names in two identical cards is how the
    wrong record came to be renamed: the edit was correct, the card was not.
    The entity switch is how you reach the other, exactly as it is everywhere
    else.

    Readable by anyone who drafts, because it is what a document will say about
    us and a drafter needs to know whether it is right before generating.
    """
    principal.require_role(
        Role.COUNSEL, Role.HEAD_OF_LEGAL, Role.ADMIN, Role.AUDITOR
    )
    record = db.execute(
        select(Organisation).where(Organisation.entity_code == entity)
    ).scalar_one_or_none()
    if record is None:
        raise NotFound("That organisation was not found.")
    return _organisation_out(record)


@router.patch("/organisations/{entity_code}")
def update_organisation(
    entity_code: str,
    payload: OrganisationUpdate,
    db: Db,
    principal: CurrentUser,
    entity: WorkingEntity,
) -> OrganisationOut:
    """Change what an agreement says about us.

    Administrative rather than clerical. These values are copied verbatim into
    executed contracts, so a wrong registration number is wrong on paper that
    has already been signed, and the change is audited with both states.
    """
    principal.require_role(Role.ADMIN, Role.HEAD_OF_LEGAL)
    principal.require_step_up("Changing an organisation's particulars")

    wanted = entity_code.upper()
    if wanted != entity:
        # The working entity is the one on screen. Editing the other from here
        # is how a record gets changed by somebody who believed they were
        # looking at it.
        raise Conflict(
            f"You are working in {entity}. Switch to {wanted} before changing its "
            "particulars, so the record you edit is the one you are reading."
        )

    record = db.execute(
        select(Organisation).where(Organisation.entity_code == wanted)
    ).scalar_one_or_none()
    if record is None:
        raise NotFound("That organisation was not found.")

    changes = payload.model_dump(exclude_unset=True)
    cleaned = {
        field: (value.strip() or None) if isinstance(value, str) else value
        for field, value in changes.items()
    }
    if "legal_name" in cleaned and not cleaned["legal_name"]:
        raise ValidationFailed(
            "An organisation needs a legal name.",
            {"legal_name": "It is what every agreement names this entity by."},
        )

    before = {field: getattr(record, field) for field in cleaned}
    for field, value in cleaned.items():
        setattr(record, field, value)

    audit.record(
        db,
        action="organisation_updated",
        object_type="organisation",
        object_id=record.entity_code,
        actor_id=principal.user_id,
        actor_label=principal.name,
        entity=record.entity_code,
        before_state=before,
        after_state=cleaned,
    )
    db.flush()
    return _organisation_out(record)


@router.get("/connectors")
def list_connectors(db: Db, principal: CurrentUser) -> list[dict]:
    """Every route out of the platform, registered, owned and reviewed.

    Registration is a deployment act rather than a screen: a connector is code
    that knows how to talk to something, and a row added here would name a
    route nothing can travel. What the register is for is the opposite
    question, which is answerable from a screen: what routes exist, who owns
    each one, what it may carry, and when somebody last looked at it.
    """
    principal.require_role(Role.ADMIN, Role.HEAD_OF_LEGAL, Role.AUDITOR)
    owners = {
        user.id: user.name for user in db.execute(select(User)).scalars()
    }
    counts = dict(
        db.execute(
            select(EgressLog.connector_code, func.count(EgressLog.id)).group_by(
                EgressLog.connector_code
            )
        ).all()
    )
    return [
        {
            "code": c.code,
            "name": c.name,
            "purpose": c.purpose,
            "direction": c.direction,
            "permitted_data_classes": c.permitted_data_classes,
            "scopes": c.scopes,
            "review_date": c.review_date,
            "owner": owners.get(c.owner_id),
            "calls": counts.get(c.code, 0),
            "active": c.active,
        }
        for c in db.execute(select(Connector).order_by(Connector.name)).scalars()
    ]


@router.get("/connectors/egress")
def list_egress(
    db: Db,
    principal: CurrentUser,
    connector: str | None = None,
    limit: int = Query(default=50, le=200),
) -> list[dict]:
    """What actually went through the connectors.

    The register says what a route is permitted to carry. This says what it
    carried. A permitted class nothing has ever travelled under is worth
    asking about, and so is a route with a review date in the past that is
    still busy.
    """
    principal.require_role(Role.ADMIN, Role.HEAD_OF_LEGAL, Role.AUDITOR)
    statement = select(EgressLog).order_by(EgressLog.occurred_at.desc()).limit(limit)
    if connector:
        statement = statement.where(EgressLog.connector_code == connector)
    return [
        {
            "id": str(row.id),
            "occurred_at": row.occurred_at,
            "connector_code": row.connector_code,
            "purpose": row.purpose,
            "record_reference": row.record_reference,
            "data_class": row.data_class,
            "result": row.result,
            "detail": row.detail,
        }
        for row in db.execute(statement).scalars()
    ]


@router.get("/retention")
def retention(db: Db, principal: CurrentUser) -> list[dict]:
    principal.require_role(Role.ADMIN, Role.AUDITOR, Role.HEAD_OF_LEGAL)
    return [
        {
            "record_class": p.record_class,
            "retain_years": p.retain_years,
            "legal_hold": p.legal_hold,
            "hold_reason": p.hold_reason,
            "hold_set_at": p.hold_set_at,
            "deletion_requires_approval": p.deletion_requires_approval,
            "description": p.description,
        }
        for p in db.execute(
            select(RetentionPolicy).order_by(RetentionPolicy.record_class)
        ).scalars()
    ]


@router.post("/users/{user_id}/mfa/reset")
def reset_second_factor(
    user_id: uuid.UUID, payload: MfaReset, db: Db, principal: CurrentUser
) -> dict:
    """Clear someone's second factor so they can enrol a new device.

    This is the request an attacker would most like to make, so it is bounded.
    Only an administrator can make it, they must re-authenticate to do it, a
    reason is required, and it is recorded against both accounts. It removes
    the factor and the recovery codes; it does not enrol anything, so the next
    privileged act that person attempts will refuse until they have.
    """
    principal.require_role(Role.ADMIN)
    principal.require_step_up("reset someone else's second factor")

    reason = payload.reason.strip()
    if not reason:
        raise ValidationFailed(
            "Say why the factor is being reset.",
            {"reason": "This is the request an attacker makes, so it is never unexplained."},
        )

    user = db.get(User, user_id)
    if user is None:
        raise NotFound("That account was not found.")
    if str(user.id) == principal.user_id:
        raise ValidationFailed(
            "Use your own enrolment screen for your own factor.",
            {"user_id": "Resetting your own factor here would leave no second person involved."},
        )

    had_factor = bool(user.mfa_secret or user.mfa_enrolled_at)
    user.mfa_secret = None
    user.mfa_enrolled_at = None
    user.mfa_last_used_counter = None
    user.mfa_recovery_codes = []

    audit.record(
        db,
        action="mfa_reset_by_administrator",
        object_type="app_user",
        object_id=str(user.id),
        actor_id=principal.user_id,
        actor_label=principal.name,
        before_state={"enrolled": had_factor},
        after_state={"enrolled": False, "reason": reason},
    )
    return {
        "user_id": str(user.id),
        "name": user.name,
        "message": (
            f"{user.name} has no second factor now. Tell them to enrol a new device: "
            "anything that needs a step-up will refuse until they do."
        ),
    }


def _user_row(user: User) -> dict:
    return {
        "id": str(user.id),
        "name": user.name,
        "work_email": user.work_email,
        "roles": user.roles,
        "entities": user.entity_codes,
        "specialisms": user.specialisms,
        "workload": user.workload,
        "workload_ceiling": user.workload_ceiling,
        "active": user.active,
        "mfa_enrolled": user.mfa_enrolled_at is not None,
        "last_login": user.last_login,
    }


@router.get("/users")
def list_users(db: Db, principal: CurrentUser) -> list[dict]:
    principal.require_role(Role.ADMIN, Role.HEAD_OF_LEGAL, Role.COUNSEL)
    return [
        _user_row(u) for u in db.execute(select(User).order_by(User.name)).scalars()
    ]


PEOPLE_ADMINS = (Role.ADMIN, Role.HEAD_OF_LEGAL)


def _person(db, user_id: uuid.UUID) -> User:
    user = db.execute(select(User).where(User.id == user_id)).scalar_one_or_none()
    if user is None:
        raise NotFound("There is nobody with that identifier.")
    return user


def _checked_roles(roles: list[str]) -> list[str]:
    known = {role.value for role in Role}
    unknown = sorted(set(roles) - known)
    if unknown:
        raise ValidationFailed(
            "That role does not exist on this platform.",
            {"roles": f"Unknown: {', '.join(unknown)}."},
        )
    return sorted(set(roles))


def _checked_entities(entities: list[str]) -> list[str]:
    known = {entity.value for entity in Entity}
    unknown = sorted(set(entities) - known)
    if unknown:
        raise ValidationFailed(
            "That entity does not exist on this platform.",
            {"entities": f"Unknown: {', '.join(unknown)}. Use {', '.join(sorted(known))}."},
        )
    return sorted(set(entities))


def _set_entities(db, user: User, entities: list[str]) -> None:
    """Entity membership is the hard boundary, so it is replaced whole.

    Reach is the intersection of role and entity, never the wider of them: a
    person left on DSN alone cannot open an EAI matter whatever their role.
    """
    wanted = set(entities)
    for membership in list(user.entities):
        if membership.entity_code not in wanted:
            db.delete(membership)
    held = {membership.entity_code for membership in user.entities}
    for code in wanted - held:
        db.add(UserEntity(user_id=user.id, entity_code=code))


def _guard_last_administrator(db, user: User, roles: list[str], active: bool) -> None:
    """Nobody can leave the platform with no one able to run it.

    An administrator who takes their own role away, or suspends the only other
    one, locks every privileged act out of the platform for everybody. There is
    no recovery from inside the interface for that, only a hand on the
    database, so it is refused before it happens rather than explained after.
    """
    still_admin = active and Role.ADMIN.value in roles
    if still_admin or Role.ADMIN.value not in (user.roles or []):
        return
    others = db.execute(
        select(func.count(User.id)).where(
            User.id != user.id,
            User.active.is_(True),
            User.roles.any(Role.ADMIN.value),
        )
    ).scalar_one()
    if others == 0:
        raise Conflict(
            f"{user.name} is the only active administrator. Give the role to somebody "
            "else first, or nothing on this platform can be administered again."
        )


@router.post("/users", status_code=201)
def create_user(payload: UserCreate, db: Db, principal: CurrentUser) -> dict:
    """Add a person, with the roles and entities they reach.

    The password is set here and never appears again: it is hashed on the way
    in, and the audit records that it was set rather than what it was.
    """
    principal.require_role(*PEOPLE_ADMINS)
    principal.require_step_up("add a person")

    email = payload.work_email.strip().lower()
    if db.execute(select(User).where(User.work_email == email)).scalar_one_or_none():
        raise Conflict(f"{email} already belongs to somebody on this platform.")

    roles = _checked_roles(payload.roles)
    entities = _checked_entities(payload.entities)

    user = User(
        subject=email,
        name=payload.name.strip(),
        work_email=email,
        password_hash=hash_password(payload.password),
        roles=roles,
        specialisms=[s.strip() for s in payload.specialisms if s.strip()],
        workload=0,
        workload_ceiling=payload.workload_ceiling,
        active=True,
    )
    db.add(user)
    db.flush()
    for code in entities:
        db.add(UserEntity(user_id=user.id, entity_code=code))
    db.flush()

    audit.record(
        db,
        action="user_created",
        object_type="app_user",
        object_id=str(user.id),
        actor_id=principal.user_id,
        actor_label=principal.name,
        after_state={
            "name": user.name,
            "work_email": user.work_email,
            "roles": roles,
            "entities": entities,
            "password_set": True,
        },
    )
    return _user_row(user)


@router.patch("/users/{user_id}")
def update_user(
    user_id: uuid.UUID, payload: UserUpdate, db: Db, principal: CurrentUser
) -> dict:
    """Change who somebody is and what they reach."""
    principal.require_role(*PEOPLE_ADMINS)
    principal.require_step_up("change what somebody reaches")
    user = _person(db, user_id)

    roles = _checked_roles(payload.roles) if payload.roles is not None else list(user.roles or [])
    entities = (
        _checked_entities(payload.entities)
        if payload.entities is not None
        else user.entity_codes
    )
    if payload.roles is not None and str(user.id) == principal.user_id:
        if Role.ADMIN.value in (user.roles or []) and Role.ADMIN.value not in roles:
            raise Conflict(
                "You cannot take the administrator role away from yourself. Ask another "
                "administrator, so the change is somebody else's decision."
            )
    _guard_last_administrator(db, user, roles, user.active)

    before = {
        "name": user.name,
        "roles": list(user.roles or []),
        "entities": user.entity_codes,
        "specialisms": list(user.specialisms or []),
        "workload_ceiling": user.workload_ceiling,
    }

    if payload.name is not None:
        user.name = payload.name.strip()
    user.roles = roles
    if payload.entities is not None:
        _set_entities(db, user, entities)
    if payload.specialisms is not None:
        user.specialisms = [s.strip() for s in payload.specialisms if s.strip()]
    if payload.workload_ceiling is not None:
        user.workload_ceiling = payload.workload_ceiling
    db.flush()

    audit.record(
        db,
        action="user_changed",
        object_type="app_user",
        object_id=str(user.id),
        actor_id=principal.user_id,
        actor_label=principal.name,
        before_state=before,
        after_state={
            "name": user.name,
            "roles": user.roles,
            "entities": user.entity_codes,
            "specialisms": user.specialisms,
            "workload_ceiling": user.workload_ceiling,
            "reason": payload.reason,
        },
    )
    return _user_row(user)


@router.post("/users/{user_id}/password")
def set_user_password(
    user_id: uuid.UUID, payload: PasswordSet, db: Db, principal: CurrentUser
) -> dict:
    """Set somebody's password.

    Whoever sets it knows it, which is why it is a reset rather than a
    recovery: the person is expected to change it, and the act is on the audit
    under both names. The password itself is not written anywhere but the hash.
    """
    principal.require_role(*PEOPLE_ADMINS)
    principal.require_step_up("set somebody's password")
    user = _person(db, user_id)

    user.password_hash = hash_password(payload.password)
    audit.record(
        db,
        action="user_password_set",
        object_type="app_user",
        object_id=str(user.id),
        actor_id=principal.user_id,
        actor_label=principal.name,
        after_state={
            "subject": user.work_email,
            "by": principal.name,
            "reason": payload.reason,
        },
    )
    return _user_row(user)


@router.post("/users/{user_id}/status")
def set_user_status(
    user_id: uuid.UUID, payload: UserStatus, db: Db, principal: CurrentUser
) -> dict:
    """Suspend somebody, or bring them back.

    Suspension bites on the next request rather than the next sign-in: the
    active flag is read when the token is turned into a principal, so a
    session already open stops at its next call. Nothing is deleted, because
    the record is on decisions, approvals and the audit chain, and removing the
    row would break attribution on work that was validly done.
    """
    principal.require_role(*PEOPLE_ADMINS)
    principal.require_step_up("suspend or reinstate somebody")
    user = _person(db, user_id)

    if str(user.id) == principal.user_id and not payload.active:
        raise Conflict("You cannot suspend yourself.")
    _guard_last_administrator(db, user, list(user.roles or []), payload.active)

    before = {"active": user.active}
    user.active = payload.active
    audit.record(
        db,
        action="user_suspended" if not payload.active else "user_reinstated",
        object_type="app_user",
        object_id=str(user.id),
        actor_id=principal.user_id,
        actor_label=principal.name,
        before_state=before,
        after_state={"active": user.active, "reason": payload.reason},
    )
    return _user_row(user)


EXPORT_RATE_LIMIT_PER_DAY = 5


@router.post("/retention/{record_class}/hold")
def set_legal_hold(
    record_class: str,
    payload: LegalHoldRequest,
    db: Db,
    principal: CurrentUser,
) -> dict:
    """Records under hold cannot be deleted by any role, LOP-M15-US-04."""
    principal.require_role(Role.ADMIN, Role.HEAD_OF_LEGAL)
    principal.require_step_up("change a legal hold")

    policy = db.execute(
        select(RetentionPolicy).where(RetentionPolicy.record_class == record_class)
    ).scalar_one_or_none()
    if policy is None:
        raise NotFound("There is no retention policy for that record class.")

    if payload.hold and not payload.reason:
        raise ValidationFailed(
            "A legal hold needs a reason.",
            {"reason": "Say what the hold is for, so it can be lifted knowingly."},
        )

    before = {"legal_hold": policy.legal_hold, "hold_reason": policy.hold_reason}
    policy.legal_hold = payload.hold
    policy.hold_reason = payload.reason if payload.hold else None
    policy.hold_set_by_id = uuid.UUID(principal.user_id) if payload.hold else None
    policy.hold_set_at = datetime.now(UTC) if payload.hold else None

    audit.record(
        db,
        action="legal_hold_changed",
        object_type="retention_policy",
        object_id=record_class,
        actor_id=principal.user_id,
        actor_label=principal.name,
        before_state=before,
        after_state={"legal_hold": policy.legal_hold, "hold_reason": policy.hold_reason},
    )
    return {
        "record_class": record_class,
        "legal_hold": policy.legal_hold,
        "hold_reason": policy.hold_reason,
        "message": (
            f"{record_class} is under legal hold and cannot be deleted by any role."
            if policy.legal_hold
            else f"The hold on {record_class} is lifted."
        ),
    }


@router.post("/deletions", status_code=201)
def request_deletion(
    payload: DeletionRequestCreate,
    db: Db,
    principal: CurrentUser,
    entity: WorkingEntity,
) -> dict:
    """Deletion is policy, not habit, LOP-M15-US-04.

    A record under hold is refused outright. Everything else is a request that a
    second authorised user has to grant where the policy says so, and granting
    it produces a certificate.
    """
    principal.require_role(Role.ADMIN, Role.HEAD_OF_LEGAL)

    policy = db.execute(
        select(RetentionPolicy).where(RetentionPolicy.record_class == payload.record_class)
    ).scalar_one_or_none()
    if policy is None:
        raise NotFound("There is no retention policy for that record class.")
    if policy.legal_hold:
        raise Conflict(
            f"{payload.record_class} is under legal hold: {policy.hold_reason}. "
            "No role can delete it while the hold stands."
        )

    record = DeletionRequest(
        entity=entity,
        record_class=payload.record_class,
        object_type=payload.object_type,
        object_reference=payload.object_reference,
        reason=payload.reason,
        requested_by_id=uuid.UUID(principal.user_id),
        status="pending" if policy.deletion_requires_approval else "approved",
    )
    if not policy.deletion_requires_approval:
        record.decided_at = datetime.now(UTC)
        record.decision_reason = "The policy for this record class needs no second approval."
    db.add(record)
    db.flush()

    audit.record(
        db,
        action="deletion_requested",
        object_type="deletion_request",
        object_id=str(record.id),
        actor_id=principal.user_id,
        actor_label=principal.name,
        entity=entity,
        after_state={
            "record_class": payload.record_class,
            "object": payload.object_reference,
            "status": record.status,
        },
    )
    return {
        "id": str(record.id),
        "status": record.status,
        "message": (
            "The deletion is queued for a second authorised user."
            if record.status == "pending"
            else "The policy allows this deletion without a second approval."
        ),
    }


@router.post("/deletions/{deletion_id}/decision")
def decide_deletion(
    deletion_id: uuid.UUID,
    payload: SecondApproval,
    db: Db,
    principal: CurrentUser,
) -> dict:
    """The second authorised user grants or refuses, and never the requester."""
    principal.require_role(Role.ADMIN, Role.HEAD_OF_LEGAL)
    principal.require_step_up("approve a deletion")

    record = db.get(DeletionRequest, deletion_id)
    if record is None:
        raise NotFound("That deletion request was not found.")
    if record.status != "pending":
        raise Conflict(f"That request is already {record.status}.")
    if str(record.requested_by_id) == principal.user_id:
        raise Forbidden(
            "A deletion cannot be approved by the person who asked for it. That is "
            "what the second approval is."
        )

    policy = db.execute(
        select(RetentionPolicy).where(RetentionPolicy.record_class == record.record_class)
    ).scalar_one_or_none()
    if policy and policy.legal_hold:
        raise Conflict(
            f"{record.record_class} came under legal hold after the request was raised."
        )

    record.status = "approved" if payload.approve else "refused"
    record.approver_id = uuid.UUID(principal.user_id)
    record.decided_at = datetime.now(UTC)
    record.decision_reason = payload.reason

    audit.record(
        db,
        action="deletion_decided",
        object_type="deletion_request",
        object_id=str(record.id),
        actor_id=principal.user_id,
        actor_label=principal.name,
        entity=record.entity,
        after_state={"status": record.status, "reason": payload.reason},
    )
    return {"id": str(record.id), "status": record.status}


@router.post("/deletions/{deletion_id}/certificate")
def issue_deletion_certificate(
    deletion_id: uuid.UUID, db: Db, principal: CurrentUser
) -> dict:
    """Deletion leaves a certificate behind, so the deletion itself is evidenced."""
    principal.require_role(Role.ADMIN, Role.HEAD_OF_LEGAL)

    record = db.get(DeletionRequest, deletion_id)
    if record is None:
        raise NotFound("That deletion request was not found.")
    if record.status != "approved":
        raise Conflict(f"That request is {record.status} and cannot be executed.")
    if record.certificate_reference:
        return {
            "certificate_reference": record.certificate_reference,
            "certificate": record.certificate,
        }

    executed_at = datetime.now(UTC)
    reference = f"DEL-{executed_at:%Y}-{uuid.uuid4().hex[:8].upper()}"
    certificate = {
        "certificate_reference": reference,
        "record_class": record.record_class,
        "object_type": record.object_type,
        "object_reference": record.object_reference,
        "entity": record.entity,
        "reason": record.reason,
        "requested_by": str(record.requested_by_id),
        "approved_by": str(record.approver_id) if record.approver_id else None,
        "executed_at": executed_at.isoformat(),
        "executed_by": principal.name,
        "statement": (
            "The record named above was deleted under the retention policy for its "
            "class. The audit trail of this deletion is itself retained."
        ),
    }
    certificate["digest"] = hashlib.sha256(
        json.dumps(certificate, sort_keys=True).encode("utf-8")
    ).hexdigest()

    record.executed_at = executed_at
    record.certificate_reference = reference
    record.certificate = certificate

    audit.record(
        db,
        action="deletion_executed",
        object_type="deletion_request",
        object_id=str(record.id),
        actor_id=principal.user_id,
        actor_label=principal.name,
        entity=record.entity,
        after_state={"certificate_reference": reference, "digest": certificate["digest"]},
    )
    return {"certificate_reference": reference, "certificate": certificate}


@router.get("/deletions")
def list_deletions(db: Db, principal: CurrentUser, entity: WorkingEntity) -> list[dict]:
    principal.require_role(Role.ADMIN, Role.HEAD_OF_LEGAL, Role.AUDITOR)
    return [
        {
            "id": str(row.id),
            "record_class": row.record_class,
            "object_reference": row.object_reference,
            "reason": row.reason,
            "status": row.status,
            "certificate_reference": row.certificate_reference,
            "created_at": row.created_at,
            "decided_at": row.decided_at,
        }
        for row in db.execute(
            select(DeletionRequest)
            .where(DeletionRequest.entity == entity)
            .order_by(DeletionRequest.created_at.desc())
        ).scalars()
    ]


@router.post("/exports", status_code=201)
def request_export(
    payload: ExportRequestCreate,
    db: Db,
    principal: CurrentUser,
    entity: WorkingEntity,
) -> dict:
    """Bulk export requires approval by a second authorised user, LOP-M15-US-05.

    The request is rate limited per person per day, carries the data classes it
    would move, and is refused outright for restricted content.
    """
    principal.require_role(Role.ADMIN, Role.HEAD_OF_LEGAL, Role.AUDITOR)

    if DataClass.RESTRICTED.value in payload.data_classes:
        raise Forbidden(
            "Restricted content is not exportable in bulk. Export the specific "
            "record from the matter it belongs to instead."
        )

    since = datetime.now(UTC) - timedelta(days=1)
    recent = db.execute(
        select(func.count())
        .select_from(ExportRequest)
        .where(
            ExportRequest.requested_by_id == uuid.UUID(principal.user_id),
            ExportRequest.created_at >= since,
        )
    ).scalar_one()
    if recent >= EXPORT_RATE_LIMIT_PER_DAY:
        raise Conflict(
            f"That is {recent} export requests in a day, which is the limit. "
            "Ask the platform administrator if you need more."
        )

    record = ExportRequest(
        entity=entity,
        record_class=payload.record_class,
        scope=payload.scope,
        reason=payload.reason,
        data_classes=payload.data_classes,
        requested_by_id=uuid.UUID(principal.user_id),
        status="pending",
    )
    db.add(record)
    db.flush()

    audit.record(
        db,
        action="export_requested",
        object_type="export_request",
        object_id=str(record.id),
        actor_id=principal.user_id,
        actor_label=principal.name,
        entity=entity,
        after_state={
            "record_class": payload.record_class,
            "reason": payload.reason,
            "data_classes": payload.data_classes,
        },
    )
    return {
        "id": str(record.id),
        "status": "pending",
        "message": (
            "The export is queued for approval by a second authorised user. It is "
            "entity-scoped, rate limited and logged."
        ),
    }


@router.post("/exports/{export_id}/decision")
def decide_export(
    export_id: uuid.UUID,
    payload: SecondApproval,
    db: Db,
    principal: CurrentUser,
) -> dict:
    principal.require_role(Role.ADMIN, Role.HEAD_OF_LEGAL)
    principal.require_step_up("approve a bulk export")

    record = db.get(ExportRequest, export_id)
    if record is None:
        raise NotFound("That export request was not found.")
    if record.status != "pending":
        raise Conflict(f"That request is already {record.status}.")
    if str(record.requested_by_id) == principal.user_id:
        raise Forbidden(
            "A bulk export cannot be approved by the person who asked for it."
        )

    record.status = "approved" if payload.approve else "refused"
    record.approver_id = uuid.UUID(principal.user_id)
    record.decided_at = datetime.now(UTC)
    record.decision_reason = payload.reason

    audit.record(
        db,
        action="export_decided",
        object_type="export_request",
        object_id=str(record.id),
        actor_id=principal.user_id,
        actor_label=principal.name,
        entity=record.entity,
        after_state={"status": record.status, "reason": payload.reason},
    )
    return {"id": str(record.id), "status": record.status}


@router.get("/exports")
def list_exports(db: Db, principal: CurrentUser, entity: WorkingEntity) -> list[dict]:
    principal.require_role(Role.ADMIN, Role.HEAD_OF_LEGAL, Role.AUDITOR)
    return [
        {
            "id": str(row.id),
            "record_class": row.record_class,
            "reason": row.reason,
            "data_classes": row.data_classes,
            "status": row.status,
            "created_at": row.created_at,
            "decided_at": row.decided_at,
        }
        for row in db.execute(
            select(ExportRequest)
            .where(ExportRequest.entity == entity)
            .order_by(ExportRequest.created_at.desc())
        ).scalars()
    ]
