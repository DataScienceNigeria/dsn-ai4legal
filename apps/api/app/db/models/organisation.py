"""Organisation and user records, PRD section 9.1."""

import uuid
from datetime import datetime

from sqlalchemy import Boolean, DateTime, ForeignKey, Integer, String, Text, UniqueConstraint
from sqlalchemy.dialects.postgresql import ARRAY, JSONB
from sqlalchemy.dialects.postgresql import UUID as PgUUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base, Timestamped, UUIDPrimaryKey


class Organisation(UUIDPrimaryKey, Timestamped, Base):
    """Parent of every other record. Entity code is DSN or EAI."""

    __tablename__ = "organisation"

    entity_code: Mapped[str] = mapped_column(String(3), unique=True, nullable=False)
    legal_name: Mapped[str] = mapped_column(String(255), nullable=False)
    registration_number: Mapped[str | None] = mapped_column(String(64))
    default_jurisdiction: Mapped[str] = mapped_column(String(64), default="Nigeria")
    branding: Mapped[dict] = mapped_column(JSONB, default=dict)
    retention_profile: Mapped[str] = mapped_column(String(64), default="standard")

    # The particulars an agreement names us by. Held here rather than typed
    # into each document, because two people typing the registered address
    # from memory is two versions of it in the archive, and the one that ends
    # up in an executed contract is whichever was typed last.
    trading_name: Mapped[str | None] = mapped_column(String(255))
    registered_address: Mapped[str | None] = mapped_column(Text)
    tax_identification_number: Mapped[str | None] = mapped_column(String(64))
    contact_email: Mapped[str | None] = mapped_column(String(320))
    contact_phone: Mapped[str | None] = mapped_column(String(64))
    website: Mapped[str | None] = mapped_column(String(255))
    #: Who signs for this entity by default, and in what capacity. Named on the
    #: document rather than assumed from whoever pressed the button.
    signatory_name: Mapped[str | None] = mapped_column(String(255))
    signatory_title: Mapped[str | None] = mapped_column(String(128))

    users: Mapped[list["UserEntity"]] = relationship(back_populates="organisation")

class User(UUIDPrimaryKey, Timestamped, Base):
    """Provisioned from Entra ID or Google Workspace through Keycloak (M15)."""

    __tablename__ = "app_user"

    subject: Mapped[str] = mapped_column(String(255), unique=True, nullable=False)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    work_email: Mapped[str] = mapped_column(String(320), unique=True, nullable=False)
    password_hash: Mapped[str | None] = mapped_column(String(255))
    roles: Mapped[list[str]] = mapped_column(ARRAY(String(32)), default=list)
    specialisms: Mapped[list[str]] = mapped_column(ARRAY(String(64)), default=list)
    delegate_id: Mapped[uuid.UUID | None] = mapped_column(
        PgUUID(as_uuid=True), ForeignKey("app_user.id", ondelete="SET NULL")
    )
    workload: Mapped[int] = mapped_column(default=0)
    workload_ceiling: Mapped[int] = mapped_column(default=10)
    active: Mapped[bool] = mapped_column(Boolean, default=True)
    last_login: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    notification_channel: Mapped[str] = mapped_column(String(32), default="email")

    # Multi-factor authentication. The secret is held here because the
    # platform is the verifier in local mode; in OIDC mode the provider owns
    # the factor and these stay empty.
    mfa_secret: Mapped[str | None] = mapped_column(String(64))
    mfa_enrolled_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    mfa_recovery_codes: Mapped[list[str]] = mapped_column(ARRAY(String(128)), default=list)
    mfa_last_used_counter: Mapped[int | None] = mapped_column(Integer)

    # SCIM provisioning. external_id is what the directory calls this person.
    external_id: Mapped[str | None] = mapped_column(String(255), index=True)
    provisioned_by: Mapped[str | None] = mapped_column(String(32))
    deprovisioned_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    @property
    def mfa_enrolled(self) -> bool:
        return bool(self.mfa_secret and self.mfa_enrolled_at)

    entities: Mapped[list["UserEntity"]] = relationship(
        back_populates="user", cascade="all, delete-orphan"
    )

    @property
    def initials(self) -> str:
        parts = [p for p in self.name.split() if p]
        return "".join(p[0].upper() for p in parts[:2]) or "?"

    @property
    def entity_codes(self) -> list[str]:
        return [m.entity_code for m in self.entities]

class UserEntity(UUIDPrimaryKey, Base):
    """Entity membership. A user's reach is the intersection of role and entity."""

    __tablename__ = "user_entity"
    __table_args__ = (UniqueConstraint("user_id", "entity_code"),)

    user_id: Mapped[uuid.UUID] = mapped_column(
        PgUUID(as_uuid=True), ForeignKey("app_user.id", ondelete="CASCADE"), nullable=False
    )
    entity_code: Mapped[str] = mapped_column(
        String(3), ForeignKey("organisation.entity_code", ondelete="CASCADE"), nullable=False
    )

    user: Mapped[User] = relationship(back_populates="entities")
    organisation: Mapped[Organisation] = relationship(back_populates="users")

class ConfigSetting(UUIDPrimaryKey, Timestamped, Base):
    """Configuration without deployment, PRD LOP-M15-US-06.

    Request types, mandatory fields, tier rules, approval chains, SLA targets,
    reminder schedules, playbooks, prompts, model routes and retention
    schedules all live here, versioned, and every change is audited.
    """

    __tablename__ = "config_setting"
    __table_args__ = (UniqueConstraint("area", "key", "version"),)

    area: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    key: Mapped[str] = mapped_column(String(128), nullable=False)
    version: Mapped[int] = mapped_column(default=1, nullable=False)
    value: Mapped[dict] = mapped_column(JSONB, nullable=False)
    description: Mapped[str | None] = mapped_column(Text)
    active: Mapped[bool] = mapped_column(Boolean, default=True)
    changed_by: Mapped[uuid.UUID | None] = mapped_column(
        PgUUID(as_uuid=True), ForeignKey("app_user.id", ondelete="SET NULL")
    )
