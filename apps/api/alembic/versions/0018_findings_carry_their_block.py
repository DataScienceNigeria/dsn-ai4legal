"""A finding knows which block of the draft it is about.

A review ended at a record of decisions. Accepting a finding stored who
accepted what and left the counterparty's document exactly as it arrived, so
producing the marked-up draft meant retyping every change by hand in the
editor. Legal marks up a contract; the marked-up contract is the deliverable.

The endpoint meant to do it read the ``suggestion`` table, which nothing in the
codebase has ever written to, so it always answered that nothing had been
accepted. Two tables were built for one idea by two paths, and the one that was
used carried no anchor: a finding knew what was wrong, never which paragraph to
replace.

``block_key`` is that anchor. ``suggestion`` is dropped, having never held a
row.

Revision ID: 0018
Revises: 0017
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "0018"
down_revision: str | None = "0017"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column("review_finding", sa.Column("block_key", sa.String(64), nullable=True))

    # Existing findings keep a null anchor rather than a guessed one. Locating
    # them means matching quoted text against the document they came from,
    # which the review does at the point it still has both; doing it here from
    # a migration would be the same work with less to go on. Re-run the review
    # to place them.
    op.drop_table("suggestion")


def downgrade() -> None:
    op.drop_column("review_finding", "block_key")
    op.create_table(
        "suggestion",
        sa.Column("id", sa.dialects.postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("document_id", sa.dialects.postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("block_key", sa.String(64), nullable=False),
        sa.Column("instruction", sa.Text()),
        sa.Column("original_text", sa.Text(), nullable=False),
        sa.Column("proposed_text", sa.Text(), nullable=False),
        sa.Column("rationale", sa.Text()),
        sa.Column("source_reference", sa.String(64)),
        sa.Column("novel", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("decision", sa.String(16), nullable=False, server_default="pending"),
        sa.Column("decided_by_id", sa.dialects.postgresql.UUID(as_uuid=True)),
        sa.Column("decided_at", sa.DateTime(timezone=True)),
        sa.Column("interaction_id", sa.String(64)),
        sa.ForeignKeyConstraint(["document_id"], ["document.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["decided_by_id"], ["app_user.id"], ondelete="SET NULL"),
    )
