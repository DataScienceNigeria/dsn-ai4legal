"""Agreements signed before the platform existed.

Two things are done with one, and neither reshapes it. The file is archived as
it arrived, byte for byte and immutable, and that is what anybody opens. Its
text is read into memory as passages that point back to a place in the
original, so a question about what was signed in 2021 has an answer.

Nothing here builds the platform's structured form of a document, the blocks
that generation, the editor and review work on. Historical paper was not
written with this platform in mind and is not forced into its shape: it is a
record of what was signed, not paper to be worked.

Suggestions are offered for a person to confirm and never stored on their own
say. Each one carries where it came from, the filename or the sentence, so the
person confirming checks a quotation rather than trusting a guess.
"""

from __future__ import annotations

import io
import re
import uuid
from dataclasses import dataclass, field
from datetime import UTC, date, datetime

from sqlalchemy import delete, or_, select
from sqlalchemy.orm import Session

from app.core import audit
from app.core.errors import Conflict, ValidationFailed
from app.db.models.contract import Contract
from app.db.models.counterparty import Counterparty
from app.db.models.document import Document
from app.db.models.platform import MemoryChunk
from app.domain import agreements
from app.domain.enums import DocumentType
from app.services import docx_import, memory, sequences, storage
from app.services.hashing import file_hash

DOCX = "application/vnd.openxmlformats-officedocument.wordprocessingml.document"
PDF = "application/pdf"
TEXT = "text/plain"

#: Paragraphs per passage, and how many each shares with the next. A passage is
#: what retrieval ranks, so it has to hold enough to answer from; the overlap is
#: so an obligation split across a boundary is still whole in one of them.
WINDOW = 6
OVERLAP = 1

#: A passage read from a PDF page is capped, because a dense page as one chunk
#: is either entirely in an answer or entirely out of it.
PAGE_LIMIT = 2400

#: Shorter than this is a heading, a page number or a signature line.
MINIMUM = 80


@dataclass
class Passage:
    locator: str
    """Where in the original this passage sits: ``p. 4`` or ``¶12-17``."""
    text: str
    detail: str


@dataclass
class Suggestion:
    value: str
    source: str
    """The filename or the sentence the value was read from."""


@dataclass
class Reading:
    passages: list[Passage] = field(default_factory=list)
    kind: str = "other"
    readable: bool = False
    reason: str | None = None


def read(filename: str, content_type: str, data: bytes) -> Reading:
    """The text of the file, for search only. The file itself is untouched."""
    name = filename.lower()
    try:
        if content_type == DOCX or name.endswith(".docx"):
            passages = _docx(data)
            kind = "docx"
        elif content_type == PDF or name.endswith(".pdf"):
            passages = _pdf(data)
            kind = "pdf"
        elif content_type == TEXT or name.endswith(".txt"):
            passages = _plain(data.decode("utf-8", errors="replace"))
            kind = "text"
        else:
            return Reading(
                kind="other",
                reason="This kind of file is archived but its text cannot be read for search.",
            )
    except Exception:
        return Reading(
            kind="other",
            reason="The file could not be read for search. It is archived as it is.",
        )

    if not passages:
        reason = (
            "No text could be read, which usually means a scan with no text layer. "
            "It is archived as it is, and will not appear in Memory."
            if kind == "pdf"
            else "No text could be read. It is archived as it is."
        )
        return Reading(kind=kind, reason=reason)
    return Reading(passages=passages, kind=kind, readable=True)


def _windows(paragraphs: list[str], unit: str) -> list[Passage]:
    kept = [(index, text.strip()) for index, text in enumerate(paragraphs, start=1) if text.strip()]
    if not kept:
        return []
    passages: list[Passage] = []
    step = max(1, WINDOW - OVERLAP)
    for start in range(0, len(kept), step):
        window = kept[start : start + WINDOW]
        body = "\n\n".join(text for _, text in window)
        if len(body) < MINIMUM:
            continue
        first, last = window[0][0], window[-1][0]
        locator = f"¶{first}" if first == last else f"¶{first}-{last}"
        passages.append(
            Passage(
                locator=locator,
                text=body,
                detail=f"{unit} {first}" if first == last else f"{unit}s {first} to {last}",
            )
        )
        if start + WINDOW >= len(kept):
            break
    return passages


