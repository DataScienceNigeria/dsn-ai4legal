"""Deterministic consistency checks, PRD LOP-M05-US-05.

Before presentation, these run on every assembled or drafted document. The
assistant may not present a draft with an unreported failure, so the caller
attaches the full result to the document and to the AI envelope.
"""

from __future__ import annotations

import re
from collections import Counter
from dataclasses import dataclass

DEFINITION_PATTERN = re.compile(r'[\("“]\s*(?:the\s+)?[“"]([A-Z][A-Za-z ]{2,40})[”"]')
QUOTED_TERM = re.compile(r'[“"]([A-Z][A-Za-z ]{2,40})[”"]')
CROSS_REFERENCE = re.compile(r"\bclause\s+(\d+(?:\.\d+)*)\b", re.I)
SCHEDULE_REFERENCE = re.compile(r"\bschedule\s+(\d+)\b", re.I)
PLACEHOLDER = re.compile(r"\{\{[^}]*\}\}|\[[A-Z_ ]{3,}\]|__+|<INSERT[^>]*>", re.I)
DATE_PATTERN = re.compile(r"\b(\d{1,2})\s+([A-Z][a-z]+)\s+(\d{4})\b")

MONTHS = {
    m: i
    for i, m in enumerate(
        [
            "January", "February", "March", "April", "May", "June",
            "July", "August", "September", "October", "November", "December",
        ],
        start=1,
    )
}

@dataclass
class CheckResult:
    name: str
    passed: bool
    detail: str
    items: list[str]

    def as_dict(self) -> dict:
        return {
            "name": self.name,
            "passed": self.passed,
            "detail": self.detail,
            "items": self.items,
        }

@dataclass
class Clause:
    """One numbered unit of a document."""

    number: str
    heading: str
    text: str

def _definitions(clauses: list[Clause]) -> set[str]:
    defined: set[str] = set()
    for clause in clauses:
        for match in DEFINITION_PATTERN.finditer(clause.text):
            defined.add(match.group(1).strip())
        if re.search(r"\bmeans\b|\bshall mean\b", clause.text, re.I):
            for match in QUOTED_TERM.finditer(clause.text):
                defined.add(match.group(1).strip())
    return defined

def _used_terms(clauses: list[Clause]) -> Counter[str]:
    used: Counter[str] = Counter()
    for clause in clauses:
        for match in QUOTED_TERM.finditer(clause.text):
            used[match.group(1).strip()] += 1
    return used

def check_defined_terms(clauses: list[Clause]) -> list[CheckResult]:
    defined = _definitions(clauses)
    used = _used_terms(clauses)

    undefined = sorted(t for t in used if t not in defined)
    unused = sorted(t for t in defined if used[t] <= 1)

    return [
        CheckResult(
            "defined_terms_used_but_not_defined",
            not undefined,
            "Every capitalised term in quotation marks resolves to a definition."
            if not undefined
            else "Terms are used as defined terms but never defined.",
            undefined,
        ),
        CheckResult(
            "defined_terms_defined_but_not_used",
            not unused,
            "Every defined term is used."
            if not unused
            else "Terms are defined but never used afterwards.",
            unused,
        ),
    ]

def check_cross_references(clauses: list[Clause]) -> CheckResult:
    numbers = {c.number for c in clauses}
    broken: set[str] = set()
    for clause in clauses:
        for match in CROSS_REFERENCE.finditer(clause.text):
            target = match.group(1)
            if target not in numbers and target.split(".")[0] not in numbers:
                broken.add(f"clause {target}, referenced in clause {clause.number}")
    ordered = sorted(broken)
    return CheckResult(
        "cross_references_resolve",
        not ordered,
        "Every cross-reference resolves to a clause in this document."
        if not ordered
        else "Cross-references point at clauses that do not exist.",
        ordered,
    )

def check_numbering(clauses: list[Clause]) -> CheckResult:
    counts = Counter(c.number for c in clauses)
    duplicates = sorted(n for n, count in counts.items() if count > 1)
    return CheckResult(
        "numbering_unique",
        not duplicates,
        "Clause numbering is unique."
        if not duplicates
        else "The same clause number appears more than once.",
        duplicates,
    )

def check_placeholders(clauses: list[Clause]) -> CheckResult:
    found: list[str] = []
    for clause in clauses:
        for match in PLACEHOLDER.finditer(clause.text):
            found.append(f"clause {clause.number}: {match.group(0)[:40]}")
    return CheckResult(
        "no_blank_placeholders",
        not found,
        "No unfilled placeholder remains in the document."
        if not found
        else "Unfilled placeholders remain, which must never reach a document.",
        found,
    )

def check_party_names(clauses: list[Clause], expected: list[str]) -> CheckResult:
    """Party naming must be consistent with the matter record."""
    problems: list[str] = []
    body = "\n".join(c.text for c in clauses)
    for name in expected:
        if name and name not in body:
            problems.append(f"{name} does not appear in the document")
    return CheckResult(
        "party_names_consistent",
        not problems,
        "Party names match the matter record."
        if not problems
        else "Party naming does not match the matter record.",
        problems,
    )

def check_date_logic(clauses: list[Clause]) -> CheckResult:
    """Dates must run forwards. An end date before a start date is a defect."""
    dates: list[tuple[str, tuple[int, int, int]]] = []
    for clause in clauses:
        for match in DATE_PATTERN.finditer(clause.text):
            day, month_name, year = match.groups()
            month = MONTHS.get(month_name)
            if month:
                dates.append((match.group(0), (int(year), month, int(day))))

    problems: list[str] = []
    for label, value in dates:
        if value[0] < 1900 or value[2] > 31:
            problems.append(f"{label} is not a plausible date")

    body = "\n".join(c.text for c in clauses).lower()
    if "commence" in body and "expire" in body and len(dates) >= 2:
        ordered = [v for _, v in dates]
        if ordered != sorted(ordered) and len(set(ordered)) > 1:
            problems.append(
                "Dates do not appear in ascending order, which may mean a term ends "
                "before it begins."
            )

    return CheckResult(
        "date_logic",
        not problems,
        "Dates are plausible and consistent."
        if not problems
        else "Date logic needs a human decision.",
        problems,
    )

def run_all(clauses: list[Clause], expected_parties: list[str] | None = None) -> list[CheckResult]:
    """Run every deterministic check. All failures are reported."""
    results: list[CheckResult] = []
    results.extend(check_defined_terms(clauses))
    results.append(check_cross_references(clauses))
    results.append(check_numbering(clauses))
    results.append(check_placeholders(clauses))
    results.append(check_date_logic(clauses))
    if expected_parties:
        results.append(check_party_names(clauses, expected_parties))
    return results

def all_passed(results: list[CheckResult]) -> bool:
    return all(r.passed for r in results)
