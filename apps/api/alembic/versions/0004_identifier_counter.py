"""Identifier counters.

Revision ID: 0004
Revises: 0003
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "0004"
down_revision: str | None = "0003"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "identifier_counter",
        sa.Column("scope", sa.String(length=64), primary_key=True),
        sa.Column("value", sa.Integer(), nullable=False, server_default="0"),
    )
    op.execute("GRANT SELECT, INSERT, UPDATE ON identifier_counter TO dsnlai_app")
    op.execute("ALTER TABLE identifier_counter ENABLE ROW LEVEL SECURITY")
    op.execute("ALTER TABLE identifier_counter FORCE ROW LEVEL SECURITY")
    op.execute(
        "CREATE POLICY identifier_counter_shared ON identifier_counter "
        "USING (true) WITH CHECK (true)"
    )


def downgrade() -> None:
    op.drop_table("identifier_counter")