def _docx(data: bytes) -> list[Passage]:
    return _windows([p.text for p in docx_import.read_paragraphs(data)], "Paragraph")


def _plain(text: str) -> list[Passage]:
    return _windows(re.split(r"\n\s*\n", text), "Paragraph")


def _pdf(data: bytes) -> list[Passage]:
    from pypdf import PdfReader

    reader = PdfReader(io.BytesIO(data))
    passages: list[Passage] = []
    for number, page in enumerate(reader.pages, start=1):
        text = re.sub(r"[ \t]+", " ", page.extract_text() or "").strip()
        if len(text) < MINIMUM:
            continue
        parts = [text[i : i + PAGE_LIMIT] for i in range(0, len(text), PAGE_LIMIT)]
        for part_index, part in enumerate(parts, start=1):
            if len(part.strip()) < MINIMUM:
                continue
            suffix = "" if len(parts) == 1 else f".{part_index}"
            passages.append(
                Passage(locator=f"p. {number}{suffix}", text=part.strip(), detail=f"Page {number}")
            )
    return passages


# ---------------------------------------------------------------- suggestions

_NOISE = {
    "signed", "executed", "final", "copy", "scan", "scanned", "clean", "draft",
    "version", "agreement", "contract", "the", "and", "with", "between", "doc",
    "non", "disclosure", "confidentiality", "understanding", "terms", "of",
    "independent", "contractor", "employee", "template", "mutual", "one", "sided",
}

#: Words in a filename that name an agreement type without ambiguity. An NDA is
#: deliberately absent: mutual and one-sided are different types, and the name
#: rarely says which.
_TYPE_WORDS: list[tuple[str, str]] = [
    (r"\bconsult", "consultancy_agreement"),
    (r"\b(msa|service|services)\b", "service_agreement"),
    (r"\b(vendor|supplier|supply)\b", "vendor_supplier_agreement"),
    (r"\bpartnership\b", "partnership_agreement"),
    (r"\b(research|collaboration)\b", "research_collaboration_agreement"),
    (r"\b(data sharing|data processing|dpa|dsa)\b", "data_sharing_agreement"),
    (r"\b(mou|memorandum)\b", "memorandum_of_understanding"),
    (r"\bgrant\b", "grant_agreement"),
]

_MONTHS = {
    m: i
    for i, m in enumerate(
        ["january", "february", "march", "april", "may", "june", "july",
         "august", "september", "october", "november", "december"],
        start=1,
    )
}
_MONTH = r"(january|february|march|april|may|june|july|august|september|october|november|december)"
_DATES = [
    re.compile(
        rf"\b(\d{{1,2}})(?:st|nd|rd|th)?(?:\s+day)?(?:\s+of)?\s+{_MONTH},?\s+(\d{{4}})\b", re.I
    ),
    re.compile(rf"\b{_MONTH}\s+(\d{{1,2}})(?:st|nd|rd|th)?,?\s+(\d{{4}})\b", re.I),
    re.compile(r"\b(\d{4})-(\d{2})-(\d{2})\b"),
]


def _stem(filename: str) -> str:
    stem = filename.rsplit(".", 1)[0]
    return re.sub(r"[_\-.,()\[\]]+", " ", stem).strip()


def suggest_type(filename: str) -> Suggestion | None:
    stem = _stem(filename).lower()
    for pattern, code in _TYPE_WORDS:
        if re.search(pattern, stem):
            return Suggestion(value=code, source=f"The filename, {filename}")
    return None


def suggest_counterparty(filename: str) -> Suggestion | None:
    """A starting point for the search box, never a record on its own."""
    stem = _stem(filename)
    for pattern, _ in _TYPE_WORDS:
        stem = re.sub(pattern, " ", stem, flags=re.I)
    words = [
        word
        for word in stem.split()
        if word.lower() not in _NOISE
        and not re.fullmatch(r"(19|20)\d{2}|v\d+|\d+", word, re.I)
        and not re.fullmatch(r"nda|dsn|eai|equalyzai", word, re.I)
    ]
    name = " ".join(words).strip()
    return Suggestion(value=name, source=f"The filename, {filename}") if len(name) >= 3 else None


