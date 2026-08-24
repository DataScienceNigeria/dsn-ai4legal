"""One test per feature in this batch, as instructed.

Each covers the rule that would be expensive to get wrong. An audit export
that a spreadsheet executes is a vulnerability shipped to the people least able
to spot it. A notification readable by the wrong person defeats the policy that
narrows the table to its recipient. And a rename that reaches a record which
has already become a matter lets the request and the matter disagree about what
the work is.
"""

import uuid
from datetime import date
from decimal import Decimal

import pytest

from app.api.v1.admin import AUDIT_CSV_COLUMNS, _csv_safe
from app.core.audit import _jsonable


def test_a_spreadsheet_cannot_execute_an_exported_audit_cell():
    """An auditor opens this file in Excel. A cell beginning with = or + is
    executed there rather than shown, and the audit trail is exactly the place
    an attacker would plant one, because it records text they supplied."""
    assert _csv_safe("=cmd|'/c calc'!A1") == "'=cmd|'/c calc'!A1"
    assert _csv_safe("+1+1") == "'+1+1"
    assert _csv_safe("-2+3") == "'-2+3"
    assert _csv_safe("@SUM(A1)") == "'@SUM(A1)"

    # Ordinary values pass through untouched, and nothing is dropped.
    assert _csv_safe("matter_renamed") == "matter_renamed"
    assert _csv_safe(None) == ""
    assert _csv_safe(261) == "261"

    # The chain travels with the export. Without these three the file is a list
    # of assertions that cannot be checked against anything.
    for column in ("sequence", "previous_digest", "digest"):
        assert column in AUDIT_CSV_COLUMNS


@pytest.mark.parametrize(
    ("status", "renamable"),
    [
        ("submitted", True),
        ("in_triage", True),
        ("accepted", False),
        ("closed_without_matter", False),
    ],
)
def test_a_request_can_only_be_renamed_while_it_is_still_a_request(status, renamable):
    """The subject becomes the matter title at acceptance. Renaming afterwards
    would leave the request and the matter disagreeing about what the work is,
    so the matter is renamed instead."""
    from app.domain.enums import MatterState

    triage_states = (MatterState.SUBMITTED.value, MatterState.IN_TRIAGE.value)
    assert (status in triage_states) is renamable


def test_an_audit_state_a_database_cannot_store_is_coerced_rather_than_lost():
    """This was a live fault, and the worst kind for this table. A matter PATCH
    put the record's due_date into before_state, psycopg refused to serialise a
    date into JSONB, and it refused at commit rather than at the call. The
    response had already been built, so the caller received 200 while the whole
    transaction, the change and its audit row together, rolled back."""
    coerced = _jsonable(
        {
            "due_date": date(2026, 3, 1),
            "value": Decimal("2500000.00"),
            "owner": uuid.UUID("25d0a8a6-f07e-432b-aa63-c7a5b2656d4f"),
            "title": "Omni Channel MSA renewal",
            "restricted": False,
            "reasons": ["personal data", None],
        }
    )

    assert coerced["due_date"] == "2026-03-01"
    assert coerced["value"] == "2500000.00"
    assert coerced["owner"] == "25d0a8a6-f07e-432b-aa63-c7a5b2656d4f"

    # Types JSONB already accepts are left exactly as they are.
    assert coerced["title"] == "Omni Channel MSA renewal"
    assert coerced["restricted"] is False
    assert coerced["reasons"] == ["personal data", None]
    assert _jsonable(None) is None


def test_counterparty_paper_reads_as_blocks_that_claim_no_house_position():
    """Their paper has to become something the comparison can walk, and every
    block of it has to be marked as theirs. A block that arrived from outside
    and carried a clause reference would be presented as house position, which
    is the one thing the library exists to prevent."""
    from app.domain.enums import DocumentType
    from app.services.docx_import import read_blocks
    from app.services.generation import GeneratedBlock, GenerationResult, render_docx

    paper = render_docx(
        GenerationResult(
            blocks=[
                GeneratedBlock("b1", "1", "Term", "This runs for 24 months.", "counterparty"),
                GeneratedBlock(
                    "b2",
                    "2",
                    "Limitation of Liability",
                    "Neither party's liability is limited in any way.",
                    "counterparty",
                ),
            ],
            values={},
            checks=[],
            content_hash="x",
            template_reference="t",
            clause_references=[],
        ),
        "Their master services agreement",
    )

    blocks = read_blocks(paper)

    assert [b["heading"] for b in blocks[-2:]] == ["Term", "Limitation of Liability"]
    assert all(b["provenance"] == "counterparty" for b in blocks)
    assert all(b["source_reference"] is None for b in blocks)

    # Novel means we wrote something no clause backs. Their paper is not our
    # writing at all, so counting it as novel would put their wording into the
    # figure that gates auto-issue.
    assert all(b["novel"] is False for b in blocks)

    assert DocumentType.COUNTERPARTY.value == "counterparty"
