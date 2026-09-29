"""Turning a received email into something a person can read.

Mail arrives as plain text, as HTML, or as both, and a reply carries every
earlier message quoted beneath it. Shown whole, a two-line answer is a screen
of chevrons and tracking links, and a model asked to classify it reads the
thread's history as if it were the new request.

So the body is split: what this sender wrote, and the history quoted under it.
Nothing is thrown away. The caller keeps the text as received beside both,
because the cleaned body is a reading aid and the original is the record.
"""

from __future__ import annotations

import html
import re
from html.parser import HTMLParser

BLOCK = {
    "p", "div", "br", "tr", "li", "ul", "ol", "table", "h1", "h2", "h3", "h4",
    "h5", "h6", "blockquote", "section", "article", "header", "footer", "hr",
}
SKIP = {"style", "script", "head", "title"}

# Where a reply stops and the quoted history begins. Each is anchored to the
# start of a line, and the earliest match wins.
QUOTE_MARKERS = [
    # Gmail and Apple Mail. Long names wrap, so the "wrote:" may sit on the
    # following line.
    re.compile(r"^On [^\n]{4,240}(?:\n[^\n]{0,240})?\bwrote:[ \t]*$", re.MULTILINE),
    re.compile(r"^-{2,}\s*Original Message\s*-{2,}\s*$", re.MULTILINE | re.IGNORECASE),
    re.compile(r"^-{2,}\s*Forwarded message\s*-{2,}\s*$", re.MULTILINE | re.IGNORECASE),
    # Outlook puts a header block, not a sentence, above the history.
    re.compile(
        r"^_{8,}\s*\n\s*From:[^\n]*\n(?:[^\n]*\n){0,2}\s*(?:Sent|Date):", re.MULTILINE
    ),
    re.compile(r"^From:[^\n]+\n\s*(?:Sent|Date):[^\n]+\n", re.MULTILINE),
]

IMAGE_PLACEHOLDER = re.compile(r"^\s*>?\s*\[image:[^\]]*\]\s*$", re.MULTILINE)


class _Text(HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.parts: list[str] = []
        self.skipping = 0

    def handle_starttag(self, tag, attrs):
        if tag in SKIP:
            self.skipping += 1
        elif tag in BLOCK:
            self.parts.append("\n")

    def handle_endtag(self, tag):
        if tag in SKIP:
            self.skipping = max(0, self.skipping - 1)
        elif tag in BLOCK:
            self.parts.append("\n")

    def handle_data(self, data):
        if not self.skipping:
            self.parts.append(data)


def html_to_text(markup: str) -> str:
    parser = _Text()
    parser.feed(markup)
    parser.close()
    text = html.unescape("".join(parser.parts)).replace("\xa0", " ")
    return re.sub(r"[ \t]+\n", "\n", text)


def looks_like_html(text: str) -> bool:
    return bool(re.search(r"<(?:html|body|div|p|br|table|span)\b", text[:4000], re.IGNORECASE))


def tidy(text: str) -> str:
    text = text.replace("\r\n", "\n").replace("\r", "\n")
    text = IMAGE_PLACEHOLDER.sub("", text)
    # HTML mail keeps the indentation of its markup, so a paragraph arrives
    # behind six tabs. Runs of spaces and tabs inside a line are one space.
    text = "\n".join(re.sub(r"[ \t]+", " ", line).strip() for line in text.split("\n"))
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text.strip()


def _quoted_block_start(text: str) -> int | None:
    """Where a run of `>` lines begins that holds the rest of the message.

    Only a run that reaches the end counts, so a sender quoting one line of
    the earlier message inline, and answering under it, keeps their answer.
    """
    lines = text.split("\n")
    offset = 0
    start = None
    for line in lines:
        stripped = line.strip()
        if stripped.startswith(">"):
            if start is None:
                start = offset
        elif stripped and start is not None:
            start = None
        offset += len(line) + 1
    return start


def split_quoted(text: str) -> tuple[str, str | None]:
    """The new message and the history under it, in that order."""
    cut = None
    for marker in QUOTE_MARKERS:
        match = marker.search(text)
        if match and (cut is None or match.start() < cut):
            cut = match.start()
    block = _quoted_block_start(text)
    if block is not None and (cut is None or block < cut):
        cut = block

    # A cut at the very top means the whole message is a forward or a quote
    # with nothing added. Hiding all of it would show an empty message.
    if cut is None or not text[:cut].strip():
        return text, None
    return text[:cut].rstrip(), text[cut:].strip() or None


def readable(body: str | None, body_html: str | None) -> tuple[str, str | None, str]:
    """(what the sender wrote, the quoted history, the text as received)."""
    raw = body or ""
    if (not raw.strip() or looks_like_html(raw)) and body_html:
        source = html_to_text(body_html)
    elif looks_like_html(raw):
        source = html_to_text(raw)
    else:
        source = raw
    fresh, quoted = split_quoted(tidy(source))
    return fresh or "(no text)", quoted, raw or (body_html or "")
