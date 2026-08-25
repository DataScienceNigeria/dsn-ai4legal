"""Privacy, DPIA and AI assessment, M11."""

from __future__ import annotations

import uuid
from datetime import UTC, datetime

from fastapi import APIRouter
from sqlalchemy import select

from app.core import audit
from app.core.deps import CurrentUser, Db, WorkingEntity
from app.core.errors import Conflict, NotFound, Refused, ValidationFailed
from app.db.models.contract import Obligation
from app.db.models.governance import Assessment
from app.domain import dpia
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
    DpiaAnswers,
    DpiaDecision,
    DpiaFormOut,
    DpiaQuestionOut,
    DpiaSectionOut,
    DpiaStart,
    DpoAssessment,
    StageComplete,
)
from app.services import notifications, sequences

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


# The DPIA, as the department lead fills it in.
#
# Requesters are the team leads of other departments: the person building a
# product is the person who knows what it does with personal data. They answer;
# legal assesses. Two jobs, two sets of endpoints, one record.
#
# There is no data protection officer role, because nobody here holds that job
# and nothing else. The assessment is written by whoever is building the thing
# and read by legal, which is what data protection is in an organisation this
# size. Anyone signed in may open one; only legal may score or decide it.


@router.get("/form/dpia", response_model=DpiaFormOut)
def dpia_form(principal: CurrentUser) -> DpiaFormOut:
    """The form definition, served rather than duplicated in the interface.

    A form written twice disagrees with itself the first time either copy is
    edited, and a data protection assessment that asks different questions in
    two places is worse than one that asks the wrong questions consistently.
    """
    return DpiaFormOut(
        sections=[
            DpiaSectionOut(
                key=section.key,
                title=section.title,
                intent=section.intent,
                assessed=section.assessed,
                questions=[
                    DpiaQuestionOut(
                        key=question.key,
                        label=question.label,
                        kind=question.kind,
                        help_text=question.help_text,
                        options=list(question.options),
                        required=question.required,
                        depends_on=question.depends_on,
                    )
                    for question in section.questions
                ],
            )
            for section in dpia.SECTIONS
        ],
        decisions=[{"key": key, "label": label} for key, label in dpia.FINAL_DECISIONS.items()],
    )


@router.get("/mine", response_model=list[AssessmentOut])
def my_assessments(db: Db, principal: CurrentUser, entity: WorkingEntity) -> list[Assessment]:
    """The assessments this person raised.

    A department lead sees their own and nobody else's. They are not legal, and
    a list of every product in the organisation under assessment is not theirs
    to read.
    """
    stmt = (
        select(Assessment)
        .where(
            Assessment.entity == entity,
            Assessment.raised_by_id == uuid.UUID(principal.user_id),
        )
        .order_by(Assessment.created_at.desc())
    )
    return list(db.execute(stmt).scalars())


@router.post("/dpia", response_model=AssessmentOut, status_code=201)
def start_dpia(
    payload: DpiaStart, db: Db, principal: CurrentUser, entity: WorkingEntity
) -> Assessment:
    """Open a DPIA. Any department lead may, because they are the ones who know."""
    assessment = Assessment(
        reference=sequences.new_assessment_reference(db),
        assessment_type=AssessmentType.DPIA.value,
        title=payload.project_name,
        entity=entity,
        stage=AssessmentStage.INITIATED.value,
        raised_by_id=uuid.UUID(principal.user_id),
        captured={"project_name": payload.project_name},
        stage_records=[],
    )
    db.add(assessment)
    db.flush()

    audit.record(
        db,
        action="dpia_started",
        object_type="assessment",
        object_id=assessment.reference,
        actor_id=principal.user_id,
        actor_label=principal.name,
        entity=entity,
        after_state={"project": payload.project_name},
    )
    return assessment


def _own_or_legal(assessment: Assessment, principal) -> None:
    """The person who raised it, or the people whose job it is to read it."""
    if str(assessment.raised_by_id) == principal.user_id:
        return
    principal.require_role(Role.COUNSEL, Role.HEAD_OF_LEGAL, Role.ADMIN)


