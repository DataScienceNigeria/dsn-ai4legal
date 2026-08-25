"""Communications, assessments and compliance, M09, M11 and M12."""

import uuid
from datetime import date, datetime

from sqlalchemy import Boolean, Date, DateTime, ForeignKey, Integer, String, Text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.dialects.postgresql import UUID as PgUUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base, EntityScoped, Timestamped, UUIDPrimaryKey
from app.domain.enums import AssessmentStage, AssessmentType, DataClass


class Mailbox(UUIDPrimaryKey, Timestamped, Base):
    """Explicitly named mailboxes only. Any change is an audited event."""

    __tablename__ = "mailbox"

    address: Mapped[str] = mapped_column(String(320), unique=True, nullable=False)
    entity: Mapped[str] = mapped_column(String(3), nullable=False)
    provider: Mapped[str] = mapped_column(String(24), default="microsoft_graph")
    scopes: Mapped[list[str]] = mapped_column(JSONB, default=list)
    active: Mapped[bool] = mapped_column(Boolean, default=True)
    owner_id: Mapped[uuid.UUID | None] = mapped_column(
        PgUUID(as_uuid=True), ForeignKey("app_user.id", ondelete="SET NULL")
    )
    last_polled_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

class Communication(UUIDPrimaryKey, Timestamped, EntityScoped, Base):
    """A message from an approved mailbox, with its suggested classification."""

    __tablename__ = "communication"

    mailbox_id: Mapped[uuid.UUID | None] = mapped_column(
        PgUUID(as_uuid=True), ForeignKey("mailbox.id", ondelete="SET NULL")
    )
    external_id: Mapped[str] = mapped_column(String(255), unique=True, nullable=False)
    direction: Mapped[str] = mapped_column(String(16), default="inbound")
    participants: Mapped[list[dict]] = mapped_column(JSONB, default=list)
    sender: Mapped[str] = mapped_column(String(320), nullable=False)
    subject: Mapped[str] = mapped_column(String(512), nullable=False)
    body: Mapped[str] = mapped_column(Text, nullable=False)
    received_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, index=True
    )
    classification: Mapped[str | None] = mapped_column(String(32), index=True)
    classification_confidence: Mapped[float | None] = mapped_column()
    classification_corrected: Mapped[bool] = mapped_column(Boolean, default=False)
    corrected_classification: Mapped[str | None] = mapped_column(String(32))
    implied_work: Mapped[bool] = mapped_column(Boolean, default=False, index=True)
    implied_work_phrase: Mapped[str | None] = mapped_column(Text)
    awaiting_response_since: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    matter_id: Mapped[uuid.UUID | None] = mapped_column(
        PgUUID(as_uuid=True), ForeignKey("matter.id", ondelete="SET NULL"), index=True
    )
    proposed_acknowledgment: Mapped[str | None] = mapped_column(Text)
    proposed_matter_type: Mapped[str | None] = mapped_column(String(64))
    proposed_priority: Mapped[str | None] = mapped_column(String(16))
    proposed_owner_id: Mapped[uuid.UUID | None] = mapped_column(
        PgUUID(as_uuid=True), ForeignKey("app_user.id", ondelete="SET NULL")
    )
    handled: Mapped[bool] = mapped_column(Boolean, default=False, index=True)
    classification_interaction_id: Mapped[str | None] = mapped_column(String(64))
    injection_flagged: Mapped[bool] = mapped_column(Boolean, default=False)
    quarantined: Mapped[bool] = mapped_column(Boolean, default=False)

    extracted_values: Mapped[list["ExtractedValue"]] = relationship(
        back_populates="communication", cascade="all, delete-orphan"
    )

