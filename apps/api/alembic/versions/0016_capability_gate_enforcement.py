"""Gates that block, and gates that only report.

A gate is an on/off switch, and a switch protects someone only where the output
goes somewhere a person will not check line by line. Obligation extraction is
the opposite: every proposal is confirmed one at a time before it becomes a
tracked task. Switching it off hands Legal an empty list instead of a
reviewable one, which is precisely the silent failure the gate was there to
prevent. So enforcement becomes a property of the capability.

The register also shipped with scores that were typed by hand. Obligation
extraction carried 0.89 against a gate of 0.93, dated 12 August, and told users
it had failed an evaluation that had never been run. A score is a measurement.
Anything not measured is cleared here and reads as not yet measured.

Revision ID: 0016
Revises: 0015
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "0016"
down_revision: str | None = "0015"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

UNENFORCED = ("obligation_extraction",)


def upgrade() -> None:
    op.add_column(
        "capability",
        sa.Column("gate_enforced", sa.Boolean(), nullable=False, server_default=sa.true()),
    )
    op.execute(
        "UPDATE capability SET gate_enforced = false WHERE code IN "
        f"({', '.join(repr(code) for code in UNENFORCED)})"
    )

    # A capability disabled by a score nobody measured is enabled again, and
    # the invented score goes with it. Runs that actually happened are in
    # evaluation_run; nothing there is touched, so a real failure survives.
    op.execute(
        """
        UPDATE capability c
        SET last_score = NULL,
            last_score_label = NULL,
            last_evaluated_at = NULL,
            state = CASE WHEN c.state = 'disabled' THEN 'enabled' ELSE c.state END,
            disabled_reason = NULL
        WHERE NOT EXISTS (
            SELECT 1 FROM evaluation_run r WHERE r.capability_id = c.id
        )
        """
    )


def downgrade() -> None:
    op.drop_column("capability", "gate_enforced")
