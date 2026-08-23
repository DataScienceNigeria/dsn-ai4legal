"""One test per Phase G feature, as instructed.

Each of these covers the rule that would be expensive to get wrong: house style
is enforced rather than suggested, auto-issue stops at the first sign of
deviation, and an imported template arrives as a proposal rather than as house
position.
"""

import zipfile
from datetime import date
from io import BytesIO

from app.services import autoissue
from app.services.docx_import import extract
from app.services.generation import GeneratedBlock, GenerationResult, render_docx
from app.services.style import HouseStyle, enforce


def test_house_style_rewrites_the_draft_and_reports_what_it_changed():
    """A violation that is corrected silently is as bad as one that is missed,
    so every rewrite lands in the style report (LOP-M05-US-03)."""
    blocks = [
        {
            "key": "b1",
            "number": 1,
            "text": "The fee is ₦2500000, payable by 01/03/2026 under clause 7.",
        },
        {"key": "b2", "number": 3, "text": "This agreement is governed by Nigerian law."},
    ]

    corrected, report = enforce(blocks, HouseStyle())

    assert "NGN 2,500,000" in corrected[0]["text"]
    assert "1 March 2026" in corrected[0]["text"]
    assert "Clause 7" in corrected[0]["text"]
    assert "Federal Republic of Nigeria" in corrected[1]["text"]

    rules = {entry["rule"] for entry in report}
    assert {"currency", "date", "cross_reference", "governing_law"} <= rules

    numbering = [entry for entry in report if entry["rule"] == "numbering"]
    assert numbering and numbering[0]["corrected"] is False


def test_auto_issue_stops_at_the_first_sign_of_deviation():
    """Tier 1 auto-issue is defensible only while nothing deviates, and the
    refusal names every reason at once (LOP-M04-US-04)."""
    clean = autoissue.assess(
        auto_issue_configured=True,
        risk_tier="tier_1",
        template_status="approved",
        template_effective_date=date(2026, 1, 1),
        novel_clause_count=0,
        open_items=[],
        outstanding_approvals=0,
        counterparty_complete=True,
        today=date(2026, 8, 22),
    )
    assert clean.permitted

    blocked = autoissue.assess(
        auto_issue_configured=True,
        risk_tier="tier_2",
        template_status="draft",
        template_effective_date=None,
        novel_clause_count=2,
        open_items=["The signatory is not recorded."],
        outstanding_approvals=1,
        counterparty_complete=False,
        today=date(2026, 8, 22),
    )
    assert not blocked.permitted
    assert len(blocked.reasons) == 6


def test_an_imported_template_arrives_as_a_proposal_with_provenance():
    """Nothing imported becomes approved without a human, so the extractor
    produces candidates whose decision is pending (LOP-M03-US-07)."""
    source = render_docx(
        GenerationResult(
            blocks=[
                GeneratedBlock(
                    key="b1",
                    number="1",
                    heading="Confidentiality",
                    text="Each party keeps the other's confidential information secret.",
                    provenance="approved_clause",
                ),
                GeneratedBlock(
                    key="b2",
                    number="2",
                    heading="Limitation of Liability",
                    text="Neither party is liable for indirect loss.",
                    provenance="approved_clause",
                ),
            ],
            values={},
            checks=[],
            content_hash="",
            template_reference="TPL-TEST-v1.0",
            clause_references=[],
        ),
        "Imported agreement",
    )

    candidates, provenance = extract(source)
    named = {candidate.heading: candidate for candidate in candidates}

    assert named["Confidentiality"].proposed_category == "CONF"
    assert named["Limitation of Liability"].proposed_category == "LIAB"
    assert all(candidate.as_dict()["decision"] == "pending" for candidate in candidates)
    assert len(provenance["source_hash"]) == 64


def test_real_paper_splits_on_the_conventions_it_actually_uses():
    """The first import of real templates returned one candidate for a whole
    agreement. Three conventions were missing: Article headings, run-in
    headings that carry their own clause, and paper that numbers nothing and
    bolds its headings instead."""
    document = _docx(
        [
            ("Article II: Confidential Information", False),
            ("B. Exclusions. Information is not confidential where it was public.", False),
            ("1. INDEMNIFICATION. Intern shall hold the Sponsor harmless.", False),
            ("Security Deposit.", True),
            ("The Tenant shall pay a deposit before taking possession.", False),
        ]
    )

    candidates, _ = extract(document)
    by_heading = {candidate.heading: candidate for candidate in candidates}

    assert set(by_heading) == {
        "Confidential Information",
        "Exclusions",
        "INDEMNIFICATION",
        "Security Deposit",
    }
    assert by_heading["Confidential Information"].number == "II"
    assert by_heading["Exclusions"].text.startswith("Information is not confidential")
    assert by_heading["INDEMNIFICATION"].text == "Intern shall hold the Sponsor harmless."
    assert by_heading["Security Deposit"].text.startswith("The Tenant shall pay")


def _docx(paragraphs: list[tuple[str, bool]]) -> bytes:
    """A minimal Word file. Each paragraph is its text and whether it is bold."""
    body = "".join(
        f"<w:p><w:r>{'<w:rPr><w:b/></w:rPr>' if bold else ''}"
        f"<w:t xml:space='preserve'>{text}</w:t></w:r></w:p>"
        for text, bold in paragraphs
    )
    xml = (
        "<?xml version='1.0'?>"
        "<w:document xmlns:w='http://schemas.openxmlformats.org/wordprocessingml/2006/main'>"
        f"<w:body>{body}</w:body></w:document>"
    )
    buffer = BytesIO()
    with zipfile.ZipFile(buffer, "w") as archive:
        archive.writestr("word/document.xml", xml)
    return buffer.getvalue()

