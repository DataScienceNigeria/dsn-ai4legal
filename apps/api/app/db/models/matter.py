"""Matter management and triage, M02.

A matter is the container for a piece of legal work. Every document,
communication, approval and obligation attaches to it.
"""

import uuid
from datetime import date, datetime

from sqlalchemy import (
    Boolean,
    Date,
    DateTime,
    ForeignKey,
    Index,
    Numeric,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.dialects.postgresql import UUID as PgUUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base, EntityScoped, Timestamped, UUIDPrimaryKey
from app.domain.enums import DataClass, MatterState, RiskTier


class Matter(UUIDPrimaryKey, Timestamped, EntityScoped, Base):
    """The lifecycle record. The matter number is issued at acceptance."""

    __tablename__ = "matter"

    number: Mapped[str] = mapped_column(String(32), unique=True, nullable=False, index=True)
    request_id: Mapped[uuid.UUID | None] = mapped_column(
        PgUUID(as_uuid=True), ForeignKey("request.id", ondelete="SET NULL")
    )
    request_type_id: Mapped[uuid.UUID | None] = mapped_column(
        PgUUID(as_uuid=True), ForeignKey("request_type.id", ondelete="SET NULL")
    )
    practice_code: Mapped[str] = mapped_column(String(3), default="COM")
    title: Mapped[str] = mapped_column(String(255), nullable=False)
    counterparty_id: Mapped[uuid.UUID | None] = mapped_column(
        PgUUID(as_uuid=True), ForeignKey("counterparty.id", ondelete="SET NULL"), index=True
    )
    requester_id: Mapped[uuid.UUID | None] = mapped_column(
        PgUUID(as_uuid=True), ForeignKey("app_user.id", ondelete="SET NULL")
    )
    business_owner_id: Mapped[uuid.UUID | None] = mapped_column(
        PgUUID(as_uuid=True), ForeignKey("app_user.id", ondelete="SET NULL")
    )
    responsible_lawyer_id: Mapped[uuid.UUID | None] = mapped_column(
        PgUUID(as_uuid=True), ForeignKey("app_user.id", ondelete="SET NULL"), index=True
    )
    priority: Mapped[str] = mapped_column(String(16), default="normal")
    risk_tier: Mapped[str] = mapped_column(String(16), default=RiskTier.TIER_2.value, index=True)
    tier_rationale: Mapped[list[str]] = mapped_column(JSONB, default=list)
    tier_overridden: Mapped[bool] = mapped_column(Boolean, default=False)
    tier_override_reason: Mapped[str | None] = mapped_column(Text)
    classification: Mapped[str] = mapped_column(
        String(16), default=DataClass.CONFIDENTIAL.value, nullable=False
    )
    status: Mapped[str] = mapped_column(
        String(40), default=MatterState.ACCEPTED.value, nullable=False, index=True
    )
    state_before_hold: Mapped[str | None] = mapped_column(String(40))
    next_action: Mapped[str | None] = mapped_column(String(255))
    due_date: Mapped[date | None] = mapped_column(Date)
    sla_target_hours: Mapped[int | None] = mapped_column()
    sla_started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    blocker: Mapped[str | None] = mapped_column(String(255))
    privacy_flag: Mapped[bool] = mapped_column(Boolean, default=False)
    value_amount: Mapped[float | None] = mapped_column(Numeric(18, 2))
    value_currency: Mapped[str] = mapped_column(String(3), default="NGN")

    restricted: Mapped[bool] = mapped_column(Boolean, default=False, index=True)

    parent_matter_id: Mapped[uuid.UUID | None] = mapped_column(
        PgUUID(as_uuid=True), ForeignKey("matter.id", ondelete="SET NULL")
    )

    counterparty = relationship("Counterparty", lazy="joined")
    transitions: Mapped[list["MatterTransition"]] = relationship(
        back_populates="matter",
        cascade="all, delete-orphan",
        order_by="MatterTransition.occurred_at",
    )
    decisions: Mapped[list["DecisionRecord"]] = relationship(
        back_populates="matter", cascade="all, delete-orphan"
    )
    access_grants: Mapped[list["MatterAccess"]] = relationship(
        back_populates="matter", cascade="all, delete-orphan"
    )

class MatterTransition(UUIDPrimaryKey, Base):
    """Every transition records actor, timestamp and reason where required.

    Transitions are the sole source for turnaround metrics (PRD section 8.2).
    """

    __tablename__ = "matter_transition"
    __table_args__ = (Index("ix_matter_transition_matter_time", "matter_id", "occurred_at"),)

    matter_id: Mapped[uuid.UUID] = mapped_column(
        PgUUID(as_uuid=True), ForeignKey("matter.id", ondelete="CASCADE"), nullable=False
    )
    from_state: Mapped[str | None] = mapped_column(String(40))
    to_state: Mapped[str] = mapped_column(String(40), nullable=False)
    reason: Mapped[str | None] = mapped_column(Text)
    actor_id: Mapped[uuid.UUID | None] = mapped_column(
        PgUUID(as_uuid=True), ForeignKey("app_user.id", ondelete="SET NULL")
    )
    occurred_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, index=True
    )
    invalidated_approvals: Mapped[int] = mapped_column(default=0)
    clock_running: Mapped[bool] = mapped_column(Boolean, default=True)

    matter: Mapped[Matter] = relationship(back_populates="transitions")

