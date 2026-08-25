"""One test, on the rule that would be expensive to get wrong.

A statutory filing that rolls forward to the wrong date is worse than one that
does not roll forward at all: the second is visibly stale, the first says a
confident, wrong number and nobody looks again until the regulator does.
"""

from datetime import date

from app.services.obligations import RECURRENCES, due_soon_days, next_occurrence


def test_a_filing_rolls_forward_only_when_it_actually_recurs():
    # The three seeded requirements are annual, and 29 February is the date the
    # arithmetic is most likely to get wrong.
    assert next_occurrence(date(2026, 9, 28), "annual") == date(2027, 9, 28)
    assert next_occurrence(date(2026, 11, 30), "quarterly") == date(2027, 2, 28)
    assert next_occurrence(date(2024, 2, 29), "annual") == date(2025, 2, 28)
    assert next_occurrence(date(2026, 1, 31), "monthly") == date(2026, 2, 28)

    # A filing triggered by a change of directors has no next date, and
    # inventing one would put a deadline on the calendar that no law imposes.
    assert next_occurrence(date(2026, 9, 28), "one_off") is None
    assert next_occurrence(date(2026, 9, 28), "event_driven") is None

    # Both kinds are still recordable. The calendar refusing to hold a one-off
    # filing is how it ends up in somebody's inbox instead.
    assert {"one_off", "event_driven", "annual"} <= RECURRENCES
    assert "fortnightly" not in RECURRENCES


def test_due_soon_is_a_share_of_the_cycle_rather_than_a_flat_number():
    """A flat lead time cannot serve a monthly return and an annual one at once.
    Thirty days out is most of the month for the first and barely worth saying
    for the second, so the warning is fifteen per cent of the period."""
    assert due_soon_days("monthly", 30) == 5
    assert due_soon_days("quarterly", 30) == 14
    assert due_soon_days("biannual", 30) == 28
    assert due_soon_days("annual", 30) == 55

    # A filing with no cycle has no share to take. The lead time on the row is
    # the only thing that can speak for it, so it is used unchanged.
    assert due_soon_days("one_off", 21) == 21
    assert due_soon_days("event_driven", 7) == 7