@router.patch("/{assessment_id}/answers", response_model=AssessmentOut)
def save_answers(
    assessment_id: uuid.UUID, payload: DpiaAnswers, db: Db, principal: CurrentUser
) -> Assessment:
    """Save what has been written so far.

    Saved as it is typed rather than on submission. A DPIA is not filled in at
    one sitting: it is fifty-nine questions across thirteen sections, several of
    which need somebody else in the building to answer, and losing a morning's
    work to a closed tab is how a form stops being filled in at all.
    """
    assessment = db.get(Assessment, assessment_id)
    if assessment is None:
        raise NotFound(ASSESSMENT_NOT_FOUND)
    _own_or_legal(assessment, principal)

    if assessment.stage == AssessmentStage.CLOSED.value:
        raise Conflict("This assessment is closed. Reopen it with a reassessment.")
    if assessment.submitted_at and str(assessment.raised_by_id) == principal.user_id:
        raise Conflict(
            "This assessment has been submitted and is with the legal team. "
            "Ask them to return it if it needs changing."
        )

    captured = dict(assessment.captured or {})
    captured.update(payload.answers)
    assessment.captured = captured

    if captured.get("project_name"):
        assessment.title = str(captured["project_name"])[:255]

    db.flush()
    return assessment


@router.post("/{assessment_id}/submit", response_model=AssessmentOut)
def submit_dpia(
    assessment_id: uuid.UUID, db: Db, principal: CurrentUser
) -> Assessment:
    """Hand it to the data protection officer.

    Refused while a required answer is missing, and the refusal names each one.
    A DPIA arriving half-filled costs the DPO a round trip and the lead a week,
    and the platform already knows exactly what is absent.
    """
    assessment = db.get(Assessment, assessment_id)
    if assessment is None:
        raise NotFound(ASSESSMENT_NOT_FOUND)
    _own_or_legal(assessment, principal)

    state = dpia.completeness(assessment.captured or {})
    if not state.complete:
        raise Refused(
            f"{len(state.missing)} answers are still needed before this can be submitted.",
            state.missing[:12],
        )

    assessment.submitted_at = datetime.now(UTC)
    assessment.stage = AssessmentStage.LEGAL.value

    audit.record(
        db,
        action="dpia_submitted",
        object_type="assessment",
        object_id=assessment.reference,
        actor_id=principal.user_id,
        actor_label=principal.name,
        entity=assessment.entity,
        after_state={"answers": state.answered},
    )

    notifications.raise_for_role(
        db,
        role=Role.COUNSEL.value,
        entity=assessment.entity,
        kind="dpia_submitted",
        title=f"DPIA for {assessment.title}",
        body=f"{principal.name} submitted {assessment.reference} for assessment.",
        href="/workspace/assessments",
        reference=assessment.reference,
    )
    return assessment


@router.post("/{assessment_id}/sections/{section}/assessment", response_model=AssessmentOut)
def record_section_assessment(
    assessment_id: uuid.UUID,
    section: str,
    payload: DpoAssessment,
    db: Db,
    principal: CurrentUser,
) -> Assessment:
    """The data protection officer's judgement on one section.

    Adequacy, reasons and a score out of ten, then recommendations with an owner
    and a date. The score is the DPO's, not a computation: it is what they think
    the information is worth against what the section reasonably required.
    """
    principal.require_role(Role.COUNSEL, Role.HEAD_OF_LEGAL, Role.ADMIN)

    assessment = db.get(Assessment, assessment_id)
    if assessment is None:
        raise NotFound(ASSESSMENT_NOT_FOUND)
    if section not in dpia.SECTIONS_BY_KEY:
        raise NotFound("That section is not part of the assessment.")
    if not dpia.SECTIONS_BY_KEY[section].assessed:
        raise Conflict(f"{dpia.SECTIONS_BY_KEY[section].title} is a record, not a judgement.")

    reviews = dict(assessment.dpo_review or {})
    reviews[section] = {
        "adequate": payload.adequate,
        "reasons": payload.reasons,
        "score": payload.score,
        "recommendations": payload.recommendations,
        "responsibility": payload.responsibility,
        "due_date": payload.due_date.isoformat() if payload.due_date else None,
        "assessed_by": principal.name,
        "assessed_at": datetime.now(UTC).isoformat(),
    }
    assessment.dpo_review = reviews
    db.flush()

    audit.record(
        db,
        action="dpia_section_assessed",
        object_type="assessment",
        object_id=assessment.reference,
        actor_id=principal.user_id,
        actor_label=principal.name,
        entity=assessment.entity,
        after_state={"section": section, "adequate": payload.adequate, "score": payload.score},
    )
    return assessment


