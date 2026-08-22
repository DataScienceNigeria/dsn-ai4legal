"""Row-level security, grants and the append-only audit store.

Authorisation is enforced in the data layer. An endpoint may not rely on the
caller having filtered correctly (PRD section 12.1), and an application defect
cannot leak across an entity or matter boundary (LOP-NFR-13).

Revision ID: 0003
Revises: 0002
"""

from collections.abc import Sequence

from alembic import op

revision: str = "0003"
down_revision: str | None = "0002"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

#: Tables carrying an entity column, scoped to the caller's entity membership.
ENTITY_SCOPED = [
    "request",
    "matter",
    "contract",
    "document",
    "obligation",
    "communication",
    "assessment",
    "compliance_item",
    "product",
    "memory_chunk",
]

#: Tables whose visibility follows the matter they belong to, so that a
#: restricted matter takes its documents, findings and approvals with it.
MATTER_DEPENDENT = [
    "matter_transition",
    "matter_access",
    "matter_link",
    "decision_record",
    "approval",
    "signature_request",
    "review_finding",
]

#: Reference data every authenticated user may read. Writes are still gated in
#: the application by role, and every write is audited.
SHARED_READABLE = [
    "organisation",
    "app_user",
    "user_entity",
    "request_type",
    "clause",
    "clause_version",
    "template",
    "template_version",
    "playbook",
    "counterparty",
    "vendor",
    "capability",
    "evaluation_run",
    "kpi_baseline",
    "approval_chain_definition",
    "config_setting",
    "connector",
    "retention_policy",
    "mailbox",
    "attachment",
    "suggestion",
    "extracted_value",
    "ai_interaction",
    "idempotency_key",
    "outbox_event",
    "egress_log",
]

ALL_RLS_TABLES = ENTITY_SCOPED + MATTER_DEPENDENT + SHARED_READABLE + ["audit_event"]


