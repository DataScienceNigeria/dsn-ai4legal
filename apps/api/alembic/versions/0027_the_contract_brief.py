"""Every request carries the Contract Brief, section 3 of the guide.

The guide lists nine groups of information, A to I, that a request has to hold
before Legal can act on it, and warns that an incomplete brief means a round
trip. The fullest request type asked five questions, so almost every request was
incomplete by the guide's own standard and the round trip happened by default.

The brief is defined once in ``domain/brief.py`` and merged into each request
type here. A request type's own questions win on name: they are written for one
errand, usually say it better than the general phrasing, and replacing them
would change what people are asked in order to tidy a data structure.

Only groups A, B and C are asked plainly. The rest are marked ``progressive``
and sit behind optional detail, because twenty-five fields in one column is a
form nobody finishes.

Revision ID: 0027
Revises: 0026
"""

import json
from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "0027"
down_revision: str | None = "0026"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    from app.domain import brief

    bind = op.get_bind()
    rows = bind.execute(
        sa.text("SELECT id, code, fields, mandatory_fields FROM request_type")
    ).fetchall()

    for row in rows:
        existing = list(row.fields or [])
        merged = brief.merged(existing)

        # The counterparty's legal name and the title of the engagement are what
        # Legal needs to open a matter at all, so they join the mandatory set
        # where the type does not already ask for the same thing.
        mandatory = list(row.mandatory_fields or [])
        names = {field["name"] for field in merged}
        for required in ("counterparty_legal_name", "engagement_title"):
            already_named = any(
                field.get("mandatory") and field["name"] in {"counterparty", required}
                for field in merged
            )
            if required in names and not already_named:
                mandatory.append(required)
                for field in merged:
                    if field["name"] == required:
                        field["mandatory"] = True

        bind.execute(
            sa.text(
                "UPDATE request_type SET fields = :fields, mandatory_fields = :mandatory "
                "WHERE id = :id"
            ),
            {
                "fields": json.dumps(merged),
                "mandatory": json.dumps(sorted(set(mandatory))),
                "id": row.id,
            },
        )


def downgrade() -> None:
    """The brief's fields are removed; the request types' own are untouched."""
    from app.domain import brief

    bind = op.get_bind()
    added = {field["name"] for field in brief.COMMON}
    rows = bind.execute(sa.text("SELECT id, fields, mandatory_fields FROM request_type")).fetchall()
    for row in rows:
        kept = [field for field in (row.fields or []) if field.get("name") not in added]
        mandatory = [name for name in (row.mandatory_fields or []) if name not in added]
        bind.execute(
            sa.text(
                "UPDATE request_type SET fields = :fields, mandatory_fields = :mandatory "
                "WHERE id = :id"
            ),
            {"fields": json.dumps(kept), "mandatory": json.dumps(mandatory), "id": row.id},
        )
