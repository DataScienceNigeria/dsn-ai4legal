"""Background jobs.

Reliability without a message broker to operate: work is queued in a durable
outbox table inside the same transaction as the record it belongs to, and this
worker drains it. A connector failure retries with backoff and never silently
drops a legal event (PRD section 11.2).
"""

from __future__ import annotations

import logging
from datetime import UTC, datetime, timedelta

from celery import Celery
from celery.schedules import crontab
from sqlalchemy import select

from app.core.config import settings
from app.db.models.contract import Approval, Obligation
from app.db.models.organisation import User
from app.db.models.platform import OutboxEvent
from app.db.session import owner_session
from app.domain.enums import ApprovalDecision, ObligationStatus
from app.services import obligations as obligation_rules
from app.services.obligations import LEGAL_DEADLINES

logger = logging.getLogger(__name__)

celery_app = Celery("dsn_lai", broker=settings.redis_url, backend=settings.redis_url)
celery_app.conf.update(
    task_acks_late=True,
    worker_prefetch_multiplier=1,
    timezone="UTC",
    beat_schedule={
        "drain-outbox": {"task": "dsn_lai.drain_outbox", "schedule": 30.0},
        # Every ten minutes, because nothing is coming the other way. See
        # signature_sweep for why this is a poll rather than a callback.
        "signature-sweep": {"task": "dsn_lai.signature_sweep", "schedule": 600.0},
        "obligation-reminders": {
            "task": "dsn_lai.obligation_reminders",
            "schedule": crontab(hour="7", minute="0"),
        },
        "escalate-approvals": {
            "task": "dsn_lai.escalate_approvals",
            "schedule": crontab(minute="*/30"),
        },
        "inbox-watch": {
            "task": "dsn_lai.inbox_watch",
            "schedule": crontab(hour="*/4", minute="15"),
        },
        "renewal-watch": {
            "task": "dsn_lai.renewal_watch",
            "schedule": crontab(hour="6", minute="30"),
        },
        # A score nobody has taken this month is not evidence a capability is
        # still safe, so the schedule takes one whether or not anyone asks.
        "evaluation-sweep": {
            "task": "dsn_lai.evaluation_sweep",
            "schedule": crontab(day_of_week="1", hour="3", minute="0"),
        },
    },
)

MAX_ATTEMPTS = 8


@celery_app.task(name="dsn_lai.drain_outbox")
def drain_outbox(batch: int = 50) -> int:
    """Deliver queued events, with exponential backoff and a dead letter."""
    delivered = 0
    with owner_session() as session:
        now = datetime.now(UTC)
        events = (
            session.execute(
                select(OutboxEvent)
                .where(OutboxEvent.status == "pending", OutboxEvent.available_at <= now)
                .order_by(OutboxEvent.available_at)
                .limit(batch)
                .with_for_update(skip_locked=True)
            )
            .scalars()
            .all()
        )

        for event in events:
            try:
                deliver(event)
                event.status = "delivered"
                event.delivered_at = datetime.now(UTC)
                delivered += 1
            except Exception as exc:
                event.attempts += 1
                event.last_error = str(exc)[:500]
                if event.attempts >= MAX_ATTEMPTS:
                    event.status = "dead_letter"
                    logger.exception("Outbox event %s dead lettered", event.id)
                else:
                    event.available_at = datetime.now(UTC) + timedelta(
                        seconds=min(3600, 2**event.attempts)
                    )
    return delivered


def deliver(event: OutboxEvent) -> None:
    """Hand an event to its transport.

    A transport that fails raises, so the outbox retries with backoff and
    eventually dead-letters. Nothing here marks a message sent that did not
    leave, which is the property the whole queue exists to hold.
    """
    from app.services.transports import Message, send

    payload = event.payload or {}
    send(
        Message(
            connector=str(payload.get("connector") or "unknown"),
            recipients=list(payload.get("recipients") or []),
            subject=str(payload.get("subject") or event.topic),
            body=str(payload.get("body") or ""),
            record_reference=payload.get("record_reference"),
            matter_id=payload.get("matter_id"),
        )
    )


