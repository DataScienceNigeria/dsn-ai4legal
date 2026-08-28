"""External counsel reads a draft, and sees nothing else.

Stage 3 of the Guide to Engaging the Legal Team. Legal shares the draft with the
designated Legal Consultant, assesses their comments, and incorporates what it
accepts while holding the organisation's position. The consultant leads legal
review alongside Legal in the guide's responsibility matrix, which is a reader's
authority: they cannot approve, publish, sign or change anything.

Two parts, and the second is the one that matters.

``consultant_review`` records the ask, the answer and what Legal did with it.
The brief is required, because "please review" is how a consultant bills for
reading a whole agreement to answer a question about one clause. Legal's
assessment is a column of its own, so "incorporates the appropriate amendments
while maintaining DSN's position" is auditable rather than aspirational.

The row-level security change is the part that would be a hole otherwise. A
matter was visible to anyone in its entity unless it was restricted, so simply
adding the role would have shown external counsel the entire portfolio. A
consultant now sees a matter only where ``matter_access`` names them, restricted
or not. Access is a grant per matter, made when a review is asked for.

Revision ID: 0028
Revises: 0027
"""

from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision: str = "0028"
down_revision: str | None = "0027"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "consultant_review",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column("entity", sa.String(3), nullable=False),
        sa.Column("matter_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("document_id", postgresql.UUID(as_uuid=True)),
        sa.Column("consultant_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("requested_by_id", postgresql.UUID(as_uuid=True)),
        sa.Column("brief", sa.Text(), nullable=False),
        sa.Column("due_date", sa.Date()),
        sa.Column("status", sa.String(24), nullable=False, server_default="requested"),
        sa.Column("comments", sa.Text()),
        sa.Column("returned_at", sa.DateTime(timezone=True)),
        sa.Column("assessment", sa.Text()),
        sa.Column("assessed_at", sa.DateTime(timezone=True)),
        sa.Column("assessed_by_id", postgresql.UUID(as_uuid=True)),
        sa.PrimaryKeyConstraint("id", name="pk_consultant_review"),
        sa.ForeignKeyConstraint(
            ["matter_id"], ["matter.id"],
            name="fk_consultant_review_matter_id_matter", ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["document_id"], ["document.id"],
            name="fk_consultant_review_document_id_document", ondelete="SET NULL",
        ),
        sa.ForeignKeyConstraint(
            ["consultant_id"], ["app_user.id"],
            name="fk_consultant_review_consultant_id_app_user", ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["requested_by_id"], ["app_user.id"],
            name="fk_consultant_review_requested_by_id_app_user", ondelete="SET NULL",
        ),
        sa.ForeignKeyConstraint(
            ["assessed_by_id"], ["app_user.id"],
            name="fk_consultant_review_assessed_by_id_app_user", ondelete="SET NULL",
        ),
    )
    for column in ("entity", "matter_id", "consultant_id", "status"):
        op.create_index(f"ix_consultant_review_{column}", "consultant_review", [column])

    op.execute("GRANT SELECT, INSERT, UPDATE, DELETE ON ALL TABLES IN SCHEMA public TO dsnlai_app")
    op.execute("GRANT USAGE, SELECT ON ALL SEQUENCES IN SCHEMA public TO dsnlai_app")
    op.execute("REVOKE UPDATE, DELETE, TRUNCATE ON audit_event FROM dsnlai_app")

    op.execute("ALTER TABLE consultant_review ENABLE ROW LEVEL SECURITY")
    op.execute("ALTER TABLE consultant_review FORCE ROW LEVEL SECURITY")
    op.execute(
        """
        CREATE POLICY consultant_review_scope ON consultant_review
        USING (dsnlai_bypass() OR dsnlai_can_see_matter(matter_id))
        WITH CHECK (dsnlai_bypass() OR entity = ANY (dsnlai_entities()))
        """
    )

    # A consultant sees only what they were asked about.
    #
    # Everyone else keeps the rule they had: their entity, minus restricted
    # matters they are not named on. For a consultant the test inverts. Being in
    # the entity is not enough, because they are not of the organisation; being
    # named on the matter is the whole permission, and it is granted one matter
    # at a time when a review is requested.
    op.execute(
        """
        CREATE OR REPLACE FUNCTION dsnlai_can_see_matter(p_matter uuid) RETURNS boolean
        LANGUAGE sql STABLE AS $$
            SELECT dsnlai_bypass() OR EXISTS (
                SELECT 1 FROM matter m
                WHERE m.id = p_matter
                  AND m.entity = ANY (dsnlai_entities())
                  AND (
                      CASE WHEN 'consultant' = ANY (dsnlai_roles())
                           THEN EXISTS (
                               SELECT 1 FROM matter_access ma
                               WHERE ma.matter_id = m.id
                                 AND ma.user_id = dsnlai_current_user()
                           )
                           ELSE NOT m.restricted
                                OR EXISTS (
                                    SELECT 1 FROM matter_access ma
                                    WHERE ma.matter_id = m.id
                                      AND ma.user_id = dsnlai_current_user()
                                )
                      END
                  )
            )
        $$;
        """
    )


def downgrade() -> None:
    op.execute(
        """
        CREATE OR REPLACE FUNCTION dsnlai_can_see_matter(p_matter uuid) RETURNS boolean
        LANGUAGE sql STABLE AS $$
            SELECT dsnlai_bypass() OR EXISTS (
                SELECT 1 FROM matter m
                WHERE m.id = p_matter
                  AND m.entity = ANY (dsnlai_entities())
                  AND (
                      NOT m.restricted
                      OR EXISTS (
                          SELECT 1 FROM matter_access ma
                          WHERE ma.matter_id = m.id
                            AND ma.user_id = dsnlai_current_user()
                      )
                  )
            )
        $$;
        """
    )
    op.execute("DROP POLICY IF EXISTS consultant_review_scope ON consultant_review")
    op.drop_table("consultant_review")
