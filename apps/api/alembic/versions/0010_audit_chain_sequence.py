"""Give the audit chain an order it can actually be verified in.

The chain forked. `record` read the previous digest before its own row was
written, so two events appended in one request, and two appended by concurrent
requests, both linked to the same predecessor. `verify_chain` then ordered by
the clock, which ties whenever two events land in the same microsecond, so it
could not distinguish a genuine fork from its own guess at the order.

Both halves are fixed. A monotonic sequence gives the chain an order that does
not depend on the clock, the digest binds that position, and `record` takes a
transaction-scoped advisory lock so read-then-append is atomic across every
writer and sees what the current transaction has already appended.

This migration is additive on purpose. Existing digests were produced by the
broken algorithm and reconcile against nothing, but they are not rewritten: the
store is append-only and rewriting it, even to make a check pass, would defeat
the control the check exists to provide. `verify_chain` will keep reporting the
historical rows that do not reconcile. That report is true, and a true report
of a past fault is worth more than a green light bought by editing the record.

Rows written from here chain correctly and verify cleanly.

Revision ID: 0010
Revises: 0009
"""

from collections.abc import Sequence

from alembic import op

revision: str = "0010"
down_revision: str | None = "0009"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.execute("CREATE SEQUENCE IF NOT EXISTS audit_event_sequence")

    # The column is added with the sequence as its default rather than backfilled
    # by an UPDATE. The append-only trigger refuses UPDATE on this table, which
    # is correct and is not worked around here: adding a column with a volatile
    # default rewrites the heap and fires no row trigger, so nothing that
    # already exists is modified.
    #
    # The rewrite numbers rows in physical order. On a table that is only ever
    # appended to and never updated, that is insertion order, which makes it the
    # most faithful reconstruction available now that the clock has ties in it.
    op.execute(
        "ALTER TABLE audit_event ADD COLUMN sequence bigint NOT NULL "
        "DEFAULT nextval('audit_event_sequence')"
    )

    op.create_index("uq_audit_event_sequence", "audit_event", ["sequence"], unique=True)
    op.execute("GRANT USAGE, SELECT ON SEQUENCE audit_event_sequence TO dsnlai_app")


def downgrade() -> None:
    op.drop_index("uq_audit_event_sequence", table_name="audit_event")
    op.drop_column("audit_event", "sequence")
    op.execute("DROP SEQUENCE IF EXISTS audit_event_sequence")
