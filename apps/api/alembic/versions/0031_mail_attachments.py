"""Attachments that arrived on a message.

The mail connector delivered the subject, the body and the participants and
dropped every file, so an agreement sent as a .docx reached the platform as a
sentence saying somebody had sent one. The attachment table already holds files
that arrive on a request, scanned before storage and addressable afterwards,
which is the same thing being held; it gains a second nullable owner rather
than a second table, because a second table means a second scan path and a
second retention rule for no difference anybody can point at.

Revision ID: 0031
Revises: 0030
"""

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import UUID as PgUUID

revision = "0031"
down_revision = "0030"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "attachment",
        sa.Column("communication_id", PgUUID(as_uuid=True), nullable=True),
    )
    op.create_foreign_key(
        "fk_attachment_communication",
        "attachment",
        "communication",
        ["communication_id"],
        ["id"],
        ondelete="CASCADE",
    )
    op.create_index(
        "ix_attachment_communication_id", "attachment", ["communication_id"]
    )


def downgrade() -> None:
    op.drop_index("ix_attachment_communication_id", table_name="attachment")
    op.drop_constraint("fk_attachment_communication", "attachment", type_="foreignkey")
    op.drop_column("attachment", "communication_id")
