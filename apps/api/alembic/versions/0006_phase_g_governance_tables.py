"""Quality sample, controlled export, defensible deletion and template import.

Four records the PRD asks for that had no table behind them: the monthly quality
sample that keeps tier 1 auto-issue under review (LOP-M04-US-04), bulk export
with a second approver (LOP-M15-US-05), deletion with a certificate
(LOP-M15-US-04), and Word template import with provenance (LOP-M03-US-07).

Revision ID: 0006
Revises: 0005
"""

from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision: str = "0006"
down_revision: str | None = "0005"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

ENTITY_SCOPED_NEW = ["quality_sample", "export_request", "deletion_request", "template_import"]


def upgrade() -> None:
    op.create_table(
        "quality_sample",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("entity", sa.String(3), nullable=False, index=True),
        sa.Column("period", sa.String(7), nullable=False, index=True),
        sa.Column("object_type", sa.String(32), nullable=False),
        sa.Column("object_reference", sa.String(64), nullable=False),
        sa.Column("reason", sa.String(255), nullable=False),
        sa.Column("reviewed", sa.Boolean(), nullable=False, server_default=sa.false(), index=True),
        sa.Column(
            "reviewer_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("app_user.id", ondelete="SET NULL"),
        ),
        sa.Column("reviewed_at", sa.DateTime(timezone=True)),
        sa.Column("outcome", sa.String(24)),
        sa.Column("notes", sa.Text()),
    )

    op.create_table(
        "export_request",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("entity", sa.String(3), nullable=False, index=True),
        sa.Column("record_class", sa.String(64), nullable=False),
        sa.Column("scope", postgresql.JSONB(), nullable=False, server_default="{}"),
        sa.Column("reason", sa.Text(), nullable=False),
        sa.Column("data_classes", postgresql.JSONB(), nullable=False, server_default="[]"),
        sa.Column(
            "requested_by_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("app_user.id", ondelete="SET NULL"),
        ),
        sa.Column("status", sa.String(16), nullable=False, server_default="pending", index=True),
        sa.Column(
            "approver_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("app_user.id", ondelete="SET NULL"),
        ),
        sa.Column("decided_at", sa.DateTime(timezone=True)),
        sa.Column("decision_reason", sa.Text()),
        sa.Column("row_count", sa.Integer()),
        sa.Column("completed_at", sa.DateTime(timezone=True)),
    )

    op.create_table(
        "deletion_request",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("entity", sa.String(3), nullable=False, index=True),
        sa.Column("record_class", sa.String(64), nullable=False, index=True),
        sa.Column("object_type", sa.String(32), nullable=False),
        sa.Column("object_reference", sa.String(64), nullable=False),
        sa.Column("reason", sa.Text(), nullable=False),
        sa.Column(
            "requested_by_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("app_user.id", ondelete="SET NULL"),
        ),
        sa.Column("status", sa.String(16), nullable=False, server_default="pending", index=True),
        sa.Column(
            "approver_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("app_user.id", ondelete="SET NULL"),
        ),
        sa.Column("decided_at", sa.DateTime(timezone=True)),
        sa.Column("decision_reason", sa.Text()),
        sa.Column("executed_at", sa.DateTime(timezone=True)),
        sa.Column("certificate_reference", sa.String(32), unique=True),
        sa.Column("certificate", postgresql.JSONB(), nullable=False, server_default="{}"),
    )

    op.create_table(
        "template_import",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("filename", sa.String(255), nullable=False),
        sa.Column("entity", sa.String(3), nullable=False, index=True),
        sa.Column("agreement_type", sa.String(64)),
        sa.Column("storage_key", sa.String(512)),
        sa.Column("source_hash", sa.String(64), nullable=False),
        sa.Column(
            "uploaded_by_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("app_user.id", ondelete="SET NULL"),
        ),
        sa.Column("status", sa.String(16), nullable=False, server_default="proposed", index=True),
        sa.Column("proposed_clauses", postgresql.JSONB(), nullable=False, server_default="[]"),
        sa.Column("provenance", postgresql.JSONB(), nullable=False, server_default="{}"),
        sa.Column("accepted_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column(
            "decided_by_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("app_user.id", ondelete="SET NULL"),
        ),
    )

    # A legal hold is a decision, so it records who took it and why
    # (LOP-M15-US-04).
    op.add_column("retention_policy", sa.Column("hold_reason", sa.Text()))
    op.add_column(
        "retention_policy",
        sa.Column(
            "hold_set_by_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("app_user.id", ondelete="SET NULL"),
        ),
    )
    op.add_column(
        "retention_policy", sa.Column("hold_set_at", sa.DateTime(timezone=True))
    )

    op.execute("GRANT SELECT, INSERT, UPDATE, DELETE ON ALL TABLES IN SCHEMA public TO dsnlai_app")
    op.execute("GRANT USAGE, SELECT ON ALL SEQUENCES IN SCHEMA public TO dsnlai_app")
    op.execute("REVOKE UPDATE, DELETE, TRUNCATE ON audit_event FROM dsnlai_app")

    # These four carry an entity column, so they follow the same separation
    # boundary as every other entity-scoped record.
    for table in ENTITY_SCOPED_NEW:
        op.execute(f"ALTER TABLE {table} ENABLE ROW LEVEL SECURITY")
        op.execute(f"ALTER TABLE {table} FORCE ROW LEVEL SECURITY")
        op.execute(
            f"""
            CREATE POLICY {table}_entity_scope ON {table}
            USING (dsnlai_bypass() OR entity = ANY (dsnlai_entities()))
            WITH CHECK (dsnlai_bypass() OR entity = ANY (dsnlai_entities()))
            """
        )


def downgrade() -> None:
    for table in ENTITY_SCOPED_NEW:
        op.execute(f"DROP POLICY IF EXISTS {table}_entity_scope ON {table}")
    op.drop_column("retention_policy", "hold_set_at")
    op.drop_column("retention_policy", "hold_set_by_id")
    op.drop_column("retention_policy", "hold_reason")
    op.drop_table("template_import")
    op.drop_table("deletion_request")
    op.drop_table("export_request")
    op.drop_table("quality_sample")
