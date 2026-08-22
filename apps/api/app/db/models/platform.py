"""Audit, outbox, idempotency and the retrieval index.

The audit store is append-only and administrators cannot alter it
(LOP-M15-US-03). The outbox gives reliable delivery without operating a message
broker in phase 1 (PRD section 10.1).
"""

import uuid
from datetime import datetime

from pgvector.sqlalchemy import Vector
from sqlalchemy import (
    BigInteger,
    Boolean,
    DateTime,
    Float,
    ForeignKey,
    Index,
    Integer,
    Sequence,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.dialects.postgresql import UUID as PgUUID
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, Timestamped, UUIDPrimaryKey

EMBEDDING_DIM = 384

class AuditEvent(UUIDPrimaryKey, Base):
    """Append-only. Insert is the only permitted operation.

    Every create, read of restricted content, update, delete, approval,
    generation, AI call, permission change and export is recorded.
    """

    __tablename__ = "audit_event"
    __table_args__ = (
        Index("ix_audit_event_object", "object_type", "object_id"),
        Index("ix_audit_event_actor_time", "actor_id", "occurred_at"),
    )

    # The chain is ordered by this, not by the clock. Two events written in the
    # same microsecond used to tie, and a tie in a hash chain means there is no
    # chain: the order the digests were computed in is unrecoverable.
    sequence: Mapped[int] = mapped_column(
        BigInteger,
        Sequence("audit_event_sequence"),
        unique=True,
        nullable=False,
        index=True,
    )
    occurred_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, index=True
    )
    actor_id: Mapped[uuid.UUID | None] = mapped_column(PgUUID(as_uuid=True))
    actor_label: Mapped[str] = mapped_column(String(255), default="system")
    entity: Mapped[str | None] = mapped_column(String(3), index=True)
    object_type: Mapped[str] = mapped_column(String(64), nullable=False)
    object_id: Mapped[str | None] = mapped_column(String(64))
    action: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    before_state: Mapped[dict | None] = mapped_column(JSONB)
    after_state: Mapped[dict | None] = mapped_column(JSONB)
    ip_address: Mapped[str | None] = mapped_column(String(64))
    session_id: Mapped[str | None] = mapped_column(String(64))
    result: Mapped[str] = mapped_column(String(16), default="success")
    detail: Mapped[str | None] = mapped_column(Text)
    previous_digest: Mapped[str | None] = mapped_column(String(64))
    digest: Mapped[str] = mapped_column(String(64), nullable=False)

class OutboxEvent(UUIDPrimaryKey, Timestamped, Base):
    """A durable outbox. Nothing that matters is delivered best-effort."""

    __tablename__ = "outbox_event"

    topic: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    payload: Mapped[dict] = mapped_column(JSONB, nullable=False)
    status: Mapped[str] = mapped_column(String(16), default="pending", index=True)
    attempts: Mapped[int] = mapped_column(Integer, default=0)
    last_error: Mapped[str | None] = mapped_column(Text)
    available_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, index=True
    )
    delivered_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

class IdempotencyKey(UUIDPrimaryKey, Timestamped, Base):
    """Retries must not create duplicate matters, documents or signature
    requests (PRD section 12.1)."""

    __tablename__ = "idempotency_key"
    __table_args__ = (UniqueConstraint("key", "endpoint"),)

    key: Mapped[str] = mapped_column(String(128), nullable=False, index=True)
    endpoint: Mapped[str] = mapped_column(String(255), nullable=False)
    user_id: Mapped[uuid.UUID | None] = mapped_column(PgUUID(as_uuid=True))
    request_digest: Mapped[str] = mapped_column(String(64), nullable=False)
    status_code: Mapped[int] = mapped_column(Integer, default=200)
    response_body: Mapped[dict] = mapped_column(JSONB, default=dict)

class Connector(UUIDPrimaryKey, Timestamped, Base):
    """Connector governance, PRD section 11.2.

    An unregistered connector is a security incident, not a convenience.
    """

    __tablename__ = "connector"

    code: Mapped[str] = mapped_column(String(64), unique=True, nullable=False)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    purpose: Mapped[str] = mapped_column(Text, nullable=False)
    direction: Mapped[str] = mapped_column(String(16), default="outbound")
    permitted_data_classes: Mapped[list[str]] = mapped_column(JSONB, default=list)
    scopes: Mapped[list[str]] = mapped_column(JSONB, default=list)
    owner_id: Mapped[uuid.UUID | None] = mapped_column(
        PgUUID(as_uuid=True), ForeignKey("app_user.id", ondelete="SET NULL")
    )
    review_date: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    active: Mapped[bool] = mapped_column(Boolean, default=True)

class EgressLog(UUIDPrimaryKey, Base):
    """Every outbound call records connector, purpose, record, class, result."""

    __tablename__ = "egress_log"

    occurred_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, index=True
    )
    connector_code: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    purpose: Mapped[str] = mapped_column(String(255), nullable=False)
    record_reference: Mapped[str | None] = mapped_column(String(64))
    data_class: Mapped[str] = mapped_column(String(16), nullable=False)
    result: Mapped[str] = mapped_column(String(16), default="success")
    detail: Mapped[str | None] = mapped_column(Text)

class RetentionPolicy(UUIDPrimaryKey, Timestamped, Base):
    """Retention is policy, not habit (PRD LOP-M15-US-04)."""

    __tablename__ = "retention_policy"

    record_class: Mapped[str] = mapped_column(String(64), unique=True, nullable=False)
    retain_years: Mapped[int] = mapped_column(Integer, default=7)
    legal_hold: Mapped[bool] = mapped_column(Boolean, default=False)
    hold_reason: Mapped[str | None] = mapped_column(Text)
    hold_set_by_id: Mapped[uuid.UUID | None] = mapped_column(
        PgUUID(as_uuid=True), ForeignKey("app_user.id", ondelete="SET NULL")
    )
    hold_set_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    deletion_requires_approval: Mapped[bool] = mapped_column(Boolean, default=True)
    description: Mapped[str | None] = mapped_column(Text)

