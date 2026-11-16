"""Playbook positions on wording that is not yet approved.

The legal team states positions for clauses whose wording is still reference
wording. The positions are kept with that wording, outside every playbook, so
nothing is lost and nothing becomes house position before it is approved.

Revision ID: 0040
Revises: 0039
"""

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "0040"
down_revision = "0039"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("clause_precedent", sa.Column("standard_position", sa.Text()))
    op.add_column(
        "clause_precedent",
        sa.Column("fallbacks", postgresql.JSONB(), nullable=False, server_default="[]"),
    )
    op.add_column("clause_precedent", sa.Column("unacceptable_position", sa.Text()))
    op.add_column("clause_precedent", sa.Column("playbook_row", sa.Integer()))


def downgrade() -> None:
    op.drop_column("clause_precedent", "playbook_row")
    op.drop_column("clause_precedent", "unacceptable_position")
    op.drop_column("clause_precedent", "fallbacks")
    op.drop_column("clause_precedent", "standard_position")
