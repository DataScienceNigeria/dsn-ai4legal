"""Masking personal details before they leave for a model provider.

A route declares `redaction_required`. Nothing read it. Confidential records
went to a hosted provider whole, with every email address, phone number and
account number in them, and the flag on the route was a statement of intent
that no code enforced.

What is masked is the personal detail, not the agreement. A contract's meaning
is in its clauses, its parties and its figures, and a redaction that removed
those would answer nothing. So: contact details, government identifiers, bank
accounts and card numbers. Party names stay, because a question about who we
signed with is the question people ask, and a name in an executed agreement is
a commercial fact rather than a private one.

Placeholders are stable within a call. The same address masked twice reads as
the same address, so a model can still say the notice went to the same person
who signed, without being told who that is.

Unmasking happens on the way back. The reader is authorised for the record the
answer came from, so what is protected is the transit, not the reader. An
answer citing [EMAIL-1] would be useless to the person who asked.

Self-hosted routes mask nothing. There is no third party, and degrading the
answer for a provider that does not exist buys nothing.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field

#: What is masked, in the order it is applied. Order matters: an email is
#: matched before the digits inside it can be read as an account number.
PATTERNS: list[tuple[str, re.Pattern[str]]] = [
    ("EMAIL", re.compile(r"\b[\w.%+-]+@[\w.-]+\.[A-Za-z]{2,}\b")),
    ("IBAN", re.compile(r"\b[A-Z]{2}\d{2}[A-Z0-9]{11,30}\b")),
    # Before CARD, and taking the country code with it. A Nigerian number in
    # international form carries thirteen digits, which a card pattern will
    # happily claim, and a phone number reported as a card number tells whoever
    # reads the check the wrong thing about what left the building.
    (
        "PHONE",
        re.compile(r"(?<![\w-])\+\d{1,3}[ -]?(?:\(?\d{2,4}\)?[ -]?){2,4}\d{2,4}(?![\w-])"),
    ),
    # A card number, spaced or grouped as people write them.
    ("CARD", re.compile(r"\b(?:\d[ -]?){13,19}\b")),
    # Nigerian NIN and BVN are both eleven digits, and both identify a person.
    ("ID", re.compile(r"\b\d{11}\b")),
    ("ACCOUNT", re.compile(r"\b\d{10}\b")),
    # A local number, written without a country code.
    ("PHONE", re.compile(r"(?<![\w-])0\d{2,3}[ -]?\d{3}[ -]?\d{4}(?![\w-])")),
]

#: Below this a "phone number" is a clause reference, a monetary figure or a
#: date somebody wrote with spaces in it.
MIN_DIGITS = 9


def _digits(value: str) -> int:
    return sum(character.isdigit() for character in value)


@dataclass
class Masking:
    """One call's worth of masking, and how to undo it."""

    replacements: dict[str, str] = field(default_factory=dict)
    """Placeholder to original. Held for the length of one call and no longer:
    it is the key to what was masked, and it is never written down."""

    counts: dict[str, int] = field(default_factory=dict)

    @property
    def total(self) -> int:
        return len(self.replacements)

    def mask(self, text: str | None) -> str:
        """Replace personal detail with stable placeholders."""
        if not text:
            return text or ""

        seen: dict[str, str] = {value: key for key, value in self.replacements.items()}

        for label, pattern in PATTERNS:
            def swap(match: re.Match[str], label: str = label) -> str:
                found = match.group(0)
                if label in {"CARD", "ID", "ACCOUNT", "PHONE"} and _digits(found) < MIN_DIGITS:
                    return found
                if found in seen:
                    return seen[found]
                self.counts[label] = self.counts.get(label, 0) + 1
                placeholder = f"[{label}-{self.counts[label]}]"
                self.replacements[placeholder] = found
                seen[found] = placeholder
                return placeholder

            text = pattern.sub(swap, text)
        return text

    def unmask(self, text: str | None) -> str:
        """Put the real values back for the reader, who is entitled to them."""
        if not text:
            return text or ""
        for placeholder, original in self.replacements.items():
            text = text.replace(placeholder, original)
        return text

    def unmask_payload(self, payload):
        """Walk a parsed model response and restore every masked value in it."""
        if isinstance(payload, str):
            return self.unmask(payload)
        if isinstance(payload, list):
            return [self.unmask_payload(item) for item in payload]
        if isinstance(payload, dict):
            return {key: self.unmask_payload(value) for key, value in payload.items()}
        return payload
