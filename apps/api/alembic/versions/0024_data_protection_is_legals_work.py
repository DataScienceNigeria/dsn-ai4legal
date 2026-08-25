"""There is no data protection officer role, because there is no such person.

The DPO in an organisation this size is not a job somebody holds and nothing
else. It is a hat: the team lead building the product knows what it does with
personal data and writes the assessment, and legal reads it, scores it and
decides. A separate ``privacy`` role made every DPIA wait on one calendar and
gave one seconded person a permission nobody else in the department had.

So the role goes. Everything it gated is legal's: reading a submitted
assessment, scoring a section, the final go-ahead, modify or stop, and closing
it out. Everything it could see alongside legal, the clause library, the
counterparty register, the capability list, the connector list, Ask, it saw
because it was legal-adjacent, and legal already sees.

Users holding it become legal staff. Fatima Bello, seeded as the DPO and the
accountable owner of the NDPC filing, keeps both the filing and the work.

Revision ID: 0024
Revises: 0023
"""

from collections.abc import Sequence

from alembic import op

revision: str = "0024"
down_revision: str | None = "0023"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # A user holding both keeps one.
    op.execute(
        """
        UPDATE app_user
        SET roles = (
            SELECT array_agg(DISTINCT CASE WHEN role = 'privacy' THEN 'counsel' ELSE role END)
            FROM unnest(roles) AS role
        )
        WHERE 'privacy' = ANY(roles)
        """
    )

    op.execute(
        "UPDATE capability SET confirming_role = 'counsel' "
        "WHERE confirming_role = 'privacy'"
    )
    op.execute("UPDATE approval SET approver_role = 'counsel' WHERE approver_role = 'privacy'")

    # Notifications need nothing. ``raise_for_role`` resolves a role to people
    # when it writes, so a bell already in someone's list names them, not a role.

    # Audit rows are not touched. They record what was true when they were
    # written, and the role existed then.


def downgrade() -> None:
    """Not reversed. Which of the merged users held the data protection role is
    no longer recorded, and inventing the split back would give somebody a
    permission they may never have had."""
