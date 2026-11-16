"""A template names the agreement sub-type it is for.

The legal team's playbooks are per sub-type, such as a consultancy agreement
for a Frontend Engineer or a Technical Lead, so the paper used for each is
recorded against the same sub-type.

Revision ID: 0039
Revises: 0038
"""

import sqlalchemy as sa
from alembic import op

revision = "0039"
down_revision = "0038"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "template", sa.Column("subtype", sa.String(128), nullable=False, server_default="")
    )


def downgrade() -> None:
    op.drop_column("template", "subtype")
