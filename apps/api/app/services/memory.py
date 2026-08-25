"""Memory, written by the work that produces it, M10.

The Ask memory screen says the corpus builds itself from normal work: decision
entries, accepted redlines, approved fallback usage and executed agreements
indexed on the events that create them, so nobody has a knowledge-entry task.
That was true of the seed and of nothing else. No code outside `seed.py` had
ever written a chunk, so an agreement executed this morning could not be asked
about this afternoon, and the answer was not "I have nothing on that" but a
capability refusing itself for having retrieved no source.

Indexing happens here, at the event. A chunk is written when a contract is
executed, when a concession is recorded, when a finding is decided against the
playbook, and when a clause version is approved. Each is the moment the record
becomes true; indexing on a schedule instead would mean a window in which the
platform holds an answer it will not give.

Rewriting rather than appending, keyed on source type and reference: a record
that changes has one chunk, and asking memory about it returns what it says
now. A superseded clause keeps its chunk and is marked, because an answer about
a position we used to hold is a real answer and the reference the model cites
has to keep resolving.
"""

from __future__ import annotations

from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from app.db.models.platform import MemoryChunk
from app.services.placeholders import is_signature_block

#: What a chunk is worth against others in the merge. An approved clause is the
#: house speaking, so it outranks an agreement that merely happens to mention
#: the same subject.
WEIGHTS = {
    "clause": 1.4,
    "decision": 1.2,
    "contract": 1.0,
    "matter_paper": 0.9,
}


def _embed(bodies: list[str]) -> list[list[float] | None]:
    """Vectors for the bodies, or nothing if the embedder is unavailable.

    Retrieval is hybrid. A chunk with no vector is still found by keyword,
    which is worth far more than refusing to record it: the alternative is an
    executed agreement that is missing from memory because a model host was
    briefly unreachable.
    """
    try:
        from app.ai.retrieval import embed

        return list(embed(bodies))
    except Exception:
        return [None] * len(bodies)


def write(
    session: Session,
    *,
    entity: str,
    source_type: str,
    source_reference: str,
    title: str,
    body: str,
    source_detail: str | None = None,
    restricted: bool = False,
    matter_id=None,
    superseded: bool = False,
    current_replacement: str | None = None,
) -> MemoryChunk:
    """Record one thing in memory, replacing what was there for it."""
    session.execute(
        delete(MemoryChunk).where(
            MemoryChunk.source_type == source_type,
            MemoryChunk.source_reference == source_reference,
            MemoryChunk.entity == entity,
        )
    )

    chunk = MemoryChunk(
        entity=entity,
        source_type=source_type,
        source_reference=source_reference,
        source_detail=source_detail,
        title=title,
        body=body,
        restricted=restricted,
        matter_id=matter_id,
        superseded=superseded,
        current_replacement=current_replacement,
        weight=WEIGHTS.get(source_type, 1.0),
        embedding=_embed([f"{title}\n{body}"])[0],
    )
    session.add(chunk)
    return chunk


def _money(amount, currency: str | None) -> str:
    if amount is None:
        return "no recorded value"
    return f"{currency or 'NGN'} {float(amount):,.2f}"


def _contract_title(contract, matter=None, counterparty=None) -> str:
    """What to call this agreement.

    "Unknown, Zamfara Agritech" is a worse answer than the matter's own title,
    which is what a person called this piece of work when they opened it. The
    agreement type is only recorded where the request came through triage.
    """
    party = counterparty.legal_name if counterparty else None
    kind = (contract.agreement_type or "").replace("_", " ").strip()
    if kind and kind != "unknown":
        return f"{kind.capitalize()}, {party or 'an unlinked counterparty'}"
    if matter is not None and matter.title:
        return matter.title
    return f"Agreement with {party or 'an unlinked counterparty'}"


