"""An account given its password by somebody else sets its own on first use.

An administrator who creates an account, or resets a password, knows the
password they typed. Until the person replaces it, that password is shared, so
the account is flagged and does nothing but change it.

Existing accounts are not flagged: nobody can say now who set their passwords.

Revision ID: 0037
Revises: 0036
"""

import sqlalchemy as sa
from alembic import op

revision = "0037"
down_revision = "0036"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "app_user",
        sa.Column(
            "password_must_change",
            sa.Boolean(),
            nullable=False,
            server_default=sa.text("false"),
        ),
    )


def downgrade() -> None:
    op.drop_column("app_user", "password_must_change")
