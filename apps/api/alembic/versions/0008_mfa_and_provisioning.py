"""Second factor and directory provisioning on the user record.

Two things the platform claimed but did not hold: a second factor for the roles
that can publish, sign, restrict or administer, and the directory's own
identifier so SCIM can find the person it is talking about.

`deprovisioned_at` exists because a leaver is deactivated rather than deleted.
The record is on decisions, approvals and the audit chain, and removing the row
would break attribution on work that was validly done.

Revision ID: 0008
Revises: 0007
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "0008"
down_revision: str | None = "0007"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column("app_user", sa.Column("mfa_secret", sa.String(64)))
    op.add_column("app_user", sa.Column("mfa_enrolled_at", sa.DateTime(timezone=True)))
    op.add_column(
        "app_user",
        sa.Column(
            "mfa_recovery_codes",
            sa.ARRAY(sa.String(128)),
            nullable=False,
            server_default="{}",
        ),
    )
    op.add_column("app_user", sa.Column("mfa_last_used_counter", sa.Integer()))
    op.add_column("app_user", sa.Column("external_id", sa.String(255)))
    op.add_column("app_user", sa.Column("provisioned_by", sa.String(32)))
    op.add_column("app_user", sa.Column("deprovisioned_at", sa.DateTime(timezone=True)))
    op.create_index("ix_app_user_external_id", "app_user", ["external_id"])

    op.execute("GRANT SELECT, INSERT, UPDATE, DELETE ON ALL TABLES IN SCHEMA public TO dsnlai_app")


def downgrade() -> None:
    op.drop_index("ix_app_user_external_id", table_name="app_user")
    op.drop_column("app_user", "deprovisioned_at")
    op.drop_column("app_user", "provisioned_by")
    op.drop_column("app_user", "external_id")
    op.drop_column("app_user", "mfa_last_used_counter")
    op.drop_column("app_user", "mfa_recovery_codes")
    op.drop_column("app_user", "mfa_enrolled_at")
    op.drop_column("app_user", "mfa_secret")
