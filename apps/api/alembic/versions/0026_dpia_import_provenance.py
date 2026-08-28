"""A DPIA can be imported from the Word template it was already written on.

Several projects filled the manual template before the platform existed, and
asking their leads to answer fifty-nine questions a second time is how a form
gets abandoned. The document is read instead.

Two columns, both about provenance. An answer a lead typed into the form is one
they wrote today knowing it would be assessed; an answer lifted from a document
written a year ago is a record of what was true then. The officer should be able
to tell which is which, and the lead should be able to see what the import
filled in so they can correct it.

Revision ID: 0026
Revises: 0025
"""

from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision: str = "0026"
down_revision: str | None = "0025"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "assessment",
        sa.Column(
            "imported_fields", postgresql.JSONB(), nullable=False, server_default="[]"
        ),
    )
    op.add_column("assessment", sa.Column("imported_from", sa.String(255)))


def downgrade() -> None:
    op.drop_column("assessment", "imported_from")
    op.drop_column("assessment", "imported_fields")
