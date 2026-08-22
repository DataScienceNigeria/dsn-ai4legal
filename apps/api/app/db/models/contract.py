"""Contracts, approvals, signature and obligations, M07 and M08."""

import uuid
from datetime import date, datetime

from sqlalchemy import (
    Boolean,
    Date,
    DateTime,
    ForeignKey,
    Integer,
    Numeric,
    String,
    Text,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.dialects.postgresql import UUID as PgUUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base, EntityScoped, Timestamped, UUIDPrimaryKey
from app.domain.enums import ApprovalDecision, ObligationStatus


class Contract(UUIDPrimaryKey, Timestamped, EntityScoped, Base):
    """A proposed or executed agreement. One matter may hold several."""

    __tablename__ = "contract"

    reference: Mapped[str] = mapped_column(String(32), unique=True, nullable=False, index=True)
    matter_id: Mapped[uuid.UUID] = mapped_column(
        PgUUID(as_uuid=True),
        ForeignKey("matter.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    counterparty_id: Mapped[uuid.UUID | None] = mapped_column(
        PgUUID(as_uuid=True), ForeignKey("counterparty.id", ondelete="SET NULL"), index=True
    )
    agreement_type: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    effective_date: Mapped[date | None] = mapped_column(Date)
    term_months: Mapped[int | None] = mapped_column(Integer)
    end_date: Mapped[date | None] = mapped_column(Date, index=True)
    renewal_type: Mapped[str] = mapped_column(String(32), default="none")
    notice_period_days: Mapped[int | None] = mapped_column(Integer)
    value_amount: Mapped[float | None] = mapped_column(Numeric(18, 2))
    value_currency: Mapped[str] = mapped_column(String(3), default="NGN")
    governing_law: Mapped[str] = mapped_column(String(64), default="Nigeria")
    signature_status: Mapped[str] = mapped_column(String(32), default="not_requested")
    executed_document_id: Mapped[uuid.UUID | None] = mapped_column(
        PgUUID(as_uuid=True),
        ForeignKey("document.id", ondelete="SET NULL", use_alter=True),
    )
    executed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    content_hash: Mapped[str | None] = mapped_column(String(64), index=True)
    signature_certificate: Mapped[dict] = mapped_column(JSONB, default=dict)
    executed_outside_platform: Mapped[bool] = mapped_column(Boolean, default=False)
    execution_reason: Mapped[str | None] = mapped_column(Text)
    amends_contract_id: Mapped[uuid.UUID | None] = mapped_column(
        PgUUID(as_uuid=True), ForeignKey("contract.id", ondelete="SET NULL")
    )
    authoritative: Mapped[bool] = mapped_column(Boolean, default=False)

    obligations: Mapped[list["Obligation"]] = relationship(
        back_populates="contract", cascade="all, delete-orphan"
    )

class ApprovalChainDefinition(UUIDPrimaryKey, Timestamped, Base):
    """Configurable by entity, agreement type, value band and risk tier."""

    __tablename__ = "approval_chain_definition"

    name: Mapped[str] = mapped_column(String(128), nullable=False)
    entity: Mapped[str | None] = mapped_column(String(3))
    agreement_type: Mapped[str | None] = mapped_column(String(64))
    risk_tier: Mapped[str | None] = mapped_column(String(16))
    min_value: Mapped[float | None] = mapped_column(Numeric(18, 2))
    max_value: Mapped[float | None] = mapped_column(Numeric(18, 2))
    steps: Mapped[list[dict]] = mapped_column(JSONB, default=list)
    active: Mapped[bool] = mapped_column(Boolean, default=True)
    priority: Mapped[int] = mapped_column(Integer, default=100)

class Approval(UUIDPrimaryKey, Timestamped, Base):
    """Approval binds to a document content hash (PRD LOP-M07-US-03)."""

    __tablename__ = "approval"

    matter_id: Mapped[uuid.UUID] = mapped_column(
        PgUUID(as_uuid=True),
        ForeignKey("matter.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    contract_id: Mapped[uuid.UUID | None] = mapped_column(
        PgUUID(as_uuid=True), ForeignKey("contract.id", ondelete="SET NULL")
    )
    document_id: Mapped[uuid.UUID | None] = mapped_column(
        PgUUID(as_uuid=True), ForeignKey("document.id", ondelete="SET NULL")
    )
    document_hash: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    chain_definition_id: Mapped[uuid.UUID | None] = mapped_column(
        PgUUID(as_uuid=True), ForeignKey("approval_chain_definition.id", ondelete="SET NULL")
    )
    chain_snapshot: Mapped[dict] = mapped_column(JSONB, default=dict)
    step_index: Mapped[int] = mapped_column(Integer, default=0)
    step_name: Mapped[str] = mapped_column(String(128), nullable=False)
    step_mode: Mapped[str] = mapped_column(String(16), default="sequential")
    approver_id: Mapped[uuid.UUID | None] = mapped_column(
        PgUUID(as_uuid=True), ForeignKey("app_user.id", ondelete="SET NULL"), index=True
    )
    approver_role: Mapped[str | None] = mapped_column(String(32))
    delegate_used_id: Mapped[uuid.UUID | None] = mapped_column(
        PgUUID(as_uuid=True), ForeignKey("app_user.id", ondelete="SET NULL")
    )
    decision: Mapped[str] = mapped_column(
        String(16), default=ApprovalDecision.PENDING.value, nullable=False, index=True
    )
    comments: Mapped[str | None] = mapped_column(Text)
    decided_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    due_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    reminders_sent: Mapped[int] = mapped_column(Integer, default=0)
    escalated_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    invalidated_by_event: Mapped[str | None] = mapped_column(String(255))

class SignatureRequest(UUIDPrimaryKey, Timestamped, Base):
    """Controlled execution. Cannot be issued for an unapproved hash."""

    __tablename__ = "signature_request"

    matter_id: Mapped[uuid.UUID] = mapped_column(
        PgUUID(as_uuid=True), ForeignKey("matter.id", ondelete="CASCADE"), nullable=False
    )
    contract_id: Mapped[uuid.UUID | None] = mapped_column(
        PgUUID(as_uuid=True), ForeignKey("contract.id", ondelete="SET NULL")
    )
    document_id: Mapped[uuid.UUID] = mapped_column(
        PgUUID(as_uuid=True), ForeignKey("document.id", ondelete="RESTRICT"), nullable=False
    )
    document_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    provider: Mapped[str] = mapped_column(String(32), default="internal")
    external_reference: Mapped[str | None] = mapped_column(String(128), index=True)
    signers: Mapped[list[dict]] = mapped_column(JSONB, default=list)
    status: Mapped[str] = mapped_column(String(24), default="sent", index=True)
    cancelled_reason: Mapped[str | None] = mapped_column(Text)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    audit_certificate: Mapped[dict] = mapped_column(JSONB, default=dict)
    requested_by_id: Mapped[uuid.UUID | None] = mapped_column(
        PgUUID(as_uuid=True), ForeignKey("app_user.id", ondelete="SET NULL")
    )

class Obligation(UUIDPrimaryKey, Timestamped, EntityScoped, Base):
    """A tracked duty arising from a contract or a statutory requirement.

    Proposals show the clause they came from and become tasks only when Legal
    confirms them (PRD LOP-M08-US-02).
    """

    __tablename__ = "obligation"

    reference: Mapped[str] = mapped_column(String(24), unique=True, nullable=False, index=True)
    contract_id: Mapped[uuid.UUID | None] = mapped_column(
        PgUUID(as_uuid=True), ForeignKey("contract.id", ondelete="CASCADE"), index=True
    )
    matter_id: Mapped[uuid.UUID | None] = mapped_column(
        PgUUID(as_uuid=True), ForeignKey("matter.id", ondelete="CASCADE")
    )
    assessment_id: Mapped[uuid.UUID | None] = mapped_column(
        PgUUID(as_uuid=True), ForeignKey("assessment.id", ondelete="CASCADE")
    )
    compliance_item_id: Mapped[uuid.UUID | None] = mapped_column(
        PgUUID(as_uuid=True), ForeignKey("compliance_item.id", ondelete="CASCADE")
    )
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    description: Mapped[str | None] = mapped_column(Text)
    obligation_type: Mapped[str] = mapped_column(String(32), default="deliverable")
    source_clause: Mapped[str | None] = mapped_column(String(64))
    source_quote: Mapped[str | None] = mapped_column(Text)
    owner_id: Mapped[uuid.UUID | None] = mapped_column(
        PgUUID(as_uuid=True), ForeignKey("app_user.id", ondelete="SET NULL"), index=True
    )
    due_date: Mapped[date | None] = mapped_column(Date, index=True)
    recurrence: Mapped[str] = mapped_column(String(24), default="none")
    lead_time_days: Mapped[int] = mapped_column(Integer, default=14)
    escalation_rule: Mapped[dict] = mapped_column(JSONB, default=dict)
    evidence_required: Mapped[bool] = mapped_column(Boolean, default=False)
    evidence_reference: Mapped[str | None] = mapped_column(String(512))
    evidence_note: Mapped[str | None] = mapped_column(Text)
    status: Mapped[str] = mapped_column(
        String(16), default=ObligationStatus.PROPOSED.value, nullable=False, index=True
    )
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    completed_by_id: Mapped[uuid.UUID | None] = mapped_column(
        PgUUID(as_uuid=True), ForeignKey("app_user.id", ondelete="SET NULL")
    )
    decision_options: Mapped[list[str]] = mapped_column(JSONB, default=list)
    decision_taken: Mapped[str | None] = mapped_column(String(32))
    interaction_id: Mapped[str | None] = mapped_column(String(64))

    contract: Mapped[Contract | None] = relationship(back_populates="obligations")
