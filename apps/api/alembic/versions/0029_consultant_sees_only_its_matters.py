"""The matter policy has to obey the consultant rule too.

``0028`` taught ``dsnlai_can_see_matter`` that a consultant sees only matters
they are named on, and every table that hangs off a matter calls that function.
The ``matter`` table itself does not: its policy has inlined the same logic
since ``0003``, so the two drifted apart the moment one changed, and a
consultant could list every unrestricted matter in the entity while being
correctly refused everything attached to them.

Two recursions had to be broken to do it. A policy on ``matter`` cannot be
written in terms of a function that selects from ``matter``, so the rule is
inlined here against the row's own columns. And the named-on lookup cannot read
``matter_access`` directly, because that table's own policy leads back to
``matter``; it goes through a ``SECURITY DEFINER`` helper instead. That loop was
always present and never entered, because the old rule short-circuited on ``NOT
restricted`` for every unrestricted matter. A consultant has no first half.

Revision ID: 0029
Revises: 0028
"""

from collections.abc import Sequence

from alembic import op

revision: str = "0029"
down_revision: str | None = "0028"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # The named-on check has to be able to read ``matter_access``.
    #
    # It could not. ``matter_access`` carries a policy of its own that calls
    # ``dsnlai_can_see_matter``, which selects from ``matter``, whose policy
    # subselects ``matter_access``. The loop was always there and was never
    # entered, because the old rule read ``NOT restricted OR EXISTS (...)`` and
    # short-circuited on the first half for every unrestricted matter. A
    # consultant has no first half: being named is the whole permission, so the
    # EXISTS always runs and the recursion unwinds at the stack depth limit.
    #
    # ``SECURITY DEFINER`` runs the lookup as the owner, which holds BYPASSRLS,
    # so it answers without re-entering any policy. The search path is pinned
    # because a definer function that resolves names from the caller's path is a
    # privilege escalation waiting for somebody to create a table.
    op.execute(
        """
        CREATE OR REPLACE FUNCTION dsnlai_named_on(p_matter uuid) RETURNS boolean
        LANGUAGE sql STABLE SECURITY DEFINER SET search_path = public, pg_temp AS $$
            SELECT EXISTS (
                SELECT 1 FROM matter_access ma
                WHERE ma.matter_id = p_matter
                  AND ma.user_id = dsnlai_current_user()
            )
        $$;
        """
    )
    op.execute("REVOKE ALL ON FUNCTION dsnlai_named_on(uuid) FROM PUBLIC")
    op.execute("GRANT EXECUTE ON FUNCTION dsnlai_named_on(uuid) TO dsnlai_app")

    op.execute(
        """
        CREATE OR REPLACE FUNCTION dsnlai_can_see_matter(p_matter uuid) RETURNS boolean
        LANGUAGE sql STABLE AS $$
            SELECT dsnlai_bypass() OR EXISTS (
                SELECT 1 FROM matter m
                WHERE m.id = p_matter
                  AND m.entity = ANY (dsnlai_entities())
                  AND (
                      CASE WHEN 'consultant' = ANY (dsnlai_roles())
                           THEN dsnlai_named_on(m.id)
                           ELSE NOT m.restricted OR dsnlai_named_on(m.id)
                      END
                  )
            )
        $$;
        """
    )

    # Inlined, not delegated.
    #
    # The obvious version has this policy call ``dsnlai_can_see_matter`` like
    # every other table does. It cannot: that function selects from ``matter``,
    # which re-applies this policy, which calls the function again. A policy on
    # a table may not be written in terms of a query against that table, so the
    # rule is stated here against the row's own columns and the two copies are
    # kept in step by hand.
    op.execute("DROP POLICY IF EXISTS matter_entity_scope ON matter")
    op.execute(
        """
        CREATE POLICY matter_entity_scope ON matter
        USING (
            dsnlai_bypass() OR (
                entity = ANY (dsnlai_entities())
                AND (
                    CASE WHEN 'consultant' = ANY (dsnlai_roles())
                         THEN dsnlai_named_on(matter.id)
                         ELSE NOT restricted OR dsnlai_named_on(matter.id)
                    END
                )
            )
        )
        WITH CHECK (dsnlai_bypass() OR entity = ANY (dsnlai_entities()))
        """
    )


def downgrade() -> None:
    op.execute("DROP POLICY IF EXISTS matter_entity_scope ON matter")
    op.execute(
        """
        CREATE POLICY matter_entity_scope ON matter
        USING (
            dsnlai_bypass() OR (
                entity = ANY (dsnlai_entities())
                AND (NOT restricted OR EXISTS (
                    SELECT 1 FROM matter_access ma
                    WHERE ma.matter_id = matter.id AND ma.user_id = dsnlai_current_user()
                ))
            )
        )
        WITH CHECK (dsnlai_bypass() OR entity = ANY (dsnlai_entities()))
        """
    )
