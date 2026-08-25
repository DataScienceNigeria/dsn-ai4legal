"""Two things nothing used, and one that was worse than unused.

``approval_chain_definition`` held configurable chains matched on entity, type,
risk tier and value band. The approval model was rewritten to what a team of
this size actually does, the requester confirming the draft is the deal and the
legal lead confirming it is safe, derived from the matter rather than looked up.
Nothing has resolved a chain since. Four seeded rows, no approval ever pointing
at one, and a resolver that raised "no approval chain is configured" for a
question nobody was asking.

``POST /capabilities/{code}/evaluate`` is the one that was worse than unused. It
took a score as a query parameter and wrote it to the register as a
measurement, which is exactly how obligation extraction came to sit disabled
behind a 0.89 nobody had measured. It also predated per-capability gate
enforcement and disabled things the register says not to disable.
``run-evaluation`` runs the golden set and is the only honest way in.

Removed in code; this drops the table.

Revision ID: 0023
Revises: 0022
"""

from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision: str = "0023"
down_revision: str | None = "0022"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # The column survives on approval. It is null on every row, and dropping a
    # column from a table the audit trail refers to buys nothing.
    op.drop_constraint(
        "fk_approval_chain_definition_id_approval_chain_definition",
        "approval",
        type_="foreignkey",
    )
    op.drop_table("approval_chain_definition")


def downgrade() -> None:
    op.create_table(
        "approval_chain_definition",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("name", sa.String(128), nullable=False),
        sa.Column("entity", sa.String(3)),
        sa.Column("agreement_type", sa.String(64)),
        sa.Column("risk_tier", sa.String(16)),
        sa.Column("min_value", sa.Numeric(18, 2)),
        sa.Column("max_value", sa.Numeric(18, 2)),
        sa.Column("steps", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("active", sa.Boolean(), nullable=False),
        sa.Column("priority", sa.Integer(), nullable=False),
        sa.PrimaryKeyConstraint("id", name="pk_approval_chain_definition"),
    )
    op.create_foreign_key(
        "fk_approval_chain_definition_id_approval_chain_definition",
        "approval",
        "approval_chain_definition",
        ["chain_definition_id"],
        ["id"],
        ondelete="SET NULL",
    )