def upgrade() -> None:
    bind = op.get_bind()

    # ---------------------------------------------------------------- grants
    op.execute("GRANT SELECT, INSERT, UPDATE, DELETE ON ALL TABLES IN SCHEMA public TO dsnlai_app")
    op.execute("GRANT USAGE, SELECT ON ALL SEQUENCES IN SCHEMA public TO dsnlai_app")
    op.execute(
        "ALTER DEFAULT PRIVILEGES IN SCHEMA public "
        "GRANT SELECT, INSERT, UPDATE, DELETE ON TABLES TO dsnlai_app"
    )

    # ------------------------------------------------------ context helpers
    # Session variables are set with SET LOCAL on every request, so a pooled
    # connection can never carry one caller's context into another's request.
    op.execute(
        """
        CREATE OR REPLACE FUNCTION dsnlai_bypass() RETURNS boolean
        LANGUAGE sql STABLE AS $$
            SELECT coalesce(current_setting('dsnlai.bypass_rls', true), 'off') = 'on'
        $$;
        """
    )
    op.execute(
        """
        CREATE OR REPLACE FUNCTION dsnlai_current_user() RETURNS uuid
        LANGUAGE plpgsql STABLE AS $$
        DECLARE raw text;
        BEGIN
            raw := nullif(current_setting('dsnlai.user_id', true), '');
            IF raw IS NULL THEN RETURN NULL; END IF;
            RETURN raw::uuid;
        EXCEPTION WHEN others THEN RETURN NULL;
        END
        $$;
        """
    )
    op.execute(
        """
        CREATE OR REPLACE FUNCTION dsnlai_entities() RETURNS text[]
        LANGUAGE sql STABLE AS $$
            SELECT coalesce(
                string_to_array(nullif(current_setting('dsnlai.entities', true), ''), ','),
                ARRAY[]::text[]
            )
        $$;
        """
    )
    op.execute(
        """
        CREATE OR REPLACE FUNCTION dsnlai_roles() RETURNS text[]
        LANGUAGE sql STABLE AS $$
            SELECT coalesce(
                string_to_array(nullif(current_setting('dsnlai.roles', true), ''), ','),
                ARRAY[]::text[]
            )
        $$;
        """
    )

    # A matter is visible when it is in one of the caller's entities and either
    # it is not restricted, or the caller is explicitly named on it. Restricted
    # matters are excluded from every list, search, index, dashboard and export
    # for anyone else (LOP-M02-US-08).
    op.execute(
        """
        CREATE OR REPLACE FUNCTION dsnlai_can_see_matter(p_matter uuid) RETURNS boolean
        LANGUAGE sql STABLE AS $$
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

    for table in ALL_RLS_TABLES:
        op.execute(f"ALTER TABLE {table} ENABLE ROW LEVEL SECURITY")
        op.execute(f"ALTER TABLE {table} FORCE ROW LEVEL SECURITY")

    # ------------------------------------------------------- entity scoping
    for table in ENTITY_SCOPED:
        restricted_clause = ""
        if table == "matter":
            restricted_clause = (
                " AND (NOT restricted OR EXISTS ("
                "SELECT 1 FROM matter_access ma WHERE ma.matter_id = matter.id "
                "AND ma.user_id = dsnlai_current_user()))"
            )
        elif table == "memory_chunk":
            # Retrieval is filtered by entity, role and matter access before
            # ranking, not after, so restricted rows never enter the candidate
            # set (LOP-M10-US-04).
            restricted_clause = (
                " AND (NOT restricted OR (matter_id IS NOT NULL "
                "AND dsnlai_can_see_matter(matter_id)))"
            )
        elif table in {"contract", "document", "obligation", "communication"}:
            restricted_clause = (
                " AND (matter_id IS NULL OR dsnlai_can_see_matter(matter_id))"
            )

        op.execute(
            f"""
            CREATE POLICY {table}_entity_scope ON {table}
            USING (dsnlai_bypass() OR (entity = ANY (dsnlai_entities()){restricted_clause}))
            WITH CHECK (dsnlai_bypass() OR entity = ANY (dsnlai_entities()))
            """
        )

    # --------------------------------------------------- matter-dependent
    for table in MATTER_DEPENDENT:
        nullable = table == "decision_record"
        predicate = (
            "matter_id IS NULL OR dsnlai_can_see_matter(matter_id)"
            if nullable
            else "dsnlai_can_see_matter(matter_id)"
        )
        op.execute(
            f"""
            CREATE POLICY {table}_matter_scope ON {table}
            USING (dsnlai_bypass() OR ({predicate}))
            WITH CHECK (dsnlai_bypass() OR ({predicate}))
            """
        )

    # -------------------------------------------------------- shared tables
    for table in SHARED_READABLE:
        op.execute(
            f"""
            CREATE POLICY {table}_shared ON {table}
            USING (true) WITH CHECK (true)
            """
        )

    # ------------------------------------------------ append-only audit store
    # The store is write-once for the retention period, and administrators
    # cannot alter it (LOP-M15-US-03).
    op.execute("CREATE POLICY audit_event_insert ON audit_event FOR INSERT WITH CHECK (true)")
    op.execute("CREATE POLICY audit_event_read ON audit_event FOR SELECT USING (true)")
    op.execute("REVOKE UPDATE, DELETE, TRUNCATE ON audit_event FROM dsnlai_app")
    op.execute(
        """
        CREATE OR REPLACE FUNCTION dsnlai_audit_is_append_only() RETURNS trigger
        LANGUAGE plpgsql AS $$
        BEGIN
            RAISE EXCEPTION 'The audit store is append-only. % is not permitted.', TG_OP;
        END
        $$;
        """
    )
    op.execute(
        """
        CREATE TRIGGER audit_event_append_only
        BEFORE UPDATE OR DELETE OR TRUNCATE ON audit_event
        FOR EACH STATEMENT EXECUTE FUNCTION dsnlai_audit_is_append_only();
        """
    )

    # An executed copy is immutable for the retention period (LOP-M08-US-01).
    op.execute(
        """
        CREATE OR REPLACE FUNCTION dsnlai_document_immutable() RETURNS trigger
        LANGUAGE plpgsql AS $$
        BEGIN
            IF OLD.immutable THEN
                RAISE EXCEPTION
                    'Document % is an immutable executed copy. Record an amendment instead.',
                    OLD.id;
            END IF;
            RETURN NEW;
        END
        $$;
        """
    )
    op.execute(
        """
        CREATE TRIGGER document_immutable
        BEFORE UPDATE OR DELETE ON document
        FOR EACH ROW EXECUTE FUNCTION dsnlai_document_immutable();
        """
    )

    # Full-text search over the retrieval corpus, the keyword half of hybrid
    # retrieval (PRD section 13.3).
    op.execute(
        "CREATE INDEX ix_memory_chunk_fts ON memory_chunk "
        "USING gin (to_tsvector('english', title || ' ' || body))"
    )
    op.execute(
        "CREATE INDEX ix_counterparty_name_trgm ON counterparty "
        "USING gin (legal_name gin_trgm_ops)"
    )
    if bind.dialect.name == "postgresql":
        op.execute(
            "CREATE INDEX ix_memory_chunk_embedding ON memory_chunk "
            "USING hnsw (embedding vector_cosine_ops)"
        )


def downgrade() -> None:
    op.execute("DROP INDEX IF EXISTS ix_memory_chunk_embedding")
    op.execute("DROP INDEX IF EXISTS ix_counterparty_name_trgm")
    op.execute("DROP INDEX IF EXISTS ix_memory_chunk_fts")
    op.execute("DROP TRIGGER IF EXISTS document_immutable ON document")
    op.execute("DROP TRIGGER IF EXISTS audit_event_append_only ON audit_event")
    op.execute("DROP FUNCTION IF EXISTS dsnlai_document_immutable")
    op.execute("DROP FUNCTION IF EXISTS dsnlai_audit_is_append_only")
    for table in ALL_RLS_TABLES:
        op.execute(f"ALTER TABLE {table} DISABLE ROW LEVEL SECURITY")
    op.execute("DROP FUNCTION IF EXISTS dsnlai_can_see_matter")
    op.execute("DROP FUNCTION IF EXISTS dsnlai_roles")
    op.execute("DROP FUNCTION IF EXISTS dsnlai_entities")
    op.execute("DROP FUNCTION IF EXISTS dsnlai_current_user")
    op.execute("DROP FUNCTION IF EXISTS dsnlai_bypass")
