"""The gate reports, it does not act.

Two things changed and both live in existing rows rather than in code. A
failing score no longer disables a capability, so any capability the harness
switched off on its own is holding a state nobody chose; those are handed back
to whoever owns them. And the management summary gate stops blocking: a
groundedness number is worth reporting, but refusing to produce a summary
because the last run scored 0.94 hands the legal lead a blank page instead of
a draft they were going to read line by line anyway.

Nothing here re-enables a capability a person disabled. Only the ones whose
reason names the harness are touched, because that is the only case where the
decision was never anybody's.

Revision ID: 0030
Revises: 0029
"""

from alembic import op

revision = "0030"
down_revision = "0029"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        """
        UPDATE capability
           SET state = 'enabled',
               disabled_reason = NULL
         WHERE state = 'disabled'
           AND disabled_reason LIKE 'Scored %Disabled automatically.'
        """
    )
    op.execute(
        """
        UPDATE capability
           SET gate_enforced = FALSE
         WHERE code = 'management_summary'
        """
    )


def downgrade() -> None:
    op.execute(
        """
        UPDATE capability
           SET gate_enforced = TRUE
         WHERE code = 'management_summary'
        """
    )