@celery_app.task(name="dsn_lai.signature_sweep")
def signature_sweep() -> dict:
    """Ask the signing service what happened to every request still out.

    A poll, and not by preference. The self-hosted signing service carries no
    outbound webhook: the feature belongs to the hosted product and there is no
    dispatcher anywhere in the container, so nothing will ever call this
    platform to say a document was signed. Waiting for a callback that cannot
    arrive would leave every executed agreement unrecorded and every obligation
    underneath it unproposed.

    It is also the safer half of the trade. A missed callback is silent and
    permanent; a missed poll is retried in ten minutes.

    Completion runs the same archive path a callback would: the executed copy
    becomes immutable, a contract record is created and obligations are
    proposed. One function, one behaviour, whichever way the news arrives.
    """
    from app.api.v1.approvals import _archive
    from app.db.models.contract import SignatureRequest
    from app.services import signature as signature_service

    provider = signature_service.selected()
    looked_at = 0
    completed = 0
    declined = 0

    with owner_session() as session:
        outstanding = list(
            session.execute(
                select(SignatureRequest).where(SignatureRequest.status == "sent")
            ).scalars()
        )

        for request in outstanding:
            if not request.external_reference:
                continue
            looked_at += 1
            state = provider.state_of(request.external_reference)
            if state is None or state["status"] == "sent":
                continue

            if state["status"] == "completed":
                request.status = "completed"
                request.completed_at = datetime.now(UTC)
                request.audit_certificate = state["certificate"]
                _archive(session, request, state["certificate"])
                completed += 1
            elif state["status"] == "declined":
                # Declined is not cancelled. Somebody was asked and said no,
                # and the record should say which of those happened.
                request.status = "declined"
                request.cancelled_reason = "A signer declined at the signing service."
                declined += 1

    if completed or declined:
        logger.info(
            "Signature sweep: %s completed, %s declined, of %s outstanding.",
            completed,
            declined,
            looked_at,
        )
    return {"checked": looked_at, "completed": completed, "declined": declined}


@celery_app.task(name="dsn_lai.obligation_reminders")
def obligation_reminders() -> int:
    """Reminders reach the owner at their configured lead time, and escalate on
    breach (PRD LOP-M08-US-03).

    Only for the deadlines that are legal's own. What an agreement requires of
    the business is a record to read, not a queue to work.
    """
    from app.services.notifications import notify

    raised = 0
    with owner_session() as session:
        obligations = (
            session.execute(
                select(Obligation).where(
                    Obligation.status == ObligationStatus.OPEN.value,
                    Obligation.due_date.is_not(None),
                    Obligation.obligation_type.in_(LEGAL_DEADLINES),
                )
            )
            .scalars()
            .all()
        )

        for obligation in obligations:
            owner = session.get(User, obligation.owner_id) if obligation.owner_id else None
            if owner is None:
                continue

            window = obligation_rules.ReminderWindow(
                obligation.due_date, obligation.lead_time_days
            )
            if not window.is_due():
                continue

            notify(
                session,
                connector_code="notification_channel",
                recipients=[owner.work_email],
                subject=f"{obligation.name} is due in {window.days_until()} days",
                body=(
                    f"{obligation.reference}. Source clause "
                    f"{obligation.source_clause or 'not recorded'}."
                ),
                record_reference=obligation.reference,
            )
            raised += 1

            target = obligation_rules.escalation_due(
                obligation.due_date, obligation.escalation_rule or {}
            )
            if target:
                notify(
                    session,
                    connector_code="notification_channel",
                    recipients=[f"{target}@dsn.example"],
                    subject=f"Overdue obligation {obligation.reference}",
                    body=f"{obligation.name} passed its due date of {obligation.due_date}.",
                    record_reference=obligation.reference,
                )
    return raised


@celery_app.task(name="dsn_lai.escalate_approvals")
def escalate_approvals() -> int:
    """Overdue approvals escalate on their own (PRD LOP-M07-US-04)."""
    from app.services.approvals import due_for_escalation
    from app.services.notifications import notify

    escalated = 0
    with owner_session() as session:
        approvals = (
            session.execute(
                select(Approval).where(Approval.decision == ApprovalDecision.PENDING.value)
            )
            .scalars()
            .all()
        )

        for approval in approvals:
            if not due_for_escalation(approval):
                continue

            approver = session.get(User, approval.approver_id) if approval.approver_id else None
            delegate = (
                session.get(User, approver.delegate_id)
                if approver and approver.delegate_id
                else None
            )
            recipients = [
                user.work_email for user in (approver, delegate) if user is not None
            ] or ["headoflegal@dsn.example"]

            notify(
                session,
                connector_code="notification_channel",
                recipients=recipients,
                subject=f"Approval overdue: {approval.step_name}",
                body=(
                    f"This step passed its due time of {approval.due_at}. "
                    "It escalates to the escalation owner next."
                ),
                record_reference=str(approval.matter_id),
            )
            approval.reminders_sent += 1
            approval.escalated_at = datetime.now(UTC)
            escalated += 1
    return escalated


