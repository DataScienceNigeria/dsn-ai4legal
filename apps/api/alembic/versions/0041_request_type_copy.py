"""The legal team's wording for the request types.

The portal cards and the request forms read their titles, descriptions, labels
and hints from the request types, so new wording has to reach the rows a live
deployment already holds. A value is replaced only where it still reads exactly
as it was seeded: wording the Head of Legal has since changed is theirs, and
this leaves it alone. Downgrade restores the old wording on the same terms.

Revision ID: 0041
Revises: 0040
"""

import json

import sqlalchemy as sa

from alembic import op

revision = "0041"
down_revision = "0040"
branch_labels = None
depends_on = None

COLUMNS: dict[str, dict[str, tuple[str, str]]] = {
    "nda_mutual": {
        "business_label": ("We want to sign an NDA", "Sign an NDA"),
        "description": (
            "A mutual confidentiality agreement before sharing information.",
            "Use this before sharing confidential information.",
        ),
    },
    "consultant_engagement": {
        "business_label": ("We are engaging a consultant", "Engage a consultant"),
        "description": (
            "An individual or firm doing defined work for a fee.",
            "Request an agreement for an individual or firm providing defined services.",
        ),
    },
    "their_paper": {
        "business_label": ("A partner sent us their contract", "Review another party's contract"),
        "description": (
            "Review a document the other side drafted.",
            "Ask Legal to review a draft received from another party.",
        ),
    },
    "data_sharing": {
        "business_label": ("We are sharing or receiving data", "Share or receive data"),
        "description": (
            "A data-sharing or data-processing arrangement.",
            "Request a data-sharing or data-processing agreement.",
        ),
    },
    "partnership": {
        "business_label": ("We are entering a partnership", "Enter a partnership"),
        "description": (
            "A collaboration or partnership agreement.",
            "Request an agreement for a proposed collaboration.",
        ),
    },
}

FIELDS: dict[str, list[tuple[str, str, str | None, str]]] = {
    "nda_mutual": [
        ("counterparty", "label", "Who is it with", "Who is the other party?"),
        ("purpose", "label", "What will you share", "What information will be shared?"),
        ("required_date", "label", "When do you need it", "When do you need the NDA?"),
    ],
    "consultant_engagement": [
        ("scope", "label", "What will they do", "What work will they carry out?"),
        ("value_amount", "label", "Fee", "Total fee"),
        (
            "value_amount",
            "help_text",
            "The total fee, in naira, excluding VAT.",
            "Enter the total fee excluding VAT.",
        ),
        ("exclusivity", "label", "Is the engagement exclusive", "Is this engagement exclusive?"),
    ],
    "their_paper": [
        ("counterparty", "label", "Who sent it", "Who sent the contract?"),
        ("purpose", "label", "What is it for", "What is the contract for?"),
        ("required_date", "label", "When do they need a response", "When is your response due?"),
        ("their_paper", "label", "Their paper", "Their draft"),
        ("their_paper", "help_text", None, "Attach the contract received from the other party."),
    ],
    "data_sharing": [
        ("counterparty", "label", "Who is the other party", "Who is the other party?"),
        ("purpose", "label", "What is the data for", "Why is the data being shared?"),
        ("data_categories", "label", "What data is involved", "What data will be shared?"),
        ("required_date", "label", "When do you need it", "When do you need the agreement?"),
    ],
    "partnership": [
        ("counterparty", "label", "Who is the partner", "Who is the partner?"),
        ("purpose", "label", "What will you do together", "What will each party do?"),
        ("value_amount", "label", "Value, if any", "Estimated value, if known"),
        ("required_date", "label", "Target date", "Target start date"),
    ],
    "something_else": [
        ("purpose", "label", "What do you need", "What do you need from Legal?"),
        ("required_date", "label", "When do you need it", "When do you need it?"),
    ],
}


def _swap_fields(fields: list[dict], changes, forward: bool) -> bool:
    changed = False
    for name, key, old, new in changes:
        current, wanted = (old, new) if forward else (new, old)
        for field in fields:
            if field.get("name") != name or field.get(key) != current:
                continue
            if wanted is None:
                del field[key]
            else:
                field[key] = wanted
            changed = True
    return changed


def _apply(forward: bool) -> None:
    bind = op.get_bind()
    for code, columns in COLUMNS.items():
        for column, (old, new) in columns.items():
            current, wanted = (old, new) if forward else (new, old)
            bind.execute(
                sa.text(
                    f"UPDATE request_type SET {column} = :wanted "
                    f"WHERE code = :code AND {column} = :current"
                ),
                {"wanted": wanted, "code": code, "current": current},
            )

    for code, changes in FIELDS.items():
        row = bind.execute(
            sa.text("SELECT id, fields FROM request_type WHERE code = :code"), {"code": code}
        ).first()
        if row is None:
            continue
        fields = [dict(field) for field in (row.fields or [])]
        if _swap_fields(fields, changes, forward):
            bind.execute(
                sa.text("UPDATE request_type SET fields = CAST(:fields AS jsonb) WHERE id = :id"),
                {"fields": json.dumps(fields), "id": row.id},
            )


def upgrade() -> None:
    _apply(forward=True)


def downgrade() -> None:
    _apply(forward=False)
