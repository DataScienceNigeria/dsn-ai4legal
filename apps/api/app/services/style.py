"""House style, LOP-M05-US-03.

House style is enforced, not suggested. Every rule here rewrites the text and
records what it changed, so the draft legal sees is already in house style and
the style report says what the platform did to get it there. Nothing in this
module calls a model: a style rule that depends on a generation is a rule that
can change its mind between two runs of the same draft.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from datetime import date

MONTHS = (
    "January",
    "February",
    "March",
    "April",
    "May",
    "June",
    "July",
    "August",
    "September",
    "October",
    "November",
    "December",
)

CURRENCY_SYMBOLS = {"₦": "NGN", "$": "USD", "£": "GBP", "€": "EUR"}


@dataclass(frozen=True)
class StyleRule:
    code: str
    description: str


@dataclass
class StyleViolation:
    rule: str
    block_key: str
    before: str
    after: str
    corrected: bool = True

    def as_dict(self) -> dict:
        return {
            "rule": self.rule,
            "block_key": self.block_key,
            "before": self.before,
            "after": self.after,
            "corrected": self.corrected,
        }


@dataclass
class HouseStyle:
    """The configurable style set. Held in the `house_style` configuration area
    so it changes without a deployment (LOP-M15-US-06)."""

    currency: str = "NGN"
    date_format: str = "long"
    cross_reference_word: str = "Clause"
    governing_law_phrase: str = (
        "This Agreement is governed by the laws of the Federal Republic of Nigeria."
    )
    party_short_names: dict[str, str] = field(default_factory=dict)
    numbering_style: str = "decimal"

    @classmethod
    def from_config(cls, values: dict) -> HouseStyle:
        return cls(
            currency=values.get("currency", "NGN"),
            date_format=values.get("date_format", "long"),
            cross_reference_word=values.get("cross_reference_word", "Clause"),
            governing_law_phrase=values.get("governing_law_phrase", cls.governing_law_phrase),
            party_short_names=values.get("party_short_names", {}),
            numbering_style=values.get("numbering_style", "decimal"),
        )


RULES = (
    StyleRule("currency", "Amounts carry the three-letter currency code and thousands separators."),
    StyleRule("date", "Dates are written in full, for example 3 March 2026."),
    StyleRule("cross_reference", "Cross-references name the clause with a capital initial."),
    StyleRule(
        "defined_term", "A term defined in quotation marks is capitalised at every later use."
    ),
    StyleRule("party_name", "A party is named in full once, then by its defined short name."),
    StyleRule("governing_law", "Governing law is stated in the house phrasing."),
    StyleRule("numbering", "Clause numbering is sequential with no repeats or gaps."),
)


def _format_amount(raw: str) -> str:
    cleaned = raw.replace(",", "").strip()
    if "." in cleaned:
        whole, _, fraction = cleaned.partition(".")
        return f"{int(whole):,}.{fraction}"
    return f"{int(cleaned):,}"


def _apply_currency(text: str, style: HouseStyle) -> tuple[str, list[tuple[str, str]]]:
    changes: list[tuple[str, str]] = []

    def symbol_sub(match: re.Match[str]) -> str:
        code = CURRENCY_SYMBOLS[match.group(1)]
        replacement = f"{code} {_format_amount(match.group(2))}"
        changes.append((match.group(0), replacement))
        return replacement

    text = re.sub(r"([₦$£€])\s?([\d,]+(?:\.\d{1,2})?)", symbol_sub, text)

    def code_sub(match: re.Match[str]) -> str:
        replacement = f"{match.group(1).upper()} {_format_amount(match.group(2))}"
        if replacement == match.group(0):
            return match.group(0)
        changes.append((match.group(0), replacement))
        return replacement

    pattern = rf"\b({style.currency}|USD|GBP|EUR)\s?([\d,]+(?:\.\d{{1,2}})?)"
    text = re.sub(pattern, code_sub, text, flags=re.IGNORECASE)
    return text, changes


def _apply_dates(text: str) -> tuple[str, list[tuple[str, str]]]:
    changes: list[tuple[str, str]] = []

    def numeric_sub(match: re.Match[str]) -> str:
        day, month, year = (int(part) for part in match.groups())
        if not 1 <= month <= 12:
            return match.group(0)
        try:
            date(year, month, day)
        except ValueError:
            return match.group(0)
        replacement = f"{day} {MONTHS[month - 1]} {year}"
        changes.append((match.group(0), replacement))
        return replacement

    text = re.sub(r"\b(\d{1,2})[/-](\d{1,2})[/-](\d{4})\b", numeric_sub, text)

    def ordinal_sub(match: re.Match[str]) -> str:
        replacement = f"{int(match.group(1))} {match.group(3)}"
        changes.append((match.group(0), replacement))
        return replacement

    text = re.sub(
        rf"\b(\d{{1,2}})(st|nd|rd|th)\s+({'|'.join(MONTHS)})\b", ordinal_sub, text
    )
    return text, changes


def _apply_cross_references(text: str, style: HouseStyle) -> tuple[str, list[tuple[str, str]]]:
    changes: list[tuple[str, str]] = []
    word = style.cross_reference_word

    def sub(match: re.Match[str]) -> str:
        replacement = f"{word} {match.group(2)}"
        changes.append((match.group(0), replacement))
        return replacement

    text = re.sub(rf"\b({word.lower()}|sub-?{word.lower()})\s+(\d+(?:\.\d+)*)", sub, text)
    return text, changes


def _defined_terms(blocks: list[dict]) -> set[str]:
    terms: set[str] = set()
    for block in blocks:
        for quoted in re.findall(r"[\"“]([A-Z][A-Za-z \-]{2,60})[\"”]", block.get("text", "")):
            terms.add(quoted.strip())
    return terms


def _apply_defined_terms(text: str, terms: set[str]) -> tuple[str, list[tuple[str, str]]]:
    changes: list[tuple[str, str]] = []
    for term in sorted(terms, key=len, reverse=True):
        lowered = term.lower()
        if lowered == term:
            continue
        pattern = re.compile(rf"(?<![\"“\w]){re.escape(lowered)}(?![\"”\w])")
        if pattern.search(text):
            text = pattern.sub(term, text)
            changes.append((lowered, term))
    return text, changes


def _apply_party_names(
    text: str, short_names: dict[str, str], seen: set[str]
) -> tuple[str, list[tuple[str, str]]]:
    changes: list[tuple[str, str]] = []
    for full, short in short_names.items():
        if full not in text:
            continue
        if full not in seen:
            seen.add(full)
            first, _, rest = text.partition(full)
            if full in rest:
                rest = rest.replace(full, short)
                changes.append((full, short))
            text = f"{first}{full}{rest}"
        else:
            text = text.replace(full, short)
            changes.append((full, short))
    return text, changes


def _governing_law_sentence(text: str) -> re.Match[str] | None:
    """Find the sentence that states the governing law.

    Sentences are split first and matched second. A single expression spanning
    the sentence would need several unbounded groups, and that shape backtracks
    badly on long clauses.
    """
    for match in re.finditer(r"[^.]{0,600}\.", text):
        sentence = match.group(0).lower()
        if "govern" in sentence and "law" in sentence:
            return match
    return None


def _apply_governing_law(text: str, style: HouseStyle) -> tuple[str, list[tuple[str, str]]]:
    if style.governing_law_phrase in text:
        return text, []
    match = _governing_law_sentence(text)
    if match is None:
        return text, []
    replacement = style.governing_law_phrase
    return (
        text[: match.start()] + replacement + text[match.end() :],
        [(match.group(0).strip(), replacement)],
    )


def _check_numbering(blocks: list[dict]) -> list[StyleViolation]:
    """Numbering is reported rather than rewritten.

    Renumbering a clause silently would break every cross-reference pointing at
    it, so this rule stops at telling the reader which number is wrong.
    """
    violations: list[StyleViolation] = []
    expected = 1
    for block in blocks:
        number = block.get("number")
        if number is None:
            continue
        if str(number) != str(expected):
            violations.append(
                StyleViolation(
                    rule="numbering",
                    block_key=str(block.get("key", "")),
                    before=f"clause {number}",
                    after=f"clause {expected}",
                    corrected=False,
                )
            )
        expected += 1
    return violations


def enforce(blocks: list[dict], style: HouseStyle | None = None) -> tuple[list[dict], list[dict]]:
    """Rewrite the draft into house style and report every correction.

    Returns the corrected blocks and the style report. A draft may not be
    presented without its report, because an uncorrected violation that nobody
    sees is the failure this rule exists to prevent.
    """
    style = style or HouseStyle()
    terms = _defined_terms(blocks)
    seen_parties: set[str] = set()

    corrected: list[dict] = []
    report: list[StyleViolation] = []

    for block in blocks:
        text = block.get("text", "")
        key = str(block.get("key", ""))
        original = text

        for rule, applied in (
            ("currency", lambda value: _apply_currency(value, style)),
            ("date", _apply_dates),
            ("cross_reference", lambda value: _apply_cross_references(value, style)),
            ("defined_term", lambda value: _apply_defined_terms(value, terms)),
            (
                "party_name",
                lambda value: _apply_party_names(value, style.party_short_names, seen_parties),
            ),
            ("governing_law", lambda value: _apply_governing_law(value, style)),
        ):
            text, changes = applied(text)
            report.extend(
                StyleViolation(rule=rule, block_key=key, before=before, after=after)
                for before, after in changes
            )

        entry = dict(block)
        if text != original:
            entry["text"] = text
        corrected.append(entry)

    report.extend(_check_numbering(blocks))
    return corrected, [violation.as_dict() for violation in report]


def rule_catalogue() -> list[dict]:
    return [{"code": rule.code, "description": rule.description} for rule in RULES]
