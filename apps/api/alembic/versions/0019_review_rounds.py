"""Negotiation is rounds, and the paper is what closes a finding.

A review produced a list of complaints once and had no idea what happened
next. Their draft came back changed, from an editor here or from a week in
somebody's Google Docs, and the platform could only be told what had been
settled by a person ticking boxes. Nobody ticks boxes honestly about a
forty-page contract, and nothing at all catches the clause the counterparty
quietly rewrote while the argument was about a different one.

So the returned paper is re-read and the rounds are compared. A point that no
longer appears is settled. A point that still appears is still open, and is
linked to the round it came from so it reads as one argument rather than as a
fresh complaint each time. A point that appears for the first time in round
three is the one worth the whole feature.

Revision ID: 0019
Revises: 0018
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "0019"
down_revision: str | None = "0018"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "review_finding",
        sa.Column("round", sa.Integer(), nullable=False, server_default="1"),
    )
    op.add_column(
        "review_finding",
        sa.Column("carried_from_id", sa.dialects.postgresql.UUID(as_uuid=True), nullable=True),
    )
    op.add_column("review_finding", sa.Column("settled_in_round", sa.Integer(), nullable=True))
    op.create_foreign_key(
        "fk_review_finding_carried_from_id_review_finding",
        "review_finding",
        "review_finding",
        ["carried_from_id"],
        ["id"],
        ondelete="SET NULL",
    )
    op.create_index("ix_review_finding_round", "review_finding", ["round"])


def downgrade() -> None:
    op.drop_index("ix_review_finding_round", table_name="review_finding")
    op.drop_constraint(
        "fk_review_finding_carried_from_id_review_finding", "review_finding", type_="foreignkey"
    )
    op.drop_column("review_finding", "settled_in_round")
    op.drop_column("review_finding", "carried_from_id")
    op.drop_column("review_finding", "round")
