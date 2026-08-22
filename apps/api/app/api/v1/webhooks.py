"""Inbound connector endpoints, M09.

n8n polls the approved mailboxes and posts what it finds here. It carries no
legal logic and writes nothing directly: this endpoint is the only way a
message enters the platform, so the mailbox allow list, the classification
gate and the audit trail all apply to it (PRD section 11.3).
"""

from __future__ import annotations

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
from app.schemas.common import Ack

router = APIRouter(prefix="/webhooks", tags=["webhooks"])


class InboundMessage(BaseModel):
    external_id: str
    mailbox: str
    sender: str
    subject: str
    body: str
    received_at: datetime
    participants: list[dict] = Field(default_factory=list)


class InboundBatch(BaseModel):
    messages: list[InboundMessage]


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

        db.add(
            Communication(
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
        )
        accepted += 1
        if scan.quarantine:
            quarantined += 1
            audit.record(
                db,
                action="prompt_injection_detected",
                object_type="communication",
                object_id=message.external_id,
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
            f"{accepted} messages accepted, {len(refused)} refused as unapproved mailboxes, "
            f"{quarantined} quarantined for review. Nothing is classified or actioned until "
            "Legal opens it."
        )
    )