def _parse(match: re.Match, index: int) -> date | None:
    groups = match.groups()
    try:
        if index == 0:
            return date(int(groups[2]), _MONTHS[groups[1].lower()], int(groups[0]))
        if index == 1:
            return date(int(groups[2]), _MONTHS[groups[0].lower()], int(groups[1]))
        return date(int(groups[0]), int(groups[1]), int(groups[2]))
    except (ValueError, KeyError):
        return None


def _sentence(text: str, start: int, end: int) -> str:
    left = max(text.rfind(".", 0, start), text.rfind("\n", 0, start)) + 1
    stop = min([i for i in (text.find(".", end), text.find("\n", end)) if i != -1] or [len(text)])
    return " ".join(text[left : stop + 1].split())[:300]


def suggest_date(reading: Reading) -> Suggestion | None:
    """The first date the agreement states, with the sentence that states it.

    Only the opening passages are read. A date on page nine is a deadline or a
    milestone, not the day the agreement was made.
    """
    for passage in reading.passages[:3]:
        found: list[tuple[int, date, int, int]] = []
        for index, pattern in enumerate(_DATES):
            for match in pattern.finditer(passage.text):
                value = _parse(match, index)
                if value and 1970 <= value.year <= datetime.now(UTC).year + 1:
                    found.append((match.start(), value, match.start(), match.end()))
        if found:
            _, value, start, end = min(found)
            return Suggestion(
                value=value.isoformat(),
                source=f"{passage.detail}: {_sentence(passage.text, start, end)}",
            )
    return None


def suggest_year(filename: str) -> Suggestion | None:
    match = re.search(r"\b(19[7-9]\d|20\d{2})\b", filename)
    return Suggestion(value=match.group(1), source=f"The filename, {filename}") if match else None


def already_archived(session: Session, entity: str, digest: str) -> Contract | None:
    """The same file offered twice is the same agreement."""
    document = session.execute(
        select(Document).where(
            Document.entity == entity,
            Document.content_hash == digest,
            Document.document_type == DocumentType.EXECUTED.value,
        )
    ).scalars().first()
    if document is None or document.contract_id is None:
        return None
    return session.get(Contract, document.contract_id)


# -------------------------------------------------------------------- archive


@dataclass
class ArchiveRequest:
    entity: str
    filename: str
    content_type: str
    data: bytes
    counterparty_id: uuid.UUID
    agreement_type: str | None = None
    effective_date: date | None = None
    end_date: date | None = None
    value_amount: float | None = None
    value_currency: str = "NGN"
    user_department: str | None = None
    remarks: str | None = None


