"""Agreements signed before the platform existed.

An agreement executed in 2021 was never a matter here. It had no request, no
triage, no approval chain and no signature request, and giving it a shell matter
to satisfy a constraint would put a fabricated history in front of everyone who
opened it. So a contract may now exist without one.

Nothing about who can see it changes. The contract policy from ``0003`` already
reads ``matter_id IS NULL OR dsnlai_can_see_matter(matter_id)``, so a contract
with no matter is scoped by entity alone, which is what an agreement that was
never legal work in this system should be.

``origin`` says which kind a row is, so every screen can say so. An empty
approvals record means one thing on an agreement executed here and another on
one that predates the platform, and the reader has to be told which.

Revision ID: 0033
Revises: 0032
"""

import sqlalchemy as sa
from alembic import op

revision = "0033"
down_revision = "0032"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.alter_column("contract", "matter_id", existing_type=sa.dialects.postgresql.UUID(), nullable=True)
    op.add_column(
        "contract",
        sa.Column("origin", sa.String(16), nullable=False, server_default="platform"),
    )


def downgrade() -> None:
    op.drop_column("contract", "origin")
    op.alter_column("contract", "matter_id", existing_type=sa.dialects.postgresql.UUID(), nullable=False)
