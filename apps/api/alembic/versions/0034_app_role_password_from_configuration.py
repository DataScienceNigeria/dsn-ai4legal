"""The application's database role takes the configured password.

``0001`` created ``dsnlai_app`` with a literal password written into the
migration, so every deployment that ran it shares one password published in the
repository, and the value an operator set in ``DSNLAI_APP_DB_PASSWORD`` was
ignored. The first sign-in then failed against a database that looked correctly
configured.

Fixing ``0001`` only helps a database created after it, and this one exists
already, so the role is realigned here. Idempotent: it sets the role to
whatever configuration currently says, which on a fresh database is what
``0001`` has just used.

Revision ID: 0034
Revises: 0033
"""


from alembic import op
from app.core.config import settings

revision = "0034"
down_revision = "0033"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # A bind parameter cannot reach inside a DO block: the body is one opaque
    # string to the driver. DDL takes no parameters either, so the literal is
    # escaped the way SQL escapes one, by doubling the quote.
    password = settings.dsnlai_app_db_password.replace("'", "''")
    op.execute(f"ALTER ROLE dsnlai_app PASSWORD '{password}'")


def downgrade() -> None:
    """Nothing. A password is not restored to a published literal."""
