"""A template version keeps the Word document it was imported from.

Templates were structured blocks only, which is what generation needs but not
what anyone can read. Keeping the source document beside the blocks lets a
version be opened, read and edited as the document it is, while generation
still runs off the blocks.

Revision ID: 0013
Revises: 0012
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "0013"
down_revision: str | None = "0012"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column("template_version", sa.Column("source_key", sa.String(512)))
    op.add_column("template_version", sa.Column("source_hash", sa.String(64)))
    op.add_column(
        "template_version",
        sa.Column("import_id", sa.dialects.postgresql.UUID(as_uuid=True)),
    )
    op.create_foreign_key(
        "fk_template_version_import_id_template_import",
        "template_version",
        "template_import",
        ["import_id"],
        ["id"],
        ondelete="SET NULL",
    )


def downgrade() -> None:
    op.drop_constraint(
        "fk_template_version_import_id_template_import", "template_version", type_="foreignkey"
    )
    op.drop_column("template_version", "import_id")
    op.drop_column("template_version", "source_hash")
    op.drop_column("template_version", "source_key")