@celery_app.task(name="dsn_lai.inbox_watch")
def inbox_watch() -> int:
    """Deadlines and silence are both escalated, LOP-M09-US-06.

    Three things go wrong quietly in a shared inbox: an extracted deadline
    arrives, high-risk language sits unread, and a message waits for a reply
    nobody sent. This sweep raises all three against the configured windows, and
    it recommends rather than replies. Nothing leaves the platform on its own.
    """
    from app.db.models.governance import Communication
    from app.db.models.organisation import ConfigSetting
    from app.services.notifications import notify

    raised = 0
    with owner_session() as session:
        settings_rows = {
            row.key: row.value
            for row in session.execute(
                select(ConfigSetting).where(
                    ConfigSetting.area == "inbox_watch", ConfigSetting.active.is_(True)
                )
            ).scalars()
        }
        deadline_lead = int(_setting(settings_rows, "deadline_lead_days", 7))
        silence_days = int(_setting(settings_rows, "silence_days", 5))
        recipients = _setting(settings_rows, "recipients", ["legal@dsn.example"])

        now = datetime.now(UTC)
        horizon = (now + timedelta(days=deadline_lead)).date()

        pending = list(
            session.execute(
                select(Communication).where(
                    Communication.handled.is_(False),
                    Communication.quarantined.is_(False),
                )
            ).scalars()
        )

        for message in pending:
            waiting_since = message.awaiting_response_since or message.received_at
            reasons = _watch_reasons(session, message, horizon, silence_days, now, waiting_since)
            if not reasons:
                continue

            notify(
                session,
                connector_code="notification_channel",
                recipients=list(recipients),
                subject=f"Inbox watch: {message.subject[:120]}",
                body=(
                    f"From {message.sender}, received {message.received_at:%d %B %Y}.\n"
                    + "\n".join(f"- {reason}" for reason in reasons)
                    + "\nNothing has been sent and no matter has been created."
                ),
                record_reference=message.external_id,
            )
            message.awaiting_response_since = message.awaiting_response_since or waiting_since
            raised += 1

    return raised


@celery_app.task(name="dsn_lai.renewal_watch")
def renewal_watch() -> int:
    """Open a renewal task on every contract whose notice window is approaching
    and that does not already carry one (LOP-M08-US-04)."""
    from app.db.models.contract import Contract
    from app.services import obligations as rules
    from app.services import sequences

    default_lead = 60
    created = 0
    with owner_session() as session:
        today = datetime.now(UTC).date()
        contracts = list(
            session.execute(
                select(Contract).where(
                    Contract.end_date.is_not(None),
                    Contract.renewal_type != "none",
                )
            ).scalars()
        )

        for contract in contracts:
            deadline = rules.notice_deadline(contract.end_date, contract.notice_period_days or 0)
            due = rules.renewal_task_date(deadline, default_lead)
            if due > today:
                continue

            existing = session.execute(
                select(Obligation).where(
                    Obligation.contract_id == contract.id,
                    Obligation.obligation_type == "renewal",
                )
            ).scalar_one_or_none()
            if existing is not None:
                continue

            session.add(
                Obligation(
                    reference=sequences.new_obligation_reference(
                        session, int(contract.reference.split("-")[-1])
                    ),
                    contract_id=contract.id,
                    matter_id=contract.matter_id,
                    entity=contract.entity,
                    name=f"Renewal decision, {contract.reference}",
                    description=(
                        f"The notice deadline is {deadline} and the agreement ends "
                        f"{contract.end_date}."
                    ),
                    obligation_type="renewal",
                    due_date=due,
                    lead_time_days=default_lead,
                    decision_options=["renew", "renegotiate", "terminate", "lapse"],
                    status=ObligationStatus.OPEN.value,
                )
            )
            created += 1

    return created


def _watch_reasons(session, message, horizon, silence_days: int, now, waiting_since) -> list[str]:
    """Collect every reason this message deserves attention.

    A message can qualify on more than one count, and the recipient needs all of
    them rather than the first one found.
    """
    from app.db.models.governance import ExtractedValue

    reasons: list[str] = []

    for value in session.execute(
        select(ExtractedValue).where(
            ExtractedValue.communication_id == message.id,
            ExtractedValue.field_name.in_(["deadline", "date"]),
        )
    ).scalars():
        due = _as_date(value.value)
        if due and due <= horizon:
            reasons.append(f"An extracted deadline falls on {due}.")

    if message.implied_work and message.implied_work_phrase:
        reasons.append(f"Implied work was flagged on the phrase: {message.implied_work_phrase}")

    if waiting_since and (now - waiting_since).days >= silence_days:
        reasons.append(f"No response has been recorded for {(now - waiting_since).days} days.")

    return reasons


def _setting(rows: dict, key: str, fallback):
    raw = rows.get(key)
    if raw is None:
        return fallback
    if isinstance(raw, dict) and "value" in raw:
        return raw["value"]
    return raw


