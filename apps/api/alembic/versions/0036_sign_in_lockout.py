"""An account stops accepting passwords after repeated failures.

Token issue had no limit of any kind, so a password could be guessed at
whatever rate the server would answer. Each failed password or second factor
now counts against the account, and enough of them in a row lock it for a
while. A successful sign-in clears the count.

Table-level grants already cover new columns, so nothing is granted here.

Revision ID: 0036
Revises: 0035
"""

import sqlalchemy as sa
from alembic import op

revision = "0036"
down_revision = "0035"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "app_user",
        sa.Column(
            "failed_login_count",
            sa.Integer(),
            nullable=False,
            server_default=sa.text("0"),
        ),
    )
    op.add_column("app_user", sa.Column("locked_until", sa.DateTime(timezone=True)))


def downgrade() -> None:
    op.drop_column("app_user", "locked_until")
    op.drop_column("app_user", "failed_login_count")
