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
from app.db.models.document import Document
from app.db.models.matter import DecisionRecord, Matter
from app.domain import lifecycle
from app.domain.enums import DocumentType, ObligationStatus

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


def outcome_needs(outcome: str, detail: str | None, due_date=None,
                  change_type: str | None = None) -> tuple[bool, str]:
    """Whether an outcome has been given enough to be made.

    Each of these creates a real record that somebody else will pick up, and a
    record created from nothing is worse than no record: it lands in a queue
    with no way to tell what it is for.
    """
    if outcome not in lifecycle.ISSUE_OUTCOMES:
        return False, f"One of {', '.join(lifecycle.ISSUE_OUTCOMES)}."
    if outcome in lifecycle.OUTCOMES_NEEDING_DETAIL and not (detail or "").strip():
        return False, (
            "Say what it is. This becomes the record somebody else picks up, and "
            "one that arrives empty tells them nothing about why it exists."
        )
    if outcome == "change_request" and change_type not in lifecycle.CHANGE_TYPES:
        return False, f"Which kind of change: one of {', '.join(lifecycle.CHANGE_TYPES)}."
    if outcome == "obligation" and due_date is None:
        return False, "A duty with no date is a duty nobody is reminded of."
    return True, ""


def issue_change_request(
    session: Session,
    issue,
    contract: Contract,
    *,
    change_type: str,
    detail: str,
    financial_effect: str | None = None,
    value_delta: float | None = None,
    timeline_effect: str | None = None,
    end_date=None,
) -> ContractChangeRequest:
    """The variation an issue turned into, carrying the issue with it.

    The rationale is the issue rather than a fresh paragraph, because the reason
    the paper is changing is the thing that went wrong, and asking somebody to
    restate it invites a shorter and worse version of what is already recorded.
    """
    from app.services import sequences

    change = ContractChangeRequest(
        entity=contract.entity,
        reference=sequences.new_change_request_reference(session),
        contract_id=contract.id,
        change_type=change_type,
        rationale=f"Raised as {issue.reference}, {issue.title}. {issue.description}",
        proposed_changes=detail,
        financial_effect=financial_effect,
        value_delta=value_delta,
        value_currency=contract.value_currency,
        timeline_effect=timeline_effect,
        proposed_end_date=end_date,
        requested_by_id=issue.assignee_id or issue.raised_by_id,
        decision="pending",
    )
    session.add(change)
    session.flush()
    return change


def reopen_matter(session: Session, issue, contract: Contract, *, detail: str,
                  responsible_lawyer_id) -> Matter | None:
    """Reopen the matter that produced the agreement, rather than start a new one.

    A dispute about performance is about the agreement that was negotiated, the
    positions taken while negotiating it and the paper that came out of it. A
    fresh matter has none of that: it opens with an empty document list, so the
    first instinct is to generate something new instead of reading the executed
    copy, and the reasoning that produced the clause now being argued about sits
    in a matter nobody thought to open.

    Reopening keeps the documents, the decisions, the findings and the
    correspondence in one place, and the issue is written into the matter's own
    record as the reason it came back. A variation is the exception and still
    opens its own matter, because an amendment is new paper with its own
    approvals and its own signature.
    """
    from app.services import sequences

    matter = contract.matter
    if matter is None:
        return None

    was = matter.status
    matter.status = "in_review"
    matter.next_action = f"Advise on {issue.reference}"
    matter.blocker = None
    if responsible_lawyer_id:
        matter.responsible_lawyer_id = responsible_lawyer_id

    session.add(
        DecisionRecord(
            sequence=sequences.new_decision_sequence(session),
            matter_id=matter.id,
            entity=matter.entity,
            decision=f"Reopened from {was} after {issue.reference}",
            reason=detail,
            decided_by_id=responsible_lawyer_id,
            decided_at=datetime.now(UTC),
        )
    )
    session.flush()
    return matter


def _executed_copy(session: Session, contract: Contract) -> Document | None:
    """The signed agreement, wherever it was filed."""
    executed = session.execute(
        select(Document)
        .where(
            Document.contract_id == contract.id,
            Document.document_type == DocumentType.EXECUTED.value,
        )
        .order_by(Document.version.desc())
    ).scalars().first()
    if executed is None and contract.matter_id:
        executed = session.execute(
            select(Document)
            .where(
                Document.matter_id == contract.matter_id,
                Document.document_type == DocumentType.EXECUTED.value,
            )
            .order_by(Document.version.desc())
        ).scalars().first()
    return executed


