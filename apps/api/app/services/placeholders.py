"""Bracket placeholders in imported templates, M03 and M04.

A template authored here declares its merge fields and writes them as
``{{counterparty}}``. A template that arrives as a Word file does not: it was
written for a person to fill in, so its blanks read ``[Company Name]`` and
``[Effective Date]``. Generation understood only the first form, so an imported
template produced a document with every blank still in it.

Rather than rewrite the stored body at import, the blanks are resolved at
generation. Two reasons. The Word file stays readable to the lawyer who opens
it, which is the whole point of holding the source document beside the blocks.
And every template already imported starts working without a data migration.

Nothing here guesses at a value. A placeholder resolves from a fact the record
already holds, or it is reported as missing and generation refuses. A document
that goes out with ``[Reseller Name]`` still in it is worse than one that was
never produced.
"""

from __future__ import annotations

import re

#: A blank a person was meant to fill in. Deliberately narrow: no newline, and
#: bounded length, so a bracketed cross-reference in prose ("[sic]", "[1]") or
#: a stray bracket in a long sentence is not mistaken for a merge field.
PLACEHOLDER = re.compile(r"\[([^\[\]\n]{2,60})\]")

#: Labels that are prose rather than blanks. A template that says "see Exhibit
#: A" inside brackets is not asking for a value.
NOT_A_BLANK = {"sic", "sign here", "signature", "seal", "initials", "page break"}


def normalise(label: str) -> str:
    """Reduce a human label to something matchable.

    "Company Name", "COMPANY NAME:" and "Company  Name" are one blank written
    three ways, and a template written by three people contains all three.
    """
    cleaned = re.sub(r"[^a-z0-9]+", " ", label.lower()).strip()
    return re.sub(r"\s+", " ", cleaned)


def slug(label: str) -> str:
    """The name this blank is asked for and supplied under."""
    return normalise(label).replace(" ", "_") or "value"


#: Each entry maps a fact the platform already holds to the labels a template
#: might use for it. Order matters: the first fact whose labels match wins, so
#: the more specific counterparty and company entries sit above the bare ones.
FACT_SYNONYMS: list[tuple[str, tuple[str, ...]]] = [
    (
        "counterparty_address",
        (
            "reseller address",
            "counterparty address",
            "client address",
            "customer address",
            "vendor address",
            "supplier address",
            "partner address",
            "distributor address",
            "licensee address",
            "second party address",
            "their address",
        ),
    ),
    (
        "our_address",
        (
            "company address",
            "our address",
            "principal place of business",
            "registered address",
            "first party address",
        ),
    ),
    (
        "counterparty",
        (
            "reseller name",
            "reseller",
            "counterparty name",
            "counterparty",
            "client name",
            "client",
            "customer name",
            "customer",
            "vendor name",
            "vendor",
            "supplier name",
            "supplier",
            "partner name",
            "distributor name",
            "distributor",
            "licensee name",
            "licensee",
            "second party",
            "other party",
        ),
    ),
    (
        "our_entity",
        (
            "company name",
            "company",
            "our entity",
            "our company",
            "our name",
            "supplier company",
            "licensor name",
            "licensor",
            "first party",
            "disclosing party",
        ),
    ),
    (
        "effective_date",
        (
            "effective date",
            "commencement date",
            "start date",
            "date",
            "agreement date",
            "date of this agreement",
        ),
    ),
    (
        "governing_law",
        (
            "state country",
            "state or country",
            "governing law",
            "jurisdiction",
            "country",
            "state",
            "applicable law",
        ),
    ),
    (
        "our_signatory_title",
        ("signatory title", "title", "our title", "designation"),
    ),
    (
        "our_signatory",
        ("signatory", "signatory name", "authorised signatory", "our signatory"),
    ),
    (
        "our_registration_number",
        ("company registration number", "rc number", "our registration number"),
    ),
    (
        "counterparty_registration_number",
        ("reseller registration number", "counterparty registration number"),
    ),
    (
        "counterparty_jurisdiction",
        ("counterparty jurisdiction", "reseller jurisdiction", "their jurisdiction"),
    ),
    (
        "matter_number",
        ("matter number", "reference", "agreement reference", "contract number"),
    ),
    (
        "value_amount",
        ("contract value", "value", "fee", "total fee", "amount", "price"),
    ),
    (
        "value_currency",
        ("currency",),
    ),
]

