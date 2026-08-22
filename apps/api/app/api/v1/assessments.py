"""Privacy, DPIA and AI assessment, M11."""

from __future__ import annotations

import uuid
from datetime import UTC, datetime

from fastapi import APIRouter
from sqlalchemy import select

from app.core import audit
from app.core.deps import CurrentUser, Db, WorkingEntity
from app.core.errors import Conflict, NotFound, ValidationFailed
from app.db.models.contract import Obligation
from app.db.models.governance import Assessment
from app.domain.enums import (
    ASSESSMENT_STAGE_ORDER,
    AssessmentStage,
    AssessmentType,
    ObligationStatus,
    Role,
)
from app.schemas.common import Ack
from app.schemas.governance import (
    AssessmentClose,
    AssessmentCreate,
    AssessmentOut,
    StageComplete,
)
from app.services import sequences

ASSESSMENT_NOT_FOUND = "That assessment was not found."

router = APIRouter(prefix="/assessments", tags=["assessments"])

REQUIRED_FIELDS = [
    "purpose",
    "intended_users",
    "affected_persons",
    "business_owner",
    "data_categories",
    "data_sources",
    "legal_basis",
    "retention",
    "hosting_locations",
    "transfers",
    "models",
    "vendors",
    "subprocessors",
    "connectors",
    "datasets",
    "material_contractual_terms",
    "potential_harms",
    "bias",
    "security_threats",
    "performance_limits",
    "human_oversight",
]

STAGE_OWNERS = {
    AssessmentStage.PRODUCT: "Product",
    AssessmentStage.ENGINEERING: "Engineering",
    AssessmentStage.LEGAL: "Legal",
    AssessmentStage.BUSINESS_OWNER: "Accountable business owner",
}


@router.get("", response_model=list[AssessmentOut])
def list_assessments(
    db: Db, principal: CurrentUser, entity: WorkingEntity, stage: str | None = None
) -> list[Assessment]:
    principal.require_role(
        Role.PRIVACY, Role.COUNSEL, Role.HEAD_OF_LEGAL, Role.LEGAL_OPS, Role.ADMIN
    )
    stmt = select(Assessment).where(Assessment.entity == entity)
    if stage:
        stmt = stmt.where(Assessment.stage == stage)
    return list(db.execute(stmt.order_by(Assessment.created_at.desc())).scalars())


@router.post("", response_model=AssessmentOut, status_code=201)
def create_assessment(
    payload: AssessmentCreate, db: Db, principal: CurrentUser
) -> Assessment:
    principal.require_role(Role.PRIVACY, Role.HEAD_OF_LEGAL, Role.ADMIN)

    assessment = Assessment(
        reference=sequences.new_assessment_reference(db),
        assessment_type=AssessmentType(payload.assessment_type).value,
        title=payload.title,
        entity=payload.entity,
        product_id=payload.product_id,
        vendor_id=payload.vendor_id,
        matter_id=payload.matter_id,
        contract_id=payload.contract_id,
        stage=AssessmentStage.INITIATED.value,
        captured=payload.captured,
        stage_records=[
            {"stage": stage.value, "status": "not_started", "owner_label": label}
            for stage, label in STAGE_OWNERS.items()
        ],
    )
    db.add(assessment)
    db.flush()

    audit.record(
        db,
        action="assessment_created",
        object_type="assessment",
        object_id=assessment.reference,
        actor_id=principal.user_id,
        actor_label=principal.name,
        entity=assessment.entity,
    )
    return assessment


@router.get("/{assessment_id}", response_model=AssessmentOut)
def get_assessment(
    assessment_id: uuid.UUID, db: Db, principal: CurrentUser
) -> Assessment:
    assessment = db.get(Assessment, assessment_id)
    if assessment is None:
        raise NotFound(ASSESSMENT_NOT_FOUND)
    return assessment


