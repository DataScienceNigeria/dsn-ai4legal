"""Reading a DPIA that was already written on the Word template.

Several projects filled the manual template before the platform existed. Asking
their leads to answer fifty-nine questions a second time is how a form gets
abandoned, so the document is read and the answers are lifted out.

The rule that shapes all of this: **it never guesses.** A question whose answer
cannot be found with confidence is left empty for the lead to fill in. An
imported assessment with the wrong text under the wrong question is worse than
an empty one, because the empty one is obviously unfinished and the wrong one
reads as complete and gets assessed.

How it works. The template is a sequence of question paragraphs, each followed
by the answer, sometimes with a bracketed tip in between and sometimes inside a
table cell. Every question here carries anchor phrases taken from the template's
own wording; a paragraph matching an anchor opens that question, and the
paragraphs after it up to the next recognised question are its answer. Anchors
rather than fuzzy similarity because a near-match on the wrong question is
exactly the failure the rule above forbids.
"""

from __future__ import annotations

import io
import re
import zipfile
from dataclasses import dataclass, field

from app.domain import dpia

MAX_BYTES = 16 * 1024 * 1024

#: Paragraph text that is never an answer.
#:
#: The template's tips are instructions to whoever fills it in, and the
#: placeholders are what an unfilled field looks like. Both sit exactly where an
#: answer would, so both have to be recognised or a blank template imports as a
#: fully answered assessment.
NOISE = re.compile(
    r"^\s*[\[(]\s*(tip|tips|insert|provide|describe|state|explain|allocate|choose|identify)\b",
    re.IGNORECASE,
)
PLACEHOLDER = re.compile(r"^\s*[\[<].{0,200}[\]>]\s*$")

#: The blank template's own guidance and labels, which sit exactly where an
#: answer would and are not answers.
#:
#: The bracketed tips are caught by ``NOISE``; these are the ones written as
#: plain prose, plus the label column of the document control table, which
#: flattens into the paragraph stream alongside its values.
TEMPLATE_ECHO = frozenset(
    {
        "version",
        "author",
        "dpia version number",
        "data protection officer contact details",
        "project description",
        "organisation type",
        "project/product name",
        "material information",
        "data controller",
        "data processor",
        "sub processor",
        "joint controller",
        "consent",
        "contractual obligation",
        "legal obligation",
        "vital interest",
        "public interest",
        "legitimate interest",
    }
)

#: Headings in the template that end an answer without starting a question.
BOUNDARIES = (
    "dpo's assessment",
    "dpo’s assessment",
    "dpo's final assessment",
    "dpo’s final assessment",
    "choose which one of the following",
    "dpo's recommendations",
    "dpo’s recommendations",
    "general background",
    "material information",
    "nature of envisaged",
    "lawful basis",
    "purposes & transparency",
    "purposes and transparency",
    "accuracy",
    "data minimisation",
    "integrity and confidentiality",
    "accountability",
    "individual rights",
    "cross-border",
    "identified vulnerabilit",
    "disparate outcome",
    "document control",
)