#: Built once. A label is looked up directly rather than scanned for.
_BY_LABEL: dict[str, str] = {
    label: fact for fact, labels in FACT_SYNONYMS for label in labels
}


def fact_for(label: str) -> str | None:
    """The fact this blank should be filled from, if the platform holds one."""
    return _BY_LABEL.get(normalise(label))


def find(text: str) -> list[str]:
    """Every blank in a piece of template text, in the order it appears."""
    return [
        match.group(1).strip()
        for match in PLACEHOLDER.finditer(text)
        if normalise(match.group(1)) not in NOT_A_BLANK
    ]


def in_body(body: list[dict]) -> list[dict]:
    """Every distinct blank in a template body, with what would fill it.

    Returned in document order and de-duplicated, because a template names the
    counterparty in the preamble and again in the signature block, and asking
    twice for one value is how two different answers get into one agreement.
    """
    seen: set[str] = set()
    found: list[dict] = []

    for block in body:
        for part in (block.get("heading", ""), block.get("text", "")):
            for label in find(part or ""):
                key = normalise(label)
                if key in seen:
                    continue
                seen.add(key)
                fact = fact_for(label)
                found.append(
                    {
                        "label": label,
                        "name": fact or slug(label),
                        "fact": fact,
                        #: True where the record already answers it, so the
                        #: interface only asks for the remainder.
                        "supplied": fact is not None,
                    }
                )
    return found


def resolve(text: str, values: dict[str, object]) -> tuple[str, list[str]]:
    """Fill the blanks in one piece of text.

    Returns the filled text and the labels that could not be filled. The caller
    decides what an unfilled blank means; generation refuses on it, and a
    preview shows it as outstanding.
    """
    missing: list[str] = []

    def substitute(match: re.Match[str]) -> str:
        label = match.group(1).strip()
        if normalise(label) in NOT_A_BLANK:
            return match.group(0)

        fact = fact_for(label)
        for key in filter(None, (fact, slug(label))):
            value = values.get(key)
            if value not in (None, ""):
                return str(value)

        missing.append(label)
        return match.group(0)

    return PLACEHOLDER.sub(substitute, text), missing


#: Where a fact comes from, so a refusal can say what to go and fix rather than
#: only what is absent. The distinction matters: an address missing from the
#: organisation record is one edit that fixes every future document, and a
#: territory missing from a template is a one-off somebody types.
FACT_SOURCE: dict[str, str] = {
    "our_entity": "organisation",
    "our_trading_name": "organisation",
    "our_address": "organisation",
    "our_registration_number": "organisation",
    "our_tax_identification_number": "organisation",
    "our_signatory": "organisation",
    "our_signatory_title": "organisation",
    "governing_law": "organisation",
    "counterparty": "counterparty",
    "counterparty_address": "counterparty",
    "counterparty_jurisdiction": "counterparty",
    "counterparty_registration_number": "counterparty",
    "matter_number": "matter",
    "value_amount": "matter",
    "value_currency": "matter",
    "effective_date": "matter",
}

WHERE_TO_FIX = {
    "organisation": (
        "Set it once under Administration, in Organisation, and every future "
        "document takes it from there."
    ),
    "counterparty": (
        "It comes from the counterparty record. Open the counterparty and add "
        "it, or link this matter to the right one."
    ),
    "matter": "It comes from the matter record.",
    "document": "The template asks for it and nothing on the record answers it, so type it here.",
}


def diagnose(labels: list[str]) -> list[dict]:
    """Say what each unfilled blank is and where it is fixed.

    A refusal that only names what is absent leaves the reader to work out
    whether it is a one-off to type or a gap in a record that will ask again on
    every document. This is derived, not inferred: the mapping is the same
    table generation resolves from, so what the message promises is what the
    next attempt will actually do.
    """
    out: list[dict] = []
    for label in labels:
        fact = fact_for(label)
        source = FACT_SOURCE.get(fact or "", "document")
        out.append(
            {
                "label": label,
                "name": fact or slug(label),
                "fact": fact,
                "source": source,
                "remedy": WHERE_TO_FIX[source],
            }
        )
    return out
