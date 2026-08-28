"""The Contract Brief, section 3 of the Guide to Engaging the Legal Team.

The guide lists nine groups of information, A to I, that a request has to carry
before Legal can act on it, and warns that an incomplete brief means a round
trip. The platform asked five questions on its fullest request type, so almost
every request was incomplete by the guide's own standard and the round trip
happened by default.

Defined once here and merged into every request type rather than written out six
times, because a brief written six times disagrees with itself the first time
one copy is edited. A request type keeps the questions that are particular to it
and inherits the rest.

Grouped because twenty-five fields in one column is a form nobody finishes.
Groups A and C are the ones Legal cannot start without, so they are asked
plainly; the rest are marked ``progressive`` and sit behind optional detail,
which is the existing mechanism for exactly this.
"""

from __future__ import annotations

#: The guide's own lettering, kept so a reader can trace a field back to it.
SECTIONS: list[dict] = [
    {"key": "brief", "letter": "A", "title": "The engagement", "intent": "What this is and why."},
    {
        "key": "party",
        "letter": "B",
        "title": "The other party",
        "intent": "Who exactly is on the other side. A trading name is not a legal name.",
    },
    {
        "key": "engagement",
        "letter": "C",
        "title": "Nature of the engagement",
        "intent": "What kind of paper this needs, and when it starts.",
    },
    {"key": "scope", "letter": "D", "title": "Scope", "intent": "What is being delivered."},
    {"key": "term", "letter": "E", "title": "Term", "intent": "How long it runs."},
    {
        "key": "commercial",
        "letter": "F",
        "title": "Payment and commercial terms",
        "intent": "What it costs, how it is paid, and where the money comes from.",
    },
    {
        "key": "responsibilities",
        "letter": "G",
        "title": "Responsibilities",
        "intent": (
            "What each side has to do. Both halves, because a one-sided list "
            "writes a one-sided contract."
        ),
    },
    {
        "key": "timeline",
        "letter": "H",
        "title": "Timeline",
        "intent": "Deadlines Legal has to work to, including ones nobody here set.",
    },
    {
        "key": "documents",
        "letter": "I",
        "title": "Supporting documents",
        "intent": "What already exists. Attach the files as well.",
    },
]

SECTIONS_BY_KEY = {section["key"]: section for section in SECTIONS}


def _field(
    name: str,
    label: str,
    kind: str,
    section: str,
    *,
    mandatory: bool = False,
    progressive: bool = True,
    help_text: str | None = None,
    unit: str | None = None,
) -> dict:
    field: dict = {
        "name": name,
        "label": label,
        "type": kind,
        "section": section,
        "mandatory": mandatory,
        "progressive": progressive,
    }
    if help_text:
        field["help_text"] = help_text
    if unit:
        field["unit"] = unit
    return field


#: What every request carries, whatever kind it is.
#:
#: A request type's own fields come first and are not touched; these are added
#: after, and any name a request type already uses is left alone rather than
#: overwritten, because the specific question is usually better worded than the
#: general one.
COMMON: list[dict] = [
    # A. The engagement.
    _field(
        "background",
        "Background and context",
        "text",
        "brief",
        progressive=False,
        help_text="How this came about, and anything Legal would otherwise have to ask you.",
    ),
    _field(
        "expected_outcome",
        "What does success look like",
        "text",
        "brief",
        help_text="What you expect to have at the end of it.",
    ),
    # B. The other party.
    _field(
        "counterparty_legal_name",
        "Their full legal name",
        "string",
        "party",
        progressive=False,
        help_text=(
            "As registered, not the trading name. An agreement signed with the wrong "
            "legal entity binds nobody."
        ),
    ),
    _field(
        "counterparty_kind",
        "Are they an individual or an organisation",
        "string",
        "party",
        progressive=False,
    ),
    _field("counterparty_address", "Registered or business address", "text", "party"),
    _field("counterparty_contact", "Contact person and email", "string", "party"),
    _field(
        "counterparty_registration",
        "Registration number",
        "string",
        "party",
        help_text="RC number or equivalent, where they are an organisation.",
    ),
    _field("counterparty_website", "Website", "string", "party"),
    # C. Nature of the engagement.
    _field(
        "engagement_title",
        "Title of the engagement",
        "string",
        "engagement",
        progressive=False,
        help_text="What this arrangement would be called in an email.",
    ),
    _field("commencement_date", "Proposed start date", "date", "engagement", progressive=False),
    # D. Scope.
    _field(
        "deliverables",
        "Deliverables and milestones",
        "text",
        "scope",
        help_text="What is being produced, and by when.",
    ),
    # E. Term.
    _field("end_date", "Proposed end date", "date", "term"),
    _field("duration_months", "Duration", "number", "term", unit="months"),
    _field(
        "renewal_expected",
        "Is renewal expected",
        "boolean",
        "term",
        help_text=(
            "If it is, Legal writes the renewal terms in now rather than "
            "negotiating them later."
        ),
    ),
    _field("renewal_terms", "On what terms would it renew", "text", "term"),
    # F. Payment and commercial.
    _field(
        "payment_structure",
        "How is it paid",
        "string",
        "commercial",
        help_text="One payment, against milestones, monthly, or something else.",
    ),
    _field("payment_timeline", "When, and on what conditions", "text", "commercial"),
    _field(
        "funding_source",
        "Which budget or grant funds it",
        "string",
        "commercial",
        help_text="Finance confirms availability against this, so name the actual line.",
    ),
    _field("other_commercial", "Any other commercial arrangement", "text", "commercial"),
    # G. Responsibilities.
    _field("their_obligations", "What they have to do", "text", "responsibilities"),
    _field("our_obligations", "What we have to do", "text", "responsibilities"),
    # H. Timeline.
    _field("project_deadline", "Project deadline", "date", "timeline"),
    _field("execution_date", "When it needs to be signed by", "date", "timeline"),
    _field(
        "external_deadline",
        "Any external deadline Legal should know about",
        "text",
        "timeline",
        help_text="A funder's cut-off, a regulator's date, a board meeting. Say whose it is.",
    ),
    # I. Supporting documents.
    _field(
        "supporting_documents",
        "What already exists",
        "text",
        "documents",
        help_text=(
            "Proposal, scope of work, quote, procurement papers, an existing contract, "
            "their draft, technical specifications, previous correspondence. Attach them "
            "below as well."
        ),
    ),
]


def merged(existing: list[dict]) -> list[dict]:
    """A request type's own fields, plus the brief it does not already ask for.

    The type's own questions win on name. They are written for one errand and
    usually say it better than the general phrasing, and replacing them would
    change what people are asked in order to tidy a data structure.
    """
    taken = {field.get("name") for field in existing}
    out = [dict(field) for field in existing]
    for field in COMMON:
        if field["name"] in taken:
            continue
        out.append(dict(field))
    return out


def section_of(field: dict) -> str:
    """Which group a field belongs to, defaulting to the engagement itself.

    A request type's own fields predate the brief and carry no section, and they
    are the ones the requester came to answer, so they lead.
    """
    return field.get("section") or "brief"
