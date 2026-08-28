"""The Legal Consultant, stage 3 of the guide.

Legal shares a draft with external counsel, reads what comes back, and records
what it did with it. The consultant leads legal review alongside Legal in the
guide's responsibility matrix, which is a reader's authority and not a
decision-maker's: nothing here lets them approve, publish, sign or alter a
document. They write, Legal decides.

Access is granted one matter at a time. Asking for a review names the consultant
on that matter through ``matter_access``, and the row-level security rule added
in ``0028`` makes that grant their whole permission, so a consultant engaged on
one negotiation cannot read the rest of the portfolio.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime

from fastapi import APIRouter
from sqlalchemy import select

from app.core import audit
from app.core.deps import CurrentUser, Db, WorkingEntity
from app.core.errors import Conflict, Forbidden, NotFound, ValidationFailed
from app.db.models.document import Document
from app.db.models.matter import ConsultantReview, Matter, MatterAccess
from app.db.models.organisation import User
from app.domain.enums import Role
from app.schemas.lifecycle import (
    ConsultantAssessment,
    ConsultantComments,
    ConsultantReviewOut,
    ConsultantReviewRequest,
)
from app.services import notifications

router = APIRouter(tags=["consultants"])

NOT_FOUND = "That review was not found."
LEGAL = (Role.COUNSEL, Role.HEAD_OF_LEGAL, Role.ADMIN)


def _decorate(db, review: ConsultantReview) -> ConsultantReviewOut:
    model = ConsultantReviewOut.model_validate(review)
    matter = db.get(Matter, review.matter_id)
    if matter:
        model.matter_number = matter.number
        model.matter_title = matter.title
    if review.document_id:
        document = db.get(Document, review.document_id)
        model.document_name = document.name if document else None
    return model


@router.post(
    "/matters/{matter_id}/consultant-review",
    response_model=ConsultantReviewOut,
    status_code=201,
)
def request_review(
    matter_id: uuid.UUID,
    payload: ConsultantReviewRequest,
    db: Db,
    principal: CurrentUser,
    entity: WorkingEntity,
) -> ConsultantReviewOut:
    """Send a draft to external counsel and say what you want read.

    Granting access is part of asking. A consultant who has not been asked about
    a matter cannot open it, so there is no separate step to forget.
    """
    principal.require_role(*LEGAL)

    matter = db.get(Matter, matter_id)
    if matter is None:
        raise NotFound("That matter was not found.")

    consultant = db.get(User, payload.consultant_id)
    if consultant is None or Role.CONSULTANT.value not in (consultant.roles or []):
        raise ValidationFailed(
            "That person is not a legal consultant.",
            {"consultant_id": "Choose somebody who holds the consultant role."},
        )
    if matter.entity not in consultant.entity_codes:
        raise ValidationFailed(
            f"{consultant.name} is not engaged for {matter.entity}.",
            {"consultant_id": "Engage them for this organisation first."},
        )

    if payload.document_id and db.get(Document, payload.document_id) is None:
        raise NotFound("That document was not found.")

    review = ConsultantReview(
        entity=matter.entity,
        matter_id=matter.id,
        document_id=payload.document_id,
        consultant_id=consultant.id,
        requested_by_id=uuid.UUID(principal.user_id),
        brief=payload.brief,
        due_date=payload.due_date,
        status="requested",
    )
    db.add(review)

    named = db.execute(
        select(MatterAccess).where(
            MatterAccess.matter_id == matter.id, MatterAccess.user_id == consultant.id
        )
    ).scalar_one_or_none()
    if named is None:
        db.add(
            MatterAccess(
                matter_id=matter.id,
                user_id=consultant.id,
                granted_by_id=uuid.UUID(principal.user_id),
            )
        )
    db.flush()

    notifications.raise_in_app(
        db,
        recipient_id=consultant.id,
        entity=matter.entity,
        kind="consultant_review",
        title=f"A draft to read on {matter.number}",
        body=payload.brief[:400],
        href="/consultant",
        reference=matter.number,
    )

    audit.record(
        db,
        action="consultant_review_requested",
        object_type="matter",
        object_id=matter.number,
        actor_id=principal.user_id,
        actor_label=principal.name,
        entity=matter.entity,
        after_state={"consultant": consultant.name, "brief": payload.brief},
    )
    return _decorate(db, review)


@router.get("/consultant-reviews", response_model=list[ConsultantReviewOut])
def list_reviews(
    db: Db, principal: CurrentUser, entity: WorkingEntity, matter_id: uuid.UUID | None = None
) -> list[ConsultantReviewOut]:
    """Legal's view of what is out with counsel."""
    principal.require_role(*LEGAL)
    stmt = select(ConsultantReview).where(ConsultantReview.entity == entity)
    if matter_id:
        stmt = stmt.where(ConsultantReview.matter_id == matter_id)
    rows = db.execute(stmt.order_by(ConsultantReview.created_at.desc())).scalars()
    return [_decorate(db, review) for review in rows]


