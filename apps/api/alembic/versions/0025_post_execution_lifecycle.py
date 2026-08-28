"""A contract has a life after it is signed.

The platform stopped at execution. An executed agreement was archived and
nothing acknowledged that most of a contract's life happens afterwards: it is
performed, it goes wrong, it is varied, and eventually it ends and somebody has
to give the data back. Sections 14 to 17 of the Guide to Engaging the Legal Team
describe all of it and none of it existed.

Three tables and a register.

``contract_issue`` is section 15. The user department runs the contract and tells
Legal promptly about breaches, disputes, performance concerns and material
changes. There was no channel: the department that noticed had an email address
and Legal had a memory.

``contract_change_request`` is section 16. No material change is implemented
informally. The important decision is that an approved change opens its own
matter rather than editing the contract, so a variation is drafted, approved,
signed and executed like any other document and the agreement that governed last
March keeps saying what it said. ``contract.amends_contract_id`` has existed
since 0002 with nothing to write it; this is what writes it.

``contract_closure_item`` is section 17, and it is the one with teeth. The
checklist is defined once in ``domain/lifecycle.py`` and materialised per
contract, fourteen items over five groups, each confirmed by a named person on a
date with a file. A contract cannot close while a required line is outstanding.
The line that matters is the return or deletion of personal data: the Nigeria
Data Protection Act requires it, the agreement will have said so, and it is the
one item that is a legal duty rather than housekeeping.

The register columns are section 14. ``user_department`` and ``contract_owner_id``
are the two whose absence explains why the register lived in a spreadsheet, since
a contract with no named owner is one nobody can be asked about.

Agreement types are rewritten to the guide's list in section 3C. They were free
strings written independently on the contract, the request type, the template,
the playbook and the template import, so five places invented their own
vocabulary and the library held a lease nothing could request.

Revision ID: 0025
Revises: 0024
"""

from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision: str = "0025"
down_revision: str | None = "0024"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

#: What the platform called things, and what the guide calls them. The three
#: imported templates the guide does not recognise land on ``other``, which is a
#: real answer, rather than being deleted along with the paper.
RENAMES = {
    "master_services_agreement": "service_agreement",
    "consultant_engagement": "consultancy_agreement",
    "lease_agreement": "other",
    "ip_assignment": "other",
    "cease_and_desist": "other",
    "unknown": "other",
}

TYPED_TABLES = ["contract", "request_type", "template", "playbook", "template_import"]

NEW_TABLES = ["contract_issue", "contract_change_request", "contract_closure_item"]


def _timestamps() -> list[sa.Column]:
    return [
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
    ]


