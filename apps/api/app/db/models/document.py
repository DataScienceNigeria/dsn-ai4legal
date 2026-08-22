"""Documents, M04 and M06.

Every generated document records the template and clause versions used, the
exact input values, the generating user, the timestamp and a content hash.
Regeneration with the same inputs produces an identical file.
"""

import uuid
from datetime import datetime

from sqlalchemy import Boolean, DateTime, ForeignKey, Integer, String, Text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.dialects.postgresql import UUID as PgUUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base, EntityScoped, Timestamped, UUIDPrimaryKey
from app.domain.enums import DataClass, DocumentType


class Document(UUIDPrimaryKey, Timestamped, EntityScoped, Base):
    __tablename__ = "document"

    matter_id: Mapped[uuid.UUID | None] = mapped_column(
        PgUUID(as_uuid=True), ForeignKey("matter.id", ondelete="CASCADE"), index=True
    )
    contract_id: Mapped[uuid.UUID | None] = mapped_column(
        PgUUID(as_uuid=True), ForeignKey("contract.id", ondelete="SET NULL")
    )
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    document_type: Mapped[str] = mapped_column(
        String(24), default=DocumentType.DRAFT.value, nullable=False
    )
    version: Mapped[int] = mapped_column(Integer, default=1)
    template_version_ref: Mapped[str | None] = mapped_column(String(40))
    clause_versions: Mapped[list[str]] = mapped_column(JSONB, default=list)
    input_values: Mapped[dict] = mapped_column(JSONB, default=dict)
    blocks: Mapped[list[dict]] = mapped_column(JSONB, default=list)
    content_hash: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    storage_key: Mapped[str | None] = mapped_column(String(512))
    classification: Mapped[str] = mapped_column(String(16), default=DataClass.CONFIDENTIAL.value)
    generated_by_id: Mapped[uuid.UUID | None] = mapped_column(
        PgUUID(as_uuid=True), ForeignKey("app_user.id", ondelete="SET NULL")
    )
    generated_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    immutable: Mapped[bool] = mapped_column(Boolean, default=False)
    supersedes_id: Mapped[uuid.UUID | None] = mapped_column(
        PgUUID(as_uuid=True), ForeignKey("document.id", ondelete="SET NULL")
    )
    novel_clause_count: Mapped[int] = mapped_column(Integer, default=0)
    open_items: Mapped[list[str]] = mapped_column(JSONB, default=list)
    style_report: Mapped[list[dict]] = mapped_column(JSONB, default=list)
    consistency_checks: Mapped[list[dict]] = mapped_column(JSONB, default=list)

class ReviewFinding(UUIDPrimaryKey, Timestamped, Base):
    """A deviation between counterparty paper and the playbook, M06."""

    __tablename__ = "review_finding"

    matter_id: Mapped[uuid.UUID] = mapped_column(
        PgUUID(as_uuid=True),
        ForeignKey("matter.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    document_id: Mapped[uuid.UUID | None] = mapped_column(
        PgUUID(as_uuid=True), ForeignKey("document.id", ondelete="SET NULL")
    )
    sequence: Mapped[int] = mapped_column(Integer, default=1)
    title: Mapped[str] = mapped_column(String(255), nullable=False)
    their_reference: Mapped[str | None] = mapped_column(String(64))
    clause_absent: Mapped[bool] = mapped_column(Boolean, default=False)
    severity: Mapped[str] = mapped_column(String(16), nullable=False, index=True)
    clause_category: Mapped[str | None] = mapped_column(String(16))
    clause_version_ref: Mapped[str | None] = mapped_column(String(32))
    their_text: Mapped[str | None] = mapped_column(Text)
    house_position: Mapped[str | None] = mapped_column(Text)
    suggested_redline: Mapped[str | None] = mapped_column(Text)
    required_authority: Mapped[str] = mapped_column(String(24), default="fallback_1")
    matches_preapproved_fallback: Mapped[bool] = mapped_column(Boolean, default=False)
    decision: Mapped[str] = mapped_column(String(16), default="pending", index=True)
    decided_by_id: Mapped[uuid.UUID | None] = mapped_column(
        PgUUID(as_uuid=True), ForeignKey("app_user.id", ondelete="SET NULL")
    )
    decided_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    clearance_rule: Mapped[str | None] = mapped_column(Text)
    edited_text: Mapped[str | None] = mapped_column(Text)
    interaction_id: Mapped[str | None] = mapped_column(String(64))

class Suggestion(UUIDPrimaryKey, Timestamped, Base):
    """A proposed change to a clause in a draft, M05 and M06.

    Every accepted change is attributed to the counsel, not to the model.
    """

    __tablename__ = "suggestion"

    document_id: Mapped[uuid.UUID] = mapped_column(
        PgUUID(as_uuid=True), ForeignKey("document.id", ondelete="CASCADE"), nullable=False
    )
    block_key: Mapped[str] = mapped_column(String(64), nullable=False)
    instruction: Mapped[str | None] = mapped_column(Text)
    original_text: Mapped[str] = mapped_column(Text, nullable=False)
    proposed_text: Mapped[str] = mapped_column(Text, nullable=False)
    rationale: Mapped[str | None] = mapped_column(Text)
    source_reference: Mapped[str | None] = mapped_column(String(64))
    novel: Mapped[bool] = mapped_column(Boolean, default=False)
    decision: Mapped[str] = mapped_column(String(16), default="pending")
    decided_by_id: Mapped[uuid.UUID | None] = mapped_column(
        PgUUID(as_uuid=True), ForeignKey("app_user.id", ondelete="SET NULL")
    )
    decided_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    interaction_id: Mapped[str | None] = mapped_column(String(64))

    document: Mapped[Document] = relationship()