class ExtractedValue(UUIDPrimaryKey, Timestamped, Base):
    """All extracted values are suggestions until confirmed, field by field.

    Each shows the sentence it came from (PRD LOP-M09-US-03).
    """

    __tablename__ = "extracted_value"

    communication_id: Mapped[uuid.UUID | None] = mapped_column(
        PgUUID(as_uuid=True), ForeignKey("communication.id", ondelete="CASCADE"), index=True
    )
    document_id: Mapped[uuid.UUID | None] = mapped_column(
        PgUUID(as_uuid=True), ForeignKey("document.id", ondelete="CASCADE")
    )
    field_name: Mapped[str] = mapped_column(String(64), nullable=False)
    value: Mapped[str] = mapped_column(Text, nullable=False)
    source_sentence: Mapped[str] = mapped_column(Text, nullable=False)
    confidence: Mapped[float | None] = mapped_column()
    decision: Mapped[str] = mapped_column(String(16), default="pending")
    decided_by_id: Mapped[uuid.UUID | None] = mapped_column(
        PgUUID(as_uuid=True), ForeignKey("app_user.id", ondelete="SET NULL")
    )
    decided_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    corrected_value: Mapped[str | None] = mapped_column(Text)

    communication: Mapped[Communication | None] = relationship(back_populates="extracted_values")

class Product(UUIDPrimaryKey, Timestamped, EntityScoped, Base):
    """A product or dataset that an assessment attaches to."""

    __tablename__ = "product"

    name: Mapped[str] = mapped_column(String(255), nullable=False)
    purpose: Mapped[str | None] = mapped_column(Text)
    owner_id: Mapped[uuid.UUID | None] = mapped_column(
        PgUUID(as_uuid=True), ForeignKey("app_user.id", ondelete="SET NULL")
    )
    intended_users: Mapped[str | None] = mapped_column(Text)
    datasets: Mapped[list[str]] = mapped_column(JSONB, default=list)
    models: Mapped[list[str]] = mapped_column(JSONB, default=list)
    vendors: Mapped[list[str]] = mapped_column(JSONB, default=list)
    approval_status: Mapped[str] = mapped_column(String(24), default="not_assessed")
    review_date: Mapped[date | None] = mapped_column(Date)

class Assessment(UUIDPrimaryKey, Timestamped, EntityScoped, Base):
    """DPIA and AI assessment as a workflow with evidence and an owner, M11."""

    __tablename__ = "assessment"

    reference: Mapped[str] = mapped_column(String(24), unique=True, nullable=False, index=True)
    assessment_type: Mapped[str] = mapped_column(
        String(24), default=AssessmentType.DPIA.value, nullable=False
    )
    title: Mapped[str] = mapped_column(String(255), nullable=False)
    product_id: Mapped[uuid.UUID | None] = mapped_column(
        PgUUID(as_uuid=True), ForeignKey("product.id", ondelete="SET NULL")
    )
    vendor_id: Mapped[uuid.UUID | None] = mapped_column(
        PgUUID(as_uuid=True), ForeignKey("vendor.id", ondelete="SET NULL")
    )
    matter_id: Mapped[uuid.UUID | None] = mapped_column(
        PgUUID(as_uuid=True), ForeignKey("matter.id", ondelete="SET NULL")
    )
    contract_id: Mapped[uuid.UUID | None] = mapped_column(
        PgUUID(as_uuid=True), ForeignKey("contract.id", ondelete="SET NULL")
    )
    stage: Mapped[str] = mapped_column(
        String(24), default=AssessmentStage.INITIATED.value, nullable=False, index=True
    )
    stage_records: Mapped[list[dict]] = mapped_column(JSONB, default=list)
    captured: Mapped[dict] = mapped_column(JSONB, default=dict)
    risks: Mapped[list[dict]] = mapped_column(JSONB, default=list)
    controls: Mapped[list[dict]] = mapped_column(JSONB, default=list)
    testing_evidence: Mapped[list[dict]] = mapped_column(JSONB, default=list)
    conditions: Mapped[list[dict]] = mapped_column(JSONB, default=list)
    residual_risk_decision: Mapped[str | None] = mapped_column(String(24))
    residual_risk_reason: Mapped[str | None] = mapped_column(Text)
    residual_risk_owner_id: Mapped[uuid.UUID | None] = mapped_column(
        PgUUID(as_uuid=True), ForeignKey("app_user.id", ondelete="SET NULL")
    )
    approved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    review_date: Mapped[date | None] = mapped_column(Date, index=True)
    reassessment_triggered: Mapped[bool] = mapped_column(Boolean, default=False)
    classification: Mapped[str] = mapped_column(String(16), default=DataClass.INTERNAL.value)

    raised_by_id: Mapped[uuid.UUID | None] = mapped_column(
        PgUUID(as_uuid=True), ForeignKey("app_user.id", ondelete="SET NULL"), index=True
    )
    """The department lead who raised it. A DPIA is written by the people
    building the thing, because they are the ones who know what it does with
    personal data; legal reads it and judges it."""

    submitted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    """When it left the requester and reached the data protection officer.
    Before this it is a draft and belongs to whoever is writing it."""

    dpo_review: Mapped[dict] = mapped_column(JSONB, default=dict)
    """The officer's judgement, section by section: adequacy, reasons, a score
    out of ten, and recommendations with an owner and a date. Kept apart from
    the answers because they are two people's work and mixing them would let
    one edit the other."""

    final_decision: Mapped[str | None] = mapped_column(String(16))
    """go_ahead, modify, or stop. Three outcomes and no fourth: stop has to be
    available or the assessment is a formality."""

    final_decision_reason: Mapped[str | None] = mapped_column(Text)

