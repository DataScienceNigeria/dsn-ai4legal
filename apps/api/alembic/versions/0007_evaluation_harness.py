"""Golden sets and their cases, so the capability gates are measured.

The register already carried a metric, a gate expression and a threshold.
Nothing measured them, which made the gate a declaration. These two tables hold
what a measurement is taken against (PRD section 16.1).

Neither table is entity-scoped. A golden set is a property of a capability, not
of DSN or EqualyzAI, and scoring the same capability differently per entity
would make the register meaningless.

Revision ID: 0007
Revises: 0006
"""

from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision: str = "0007"
down_revision: str | None = "0006"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "golden_set",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("name", sa.String(64), nullable=False, index=True),
        sa.Column("version", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("capability_code", sa.String(64), nullable=False, index=True),
        sa.Column("description", sa.Text()),
        sa.Column(
            "owner_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("app_user.id", ondelete="SET NULL"),
        ),
        sa.Column("active", sa.Boolean(), nullable=False, server_default=sa.true(), index=True),
        sa.UniqueConstraint("name", "version", name="uq_golden_set_name_version"),
    )

    op.create_table(
        "golden_case",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column(
            "set_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("golden_set.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("reference", sa.String(64), nullable=False, index=True),
        sa.Column("prompt", sa.Text(), nullable=False),
        sa.Column("context", postgresql.JSONB(), nullable=False, server_default="[]"),
        sa.Column("expected", postgresql.JSONB(), nullable=False, server_default="{}"),
        sa.Column("notes", sa.Text()),
        sa.Column("source", sa.String(255)),
        sa.Column("active", sa.Boolean(), nullable=False, server_default=sa.true()),
    )

    op.execute("GRANT SELECT, INSERT, UPDATE, DELETE ON ALL TABLES IN SCHEMA public TO dsnlai_app")
    op.execute("GRANT USAGE, SELECT ON ALL SEQUENCES IN SCHEMA public TO dsnlai_app")
    op.execute("REVOKE UPDATE, DELETE, TRUNCATE ON audit_event FROM dsnlai_app")


def downgrade() -> None:
    op.drop_table("golden_case")
    op.drop_table("golden_set")
