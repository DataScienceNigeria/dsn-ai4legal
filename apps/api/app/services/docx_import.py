"""Word import and candidate clause extraction, LOP-M03-US-07.

Existing templates are the accumulated judgement of the legal function, so the
import keeps what makes them ours: the source file is hashed and retained, every
candidate clause records the paragraph range it came from, and nothing becomes
approved without a clause owner saying so.

The breakdown is deterministic. A model would give a smoother split, but an
import that produces a different library on a second run is not provenance.
"""

from __future__ import annotations

import hashlib
import re
import zipfile
from dataclasses import dataclass
from io import BytesIO
from xml.etree import ElementTree

WORD_NS = "{http://schemas.openxmlformats.org/wordprocessingml/2006/main}"

CATEGORY_HINTS: tuple[tuple[str, tuple[str, ...]], ...] = (
    ("LIAB", ("limitation of liability", "liability", "indemnit")),
    ("CONF", ("confidential", "non-disclosure", "secrecy")),
    ("DP", ("data protection", "personal data", "privacy", "ndpa", "gdpr")),
    (
        "IP",
        ("intellectual property", "ownership of", "copyright", "licence", "license", "invention"),
    ),
    ("TERM", ("termination", "term and termination", "expiry")),
    ("LAW", ("governing law", "jurisdiction")),
    ("DISP", ("dispute", "arbitration", "mediation")),
    ("PAY", ("payment", "fees", "invoice", "consideration", "rent", "deposit")),
    ("WARR", ("warrant", "representation")),
    ("FM", ("force majeure",)),
    ("ASSN", ("assignment", "novation")),
    ("NOTC", ("notices",)),
)

HEADING_PATTERN = re.compile(r"^\s*(\d+(?:\.\d+)*)[\.\)]?\s+(.{2,120})$")

#: Real templates do not all number their clauses 1, 1.1, 1.2. Three further
#: conventions turned up the first time actual paper was imported, and without
#: them a whole agreement came back as one candidate clause.
#:
#: "Article IV: Entire Agreement", and its Section and Clause variants. Split
#: by hand rather than by one regex, because the single expression that covered
#: every keyword and every numeral form was harder to read than the thing it
#: was matching.
ARTICLE_WORDS = frozenset(
    {"article", "section", "clause", "schedule", "annex", "annexure", "appendix"}
)
ARTICLE_NUMERAL = re.compile(r"^([ivxlcdm]+|\d+(?:\.\d+)*|[a-z])[:.)\u2013\u2014-]?$", re.I)

#: "B. Exclusions. For the purposes of this Agreement, ..." and its numbered
#: form, "1. KNOWLEDGE AND EXPERIENCE. The Sponsor shall be ...". The heading
#: runs on into the clause, so what follows the full stop is body, not title.
LETTERED_PATTERN = re.compile(
    r"^\s*\(?([\dA-Za-z.]{1,6})[.)]\s+([A-Z][^.]{2,70})\.\s+(\S.*)$"
)

#: A line of underscores is a fill-in blank, and a checkbox is an option. Both
#: are sometimes bold, and neither is a heading.
FILLER_PATTERN = re.compile(r"^[\s_\u2610\u2611\u2612.:-]*$")

#: A Word template is prose. Anything claiming to expand past this is either
#: corrupt or a decompression bomb, and either way it is not a template.
MAX_DOCUMENT_XML_BYTES = 64 * 1024 * 1024


@dataclass(frozen=True)
class Paragraph:
    index: int
    text: str
    style: str
    #: Every run carrying text is bold. In paper that numbers nothing, this is
    #: what tells a clause heading apart from the clause.
    bold: bool = False


@dataclass
class CandidateClause:
    number: str
    heading: str
    text: str
    proposed_category: str | None
    first_paragraph: int
    last_paragraph: int
    confidence: float

    def as_dict(self) -> dict:
        return {
            "number": self.number,
            "heading": self.heading,
            "text": self.text,
            "proposed_category": self.proposed_category,
            "first_paragraph": self.first_paragraph,
            "last_paragraph": self.last_paragraph,
            "confidence": round(self.confidence, 2),
            "decision": "pending",
        }


class NotADocx(ValueError):
    """The upload is not a readable Word file."""


