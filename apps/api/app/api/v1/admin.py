"""Administration, access control and audit, M15."""

from __future__ import annotations

import csv
import hashlib
import io
import json
import uuid
from datetime import UTC, datetime, timedelta

from fastapi import APIRouter, Query
from fastapi.responses import StreamingResponse
from sqlalchemy import func, select

from app.core import audit
from app.core.deps import CurrentUser, Db, WorkingEntity
from app.core.errors import Conflict, Forbidden, NotFound, ValidationFailed
from app.db.models.ai import Capability, EvaluationRun
from app.db.models.evaluation import GoldenCase, GoldenSet
from app.db.models.organisation import ConfigSetting, Organisation, User
from app.db.models.platform import (
    AuditEvent,
    Connector,
    DeletionRequest,
    ExportRequest,
    RetentionPolicy,
)
from app.domain.enums import CapabilityState, DataClass, Role
from app.schemas.common import AuditEventOut, ConfigValue
from app.schemas.governance import (
    AIInteractionOut,
    CapabilityOut,
    CapabilityToggle,
    DeletionRequestCreate,
    EvaluationRunOut,
    ExportRequestCreate,
    GoldenCaseCreate,
    GoldenCaseOut,
    GoldenSetCreate,
    GoldenSetOut,
    LegalHoldRequest,
    MfaReset,
    OrganisationOut,
    OrganisationUpdate,
    SecondApproval,
)
from app.services import evaluation

router = APIRouter(tags=["admin"])

CAPABILITY_NOT_FOUND = "That capability is not in the register."


def _decorate(capability: Capability) -> CapabilityOut:
    model = CapabilityOut.model_validate(capability)
    model.passes_gate = capability.passes_gate
    return model


