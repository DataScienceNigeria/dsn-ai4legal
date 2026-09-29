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
import mimetypes
from datetime import UTC, datetime
from typing import Annotated

from fastapi import APIRouter, Header, Request
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError

from app.ai import guards
from app.core import audit
from app.core.deps import AnonDb
from app.core.errors import Forbidden, ValidationFailed
from app.core.security import verify_webhook
from app.db.models.governance import Communication, Mailbox
from app.db.models.intake import Attachment
from app.schemas.common import Ack
from app.services import storage
from app.services.mail_text import readable
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
    """One message, and what its mailbox says about it.

    ``read`` and ``labels`` are the mailbox's state, recorded as it is rather
    than changed: the connector reads every message, and Legal still works
    from the mailbox itself. ``None`` for ``read`` means the connector did not
    say, which is not the same as unread.
    """

    external_id: str
    mailbox: str
    sender: str
    subject: str
    body: str = ""
    body_html: str | None = None
    received_at: datetime
    direction: str = Field(default="inbound", pattern="^(inbound|outbound)$")
    thread_id: str | None = None
    read: bool | None = None
    labels: list[str] = Field(default_factory=list)
    participants: list[dict] = Field(default_factory=list)
    attachments: list[InboundAttachment] = Field(default_factory=list)


class InboundBatch(BaseModel):
    messages: list[InboundMessage]


def _content_type(item: InboundAttachment) -> str:
    """The declared type, or the one the filename implies where none was given.

    Mail clients label spreadsheets and presentations as octet-stream as often
    as not, and taking that at face value refuses the agreement's schedule
    while accepting the covering note.
    """
    declared = (item.content_type or "").split(";")[0].strip().lower()
    if declared and declared != "application/octet-stream":
        return declared
    guessed, _ = mimetypes.guess_type(item.filename)
    return guessed or "application/octet-stream"


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

        content_type = _content_type(item)
        try:
            digest = storage.validate_upload(item.filename, content_type, data)
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
        storage.store.put(key, data, content_type)
        db.add(
            Attachment(
                communication_id=communication.id,
                filename=item.filename,
                content_type=content_type,
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
    updated = 0
    refused: list[str] = []
    quarantined = 0
    stored_files = 0
    polled: set[str] = set()
    seen: set[str] = set()
    now = datetime.now(UTC)

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
        polled.add(mailbox.address)

        if message.external_id in seen:
            continue
        seen.add(message.external_id)

        existing = db.execute(
            select(Communication).where(Communication.external_id == message.external_id)
        ).scalar_one_or_none()
        if existing is not None:
            # Seen before. The connector reads the whole mailbox and re-reads
            # recent mail on every pass, so this is the common case: the
            # message is not created again, only its mailbox state brought up
            # to date, plus anything an earlier pass could not supply.
            existing.mailbox_read = message.read
            existing.mailbox_labels = message.labels
            existing.thread_id = message.thread_id or existing.thread_id
            existing.mailbox_seen_at = now
            if existing.body_original is None:
                fresh, quoted, original = readable(message.body, message.body_html)
                existing.body, existing.body_quoted, existing.body_original = fresh, quoted, original
            if message.attachments and not existing.attachments:
                stored_files += _store_attachments(db, existing, message, existing.entity)
            updated += 1
            continue

        fresh, quoted, original = readable(message.body, message.body_html)

        # Ingested content is untrusted. It is scanned on the way in so that a
        # quarantined message never reaches a capability at all. The whole
        # text is scanned, quoted history included: an instruction hidden in
        # the history is still in the message.
        scan = guards.scan(f"{message.subject}\n\n{fresh}\n\n{quoted or ''}")

        communication = Communication(
            mailbox_id=mailbox.id,
            entity=mailbox.entity,
            external_id=message.external_id,
            direction=message.direction,
            sender=message.sender,
            subject=message.subject[:512],
            body=fresh,
            body_quoted=quoted,
            body_original=original,
            received_at=message.received_at,
            thread_id=message.thread_id,
            mailbox_read=message.read,
            mailbox_labels=message.labels,
            mailbox_seen_at=now,
            participants=message.participants,
            injection_flagged=scan.detected,
            quarantined=scan.quarantine,
        )
        # Two passes can overlap. The unique external_id stops the second
        # from creating a duplicate, and the savepoint keeps that refusal to
        # this one message rather than failing the batch.
        try:
            with db.begin_nested():
                db.add(communication)
                db.flush()
        except IntegrityError:
            continue

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

    for address in polled:
        known[address].last_polled_at = now

    if refused and not accepted and not updated:
        raise ValidationFailed(
            "No message was accepted.",
            {"mailbox": f"These mailboxes are not approved: {', '.join(sorted(set(refused)))}"},
        )

    return Ack(
        message=(
            f"{accepted} messages accepted, {updated} already held and brought up to date, "
            f"{stored_files} attachments stored, "
            f"{len(refused)} refused as unapproved mailboxes, {quarantined} quarantined "
            "for review. Nothing is classified or actioned until Legal opens it."
        )
    )