def read_paragraphs(data: bytes) -> list[Paragraph]:
    try:
        with zipfile.ZipFile(BytesIO(data)) as archive:
            entry = archive.getinfo("word/document.xml")
            if entry.file_size > MAX_DOCUMENT_XML_BYTES:
                raise NotADocx(
                    "That file expands to more than 64 MB of document body, which no template "
                    "does. It has not been read."
                )
            with archive.open(entry) as stream:
                xml = stream.read(MAX_DOCUMENT_XML_BYTES + 1)
            if len(xml) > MAX_DOCUMENT_XML_BYTES:
                raise NotADocx(
                    "That file expands past the 64 MB limit for a template body. It has not "
                    "been read."
                )
    except (zipfile.BadZipFile, KeyError) as exc:
        raise NotADocx(
            "That file could not be read as a Word document. Save it as .docx and try again."
        ) from exc

    lowered = xml[:4096].lower()
    if b"<!doctype" in lowered or b"<!entity" in lowered:
        raise NotADocx(
            "That file declares an XML document type or entity. A Word template does not, "
            "and it has not been parsed."
        )

    try:
        root = ElementTree.fromstring(xml)
    except ElementTree.ParseError as exc:
        raise NotADocx("That Word file has a document body that could not be parsed.") from exc

    body = root.find(f"{WORD_NS}body")
    paragraphs: list[Paragraph] = []
    counter = 0

    for node in list(body if body is not None else root):
        if node.tag == f"{WORD_NS}tbl":
            for paragraph_node in _table_paragraphs(node):
                built = _paragraph(paragraph_node, counter)
                if built:
                    paragraphs.append(built)
                    counter += 1
            continue
        for paragraph_node in node.iter(f"{WORD_NS}p"):
            built = _paragraph(paragraph_node, counter)
            if built:
                paragraphs.append(built)
                counter += 1

    return paragraphs


def _paragraph(node, index: int) -> Paragraph | None:
    text = "".join(run.text or "" for run in node.iter(f"{WORD_NS}t")).strip()
    if not text:
        return None
    style_node = node.find(f"{WORD_NS}pPr/{WORD_NS}pStyle")
    style = style_node.get(f"{WORD_NS}val", "") if style_node is not None else ""
    return Paragraph(index=index, text=text, style=style, bold=_all_runs_bold(node))


def _looks_like_parallel_blocks(rows: list[list]) -> bool:
    """Whether this table is two things side by side rather than a grid.

    A signature block is a two-column table with a party heading at the top of
    each column, and the two columns are two separate passages that happen to
    be laid out beside each other. Read in document order it comes out
    interleaved: both headings, then both first lines, then both second lines,
    so one party's block swallows the other's contents and the first heading
    ends up with nothing under it.

    A definitions table is also two columns and must not be transposed, since
    term and meaning belong on the same line. The heading is what tells them
    apart: a signature column is headed, a definition row is not.
    """
    if len(rows) < 2 or any(len(row) != 2 for row in rows):
        return False

    heads = ["".join(cell.itertext()).strip() for cell in rows[0]]
    if not all(heads):
        return False
    return all(
        head.endswith(":") or (head.isupper() and len(head.split()) <= 4) for head in heads
    )


def _table_paragraphs(table) -> list:
    """Every paragraph in a table, in an order that keeps a passage together.

    Column by column where the table is two passages side by side, row by row
    otherwise, which is what a grid means.
    """
    rows = [
        [cell for cell in row.findall(f"{WORD_NS}tc")]
        for row in table.findall(f"{WORD_NS}tr")
    ]
    rows = [row for row in rows if row]
    if not rows:
        return []

    if _looks_like_parallel_blocks(rows):
        ordered = []
        for column in range(len(rows[0])):
            for row in rows:
                if column < len(row):
                    ordered.extend(row[column].iter(f"{WORD_NS}p"))
        return ordered

    return list(table.iter(f"{WORD_NS}p"))


def _all_runs_bold(node) -> bool:
    """True when every run carrying text in this paragraph is bold.

    Partly bold is not a heading. A clause that emphasises two words in the
    middle of a sentence would otherwise be read as one.
    """
    runs = [
        run
        for run in node.iter(f"{WORD_NS}r")
        if "".join(t.text or "" for t in run.iter(f"{WORD_NS}t")).strip()
    ]
    if not runs:
        return False
    for run in runs:
        bold = run.find(f"{WORD_NS}rPr/{WORD_NS}b")
        if bold is None or bold.get(f"{WORD_NS}val") in {"0", "false"}:
            return False
    return True


@dataclass(frozen=True)
class Heading:
    number: str
    title: str
    #: What is left of the paragraph once the heading is taken off it. A run-in
    #: heading carries its own clause, and dropping the remainder would lose
    #: the text the clause is made of.
    remainder: str = ""


