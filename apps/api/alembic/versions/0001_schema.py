"""Initial schema, extensions and the application role.

Revision ID: 0001
Revises:
"""

from collections.abc import Sequence

from alembic import op

revision: str = "0001"
down_revision: str | None = None
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # pgvector backs the vector half of hybrid retrieval, and pg_trgm backs the
    # fuzzy counterparty matching required by LOP-M13-US-02.
    op.execute("CREATE EXTENSION IF NOT EXISTS vector")
    op.execute("CREATE EXTENSION IF NOT EXISTS pg_trgm")
    op.execute('CREATE EXTENSION IF NOT EXISTS "uuid-ossp"')

    # The application connects as this role. It is deliberately not the owner,
    # because row-level security does not apply to a table's owner and would
    # therefore be decorative (LOP-NFR-13).
    op.execute(
        """
        DO $$
        BEGIN
            IF NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'dsnlai_app') THEN
                CREATE ROLE dsnlai_app LOGIN PASSWORD 'dsnlai_app_dev_password';
            END IF;
        END
        $$;
        """
    )
    op.execute("GRANT USAGE ON SCHEMA public TO dsnlai_app")


def downgrade() -> None:
    op.execute("REVOKE USAGE ON SCHEMA public FROM dsnlai_app")
