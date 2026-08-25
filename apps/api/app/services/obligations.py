"""Obligation lifecycle, M08.

Obligations are proposed from the executed agreement, confirmed by a person,
and only then become tracked tasks with reminders and escalation.

Obligations are a record of what an agreement requires, not a queue for the
legal team. Reminders and the calendar carry LEGAL_DEADLINES only: renewal,
notice and termination windows, which are legal's own and which nobody else is
watching.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, date, datetime, timedelta

from app.domain.enums import ObligationStatus

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
