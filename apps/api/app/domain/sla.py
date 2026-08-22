"""Service clock, PRD LOP-M02-US-04.

The clock starts at acceptance, pauses on a recorded wait-on-requester or
wait-on-counterparty state, and resumes automatically. Elapsed time is derived
from the recorded transitions rather than from any manually entered date.
"""

from dataclasses import dataclass
from datetime import UTC, datetime, timedelta

from app.domain.enums import MatterState
from app.domain.state_machine import CLOCK_PAUSED_STATES

NEAR_BREACH_FRACTION = 0.8

@dataclass(frozen=True)
class ClockSegment:
    """One period the matter spent in a single state."""

    state: MatterState
    started_at: datetime
    ended_at: datetime | None = None

@dataclass(frozen=True)
class SlaStatus:
    elapsed: timedelta
    target: timedelta | None
    running: bool
    breached: bool
    near_breach: bool
    remaining: timedelta | None

    @property
    def elapsed_hours(self) -> float:
        return self.elapsed.total_seconds() / 3600.0

def elapsed_running_time(segments: list[ClockSegment], now: datetime | None = None) -> timedelta:
    """Sum the time spent in states where the clock runs."""
    now = now or datetime.now(UTC)
    total = timedelta()
    for segment in segments:
        if segment.state in CLOCK_PAUSED_STATES:
            continue
        end = segment.ended_at or now
        if end > segment.started_at:
            total += end - segment.started_at
    return total

def evaluate(
    segments: list[ClockSegment],
    target_hours: float | None,
    current_state: MatterState,
    now: datetime | None = None,
) -> SlaStatus:
    """Return the clock position for a matter."""
    elapsed = elapsed_running_time(segments, now)
    running = current_state not in CLOCK_PAUSED_STATES
    if target_hours is None:
        return SlaStatus(elapsed, None, running, False, False, None)
    target = timedelta(hours=target_hours)
    remaining = target - elapsed
    breached = elapsed > target
    near = not breached and elapsed >= target * NEAR_BREACH_FRACTION
    return SlaStatus(elapsed, target, running, breached, near, remaining)