class DecisionRecord(UUIDPrimaryKey, Timestamped, Base):
    """A decision and its reason, so the memory survives the individual.

    Entries are indexed into institutional memory (M10) and cannot be silently
    deleted, only superseded (PRD LOP-M02-US-05).
    """

    __tablename__ = "decision_record"

    sequence: Mapped[int] = mapped_column(nullable=False, index=True)
    matter_id: Mapped[uuid.UUID | None] = mapped_column(
        PgUUID(as_uuid=True), ForeignKey("matter.id", ondelete="CASCADE"), index=True
    )
    clause_id: Mapped[uuid.UUID | None] = mapped_column(
        PgUUID(as_uuid=True), ForeignKey("clause.id", ondelete="SET NULL")
    )
    entity: Mapped[str] = mapped_column(String(3), nullable=False, index=True)
    decision: Mapped[str] = mapped_column(Text, nullable=False)
    reason: Mapped[str] = mapped_column(Text, nullable=False)
    alternatives_considered: Mapped[str | None] = mapped_column(Text)
    clause_references: Mapped[list[str]] = mapped_column(JSONB, default=list)
    authority_level: Mapped[str] = mapped_column(String(24), default="house")
    residual_risk_accepted: Mapped[bool] = mapped_column(Boolean, default=False)
    commercial_rationale: Mapped[str | None] = mapped_column(Text)
    decided_by_id: Mapped[uuid.UUID | None] = mapped_column(
        PgUUID(as_uuid=True), ForeignKey("app_user.id", ondelete="SET NULL")
    )
    decided_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    superseded_by_id: Mapped[uuid.UUID | None] = mapped_column(
        PgUUID(as_uuid=True), ForeignKey("decision_record.id", ondelete="SET NULL")
    )
    counterparty_id: Mapped[uuid.UUID | None] = mapped_column(
        PgUUID(as_uuid=True), ForeignKey("counterparty.id", ondelete="SET NULL")
    )

    matter: Mapped[Matter | None] = relationship(back_populates="decisions")

class MatterAccess(UUIDPrimaryKey, Base):
    """Explicit naming for restricted matters."""

    __tablename__ = "matter_access"
    __table_args__ = (UniqueConstraint("matter_id", "user_id"),)

    matter_id: Mapped[uuid.UUID] = mapped_column(
        PgUUID(as_uuid=True), ForeignKey("matter.id", ondelete="CASCADE"), nullable=False
    )
    user_id: Mapped[uuid.UUID] = mapped_column(
        PgUUID(as_uuid=True), ForeignKey("app_user.id", ondelete="CASCADE"), nullable=False
    )
    granted_by_id: Mapped[uuid.UUID | None] = mapped_column(
        PgUUID(as_uuid=True), ForeignKey("app_user.id", ondelete="SET NULL")
    )

    matter: Mapped[Matter] = relationship(back_populates="access_grants")

