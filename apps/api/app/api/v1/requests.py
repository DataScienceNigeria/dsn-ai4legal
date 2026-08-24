"""Requests and intake, M01."""

from __future__ import annotations

import uuid
from datetime import UTC, datetime
from typing import Annotated

from fastapi import APIRouter, File, Request, Response, UploadFile
from sqlalchemy import select

from app.core import audit
from app.core.deps import CurrentUser, Db, client_ip
from app.core.errors import NotFound, ValidationFailed
from app.db.models.contract import Approval
from app.db.models.document import Document
from app.db.models.intake import Attachment, RequestType
from app.db.models.intake import Request as RequestRecord
from app.db.models.matter import Matter
from app.db.models.organisation import User
from app.domain.enums import ApprovalDecision, MatterState, Role
from app.schemas.common import Ack
from app.schemas.intake import (
    AttachmentOut,
    AwaitingConfirmation,
    DraftBlock,
    DraftForConfirmation,
    RequestCreate,
    RequestOut,
    RequestStatusOut,
    RequestTypeOut,
    TimelineEntry,
)
from app.services import notifications, sequences, storage
from app.services.hashing import file_hash

DOCX_MEDIA_TYPE = (
    "application/vnd.openxmlformats-officedocument.wordprocessingml.document"
)

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
        # On its own connection: the refusal below rolls this transaction
        # back, and a quarantined upload that leaves no trace is the one
        # upload anybody would want a record of.
        audit.record_refusal(
            action="upload_quarantined",
            object_type="request",
            object_id=record.reference,
            actor_id=principal.user_id,
            actor_label=principal.name,
            entity=record.entity,
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


@router.get("/{request_id}/attachments/{attachment_id}")
def get_attachment(
    request_id: uuid.UUID, attachment_id: uuid.UUID, db: Db, principal: CurrentUser
) -> Response:
    """The stored file itself, for reading rather than saving.

    The request is loaded first so the caller's visibility of it is what
    decides access. An attachment carries no entity of its own, and reading it
    by its own identifier alone would step around the separation the request
    is subject to.
    """
    record = db.get(RequestRecord, request_id)
    if record is None:
        raise NotFound(REQUEST_NOT_FOUND)

    attachment = db.get(Attachment, attachment_id)
    if attachment is None or attachment.request_id != record.id:
        raise NotFound("That attachment is not on this request.")

    try:
        data = storage.store.get(attachment.storage_key)
    except FileNotFoundError as exc:
        raise NotFound(
            "The record is here but the file is not in the object store. "
            "Report this: an attachment should never outlive its bytes."
        ) from exc

    audit.record(
        db,
        action="attachment_read",
        object_type="request",
        object_id=record.reference,
        actor_id=principal.user_id,
        actor_label=principal.name,
        entity=record.entity,
        after_state={"filename": attachment.filename},
    )
    return Response(
        content=data,
        media_type=attachment.content_type,
        headers={
            # inline, because the point is to read it without leaving the
            # matter. A type the browser cannot render still downloads.
            "Content-Disposition": f'inline; filename="{attachment.filename}"',
            "X-Content-Hash": attachment.content_hash,
        },
    )


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


def _draft_waiting_on(db, principal, record: RequestRecord) -> AwaitingConfirmation:
    """The draft this caller is being asked to confirm, or nothing.

    Two conditions, and both are needed. There has to be a step open on the
    requester, and the caller has to be that requester. `get_request` lets
    Legal read any request, which is right for a status screen and wrong here:
    this endpoint says a draft is waiting on you, and it should be reachable
    only by the person it is waiting on. Legal reads the same document from the
    matter, where it belongs to them.
    """
    matter = db.execute(
        select(Matter).where(Matter.request_id == record.id)
    ).scalar_one_or_none()

    waiting = _pending_confirmation(db, record, matter)
    if waiting is None or str(record.requester_id) != principal.user_id:
        raise NotFound("There is no draft waiting on you for this request.")
    return waiting


def _pending_confirmation(db, record: RequestRecord, matter) -> AwaitingConfirmation | None:
    """The approval step waiting on this requester, if there is one.

    Scoped by the approver on the row rather than by role, so a requester sees
    the step that is theirs and nothing else about the chain. What the Head of
    Legal is deciding is not their business, and the fact that a step exists
    above theirs is not something the portal needs to say.
    """
    if matter is None:
        return None

    approval = db.execute(
        select(Approval)
        .where(
            Approval.matter_id == matter.id,
            Approval.approver_id == record.requester_id,
            Approval.decision == ApprovalDecision.PENDING.value,
            Approval.invalidated_by_event.is_(None),
        )
        .order_by(Approval.step_index)
    ).scalars().first()
    if approval is None or approval.document_id is None:
        return None

    document = db.get(Document, approval.document_id)
    if document is None:
        return None

    return AwaitingConfirmation(
        approval_id=approval.id,
        document_id=document.id,
        document_name=document.name,
        step_name=approval.step_name,
        due_at=approval.due_at,
        changes_requested=approval.comments,
    )


@router.get("/{request_id}/draft")
def draft_for_confirmation(
    request_id: uuid.UUID, db: Db, principal: CurrentUser
) -> DraftForConfirmation:
    """The draft, for the person who asked for the work.

    Reachable only while a step on it is assigned to them and undecided. Once
    they have confirmed, the draft is Legal's again: a requester holding an
    open window onto every document on their matter is a wider grant than the
    one act they were asked to perform.
    """
    record = get_request(request_id, db, principal)
    waiting = _draft_waiting_on(db, principal, record)

    document = db.get(Document, waiting.document_id)
    audit.record(
        db,
        action="draft_read_by_requester",
        object_type="document",
        object_id=str(document.id),
        actor_id=principal.user_id,
        actor_label=principal.name,
        entity=record.entity,
        after_state={"request": record.reference, "hash": document.content_hash},
    )

    return DraftForConfirmation(
        reference=record.reference,
        subject=record.subject,
        document_name=document.name,
        generated_at=document.generated_at,
        blocks=[
            DraftBlock(
                number=str(block.get("number", "")),
                heading=block.get("heading", ""),
                text=block.get("text", ""),
            )
            for block in document.blocks or []
        ],
        approval_id=waiting.approval_id,
        step_name=waiting.step_name,
        changes_requested=waiting.changes_requested,
    )


@router.get("/{request_id}/draft/file")
def draft_file(request_id: uuid.UUID, db: Db, principal: CurrentUser) -> Response:
    """The draft as the file, so the requester reads it as the document it is.

    Rendered from the stored blocks rather than served from storage, which is
    the same path the workspace download takes: the blocks are what the hash
    was computed over, so what they read is what everyone else is deciding
    about. Reachable only while a step on it is theirs and undecided, and
    served inline rather than as an attachment, because they are reading it in
    the platform and not taking a copy of a confidential agreement away.
    """
    record = get_request(request_id, db, principal)
    waiting = _draft_waiting_on(db, principal, record)

    document = db.get(Document, waiting.document_id)

    from app.services.generation import GeneratedBlock, GenerationResult, render_docx

    data = render_docx(
        GenerationResult(
            blocks=[
                GeneratedBlock(
                    key=block.get("key", ""),
                    number=str(block.get("number", "")),
                    heading=block.get("heading", ""),
                    text=block.get("text", ""),
                    provenance=block.get("provenance", "template_text"),
                    source_reference=block.get("source_reference"),
                )
                for block in document.blocks or []
            ],
            values=document.input_values,
            checks=[],
            content_hash=document.content_hash,
            template_reference=document.template_version_ref or "",
            clause_references=document.clause_versions,
        ),
        document.name,
    )

    audit.record(
        db,
        action="draft_read_by_requester",
        object_type="document",
        object_id=str(document.id),
        actor_id=principal.user_id,
        actor_label=principal.name,
        entity=record.entity,
        after_state={"request": record.reference, "hash": document.content_hash, "as": "docx"},
    )

    return Response(
        content=data,
        media_type=DOCX_MEDIA_TYPE,
        headers={
            "Content-Disposition": f'inline; filename="{document.name}.docx"',
            "X-Content-Hash": document.content_hash,
        },
    )


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
        id=record.id,
        reference=record.reference,
        subject=record.subject,
        status=current_status,
        stage_label=STAGE_LABELS.get(current_status, current_status.replace("_", " ")),
        owner_first_name=owner_first_name,
        expected_date=matter.due_date if matter else record.required_date,
        last_update=matter.updated_at if matter else record.updated_at,
        matter_number=matter.number if matter else None,
        awaiting_confirmation=_pending_confirmation(db, record, matter),
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
