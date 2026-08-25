"""The legal department is staff and a lead.

There were two staff roles, legal operations and counsel. The split modelled
somebody else's org chart: an in-house team of this size has people who do the
work and one person who leads them, and nothing in between. It bought exactly
one rule in the whole codebase, about which findings legal operations could
clear on its own, and that rule was the authority matrix written a second time
and worse, hard coded to one severity and one tier.

The matrix stays and does the work it was always doing: house and fallback 1
are staff, fallback 2 and above are the lead, and anything needing
re-authentication, publishing a clause version, changing a capability state,
restricting a matter, is the lead's. Two ranks, five weights of decision, which
is the right shape. What goes is the role that duplicated it.

``counsel`` survives as the stored value rather than being renamed. It is
written on users, capability rows and audit entries that already exist, and
renaming it would rewrite history to say something it did not say at the time.

Revision ID: 0021
Revises: 0020
"""

from collections.abc import Sequence

from alembic import op

revision: str = "0021"
down_revision: str | None = "0020"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # A user holding both keeps one. A user holding only legal operations
    # becomes staff, which is what they already were.
    op.execute(
        """
        UPDATE app_user
        SET roles = (
            SELECT array_agg(DISTINCT CASE WHEN role = 'legal_ops' THEN 'counsel' ELSE role END)
            FROM unnest(roles) AS role
        )
        WHERE 'legal_ops' = ANY(roles)
        """
    )

    # Who confirms a capability's output. Legal operations confirmed inbox
    # classification, extraction and obligations; legal staff does now.
    op.execute(
        "UPDATE capability SET confirming_role = 'counsel' "
        "WHERE confirming_role = 'legal_ops'"
    )

    # Approval chains name a role per step.
    op.execute(
        """
        UPDATE approval_chain_definition
        SET steps = replace(steps::text, '"legal_ops"', '"counsel"')::jsonb
        WHERE steps::text LIKE '%legal_ops%'
        """
    )
    op.execute("UPDATE approval SET approver_role = 'counsel' WHERE approver_role = 'legal_ops'")

    # Audit rows are not touched. They record what was true when they were
    # written, and a role that existed then existed.


def downgrade() -> None:
    """Not reversed. Which of the merged users were legal operations and which
    were counsel is no longer recorded, and inventing the split back would put
    people in a role they may never have held."""