class MemoryChunk(UUIDPrimaryKey, Timestamped, Base):
    """The retrieval corpus, M10.

    Chunking is clause-aware rather than fixed-length, so a citation always
    resolves to a legally meaningful unit (PRD section 13.3). Permission fields
    are stored on the chunk so retrieval can filter before ranking rather than
    after.
    """

    __tablename__ = "memory_chunk"
    __table_args__ = (
        Index("ix_memory_chunk_scope", "entity", "restricted"),
        Index("ix_memory_chunk_source", "source_type", "source_reference"),
    )

    entity: Mapped[str] = mapped_column(String(3), nullable=False, index=True)
    source_type: Mapped[str] = mapped_column(String(32), nullable=False, index=True)
    source_reference: Mapped[str] = mapped_column(String(64), nullable=False)
    source_detail: Mapped[str | None] = mapped_column(String(512))
    title: Mapped[str] = mapped_column(String(255), nullable=False)
    body: Mapped[str] = mapped_column(Text, nullable=False)
    restricted: Mapped[bool] = mapped_column(Boolean, default=False)
    matter_id: Mapped[uuid.UUID | None] = mapped_column(
        PgUUID(as_uuid=True), ForeignKey("matter.id", ondelete="CASCADE")
    )
    superseded: Mapped[bool] = mapped_column(Boolean, default=False)
    current_replacement: Mapped[str | None] = mapped_column(String(64))
    embedding: Mapped[list[float] | None] = mapped_column(Vector(EMBEDDING_DIM))
    weight: Mapped[float] = mapped_column(Float, default=1.0)

class QualitySample(UUIDPrimaryKey, Timestamped, Base):
    """The monthly quality sample, LOP-M04-US-04 and PRD section 16.3.

    Auto-issued documents never pass a human eye at the moment of issue, so each
    one is placed here and reviewed in the monthly sample. An unreviewed sample
    is the signal that tier 1 automation has outrun its assurance.
    """

    __tablename__ = "quality_sample"

    entity: Mapped[str] = mapped_column(String(3), nullable=False, index=True)
    period: Mapped[str] = mapped_column(String(7), nullable=False, index=True)
    object_type: Mapped[str] = mapped_column(String(32), nullable=False)
    object_reference: Mapped[str] = mapped_column(String(64), nullable=False)
    reason: Mapped[str] = mapped_column(String(255), nullable=False)
    reviewed: Mapped[bool] = mapped_column(Boolean, default=False, index=True)
    reviewer_id: Mapped[uuid.UUID | None] = mapped_column(
        PgUUID(as_uuid=True), ForeignKey("app_user.id", ondelete="SET NULL")
    )
    reviewed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    outcome: Mapped[str | None] = mapped_column(String(24))
    notes: Mapped[str | None] = mapped_column(Text)

class ExportRequest(UUIDPrimaryKey, Timestamped, Base):
    """Bulk export requires approval by a second authorised user, LOP-M15-US-05.

    The request is a record rather than an acknowledgment, because an export
    that nobody can point at afterwards is not a controlled export.
    """

    __tablename__ = "export_request"

    entity: Mapped[str] = mapped_column(String(3), nullable=False, index=True)
    record_class: Mapped[str] = mapped_column(String(64), nullable=False)
    scope: Mapped[dict] = mapped_column(JSONB, default=dict)
    reason: Mapped[str] = mapped_column(Text, nullable=False)
    data_classes: Mapped[list[str]] = mapped_column(JSONB, default=list)
    requested_by_id: Mapped[uuid.UUID | None] = mapped_column(
        PgUUID(as_uuid=True), ForeignKey("app_user.id", ondelete="SET NULL")
    )
    status: Mapped[str] = mapped_column(String(16), default="pending", index=True)
    approver_id: Mapped[uuid.UUID | None] = mapped_column(
        PgUUID(as_uuid=True), ForeignKey("app_user.id", ondelete="SET NULL")
    )
    decided_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    decision_reason: Mapped[str | None] = mapped_column(Text)
    row_count: Mapped[int | None] = mapped_column(Integer)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

class DeletionRequest(UUIDPrimaryKey, Timestamped, Base):
    """Defensible deletion, LOP-M15-US-04.

    A record under legal hold cannot be deleted by any role, deletion needs a
    second approver where the policy says so, and what is deleted leaves a
    certificate behind so the deletion itself is evidenced.
    """

    __tablename__ = "deletion_request"

    entity: Mapped[str] = mapped_column(String(3), nullable=False, index=True)
    record_class: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    object_type: Mapped[str] = mapped_column(String(32), nullable=False)
    object_reference: Mapped[str] = mapped_column(String(64), nullable=False)
    reason: Mapped[str] = mapped_column(Text, nullable=False)
    requested_by_id: Mapped[uuid.UUID | None] = mapped_column(
        PgUUID(as_uuid=True), ForeignKey("app_user.id", ondelete="SET NULL")
    )
    status: Mapped[str] = mapped_column(String(16), default="pending", index=True)
    approver_id: Mapped[uuid.UUID | None] = mapped_column(
        PgUUID(as_uuid=True), ForeignKey("app_user.id", ondelete="SET NULL")
    )
    decided_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    decision_reason: Mapped[str | None] = mapped_column(Text)
    executed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    certificate_reference: Mapped[str | None] = mapped_column(String(32), unique=True)
    certificate: Mapped[dict] = mapped_column(JSONB, default=dict)
