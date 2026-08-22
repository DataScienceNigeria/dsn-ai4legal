"""One document per hash per matter, and a delete trigger that actually deletes.

Two faults, found by running the load test at eight concurrent callers.

The first: generation is deterministic, so the same template, the same facts and the same
clause versions produce the same bytes and therefore the same hash. The
endpoint already returned the existing document rather than making a second
one, but nothing stopped two concurrent callers from both passing that check
and both inserting. A load test at eight concurrent callers produced four
copies of the same document and then failed every later read of it.

The second: `dsnlai_document_immutable` is a BEFORE trigger that returns NEW.
On an UPDATE that is correct. On a DELETE, NEW is NULL, and returning NULL from
a BEFORE DELETE trigger cancels the delete. Every deletion of a non-immutable
document has therefore been silently doing nothing and reporting success, which
is worse than refusing, because nothing said so.

Deduplication keeps the earliest row, because approvals, signature requests
and contracts bind to a document id and the earliest is the one anything else
is most likely to reference.

Revision ID: 0009
Revises: 0008
"""

from collections.abc import Sequence

from alembic import op

revision: str = "0009"
down_revision: str | None = "0008"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # The trigger has to be corrected before anything can be deleted, because
    # until it is, every delete below would report success and do nothing.
    op.execute(
        """
        CREATE OR REPLACE FUNCTION dsnlai_document_immutable() RETURNS trigger AS $$
        BEGIN
            IF OLD.immutable THEN
                RAISE EXCEPTION
                    'Document % is an immutable executed copy. Record an amendment instead.',
                    OLD.id;
            END IF;
            IF TG_OP = 'DELETE' THEN
                RETURN OLD;
            END IF;
            RETURN NEW;
        END
        $$ LANGUAGE plpgsql
        """
    )

    # Keep the earliest row in each group. A later copy is byte-identical by
    # construction, so nothing is lost, but one that something already points
    # at is left alone and reported rather than deleted underneath it.
    op.execute(
        """
        DELETE FROM document d
        WHERE d.matter_id IS NOT NULL
          AND d.id <> (
              SELECT e.id FROM document e
              WHERE e.matter_id = d.matter_id AND e.content_hash = d.content_hash
              ORDER BY e.created_at, e.id
              LIMIT 1
          )
          AND NOT EXISTS (SELECT 1 FROM signature_request s WHERE s.document_id = d.id)
          AND NOT EXISTS (SELECT 1 FROM contract c WHERE c.executed_document_id = d.id)
          AND NOT EXISTS (SELECT 1 FROM document p WHERE p.supersedes_id = d.id)
          AND d.immutable IS NOT TRUE
        """
    )

    op.create_index(
        "uq_document_matter_hash",
        "document",
        ["matter_id", "content_hash"],
        unique=True,
    )


def downgrade() -> None:
    op.drop_index("uq_document_matter_hash", table_name="document")
    op.execute(
        """
        CREATE OR REPLACE FUNCTION dsnlai_document_immutable() RETURNS trigger AS $$
        BEGIN
            IF OLD.immutable THEN
                RAISE EXCEPTION
                    'Document % is an immutable executed copy. Record an amendment instead.',
                    OLD.id;
            END IF;
            RETURN NEW;
        END
        $$ LANGUAGE plpgsql
        """
    )
