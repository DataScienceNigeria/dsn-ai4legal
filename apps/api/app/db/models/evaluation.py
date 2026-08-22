"""Golden sets and their cases, PRD section 16.1.

A gate that nothing measures is a declaration. These tables hold what the
measurement is taken against: a named, versioned set of cases per capability,
each with an input and the answer a competent person would give.
"""

import uuid

from sqlalchemy import Boolean, ForeignKey, Integer, String, Text, UniqueConstraint
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.dialects.postgresql import UUID as PgUUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base, Timestamped, UUIDPrimaryKey


class GoldenSet(UUIDPrimaryKey, Timestamped, Base):
    """One evaluation set for one capability.

    A set is versioned rather than edited, so a score recorded last quarter
    still names the cases it was measured against.
    """

    __tablename__ = "golden_set"
    __table_args__ = (UniqueConstraint("name", "version", name="uq_golden_set_name_version"),)

    name: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    version: Mapped[int] = mapped_column(Integer, default=1, nullable=False)
    capability_code: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    description: Mapped[str | None] = mapped_column(Text)
    owner_id: Mapped[uuid.UUID | None] = mapped_column(
        PgUUID(as_uuid=True), ForeignKey("app_user.id", ondelete="SET NULL")
    )
    active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False, index=True)

    cases: Mapped[list["GoldenCase"]] = relationship(
        back_populates="golden_set", cascade="all, delete-orphan"
    )


class GoldenCase(UUIDPrimaryKey, Timestamped, Base):
    """One case: what goes in, and what should come back.

    `expected` is shaped by the capability being measured. The scorer for that
    capability knows how to read it, and nothing else does.
    """

    __tablename__ = "golden_case"

    set_id: Mapped[uuid.UUID] = mapped_column(
        PgUUID(as_uuid=True), ForeignKey("golden_set.id", ondelete="CASCADE"), nullable=False
    )
    reference: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    prompt: Mapped[str] = mapped_column(Text, nullable=False)
    context: Mapped[list[dict]] = mapped_column(JSONB, default=list)
    expected: Mapped[dict] = mapped_column(JSONB, default=dict, nullable=False)
    notes: Mapped[str | None] = mapped_column(Text)
    source: Mapped[str | None] = mapped_column(String(255))
    active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)

    golden_set: Mapped[GoldenSet] = relationship(back_populates="cases")