class ComplianceItem(UUIDPrimaryKey, Timestamped, EntityScoped, Base):
    """Filing calendar with owners and evidence, M12."""

    __tablename__ = "compliance_item"

    requirement: Mapped[str] = mapped_column(String(255), nullable=False)
    statutory_reference: Mapped[str | None] = mapped_column(String(128))
    jurisdiction: Mapped[str] = mapped_column(String(64), default="Nigeria")
    filing_date: Mapped[date | None] = mapped_column(Date)
    recurrence: Mapped[str] = mapped_column(String(24), default="annual")
    accountable_owner_id: Mapped[uuid.UUID | None] = mapped_column(
        PgUUID(as_uuid=True), ForeignKey("app_user.id", ondelete="SET NULL")
    )
    evidence_required: Mapped[bool] = mapped_column(Boolean, default=True)
    evidence_reference: Mapped[str | None] = mapped_column(String(512))
    filing_number: Mapped[str | None] = mapped_column(String(128))
    filed_by_id: Mapped[uuid.UUID | None] = mapped_column(
        PgUUID(as_uuid=True), ForeignKey("app_user.id", ondelete="SET NULL")
    )
    next_due_date: Mapped[date | None] = mapped_column(Date, index=True)
    lead_time_days: Mapped[int] = mapped_column(Integer, default=30)
    version: Mapped[int] = mapped_column(Integer, default=1)
    effective_date: Mapped[date | None] = mapped_column(Date)
    supersedes_id: Mapped[uuid.UUID | None] = mapped_column(
        PgUUID(as_uuid=True), ForeignKey("compliance_item.id", ondelete="SET NULL")
    )
    status: Mapped[str] = mapped_column(String(24), default="open", index=True)

    # A deadline with no name against it is nobody's deadline, and the reminder
    # that will one day go out has to have somewhere to go.
    accountable_owner: Mapped["User | None"] = relationship(  # noqa: F821
        "User", foreign_keys=[accountable_owner_id], lazy="joined", viewonly=True
    )

    @property
    def accountable_owner_name(self) -> str | None:
        return self.accountable_owner.name if self.accountable_owner else None

    @property
    def due_soon_days(self) -> int:
        """How many days ahead of the date this starts asking to be done.

        A share of its own cycle rather than a flat number, because thirty days
        out is most of the month for a monthly return and barely worth saying
        for an annual one.
        """
        from app.services.obligations import due_soon_days as window

        return window(self.recurrence, self.lead_time_days)
