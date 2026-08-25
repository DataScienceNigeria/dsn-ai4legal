"""Where a finding belongs in the counterparty's draft, M06.

A finding knows what is wrong, "liability is uncapped". Working it means
reading it beside the clause it is about, so the finding has to know which
paragraph that is. Nothing joined the two, and the review was a list of
complaints about a document you could not see.

Locating is deterministic, from the clause reference the review reported and
the counterparty text it quoted. It is not asked of a model: pointing a
reviewer at the wrong clause of an agreement wastes the one thing the screen
exists to give them, and a model that is confident about the wrong paragraph
reports nothing about its own confidence.

Nothing here writes. Every change to their paper is made by a person in the
editor. The platform suggests and locates; the human effects.
"""

from __future__ import annotations

import re
from typing import Any

#: A finding, as a mapping, from either a stored row or fresh model output.
FindingLike = dict[str, Any]

#: The clause label inside a reference, however it was written. "Clause 9.2",
#: "9.2", "cl. 9.2" and "Section 9.2" are one reference in four hands.
CLAUSE_NUMBER = re.compile(r"\d+(?:\.\d+)*")

#: Words too common to say anything about which clause is which.
NOISE = frozenset(
    {
        "the",
        "a",
        "an",
        "and",
        "or",
        "of",
        "to",
        "in",
        "for",
        "on",
        "by",
        "with",
        "this",
        "that",
        "any",
        "all",
        "shall",
        "will",
        "may",
        "not",
        "is",
        "are",
        "be",
        "as",
        "at",
        "it",
        "its",
        "such",
        "party",
        "parties",
        "agreement",
    }
)

#: Below this, two passages have nothing in common but ordinary English, and a
#: match would be a coincidence rather than a location.
MATCH_FLOOR = 0.18


def clause_key(label: str | None) -> str:
    """The comparable form of a clause reference, or "" if it names no number."""
    if not label:
        return ""
    found = CLAUSE_NUMBER.search(label)
    return found.group(0).rstrip(".") if found else ""


def _words(text: str | None) -> set[str]:
    return {
        word
        for word in re.findall(r"[a-z0-9]+", (text or "").lower())
        if word not in NOISE and len(word) > 2
    }


def overlap(left: str | None, right: str | None) -> float:
    """How much two passages share, ignoring ordinary English."""
    a, b = _words(left), _words(right)
    if not a or not b:
        return 0.0
    return len(a & b) / len(a | b)


def locate(blocks: list[dict], reference: str | None, quoted: str | None) -> str | None:
    """Which block of the draft a finding is about, or None if it cannot be told.

    The clause number narrows it and the quoted text decides it. Numbers alone
    are not enough: a counterparty draft routinely carries several blocks under
    one number, a heading and its paragraphs, and replacing the heading with a
    liability clause is the kind of mistake that survives review because the
    document still reads as a document.
    """
    key = clause_key(reference)
    numbered = [block for block in blocks if clause_key(block.get("number")) == key] if key else []

    candidates = numbered or blocks
    scored = [(overlap(quoted, block.get("text")), block) for block in candidates]
    best_score, best = max(scored, key=lambda pair: pair[0], default=(0.0, None))

    if best is not None and best_score >= MATCH_FLOOR:
        return str(best.get("key")) if best.get("key") else None

    # A number that matches exactly one block is a location on its own. More
    # than one, and without text to tell them apart there is nothing to choose.
    if len(numbered) == 1 and numbered[0].get("key"):
        return str(numbered[0]["key"])
    return None


#: Two findings are the same argument when they are about the same clause and
#: say close to the same thing. Deliberately generous: the model rewords a
#: complaint between rounds, and reporting the same uncapped liability twice as
#: two separate problems is worse than occasionally joining two that differ.
SAME_POINT = 0.42


def same_point(earlier: FindingLike, later: FindingLike) -> bool:
    """Whether a finding raised now is one already raised in an earlier round."""
    category = earlier.get("clause_category")
    category_agrees = bool(category) and category == later.get("clause_category")

    keys = (clause_key(earlier.get("their_reference")), clause_key(later.get("their_reference")))
    clause_agrees = bool(keys[0]) and keys[0] == keys[1]

    titles = overlap(earlier.get("title"), later.get("title"))
    positions = overlap(earlier.get("house_position"), later.get("house_position"))

    # Either the clause or the category anchors it, and the wording confirms it.
    # Wording alone is not enough: two different clauses can both be about
    # liability without being the same argument.
    if (clause_agrees or category_agrees) and max(titles, positions) >= SAME_POINT:
        return True
    # A clause reference plus a category is an anchor on its own.
    return clause_agrees and category_agrees


def carry_over(
    previous: list[FindingLike], current: list[FindingLike]
) -> tuple[dict[int, int], list[int]]:
    """Match this round's findings to the last round's.

    Returns the index pairs that are the same argument, and the indices of the
    previous round's findings that nothing in this one matches. Those are
    settled: their paper no longer carries the point, whether it was argued
    here or over a fortnight in somebody else's document.
    """
    matched: dict[int, int] = {}
    taken: set[int] = set()

    for now, later in enumerate(current):
        for before, earlier in enumerate(previous):
            if before in taken:
                continue
            if same_point(earlier, later):
                matched[now] = before
                taken.add(before)
                break

    settled = [index for index in range(len(previous)) if index not in taken]
    return matched, settled
