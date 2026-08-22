"""Matter state model, PRD section 8.2.

Transitions are the sole source for turnaround metrics, so no metric is ever
computed from a manually entered date. Every transition is recorded with the
actor, the timestamp and, for reversals and holds, a reason.
"""

from dataclasses import dataclass

from app.domain.enums import MatterState

S = MatterState

TRANSITIONS: dict[MatterState, frozenset[MatterState]] = {
    S.SUBMITTED: frozenset({S.IN_TRIAGE, S.RETURNED_FOR_INFORMATION, S.CLOSED_WITHOUT_MATTER}),
    S.RETURNED_FOR_INFORMATION: frozenset({S.IN_TRIAGE, S.CLOSED_WITHOUT_MATTER}),
    S.IN_TRIAGE: frozenset({S.ACCEPTED, S.RETURNED_FOR_INFORMATION, S.CLOSED_WITHOUT_MATTER}),
    S.ACCEPTED: frozenset({S.DRAFTING, S.ON_HOLD}),
    S.DRAFTING: frozenset({S.IN_REVIEW, S.ON_HOLD}),
    S.IN_REVIEW: frozenset({S.IN_APPROVAL, S.DRAFTING, S.ESCALATED}),
    S.ESCALATED: frozenset({S.IN_REVIEW, S.IN_APPROVAL, S.ON_HOLD}),
    S.IN_APPROVAL: frozenset({S.AWAITING_SIGNATURE, S.IN_REVIEW}),
    S.AWAITING_SIGNATURE: frozenset({S.EXECUTED, S.IN_APPROVAL}),
    S.EXECUTED: frozenset({S.ACTIVE}),
    S.ACTIVE: frozenset({S.AMENDED, S.EXPIRED, S.TERMINATED}),
    S.AMENDED: frozenset({S.ACTIVE}),
    S.EXPIRED: frozenset({S.ARCHIVED}),
    S.TERMINATED: frozenset({S.ARCHIVED}),
    S.ARCHIVED: frozenset(),
    S.ON_HOLD: frozenset(),  # resolved dynamically, see permitted_next
    S.CLOSED_WITHOUT_MATTER: frozenset(),
}

CLOCK_PAUSED_STATES: frozenset[MatterState] = frozenset(
    {S.ON_HOLD, S.RETURNED_FOR_INFORMATION}
)

TERMINAL_STATES: frozenset[MatterState] = frozenset({S.ARCHIVED, S.CLOSED_WITHOUT_MATTER})

_REVERSALS: frozenset[tuple[MatterState, MatterState]] = frozenset(
    {
        (S.IN_REVIEW, S.DRAFTING),
        (S.IN_APPROVAL, S.IN_REVIEW),
        (S.AWAITING_SIGNATURE, S.IN_APPROVAL),
        (S.IN_TRIAGE, S.RETURNED_FOR_INFORMATION),
        (S.SUBMITTED, S.RETURNED_FOR_INFORMATION),
    }
)

class IllegalTransition(ValueError):
    """Raised when a caller attempts a transition the state model forbids."""

@dataclass(frozen=True)
class TransitionRules:
    reason_required: bool
    pauses_clock: bool
    resumes_clock: bool
    invalidates_approvals: bool

def permitted_next(current: MatterState, previous: MatterState | None = None) -> set[MatterState]:
    """Return the states reachable from ``current``.

    ``on hold`` returns to its previous state, so the caller supplies the state
    the matter held before the hold was applied.
    """
    if current is S.ON_HOLD:
        allowed = {S.CLOSED_WITHOUT_MATTER}
        if previous is not None and previous is not S.ON_HOLD:
            allowed.add(previous)
        return allowed
    return set(TRANSITIONS[current])

def can_transition(
    current: MatterState, target: MatterState, previous: MatterState | None = None
) -> bool:
    return target in permitted_next(current, previous)

def rules_for(current: MatterState, target: MatterState) -> TransitionRules:
    """Describe what the platform must record and do for a transition."""
    return TransitionRules(
        reason_required=(current, target) in _REVERSALS or target is S.ON_HOLD,
        pauses_clock=target in CLOCK_PAUSED_STATES,
        resumes_clock=current in CLOCK_PAUSED_STATES and target not in CLOCK_PAUSED_STATES,
        invalidates_approvals=current in {S.IN_APPROVAL, S.AWAITING_SIGNATURE}
        and target in {S.IN_REVIEW, S.DRAFTING},
    )

def assert_transition(
    current: MatterState,
    target: MatterState,
    previous: MatterState | None = None,
    reason: str | None = None,
) -> TransitionRules:
    """Validate a transition and return what the caller must record."""
    if not can_transition(current, target, previous):
        raise IllegalTransition(
            f"{current.value} cannot move to {target.value}. "
            f"Permitted: {sorted(s.value for s in permitted_next(current, previous))}"
        )
    rules = rules_for(current, target)
    if rules.reason_required and not (reason or "").strip():
        raise IllegalTransition(
            f"A reason is required to move from {current.value} to {target.value}."
        )
    return rules
