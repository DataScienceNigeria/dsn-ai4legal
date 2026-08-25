"""Obligation lifecycle, M08.

Obligations are proposed from the executed agreement, confirmed by a person,
and only then become tracked tasks with reminders and escalation.

Extraction can fail two ways, and they are not equally bad. A duty invented is
read, recognised as wrong and rejected, because a person works through the
proposals one at a time. A duty missed produces nothing at all: no proposal, no
task, no reminder, and nobody staring at a blank space wondering what should
have been in it. Eighteen months later the notice window closes on its own.

That second failure is what coverage answers. Rather than block the capability
behind a threshold, which hands Legal an empty list and is the same silent
failure by another route, every clause of the executed agreement is accounted
for: this one produced a duty, that one did not. The clauses that produced
nothing are shown, so a miss is something to look at instead of an absence.

Coverage is computed here from the stored blocks and the stored obligations,
never asked of a model. A report on whether the model missed something, written
by the model, reports nothing.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import UTC, date, datetime, timedelta

from app.domain.enums import ObligationStatus
from app.services.placeholders import is_signature_block

RENEWAL_DECISION_OPTIONS = ["renew", "renegotiate", "terminate", "allow_to_lapse"]

#: The deadlines legal is on the hook for, and the only ones it is reminded of.
#:
#: A consultant's milestone belongs to the project manager and to finance, not
#: to the legal team, and the platform emailing legal about it was telling the
#: wrong people to do something. A notice window is different: nobody else is
#: watching it, and letting it pass renews an agreement on terms the business
#: wanted to change.
LEGAL_DEADLINES = ("renewal", "notice_period", "termination_window")

DEFAULT_RENEWAL_LEAD_DAYS = 60


@dataclass
class ReminderWindow:
    due_date: date
    lead_time_days: int

    @property
    def first_reminder(self) -> date:
        return self.due_date - timedelta(days=self.lead_time_days)

    def is_due(self, today: date | None = None) -> bool:
        return (today or datetime.now(UTC).date()) >= self.first_reminder

    def is_overdue(self, today: date | None = None) -> bool:
        return (today or datetime.now(UTC).date()) > self.due_date

    def days_until(self, today: date | None = None) -> int:
        return (self.due_date - (today or datetime.now(UTC).date())).days


def renewal_task_date(
    notice_deadline: date, lead_time_days: int = DEFAULT_RENEWAL_LEAD_DAYS
) -> date:
    """A renewal window opens at the notice deadline minus the lead time."""
    return notice_deadline - timedelta(days=lead_time_days)


def notice_deadline(end_date: date, notice_period_days: int) -> date:
    return end_date - timedelta(days=notice_period_days)


def next_occurrence(due: date, recurrence: str) -> date | None:
    """The next due date for a recurring obligation."""
    steps = {
        "monthly": 1,
        "quarterly": 3,
        "biannual": 6,
        "annual": 12,
    }
    months = steps.get(recurrence)
    if months is None:
        return None
    month = due.month - 1 + months
    year = due.year + month // 12
    month = month % 12 + 1
    lengths = [31, 29 if year % 4 == 0 else 28, 31, 30, 31, 30, 31, 31, 30, 31, 30, 31]
    day = min(due.day, lengths[month - 1])
    return date(year, month, day)


def can_complete(
    status: str, evidence_required: bool, evidence_reference: str | None
) -> tuple[bool, str]:
    """Completion requires a status and, where configured, evidence."""
    if status == ObligationStatus.COMPLETED.value:
        return False, "This obligation is already completed."
    if status == ObligationStatus.PROPOSED.value:
        return False, "This obligation has not been confirmed, so it is not yet a task."
    if evidence_required and not evidence_reference:
        return False, "Evidence is required before this obligation can be completed."
    return True, ""


def escalation_due(due: date, escalation_rule: dict, today: date | None = None) -> str | None:
    """Return who the highest triggered escalation level notifies, if any."""
    overdue_days = ((today or datetime.now(UTC).date()) - due).days
    if overdue_days < 0:
        return None

    triggered = [
        level
        for level in escalation_rule.get("levels", [])
        if overdue_days >= int(level.get("after_days", 0))
    ]
    if not triggered:
        return None
    return max(triggered, key=lambda level: int(level.get("after_days", 0))).get("notify")


#: The clause label inside a citation, however it was written. "Clause 6",
#: "6.", "Section 6.2" and "6.2" are one reference in four hands.
CLAUSE_NUMBER = re.compile(r"\d+(?:\.\d+)*")

#: Below this a block is a heading, a page number or a stray line, not a clause
#: that could carry a duty.
CLAUSE_MIN_LENGTH = 40


def clause_key(label: str | None) -> str:
    """The comparable form of a clause reference, or "" if it names no number."""
    if not label:
        return ""
    found = CLAUSE_NUMBER.search(label)
    return found.group(0).rstrip(".") if found else ""


def is_clause(block: dict) -> bool:
    """Whether this block is prose that could carry a duty.

    Recitals, headings and the execution block are not. The signature block in
    particular has to go: it is where the agreement is signed, not where it
    says what anyone must do, and reporting it as unaccounted for on every
    contract would train people to ignore the list.
    """
    text = (block.get("text") or "").strip()
    if len(text) < CLAUSE_MIN_LENGTH:
        return False
    if is_signature_block(text, block.get("heading") or ""):
        return False
    return bool(clause_key(block.get("number")))


@dataclass
class UnaccountedClause:
    number: str
    heading: str
    excerpt: str


@dataclass
class Coverage:
    """What extraction accounted for, and what it passed over."""

    clauses_read: int
    clauses_with_duties: int
    unaccounted: list[UnaccountedClause]
    uncited: int
    """Obligations whose citation matched no clause. A duty is still a duty,
    but a citation that points nowhere cannot be checked against its source."""

    @property
    def complete(self) -> bool:
        return not self.unaccounted and not self.uncited


EXCERPT_LENGTH = 180


def coverage(blocks: list[dict], cited: list[str | None]) -> Coverage:
    """Account for every clause of an executed agreement against what was drawn from it."""
    clauses = [block for block in blocks if is_clause(block)]
    keys = {clause_key(block.get("number")): block for block in clauses}

    matched: set[str] = set()
    uncited = 0
    for citation in cited:
        key = clause_key(citation)
        if key and key in keys:
            matched.add(key)
        else:
            uncited += 1

    unaccounted = [
        UnaccountedClause(
            number=str(block.get("number") or "").strip(),
            heading=str(block.get("heading") or "").strip(),
            excerpt=_excerpt(str(block.get("text") or "")),
        )
        for key, block in keys.items()
        if key not in matched
    ]
    return Coverage(
        clauses_read=len(clauses),
        clauses_with_duties=len(matched),
        unaccounted=unaccounted,
        uncited=uncited,
    )


def _excerpt(text: str) -> str:
    body = " ".join(text.split())
    if len(body) <= EXCERPT_LENGTH:
        return body
    return body[:EXCERPT_LENGTH].rsplit(" ", 1)[0] + "..."
