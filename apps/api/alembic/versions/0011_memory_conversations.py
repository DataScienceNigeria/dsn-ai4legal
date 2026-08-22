"""Saved conversations for Ask memory, M10.

Answers were being produced and thrown away. These tables keep the thread, so a
question asked in March can be reopened, read with its citations intact and
traced back to the AI interaction that produced it.

A conversation is personal. The policy is narrower than the usual entity scope:
the row also has to belong to the caller, because retrieval assembled it under
that person's access and nobody else's.

Revision ID: 0011
Revises: 0010
"""

from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision: str = "0011"
down_revision: str | None = "0010"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "ai_conversation",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column("entity", sa.String(3), nullable=False, index=True),
        sa.Column("title", sa.String(200), nullable=False),
        sa.Column(
            "owner_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("app_user.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "matter_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("matter.id", ondelete="SET NULL"),
        ),
        sa.Column("last_message_at", sa.DateTime(timezone=True), index=True),
        sa.Column("message_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("archived", sa.Boolean(), nullable=False, server_default=sa.false(), index=True),
    )
    op.create_index(
        "ix_ai_conversation_owner_recent",
        "ai_conversation",
        ["owner_id", "entity", sa.text("last_message_at DESC")],
    )

    op.create_table(
        "ai_conversation_turn",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "conversation_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("ai_conversation.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("sequence", sa.Integer(), nullable=False),
        sa.Column("question", sa.Text(), nullable=False),
        sa.Column("answer", postgresql.JSONB(), nullable=False, server_default="{}"),
        sa.Column("interaction_id", sa.String(64)),
        sa.Column("refused", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.UniqueConstraint("conversation_id", "sequence", name="uq_ai_conversation_turn_sequence"),
    )
    op.create_index(
        "ix_ai_conversation_turn_thread",
        "ai_conversation_turn",
        ["conversation_id", "sequence"],
    )

    op.execute("GRANT SELECT, INSERT, UPDATE, DELETE ON ai_conversation TO dsnlai_app")
    op.execute("GRANT SELECT, INSERT, UPDATE, DELETE ON ai_conversation_turn TO dsnlai_app")

    op.execute("ALTER TABLE ai_conversation ENABLE ROW LEVEL SECURITY")
    op.execute("ALTER TABLE ai_conversation FORCE ROW LEVEL SECURITY")
    op.execute(
        """
        CREATE POLICY ai_conversation_owner ON ai_conversation
        USING (
            dsnlai_bypass()
            OR (entity = ANY (dsnlai_entities()) AND owner_id = dsnlai_current_user())
        )
        WITH CHECK (
            dsnlai_bypass()
            OR (entity = ANY (dsnlai_entities()) AND owner_id = dsnlai_current_user())
        )
        """
    )

    # The turn carries no entity and no owner of its own. It reaches both
    # through its parent, and the subquery is itself filtered by the policy
    # above, so a turn is reachable exactly when its conversation is. Nothing
    # here refers back to the turn table, so there is no recursion to break.
    op.execute("ALTER TABLE ai_conversation_turn ENABLE ROW LEVEL SECURITY")
    op.execute("ALTER TABLE ai_conversation_turn FORCE ROW LEVEL SECURITY")
    op.execute(
        """
        CREATE POLICY ai_conversation_turn_parent ON ai_conversation_turn
        USING (
            dsnlai_bypass()
            OR EXISTS (SELECT 1 FROM ai_conversation c WHERE c.id = conversation_id)
        )
        WITH CHECK (
            dsnlai_bypass()
            OR EXISTS (SELECT 1 FROM ai_conversation c WHERE c.id = conversation_id)
        )
        """
    )


def downgrade() -> None:
    op.execute("DROP POLICY IF EXISTS ai_conversation_turn_parent ON ai_conversation_turn")
    op.execute("DROP POLICY IF EXISTS ai_conversation_owner ON ai_conversation")
    op.drop_table("ai_conversation_turn")
    op.drop_table("ai_conversation")
