"""Grounding and retrieval, PRD section 13.3.

Retrieval is permission-filtered before ranking. The index is partitioned by
entity and excludes restricted matters for users without explicit access, so no
snippet, title or citation can leak from a record the user cannot open
(LOP-M10-US-04).

Hybrid retrieval combines keyword and vector search with a reciprocal-rank
merge. Chunking is clause-aware rather than fixed-length, so a citation always
resolves to a legally meaningful unit.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

from sqlalchemy import func, select, text
from sqlalchemy.orm import Session

from app.ai.envelope import Source
from app.db.models.platform import MemoryChunk

RRF_K = 60

#: How far a chunk's weight is allowed to move it.
#:
#: Weight says what kind of record outranks another where both answer the
#: question: the house speaking in an approved clause beats an agreement that
#: happens to mention the subject. Applied raw it did more than that. With
#: reciprocal-rank scores this close together, a 1.4 multiplier let a clause
#: ranked third in both halves beat the one record that named the counterparty
#: in the question, so asking about an agreement by name returned six clauses
#: and not the agreement.
#:
#: Damped, it breaks ties and cannot overturn a rank.
WEIGHT_INFLUENCE = 0.25

#: What each question word found in a chunk's own title is worth. Enough that
#: naming a counterparty finds their agreement, small enough that a long title
#: cannot win on incidental words alone.
TITLE_MATCH = 0.35

#: How many matched title words can count. Naming a counterparty or a subject
#: takes one or two; beyond that a long title wins by having more words in it,
#: which is a property of the title and not of the answer.
TITLE_TERMS = 2


def _nudge(weight: float) -> float:
    return 1.0 + (weight - 1.0) * WEIGHT_INFLUENCE

@dataclass
class RetrievedChunk:
    chunk: MemoryChunk
    score: float
    keyword_rank: int | None = None
    vector_rank: int | None = None

    def to_source(self) -> Source:
        label = self.chunk.source_reference
        detail = self.chunk.source_detail or self.chunk.title
        if self.chunk.superseded:
            detail = f"Superseded. {detail}"
            if self.chunk.current_replacement:
                detail += f" The current position is {self.chunk.current_replacement}."
        return Source(
            reference=label,
            kind=self.chunk.source_type,
            detail=detail,
            quote=self.chunk.body[:400],
            score=round(self.score, 4),
        )

def embed(texts: list[str]) -> list[list[float]]:
    """Project text into the retrieval vector space.

    The implementation lives in `app.ai.embeddings`, which picks a hosted model
    where one is configured and a deterministic projection where none is. This
    stays as the name every caller already uses.
    """
    from app.ai.embeddings import embed as _embed

    return _embed(texts)


def _scope(stmt, entity: str, source_types: list[str] | None, matter_id=None):
    """Apply the filters that must run before ranking, never after.

    Row-level security already hides restricted matters from a caller who is
    not named on them. This adds the corpus rules on top: the corpus is the
    approved library, executed agreements, decision records, playbooks and
    policies, and counterparty paper is retrieved only within its own matter.
    """
    stmt = stmt.where(MemoryChunk.entity == entity)
    if source_types:
        stmt = stmt.where(MemoryChunk.source_type.in_(source_types))
    stmt = stmt.where(
        (MemoryChunk.source_type != "matter_paper")
        | (MemoryChunk.matter_id == matter_id if matter_id else False)
    )
    return stmt

#: Words that survive stemming but say nothing about which record is wanted.
#: Postgres drops the usual stop words itself; these are the ones a question is
#: built from rather than the ones English is.
ASKING = frozenset({"tell", "show", "give", "find", "know", "want", "need", "please", "explain"})


def _lexemes(query: str) -> list[str]:
    """The searchable words of a question, sanitised for a tsquery."""
    return [
        word
        for word in re.findall(r"[A-Za-z0-9]+", query)
        if len(word) > 1 and word.lower() not in ASKING
    ]


def keyword_search(
    session: Session,
    query: str,
    entity: str,
    limit: int = 20,
    source_types: list[str] | None = None,
    matter_id=None,
) -> list[tuple[MemoryChunk, float]]:
    """Rank the corpus by the words a question shares with it.

    Terms are joined with OR, not AND. `websearch_to_tsquery` builds an AND of
    everything it is given, so "Tell me about the Zamfara Agritech agreement"
    became `tell & zamfara & agritech & agreement` and matched nothing, because
    no contract contains the word "tell". Every question phrased as a sentence,
    which is every question anyone types, lost the keyword half of hybrid
    retrieval in silence.

    OR restores it, and `ts_rank_cd` does the discriminating: a record carrying
    more of the terms, closer together, ranks above one that carries a single
    common word.
    """
    terms = _lexemes(query)
    if not terms:
        return []

    ts_query = func.to_tsquery("english", " | ".join(terms))
    ts_vector = func.to_tsvector(
        "english", MemoryChunk.title + text("' '") + MemoryChunk.body
    )
    rank = func.ts_rank_cd(ts_vector, ts_query)
    stmt = select(MemoryChunk, rank.label("rank")).where(ts_vector.op("@@")(ts_query))
    stmt = _scope(stmt, entity, source_types, matter_id)
    stmt = stmt.order_by(rank.desc()).limit(limit)
    return [(row[0], float(row[1])) for row in session.execute(stmt)]

def vector_search(
    session: Session,
    query: str,
    entity: str,
    limit: int = 20,
    source_types: list[str] | None = None,
    matter_id=None,
) -> list[tuple[MemoryChunk, float]]:
    vector = embed([query])[0]
    distance = MemoryChunk.embedding.cosine_distance(vector)
    stmt = select(MemoryChunk, distance.label("distance")).where(
        MemoryChunk.embedding.is_not(None)
    )
    stmt = _scope(stmt, entity, source_types, matter_id)
    stmt = stmt.order_by(distance.asc()).limit(limit)
    return [(row[0], 1.0 - float(row[1])) for row in session.execute(stmt)]

def retrieve(
    session: Session,
    query: str,
    entity: str,
    *,
    limit: int = 8,
    source_types: list[str] | None = None,
    matter_id=None,
    candidate_pool: int = 24,
) -> list[RetrievedChunk]:
    """Hybrid retrieval with a reciprocal-rank merge and a light rerank.

    Both halves run under the same permission filter, so a record the caller
    cannot open cannot enter the candidate set by either route.
    """
    keyword = keyword_search(session, query, entity, candidate_pool, source_types, matter_id)
    vector = vector_search(session, query, entity, candidate_pool, source_types, matter_id)

    merged: dict[str, RetrievedChunk] = {}
    for rank, (chunk, _) in enumerate(keyword, start=1):
        merged[str(chunk.id)] = RetrievedChunk(
            chunk=chunk, score=1.0 / (RRF_K + rank), keyword_rank=rank
        )
    for rank, (chunk, _) in enumerate(vector, start=1):
        key = str(chunk.id)
        if key in merged:
            merged[key].score += 1.0 / (RRF_K + rank)
            merged[key].vector_rank = rank
        else:
            merged[key] = RetrievedChunk(
                chunk=chunk, score=1.0 / (RRF_K + rank), vector_rank=rank
            )

    # The light rerank. A record whose own title carries the words of the
    # question is the record that was asked about, and reciprocal-rank scores
    # sit too close together to say so on their own: "Zamfara Agritech" and
    # "agreement" both hit, but every clause in the corpus contains the word
    # agreement, so the one contract that names the counterparty ranked below
    # three clauses that did not.
    wanted = {word.lower() for word in _lexemes(query)}
    results = list(merged.values())
    for result in results:
        named = wanted & {word.lower() for word in _lexemes(result.chunk.title)}
        boost = 1 + TITLE_MATCH * min(len(named), TITLE_TERMS)
        result.score *= _nudge(result.chunk.weight) * boost
        if result.chunk.superseded:
            result.score *= 0.4

    results.sort(key=lambda r: r.score, reverse=True)
    return results[:limit]

def render_context(chunks: list[RetrievedChunk]) -> str:
    """Format retrieved material for the prompt.

    Each block is labelled with the reference the model must cite, so an answer
    can be checked against its sources mechanically rather than by reading.
    """
    blocks = []
    for chunk in chunks:
        status = " (superseded)" if chunk.chunk.superseded else ""
        blocks.append(
            f"[{chunk.chunk.source_reference}]{status} {chunk.chunk.title}\n{chunk.chunk.body}"
        )
    return "\n\n".join(blocks)