#: The template's own words for each question, lowercased.
#:
#: Each anchor must match at the **start** of a paragraph, allowing a leading
#: number or bullet. Matching anywhere in the paragraph is what made the first
#: version put transfer text under "author": the word appears in a dozen
#: sentences and in only one of them is it the question.
#:
#: Anchors shorter than fifteen characters are deliberately absent. A short
#: anchor cannot identify a question, and a wrong match is the one failure this
#: importer is not allowed to have.
ANCHORS: dict[str, tuple[str, ...]] = {
    "project_name": ("project/product name", "project or product name"),
    "project_description": ("project description",),
    "organisation_context": ("organisation type", "business context for the dpia"),
    "author": ("author of the dpia", "author:"),
    "dpo_contact": ("dpo name & contact", "dpo name and contact"),
    "why_required": ("why is a dpia is required", "why is a dpia required"),
    "risks": ("what are the risks presented by this new",),
    "mitigations": ("what steps have been taken to mitigate",),
    "processing_activities": ("explain the processing activities",),
    "our_role": ("what is dsn’s role", "what is dsn's role", "what is the organisation’s role"),
    "data_types": ("what types of personal data will we collect",),
    "data_sources": ("how will the data be sourced", "how  will the data be sourced"),
    "processing_method": ("will data be processed automatically",),
    "third_party_data": ("are we going to process data from any third party",),
    "secondary_use": ("is there a risk that the data will be used for other purposes",),
    "bases": (
        "what are the legal basis from processing",
        "what are the legal basis for processing",
    ),
    "prior_relationship": ("explain any prior relationships with the data subjects",),
    "purpose": ("what is the purpose of the processing",),
    "alternatives": ("briefly state if you considered alternative methods",),
    "alternatives_rejected": ("explain why these other methods would not be effective",),
    "privacy_notice": ("will you need to update our privacy notices",),
    "notice_alternative": ("if we are not updating our privacy notices",),
    "consent_mechanism": ("how are we obtaining consent",),
    "consent_records": ("are we maintaining appropriate records of the data subjects",),
    "consent_withdrawal": ("is there a process in place for data subjects to withdraw",),
    "lia_completed": ("if legitimate interests is our lawful basis",),
    "accuracy_confidence": ("are we satisfied the personal data",),
    "verification": (
        "if the personal data isn’t being obtained",
        "if the personal data isn't being obtained",
    ),
    "minimisation": ("have you done everything you can to minimise",),
    "retention_period": ("how long is the data to be kept", "how long will the data be kept"),
    "deletion": ("how will you ensure the personal data are deleted",),
    "schedule_update": ("do you need to update our retention and disposal schedule",),
    "storage_location": ("where will the personal data be stored", "where is the data stored"),
    "security_measures": ("explain the measures that are taken to keep the personal data secure",),
    "cyber_assessment": ("have you carried out a cybersecurity assessment",),
    "staff_measures": ("what policies, training or instructions",),
    "responsible_person": ("who will be responsible for the personal data",),
    "ropa_updated": ("have we updated our records of processing activities",),
    "dpa_signed": ("if we are using a data processor or sharing data",),
    "access": ("is there a means of providing the data subjects with access",),
    "rectification": ("what measures are in place to allow data subjects to update",),
    "restriction": ("can we restrict our processing of the personal data",),
    "objection": ("can we stop our processing of the personal data",),
    "portability": ("can we extract and transmit the personal data",),
    "erasure": ("can we erase the personal data",),
    "transfers_abroad": ("will data be transferred outside nigeria",),
    "destination_countries": ("if yes, specify the countries",),
    "transfer_basis": ("indicate the legal justification for transferring",),
    "non_whitelist_measures": ("if transferring to a country not on the",),
    "transfer_risks": ("considering the processing method and data types",),
    "grievance_mechanism": ("describe the specific mechanisms in the destination country",),
    "retain_locally": ("how practical and effective is it to retain the data",),
    "public_function": ("indicate if the processing is for public service",),
    "breach_risk": ("assess any potential risks of data breaches",),
    "vulnerability_index": ("provide an overview of the data subjects",),
    "rights_impact": ("is the proposed processing likely to impact on the fundamental rights",),
    "disparate_mitigation": ("if yes, what steps are being taken to mitigate",),
}

#: A paragraph that reads like a question ends the previous answer, whether or
#: not it is a question this form asks.
#:
#: This is what the first version was missing. The blank template is nothing but
#: questions, so with no way to recognise an unfamiliar one, every question
#: became the answer to the one above it. A template with nothing filled in has
#: to import as nothing filled in, and that is the test.
INTERROGATIVE = re.compile(
    r"^\s*(?:\d+[.)]\s*)?(what|who|when|where|why|how|will|are|is|do|does|can|could|should|"
    r"has|have|if|explain|describe|state|provide|identify|indicate|briefly|allocate|choose)\b",
    re.IGNORECASE,
)

