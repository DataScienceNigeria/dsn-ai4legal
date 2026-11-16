"""Template and clause library, M03.

The single source of truth for house position. Only the approved clause library
may be presented anywhere in the platform as house position.
"""

import uuid
from datetime import date, datetime

from sqlalchemy import (
    Boolean,
    Date,
    DateTime,
    ForeignKey,
    Integer,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.dialects.postgresql import ARRAY, JSONB
from sqlalchemy.dialects.postgresql import UUID as PgUUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base, Timestamped, UUIDPrimaryKey
from app.domain.enums import VersionStatus


class Clause(UUIDPrimaryKey, Timestamped, Base):
    """A clause category with an owner. Versions hold the text."""

    __tablename__ = "clause"

    category: Mapped[str] = mapped_column(String(16), unique=True, nullable=False, index=True)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    owner_id: Mapped[uuid.UUID | None] = mapped_column(
        PgUUID(as_uuid=True), ForeignKey("app_user.id", ondelete="SET NULL")
    )
    entity_applicability: Mapped[list[str]] = mapped_column(
        ARRAY(String(3)), default=lambda: ["DSN", "EAI"]
    )
    jurisdiction: Mapped[str] = mapped_column(String(64), default="Nigeria")
    language: Mapped[str] = mapped_column(String(8), default="en")
    required_for_types: Mapped[list[str]] = mapped_column(JSONB, default=list)
    family: Mapped[str | None] = mapped_column(String(64), index=True)

    versions: Mapped[list["ClauseVersion"]] = relationship(
        back_populates="clause", cascade="all, delete-orphan", order_by="ClauseVersion.major"
    )
    variants: Mapped[list["ClauseVariant"]] = relationship(
        back_populates="clause", cascade="all, delete-orphan", order_by="ClauseVariant.code"
    )


class ClauseVariant(UUIDPrimaryKey, Timestamped, Base):
    """One wording of a clause for an entity, agreement type and role.

    The legal team's library holds the same clause in several forms: the
    assignment clause DSN offers on a general service agreement is not the one
    EqualyzAI offers on an AI compute agreement. Each form is its own line of
    versions, identified by the legal team's own ``CLV`` code, so a change to
    one never supersedes another.
    """

    __tablename__ = "clause_variant"

    clause_id: Mapped[uuid.UUID] = mapped_column(
        PgUUID(as_uuid=True),
        ForeignKey("clause.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    code: Mapped[str] = mapped_column(String(24), unique=True, nullable=False, index=True)
    title: Mapped[str] = mapped_column(String(255), nullable=False)
    entity_scope: Mapped[str] = mapped_column(String(4), nullable=False, index=True)
    agreement_type: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    subtype: Mapped[str] = mapped_column(String(128), nullable=False, default="")
    transaction_role: Mapped[str] = mapped_column(String(64), nullable=False)
    source_url: Mapped[str | None] = mapped_column(Text)

    clause: Mapped[Clause] = relationship(back_populates="variants")
    versions: Mapped[list["ClauseVersion"]] = relationship(
        back_populates="variant", order_by="ClauseVersion.major"
    )

    @property
    def entities(self) -> list[str]:
        return ["DSN", "EAI"] if self.entity_scope == "BOTH" else [self.entity_scope]

class ClauseVersion(UUIDPrimaryKey, Timestamped, Base):
    """House position, ranked fallbacks and the unacceptable position.

    Fallbacks carry the authority level required to concede them
    (PRD LOP-M03-US-02 and section 14.3).
    """

    __tablename__ = "clause_version"
    __table_args__ = (
        UniqueConstraint(
            "clause_id",
            "variant_id",
            "major",
            "minor",
            name="uq_clause_version_variant_major_minor",
            postgresql_nulls_not_distinct=True,
        ),
    )

    clause_id: Mapped[uuid.UUID] = mapped_column(
        PgUUID(as_uuid=True), ForeignKey("clause.id", ondelete="CASCADE"), nullable=False
    )
    variant_id: Mapped[uuid.UUID | None] = mapped_column(
        PgUUID(as_uuid=True), ForeignKey("clause_variant.id", ondelete="CASCADE"), index=True
    )
    reference: Mapped[str] = mapped_column(String(32), unique=True, nullable=False, index=True)
    major: Mapped[int] = mapped_column(Integer, default=1)
    minor: Mapped[int] = mapped_column(Integer, default=0)
    status: Mapped[str] = mapped_column(String(16), default=VersionStatus.DRAFT.value, index=True)
    house_position: Mapped[str] = mapped_column(Text, nullable=False)
    standard_position: Mapped[str | None] = mapped_column(Text)
    fallbacks: Mapped[list[dict]] = mapped_column(JSONB, default=list)
    unacceptable_position: Mapped[str | None] = mapped_column(Text)
    usage_conditions: Mapped[str | None] = mapped_column(Text)
    risk_notes: Mapped[str | None] = mapped_column(Text)
    approved_by_id: Mapped[uuid.UUID | None] = mapped_column(
        PgUUID(as_uuid=True), ForeignKey("app_user.id", ondelete="SET NULL")
    )
    approval_date: Mapped[date | None] = mapped_column(Date)
    effective_date: Mapped[date | None] = mapped_column(Date)
    review_date: Mapped[date | None] = mapped_column(Date, index=True)
    supersedes_id: Mapped[uuid.UUID | None] = mapped_column(
        PgUUID(as_uuid=True), ForeignKey("clause_version.id", ondelete="SET NULL")
    )
    provenance: Mapped[str | None] = mapped_column(Text)
    library_import_id: Mapped[uuid.UUID | None] = mapped_column(
        PgUUID(as_uuid=True), ForeignKey("library_import.id", ondelete="SET NULL")
    )

    clause: Mapped[Clause] = relationship(back_populates="versions")
    variant: Mapped[ClauseVariant | None] = relationship(back_populates="versions")

class Template(UUIDPrimaryKey, Timestamped, Base):
    """An agreement template. Only an approved, effective version may generate."""

    __tablename__ = "template"

    code: Mapped[str] = mapped_column(String(32), unique=True, nullable=False, index=True)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    agreement_type: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    subtype: Mapped[str] = mapped_column(String(128), nullable=False, default="")
    owner_id: Mapped[uuid.UUID | None] = mapped_column(
        PgUUID(as_uuid=True), ForeignKey("app_user.id", ondelete="SET NULL")
    )
    entity_applicability: Mapped[list[str]] = mapped_column(
        ARRAY(String(3)), default=lambda: ["DSN", "EAI"]
    )
    jurisdiction: Mapped[str] = mapped_column(String(64), default="Nigeria")
    language: Mapped[str] = mapped_column(String(8), default="en")

    versions: Mapped[list["TemplateVersion"]] = relationship(
        back_populates="template", cascade="all, delete-orphan"
    )

class TemplateVersion(UUIDPrimaryKey, Timestamped, Base):
    """A versioned, approved template with declared merge variables.

    Generation fails safely and reports the missing variable rather than
    emitting a placeholder into a document (PRD LOP-M03-US-04).
    """

    __tablename__ = "template_version"
    __table_args__ = (UniqueConstraint("template_id", "major", "minor"),)

    template_id: Mapped[uuid.UUID] = mapped_column(
        PgUUID(as_uuid=True), ForeignKey("template.id", ondelete="CASCADE"), nullable=False
    )
    reference: Mapped[str] = mapped_column(String(40), unique=True, nullable=False, index=True)
    major: Mapped[int] = mapped_column(Integer, default=1)
    minor: Mapped[int] = mapped_column(Integer, default=0)
    status: Mapped[str] = mapped_column(String(16), default=VersionStatus.DRAFT.value, index=True)
    body: Mapped[list[dict]] = mapped_column(JSONB, default=list)
    variables: Mapped[list[dict]] = mapped_column(JSONB, default=list)
    clause_references: Mapped[list[str]] = mapped_column(JSONB, default=list)
    approved_by_id: Mapped[uuid.UUID | None] = mapped_column(
        PgUUID(as_uuid=True), ForeignKey("app_user.id", ondelete="SET NULL")
    )
    approval_date: Mapped[date | None] = mapped_column(Date)
    effective_date: Mapped[date | None] = mapped_column(Date)
    review_date: Mapped[date | None] = mapped_column(Date, index=True)
    supersedes_id: Mapped[uuid.UUID | None] = mapped_column(
        PgUUID(as_uuid=True), ForeignKey("template_version.id", ondelete="SET NULL")
    )
    change_summary: Mapped[str | None] = mapped_column(Text)
    provenance: Mapped[str | None] = mapped_column(Text)

    # The Word document this version is, kept beside the blocks generation
    # runs off. A version imported from paper has one; a version authored as
    # blocks does not, and is rendered from them on demand instead.
    source_key: Mapped[str | None] = mapped_column(String(512))
    source_hash: Mapped[str | None] = mapped_column(String(64))
    import_id: Mapped[uuid.UUID | None] = mapped_column(
        PgUUID(as_uuid=True), ForeignKey("template_import.id", ondelete="SET NULL")
    )

    template: Mapped[Template] = relationship(back_populates="versions")

class Playbook(UUIDPrimaryKey, Timestamped, Base):
    """Per agreement type, the clauses we require and how far we will move.

    A playbook may be one entity's and one sub-type's: DSN's general service
    agreement and its AI compute agreement require different clauses. With no
    entity it serves both, and with no sub-type it serves the whole type.
    """

    __tablename__ = "playbook"
    __table_args__ = (
        UniqueConstraint(
            "agreement_type",
            "entity",
            "subtype",
            name="uq_playbook_type_entity_subtype",
            postgresql_nulls_not_distinct=True,
        ),
    )

    agreement_type: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    entity: Mapped[str | None] = mapped_column(String(3), index=True)
    subtype: Mapped[str] = mapped_column(String(128), nullable=False, default="")
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    version: Mapped[int] = mapped_column(Integer, default=1)
    required_clauses: Mapped[list[dict]] = mapped_column(JSONB, default=list)
    active: Mapped[bool] = mapped_column(Boolean, default=True)
    library_import_id: Mapped[uuid.UUID | None] = mapped_column(
        PgUUID(as_uuid=True), ForeignKey("library_import.id", ondelete="SET NULL")
    )


class ClausePrecedent(UUIDPrimaryKey, Timestamped, Base):
    """Wording the legal team has seen, which is not house position.

    Reference wording comes from agreements already signed, so it shows what
    has been accepted before. Prohibited wording is what must never be
    accepted. Neither is ever offered as what we propose.
    """

    __tablename__ = "clause_precedent"

    clause_id: Mapped[uuid.UUID] = mapped_column(
        PgUUID(as_uuid=True),
        ForeignKey("clause.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    fingerprint: Mapped[str] = mapped_column(String(64), unique=True, nullable=False)
    reference: Mapped[str | None] = mapped_column(String(24), index=True)
    kind: Mapped[str] = mapped_column(String(16), nullable=False, index=True)
    entity_scope: Mapped[str] = mapped_column(String(4), nullable=False, index=True)
    agreement_type: Mapped[str] = mapped_column(String(64), nullable=False)
    subtype: Mapped[str] = mapped_column(String(128), nullable=False, default="")
    transaction_role: Mapped[str] = mapped_column(String(64), nullable=False)
    family: Mapped[str] = mapped_column(String(64), nullable=False)
    title: Mapped[str] = mapped_column(String(255), nullable=False)
    text: Mapped[str] = mapped_column(Text, nullable=False)
    source_url: Mapped[str | None] = mapped_column(Text)
    library_import_id: Mapped[uuid.UUID | None] = mapped_column(
        PgUUID(as_uuid=True), ForeignKey("library_import.id", ondelete="SET NULL")
    )
    source_row: Mapped[int | None] = mapped_column(Integer)
    standard_position: Mapped[str | None] = mapped_column(Text)
    fallbacks: Mapped[list[dict]] = mapped_column(JSONB, default=list)
    unacceptable_position: Mapped[str | None] = mapped_column(Text)
    playbook_row: Mapped[int | None] = mapped_column(Integer)

    clause: Mapped[Clause] = relationship()


class LibraryImport(UUIDPrimaryKey, Timestamped, Base):
    """The legal team's playbook and clause library workbook, checked first.

    Uploading only checks. The record holds what the workbook would do and
    every problem found, row by row, and nothing reaches the library until
    someone applies it. Applying writes drafts, never approved versions.
    """

    __tablename__ = "library_import"

    filename: Mapped[str] = mapped_column(String(255), nullable=False)
    storage_key: Mapped[str | None] = mapped_column(String(512))
    source_hash: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    uploaded_by_id: Mapped[uuid.UUID | None] = mapped_column(
        PgUUID(as_uuid=True), ForeignKey("app_user.id", ondelete="SET NULL")
    )
    status: Mapped[str] = mapped_column(String(16), default="checked", nullable=False, index=True)
    summary: Mapped[dict] = mapped_column(JSONB, default=dict)
    issues: Mapped[list[dict]] = mapped_column(JSONB, default=list)
    plan: Mapped[dict] = mapped_column(JSONB, default=dict)
    applied_by_id: Mapped[uuid.UUID | None] = mapped_column(
        PgUUID(as_uuid=True), ForeignKey("app_user.id", ondelete="SET NULL")
    )
    applied_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

class TemplateImport(UUIDPrimaryKey, Timestamped, Base):
    """Word import with a proposed clause breakdown, LOP-M03-US-07.

    Nothing imported becomes approved without explicit human approval. The
    import holds candidates and provenance until a clause owner accepts them,
    so an old template cannot smuggle an unapproved position into the library.
    """

    __tablename__ = "template_import"

    filename: Mapped[str] = mapped_column(String(255), nullable=False)
    entity: Mapped[str] = mapped_column(String(3), nullable=False, index=True)
    agreement_type: Mapped[str | None] = mapped_column(String(64))
    storage_key: Mapped[str | None] = mapped_column(String(512))
    source_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    uploaded_by_id: Mapped[uuid.UUID | None] = mapped_column(
        PgUUID(as_uuid=True), ForeignKey("app_user.id", ondelete="SET NULL")
    )
    status: Mapped[str] = mapped_column(String(16), default="proposed", index=True)

    # The uploaded file is never written over. Editing produces a working copy
    # beside it, so the hash recorded at import still refers to what arrived.
    working_key: Mapped[str | None] = mapped_column(String(512))
    working_hash: Mapped[str | None] = mapped_column(String(64))
    revision: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    edited_by_id: Mapped[uuid.UUID | None] = mapped_column(
        PgUUID(as_uuid=True), ForeignKey("app_user.id", ondelete="SET NULL")
    )
    edited_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    proposed_clauses: Mapped[list[dict]] = mapped_column(JSONB, default=list)
    provenance: Mapped[dict] = mapped_column(JSONB, default=dict)
    accepted_count: Mapped[int] = mapped_column(Integer, default=0)
    decided_by_id: Mapped[uuid.UUID | None] = mapped_column(
        PgUUID(as_uuid=True), ForeignKey("app_user.id", ondelete="SET NULL")
    )
