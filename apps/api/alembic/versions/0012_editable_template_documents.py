"""A template import is a document people edit, not only a proposal to read.

The uploaded file stays exactly as it arrived: provenance is the reason the
import records a hash at all, and an edit that overwrote the original would
leave nothing to compare a later version against. Edits land in a working copy
beside it, and the revision counter says how many times it has been saved.

Revision ID: 0012
Revises: 0011
"""

from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision: str = "0012"
down_revision: str | None = "0011"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column("template_import", sa.Column("working_key", sa.String(512)))
    op.add_column("template_import", sa.Column("working_hash", sa.String(64)))
    op.add_column(
        "template_import",
        sa.Column("revision", sa.Integer(), nullable=False, server_default="0"),
    )
    op.add_column(
        "template_import",
        sa.Column(
            "edited_by_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("app_user.id", ondelete="SET NULL"),
        ),
    )
    op.add_column("template_import", sa.Column("edited_at", sa.DateTime(timezone=True)))


def downgrade() -> None:
    op.drop_column("template_import", "edited_at")
    op.drop_column("template_import", "edited_by_id")
    op.drop_column("template_import", "revision")
    op.drop_column("template_import", "working_hash")
    op.drop_column("template_import", "working_key")
