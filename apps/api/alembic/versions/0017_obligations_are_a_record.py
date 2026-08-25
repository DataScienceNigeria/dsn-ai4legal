"""Obligations are a record of the agreement, not a queue for the legal team.

Extraction used to write every duty as ``proposed``, meaning "not yet a task",
because obligations were built as tracked work with an owner, a reminder and an
escalation ladder. Legal does not work those. A consultant's milestones belong
to the project manager and to finance; what legal holds is the reading of what
the agreement requires, produced when the parties disagree about it.

With no task waiting on a confirmation, ``proposed`` described nothing and
nothing could move an entry out of it. Everything extraction produced is
recorded as ``open``.

Confirmed work is untouched, and so is anything already completed.

Revision ID: 0017
Revises: 0016
"""

from collections.abc import Sequence

from alembic import op

revision: str = "0017"
down_revision: str | None = "0016"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # interaction_id is what marks an entry as extraction's own. A renewal task
    # somebody opened by hand carries none, and is left where it is.
    op.execute(
        """
        UPDATE obligation
        SET status = 'open'
        WHERE status = 'proposed' AND interaction_id IS NOT NULL
        """
    )


def downgrade() -> None:
    """Not reversed. Which entries were once proposed is not recorded, and
    guessing would put confirmed duties back into a state they never held."""