def _as_date(raw: str):
    from datetime import date

    try:
        return date.fromisoformat(raw.strip()[:10])
    except (ValueError, AttributeError):
        return None


@celery_app.task(name="dsn_lai.evaluation_sweep")
def evaluation_sweep() -> dict:
    """Re-measure every capability that has an active golden set.

    Nothing is switched off here. A capability nobody has measured for a
    quarter is a capability nobody can defend, so the schedule takes the
    reading whether or not anyone remembers, and the register carries the
    failures to whoever owns them.
    """
    from app.services import evaluation

    with owner_session() as session:
        outcomes = evaluation.sweep(session)

    measured = [row for row in outcomes if row.get("measured")]
    failed = [row for row in measured if not row.get("passed")]
    logger.info(
        "Evaluation sweep measured %s capabilities, %s below their gate.",
        len(measured),
        len(failed),
    )
    return {
        "measured": len(measured),
        "below_gate": [row["capability"] for row in failed],
        "skipped": [
            {"capability": row["capability"], "reason": row["reason"]}
            for row in outcomes
            if not row.get("measured")
        ],
    }


@celery_app.task(name="dsn_lai.rebuild_memory")
def rebuild_memory() -> dict:
    """Write memory from the records that should already be in it.

    Indexing happens at the event that creates a record, which is the only way
    an agreement executed this morning is answerable this afternoon. This is
    the repair for everything that predates that, and the safety net for a
    write that failed while an embedding host was unreachable.

    Idempotent: each chunk is keyed on its source and rewritten, so running it
    twice leaves one chunk per record rather than two.
    """
    from app.db.models.contract import Contract
    from app.db.models.counterparty import Counterparty
    from app.db.models.document import Document, ReviewFinding
    from app.db.models.library import Clause, ClauseVersion
    from app.db.models.matter import DecisionRecord, Matter
    from app.domain.enums import VersionStatus
    from app.services import memory

    written = {"contracts": 0, "decisions": 0, "findings": 0, "clauses": 0}
    with owner_session() as session:
        for contract in session.execute(
            select(Contract).where(Contract.authoritative.is_(True))
        ).scalars():
            matter = session.get(Matter, contract.matter_id)
            memory.index_contract(
                session,
                contract,
                matter=matter,
                counterparty=session.get(Counterparty, contract.counterparty_id)
                if contract.counterparty_id
                else None,
            )
            written["contracts"] += 1
            document = (
                session.get(Document, contract.executed_document_id)
                if contract.executed_document_id
                else None
            )
            written["clauses"] += len(
                memory.index_contract_clauses(
                    session,
                    contract,
                    document,
                    matter=matter,
                    counterparty=session.get(Counterparty, contract.counterparty_id)
                    if contract.counterparty_id
                    else None,
                )
            )

        for record in session.execute(select(DecisionRecord)).scalars():
            matter = session.get(Matter, record.matter_id) if record.matter_id else None
            memory.index_decision(session, record, matter=matter)
            written["decisions"] += 1

        for finding in session.execute(
            select(ReviewFinding).where(ReviewFinding.decision.in_(["accepted", "edited"]))
        ).scalars():
            memory.index_finding(session, finding, matter=session.get(Matter, finding.matter_id))
            written["findings"] += 1

        for version in session.execute(
            select(ClauseVersion).where(ClauseVersion.status == VersionStatus.APPROVED.value)
        ).scalars():
            clause = session.get(Clause, version.clause_id)
            for entity in (clause.entity_applicability if clause else None) or ["EAI"]:
                memory.index_clause_version(
                    session,
                    version,
                    category=clause.category if clause else "Clause",
                    entity=entity,
                )
                written["clauses"] += 1

        session.flush()

    logger.info("Rebuilt memory: %s", written)
    return written


@celery_app.task(name="dsn_lai.reindex_memory")
def reindex_memory(batch: int = 200) -> dict:
    """Re-embed the retrieval corpus under the configured provider.

    Vectors written under one embedding provider mean nothing to another, so
    changing the provider makes the existing index unreadable rather than
    merely worse. This is how an index is moved from one space to the other,
    and it has to finish before retrieval quality can be judged.
    """
    from app.ai.embeddings import embed, provider
    from app.db.models.platform import MemoryChunk

    name = provider()
    written = 0
    with owner_session() as session:
        chunks = list(session.execute(select(MemoryChunk)).scalars())
        for start in range(0, len(chunks), batch):
            window = chunks[start : start + batch]
            vectors = embed([chunk.body for chunk in window])
            for chunk, vector in zip(window, vectors, strict=True):
                chunk.embedding = vector
            written += len(window)
            session.flush()

    logger.info("Reindexed %s chunks under the %s embedding provider.", written, name)
    return {"chunks": written, "provider": name}
