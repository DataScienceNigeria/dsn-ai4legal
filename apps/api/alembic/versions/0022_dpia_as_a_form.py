"""The DPIA is written by the people building the thing.

An assessment was something legal opened about a product. That is the wrong way
round: the person who knows what a system does with personal data is the team
lead who is building it, and asking legal to describe it first means legal
guessing and the lead correcting.

So a department lead raises it, answers it in the portal, and submits it. Only
then does it reach the data protection officer, who assesses each section,
scores it, recommends, and decides go ahead, modify or stop.

Four columns for that split. Who raised it, when it was submitted, the
officer's judgement section by section, and the decision. The answers already
had somewhere to live in ``captured``; the judgement did not, and putting it
there would have let either person's work overwrite the other's.

Revision ID: 0022
Revises: 0021
"""

from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision: str = "0022"
down_revision: str | None = "0021"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

COLUMNS = [
    sa.Column("raised_by_id", postgresql.UUID(as_uuid=True), nullable=True),
    sa.Column("submitted_at", sa.DateTime(timezone=True), nullable=True),
    sa.Column(
        "dpo_review",
        postgresql.JSONB(astext_type=sa.Text()),
        nullable=False,
        server_default="{}",
    ),
    sa.Column("final_decision", sa.String(16), nullable=True),
    sa.Column("final_decision_reason", sa.Text(), nullable=True),
]


def upgrade() -> None:
    for column in COLUMNS:
        op.add_column("assessment", column)
    op.create_foreign_key(
        "fk_assessment_raised_by_id_app_user",
        "assessment",
        "app_user",
        ["raised_by_id"],
        ["id"],
        ondelete="SET NULL",
    )
    op.create_index("ix_assessment_raised_by_id", "assessment", ["raised_by_id"])


def downgrade() -> None:
    op.drop_index("ix_assessment_raised_by_id", table_name="assessment")
    op.drop_constraint("fk_assessment_raised_by_id_app_user", "assessment", type_="foreignkey")
    for column in reversed(COLUMNS):
        op.drop_column("assessment", column.name)