@router.get("/capabilities")
def list_capabilities(db: Db, principal: CurrentUser) -> list[CapabilityOut]:
    """The capability register. Nothing runs as an unnamed model call."""
    principal.require_role(
        Role.ADMIN, Role.HEAD_OF_LEGAL, Role.AUDITOR, Role.COUNSEL, Role.PRIVACY
    )
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
        if state is CapabilityState.ENABLED and not capability.passes_gate:
            raise Conflict(
                f"{capability.name} scores {capability.last_score} against a gate of "
                f"{capability.gate_threshold}. A capability below its gate does not run."
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


@router.post("/capabilities/{code}/evaluate")
def record_evaluation(
    code: str,
    score: float,
    db: Db,
    principal: CurrentUser,
    score_label: str | None = None,
    set_size: int = 0,
) -> CapabilityOut:
    """Record a golden-set run. A capability that falls below its threshold is
    disabled until it passes again (PRD section 4.2)."""
    principal.require_role(Role.ADMIN)

    capability = db.execute(
        select(Capability).where(Capability.code == code)
    ).scalar_one_or_none()
    if capability is None:
        raise NotFound(CAPABILITY_NOT_FOUND)
    if capability.gate_threshold is None:
        raise ValidationFailed(
            "This capability has no gate defined, so a result cannot be assessed.",
            {"gate_threshold": "Define the gate before recording a result."},
        )

    passed = score >= capability.gate_threshold
    db.add(
        EvaluationRun(
            capability_id=capability.id,
            golden_set=capability.golden_set or "unspecified",
            set_size=set_size,
            score=score,
            score_label=score_label,
            threshold=capability.gate_threshold,
            passed=passed,
            run_at=datetime.now(UTC),
        )
    )
    capability.last_score = score
    capability.last_score_label = score_label
    capability.last_evaluated_at = datetime.now(UTC)

    if not passed and capability.state == CapabilityState.ENABLED.value:
        capability.state = CapabilityState.DISABLED.value
        capability.disabled_reason = (
            f"Scored {score} against a gate of {capability.gate_threshold} on the "
            f"{capability.golden_set} set. Disabled automatically."
        )

    audit.record(
        db,
        action="capability_evaluated",
        object_type="capability",
        object_id=capability.code,
        actor_id=principal.user_id,
        actor_label=principal.name,
        after_state={"score": score, "passed": passed, "state": capability.state},
    )
    return _decorate(capability)


def _capability(db, code: str) -> Capability:
    capability = db.execute(
        select(Capability).where(Capability.code == code)
    ).scalar_one_or_none()
    if capability is None:
        raise NotFound(CAPABILITY_NOT_FOUND)
    return capability


@router.get("/capabilities/{code}/golden-set")
def get_golden_set(code: str, db: Db, principal: CurrentUser) -> GoldenSetOut:
    """The set the gate is measured against, and every case in it."""
    principal.require_role(Role.ADMIN, Role.HEAD_OF_LEGAL, Role.AUDITOR, Role.COUNSEL)
    _capability(db, code)

    golden = evaluation.active_set(db, code)
    if golden is None:
        raise NotFound(
            f"No golden set exists for {code}, so its gate has nothing to measure."
        )
    return GoldenSetOut(
        id=golden.id,
        name=golden.name,
        version=golden.version,
        capability_code=golden.capability_code,
        description=golden.description,
        active=golden.active,
        cases=[GoldenCaseOut.model_validate(case) for case in golden.cases],
    )


@router.post("/capabilities/{code}/golden-set", status_code=201)
def create_golden_set(
    code: str, payload: GoldenSetCreate, db: Db, principal: CurrentUser
) -> GoldenSetOut:
    """A new version rather than an edit.

    Editing a set in place would make an old score unreadable, because nobody
    could say which cases produced it.
    """
    principal.require_role(Role.ADMIN, Role.HEAD_OF_LEGAL)
    _capability(db, code)

    previous = list(
        db.execute(
            select(GoldenSet).where(GoldenSet.capability_code == code)
        ).scalars()
    )
    for existing in previous:
        existing.active = False

    golden = GoldenSet(
        name=payload.name,
        version=max((row.version for row in previous), default=0) + 1,
        capability_code=code,
        description=payload.description,
        owner_id=uuid.UUID(principal.user_id),
        active=True,
    )
    db.add(golden)
    db.flush()

    audit.record(
        db,
        action="golden_set_created",
        object_type="golden_set",
        object_id=f"{golden.name}@v{golden.version}",
        actor_id=principal.user_id,
        actor_label=principal.name,
        after_state={"capability": code},
    )
    return GoldenSetOut(
        id=golden.id,
        name=golden.name,
        version=golden.version,
        capability_code=code,
        description=golden.description,
        active=True,
        cases=[],
    )


@router.post("/capabilities/{code}/golden-set/cases", status_code=201)
def add_golden_case(
    code: str, payload: GoldenCaseCreate, db: Db, principal: CurrentUser
) -> GoldenCaseOut:
    """One case: what goes in, and the answer a competent person would give."""
    principal.require_role(Role.ADMIN, Role.HEAD_OF_LEGAL, Role.COUNSEL)
    _capability(db, code)

    golden = evaluation.active_set(db, code)
    if golden is None:
        raise Conflict(
            f"No golden set exists for {code}. Create the set before adding cases."
        )

    case = GoldenCase(
        set_id=golden.id,
        reference=payload.reference,
        prompt=payload.prompt,
        context=payload.context,
        expected=payload.expected,
        notes=payload.notes,
        source=payload.source,
        active=True,
    )
    db.add(case)
    db.flush()

    audit.record(
        db,
        action="golden_case_added",
        object_type="golden_case",
        object_id=case.reference,
        actor_id=principal.user_id,
        actor_label=principal.name,
        after_state={"set": golden.name, "capability": code},
    )
    return GoldenCaseOut.model_validate(case)


@router.post("/capabilities/{code}/run-evaluation")
def run_evaluation(
    code: str, db: Db, principal: CurrentUser, entity: WorkingEntity
) -> CapabilityOut:
    """Run the capability over its golden set and act on the result.

    This is the measurement the gate depends on. A capability that falls below
    its threshold is disabled here, and a disabled one is still measurable, so
    it can come back when it passes again.
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
        Role.ADMIN, Role.HEAD_OF_LEGAL, Role.AUDITOR, Role.COUNSEL, Role.LEGAL_OPS
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


@router.get("/audit/events", response_model=list[AuditEventOut])
def audit_events(
    db: Db,
    principal: CurrentUser,
    object_type: str | None = None,
    object_id: str | None = None,
    action: str | None = None,
    limit: int = Query(default=200, le=1000),
) -> list[AuditEvent]:
    principal.require_role(Role.ADMIN, Role.AUDITOR, Role.HEAD_OF_LEGAL)

    stmt = select(AuditEvent)
    if object_type:
        stmt = stmt.where(AuditEvent.object_type == object_type)
    if object_id:
        stmt = stmt.where(AuditEvent.object_id == object_id)
    if action:
        stmt = stmt.where(AuditEvent.action == action)
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

    stmt = select(AuditEvent)
    if object_type:
        stmt = stmt.where(AuditEvent.object_type == object_type)
    if object_id:
        stmt = stmt.where(AuditEvent.object_id == object_id)
    if action:
        stmt = stmt.where(AuditEvent.action == action)
    if entity:
        stmt = stmt.where(AuditEvent.entity == entity)

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
def list_organisations(db: Db, principal: CurrentUser) -> list[OrganisationOut]:
    """The particulars each entity is named by in an agreement.

    Readable by anyone who drafts, because it is what a document will say about
    us and a drafter needs to know whether it is right before generating.
    """
    principal.require_role(
        Role.LEGAL_OPS, Role.COUNSEL, Role.HEAD_OF_LEGAL, Role.ADMIN, Role.AUDITOR
    )
    records = db.execute(select(Organisation).order_by(Organisation.entity_code)).scalars()
    return [_organisation_out(record) for record in records]


@router.patch("/organisations/{entity_code}")
def update_organisation(
    entity_code: str, payload: OrganisationUpdate, db: Db, principal: CurrentUser
) -> OrganisationOut:
    """Change what an agreement says about us.

    Administrative rather than clerical. These values are copied verbatim into
    executed contracts, so a wrong registration number is wrong on paper that
    has already been signed, and the change is audited with both states.
    """
    principal.require_role(Role.ADMIN, Role.HEAD_OF_LEGAL)
    principal.require_step_up("Changing an organisation's particulars")

    record = db.execute(
        select(Organisation).where(Organisation.entity_code == entity_code.upper())
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


@router.get("/config/{area}")
def get_config(area: str, db: Db, principal: CurrentUser) -> list[ConfigValue]:
    principal.require_role(Role.ADMIN, Role.HEAD_OF_LEGAL)
    return [
        ConfigValue(
            area=row.area,
            key=row.key,
            value=row.value,
            version=row.version,
            description=row.description,
        )
        for row in db.execute(
            select(ConfigSetting).where(
                ConfigSetting.area == area, ConfigSetting.active.is_(True)
            )
        ).scalars()
    ]


@router.patch("/config/{area}")
def set_config(
    area: str, payload: ConfigValue, db: Db, principal: CurrentUser
) -> ConfigValue:
    """Configuration without deployment. Changes are versioned and audited."""
    principal.require_role(Role.ADMIN, Role.HEAD_OF_LEGAL)
    principal.require_step_up("change platform configuration")

    existing = db.execute(
        select(ConfigSetting)
        .where(
            ConfigSetting.area == area,
            ConfigSetting.key == payload.key,
            ConfigSetting.active.is_(True),
        )
        .order_by(ConfigSetting.version.desc())
    ).scalars().first()

    version = (existing.version + 1) if existing else 1
    if existing:
        existing.active = False

    setting = ConfigSetting(
        area=area,
        key=payload.key,
        version=version,
        value=payload.value,
        description=payload.description,
        active=True,
        changed_by=uuid.UUID(principal.user_id),
    )
    db.add(setting)

    audit.record(
        db,
        action="configuration_changed",
        object_type="config_setting",
        object_id=f"{area}.{payload.key}",
        actor_id=principal.user_id,
        actor_label=principal.name,
        before_state={"value": existing.value} if existing else None,
        after_state={"value": payload.value, "version": version},
    )
    return ConfigValue(
        area=area,
        key=payload.key,
        value=payload.value,
        version=version,
        description=payload.description,
    )


@router.get("/connectors")
def list_connectors(db: Db, principal: CurrentUser) -> list[dict]:
    """Every route out of the platform, registered, owned and reviewed."""
    principal.require_role(Role.ADMIN, Role.HEAD_OF_LEGAL, Role.AUDITOR, Role.PRIVACY)
    return [
        {
            "code": c.code,
            "name": c.name,
            "purpose": c.purpose,
            "direction": c.direction,
            "permitted_data_classes": c.permitted_data_classes,
            "scopes": c.scopes,
            "review_date": c.review_date,
            "active": c.active,
        }
        for c in db.execute(select(Connector).order_by(Connector.name)).scalars()
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


@router.get("/users")
def list_users(db: Db, principal: CurrentUser) -> list[dict]:
    principal.require_role(Role.ADMIN, Role.HEAD_OF_LEGAL, Role.LEGAL_OPS, Role.COUNSEL)
    return [
        {
            "id": str(u.id),
            "name": u.name,
            "work_email": u.work_email,
            "roles": u.roles,
            "entities": u.entity_codes,
            "specialisms": u.specialisms,
            "workload": u.workload,
            "workload_ceiling": u.workload_ceiling,
            "active": u.active,
        }
        for u in db.execute(select(User).order_by(User.name)).scalars()
    ]


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
