"""What the platform does after a contract is executed.

The rules live here rather than in the routes, because all three of these things
are refusals as much as they are writes: an issue is not settled until somebody
says what was done, a change request cannot become paper until Legal says which
paper, and a contract cannot close while a required line of the checklist is
outstanding.
"""

from __future__ import annotations

import uuid
from datetime import UTC, date, datetime

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.models.contract import (
    Contract,
    ContractChangeRequest,
    ContractClosureItem,
    ContractIssue,
    Obligation,
)
from app.domain import lifecycle
from app.domain.enums import ObligationStatus

# ---------------------------------------------------------------- the register


def derive_termination_deadline(
    end_date: date | None, notice_period_days: int | None
) -> date | None:
    """The last day notice can be given.

    Only where the paper says enough to work it out. A guess here is worse than
    a blank, because a blank is read as unknown and a wrong date is read as
    known.
    """
    if end_date is None or notice_period_days is None:
        return None
    from datetime import timedelta

    return end_date - timedelta(days=notice_period_days)


# -------------------------------------------------------------------- issues


def may_resolve(status: str, resolution: str | None) -> tuple[bool, str]:
    """Settling an issue requires saying what was done about it."""
    if status not in lifecycle.ISSUE_SETTLED:
        return True, ""
    if len((resolution or "").strip()) < lifecycle.MIN_RESOLUTION:
        return False, (
            "Say what was done. An issue closed with a tick is the spreadsheet "
            "this replaced, and the next person to ask about this contract will "
            "have nothing to read."
        )
    return True, ""


def open_issues(session: Session, contract_id: uuid.UUID) -> list[ContractIssue]:
    return [
        issue
        for issue in session.execute(
            select(ContractIssue).where(ContractIssue.contract_id == contract_id)
        ).scalars()
        if issue.status not in lifecycle.ISSUE_SETTLED
    ]


# ----------------------------------------------------------- change requests


def may_decide(
    change: ContractChangeRequest, decision: str, instrument: str | None
) -> tuple[bool, str]:
    """An approval has to say which paper carries the change.

    ``no_paper_needed`` is the exception and the honest one: a change that turns
    out not to touch contractual rights needs no instrument, and recording that
    determination is the answer rather than the absence of one.
    """
    if change.decision not in lifecycle.CHANGE_OPEN:
        return False, f"This request was already {change.decision.replace('_', ' ')}."
    if decision == "approved" and instrument in (None, "", "none"):
        return False, (
            "Name the instrument. Approving a change without saying whether it is "
            "an amendment, an addendum or a variation leaves the drafter guessing "
            "at the one thing this step exists to decide."
        )
    if decision == "no_paper_needed" and instrument not in (None, "", "none"):
        return False, (
            "That determination and that instrument disagree. Either paper is "
            "required or it is not."
        )
    return True, ""


#: The practice area a variation is drafted under. Amendments are contract work
#: whatever the original was about, and the matter number has to say something.
CHANGE_PRACTICE = "COM"


def matter_title(contract: Contract, change: ContractChangeRequest) -> str:
    instrument = lifecycle.INSTRUMENTS.get(change.instrument or "", "Change")
    return f"{instrument} to {contract.reference}"


# ------------------------------------------------------------------- closure


def materialise_checklist(
    session: Session, contract: Contract
) -> list[ContractClosureItem]:
    """Write the checklist for this contract, once.

    Defined once in ``domain/lifecycle`` and written per contract, the same way
    the DPIA form is defined once and answered per assessment. Rows rather than
    a JSON blob because each line is confirmed by a named person on a date with
    a file attached, and that is a record.

    Idempotent: opening closure twice does not duplicate the list, and an item
    added to the definition after a closure opened appears on the next call
    rather than being silently missing.
    """
    existing = {
        row.item_key
        for row in session.execute(
            select(ContractClosureItem).where(
                ContractClosureItem.contract_id == contract.id
            )
        ).scalars()
    }
    created: list[ContractClosureItem] = []
    for item in lifecycle.ITEMS:
        if item.key in existing:
            continue
        row = ContractClosureItem(
            entity=contract.entity,
            contract_id=contract.id,
            item_key=item.key,
            group_key=item.group,
            status="outstanding",
        )
        session.add(row)
        created.append(row)
    return created