@router.post("/{assessment_id}/decision", response_model=AssessmentOut)
def record_dpia_decision(
    assessment_id: uuid.UUID, payload: DpiaDecision, db: Db, principal: CurrentUser
) -> Assessment:
    """Go ahead, modify, or stop.

    Three outcomes and no fourth. "Stop" has to be one of them or the assessment
    is a formality, and a formality is what a DPIA becomes when the only
    available answer is a longer list of conditions.
    """
    principal.require_role(Role.COUNSEL, Role.HEAD_OF_LEGAL, Role.ADMIN)

    assessment = db.get(Assessment, assessment_id)
    if assessment is None:
        raise NotFound(ASSESSMENT_NOT_FOUND)
    if payload.decision not in dpia.FINAL_DECISIONS:
        raise ValidationFailed(
            "That is not one of the available decisions.",
            {"decision": f"Choose one of {', '.join(dpia.FINAL_DECISIONS)}."},
        )

    unassessed = [
        dpia.SECTIONS_BY_KEY[key].title
        for key in dpia.ASSESSED_SECTIONS
        if key not in (assessment.dpo_review or {})
    ]
    if unassessed:
        raise Refused(
            "Every section is assessed before the assessment concludes.",
            [f"Not yet assessed: {title}" for title in unassessed],
        )

    assessment.final_decision = payload.decision
    assessment.final_decision_reason = payload.reason
    assessment.approved_at = datetime.now(UTC)
    assessment.review_date = payload.review_date
    assessment.stage = AssessmentStage.CLOSED.value

    audit.record(
        db,
        action="dpia_decided",
        object_type="assessment",
        object_id=assessment.reference,
        actor_id=principal.user_id,
        actor_label=principal.name,
        entity=assessment.entity,
        after_state={"decision": payload.decision, "review_date": str(payload.review_date)},
    )

    if assessment.raised_by_id:
        notifications.raise_in_app(
            db,
            recipient_id=assessment.raised_by_id,
            entity=assessment.entity,
            kind="dpia_decided",
            title=f"{assessment.title}: {payload.decision.replace('_', ' ')}",
            body=dpia.FINAL_DECISIONS[payload.decision],
            href=f"/portal/assessments/{assessment.id}",
            reference=assessment.reference,
        )
    return assessment


@router.get("", response_model=list[AssessmentOut])
def list_assessments(
    db: Db, principal: CurrentUser, entity: WorkingEntity, stage: str | None = None
) -> list[Assessment]:
    principal.require_role(Role.COUNSEL, Role.HEAD_OF_LEGAL, Role.ADMIN)
    stmt = select(Assessment).where(Assessment.entity == entity)
    if stage:
        stmt = stmt.where(Assessment.stage == stage)
    return list(db.execute(stmt.order_by(Assessment.created_at.desc())).scalars())


@router.post("", response_model=AssessmentOut, status_code=201)
def create_assessment(
    payload: AssessmentCreate, db: Db, principal: CurrentUser
) -> Assessment:
    principal.require_role(Role.COUNSEL, Role.HEAD_OF_LEGAL, Role.ADMIN)

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
    principal.require_role(Role.COUNSEL, Role.HEAD_OF_LEGAL, Role.ADMIN)

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