def upgrade() -> None:
    # -------------------------------------------------- the register, section 14
    op.add_column(
        "contract",
        sa.Column("status", sa.String(24), nullable=False, server_default="executed"),
    )
    op.create_index("ix_contract_status", "contract", ["status"])
    op.add_column("contract", sa.Column("user_department", sa.String(128)))
    op.add_column("contract", sa.Column("contract_owner_id", postgresql.UUID(as_uuid=True)))
    op.create_index("ix_contract_contract_owner_id", "contract", ["contract_owner_id"])
    op.create_foreign_key(
        "fk_contract_contract_owner_id_app_user",
        "contract",
        "app_user",
        ["contract_owner_id"],
        ["id"],
        ondelete="SET NULL",
    )
    op.add_column("contract", sa.Column("payment_terms", sa.Text()))
    op.add_column("contract", sa.Column("key_deliverables", sa.Text()))
    op.add_column(
        "contract",
        sa.Column("milestones", postgresql.JSONB(), nullable=False, server_default="[]"),
    )
    op.add_column("contract", sa.Column("termination_deadline", sa.Date()))
    op.add_column("contract", sa.Column("remarks", sa.Text()))
    op.add_column("contract", sa.Column("closure_opened_at", sa.DateTime(timezone=True)))
    op.add_column("contract", sa.Column("closed_at", sa.DateTime(timezone=True)))
    op.add_column("contract", sa.Column("closure_note", sa.Text()))

    # An executed agreement still inside its term is active. One whose end date
    # has passed is not closed, because closure is a process somebody runs and
    # nobody has run it; it stays executed and will show as needing attention.
    op.execute(
        """
        UPDATE contract
        SET status = 'active'
        WHERE authoritative
          AND (end_date IS NULL OR end_date >= CURRENT_DATE)
        """
    )

    # The last day notice can be given, where the paper says enough to work it
    # out. Overridable afterwards: a contract naming a specific date in words
    # beats the arithmetic.
    op.execute(
        """
        UPDATE contract
        SET termination_deadline = end_date - (notice_period_days || ' days')::interval
        WHERE end_date IS NOT NULL AND notice_period_days IS NOT NULL
        """
    )

    # ------------------------------------------------------ section 15, issues
    op.create_table(
        "contract_issue",
        *_timestamps(),
        sa.Column("entity", sa.String(3), nullable=False),
        sa.Column("reference", sa.String(32), nullable=False),
        sa.Column("contract_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("issue_type", sa.String(32), nullable=False),
        sa.Column("severity", sa.String(16), nullable=False),
        sa.Column("title", sa.String(255), nullable=False),
        sa.Column("description", sa.Text(), nullable=False),
        sa.Column("occurred_on", sa.Date()),
        sa.Column("evidence_document_id", postgresql.UUID(as_uuid=True)),
        sa.Column("evidence_note", sa.Text()),
        sa.Column("raised_by_id", postgresql.UUID(as_uuid=True)),
        sa.Column("assignee_id", postgresql.UUID(as_uuid=True)),
        sa.Column("status", sa.String(24), nullable=False, server_default="open"),
        sa.Column("resolution", sa.Text()),
        sa.Column("resolved_at", sa.DateTime(timezone=True)),
        sa.Column("resolved_by_id", postgresql.UUID(as_uuid=True)),
        sa.Column("change_request_id", postgresql.UUID(as_uuid=True)),
        sa.PrimaryKeyConstraint("id", name="pk_contract_issue"),
        sa.UniqueConstraint("reference", name="uq_contract_issue_reference"),
        sa.ForeignKeyConstraint(
            ["contract_id"],
            ["contract.id"],
            name="fk_contract_issue_contract_id_contract",
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["evidence_document_id"],
            ["document.id"],
            name="fk_contract_issue_evidence_document_id_document",
            ondelete="SET NULL",
        ),
        sa.ForeignKeyConstraint(
            ["raised_by_id"],
            ["app_user.id"],
            name="fk_contract_issue_raised_by_id_app_user",
            ondelete="SET NULL",
        ),
        sa.ForeignKeyConstraint(
            ["assignee_id"],
            ["app_user.id"],
            name="fk_contract_issue_assignee_id_app_user",
            ondelete="SET NULL",
        ),
        sa.ForeignKeyConstraint(
            ["resolved_by_id"],
            ["app_user.id"],
            name="fk_contract_issue_resolved_by_id_app_user",
            ondelete="SET NULL",
        ),
    )
    for column in ("entity", "contract_id", "issue_type", "severity", "status",
                   "raised_by_id", "assignee_id", "reference"):
        op.create_index(f"ix_contract_issue_{column}", "contract_issue", [column])

    # ---------------------------------------------- section 16, change requests
    op.create_table(
        "contract_change_request",
        *_timestamps(),
        sa.Column("entity", sa.String(3), nullable=False),
        sa.Column("reference", sa.String(32), nullable=False),
        sa.Column("contract_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("change_type", sa.String(32), nullable=False),
        sa.Column("rationale", sa.Text(), nullable=False),
        sa.Column("proposed_changes", sa.Text(), nullable=False),
        sa.Column("financial_effect", sa.String(16)),
        sa.Column("value_delta", sa.Numeric(18, 2)),
        sa.Column("value_currency", sa.String(3)),
        sa.Column("financial_note", sa.Text()),
        sa.Column("timeline_effect", sa.String(16)),
        sa.Column("proposed_end_date", sa.Date()),
        sa.Column("timeline_note", sa.Text()),
        sa.Column("requested_by_id", postgresql.UUID(as_uuid=True)),
        sa.Column("instrument", sa.String(24)),
        sa.Column("decision", sa.String(24), nullable=False, server_default="pending"),
        sa.Column("decision_reason", sa.Text()),
        sa.Column("decided_by_id", postgresql.UUID(as_uuid=True)),
        sa.Column("decided_at", sa.DateTime(timezone=True)),
        sa.Column("resulting_matter_id", postgresql.UUID(as_uuid=True)),
        sa.PrimaryKeyConstraint("id", name="pk_contract_change_request"),
        sa.UniqueConstraint("reference", name="uq_contract_change_request_reference"),
        sa.ForeignKeyConstraint(
            ["contract_id"],
            ["contract.id"],
            name="fk_contract_change_request_contract_id_contract",
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["requested_by_id"],
            ["app_user.id"],
            name="fk_contract_change_request_requested_by_id_app_user",
            ondelete="SET NULL",
        ),
        sa.ForeignKeyConstraint(
            ["decided_by_id"],
            ["app_user.id"],
            name="fk_contract_change_request_decided_by_id_app_user",
            ondelete="SET NULL",
        ),
        sa.ForeignKeyConstraint(
            ["resulting_matter_id"],
            ["matter.id"],
            name="fk_contract_change_request_resulting_matter_id_matter",
            ondelete="SET NULL",
        ),
    )
    for column in ("entity", "contract_id", "change_type", "decision",
                   "requested_by_id", "resulting_matter_id", "reference"):
        op.create_index(
            f"ix_contract_change_request_{column}", "contract_change_request", [column]
        )

    # An issue is often answered by changing the paper. Added after the target
    # table exists.
    op.create_foreign_key(
        "fk_contract_issue_change_request_id_contract_change_request",
        "contract_issue",
        "contract_change_request",
        ["change_request_id"],
        ["id"],
        ondelete="SET NULL",
    )

    # ----------------------------------------------------- section 17, closure
    op.create_table(
        "contract_closure_item",
        *_timestamps(),
        sa.Column("entity", sa.String(3), nullable=False),
        sa.Column("contract_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("item_key", sa.String(64), nullable=False),
        sa.Column("group_key", sa.String(32), nullable=False),
        sa.Column("status", sa.String(24), nullable=False, server_default="outstanding"),
        sa.Column("evidence_document_id", postgresql.UUID(as_uuid=True)),
        sa.Column("evidence_reference", sa.String(512)),
        sa.Column("note", sa.Text()),
        sa.Column("confirmed_by_id", postgresql.UUID(as_uuid=True)),
        sa.Column("confirmed_at", sa.DateTime(timezone=True)),
        sa.PrimaryKeyConstraint("id", name="pk_contract_closure_item"),
        sa.UniqueConstraint("contract_id", "item_key", name="uq_closure_item"),
        sa.ForeignKeyConstraint(
            ["contract_id"],
            ["contract.id"],
            name="fk_contract_closure_item_contract_id_contract",
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["evidence_document_id"],
            ["document.id"],
            name="fk_contract_closure_item_evidence_document_id_document",
            ondelete="SET NULL",
        ),
        sa.ForeignKeyConstraint(
            ["confirmed_by_id"],
            ["app_user.id"],
            name="fk_contract_closure_item_confirmed_by_id_app_user",
            ondelete="SET NULL",
        ),
    )
    for column in ("entity", "contract_id", "group_key", "status"):
        op.create_index(
            f"ix_contract_closure_item_{column}", "contract_closure_item", [column]
        )

    # ------------------------------------------------------------------ policy
    # Authorisation is enforced in the data layer, so a new table without a
    # policy is a hole rather than a table. All three carry an entity and hang
    # off a contract, which already narrows to its matter.
    op.execute("GRANT SELECT, INSERT, UPDATE, DELETE ON ALL TABLES IN SCHEMA public TO dsnlai_app")
    op.execute("GRANT USAGE, SELECT ON ALL SEQUENCES IN SCHEMA public TO dsnlai_app")
    op.execute("REVOKE UPDATE, DELETE, TRUNCATE ON audit_event FROM dsnlai_app")

    for table in NEW_TABLES:
        op.execute(f"ALTER TABLE {table} ENABLE ROW LEVEL SECURITY")
        op.execute(f"ALTER TABLE {table} FORCE ROW LEVEL SECURITY")
        op.execute(
            f"""
            CREATE POLICY {table}_entity_scope ON {table}
            USING (
                dsnlai_bypass() OR (
                    entity = ANY (dsnlai_entities())
                    AND EXISTS (
                        SELECT 1 FROM contract c
                        WHERE c.id = {table}.contract_id
                          AND (c.matter_id IS NULL OR dsnlai_can_see_matter(c.matter_id))
                    )
                )
            )
            WITH CHECK (dsnlai_bypass() OR entity = ANY (dsnlai_entities()))
            """
        )

    # ------------------------------------------------- section 3C, the vocabulary
    for old, new in RENAMES.items():
        for table in TYPED_TABLES:
            op.execute(
                f"UPDATE {table} SET agreement_type = '{new}' WHERE agreement_type = '{old}'"
            )

    # A request type names the agreement it produces, and its own code named the
    # errand rather than the paper. The label the requester reads is unchanged.
    op.execute(
        "UPDATE request_type SET agreement_type = 'consultancy_agreement' "
        "WHERE code = 'consultant_engagement'"
    )
    op.execute(
        "UPDATE request_type SET agreement_type = 'other' WHERE code = 'something_else'"
    )


def downgrade() -> None:
    for table in reversed(NEW_TABLES):
        op.execute(f"DROP POLICY IF EXISTS {table}_entity_scope ON {table}")
    op.drop_constraint(
        "fk_contract_issue_change_request_id_contract_change_request",
        "contract_issue",
        type_="foreignkey",
    )
    op.drop_table("contract_closure_item")
    op.drop_table("contract_change_request")
    op.drop_table("contract_issue")

    for column in (
        "closure_note",
        "closed_at",
        "closure_opened_at",
        "remarks",
        "termination_deadline",
        "milestones",
        "key_deliverables",
        "payment_terms",
        "contract_owner_id",
        "user_department",
        "status",
    ):
        op.drop_column("contract", column)

    # The old vocabulary is not restored. Three of the six renames collapsed
    # into ``other`` and which template was a lease and which an IP assignment
    # is no longer recorded, so inventing the split back would mistype paper.