def index_contract(session: Session, contract, matter=None, counterparty=None) -> MemoryChunk:
    """An executed agreement, as memory can answer about it.

    Written from the record rather than from the document body. What a person
    asks memory is who we signed with, when it runs to, what we agreed it was
    worth and what has to happen before it lapses; the clause text answers a
    different question, and the agreement itself is one click away.
    """
    title = _contract_title(contract, matter, counterparty)
    party = counterparty.legal_name if counterparty else "an unlinked counterparty"

    lines = [
        f"Executed {contract.executed_at:%d %B %Y}."
        if contract.executed_at
        else "Executed, date not recorded.",
        f"Value {_money(contract.value_amount, contract.value_currency)}.",
    ]
    if contract.effective_date:
        lines.append(f"Effective from {contract.effective_date:%d %B %Y}.")
    if contract.end_date:
        lines.append(f"Runs to {contract.end_date:%d %B %Y}.")
    if contract.notice_period_days:
        lines.append(f"Notice period {contract.notice_period_days} days.")
    if contract.renewal_type and contract.renewal_type != "none":
        lines.append(f"Renewal is {contract.renewal_type.replace('_', ' ')}.")
    if contract.executed_outside_platform:
        lines.append("Executed on paper and recorded here afterwards.")
    if matter is not None:
        lines.append(f"Reached under matter {matter.number}, {matter.title}.")

    return write(
        session,
        entity=contract.entity,
        source_type="contract",
        source_reference=contract.reference,
        title=title,
        body=" ".join(lines),
        source_detail=f"Executed agreement, {party}",
        restricted=bool(matter is not None and getattr(matter, "restricted", False)),
        matter_id=contract.matter_id,
    )


#: A clause chunk names the agreement and the clause, so a citation reads as a
#: place in a document rather than as an opaque key.
CLAUSE_SUFFIX = " cl. "


def index_contract_clauses(
    session: Session, contract, document, matter=None, counterparty=None
) -> list[MemoryChunk]:
    """The agreement itself, clause by clause.

    The overview above answers who, when and how much. It cannot answer what
    the agreement says, and that is most of what anybody asks. Indexing only
    the record fields left memory holding a single sentence about a twelve
    clause contract, so an answer about it was one sentence long and read as
    though the model were being terse. It was being accurate about a corpus
    that held nothing else.

    One chunk per clause, because retrieval is what decides which parts of an
    agreement reach an answer, and a whole contract as one chunk is either
    entirely in or entirely out. A clause is also the unit a person cites.
    """
    if not document or not document.blocks:
        return []

    prefix = f"{contract.reference}{CLAUSE_SUFFIX}"
    session.execute(
        delete(MemoryChunk).where(
            MemoryChunk.source_type == "contract",
            MemoryChunk.source_reference.like(f"{prefix}%"),
        )
    )

    subject = _contract_title(contract, matter, counterparty)
    written: list[MemoryChunk] = []
    seen: set[str] = set()

    for index, block in enumerate(document.blocks, start=1):
        body = (block.get("text") or "").strip()
        heading = (block.get("heading") or "").strip()

        if len(body) < 40:
            # A heading on its own, or a page number. Nothing anybody asks
            # about, and every one of them dilutes the ranking.
            continue
        if is_signature_block(body, heading):
            # Where the agreement is signed, not where it says what anyone
            # must do. Retrieving it answers no question ever asked.
            continue

        # A counterparty draft routinely repeats a number, a title page and
        # its first clause both being "1". Distinct references matter: they
        # are what a citation resolves against, and two chunks sharing one
        # would leave the reader unable to tell which clause was cited.
        number = str(block.get("number") or index).strip()
        reference = f"{prefix}{number}"[:64]
        if reference in seen:
            reference = f"{prefix}{number}.{index}"[:64]
        seen.add(reference)

        written.append(
            write(
                session,
                entity=contract.entity,
                source_type="contract",
                source_reference=reference,
                title=f"{heading.title() if heading.isupper() else heading}, {subject}"
                if heading
                else f"Clause {number}, {subject}",
                body=body,
                source_detail=f"Clause {number} of the executed agreement",
                matter_id=contract.matter_id,
            )
        )
    return written


