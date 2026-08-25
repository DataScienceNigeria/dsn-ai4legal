"""Workspace navigation: what is waiting, and where a record lives.

Two questions the interface could not answer before. How much work is behind
each menu item, and where is the record I can already name. Both are read-only
and both go through the same row-level security as the screens they point at,
so neither can surface a matter the caller cannot open.
"""

from __future__ import annotations

import uuid
from datetime import UTC, date, datetime

from fastapi import APIRouter, Query
from sqlalchemy import func, or_, select

from app.core.deps import CurrentUser, Db, WorkingEntity
from app.core.errors import NotFound
from app.db.models.contract import Contract, Obligation
from app.db.models.counterparty import Counterparty
from app.db.models.document import ReviewFinding
from app.db.models.governance import Assessment, Communication, ComplianceItem
from app.db.models.intake import Request as RequestRecord
from app.db.models.library import Template
from app.db.models.matter import Matter
from app.db.models.platform import Notification
from app.domain.enums import (
    AssessmentStage,
    MatterState,
    ObligationStatus,
    Role,
)
from app.schemas.workspace import (
    NavCounts,
    NotificationOut,
    NotificationPage,
    SearchHit,
    SearchResults,
)

router = APIRouter(prefix="/workspace", tags=["workspace"])

LEGAL = (Role.COUNSEL, Role.HEAD_OF_LEGAL, Role.ADMIN)

OPEN_MATTER_STATES = [
    MatterState.ACCEPTED.value,
    MatterState.DRAFTING.value,
    MatterState.IN_REVIEW.value,
    MatterState.ESCALATED.value,
    MatterState.IN_APPROVAL.value,
    MatterState.AWAITING_SIGNATURE.value,
    MatterState.ON_HOLD.value,
]

TRIAGE_STATES = [MatterState.SUBMITTED.value, MatterState.IN_TRIAGE.value]

CLOSED_ASSESSMENT_STAGES = [AssessmentStage.CLOSED.value]


def _count(db, stmt) -> int:
    return int(db.execute(select(func.count()).select_from(stmt.subquery())).scalar() or 0)


def _compliance_due(db, entity: str, today: date) -> int:
    """Filings due soon or already overdue.

    The window is a share of each filing's own cycle rather than a flat number
    of days, so it has to be worked out per row. The table holds one entry per
    statutory duty the organisation has, which is tens of rows, not thousands.
    """
    due = 0
    for item in db.execute(
        select(ComplianceItem).where(
            ComplianceItem.entity == entity,
            ComplianceItem.status == "open",
            ComplianceItem.next_due_date.is_not(None),
        )
    ).scalars():
        if (item.next_due_date - today).days <= item.due_soon_days:
            due += 1
    return due


@router.get("/counts")
def nav_counts(db: Db, principal: CurrentUser, entity: WorkingEntity) -> NavCounts:
    """What is waiting behind each menu item, for this entity.

    A badge answers "is there work here" without a visit, so every count is
    work outstanding rather than a total. A screen showing 248 records tells
    nobody anything; a screen showing 12 awaiting a decision does.
    """
    if not principal.has_role(*LEGAL):
        return NavCounts()

    today = date.today()

    open_matters = select(Matter.id).where(
        Matter.entity == entity, Matter.status.in_(OPEN_MATTER_STATES)
    )

    return NavCounts(
        triage=_count(
            db,
            select(RequestRecord.id).where(
                RequestRecord.entity == entity, RequestRecord.status.in_(TRIAGE_STATES)
            ),
        ),
        matters=_count(db, open_matters),
        review=_count(
            db,
            select(ReviewFinding.id)
            .join(Matter, Matter.id == ReviewFinding.matter_id)
            .where(Matter.entity == entity, ReviewFinding.decision == "pending"),
        ),
        obligations=_count(
            db,
            select(Obligation.id).where(
                Obligation.entity == entity,
                Obligation.status.in_(
                    [ObligationStatus.PROPOSED.value, ObligationStatus.OPEN.value]
                ),
            ),
        ),
        inbox=_count(
            db,
            select(Communication.id).where(
                Communication.entity == entity, Communication.handled.is_(False)
            ),
        ),
        assessments=_count(
            db,
            select(Assessment.id).where(
                Assessment.entity == entity,
                Assessment.stage.notin_(CLOSED_ASSESSMENT_STAGES),
            ),
        ),
        compliance=_compliance_due(db, entity, today),
    )


@router.get("/notifications")
def list_notifications(
    db: Db,
    principal: CurrentUser,
    entity: WorkingEntity,
    unread_only: bool = Query(default=False),
    limit: int = Query(default=30, le=100),
) -> NotificationPage:
    """This person's notifications in this organisation, newest first.

    Row-level security narrows the table to the recipient, so the filter here
    is a convenience rather than the control. Someone else's queue is not
    readable simply because it sits in the same organisation.
    """
    mine = Notification.recipient_id == uuid.UUID(principal.user_id)
    scope = (mine, Notification.entity == entity)

    stmt = select(Notification).where(*scope)
    if unread_only:
        stmt = stmt.where(Notification.read_at.is_(None))

    rows = list(
        db.execute(stmt.order_by(Notification.created_at.desc()).limit(limit)).scalars()
    )
    unread = _count(
        db, select(Notification.id).where(*scope, Notification.read_at.is_(None))
    )

    return NotificationPage(
        unread=unread,
        notifications=[NotificationOut.model_validate(row) for row in rows],
    )


