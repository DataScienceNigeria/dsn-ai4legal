"""Requests and intake, M01."""

from __future__ import annotations

import uuid
from datetime import UTC, datetime
from typing import Annotated

from fastapi import APIRouter, File, Request, UploadFile
from sqlalchemy import select

from app.core import audit
from app.core.deps import CurrentUser, Db, client_ip
from app.core.errors import NotFound, ValidationFailed
from app.db.models.intake import Attachment, RequestType
from app.db.models.intake import Request as RequestRecord
from app.db.models.matter import Matter
from app.db.models.organisation import User
from app.domain.enums import MatterState, Role
from app.schemas.common import Ack
from app.schemas.intake import (
    AttachmentOut,
    RequestCreate,
    RequestOut,
    RequestStatusOut,
    RequestTypeOut,
    TimelineEntry,
)
from app.services import notifications, sequences, storage
from app.services.hashing import file_hash

REQUEST_NOT_FOUND = "That request was not found."

router = APIRouter(prefix="/requests", tags=["requests"])

STAGE_LABELS: dict[str, str] = {
    MatterState.SUBMITTED.value: "Received",
    MatterState.IN_TRIAGE.value: "Being assessed by Legal",
    MatterState.RETURNED_FOR_INFORMATION.value: "Waiting for your information",
    MatterState.ACCEPTED.value: "Accepted, work has started",
    MatterState.DRAFTING.value: "Drafting",
    MatterState.IN_REVIEW.value: "In legal review",
    MatterState.IN_APPROVAL.value: "In approval",
    MatterState.AWAITING_SIGNATURE.value: "Awaiting signature",
    MatterState.EXECUTED.value: "Signed",
    MatterState.ACTIVE.value: "Live",
    MatterState.CLOSED_WITHOUT_MATTER.value: "Answered and closed",
}

TIMELINE_ORDER = [
    (MatterState.SUBMITTED.value, "Received"),
    (MatterState.IN_TRIAGE.value, "Triage"),
    (MatterState.ACCEPTED.value, "Accepted"),
    (MatterState.DRAFTING.value, "Drafting"),
    (MatterState.IN_APPROVAL.value, "Approval"),
    (MatterState.AWAITING_SIGNATURE.value, "Signature"),
    (MatterState.EXECUTED.value, "Signed"),
]


@router.get("/types", response_model=list[RequestTypeOut])
def list_request_types(db: Db, principal: CurrentUser) -> list[RequestType]:
    """Request types in business language, so a requester need not know legal
    categories (LOP-M01-US-01)."""
    return list(
        db.execute(
            select(RequestType)
            .where(RequestType.active.is_(True))
            .order_by(RequestType.sort_order, RequestType.business_label)
        ).scalars()
    )


def validate_mandatory(request_type: RequestType, payload: RequestCreate) -> dict[str, str]:
    """Submission is blocked while any mandatory field is empty, and the errors
    are field level rather than a generic failure (LOP-M01-US-03)."""
    errors: dict[str, str] = {}
    supplied = {
        "subject": payload.subject,
        "purpose": payload.purpose,
        "counterparty": payload.proposed_counterparty,
        "required_date": payload.required_date,
        "value_amount": payload.value_amount,
        **payload.answers,
    }
    labels = {f["name"]: f.get("label", f["name"]) for f in (request_type.fields or [])}

    for name in request_type.mandatory_fields or []:
        value = supplied.get(name)
        if value is None or (isinstance(value, str) and not value.strip()):
            errors[name] = f"{labels.get(name, name)} is required for this request type."
    return errors


@router.post("", response_model=RequestOut, status_code=201)
def create_request(
    payload: RequestCreate,
    db: Db,
    principal: CurrentUser,
    http_request: Request,
) -> RequestRecord:
    request_type = db.execute(
        select(RequestType).where(RequestType.code == payload.request_type_code)
    ).scalar_one_or_none()
    if request_type is None:
        raise NotFound("That request type is not available.")

    if not principal.in_entity(payload.entity):
        raise NotFound("That entity is not available to you.")

    errors = validate_mandatory(request_type, payload)
    if errors:
        raise ValidationFailed(
            "This request cannot be submitted while required information is missing.",
            errors,
        )

    privacy_flag = any(
        [
            payload.personal_data,
            payload.special_category_data,
            payload.third_party_confidential,
            payload.leaves_nigeria,
        ]
    )

    record = RequestRecord(
        reference=sequences.new_request_reference(db),
        entity=payload.entity,
        request_type_id=request_type.id,
        requester_id=uuid.UUID(principal.user_id),
        subject=payload.subject,
        purpose=payload.purpose,
        proposed_counterparty=payload.proposed_counterparty,
        counterparty_id=payload.counterparty_id,
        required_date=payload.required_date,
        value_amount=payload.value_amount,
        value_currency=payload.value_currency,
        personal_data=payload.personal_data,
        special_category_data=payload.special_category_data,
        third_party_confidential=payload.third_party_confidential,
        leaves_nigeria=payload.leaves_nigeria,
        privacy_flag=privacy_flag,
        answers=payload.answers,
        status=MatterState.SUBMITTED.value,
        acknowledged_at=datetime.now(UTC),
    )
    db.add(record)
    db.flush()

    notifications.notify(
        db,
        connector_code="mail_administrative",
        recipients=[principal.email],
        subject=f"We have your request, {record.reference}",
        body=(
            f"Thank you. Your request {record.reference} has been received.\n\n"
            f"What happens next: Legal will assess it and either accept it as a matter, "
            f"answer it and close it, or come back to you for more information. "
            f"You can expect an update within {request_type.sla_hours} working hours.\n\n"
            "This message is administrative. It contains no legal position or advice."
        ),
        record_reference=record.reference,
    )

    if privacy_flag:
        notifications.notify(
            db,
            connector_code="mail_administrative",
            recipients=["dpo@dsn.example"],
            subject=f"Privacy flag raised on {record.reference}",
            body=(
                f"Request {record.reference} declares personal data, special-category "
                "data, third-party confidential information, or a transfer out of "
                "Nigeria. A privacy review is required."
            ),
            record_reference=record.reference,
        )

    audit.record(
        db,
        action="request_submitted",
        object_type="request",
        object_id=record.reference,
        actor_id=principal.user_id,
        actor_label=principal.name,
        entity=record.entity,
        after_state={"status": record.status, "privacy_flag": privacy_flag},
        ip_address=client_ip(http_request),
        session_id=principal.session_id,
    )
    return record


