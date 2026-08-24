"""The particulars an agreement names us by.

Generation fills [Company Name] and [Company Address] from the organisation
record, and the record held the name but not the address, so every imported
template asked someone to type it. Two people typing a registered address from
memory is two versions of it in the archive, and the one that reaches an
executed contract is whichever was typed last.

Held per entity, because DSN and EqualyzAI are different companies with
different registrations, and the whole platform exists to keep them apart.

Revision ID: 0015
Revises: 0014
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "0015"
down_revision: str | None = "0014"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

COLUMNS = [
    sa.Column("trading_name", sa.String(255)),
    sa.Column("registered_address", sa.Text()),
    sa.Column("tax_identification_number", sa.String(64)),
    sa.Column("contact_email", sa.String(320)),
    sa.Column("contact_phone", sa.String(64)),
    sa.Column("website", sa.String(255)),
    sa.Column("signatory_name", sa.String(255)),
    sa.Column("signatory_title", sa.String(128)),
]


def upgrade() -> None:
    for column in COLUMNS:
        op.add_column("organisation", column)

    # An address already recorded under branding moves rather than being asked
    # for again. It was the only place there was to put one.
    op.execute(
        """
        UPDATE organisation
        SET registered_address = branding ->> 'address'
        WHERE branding ? 'address' AND branding ->> 'address' <> ''
        """
    )


def downgrade() -> None:
    for column in reversed(COLUMNS):
        op.drop_column("organisation", column.name)
