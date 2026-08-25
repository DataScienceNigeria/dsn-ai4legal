"""Findings, written into their Word file as comments.

Half of every negotiation happens somewhere this platform cannot see. Their
counsel works in Word, ours works in Google Docs, and the version that comes
back was argued over in a meeting nobody minuted. The platform's answer to that
is not to insist the work happens here. It is to send the findings out in the
one format every one of those tools already understands, and to read the
returned file to find out what happened.

So a review can be exported as their own document with a comment on each clause
it has something to say about. It opens in Word, in Pages, in Google Docs, in
whatever their counsel uses, with our position in the margin beside the clause
it is about, which is exactly what a marked-up draft looks like when a person
does it by hand.

The file is edited rather than rebuilt. Their numbering, their defined terms,
their formatting and their styles all survive, because the only thing added is
a comments part and an anchor around a paragraph. Rebuilding the document from
the blocks we split it into would hand them back a document that says the same
words in none of the same ways.

Anchors are found by text, not by paragraph number. Paragraph indexing depends
on which empty paragraphs and table cells you count, and a comment attached to
the wrong clause of a contract is worse than no comment.
"""

from __future__ import annotations

import io
import re
import zipfile
from dataclasses import dataclass

from app.services.docx_import import NotADocx

WORD_NS = "http://schemas.openxmlformats.org/wordprocessingml/2006/main"
COMMENTS_PART = "word/comments.xml"
COMMENTS_TYPE = (
    "application/vnd.openxmlformats-officedocument.wordprocessingml.comments+xml"
)
COMMENTS_REL = "http://schemas.openxmlformats.org/officeDocument/2006/relationships/comments"

#: A fixed date on every comment, for the same reason the archive carries a
#: fixed timestamp: exporting the same review twice has to produce the same
#: bytes, and a clock reading in the file would break that.
COMMENT_DATE = "1980-01-01T00:00:00Z"

#: How much of a clause has to match before a comment is anchored to it. Long
#: enough that two clauses cannot both satisfy it, short enough to survive the
#: whitespace differences between what we stored and what their file holds.
ANCHOR_CHARS = 60

_PARAGRAPH_OPEN = re.compile(r"<w:p(?:\s[^>]*)?>")
_TAG = re.compile(r"<[^>]+>")
_PPR = re.compile(r"^<w:pPr[\s>]")


@dataclass
class Note:
    """One finding, as it will read in the margin of their document."""

    anchor: str
    """Text from the clause it belongs against. Matched, not trusted: a note
    whose anchor is found nowhere is reported rather than placed somewhere."""

    author: str
    initials: str
    body: str


@dataclass
class Annotated:
    data: bytes
    placed: list[str]
    unplaced: list[str]
    """Notes whose clause could not be found in their file. Named, because an
    export that quietly dropped a critical finding would look complete."""


def _normalise(text: str) -> str:
    return " ".join(text.lower().split())


def _paragraph_spans(xml: str) -> list[tuple[int, int]]:
    """Every ``w:p`` in document order, as (start, end-of-open, close) offsets.

    Returned as (open_end, close_start) so a caller can insert at the front of
    a paragraph's content and at the back of it without re-parsing.
    """
    spans: list[tuple[int, int]] = []
    for match in _PARAGRAPH_OPEN.finditer(xml):
        depth = 1
        cursor = match.end()
        while depth:
            opened = _PARAGRAPH_OPEN.search(xml, cursor)
            closed = xml.find("</w:p>", cursor)
            if closed == -1:
                return spans
            if opened is not None and opened.start() < closed:
                depth += 1
                cursor = opened.end()
                continue
            depth -= 1
            cursor = closed + len("</w:p>")
        spans.append((match.end(), cursor - len("</w:p>")))
    return spans


def _text_of(fragment: str) -> str:
    return _normalise(_TAG.sub("", fragment))


def _after_properties(xml: str, open_end: int) -> int:
    """Where content starts, which is after ``w:pPr`` when there is one.

    Word requires the paragraph properties to be the first child. A comment
    range inserted before them produces a file Word declines to open, and
    declines to say why.
    """
    if not _PPR.match(xml[open_end : open_end + 12]):
        return open_end
    closed = xml.find("</w:pPr>", open_end)
    if closed == -1:
        empty = xml.find("/>", open_end)
        return empty + 2 if empty != -1 else open_end
    return closed + len("</w:pPr>")


def _escape(value: str) -> str:
    return value.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")


