"""Legal portal and guided intake, M01."""

import uuid
from datetime import date, datetime

from sqlalchemy import Boolean, Date, DateTime, ForeignKey, Integer, Numeric, String, Text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.dialects.postgresql import UUID as PgUUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base, EntityScoped, Timestamped, UUIDPrimaryKey
from app.domain.enums import MatterState


class RequestType(UUIDPrimaryKey, Timestamped, Base):
    """A request type in business language, mapped to an internal type.

    The mandatory field set is configurable per request type by the Head of
    Legal without a code change (PRD LOP-M01-US-03).
    """

    __tablename__ = "request_type"

    code: Mapped[str] = mapped_column(String(64), unique=True, nullable=False)
    business_label: Mapped[str] = mapped_column(String(255), nullable=False)
    description: Mapped[str | None] = mapped_column(Text)
    agreement_type: Mapped[str] = mapped_column(String(64), nullable=False)
    practice_code: Mapped[str] = mapped_column(String(3), default="COM")
    fields: Mapped[list[dict]] = mapped_column(JSONB, default=list)
    mandatory_fields: Mapped[list[str]] = mapped_column(JSONB, default=list)
    sla_hours: Mapped[int] = mapped_column(Integer, default=48)
    value_threshold: Mapped[float | None] = mapped_column(Numeric(18, 2))
    active: Mapped[bool] = mapped_column(Boolean, default=True)
    sort_order: Mapped[int] = mapped_column(default=0)
    drafting_enabled: Mapped[bool] = mapped_column(Boolean, default=False)
    tier_1_auto_issue: Mapped[bool] = mapped_column(Boolean, default=False)

class Request(UUIDPrimaryKey, Timestamped, EntityScoped, Base):
    """A request remains a request until Legal accepts it (PRD section 7.1)."""

    __tablename__ = "request"

    reference: Mapped[str] = mapped_column(String(24), unique=True, nullable=False, index=True)
    request_type_id: Mapped[uuid.UUID] = mapped_column(
        PgUUID(as_uuid=True), ForeignKey("request_type.id", ondelete="RESTRICT"), nullable=False
    )
    requester_id: Mapped[uuid.UUID] = mapped_column(
        PgUUID(as_uuid=True), ForeignKey("app_user.id", ondelete="RESTRICT"), nullable=False
    )
    subject: Mapped[str] = mapped_column(String(255), nullable=False)
    purpose: Mapped[str | None] = mapped_column(Text)
    proposed_counterparty: Mapped[str | None] = mapped_column(String(255))
    counterparty_id: Mapped[uuid.UUID | None] = mapped_column(
        PgUUID(as_uuid=True), ForeignKey("counterparty.id", ondelete="SET NULL")
    )
    required_date: Mapped[date | None] = mapped_column(Date)
    value_amount: Mapped[float | None] = mapped_column(Numeric(18, 2))
    value_currency: Mapped[str] = mapped_column(String(3), default="NGN")

    personal_data: Mapped[bool] = mapped_column(Boolean, default=False)
    special_category_data: Mapped[bool] = mapped_column(Boolean, default=False)
    third_party_confidential: Mapped[bool] = mapped_column(Boolean, default=False)
    leaves_nigeria: Mapped[bool] = mapped_column(Boolean, default=False)
    privacy_flag: Mapped[bool] = mapped_column(Boolean, default=False, index=True)

    answers: Mapped[dict] = mapped_column(JSONB, default=dict)
    status: Mapped[str] = mapped_column(
        String(40), default=MatterState.SUBMITTED.value, nullable=False, index=True
    )
    triage_notes: Mapped[str | None] = mapped_column(Text)
    suggested_tier: Mapped[str | None] = mapped_column(String(16))
    tier_rationale: Mapped[list[str]] = mapped_column(JSONB, default=list)
    suggested_owner_id: Mapped[uuid.UUID | None] = mapped_column(
        PgUUID(as_uuid=True), ForeignKey("app_user.id", ondelete="SET NULL")
    )
    owner_rationale: Mapped[str | None] = mapped_column(Text)
    acknowledged_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    request_type: Mapped[RequestType] = relationship()
    attachments: Mapped[list["Attachment"]] = relationship(
        back_populates="request", cascade="all, delete-orphan"
    )

class Attachment(UUIDPrimaryKey, Timestamped, Base):
    """Supporting documents, virus scanned before storage (PRD LOP-M01-US-04)."""

    __tablename__ = "attachment"

    request_id: Mapped[uuid.UUID | None] = mapped_column(
        PgUUID(as_uuid=True), ForeignKey("request.id", ondelete="CASCADE")
    )
    filename: Mapped[str] = mapped_column(String(255), nullable=False)
    content_type: Mapped[str] = mapped_column(String(128), nullable=False)
    size_bytes: Mapped[int] = mapped_column(nullable=False)
    storage_key: Mapped[str] = mapped_column(String(512), nullable=False)
    content_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    scan_status: Mapped[str] = mapped_column(String(24), default="clean")
    uploaded_by_id: Mapped[uuid.UUID | None] = mapped_column(
        PgUUID(as_uuid=True), ForeignKey("app_user.id", ondelete="SET NULL")
    )

    request: Mapped[Request | None] = relationship(back_populates="attachments")
