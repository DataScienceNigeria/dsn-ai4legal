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
    ("IP", ("intellectual property", "ownership of", "copyright", "licence", "license")),
    ("TERM", ("termination", "term and termination", "expiry")),
    ("LAW", ("governing law", "jurisdiction")),
    ("DISP", ("dispute", "arbitration", "mediation")),
    ("PAY", ("payment", "fees", "invoice", "consideration")),
    ("WARR", ("warrant", "representation")),
    ("FM", ("force majeure",)),
    ("ASSN", ("assignment", "novation")),
    ("NOTC", ("notices",)),
)

HEADING_PATTERN = re.compile(r"^\s*(\d+(?:\.\d+)*)[\.\)]?\s+(.{2,120})$")

#: A Word template is prose. Anything claiming to expand past this is either
#: corrupt or a decompression bomb, and either way it is not a template.
MAX_DOCUMENT_XML_BYTES = 64 * 1024 * 1024


@dataclass(frozen=True)
class Paragraph:
    index: int
    text: str
    style: str


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

    paragraphs: list[Paragraph] = []
    for index, node in enumerate(root.iter(f"{WORD_NS}p")):
        text = "".join(run.text or "" for run in node.iter(f"{WORD_NS}t")).strip()
        if not text:
            continue
        style_node = node.find(f"{WORD_NS}pPr/{WORD_NS}pStyle")
        style = style_node.get(f"{WORD_NS}val", "") if style_node is not None else ""
        paragraphs.append(Paragraph(index=index, text=text, style=style))
    return paragraphs


def _is_heading(paragraph: Paragraph) -> tuple[bool, str, str]:
    if paragraph.style.lower().startswith("heading"):
        match = HEADING_PATTERN.match(paragraph.text)
        if match:
            return True, match.group(1), match.group(2).strip()
        return True, "", paragraph.text

    match = HEADING_PATTERN.match(paragraph.text)
    if match and len(match.group(2).split()) <= 12:
        return True, match.group(1), match.group(2).strip()

    if paragraph.text.isupper() and 2 <= len(paragraph.text.split()) <= 10:
        return True, "", paragraph.text.title()

    return False, "", ""


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
        heading, number, title = _is_heading(paragraph)
        if heading:
            if current:
                candidates.append(_close(current))
            current = {
                "number": number,
                "heading": title,
                "body": [],
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