@router.post("/{assessment_id}/stages/{stage}/complete", response_model=AssessmentOut)
def complete_stage(
    assessment_id: uuid.UUID,
    stage: str,
    payload: StageComplete,
    db: Db,
    principal: CurrentUser,
) -> Assessment:
    """Stages route between Product, Engineering, Legal and the business owner."""
    assessment = db.get(Assessment, assessment_id)
    if assessment is None:
        raise NotFound(ASSESSMENT_NOT_FOUND)

    target = AssessmentStage(stage)
    records = list(assessment.stage_records or [])
    for record in records:
        if record.get("stage") == target.value:
            record["status"] = "complete"
            record["completed_at"] = datetime.now(UTC).isoformat()
            record["notes"] = payload.notes
            record["completed_by"] = principal.name
            break
    assessment.stage_records = records
    assessment.captured = {**(assessment.captured or {}), **payload.captured}

    index = ASSESSMENT_STAGE_ORDER.index(target)
    if index + 1 < len(ASSESSMENT_STAGE_ORDER):
        assessment.stage = ASSESSMENT_STAGE_ORDER[index + 1].value

    audit.record(
        db,
        action="assessment_stage_completed",
        object_type="assessment",
        object_id=assessment.reference,
        actor_id=principal.user_id,
        actor_label=principal.name,
        entity=assessment.entity,
        after_state={"stage": target.value, "next": assessment.stage},
    )
    return assessment


@router.post("/{assessment_id}/close", response_model=AssessmentOut)
def close_assessment(
    assessment_id: uuid.UUID,
    payload: AssessmentClose,
    db: Db,
    principal: CurrentUser,
) -> Assessment:
    """Closure requires a recorded residual-risk decision by a named owner.

    The platform will not close an assessment with an unassigned residual risk,
    and outstanding conditions become tracked tasks on the same engine as M08.
    """
    principal.require_role(Role.PRIVACY, Role.HEAD_OF_LEGAL, Role.ADMIN)

    assessment = db.get(Assessment, assessment_id)
    if assessment is None:
        raise NotFound(ASSESSMENT_NOT_FOUND)
    if assessment.stage == AssessmentStage.CLOSED.value:
        raise Conflict("That assessment is already closed.")

    if payload.residual_risk_decision not in {"accept", "mitigate", "escalate"}:
        raise ValidationFailed(
            "The residual-risk decision must be accept, mitigate or escalate.",
            {"residual_risk_decision": "Choose accept, mitigate or escalate."},
        )

    missing = [field for field in REQUIRED_FIELDS if not (assessment.captured or {}).get(field)]
    if missing:
        raise ValidationFailed(
            "This assessment cannot be closed while required detail is missing.",
            {
                field: f"{field.replace('_', ' ').capitalize()} has not been captured."
                for field in missing
            },
        )

    assessment.residual_risk_decision = payload.residual_risk_decision
    assessment.residual_risk_reason = payload.residual_risk_reason
    assessment.residual_risk_owner_id = payload.residual_risk_owner_id
    assessment.review_date = payload.review_date
    assessment.approved_at = datetime.now(UTC)
    assessment.stage = AssessmentStage.CLOSED.value

    created = 0
    for condition in assessment.conditions or []:
        if condition.get("satisfied"):
            continue
        db.add(
            Obligation(
                reference=f"{assessment.reference}-C{created + 1:02d}",
                assessment_id=assessment.id,
                entity=assessment.entity,
                name=condition.get("name", "Assessment condition"),
                description=condition.get("detail"),
                obligation_type="condition_precedent",
                owner_id=payload.residual_risk_owner_id,
                due_date=condition.get("due_date"),
                evidence_required=True,
                status=ObligationStatus.OPEN.value,
            )
        )
        created += 1

    audit.record(
        db,
        action="assessment_closed",
        object_type="assessment",
        object_id=assessment.reference,
        actor_id=principal.user_id,
        actor_label=principal.name,
        entity=assessment.entity,
        after_state={
            "residual_risk": payload.residual_risk_decision,
            "owner": str(payload.residual_risk_owner_id),
            "conditions_tracked": created,
        },
    )
    return assessment


@router.post("/{assessment_id}/reassess")
def trigger_reassessment(
    assessment_id: uuid.UUID, reason: str, db: Db, principal: CurrentUser
) -> Ack:
    """Material change to purpose, data, model, vendor or transfer route."""
    assessment = db.get(Assessment, assessment_id)
    if assessment is None:
        raise NotFound(ASSESSMENT_NOT_FOUND)

    assessment.reassessment_triggered = True
    assessment.stage = AssessmentStage.PRODUCT.value

    audit.record(
        db,
        action="assessment_reassessment_triggered",
        object_type="assessment",
        object_id=assessment.reference,
        actor_id=principal.user_id,
        actor_label=principal.name,
        entity=assessment.entity,
        detail=reason,
    )
    return Ack(message=f"{assessment.reference} reopened for reassessment.")
