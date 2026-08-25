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

from app.db.models.platform import Connector, EgressLog, Notification, OutboxEvent
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


def raise_for_role(
    session: Session,
    *,
    role: str,
    entity: str,
    kind: str,
    title: str,
    body: str | None = None,
    href: str | None = None,
    reference: str | None = None,
) -> int:
    """Put a message in the bell of everyone who holds a role in this entity.

    For work that belongs to a job rather than to a person. A DPIA arriving for
    assessment is the data protection officer's, whoever that is this month,
    and addressing it to a name that was right when the code was written is how
    a submission sits unread while somebody is on leave.
    """
    from app.db.models.organisation import User, UserEntity

    recipients = session.execute(
        select(User)
        .join(UserEntity, UserEntity.user_id == User.id)
        .where(
            User.roles.any(role),
            UserEntity.entity_code == entity,
            User.active.is_(True),
        )
        .distinct()
    ).scalars()

    raised = 0
    for person in recipients:
        if raise_in_app(
            session,
            recipient_id=person.id,
            entity=entity,
            kind=kind,
            title=title,
            body=body,
            href=href,
            reference=reference,
        ):
            raised += 1
    return raised


def raise_in_app(
    session: Session,
    *,
    recipient_id: uuid.UUID | None,
    entity: str,
    kind: str,
    title: str,
    body: str | None = None,
    href: str | None = None,
    reference: str | None = None,
    matter_id: uuid.UUID | None = None,
) -> Notification | None:
    """Put a message in one person's bell.

    Deliberately not routed through the outbox. The outbox carries mail to an
    external connector and can be refused, deferred or switched off; this stays
    inside the platform and is what the person sees when they next open it.
    Both are raised together where an event matters enough to leave the
    building, so the in-app record survives a connector that is unavailable.

    An event with no identified recipient writes nothing. A notification with
    nobody to read it is a row that accumulates and is never cleared.
    """
    if recipient_id is None:
        return None

    # The timestamps are set here rather than left to the column defaults, and
    # that is load-bearing rather than tidiness. A server default makes
    # SQLAlchemy add RETURNING to fetch it back, and Postgres applies the read
    # policy to a row an INSERT returns. The read policy on this table is
    # narrowed to the recipient, which is the point of it, so writing a
    # notification addressed to somebody else was refused at the read rather
    # than at the write. Supplying every value means there is nothing to
    # return, and the strict read policy stays exactly as strict.
    stamp = datetime.now(UTC)
    record = Notification(
        id=uuid.uuid4(),
        created_at=stamp,
        updated_at=stamp,
        recipient_id=recipient_id,
        entity=entity,
        kind=kind,
        title=title,
        body=body,
        href=href,
        reference=reference,
        matter_id=matter_id,
    )
    session.add(record)
    return record