@router.post("/notifications/{notification_id}/read")
def mark_read(
    notification_id: uuid.UUID, db: Db, principal: CurrentUser
) -> NotificationOut:
    record = db.get(Notification, notification_id)
    if record is None or str(record.recipient_id) != principal.user_id:
        # Absent rather than forbidden. Confirming that somebody else's
        # notification exists is itself a disclosure.
        raise NotFound("That notification was not found.")
    if record.read_at is None:
        record.read_at = datetime.now(UTC)
    db.flush()
    return NotificationOut.model_validate(record)


@router.post("/notifications/read-all")
def mark_all_read(db: Db, principal: CurrentUser, entity: WorkingEntity) -> NotificationPage:
    """Clear the bell for this organisation only.

    Entity-scoped on purpose. Clearing what is in front of you should not also
    clear a queue you are not currently looking at.
    """
    now = datetime.now(UTC)
    rows = list(
        db.execute(
            select(Notification).where(
                Notification.recipient_id == uuid.UUID(principal.user_id),
                Notification.entity == entity,
                Notification.read_at.is_(None),
            )
        ).scalars()
    )
    for row in rows:
        row.read_at = now
    db.flush()
    return NotificationPage(unread=0, notifications=[])


def _like(term: str) -> str:
    return f"%{term.lower()}%"


@router.get("/search")
def search(
    db: Db,
    principal: CurrentUser,
    entity: WorkingEntity,
    q: str = Query(min_length=2, max_length=120),
    limit: int = Query(default=6, le=20),
) -> SearchResults:
    """Find a record the caller can already name.

    Deliberately not the grounded answer that Ask memory gives. This resolves
    an identifier or a name to the screen that holds it, and states nothing
    about the record beyond what the list screens already show. Row-level
    security applies, so a restricted matter the caller is not named on is
    absent rather than redacted.
    """
    principal.require_role(*LEGAL)
    term = _like(q.strip())
    hits: list[SearchHit] = []

    for matter in db.execute(
        select(Matter)
        .where(
            Matter.entity == entity,
            or_(func.lower(Matter.number).like(term), func.lower(Matter.title).like(term)),
        )
        .order_by(Matter.created_at.desc())
        .limit(limit)
    ).scalars():
        hits.append(
            SearchHit(
                kind="matter",
                label=matter.title,
                reference=matter.number,
                detail=matter.status.replace("_", " "),
                href=f"/workspace/matters/{matter.id}",
            )
        )

    for record in db.execute(
        select(RequestRecord)
        .where(
            RequestRecord.entity == entity,
            or_(
                func.lower(RequestRecord.reference).like(term),
                func.lower(RequestRecord.subject).like(term),
            ),
        )
        .order_by(RequestRecord.created_at.desc())
        .limit(limit)
    ).scalars():
        hits.append(
            SearchHit(
                kind="request",
                label=record.subject,
                reference=record.reference,
                detail=record.status.replace("_", " "),
                href="/workspace/triage",
            )
        )

    for contract in db.execute(
        select(Contract)
        .where(
            Contract.entity == entity,
            or_(
                func.lower(Contract.reference).like(term),
                func.lower(Contract.agreement_type).like(term),
            ),
        )
        .order_by(Contract.created_at.desc())
        .limit(limit)
    ).scalars():
        hits.append(
            SearchHit(
                kind="contract",
                label=contract.agreement_type.replace("_", " "),
                reference=contract.reference,
                detail="executed" if contract.authoritative else "not executed",
                href="/workspace/archive",
            )
        )

    for template in db.execute(
        select(Template)
        .where(
            or_(func.lower(Template.code).like(term), func.lower(Template.name).like(term))
        )
        .order_by(Template.code)
        .limit(limit)
    ).scalars():
        if entity not in (template.entity_applicability or []):
            continue
        hits.append(
            SearchHit(
                kind="template",
                label=template.name,
                reference=template.code,
                detail=template.agreement_type.replace("_", " "),
                href=f"/workspace/library/{template.code}",
            )
        )

    for party in db.execute(
        select(Counterparty)
        .where(
            or_(
                func.lower(Counterparty.reference).like(term),
                func.lower(Counterparty.legal_name).like(term),
            )
        )
        .order_by(Counterparty.legal_name)
        .limit(limit)
    ).scalars():
        hits.append(
            SearchHit(
                kind="counterparty",
                label=party.legal_name,
                reference=party.reference,
                detail=party.jurisdiction,
                href="/workspace/counterparties",
            )
        )

    for obligation in db.execute(
        select(Obligation)
        .where(
            Obligation.entity == entity,
            or_(
                func.lower(Obligation.reference).like(term),
                func.lower(Obligation.name).like(term),
            ),
        )
        .order_by(Obligation.due_date.asc().nulls_last())
        .limit(limit)
    ).scalars():
        hits.append(
            SearchHit(
                kind="obligation",
                label=obligation.name,
                reference=obligation.reference,
                detail=obligation.status.replace("_", " "),
                href="/workspace/obligations",
            )
        )

    return SearchResults(query=q, hits=hits, searched_at=datetime.now(UTC))
