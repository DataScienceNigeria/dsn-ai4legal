"""Notification and connector dispatch through the outbox.

Connector failure degrades gracefully, queues work, alerts the owner and never
silently drops a legal event (PRD section 11.2). Every outbound call is
recorded against a registered connector, and an unregistered connector is
refused rather than delivered.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.models.platform import Connector, EgressLog, OutboxEvent
from app.domain.enums import CLASS_RANK, DataClass


class ConnectorRefused(PermissionError):
    """The connector is unregistered, inactive, or not cleared for the class."""


def enqueue(
    session: Session,
    topic: str,
    payload: dict[str, Any],
    available_at: datetime | None = None,
) -> OutboxEvent:
    event = OutboxEvent(
        topic=topic,
        payload=payload,
        available_at=available_at or datetime.now(UTC),
    )
    session.add(event)
    return event


def assert_connector_permitted(
    session: Session, connector_code: str, data_class: DataClass
) -> Connector:
    connector = session.execute(
        select(Connector).where(Connector.code == connector_code)
    ).scalar_one_or_none()

    if connector is None:
        raise ConnectorRefused(
            f"{connector_code} is not a registered connector. An unregistered route out "
            "of the platform is a security incident, not a convenience."
        )
    if not connector.active:
        raise ConnectorRefused(f"The {connector.name} connector is switched off.")

    permitted = connector.permitted_data_classes or []
    highest = max((CLASS_RANK[DataClass(c)] for c in permitted), default=-1)
    if CLASS_RANK[data_class] > highest:
        raise ConnectorRefused(
            f"The {connector.name} connector is not cleared to carry {data_class.value} "
            "content."
        )
    return connector


def log_egress(
    session: Session,
    connector_code: str,
    purpose: str,
    data_class: DataClass,
    record_reference: str | None = None,
    result: str = "success",
    detail: str | None = None,
) -> None:
    session.add(
        EgressLog(
            occurred_at=datetime.now(UTC),
            connector_code=connector_code,
            purpose=purpose,
            record_reference=record_reference,
            data_class=data_class.value,
            result=result,
            detail=detail,
        )
    )


def notify(
    session: Session,
    *,
    connector_code: str,
    recipients: list[str],
    subject: str,
    body: str,
    data_class: DataClass = DataClass.INTERNAL,
    record_reference: str | None = None,
    matter_id: uuid.UUID | None = None,
) -> OutboxEvent:
    """Queue an administrative message.

    Substantive external communication is never sent by the platform on its own.
    Everything routed here is administrative and templated.
    """
    connector = assert_connector_permitted(session, connector_code, data_class)
    log_egress(
        session, connector.code, subject, data_class, record_reference, "queued"
    )
    return enqueue(
        session,
        topic="notification",
        payload={
            "connector": connector.code,
            "recipients": recipients,
            "subject": subject,
            "body": body,
            "matter_id": str(matter_id) if matter_id else None,
            "record_reference": record_reference,
        },
    )