YES = ("yes", "y", "true", "done", "completed", "complete", "affirmative")
NO = ("no", "n", "false", "not applicable", "n/a", "none", "not required")


@dataclass
class Imported:
    """What the document gave up, and what it did not."""

    answers: dict[str, object] = field(default_factory=dict)
    #: Which keys came from the document rather than from a person. Kept so the
    #: form can show provenance and the officer can tell the two apart.
    imported_keys: list[str] = field(default_factory=list)
    #: Questions the document had nothing for. Reported rather than hidden: a
    #: lead who is told what is missing fills it in, and one who is not assumes
    #: the form is done.
    missing: list[str] = field(default_factory=list)
    #: Text found under a heading the parser could not attribute. Surfaced so
    #: nothing in the document is silently dropped.
    unmatched: list[str] = field(default_factory=list)


class NotATemplate(ValueError):
    """The file is not a readable DPIA document, and the message says why."""


def _paragraphs(data: bytes) -> list[str]:
    """Every paragraph of the document in order, table cells included.

    Table cells matter: the template's document control block is a two-column
    table, so the project name lives in one and its label in the other.
    """
    try:
        archive = zipfile.ZipFile(io.BytesIO(data))
    except zipfile.BadZipFile as exception:
        raise NotATemplate(
            "That file is not a .docx. Word documents are zip archives and this one "
            "could not be opened."
        ) from exception

    if "word/document.xml" not in archive.namelist():
        raise NotATemplate("That .docx has no document body.")

    xml = archive.read("word/document.xml").decode("utf-8", errors="replace")

    # An entity declaration in a document nobody wrote by hand is an attack, not
    # a document. The same refusal the clause importer makes.
    if "<!ENTITY" in xml or "<!DOCTYPE" in xml:
        raise NotATemplate("That document declares XML entities and was not read.")

    out: list[str] = []
    for block in re.findall(r"<w:p[ >].*?</w:p>", xml, re.S):
        text = "".join(re.findall(r"<w:t[^>]*>(.*?)</w:t>", block, re.S))
        text = (
            text.replace("&amp;", "&")
            .replace("&lt;", "<")
            .replace("&gt;", ">")
            .replace("&quot;", '"')
            .replace("&apos;", "'")
        )
        text = re.sub(r"\s+", " ", text).strip()
        if text:
            out.append(text)
    return out


def _is_noise(text: str) -> bool:
    lowered = text.lower().strip().rstrip(":").strip()
    if NOISE.match(text) or PLACEHOLDER.match(text):
        return True
    if lowered in {".", "-", "n/a"} or lowered in TEMPLATE_ECHO:
        return True
    return "tip:" in lowered[:12] or "tips:" in lowered[:12]


#: A heading is short. Prose that happens to begin with a heading's word is not.
#:
#: "Accuracy" is a section heading and also how somebody starts a sentence about
#: accuracy, and matching on the prefix alone threw away a real answer that read
#: "Accuracy is measured per language to ensure no group is disadvantaged."
HEADING_LENGTH = 60


def _is_boundary(text: str) -> bool:
    lowered = text.lower().strip().rstrip(".:").strip()
    if len(lowered) > HEADING_LENGTH:
        return False
    return any(lowered.startswith(word) for word in BOUNDARIES)


#: Leading bullet, number or letter the template numbers its questions with.
LEAD = re.compile(r"^\s*(?:[\d]+[.)]\s*|[a-z][.)]\s*|[-•]\s*)?", re.IGNORECASE)