@router.post("/{request_id}/attachments", response_model=AttachmentOut, status_code=201)
def add_attachment(
    request_id: uuid.UUID,
    db: Db,
    principal: CurrentUser,
    file: Annotated[UploadFile, File()],
) -> Attachment:
    record = db.get(RequestRecord, request_id)
    if record is None:
        raise NotFound(REQUEST_NOT_FOUND)

    data = file.file.read()
    content_type = file.content_type or "application/octet-stream"
    digest = storage.validate_upload(file.filename or "", content_type, data)

    clean, scan_detail = storage.scan_upload(data)
    if not clean:
        audit.record(
            db,
            action="upload_quarantined",
            object_type="request",
            object_id=record.reference,
            actor_id=principal.user_id,
            actor_label=principal.name,
            entity=record.entity,
            result="failure",
            detail=scan_detail,
        )
        raise ValidationFailed(
            "This file was refused and has been quarantined.", {"file": scan_detail}
        )

    key = f"requests/{record.reference}/{digest[:12]}-{file.filename}"
    storage.store.put(key, data, content_type)

    attachment = Attachment(
        request_id=record.id,
        filename=file.filename or "attachment",
        content_type=content_type,
        size_bytes=len(data),
        storage_key=key,
        content_hash=file_hash(data),
        scan_status="clean",
        uploaded_by_id=uuid.UUID(principal.user_id),
    )
    db.add(attachment)
    db.flush()

    audit.record(
        db,
        action="attachment_added",
        object_type="request",
        object_id=record.reference,
        actor_id=principal.user_id,
        actor_label=principal.name,
        entity=record.entity,
        after_state={"filename": attachment.filename, "bytes": attachment.size_bytes},
    )
    return attachment


@router.get("/mine")
def my_requests(db: Db, principal: CurrentUser) -> list[RequestStatusOut]:
    """A requester sees their own requests and nothing else (LOP-M01-US-06)."""
    records = list(
        db.execute(
            select(RequestRecord)
            .where(RequestRecord.requester_id == uuid.UUID(principal.user_id))
            .order_by(RequestRecord.created_at.desc())
        ).scalars()
    )
    return [_status_for(db, record) for record in records]


@router.get("/{request_id}", response_model=RequestOut)
def get_request(request_id: uuid.UUID, db: Db, principal: CurrentUser) -> RequestRecord:
    record = db.get(RequestRecord, request_id)
    if record is None:
        raise NotFound(REQUEST_NOT_FOUND)
    owns_it = str(record.requester_id) == principal.user_id
    if not owns_it and not principal.has_role(
        Role.LEGAL_OPS, Role.COUNSEL, Role.HEAD_OF_LEGAL, Role.ADMIN
    ):
        raise NotFound(REQUEST_NOT_FOUND)
    return record


@router.get("/{request_id}/status")
def request_status(
    request_id: uuid.UUID, db: Db, principal: CurrentUser
) -> RequestStatusOut:
    record = get_request(request_id, db, principal)
    return _status_for(db, record)


def _status_for(db, record: RequestRecord) -> RequestStatusOut:
    matter = db.execute(
        select(Matter).where(Matter.request_id == record.id)
    ).scalar_one_or_none()

    current_status = matter.status if matter else record.status
    owner_first_name = None
    if matter and matter.responsible_lawyer_id:
        owner = db.get(User, matter.responsible_lawyer_id)
        owner_first_name = owner.name.split()[0] if owner else None

    reached = False
    timeline: list[TimelineEntry] = []
    for state, label in TIMELINE_ORDER:
        is_current = state == current_status
        timeline.append(
            TimelineEntry(
                stage=state,
                label=label,
                occurred_at=record.created_at if state == MatterState.SUBMITTED.value else None,
                current=is_current,
                owner_first_name=owner_first_name if is_current else None,
            )
        )
        if is_current:
            reached = True
    if not reached and current_status in STAGE_LABELS:
        timeline.append(
            TimelineEntry(
                stage=current_status,
                label=STAGE_LABELS[current_status],
                occurred_at=None,
                current=True,
            )
        )

    return RequestStatusOut(
        reference=record.reference,
        subject=record.subject,
        status=current_status,
        stage_label=STAGE_LABELS.get(current_status, current_status.replace("_", " ")),
        owner_first_name=owner_first_name,
        expected_date=matter.due_date if matter else record.required_date,
        last_update=matter.updated_at if matter else record.updated_at,
        matter_number=matter.number if matter else None,
        timeline=timeline,
    )


@router.get("/{request_id}/acknowledgment")
def acknowledgment(request_id: uuid.UUID, db: Db, principal: CurrentUser) -> Ack:
    record = get_request(request_id, db, principal)
    return Ack(
        message=(
            f"Request {record.reference} was acknowledged at "
            f"{record.acknowledged_at:%d %B %Y, %H:%M} UTC."
        )
    )