@router.get("/consultant-reviews/mine", response_model=list[ConsultantReviewOut])
def my_reviews(db: Db, principal: CurrentUser) -> list[ConsultantReviewOut]:
    """What this consultant has been asked to read.

    Theirs and nothing else, and no entity filter: a consultant is engaged by
    matter rather than by organisation, and the row-level security rule already
    limits this to matters they were named on.
    """
    principal.require_role(Role.CONSULTANT, Role.ADMIN)
    rows = db.execute(
        select(ConsultantReview)
        .where(ConsultantReview.consultant_id == uuid.UUID(principal.user_id))
        .order_by(ConsultantReview.created_at.desc())
    ).scalars()
    return [_decorate(db, review) for review in rows]


@router.post("/consultant-reviews/{review_id}/comments", response_model=ConsultantReviewOut)
def return_comments(
    review_id: uuid.UUID, payload: ConsultantComments, db: Db, principal: CurrentUser
) -> ConsultantReviewOut:
    """The consultant's answer.

    Comments, not changes. The draft is not theirs to edit, and a review that
    could rewrite the document would put wording into an agreement that no
    clause owner ever cleared.
    """
    principal.require_role(Role.CONSULTANT, Role.ADMIN)
    review = db.get(ConsultantReview, review_id)
    if review is None:
        raise NotFound(NOT_FOUND)
    if str(review.consultant_id) != principal.user_id and not principal.is_admin:
        raise Forbidden("That review was asked of somebody else.")
    if review.status == "assessed":
        raise Conflict("Legal has already assessed this review.")

    review.comments = payload.comments
    review.status = "returned"
    review.returned_at = datetime.now(UTC)

    if review.requested_by_id:
        matter = db.get(Matter, review.matter_id)
        notifications.raise_in_app(
            db,
            recipient_id=review.requested_by_id,
            entity=review.entity,
            kind="consultant_returned",
            title=f"Counsel has come back on {matter.number if matter else 'a matter'}",
            body=payload.comments[:400],
            href="/workspace/matters",
            reference=matter.number if matter else None,
        )

    audit.record(
        db,
        action="consultant_review_returned",
        object_type="consultant_review",
        object_id=str(review.id),
        actor_id=principal.user_id,
        actor_label=principal.name,
        entity=review.entity,
        after_state={"status": review.status},
    )
    return _decorate(db, review)


@router.post("/consultant-reviews/{review_id}/assessment", response_model=ConsultantReviewOut)
def assess(
    review_id: uuid.UUID, payload: ConsultantAssessment, db: Db, principal: CurrentUser
) -> ConsultantReviewOut:
    """What Legal did with the comments.

    The guide says Legal assesses the comments and incorporates the appropriate
    amendments while maintaining the organisation's position. Writing down which
    were taken and which were not is what makes the second half of that sentence
    auditable rather than aspirational, and it is the record somebody reads in
    two years when the clause is argued about.
    """
    principal.require_role(*LEGAL)
    review = db.get(ConsultantReview, review_id)
    if review is None:
        raise NotFound(NOT_FOUND)
    if review.status == "requested":
        raise Conflict("Counsel has not come back on this yet.")

    review.assessment = payload.assessment
    review.assessed_at = datetime.now(UTC)
    review.assessed_by_id = uuid.UUID(principal.user_id)
    review.status = "assessed"

    audit.record(
        db,
        action="consultant_review_assessed",
        object_type="consultant_review",
        object_id=str(review.id),
        actor_id=principal.user_id,
        actor_label=principal.name,
        entity=review.entity,
        after_state={"assessment": payload.assessment},
    )
    return _decorate(db, review)