def _article_heading(text: str) -> Heading | None:
    """"Article IV: Entire Agreement", and the Section and Clause variants."""
    words = text.split()
    if len(words) < 2 or words[0].lower().rstrip(".:") not in ARTICLE_WORDS:
        return None

    numeral = ARTICLE_NUMERAL.match(words[1])
    if numeral is None:
        return None

    title = " ".join(words[2:]).lstrip(":.\u2013\u2014- ").strip()
    if len(title.split()) > 12:
        return None
    return Heading(numeral.group(1).upper(), title or text.strip())


def _is_heading(paragraph: Paragraph) -> Heading | None:
    text = paragraph.text

    if paragraph.style.lower().startswith("heading"):
        match = HEADING_PATTERN.match(text)
        if match:
            return Heading(match.group(1), match.group(2).strip())
        return Heading("", text)

    article = _article_heading(text)
    if article is not None:
        return article

    # Before the plain numbered pattern, which would otherwise swallow a short
    # run-in clause whole and call the entire paragraph a heading.
    match = LETTERED_PATTERN.match(text)
    if match:
        return Heading(match.group(1), match.group(2).strip(), match.group(3).strip())

    match = HEADING_PATTERN.match(text)
    if match and len(match.group(2).split()) <= 12:
        return Heading(match.group(1), match.group(2).strip())

    if paragraph.bold and 1 <= len(text.split()) <= 12 and not FILLER_PATTERN.match(text):
        return Heading("", text.rstrip(".").strip())

    if text.isupper() and 2 <= len(text.split()) <= 10:
        return Heading("", text.title())

    return None


def propose_category(heading: str, body: str) -> tuple[str | None, float]:
    """Map a candidate to a library category on the heading first.

    A hit in the heading is worth more than a hit in the body, because a body
    mention is as often a cross-reference to another clause as it is the clause
    itself.
    """
    lowered_heading = heading.lower()
    for category, hints in CATEGORY_HINTS:
        if any(hint in lowered_heading for hint in hints):
            return category, 0.9

    lowered_body = body.lower()[:600]
    for category, hints in CATEGORY_HINTS:
        if any(hint in lowered_body for hint in hints):
            return category, 0.55

    return None, 0.2


def extract(data: bytes) -> tuple[list[CandidateClause], dict]:
    paragraphs = read_paragraphs(data)
    if not paragraphs:
        raise NotADocx("That Word file has no readable paragraphs.")

    candidates: list[CandidateClause] = []
    current: dict | None = None

    for paragraph in paragraphs:
        heading = _is_heading(paragraph)
        if heading is not None:
            if current:
                candidates.append(_close(current))
            current = {
                "number": heading.number,
                "heading": heading.title,
                "body": [heading.remainder] if heading.remainder else [],
                "first": paragraph.index,
                "last": paragraph.index,
            }
            continue
        if current is None:
            current = {
                "number": "",
                "heading": "Preamble",
                "body": [],
                "first": paragraph.index,
                "last": paragraph.index,
            }
        current["body"].append(paragraph.text)
        current["last"] = paragraph.index

    if current:
        candidates.append(_close(current))

    provenance = {
        "source_hash": hashlib.sha256(data).hexdigest(),
        "paragraph_count": len(paragraphs),
        "candidate_count": len(candidates),
        "method": "deterministic heading and numbering split",
    }
    return candidates, provenance


def _close(current: dict) -> CandidateClause:
    body = "\n\n".join(current["body"]).strip()
    category, confidence = propose_category(current["heading"], body)
    return CandidateClause(
        number=current["number"],
        heading=current["heading"],
        text=body,
        proposed_category=category,
        first_paragraph=current["first"],
        last_paragraph=current["last"],
        confidence=confidence,
    )


def read_blocks(data: bytes) -> list[dict]:
    """The document as numbered blocks, in the shape review reads.

    Counterparty paper arrives as a file and has to become something the
    playbook comparison can walk clause by clause. The split is the same
    deterministic heading and numbering split used for a template import, so
    what a reviewer sees on screen is what the model was given.

    Every block is marked as counterparty text. That is the whole point of
    keeping it apart from a generated document: nothing here came from an
    approved clause, and nothing here may be presented as house position.
    """
    candidates, _ = extract(data)
    return [
        {
            "key": f"cp{index}",
            "number": candidate.number or str(index),
            "heading": candidate.heading,
            "text": candidate.text,
            "provenance": "counterparty",
            "source_reference": None,
            "novel": False,
        }
        for index, candidate in enumerate(candidates, start=1)
    ]
