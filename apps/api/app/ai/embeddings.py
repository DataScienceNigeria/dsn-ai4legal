"""Turning text into the vectors retrieval ranks on.

Two providers behind one function. A hosted embedding model where one is
configured, and a deterministic hashed projection where none is.

The two are not interchangeable after the fact. Vectors written under one
provider mean nothing to the other, so changing the provider makes the existing
index unreadable rather than merely worse. `dsn_lai.reindex_memory` exists for
exactly that reason and the register records which provider produced what.

The dimension is pinned to the column's width. A hosted model that returns more
is asked for fewer where it supports that, and truncated and renormalised where
it does not, because a vector of the wrong length cannot be stored at all.
"""

from __future__ import annotations

import hashlib
import logging
import math
import re

from app.core.config import settings
from app.db.models.platform import EMBEDDING_DIM

logger = logging.getLogger(__name__)

DETERMINISTIC = "deterministic"


def deterministic(texts: list[str]) -> list[list[float]]:
    """A hashed bag-of-words projection.

    It needs no external service, which means retrieval, and therefore every
    grounded capability, keeps working with nothing configured. It captures
    term overlap and position weighting and nothing else: no synonymy, no
    paraphrase. Keyword search carries most of the weight in that mode, and the
    reciprocal-rank merge is what makes the pair usable.
    """
    vectors: list[list[float]] = []
    for body in texts:
        vector = [0.0] * EMBEDDING_DIM
        tokens = re.findall(r"[a-z0-9]+", body.lower())
        for position, token in enumerate(tokens):
            digest = hashlib.blake2b(token.encode(), digest_size=8).digest()
            index = int.from_bytes(digest[:4], "big") % EMBEDDING_DIM
            sign = 1.0 if digest[4] % 2 == 0 else -1.0
            vector[index] += sign * (1.0 / math.log(position + 2))
        norm = math.sqrt(sum(v * v for v in vector)) or 1.0
        vectors.append([v / norm for v in vector])
    return vectors


def _fit(vector: list[float]) -> list[float]:
    """Make a returned vector exactly the width the column holds."""
    if len(vector) == EMBEDDING_DIM:
        return vector
    trimmed = list(vector[:EMBEDDING_DIM]) + [0.0] * max(0, EMBEDDING_DIM - len(vector))
    norm = math.sqrt(sum(v * v for v in trimmed)) or 1.0
    return [v / norm for v in trimmed]


def openai(texts: list[str]) -> list[list[float]]:
    """A hosted embedding model, batched in one call."""
    from openai import OpenAI

    client = OpenAI(
        api_key=settings.openai_api_key,
        base_url=settings.openai_base_url or None,
        timeout=settings.dsnlai_ai_timeout_seconds,
        max_retries=2,
    )
    response = client.embeddings.create(
        model=settings.dsnlai_embedding_model,
        input=[text[:8000] for text in texts],
        dimensions=EMBEDDING_DIM,
    )
    ordered = sorted(response.data, key=lambda item: item.index)
    return [_fit(list(item.embedding)) for item in ordered]


def provider() -> str:
    """Which provider will actually be used, not which was asked for."""
    if settings.dsnlai_embedding_provider == "openai" and settings.openai_api_key:
        return "openai"
    return DETERMINISTIC


def embed(texts: list[str]) -> list[list[float]]:
    """Embed a batch. Falls back rather than failing.

    A retrieval call that raises because an embedding service was briefly down
    would take every grounded capability with it, so the fallback runs and the
    log says the index has gone mixed until the next reindex.
    """
    if not texts:
        return []
    if provider() == DETERMINISTIC:
        return deterministic(texts)

    try:
        return openai(texts)
    except Exception:
        logger.exception(
            "The embedding provider failed. The deterministic projection was used "
            "instead, so these vectors are in a different space until reindexed."
        )
        return deterministic(texts)