def archive(session: Session, principal, request: ArchiveRequest) -> tuple[Contract, Reading]:
    """Store one historical agreement and read it into memory."""
    storage.validate_upload(request.filename, request.content_type, request.data)

    clean, scan_detail = storage.scan_upload(request.data)
    if not clean:
        audit.record_refusal(
            action="upload_quarantined",
            object_type="historical_agreement",
            object_id=request.filename[:64],
            actor_id=principal.user_id,
            actor_label=principal.name,
            entity=request.entity,
            detail=scan_detail,
        )
        raise ValidationFailed(
            "This file was refused and has been quarantined.", {"file": scan_detail}
        )

    digest = file_hash(request.data)
    existing = already_archived(session, request.entity, digest)
    if existing is not None:
        raise Conflict(f"This file is already archived as {existing.reference}.")

    counterparty = session.get(Counterparty, request.counterparty_id)
    if counterparty is None:
        raise ValidationFailed(
            "Choose who the agreement is with.", {"counterparty": "Not found."}
        )

    if request.end_date and request.effective_date and request.end_date < request.effective_date:
        raise ValidationFailed(
            "The end date is before the effective date.",
            {"end_date": "Must be on or after the effective date."},
        )

    agreement_type = request.agreement_type or "other"
    if not agreements.is_known(agreement_type):
        raise ValidationFailed(
            "That is not one of the agreement types.", {"agreement_type": agreement_type}
        )

    year = request.effective_date.year if request.effective_date else datetime.now(UTC).year
    reference, _ = sequences.new_contract_reference(session, request.entity, year)

    contract = Contract(
        reference=reference,
        entity=request.entity,
        matter_id=None,
        origin="migrated",
        counterparty_id=counterparty.id,
        agreement_type=agreement_type,
        effective_date=request.effective_date,
        end_date=request.end_date,
        value_amount=request.value_amount,
        value_currency=request.value_currency or "NGN",
        signature_status="signed_before_platform",
        content_hash=digest,
        authoritative=True,
        status="executed",
        user_department=request.user_department,
        remarks=request.remarks,
    )
    session.add(contract)
    session.flush()

    name = request.filename or f"{reference} executed"
    key = f"contracts/{reference}/executed/{digest[:12]}-{name}"
    storage.store.put_immutable(key, request.data, request.content_type)

    document = Document(
        entity=request.entity,
        matter_id=None,
        contract_id=contract.id,
        name=name,
        document_type=DocumentType.EXECUTED.value,
        content_hash=digest,
        storage_key=key,
        immutable=True,
        generated_by_id=uuid.UUID(principal.user_id),
        generated_at=datetime.now(UTC),
    )
    session.add(document)
    session.flush()
    contract.executed_document_id = document.id

    reading = read(request.filename, request.content_type, request.data)
    indexed = index(session, contract, counterparty, reading)

    audit.record(
        session,
        action="historical_agreement_archived",
        object_type="contract",
        object_id=reference,
        actor_id=principal.user_id,
        actor_label=principal.name,
        entity=request.entity,
        after_state={
            "file": name,
            "bytes": len(request.data),
            "hash": digest,
            "counterparty": counterparty.reference,
            "agreement_type": agreement_type,
            "effective_date": (
                request.effective_date.isoformat() if request.effective_date else None
            ),
            "end_date": request.end_date.isoformat() if request.end_date else None,
            "searchable_passages": indexed,
        },
    )
    return contract, reading


def index(session: Session, contract: Contract, counterparty, reading: Reading) -> int:
    """The record and its passages, each citing a place in the original."""
    memory.index_contract(session, contract, None, counterparty)
    session.execute(
        delete(MemoryChunk).where(
            MemoryChunk.entity == contract.entity,
            MemoryChunk.source_type == "contract",
            or_(
                MemoryChunk.source_reference.like(f"{contract.reference} p. %"),
                MemoryChunk.source_reference.like(f"{contract.reference} ¶%"),
            ),
        )
    )
    if not reading.readable:
        return 0

    party = counterparty.legal_name if counterparty else "an unlinked counterparty"
    label = agreements.label(contract.agreement_type)
    year = f", {contract.effective_date.year}" if contract.effective_date else ""
    seen: set[str] = set()
    written = 0
    for passage in reading.passages:
        reference = f"{contract.reference} {passage.locator}"[:64]
        if reference in seen:
            continue
        seen.add(reference)
        memory.write(
            session,
            entity=contract.entity,
            source_type="contract",
            source_reference=reference,
            title=f"{party}, {label}{year}, {passage.locator}",
            body=passage.text,
            source_detail=f"{passage.detail} of an agreement signed before the platform",
            matter_id=None,
        )
        written += 1
    return written


def reindex(session: Session, contract: Contract) -> int:
    """Read the archived file again. The file is never rewritten, only reread."""
    if not contract.executed_document_id:
        return 0
    document = session.get(Document, contract.executed_document_id)
    if document is None or not document.storage_key:
        return 0
    data = storage.store.get(document.storage_key)
    counterparty = (
        session.get(Counterparty, contract.counterparty_id) if contract.counterparty_id else None
    )
    content_type = storage.sniff(data) or ""
    return index(session, contract, counterparty, read(document.name, content_type, data))
