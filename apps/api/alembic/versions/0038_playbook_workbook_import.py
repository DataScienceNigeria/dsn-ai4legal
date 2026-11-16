"""The legal team's playbook and clause library workbook.

A clause is held in several forms, one per entity, agreement type and role,
and each form is its own line of versions. The playbook position travels with
the version that states it. Wording seen in signed agreements, or forbidden
outright, is kept as precedent and never as house position. A playbook may now
be one entity's and one sub-type's. The workbook import is recorded, with what
it would do and every problem found, before anything is written.

Revision ID: 0038
Revises: 0037
"""

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "0038"
down_revision = "0037"
branch_labels = None
depends_on = None

NEW_TABLES = ["library_import", "clause_variant", "clause_precedent"]


def _timestamps() -> list[sa.Column]:
    return [
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
    ]


def _user_fk(name: str) -> sa.Column:
    return sa.Column(
        name, postgresql.UUID(as_uuid=True), sa.ForeignKey("app_user.id", ondelete="SET NULL")
    )


def _import_fk() -> sa.Column:
    return sa.Column(
        "library_import_id",
        postgresql.UUID(as_uuid=True),
        sa.ForeignKey("library_import.id", ondelete="SET NULL"),
    )


def upgrade() -> None:
    op.create_table(
        "library_import",
        *_timestamps(),
        sa.Column("filename", sa.String(255), nullable=False),
        sa.Column("storage_key", sa.String(512)),
        sa.Column("source_hash", sa.String(64), nullable=False, index=True),
        _user_fk("uploaded_by_id"),
        sa.Column("status", sa.String(16), nullable=False, server_default="checked", index=True),
        sa.Column("summary", postgresql.JSONB(), nullable=False, server_default="{}"),
        sa.Column("issues", postgresql.JSONB(), nullable=False, server_default="[]"),
        sa.Column("plan", postgresql.JSONB(), nullable=False, server_default="{}"),
        _user_fk("applied_by_id"),
        sa.Column("applied_at", sa.DateTime(timezone=True)),
    )

    op.add_column("clause", sa.Column("family", sa.String(64)))
    op.create_index("ix_clause_family", "clause", ["family"])

    op.create_table(
        "clause_variant",
        *_timestamps(),
        sa.Column(
            "clause_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("clause.id", ondelete="CASCADE"),
            nullable=False,
            index=True,
        ),
        sa.Column("code", sa.String(24), nullable=False, unique=True, index=True),
        sa.Column("title", sa.String(255), nullable=False),
        sa.Column("entity_scope", sa.String(4), nullable=False, index=True),
        sa.Column("agreement_type", sa.String(64), nullable=False, index=True),
        sa.Column("subtype", sa.String(128), nullable=False, server_default=""),
        sa.Column("transaction_role", sa.String(64), nullable=False),
        sa.Column("source_url", sa.Text()),
    )

    op.add_column(
        "clause_version",
        sa.Column(
            "variant_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("clause_variant.id", ondelete="CASCADE"),
        ),
    )
    op.create_index("ix_clause_version_variant_id", "clause_version", ["variant_id"])
    op.add_column("clause_version", sa.Column("standard_position", sa.Text()))
    op.add_column("clause_version", _import_fk())
    op.drop_constraint("uq_clause_version_clause_id", "clause_version", type_="unique")
    op.create_unique_constraint(
        "uq_clause_version_variant_major_minor",
        "clause_version",
        ["clause_id", "variant_id", "major", "minor"],
        postgresql_nulls_not_distinct=True,
    )

    op.add_column("playbook", sa.Column("entity", sa.String(3)))
    op.add_column(
        "playbook", sa.Column("subtype", sa.String(128), nullable=False, server_default="")
    )
    op.add_column("playbook", _import_fk())
    op.drop_constraint("uq_playbook_agreement_type", "playbook", type_="unique")
    op.create_unique_constraint(
        "uq_playbook_type_entity_subtype",
        "playbook",
        ["agreement_type", "entity", "subtype"],
        postgresql_nulls_not_distinct=True,
    )
    op.create_index("ix_playbook_agreement_type", "playbook", ["agreement_type"])
    op.create_index("ix_playbook_entity", "playbook", ["entity"])

    op.create_table(
        "clause_precedent",
        *_timestamps(),
        sa.Column(
            "clause_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("clause.id", ondelete="CASCADE"),
            nullable=False,
            index=True,
        ),
        sa.Column("fingerprint", sa.String(64), nullable=False, unique=True),
        sa.Column("reference", sa.String(24), index=True),
        sa.Column("kind", sa.String(16), nullable=False, index=True),
        sa.Column("entity_scope", sa.String(4), nullable=False, index=True),
        sa.Column("agreement_type", sa.String(64), nullable=False),
        sa.Column("subtype", sa.String(128), nullable=False, server_default=""),
        sa.Column("transaction_role", sa.String(64), nullable=False),
        sa.Column("family", sa.String(64), nullable=False),
        sa.Column("title", sa.String(255), nullable=False),
        sa.Column("text", sa.Text(), nullable=False),
        sa.Column("source_url", sa.Text()),
        _import_fk(),
        sa.Column("source_row", sa.Integer()),
    )

    op.execute("GRANT SELECT, INSERT, UPDATE, DELETE ON ALL TABLES IN SCHEMA public TO dsnlai_app")
    for table in NEW_TABLES:
        op.execute(f"ALTER TABLE {table} ENABLE ROW LEVEL SECURITY")
        op.execute(f"ALTER TABLE {table} FORCE ROW LEVEL SECURITY")
        op.execute(f"CREATE POLICY {table}_shared ON {table} USING (true) WITH CHECK (true)")


def downgrade() -> None:
    op.drop_table("clause_precedent")

    op.drop_index("ix_playbook_entity", "playbook")
    op.drop_index("ix_playbook_agreement_type", "playbook")
    op.drop_constraint("uq_playbook_type_entity_subtype", "playbook", type_="unique")
    op.execute("DELETE FROM playbook WHERE entity IS NOT NULL OR subtype <> ''")
    op.create_unique_constraint("uq_playbook_agreement_type", "playbook", ["agreement_type"])
    op.drop_column("playbook", "library_import_id")
    op.drop_column("playbook", "subtype")
    op.drop_column("playbook", "entity")

    op.drop_constraint("uq_clause_version_variant_major_minor", "clause_version", type_="unique")
    op.execute("DELETE FROM clause_version WHERE variant_id IS NOT NULL")
    op.create_unique_constraint(
        "uq_clause_version_clause_id", "clause_version", ["clause_id", "major", "minor"]
    )
    op.drop_column("clause_version", "library_import_id")
    op.drop_column("clause_version", "standard_position")
    op.drop_index("ix_clause_version_variant_id", "clause_version")
    op.drop_column("clause_version", "variant_id")

    op.drop_table("clause_variant")
    op.drop_index("ix_clause_family", "clause")
    op.drop_column("clause", "family")
    op.drop_table("library_import")