def _comment(index: int, note: Note) -> str:
    paragraphs = "".join(
        f'<w:p><w:r><w:t xml:space="preserve">{_escape(line)}</w:t></w:r></w:p>'
        for line in note.body.split("\n")
    )
    return (
        f'<w:comment w:id="{index}" w:author="{_escape(note.author)}" '
        f'w:initials="{_escape(note.initials)}" w:date="{COMMENT_DATE}">'
        f"{paragraphs}</w:comment>"
    )


def _append_child(xml: str, root: str, child: str) -> str:
    """Add a child to a container element, opening it if it is self-closing.

    A document with no relationships at all writes ``<Relationships .../>``,
    and appending before a closing tag that is not there silently drops the
    part. The comment then exists in the package and Word never loads it.
    """
    closing = f"</{root}>"
    if closing in xml:
        return xml.replace(closing, child + closing, 1)

    empty = re.search(rf"<{root}(\s[^>]*?)?/>", xml)
    if empty is None:
        return xml
    attributes = empty.group(1) or ""
    return xml[: empty.start()] + f"<{root}{attributes}>{child}{closing}" + xml[empty.end() :]


def _with_comments_rel(rels: str) -> str:
    if COMMENTS_REL in rels:
        return rels
    return _append_child(
        rels,
        "Relationships",
        f'<Relationship Id="rIdComments" Type="{COMMENTS_REL}" Target="comments.xml"/>',
    )


def _with_comments_type(types: str) -> str:
    if COMMENTS_PART in types:
        return types
    return _append_child(
        types,
        "Types",
        f'<Override PartName="/{COMMENTS_PART}" ContentType="{COMMENTS_TYPE}"/>',
    )


def annotate(data: bytes, notes: list[Note]) -> Annotated:
    """Return their document with a comment against each clause we have one for."""
    try:
        with zipfile.ZipFile(io.BytesIO(data)) as archive:
            members = {name: archive.read(name) for name in archive.namelist()}
    except zipfile.BadZipFile as exc:
        raise NotADocx("That file could not be read as a Word document.") from exc

    if "word/document.xml" not in members:
        raise NotADocx("That Word file has no document body.")

    xml = members["word/document.xml"].decode("utf-8")
    spans = _paragraph_spans(xml)
    texts = [_text_of(xml[open_end:close_start]) for open_end, close_start in spans]

    placed: list[tuple[int, int, Note]] = []
    unplaced: list[str] = []
    taken: set[int] = set()

    for note in notes:
        anchor = _normalise(note.anchor)[:ANCHOR_CHARS]
        if not anchor:
            unplaced.append(note.body)
            continue
        index = next(
            (
                position
                for position, text in enumerate(texts)
                if position not in taken and anchor in text
            ),
            None,
        )
        if index is None:
            unplaced.append(note.body)
            continue
        taken.add(index)
        placed.append((index, len(placed), note))

    if not placed:
        return Annotated(data=data, placed=[], unplaced=unplaced)

    # Back to front, so an insertion never moves an offset still to be used.
    for index, comment_id, _ in sorted(placed, key=lambda item: item[0], reverse=True):
        open_end, close_start = spans[index]
        content = _after_properties(xml, open_end)
        end = (
            f'<w:commentRangeEnd w:id="{comment_id}"/>'
            f'<w:r><w:commentReference w:id="{comment_id}"/></w:r>'
        )
        xml = xml[:close_start] + end + xml[close_start:]
        xml = xml[:content] + f'<w:commentRangeStart w:id="{comment_id}"/>' + xml[content:]

    members["word/document.xml"] = xml.encode("utf-8")
    members[COMMENTS_PART] = (
        '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
        f'<w:comments xmlns:w="{WORD_NS}">'
        + "".join(
            _comment(comment_id, note)
            for _, comment_id, note in sorted(placed, key=lambda item: item[1])
        )
        + "</w:comments>"
    ).encode("utf-8")

    rels_name = "word/_rels/document.xml.rels"
    existing = members.get(
        rels_name,
        b'<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
        b'<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships"/>',
    )
    members[rels_name] = _with_comments_rel(existing.decode("utf-8")).encode("utf-8")
    members["[Content_Types].xml"] = _with_comments_type(
        members["[Content_Types].xml"].decode("utf-8")
    ).encode("utf-8")

    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w", zipfile.ZIP_DEFLATED) as archive:
        for name in sorted(members):
            info = zipfile.ZipInfo(name, date_time=(1980, 1, 1, 0, 0, 0))
            info.compress_type = zipfile.ZIP_DEFLATED
            info.external_attr = 0o600 << 16
            archive.writestr(info, members[name])

    return Annotated(
        data=buffer.getvalue(),
        placed=[note.body for _, _, note in sorted(placed, key=lambda item: item[1])],
        unplaced=unplaced,
    )
