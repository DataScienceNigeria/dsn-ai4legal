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
        "answer": {
            "type": "string",
            "description": (
                "The answer, written as Markdown. Headings, bold and lists where they "
                "help a reader; ordinary connected prose where they do not. Cite inline "
                "with the reference in square brackets."
            ),
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
    "required": ["answer"],
}

ASK_SYSTEM = """\
You answer questions about this organisation's legal position from its own
records, and you write like a colleague answering across a desk.

Be comprehensive. Say everything the retrieved records support that bears on
the question, and organise it so a reader can find their way. A lawyer asking
about an agreement wants what it says: its term, what each party has to do,
what it costs, how it ends, what happens on breach, what was conceded and by
whom. Answer that fully. Brevity is not a virtue here; only irrelevance is.

Write in Markdown and write properly. Lead with the direct answer in a sentence
or two, then set out the detail. Use headings where an answer has parts, a list
where the content is a list, and connected prose everywhere else: one idea
leading into the next, not a stack of disconnected sentences. Where the records
are genuinely thin, a short answer is the honest one, and padding it is worse
than its being short.

Bold sparingly, for the figure or the name the reader came for. Bolding every
date and value in a sentence makes a form of it, and a form is harder to read
than the sentence was.

Cite inline, in square brackets, using the reference exactly as it appears in
the retrieved material, at the end of the clause or sentence it supports. Cite
where the claim is made rather than collecting every reference at the end. Do
not cite the same reference twice in one sentence, and do not restate a
reference the reader can already see.

What you may say is bounded by what you were given. A statement you cannot
attribute to a retrieved record does not go in the answer; count it in
suppressed_statements.

Gaps go in the note and nowhere else. Say what is missing once, plainly, in the
reader's terms, and without a citation: "the record does not say what the
notice period is", not "no source was retrieved". Do not list the gap in the
answer as well; a paragraph enumerating everything a record fails to mention is
not an answer, and reading it twice is worse than reading it once. Where the
gap is the answer, because the records hold nothing on the question, say that
in the answer and leave the note empty.

Where the current house position and a superseded one both appear, give the
current position first and label the superseded one.

You judge nothing about whether a position should change. You report what the
records say. Never invent a reference, a figure or a date."""


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
                    "title": {
                        "type": "string",
                        "description": "A plain heading for the finding, with no citation in it.",
                    },
                    "their_reference": {
                        "type": "string",
                        "description": (
                            "The clause number in the counterparty draft, such as "
                            "'clause 5'. Not the label of the material it arrived in."
                        ),
                    },
                    "clause_absent": {
                        "type": "boolean",
                        "description": (
                            "True when the playbook requires this clause and the draft "
                            "does not contain it at all."
                        ),
                    },
                    "severity": {"type": "string", "enum": SEVERITY_VALUES},
                    "clause_category": {
                        "type": "string",
                        "description": (
                            "The house clause category alone, such as TERM. At most 16 "
                            "characters, and never with a version reference appended."
                        ),
                    },
                    "clause_version_ref": {
                        "type": "string",
                        "description": (
                            "The approved clause version this is measured against, such "
                            "as CLS-TERM-v1.4. No square brackets."
                        ),
                    },
                    "their_text": {"type": "string"},
                    "house_position": {"type": "string"},
                    "suggested_redline": {
                        "type": "string",
                        "description": (
                            "Contract wording a lawyer can paste as it stands. No "
                            "citation, no commentary."
                        ),
                    },
                    "cites": _string_array(),
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


TITLE_SCHEMA: dict[str, Any] = {
    "type": "object",
    "properties": {
        "title": {
            "type": "string",
            "description": "Three to six words naming what the thread is about.",
        }
    },
    "required": ["title"],
}

TITLE_SYSTEM = """\
You name a saved thread from the question that opened it. Three to six words,
naming the subject rather than repeating the sentence: "Uncapped liability
precedent" not "Have we ever accepted uncapped liability".

No trailing punctuation, no quotation marks, and no words like question, query
or thread. Where the question names a counterparty or an agreement, keep that
name: it is what someone scanning a list of threads is looking for."""


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

The legal lead reads and approves this before it is circulated."""


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
    "conversation_title": {
        "system": TITLE_SYSTEM,
        "schema": TITLE_SCHEMA,
        "schema_name": "conversation_title",
        # Not substantive: naming a thread states nothing about the record, so
        # it needs no source and makes no claim anyone could rely on.
        "substantive": False,
    },
    "management_summary": {
        "system": SUMMARY_SYSTEM,
        "schema": SUMMARY_SCHEMA,
        "schema_name": "management_summary",
        "substantive": True,
    },
}