def carry_executed_copy(session: Session, contract: Contract, matter: Matter) -> Document | None:
    """Put the agreement being varied into the matter that varies it.

    A variation matter opened with an empty document list, and an empty list is
    an instruction: the first thing anybody does is generate something, when
    what they need is the executed copy in front of them. An amendment is
    written against the clause numbers of the thing it amends, and a restatement
    starts from its whole text, so in both cases the paper has to be there.

    The row is new and the file is not. Both point at the same object, so the
    content hash is the same one the signature was taken over and nothing is
    duplicated in the store: this is the executed copy appearing where it is
    needed, not a second copy of it that could drift.
    """
    executed = _executed_copy(session, contract)
    if executed is None:
        return None

    carried = Document(
        entity=executed.entity,
        matter_id=matter.id,
        contract_id=contract.id,
        name=f"{contract.reference} as executed",
        document_type=DocumentType.EXECUTED.value,
        version=executed.version,
        template_version_ref=executed.template_version_ref,
        clause_versions=list(executed.clause_versions or []),
        input_values=dict(executed.input_values or {}),
        blocks=list(executed.blocks or []),
        content_hash=executed.content_hash,
        storage_key=executed.storage_key,
        classification=executed.classification,
        # Immutable, as the thing it is a view of. An amendment changes the
        # agreement by being signed alongside it, never by editing what was.
        immutable=True,
        supersedes_id=executed.id,
    )
    session.add(carried)
    session.flush()
    return carried


def seed_restatement_draft(
    session: Session, contract: Contract, matter: Matter
) -> Document | None:
    """An editable copy of the agreement, for the one instrument that rewrites it.

    A restatement is the whole agreement again with the changes in it, so the
    drafter starts from the existing text rather than from a template. The four
    other instruments do not: an amendment is a short document saying what
    changes, and seeding a full copy for one of those would invite somebody to
    edit the agreement in place, which is exactly what a variation exists to
    avoid.

    The bytes are copied rather than shared. The carried executed copy points at
    the signed object and must keep doing so; a draft that autosaved over it
    would overwrite the thing the signature was taken on.
    """
    from app.services import storage

    executed = _executed_copy(session, contract)
    if executed is None:
        return None

    key = None
    if executed.storage_key:
        try:
            data = storage.store.get(executed.storage_key)
        except Exception:
            data = None
        if data is not None:
            key = f"matters/{matter.number}/restatement-{executed.content_hash[:12]}.docx"
            storage.store.put(
                key,
                data,
                "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
            )

    if key is None and not executed.blocks:
        # Nothing to seed from. Better to leave the list holding the executed
        # copy alone than to add an empty draft that looks like a starting
        # point and is not.
        return None

    draft = Document(
        entity=executed.entity,
        matter_id=matter.id,
        contract_id=contract.id,
        name=f"{contract.reference} restated, draft",
        document_type=DocumentType.DRAFT.value,
        version=1,
        template_version_ref=executed.template_version_ref,
        clause_versions=list(executed.clause_versions or []),
        input_values=dict(executed.input_values or {}),
        blocks=list(executed.blocks or []),
        content_hash=executed.content_hash,
        storage_key=key,
        classification=executed.classification,
        immutable=False,
        supersedes_id=executed.id,
    )
    session.add(draft)
    session.flush()
    return draft


def issue_obligation(session: Session, issue, contract: Contract, *, detail: str,
                     due_date, owner_id) -> Obligation:
    """A dated duty on the other side, so the sweep carries it.

    An issue resolved with "they will fix it by the 30th" and nothing else is a
    promise held in a paragraph. As an obligation it is a date the platform
    watches, which is the whole reason the obligations exist.
    """
    from app.services import sequences

    obligation = Obligation(
        entity=contract.entity,
        reference=sequences.new_obligation_reference(
            session, int(contract.reference.split("-")[-1])
        ),
        contract_id=contract.id,
        matter_id=contract.matter_id,
        name=detail[:255],
        description=f"Arising from {issue.reference}, {issue.title}.",
        obligation_type="remediation",
        owner_id=owner_id,
        due_date=due_date,
        status="open",
    )
    session.add(obligation)
    session.flush()
    return obligation


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
    """What may be recorded against one line of the checklist.

    Evidence is asked for and not demanded. Refusing the confirmation without
    it sounds stricter than it is: the evidence field took any string at all,
    so "see email" satisfied it, and the only thing the rule reliably stopped
    was somebody recording a truthful confirmation whose paper lived in another
    system. The line now carries whatever it carries, and the checklist says
    which lines have a file behind them, so a reader can tell the difference
    that the refusal only pretended to enforce.

    Dismissing a line is still refused without a reason, because that is a
    claim about the agreement rather than a record of work done.
    """
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
