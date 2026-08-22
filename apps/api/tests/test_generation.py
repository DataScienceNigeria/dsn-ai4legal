"""Deterministic document generation, PRD LOP-M04-US-03 and LOP-M03-US-04."""

import pytest

from app.core.errors import Refused
from app.services.generation import generate, render_docx

BODY = [
    {"key": "p", "number": "1", "heading": "Parties",
     "text": "Made between {{our_entity}} and {{counterparty}} on {{effective_date}}."},
    {"key": "c", "number": "2", "heading": "Confidentiality", "clause": "CLS-CONF-v3.1"},
    {"key": "d", "number": "3", "heading": "Data protection", "clause": "CLS-DPR-v1.4",
     "condition": "privacy_flag"},
]

VARIABLES = [
    {"name": "our_entity", "label": "Our entity", "type": "string", "mandatory": True},
    {"name": "counterparty", "label": "Counterparty", "type": "string", "mandatory": True},
    {"name": "effective_date", "label": "Effective date", "type": "date", "mandatory": True},
]

CLAUSES = {
    "CLS-CONF-v3.1": {"text": "Each party shall keep the other secrets.", "provenance": "approved_clause"},
    "CLS-DPR-v1.4": {"text": "Breach notification within 48 hours.", "provenance": "approved_clause"},
}

FACTS = {
    "our_entity": "EqualyzAI Limited",
    "counterparty": "Harmattan Analytics Limited",
    "effective_date": "2026-08-21",
    "privacy_flag": True,
}


def _run(facts):
    return generate(
        template_reference="TPL-NDA-v3.1",
        body=BODY,
        declared_variables=VARIABLES,
        facts=facts,
        clause_texts=CLAUSES,
    )


def test_the_same_facts_produce_a_byte_identical_file_and_a_changed_fact_changes_the_hash():
    """Reproducibility is what makes a generated document attributable, so the
    archive bytes and the hash must both be stable."""
    first, second = _run(FACTS), _run(FACTS)

    assert first.content_hash == second.content_hash
    assert render_docx(first, "NDA") == render_docx(second, "NDA")
    assert first.clause_references == ["CLS-CONF-v3.1", "CLS-DPR-v1.4"]

    without_privacy = _run({**FACTS, "privacy_flag": False})
    assert "Data protection" not in without_privacy.as_text()
    assert without_privacy.content_hash != first.content_hash


def test_a_missing_mandatory_variable_is_refused_rather_than_left_as_a_placeholder():
    with pytest.raises(Refused) as raised:
        _run({**FACTS, "counterparty": ""})

    assert any("Counterparty" in reason for reason in raised.value.reasons)
