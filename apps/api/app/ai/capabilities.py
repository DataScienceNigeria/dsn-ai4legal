"""The named AI capabilities, PRD section 13.2.

Each capability declares its own instruction and output schema. Everything they
share, grounding, refusal, routing, logging and the prohibition on acting, is
enforced by the gateway rather than repeated here.
"""

from __future__ import annotations

from typing import Any

CLASSIFICATION_VALUES = [
    "action_required",
    "deadline_present",
    "awareness_only",
    "possible_contract",
    "privacy_issue",
    "vendor_issue",
    "unclear",
]

SEVERITY_VALUES = ["critical", "material", "minor", "acceptable"]


def _string_array() -> dict[str, Any]:
    return {"type": "array", "items": {"type": "string"}}


ASK_SCHEMA: dict[str, Any] = {
    "type": "object",
    "properties": {
        "paragraphs": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "text": {"type": "string"},
                    "cites": _string_array(),
                },
            },
        },
        "suppressed_statements": {
            "type": "integer",
            "description": (
                "How many statements you left out because no retrieved record "
                "supported them."
            ),
        },
        "note": {"type": "string"},
        "unsupported_segments": _string_array(),
    },
}

ASK_SYSTEM = """\
You answer questions about this organisation's legal position from its own
records. Answer in short paragraphs. Each paragraph cites the records it rests
on, using the reference in square brackets exactly as it appears in the
retrieved material.

A statement you cannot attribute to a retrieved record does not go in the
answer. Count it in suppressed_statements instead. Where the current house
position and a superseded one both appear, give the current position first and
label the superseded one.

You judge nothing about whether a position should change. You report what the
records say."""


CLASSIFY_SCHEMA: dict[str, Any] = {
    "type": "object",
    "properties": {
        "classification": {"type": "string", "enum": CLASSIFICATION_VALUES},
        "confidence": {"type": "number"},
        "reasoning": {"type": "string"},
        "implied_work": {
            "type": "boolean",
            "description": (
                "True when the message implies future legal work without assigning it."
            ),
        },
        "implied_work_phrase": {"type": "string"},
        "proposed_matter_type": {"type": "string"},
        "proposed_priority": {"type": "string", "enum": ["low", "normal", "high", "urgent"]},
        "acknowledgment_draft": {
            "type": "string",
            "description": (
                "An administrative acknowledgment. It confirms receipt and states what "
                "happens next. It contains no legal position, advice or commitment."
            ),
        },
        "missing_information": _string_array(),
        "unsupported_segments": _string_array(),
    },
}

CLASSIFY_SYSTEM = """\
You triage a shared legal mailbox. You classify one message, extract nothing
that is not present in it, and propose a next step for a person to confirm.

Nothing you produce is sent. The acknowledgment draft you write is
administrative: it confirms receipt, names what happens next, and gives no legal
position, advice, undertaking or commitment of any kind. If you cannot write one
without taking a position, leave it empty and say so in missing_information.

Classify implied work carefully. A message implies future legal work when it
describes something that will need legal input but assigns nothing. Quote the
phrase that made you think so."""


EXTRACT_SCHEMA: dict[str, Any] = {
    "type": "object",
    "properties": {
        "values": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "field_name": {
                        "type": "string",
                        "enum": [
                            "deadline",
                            "counterparty",
                            "apparent_requester",
                            "monetary_value",
                            "deliverable",
                            "referenced_document",
                            "party",
                        ],
                    },
                    "value": {"type": "string"},
                    "source_sentence": {
                        "type": "string",
                        "description": "The sentence this value came from, quoted exactly.",
                    },
                    "confidence": {"type": "number"},
                },
            },
        },
        "unsupported_segments": _string_array(),
    },
}

EXTRACT_SYSTEM = """\
You extract facts from a document or message. Every value you return quotes the
sentence it came from, exactly as it appears. A value you cannot quote a source
sentence for is not extracted.

Normalise dates to an ISO date where the text makes the year unambiguous, and
leave them as written where it does not. Every value is a suggestion for a
person to confirm field by field."""


DRAFT_SCHEMA: dict[str, Any] = {
    "type": "object",
    "properties": {
        "title": {"type": "string"},
        "clauses": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "number": {"type": "string"},
                    "heading": {"type": "string"},
                    "text": {"type": "string"},
                    "provenance": {
                        "type": "string",
                        "enum": [
                            "approved_clause",
                            "approved_fallback",
                            "prior_agreement",
                            "novel",
                        ],
                    },
                    "source_reference": {
                        "type": "string",
                        "description": (
                            "The reference of the approved clause, fallback or prior "
                            "agreement this clause came from. Empty only when the "
                            "provenance is novel."
                        ),
                    },
                },
            },
        },
        "open_items": {
            "type": "array",
            "items": {"type": "string"},
            "description": (
                "Missing facts, decisions requiring instruction, clauses with no "
                "approved position, and every assumption you made."
            ),
        },
        "prior_positions": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "reference": {"type": "string"},
                    "position": {"type": "string"},
                    "contradicts_draft": {"type": "boolean"},
                },
            },
        },
        "unsupported_segments": _string_array(),
    },
}