def checklist(session: Session, contract_id: uuid.UUID) -> list[ContractClosureItem]:
    rows = list(
        session.execute(
            select(ContractClosureItem).where(
                ContractClosureItem.contract_id == contract_id
            )
        ).scalars()
    )
    order = {item.key: index for index, item in enumerate(lifecycle.ITEMS)}
    return sorted(rows, key=lambda row: order.get(row.item_key, 999))


def may_confirm(
    item: ContractClosureItem, status: str, evidence: str | None, note: str | None
) -> tuple[bool, str]:
    """Confirming a line requires the evidence that line was defined to need."""
    definition = lifecycle.ITEMS_BY_KEY.get(item.item_key)
    if definition is None:
        return False, "That is not a line on the closure checklist."

    if status == "not_applicable":
        if not definition.may_not_apply:
            return False, (
                f"{definition.label} applies to every agreement. It can be confirmed "
                "or left outstanding, but not dismissed."
            )
        if not (note or "").strip():
            return False, (
                "Say why it does not apply. A line dismissed without a reason is a "
                "line nobody read."
            )
        return True, ""

    if status == "confirmed" and definition.evidence_required:
        if not (evidence or "").strip():
            return False, (
                f"{definition.label} needs its evidence. The point of the checklist "
                "is that it can be shown to somebody afterwards, and an assurance "
                "with nothing behind it cannot be."
            )
    return True, ""


def blocking(session: Session, contract: Contract) -> list[str]:
    """What stands between this contract and closed, in words.

    Three kinds of blocker, and the obligations one is why closure reads the
    obligations rather than trusting the checklist: a duty still open on the
    agreement is either done and unrecorded or genuinely outstanding, and
    closing over it loses the difference.
    """
    reasons: list[str] = []

    rows = checklist(session, contract.id)
    if not rows:
        return ["Closure has not been opened on this agreement."]

    still_open = [
        lifecycle.ITEMS_BY_KEY[row.item_key].label
        for row in rows
        if row.status == "outstanding" and row.item_key in lifecycle.ITEMS_BY_KEY
    ]
    if still_open:
        reasons.append(
            f"{len(still_open)} checklist "
            f"{'line' if len(still_open) == 1 else 'lines'} outstanding: "
            + "; ".join(still_open[:4])
            + ("; and more." if len(still_open) > 4 else ".")
        )

    unsettled = open_issues(session, contract.id)
    if unsettled:
        reasons.append(
            f"{len(unsettled)} open "
            f"{'issue' if len(unsettled) == 1 else 'issues'} on this agreement. "
            "An unresolved dispute does not end because the term did."
        )

    pending = [
        change
        for change in session.execute(
            select(ContractChangeRequest).where(
                ContractChangeRequest.contract_id == contract.id
            )
        ).scalars()
        if change.decision in lifecycle.CHANGE_OPEN
    ]
    if pending:
        reasons.append(
            f"{len(pending)} change "
            f"{'request' if len(pending) == 1 else 'requests'} still with Legal."
        )

    duties = [
        obligation
        for obligation in session.execute(
            select(Obligation).where(Obligation.contract_id == contract.id)
        ).scalars()
        if obligation.status == ObligationStatus.OPEN.value
    ]
    if duties:
        reasons.append(
            f"{len(duties)} obligation{'' if len(duties) == 1 else 's'} still open on "
            "the agreement. Each is either done and unrecorded, or genuinely "
            "outstanding, and closing over it loses the difference."
        )

    return reasons


def progress(rows: list[ContractClosureItem]) -> tuple[int, int]:
    """How much of the checklist is settled, and how much there is."""
    settled = sum(1 for row in rows if row.status in {"confirmed", "not_applicable"})
    return settled, len(rows)


def close(contract: Contract, status: str, note: str | None) -> None:
    contract.status = status
    contract.closed_at = datetime.now(UTC)
    contract.closure_note = note
