"""Inbound connector endpoints, M09.

n8n polls the approved mailboxes and posts what it finds here. It carries no
legal logic and writes nothing directly: this endpoint is the only way a
message enters the platform, so the mailbox allow list, the classification
gate and the audit trail all apply to it (PRD section 11.3).
"""

from __future__ import annotations

import base64
import binascii
import json
from datetime import UTC, datetime
from typing import Annotated

from fastapi import APIRouter, Header, Request
from pydantic import BaseModel, Field
from sqlalchemy import select

from app.ai import guards
from app.core import audit
from app.core.deps import AnonDb
from app.core.errors import Forbidden, ValidationFailed
from app.core.security import verify_webhook
from app.db.models.governance import Communication, Mailbox
from app.db.models.intake import Attachment
from app.schemas.common import Ack
from app.services import storage
from app.services.hashing import file_hash

router = APIRouter(prefix="/webhooks", tags=["webhooks"])


class InboundAttachment(BaseModel):
    """A file that arrived on a message, carried as base64.

    n8n reads the attachment from Graph and hands over the bytes rather than a
    URL, because a URL would make the platform hold a mailbox credential to
    fetch it and the whole point of the connector is that it does not.
    """

    filename: str
    content_type: str = "application/octet-stream"
    content_base64: str


class InboundMessage(BaseModel):
    external_id: str
    mailbox: str
    sender: str
    subject: str
    body: str
    received_at: datetime
    participants: list[dict] = Field(default_factory=list)
    attachments: list[InboundAttachment] = Field(default_factory=list)


class InboundBatch(BaseModel):
    messages: list[InboundMessage]


def _store_attachments(db, communication, message, entity: str) -> int:
    """Store what came with the message, scanning each file first.

    A file that fails the scan or the type check is refused on its own and
    recorded; the message still lands. Dropping the whole message because one
    attachment was a .exe would lose the correspondence that says why it was
    sent, which is the part Legal reads.
    """
    stored = 0
    for item in message.attachments:
        try:
            data = base64.b64decode(item.content_base64, validate=True)
        except (binascii.Error, ValueError):
            audit.record(
                db,
                action="attachment_refused",
                object_type="communication",
                object_id=str(communication.id),
                actor_label="n8n mail connector",
                entity=entity,
                result="failure",
                detail=f"{item.filename} was not valid base64.",
            )
            continue

        try:
            digest = storage.validate_upload(item.filename, item.content_type, data)
        except ValidationFailed as refusal:
            audit.record(
                db,
                action="attachment_refused",
                object_type="communication",
                object_id=str(communication.id),
                actor_label="n8n mail connector",
                entity=entity,
                result="failure",
                detail=f"{item.filename}: {refusal.detail}",
            )
            continue

        clean, scan_detail = storage.scan_upload(data)
        if not clean:
            # Quarantined rather than stored, and recorded either way. An
            # infected attachment that leaves no trace is the one attachment
            # anybody would want a record of.
            audit.record(
                db,
                action="upload_quarantined",
                object_type="communication",
                object_id=str(communication.id),
                actor_label="n8n mail connector",
                entity=entity,
                result="failure",
                detail=f"{item.filename}: {scan_detail}",
            )
            continue

        key = f"mail/{communication.id}/{digest[:12]}-{item.filename}"
        storage.store.put(key, data, item.content_type)
        db.add(
            Attachment(
                communication_id=communication.id,
                filename=item.filename,
                content_type=item.content_type,
                size_bytes=len(data),
                storage_key=key,
                content_hash=file_hash(data),
                scan_status="clean",
            )
        )
        stored += 1

    if stored:
        audit.record(
            db,
            action="mail_attachments_stored",
            object_type="communication",
            object_id=str(communication.id),
            actor_label="n8n mail connector",
            entity=entity,
            after_state={
                "files": stored,
                "of": len(message.attachments),
                "message_id": message.external_id,
            },
        )
    return stored


@router.post("/mail")
async def receive_mail(
    http_request: Request,
    db: AnonDb,
    x_signature: Annotated[str, Header()] = "",
) -> Ack:
    """Accept messages from an approved mailbox only.

    Personal mailboxes and broad archives are never ingested. A mailbox that is
    not on the configured list is refused and the attempt is recorded, because
    an unregistered ingest route is a security incident rather than a
    convenience.
    """
    raw = await http_request.body()
    if not verify_webhook(raw, x_signature):
        raise Forbidden("The webhook signature did not verify.")

    batch = InboundBatch.model_validate(json.loads(raw))

    known = {
        record.address: record
        for record in db.execute(select(Mailbox).where(Mailbox.active.is_(True))).scalars()
    }

    accepted = 0
    refused: list[str] = []
    quarantined = 0
    stored_files = 0

    for message in batch.messages:
        mailbox = known.get(message.mailbox.lower())
        if mailbox is None:
            refused.append(message.mailbox)
            audit.record(
                db,
                action="mailbox_ingest_refused",
                object_type="mailbox",
                object_id=message.mailbox,
                actor_label="n8n mail connector",
                result="failure",
                detail="The mailbox is not on the approved list.",
            )
            continue

        existing = db.execute(
            select(Communication).where(Communication.external_id == message.external_id)
        ).scalar_one_or_none()
        if existing is not None:
            continue

        # Ingested content is untrusted. It is scanned on the way in so that a
        # quarantined message never reaches a capability at all.
        scan = guards.scan(f"{message.subject}\n\n{message.body}")

        communication = Communication(
            mailbox_id=mailbox.id,
            entity=mailbox.entity,
            external_id=message.external_id,
            direction="inbound",
            sender=message.sender,
            subject=message.subject,
            body=message.body,
            received_at=message.received_at,
            participants=message.participants,
            injection_flagged=scan.detected,
            quarantined=scan.quarantine,
        )
        db.add(communication)
        db.flush()
        stored_files += _store_attachments(db, communication, message, mailbox.entity)
        accepted += 1
        if scan.quarantine:
            quarantined += 1
            audit.record(
                db,
                action="prompt_injection_detected",
                object_type="communication",
                object_id=str(communication.id),
                actor_label="n8n mail connector",
                entity=mailbox.entity,
                result="failure",
                detail=", ".join(scan.patterns),
            )

    mailbox_record = next(iter(known.values()), None)
    if mailbox_record is not None:
        mailbox_record.last_polled_at = datetime.now(UTC)

    if refused and not accepted:
        raise ValidationFailed(
            "No message was accepted.",
            {"mailbox": f"These mailboxes are not approved: {', '.join(sorted(set(refused)))}"},
        )

    return Ack(
        message=(
            f"{accepted} messages accepted, {stored_files} attachments stored, "
            f"{len(refused)} refused as unapproved mailboxes, {quarantined} quarantined "
            "for review. Nothing is classified or actioned until Legal opens it."
        )
    )