class MatterLink(UUIDPrimaryKey, Base):
    """Related work grouped, not duplicated (PRD LOP-M02-US-06)."""

    __tablename__ = "matter_link"
    __table_args__ = (UniqueConstraint("matter_id", "linked_matter_id", "link_type"),)

    matter_id: Mapped[uuid.UUID] = mapped_column(
        PgUUID(as_uuid=True), ForeignKey("matter.id", ondelete="CASCADE"), nullable=False
    )
    linked_matter_id: Mapped[uuid.UUID] = mapped_column(
        PgUUID(as_uuid=True), ForeignKey("matter.id", ondelete="CASCADE"), nullable=False
    )
    link_type: Mapped[str] = mapped_column(String(32), default="related")


class ConsultantReview(UUIDPrimaryKey, Timestamped, EntityScoped, Base):
    """External counsel asked to read a draft, and what they said about it.

    Stage 3 of the guide. Legal shares the draft with the designated Legal
    Consultant, assesses their comments, and incorporates what it accepts while
    holding the organisation's position.

    A review rather than an approval, and the distinction is the whole design.
    The guide's responsibility matrix has the consultant leading legal review
    alongside Legal, which is a reader's authority; nothing here lets them
    approve, publish, sign, or change a document. They write, Legal decides. The
    same rule the platform applies to its own model layer, applied to a person
    who is not on the staff.

    Access is a grant, not a role. Asking for a review names the consultant on
    that matter and nothing else, so a consultant engaged on one negotiation
    cannot read the rest of the portfolio.
    """

    __tablename__ = "consultant_review"

    matter_id: Mapped[uuid.UUID] = mapped_column(
        PgUUID(as_uuid=True), ForeignKey("matter.id", ondelete="CASCADE"), nullable=False,
        index=True,
    )
    document_id: Mapped[uuid.UUID | None] = mapped_column(
        PgUUID(as_uuid=True), ForeignKey("document.id", ondelete="SET NULL")
    )
    consultant_id: Mapped[uuid.UUID] = mapped_column(
        PgUUID(as_uuid=True), ForeignKey("app_user.id", ondelete="CASCADE"), nullable=False,
        index=True,
    )
    requested_by_id: Mapped[uuid.UUID | None] = mapped_column(
        PgUUID(as_uuid=True), ForeignKey("app_user.id", ondelete="SET NULL")
    )

    brief: Mapped[str] = mapped_column(Text, nullable=False)
    """What Legal is asking them to look at.

    Required, because "please review" is how a consultant bills for reading the
    whole agreement to answer a question about one clause."""

    due_date: Mapped[date | None] = mapped_column(Date)
    status: Mapped[str] = mapped_column(
        String(24), default="requested", nullable=False, index=True
    )
    comments: Mapped[str | None] = mapped_column(Text)
    returned_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    assessment: Mapped[str | None] = mapped_column(Text)
    """What Legal did with the comments.

    The guide says Legal assesses the comments and incorporates the appropriate
    amendments while maintaining the organisation's position. Recording which
    were taken and which were not is what makes the second half of that sentence
    auditable rather than aspirational."""

    assessed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    assessed_by_id: Mapped[uuid.UUID | None] = mapped_column(
        PgUUID(as_uuid=True), ForeignKey("app_user.id", ondelete="SET NULL")
    )

    matter: Mapped[Matter] = relationship("Matter", viewonly=True)
    consultant: Mapped["User"] = relationship(  # noqa: F821
        "User", foreign_keys=[consultant_id], lazy="joined", viewonly=True
    )

    @property
    def consultant_name(self) -> str | None:
        return self.consultant.name if self.consultant else None
