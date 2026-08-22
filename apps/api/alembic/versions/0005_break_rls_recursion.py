"""Make the matter visibility helper non-recursive.

``dsnlai_can_see_matter`` reads ``matter``, whose policy reads ``matter_access``,
whose policy called ``dsnlai_can_see_matter`` again. Postgres unwound that until
it hit the stack limit.

The helper now runs as the definer with row security off, so the reads it makes
to answer the question do not themselves re-enter the policies. This is safe
because the function takes a matter identifier and returns a boolean: it
discloses no row content, and it still answers against the caller's session
context rather than the definer's.

Revision ID: 0005
Revises: 0004
"""

from collections.abc import Sequence

from alembic import op

revision: str = "0005"
down_revision: str | None = "0004"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.execute(
        """
        CREATE OR REPLACE FUNCTION dsnlai_is_named_on(p_matter uuid) RETURNS boolean
        LANGUAGE sql STABLE SECURITY DEFINER SET row_security = off AS $$
            SELECT EXISTS (
                SELECT 1 FROM matter_access ma
                WHERE ma.matter_id = p_matter AND ma.user_id = dsnlai_current_user()
            )
        $$;
        """
    )
    op.execute(
        """
        CREATE OR REPLACE FUNCTION dsnlai_can_see_matter(p_matter uuid) RETURNS boolean
        LANGUAGE sql STABLE SECURITY DEFINER SET row_security = off AS $$
            SELECT dsnlai_bypass() OR EXISTS (
                SELECT 1 FROM matter m
                WHERE m.id = p_matter
                  AND m.entity = ANY (dsnlai_entities())
                  AND (
                      NOT m.restricted
                      OR EXISTS (
                          SELECT 1 FROM matter_access ma
                          WHERE ma.matter_id = m.id
                            AND ma.user_id = dsnlai_current_user()
                      )
                  )
            )
        $$;
        """
    )

    # The matter policy reached into matter_access directly, which put the
    # policy for that table on the same path. It now asks the helper instead.
    op.execute("DROP POLICY IF EXISTS matter_entity_scope ON matter")
    op.execute(
        """
        CREATE POLICY matter_entity_scope ON matter
        USING (
            dsnlai_bypass()
            OR (
                entity = ANY (dsnlai_entities())
                AND (NOT restricted OR dsnlai_is_named_on(id))
            )
        )
        WITH CHECK (dsnlai_bypass() OR entity = ANY (dsnlai_entities()))
        """
    )


def downgrade() -> None:
    op.execute(
        """
        CREATE OR REPLACE FUNCTION dsnlai_can_see_matter(p_matter uuid) RETURNS boolean
        LANGUAGE sql STABLE AS $$
            SELECT dsnlai_bypass() OR EXISTS (
                SELECT 1 FROM matter m
                WHERE m.id = p_matter AND m.entity = ANY (dsnlai_entities())
            )
        $$;
        """
    )
