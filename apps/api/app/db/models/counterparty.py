"""Counterparty and vendor governance, M13."""

import uuid
from datetime import date

from sqlalchemy import Boolean, Date, ForeignKey, String, Text
from sqlalchemy.dialects.postgresql import ARRAY, JSONB
from sqlalchemy.dialects.postgresql import UUID as PgUUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base, Timestamped, UUIDPrimaryKey


class Counterparty(UUIDPrimaryKey, Timestamped, Base):
    """One permanent identity per counterparty, PRD LOP-M13-US-01.

    Name changes update the record without changing the identifier, and merged
    identifiers are retained as aliases.
    """

    __tablename__ = "counterparty"

    reference: Mapped[str] = mapped_column(String(16), unique=True, nullable=False, index=True)
    legal_name: Mapped[str] = mapped_column(String(255), nullable=False, index=True)
    aliases: Mapped[list[str]] = mapped_column(ARRAY(String(255)), default=list)
    trading_names: Mapped[list[str]] = mapped_column(ARRAY(String(255)), default=list)
    counterparty_type: Mapped[str] = mapped_column(String(64), default="company")
    registration_number: Mapped[str | None] = mapped_column(String(64), index=True)
    domain: Mapped[str | None] = mapped_column(String(255), index=True)
    jurisdiction: Mapped[str] = mapped_column(String(64), default="Nigeria")
    addresses: Mapped[list[dict]] = mapped_column(JSONB, default=list)
    contacts: Mapped[list[dict]] = mapped_column(JSONB, default=list)
    relationship_class: Mapped[str] = mapped_column(String(64), default="commercial")
    risk_class: Mapped[str] = mapped_column(String(32), default="standard")
    negotiation_notes: Mapped[str | None] = mapped_column(Text)
    merged_into_id: Mapped[uuid.UUID | None] = mapped_column(
        PgUUID(as_uuid=True), ForeignKey("counterparty.id", ondelete="SET NULL")
    )

    vendor: Mapped["Vendor | None"] = relationship(
        back_populates="counterparty", uselist=False, cascade="all, delete-orphan"
    )

class Vendor(UUIDPrimaryKey, Timestamped, Base):
    """Vendor governance in one record, PRD LOP-M13-US-03."""

    __tablename__ = "vendor"

    counterparty_id: Mapped[uuid.UUID] = mapped_column(
        PgUUID(as_uuid=True), ForeignKey("counterparty.id", ondelete="CASCADE"), unique=True
    )
    service_owner_id: Mapped[uuid.UUID | None] = mapped_column(
        PgUUID(as_uuid=True), ForeignKey("app_user.id", ondelete="SET NULL")
    )
    security_review_status: Mapped[str] = mapped_column(String(32), default="not_started")
    security_review_date: Mapped[date | None] = mapped_column(Date)
    open_security_findings: Mapped[int] = mapped_column(default=0)
    data_processing_terms: Mapped[str | None] = mapped_column(Text)
    subprocessors: Mapped[list[dict]] = mapped_column(JSONB, default=list)
    hosting_locations: Mapped[list[str]] = mapped_column(ARRAY(String(64)), default=list)
    renewal_date: Mapped[date | None] = mapped_column(Date)
    spend_band: Mapped[str | None] = mapped_column(String(32))
    performance_notes: Mapped[str | None] = mapped_column(Text)
    assessment_expired: Mapped[bool] = mapped_column(Boolean, default=False)

    counterparty: Mapped[Counterparty] = relationship(back_populates="vendor")
