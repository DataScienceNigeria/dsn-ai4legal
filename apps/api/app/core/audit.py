"""Immutable audit trail, LOP-M15-US-03 and LOP-NFR-19.

Events are append-only. The database revokes update and delete on the table for
every application role, and each row carries a digest chained over the previous
row so that removal or alteration is detectable.
"""

import hashlib
import json
import logging
import uuid
from datetime import UTC, datetime
from typing import Any

from sqlalchemy import select, text
from sqlalchemy.orm import Session

from app.db.models.platform import AuditEvent

# One fixed key, because there is one chain. Any constant would do; this one is
# written out rather than hashed so it is greppable when a lock shows up in
# pg_locks during an investigation.
CHAIN_LOCK = 8_150_112_026

logger = logging.getLogger(__name__)


def _canonical(value: Any) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), default=str)


def _jsonable(state: dict | None) -> dict | None:
    """Make a state dictionary something JSONB will accept.

    Callers hand this whatever the record holds, which includes dates, UUIDs
    and decimals. psycopg raises on those, and it raises at commit rather than
    at the call, by which point the response has been built and returned. That
    is the worst possible failure for this table in particular: the change was
    committed, the audit row was not, and the caller was told it worked. A
    round trip through the canonical encoder gives every value the same string
    form the digest is computed over.
    """
    if state is None:
        return None
    return json.loads(_canonical(state))


def compute_digest(
    *,
    sequence: int,
    occurred_at: datetime,
    actor_label: str,
    object_type: str,
    object_id: str | None,
    action: str,
    result: str,
    previous_digest: str | None,
) -> str:
    """The digest binds the event's position as well as its content.

    Without the position, two events written in the same microsecond hash the
    same way whichever order they were appended in, and the chain cannot tell a
    reordering from the truth.
    """
    material = _canonical(
        {
            "seq": sequence,
            "at": occurred_at.isoformat(),
            "actor": actor_label,
            "object_type": object_type,
            "object_id": object_id,
            "action": action,
            "result": result,
            "previous": previous_digest,
        }
    )
    return hashlib.sha256(material.encode()).hexdigest()


def legacy_digest(
    *,
    occurred_at: datetime,
    actor_label: str,
    object_type: str,
    object_id: str | None,
    action: str,
    result: str,
    previous_digest: str | None,
) -> str:
    """The digest as it was computed before the chain gained a sequence.

    Kept so verification can tell a row written under the old formula from a
    row that has actually been tampered with. Deleting it would make every
    historical event look broken, which would bury the four that really are.
    """
    material = _canonical(
        {
            "at": occurred_at.isoformat(),
            "actor": actor_label,
            "object_type": object_type,
            "object_id": object_id,
            "action": action,
            "result": result,
            "previous": previous_digest,
        }
    )
    return hashlib.sha256(material.encode()).hexdigest()


def record_refusal(
    *,
    action: str,
    object_type: str,
    object_id: str | None = None,
    actor_id: uuid.UUID | str | None = None,
    actor_label: str = "system",
    entity: str | None = None,
    ip_address: str | None = None,
    session_id: str | None = None,
    detail: str | None = None,
) -> None:
    """Append an event that survives the refusal that follows it.

    A refusal raises, the request's transaction rolls back, and everything
    written in it goes with the change it was rolling back, including the audit
    row. So a rejected password, a quarantined upload and every other refused
    act recorded nothing at all, which is precisely backwards: the refused
    attempts are the ones a trail exists to hold.

    This writes on its own connection and commits by itself. It takes the same
    chain lock, so it serialises against every other writer, and it must
    therefore be called before any in-transaction ``record`` in the same
    request: two connections in one request waiting on one lock is a deadlock
    with only itself to blame.

    Failing to write the trail never turns into a second failure on top of the
    first. The caller is refusing already, and a refusal that becomes a 500
    because the logging failed tells the person even less than it did before.
    """
    from app.db.session import owner_session

    try:
        with owner_session() as session:
            record(
                session,
                action=action,
                object_type=object_type,
                object_id=object_id,
                actor_id=actor_id,
                actor_label=actor_label,
                entity=entity,
                ip_address=ip_address,
                session_id=session_id,
                result="failure",
                detail=detail,
            )
    except Exception:
        logger.exception("The audit trail could not record a refusal of %s", action)


def record(
    session: Session,
    *,
    action: str,
    object_type: str,
    object_id: str | None = None,
    actor_id: uuid.UUID | str | None = None,
    actor_label: str = "system",
    entity: str | None = None,
    before_state: dict | None = None,
    after_state: dict | None = None,
    ip_address: str | None = None,
    session_id: str | None = None,
    result: str = "success",
    detail: str | None = None,
) -> AuditEvent:
    """Append one event. The caller commits with the surrounding transaction.

    The lock is what makes this a chain rather than a set of forks. Reading the
    previous digest and writing the next one has to be atomic across every
    writer, and it has to see the events this transaction has already appended.
    Without it, two events in one request and two concurrent requests both
    linked to the same predecessor, and the chain stopped reconciling.
    """
    session.execute(text("SELECT pg_advisory_xact_lock(:key)"), {"key": CHAIN_LOCK})
    session.flush()

    occurred_at = datetime.now(UTC)
    previous = session.execute(
        select(AuditEvent.digest).order_by(AuditEvent.sequence.desc()).limit(1)
    ).scalar_one_or_none()
    sequence = session.execute(
        text("SELECT nextval('audit_event_sequence')")
    ).scalar_one()

    event = AuditEvent(
        sequence=sequence,
        occurred_at=occurred_at,
        actor_id=uuid.UUID(str(actor_id)) if actor_id else None,
        actor_label=actor_label,
        entity=entity,
        object_type=object_type,
        object_id=str(object_id) if object_id is not None else None,
        action=action,
        before_state=_jsonable(before_state),
        after_state=_jsonable(after_state),
        ip_address=ip_address,
        session_id=session_id,
        result=result,
        detail=detail,
        previous_digest=previous,
        digest=compute_digest(
            sequence=sequence,
            occurred_at=occurred_at,
            actor_label=actor_label,
            object_type=object_type,
            object_id=str(object_id) if object_id is not None else None,
            action=action,
            result=result,
            previous_digest=previous,
        ),
    )
    session.add(event)
    return event


def verify_chain(session: Session, limit: int = 1000) -> list[str]:
    """Recompute the chain and report any row that does not reconcile.

    Ordered by sequence, because that is the order the digests were computed
    in. Ordering by the clock ties, and a tie reports a fault that is really
    the verifier guessing.
    """
    rows = session.execute(
        select(AuditEvent).order_by(AuditEvent.sequence.asc()).limit(limit)
    ).scalars().all()
    problems: list[str] = []
    previous: str | None = None

    for row in rows:
        shared = {
            "occurred_at": row.occurred_at,
            "actor_label": row.actor_label,
            "object_type": row.object_type,
            "object_id": row.object_id,
            "action": row.action,
            "result": row.result,
            "previous_digest": previous,
        }
        # A row is sound if it reconciles under the formula in force when it
        # was written. Accepting only the current one would report every event
        # from before the fix as tampered with, which is false and would bury
        # the ones that genuinely forked.
        expected = compute_digest(sequence=row.sequence, **shared)
        if row.digest not in {expected, legacy_digest(**shared)}:
            problems.append(f"{row.id} does not reconcile with the chain.")
        previous = row.digest
    return problems