DRAFT_SYSTEM = """\
You produce a first pass of an agreement for counsel to work on. You build it
from the approved clauses supplied to you. Where an approved clause covers a
term, use it as written and mark its provenance and reference. Where no approved
position exists, you may write the clause, but you mark it novel and you list it
in open_items.

Novel text is a cost, not a convenience. Prefer an approved clause, then an
approved fallback, then a clause from a prior executed agreement, and only then
your own words.

Every assumption you make goes in open_items. An assumption you do not surface
there is a defect.

House style: define a term before using it, number clauses sequentially, refer
to clauses as "clause 4.1", name the parties consistently as they are named in
the matter record, write dates as "1 January 2026", and state governing law as
"the laws of the Federal Republic of Nigeria"."""


REVIEW_SCHEMA: dict[str, Any] = {
    "type": "object",
    "properties": {
        "findings": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "title": {"type": "string"},
                    "their_reference": {"type": "string"},
                    "clause_absent": {
                        "type": "boolean",
                        "description": (
                            "True when the playbook requires this clause and the draft "
                            "does not contain it at all."
                        ),
                    },
                    "severity": {"type": "string", "enum": SEVERITY_VALUES},
                    "clause_category": {"type": "string"},
                    "clause_version_ref": {"type": "string"},
                    "their_text": {"type": "string"},
                    "house_position": {"type": "string"},
                    "suggested_redline": {"type": "string"},
                    "matches_preapproved_fallback": {"type": "boolean"},
                    "fallback_rank": {"type": "integer"},
                    "reasoning": {"type": "string"},
                },
            },
        },
        "unsupported_segments": _string_array(),
    },
}

REVIEW_SYSTEM = """\
You compare a counterparty draft against this organisation's playbook and
approved clauses, and you rank what you find.

Report two kinds of finding. First, a term that differs from the house position.
Second, a required clause that is absent altogether. Absence is the finding
people miss, so check the playbook's required list explicitly and report every
one that is not present.

Severity is about consequence, not wording. Critical means uncapped or unbounded
exposure, a missing data protection term where personal data is involved, or a
loss of ownership. Material means a real commercial cost. Minor means a
departure that a pre-approved fallback already covers. Acceptable means it
differs but sits inside the house position.

Set matches_preapproved_fallback only when the counterparty's term is already
covered by one of the ranked fallbacks supplied to you, and name which one.
Every suggestion you write is a draft until a named person accepts it."""


OBLIGATION_SCHEMA: dict[str, Any] = {
    "type": "object",
    "properties": {
        "obligations": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "name": {"type": "string"},
                    "description": {"type": "string"},
                    "obligation_type": {
                        "type": "string",
                        "enum": [
                            "deliverable",
                            "payment_milestone",
                            "reporting",
                            "renewal",
                            "notice_period",
                            "termination_window",
                            "condition_precedent",
                        ],
                    },
                    "source_clause": {"type": "string"},
                    "source_quote": {
                        "type": "string",
                        "description": "The clause text this obligation came from.",
                    },
                    "due_date": {
                        "type": "string",
                        "description": (
                            "An ISO date, or an empty string where the clause sets an "
                            "event trigger rather than a date."
                        ),
                    },
                    "recurrence": {
                        "type": "string",
                        "enum": ["none", "monthly", "quarterly", "biannual", "annual"],
                    },
                    "event_driven": {"type": "boolean"},
                },
            },
        },
        "unsupported_segments": _string_array(),
    },
}

OBLIGATION_SYSTEM = """\
You read an executed agreement and propose the duties it creates, for a person
to confirm. Cover deliverables, payment milestones, reporting duties, renewal
dates, notice periods, termination windows and conditions precedent.

Every proposal quotes the clause it came from. Where a clause creates a duty but
sets no date, mark it event driven rather than inventing a date. Nothing you
propose becomes a task until Legal confirms it."""


SUMMARY_SCHEMA: dict[str, Any] = {
    "type": "object",
    "properties": {
        "delivery": _string_array(),
        "volumes": _string_array(),
        "turnaround": _string_array(),
        "blockers": _string_array(),
        "next_actions": _string_array(),
        "unsupported_segments": _string_array(),
    },
}

SUMMARY_SYSTEM = """\
You write a management update from the figures supplied to you. Every line
states a number that appears in the supplied data. You draw no conclusion the
figures do not support, and you make no forecast.

The Head of Legal reads and approves this before it is circulated."""


REGISTRY: dict[str, dict[str, Any]] = {
    "inbox_classification": {
        "system": CLASSIFY_SYSTEM,
        "schema": CLASSIFY_SCHEMA,
        "schema_name": "inbox_classification",
        "substantive": True,
    },
    "fact_extraction": {
        "system": EXTRACT_SYSTEM,
        "schema": EXTRACT_SCHEMA,
        "schema_name": "fact_extraction",
        "substantive": True,
    },
    "clause_retrieval_answer": {
        "system": ASK_SYSTEM,
        "schema": ASK_SCHEMA,
        "schema_name": "grounded_answer",
        "substantive": True,
    },
    "ai_first_draft": {
        "system": DRAFT_SYSTEM,
        "schema": DRAFT_SCHEMA,
        "schema_name": "first_draft",
        "substantive": True,
    },
    "deviation_detection": {
        "system": REVIEW_SYSTEM,
        "schema": REVIEW_SCHEMA,
        "schema_name": "playbook_review",
        "substantive": True,
    },
    "obligation_extraction": {
        "system": OBLIGATION_SYSTEM,
        "schema": OBLIGATION_SCHEMA,
        "schema_name": "obligations",
        "substantive": True,
    },
    "management_summary": {
        "system": SUMMARY_SYSTEM,
        "schema": SUMMARY_SCHEMA,
        "schema_name": "management_summary",
        "substantive": True,
    },
}