def _match(text: str) -> str | None:
    """Which question this paragraph is, if any.

    The anchor has to sit at the start of the paragraph, after any numbering.
    Matching anywhere is what put transfer text under "author" in the first
    version: the word appears in a dozen sentences and is the question in one.

    Longest anchor wins where two could apply, so a specific phrasing is never
    claimed by a shorter one that happens to be its prefix.
    """
    lowered = LEAD.sub("", text.lower(), count=1).strip()
    best: tuple[int, str] | None = None
    for key, anchors in ANCHORS.items():
        for anchor in anchors:
            if lowered.startswith(anchor) and (best is None or len(anchor) > best[0]):
                best = (len(anchor), key)
    return best[1] if best else None


def _looks_like_a_question(text: str) -> bool:
    """Whether this paragraph is asking rather than answering.

    Used to end an answer at a question the form does not ask. Without it the
    blank template imports as fully answered, because a document of nothing but
    questions makes each question the answer to the one above it.

    A trailing question mark is decisive. Otherwise an interrogative opening
    counts only on a short paragraph: a real answer often begins "We will" or
    "Data is", and a hundred and forty words of prose is not a question however
    it starts.
    """
    stripped = text.strip()
    if stripped.endswith("?"):
        return True
    return bool(INTERROGATIVE.match(stripped)) and len(stripped) < 140


def _coerce(key: str, text: str) -> object | None:
    """Fit the answer to the shape the question expects.

    A choice question whose recorded answer matches none of its options returns
    nothing rather than a value the form cannot render. The lead answers it
    themselves, which is the correct outcome: the document said something the
    form does not offer, and picking the nearest option would put words in
    somebody's mouth.
    """
    question = next(
        (q for section in dpia.SECTIONS for q in section.questions if q.key == key), None
    )
    if question is None:
        return None

    if question.kind == "boolean":
        head = text.lower().strip().rstrip(".")[:40]
        if any(head.startswith(word) for word in YES):
            return True
        if any(head.startswith(word) for word in NO):
            return False
        return None

    if question.kind in {"choice", "multi_choice"}:
        # Choices are never imported.
        #
        # Six of the fifty-nine questions offer a fixed set of options, and they
        # are the six where a wrong answer costs the most: whether we are
        # controller or processor, which lawful basis applies, what justifies a
        # transfer abroad. The template writes its options as prose lines under
        # the question, so a document that has been filled in and one that has
        # not look identical from here, and the platform's option wording is not
        # the template's. Reading the menu as the order is the confident wrong
        # answer this importer exists to avoid, so the lead picks. The prose is
        # not thrown away: it is offered back to them as what the document said.
        return None

    return text


def read(data: bytes) -> Imported:
    """Lift what the document holds into the form's own keys."""
    if len(data) > MAX_BYTES:
        raise NotATemplate("That document is larger than 16 MB and was not read.")

    paragraphs = _paragraphs(data)
    if len(paragraphs) < 10:
        raise NotATemplate(
            "That document has almost nothing in it. Check it is the completed DPIA "
            "rather than a cover sheet."
        )

    collected: dict[str, list[str]] = {}
    current: str | None = None
    stray: list[str] = []

    for text in paragraphs:
        matched = _match(text)
        if matched is not None:
            current = matched
            collected.setdefault(current, [])
            continue
        if _is_boundary(text) or _looks_like_a_question(text):
            current = None
            continue
        if _is_noise(text):
            continue
        if current is None:
            if len(text) > 60:
                stray.append(text)
            continue
        collected[current].append(text)

    result = Imported(unmatched=stray[:20])
    for section in dpia.SECTIONS:
        for question in section.questions:
            lines = collected.get(question.key) or []
            joined = "\n".join(lines).strip()
            value = _coerce(question.key, joined) if joined else None
            if value in (None, "", []):
                result.missing.append(question.label)
                continue
            result.answers[question.key] = value
            result.imported_keys.append(question.key)

    if not result.imported_keys:
        raise NotATemplate(
            "Nothing in that document matched the assessment. Check it is the DSN "
            "DPIA template rather than another form, and that the answers sit under "
            "the template's own questions."
        )
    return result
