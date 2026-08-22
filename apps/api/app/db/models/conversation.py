"""Saved conversations with memory, M10.

An answer that cannot be found again is a demonstration rather than a working
record. These two tables hold the question, the answer that was given and the
interaction that produced it, so a position someone relied on last month can be
opened, read and traced back to the AI interaction log.

A conversation belongs to one person in one entity. Nothing here is shared:
retrieval already filtered by the asker's own access, so a transcript is only
safe in front of the person it was assembled for.
"""

import uuid
from datetime import datetime

from sqlalchemy import Boolean, DateTime, ForeignKey, Integer, String, Text, UniqueConstraint
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.dialects.postgresql import UUID as PgUUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base, EntityScoped, Timestamped, UUIDPrimaryKey


class Conversation(UUIDPrimaryKey, Timestamped, EntityScoped, Base):
    """One thread of questions and answers."""

    __tablename__ = "ai_conversation"

    title: Mapped[str] = mapped_column(String(200), nullable=False)
    owner_id: Mapped[uuid.UUID] = mapped_column(
        PgUUID(as_uuid=True), ForeignKey("app_user.id", ondelete="CASCADE"), nullable=False
    )
    matter_id: Mapped[uuid.UUID | None] = mapped_column(
        PgUUID(as_uuid=True), ForeignKey("matter.id", ondelete="SET NULL")
    )
    last_message_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), index=True)
    message_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    archived: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False, index=True)

    turns: Mapped[list["ConversationTurn"]] = relationship(
        back_populates="conversation",
        cascade="all, delete-orphan",
        order_by="ConversationTurn.sequence",
    )


class ConversationTurn(UUIDPrimaryKey, Timestamped, Base):
    """One question and the answer it received.

    The answer is stored as the envelope the interface was given rather than as
    prose, so the citations, the sources and the count of suppressed statements
    survive alongside the text. Re-rendering an old answer therefore shows what
    was actually shown at the time.
    """

    __tablename__ = "ai_conversation_turn"
    __table_args__ = (
        UniqueConstraint("conversation_id", "sequence", name="uq_ai_conversation_turn_sequence"),
    )

    conversation_id: Mapped[uuid.UUID] = mapped_column(
        PgUUID(as_uuid=True), ForeignKey("ai_conversation.id", ondelete="CASCADE"), nullable=False
    )
    sequence: Mapped[int] = mapped_column(Integer, nullable=False)
    question: Mapped[str] = mapped_column(Text, nullable=False)
    answer: Mapped[dict] = mapped_column(JSONB, default=dict, nullable=False)
    interaction_id: Mapped[str | None] = mapped_column(String(64))
    refused: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)

    conversation: Mapped[Conversation] = relationship(back_populates="turns")
