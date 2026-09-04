"""What an issue turned into.

Section 15 of the guide says the department reports and Legal decides. It does
not say what a decision produces, so nothing did: raise, triage, resolve, and
the record ended at a paragraph saying somebody had dealt with it. That is an
account of a problem rather than an account of what was done about it, and the
next person to ask about the agreement had a note and no chain.

Four things a contract problem actually becomes, and a fifth honest answer. The
change request link was already on the table from ``0025`` and nothing wrote
it; the matter and the obligation are new, and the termination outcome needs no
column because it is the closure checklist, which already carries its own note.

Revision ID: 0032
Revises: 0031
"""

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import UUID as PgUUID

revision = "0032"
down_revision = "0031"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("contract_issue", sa.Column("outcome", sa.String(24), nullable=True))
    op.add_column(
        "contract_issue",
        sa.Column("outcome_matter_id", PgUUID(as_uuid=True), nullable=True),
    )
    op.add_column(
        "contract_issue",
        sa.Column("outcome_obligation_id", PgUUID(as_uuid=True), nullable=True),
    )
    op.create_foreign_key(
        "fk_contract_issue_outcome_matter",
        "contract_issue", "matter", ["outcome_matter_id"], ["id"], ondelete="SET NULL",
    )
    op.create_foreign_key(
        "fk_contract_issue_outcome_obligation",
        "contract_issue", "obligation", ["outcome_obligation_id"], ["id"],
        ondelete="SET NULL",
    )
    op.create_index("ix_contract_issue_outcome", "contract_issue", ["outcome"])
    op.create_index(
        "ix_contract_issue_outcome_matter_id", "contract_issue", ["outcome_matter_id"]
    )
    op.create_index(
        "ix_contract_issue_outcome_obligation_id",
        "contract_issue", ["outcome_obligation_id"],
    )


def downgrade() -> None:
    op.drop_index("ix_contract_issue_outcome_obligation_id", table_name="contract_issue")
    op.drop_index("ix_contract_issue_outcome_matter_id", table_name="contract_issue")
    op.drop_index("ix_contract_issue_outcome", table_name="contract_issue")
    op.drop_constraint(
        "fk_contract_issue_outcome_obligation", "contract_issue", type_="foreignkey"
    )
    op.drop_constraint(
        "fk_contract_issue_outcome_matter", "contract_issue", type_="foreignkey"
    )
    op.drop_column("contract_issue", "outcome_obligation_id")
    op.drop_column("contract_issue", "outcome_matter_id")
    op.drop_column("contract_issue", "outcome")