def index_decision(session: Session, record, matter=None) -> MemoryChunk:
    """A position taken, and why it moved.

    This is the one people come to memory for. "Have we ever accepted uncapped
    liability, and who approved it" is answerable only if the concession was
    written down at the moment it was made.
    """
    lines = [record.decision]
    if record.reason:
        lines.append(f"Reason: {record.reason}")
    if record.alternatives_considered:
        lines.append(f"Alternatives considered: {record.alternatives_considered}")
    if record.clause_references:
        lines.append(f"Departs from: {', '.join(record.clause_references)}")
    lines.append(f"Authority: {record.authority_level.replace('_', ' ')}.")
    if record.residual_risk_accepted:
        lines.append("Residual risk was knowingly accepted.")
    if record.commercial_rationale:
        lines.append(f"Commercially: {record.commercial_rationale}")
    if matter is not None:
        lines.append(f"On matter {matter.number}, {matter.title}.")

    return write(
        session,
        entity=record.entity,
        source_type="decision",
        source_reference=f"Decision {record.sequence}",
        title=record.decision[:200],
        body="\n".join(lines),
        source_detail="Decision record",
        restricted=bool(matter is not None and getattr(matter, "restricted", False)),
        matter_id=record.matter_id,
        superseded=record.superseded_by_id is not None,
    )


def index_finding(session: Session, finding, matter=None) -> MemoryChunk | None:
    """A concession on counterparty paper, once somebody has made it.

    Only accepted findings. A rejected one is the house holding its position,
    which memory already knows from the playbook, and indexing every complaint
    ever raised would bury the concessions among them.
    """
    if finding.decision not in {"accepted", "edited"}:
        return None

    agreed = finding.edited_text or finding.suggested_redline
    lines = [
        f"On {matter.number if matter else 'a matter'}, "
        f"{finding.severity} deviation at {finding.their_reference or 'an unnumbered clause'}."
    ]
    if finding.their_text:
        lines.append(f"They proposed: {finding.their_text}")
    if finding.house_position:
        lines.append(f"House position: {finding.house_position}")
    if agreed:
        lines.append(f"Agreed wording: {agreed}")
    lines.append(f"Conceded at {finding.required_authority.replace('_', ' ')} authority.")
    if finding.matches_preapproved_fallback:
        lines.append("Matched a pre-approved fallback.")

    return write(
        session,
        entity=matter.entity if matter else "EAI",
        source_type="decision",
        source_reference=f"Finding {finding.id}",
        title=finding.title,
        body="\n".join(lines),
        source_detail="Accepted redline on counterparty paper",
        restricted=bool(matter is not None and getattr(matter, "restricted", False)),
        matter_id=finding.matter_id,
    )


def index_clause_version(session: Session, version, category: str, entity: str) -> MemoryChunk:
    """An approved clause: the house position and what it will fall back to."""
    fallbacks = " ".join(
        f"Fallback {item.get('rank')}, requires {item.get('required_authority')}: "
        f"{item.get('text')}"
        for item in (version.fallbacks or [])
    )
    body = version.house_position
    if fallbacks:
        body += f"\n\nFallbacks: {fallbacks}"
    if version.unacceptable_position:
        body += f"\n\nUnacceptable: {version.unacceptable_position}"

    return write(
        session,
        entity=entity,
        source_type="clause",
        source_reference=version.reference,
        title=f"{category}, house position",
        body=body,
        source_detail="Approved clause, house position and ranked fallbacks",
    )


def supersede(session: Session, source_type: str, source_reference: str, replacement: str) -> None:
    """Mark what a record used to say, without removing it.

    A question about a position we held last year has an answer, and the model
    has to be able to cite it. What it must not do is present it as current, so
    the chunk stays, is weighted down by retrieval, and names what replaced it.
    """
    for chunk in session.execute(
        select(MemoryChunk).where(
            MemoryChunk.source_type == source_type,
            MemoryChunk.source_reference == source_reference,
        )
    ).scalars():
        chunk.superseded = True
        chunk.current_replacement = replacement
