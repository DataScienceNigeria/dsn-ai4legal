"""A message keeps the state its mailbox gives it.

The connector used to read unread mail only and mark it read, which hid every
message somebody had already opened and changed the mailbox Legal works from.
It now reads all of it, so the platform records what the mailbox says about
each message rather than altering it: read or not, its labels or categories,
and the conversation it belongs to.

The body is split into what the sender wrote and the history quoted beneath
it, and the text as received is kept alongside, because a cleaned body is a
reading aid and the original is the record.

Revision ID: 0035
Revises: 0034
"""

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "0035"
down_revision = "0034"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("communication", sa.Column("body_quoted", sa.Text()))
    op.add_column("communication", sa.Column("body_original", sa.Text()))
    op.add_column("communication", sa.Column("thread_id", sa.String(255)))
    op.add_column("communication", sa.Column("mailbox_read", sa.Boolean()))
    op.add_column(
        "communication",
        sa.Column(
            "mailbox_labels",
            postgresql.JSONB(),
            nullable=False,
            server_default=sa.text("'[]'::jsonb"),
        ),
    )
    op.add_column(
        "communication", sa.Column("mailbox_seen_at", sa.DateTime(timezone=True))
    )
    op.create_index("ix_communication_thread_id", "communication", ["thread_id"])
    op.create_index("ix_communication_mailbox_read", "communication", ["mailbox_read"])


def downgrade() -> None:
    op.drop_index("ix_communication_mailbox_read", table_name="communication")
    op.drop_index("ix_communication_thread_id", table_name="communication")
    for column in (
        "mailbox_seen_at",
        "mailbox_labels",
        "mailbox_read",
        "thread_id",
        "body_original",
        "body_quoted",
    ):
        op.drop_column("communication", column)
