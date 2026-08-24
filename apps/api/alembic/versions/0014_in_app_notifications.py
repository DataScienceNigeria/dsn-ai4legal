"""In-app notifications.

The events that most need someone's attention, a matter assigned, an approval
waiting, a finding raised, a request returned, were announced only through the
outbox, which carries mail to an external connector the platform may not be
cleared or configured to use. Nothing reached the person inside the product.

A notification is personal, so the policy narrows past the usual entity scope
to the recipient. Someone else's queue is not readable simply because it sits
in the same organisation.

Revision ID: 0014
Revises: 0013
"""

from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision: str = "0014"
down_revision: str | None = "0013"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "notification",
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
            "recipient_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("app_user.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("entity", sa.String(3), nullable=False),
        sa.Column("kind", sa.String(32), nullable=False),
        sa.Column("title", sa.String(255), nullable=False),
        sa.Column("body", sa.Text()),
        sa.Column("href", sa.String(512)),
        sa.Column("reference", sa.String(64)),
        sa.Column(
            "matter_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("matter.id", ondelete="CASCADE"),
        ),
        sa.Column("read_at", sa.DateTime(timezone=True)),
    )

    # The bell asks one question on every page load: what is unread for me, in
    # this organisation, newest first. This index is that question.
    op.create_index(
        "ix_notification_recipient_recent",
        "notification",
        ["recipient_id", "entity", sa.text("created_at DESC")],
    )
    op.create_index("ix_notification_kind", "notification", ["kind"])
    op.create_index("ix_notification_read_at", "notification", ["read_at"])

    op.execute("GRANT SELECT, INSERT, UPDATE, DELETE ON notification TO dsnlai_app")

    op.execute("ALTER TABLE notification ENABLE ROW LEVEL SECURITY")
    op.execute("ALTER TABLE notification FORCE ROW LEVEL SECURITY")
    op.execute(
        """
        CREATE POLICY notification_recipient ON notification
        USING (
            dsnlai_bypass()
            OR (entity = ANY (dsnlai_entities()) AND recipient_id = dsnlai_current_user())
        )
        WITH CHECK (
            dsnlai_bypass()
            OR entity = ANY (dsnlai_entities())
        )
        """
    )


def downgrade() -> None:
    op.execute("DROP POLICY IF EXISTS notification_recipient ON notification")
    op.drop_index("ix_notification_read_at", table_name="notification")
    op.drop_index("ix_notification_kind", table_name="notification")
    op.drop_index("ix_notification_recipient_recent", table_name="notification")
    op.drop_table("notification")
