"""The life of a contract after it is signed, M07 continued.

Sections 15, 16 and 17 of the Guide to Engaging the Legal Team. The platform
used to stop at execution, which meant the part of a contract's life where it is
performed, goes wrong, is varied and eventually ends happened entirely off the
platform, in email and a spreadsheet.

Three things live here and they divide along the guide's own line. Raising an
issue and asking for a change belong to the user department, because they are
the ones running the contract and they are who notices. Deciding what to do
about either belongs to Legal. Closing a contract belongs to Legal and refuses
to happen while anything is outstanding.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime

from fastapi import APIRouter
from sqlalchemy import select

from app.core import audit
from app.core.deps import CurrentUser, Db, WorkingEntity
from app.core.errors import Conflict, Forbidden, NotFound, Refused, ValidationFailed
from app.db.models.contract import (
    Contract,
    ContractChangeRequest,
    ContractClosureItem,
    ContractIssue,
)
from app.db.models.matter import Matter
from app.db.models.organisation import User
from app.domain import agreements
from app.domain import lifecycle as vocab
from app.domain.enums import MatterState, RiskTier, Role, Severity
from app.schemas.lifecycle import (
    ChangeDetermination,
    ChangeRequestCreate,
    ChangeRequestOut,
    CloseRequest,
    ClosureGroupOut,
    ClosureItemOut,
    ClosureItemUpdate,
    ClosureOut,
    IssueCreate,
    IssueOut,
    IssueResolve,
    IssueTriage,
    RegisterUpdate,
    VocabularyOut,
)
from app.services import lifecycle as service
from app.services import notifications, sequences

router = APIRouter(tags=["lifecycle"])

CONTRACT_NOT_FOUND = "That agreement was not found."
ISSUE_NOT_FOUND = "That issue was not found."
CHANGE_NOT_FOUND = "That change request was not found."

LEGAL = (Role.COUNSEL, Role.HEAD_OF_LEGAL, Role.ADMIN)

#: Who may read the register's working records without acting on them. An
#: auditor reads everything and changes nothing, which is what an auditor does
#: everywhere else in the platform, and the queues sit on a page they can
#: already open.
READERS = (*LEGAL, Role.AUDITOR)


def _terms(mapping: dict[str, str]) -> list[dict]:
    return [{"key": key, "label": label} for key, label in mapping.items()]


@router.get("/lifecycle/vocabulary", response_model=VocabularyOut)
def vocabulary(principal: CurrentUser) -> VocabularyOut:
    """The words, served rather than duplicated in the interface.

    A list written twice disagrees with itself the first time either copy is
    edited, and this is exactly what went wrong with agreement types: five
    tables invented their own and the library held one nothing could request.
    """
    return VocabularyOut(
        agreement_types=_terms(agreements.AGREEMENT_TYPES),
        issue_types=_terms(vocab.ISSUE_TYPES),
        issue_statuses=_terms(vocab.ISSUE_STATUSES),
        change_types=_terms(vocab.CHANGE_TYPES),
        instruments=_terms(vocab.INSTRUMENTS),
        change_decisions=_terms(vocab.CHANGE_DECISIONS),
        contract_statuses=_terms(vocab.CONTRACT_STATUSES),
        closure_statuses=_terms(vocab.CLOSURE_STATUSES),
        severities=[s.value for s in Severity],
    )


def _contract(db, contract_id: uuid.UUID) -> Contract:
    contract = db.get(Contract, contract_id)
    if contract is None:
        raise NotFound(CONTRACT_NOT_FOUND)
    return contract


def _mine_or_legal(contract: Contract, principal) -> None:
    """Who may see one agreement's issues and changes.

    Legal sees everything. A department lead sees the agreements their own
    matter produced, because section 15 makes them responsible for running it
    and a person cannot be accountable for a record they cannot open.
    """
    if principal.has_role(*READERS):
        return
    matter = contract.matter
    if matter is not None and str(matter.requester_id) == principal.user_id:
        return
    raise Forbidden("That agreement is not one of yours.")


def _decorate_issue(issue: ContractIssue) -> IssueOut:
    model = IssueOut.model_validate(issue)
    contract = issue.contract
    if contract is not None:
        model.contract_reference = contract.reference
        model.counterparty_name = (
            contract.counterparty.legal_name if contract.counterparty else None
        )
    return model


def _decorate_change(change: ContractChangeRequest, db) -> ChangeRequestOut:
    model = ChangeRequestOut.model_validate(change)
    contract = change.contract
    if contract is not None:
        model.contract_reference = contract.reference
        model.counterparty_name = (
            contract.counterparty.legal_name if contract.counterparty else None
        )
    if change.resulting_matter_id:
        matter = db.get(Matter, change.resulting_matter_id)
        model.resulting_matter_number = matter.number if matter else None
    return model


# =========================================================== section 15, issues


@router.post("/contracts/{contract_id}/issues", response_model=IssueOut, status_code=201)
def raise_issue(
    contract_id: uuid.UUID, payload: IssueCreate, db: Db, principal: CurrentUser
) -> IssueOut:
    """Tell Legal something is wrong.

    Open to whoever runs the contract as well as to Legal, which is the point:
    the guide puts day-to-day performance with the user department, so the
    person who notices the missed milestone is not in Legal and needs a way in
    that is not an email.
    """
    contract = _contract(db, contract_id)
    _mine_or_legal(contract, principal)

    if payload.issue_type not in vocab.ISSUE_TYPES:
        raise ValidationFailed(
            "That is not a kind of issue the register recognises.",
            {"issue_type": f"One of {', '.join(vocab.ISSUE_TYPES)}."},
        )
    if payload.severity not in {s.value for s in Severity}:
        raise ValidationFailed(
            "That is not a severity.",
            {"severity": f"One of {', '.join(s.value for s in Severity)}."},
        )

    issue = ContractIssue(
        entity=contract.entity,
        reference=sequences.new_issue_reference(db),
        contract_id=contract.id,
        issue_type=payload.issue_type,
        severity=payload.severity,
        title=payload.title,
        description=payload.description,
        occurred_on=payload.occurred_on,
        evidence_document_id=payload.evidence_document_id,
        evidence_note=payload.evidence_note,
        raised_by_id=uuid.UUID(principal.user_id),
        status="open",
    )
    db.add(issue)
    db.flush()

    # A critical issue on a signed agreement is the lead's, not the queue's.
    role = (
        Role.HEAD_OF_LEGAL.value
        if payload.severity == Severity.CRITICAL.value
        else Role.COUNSEL.value
    )
    notifications.raise_for_role(
        db,
        role=role,
        entity=contract.entity,
        kind="contract_issue",
        title=f"{vocab.ISSUE_TYPES[payload.issue_type]} on {contract.reference}",
        body=f"{principal.name} raised {issue.reference}. {payload.title}",
        href="/workspace/lifecycle",
        reference=issue.reference,
    )

    audit.record(
        db,
        action="contract_issue_raised",
        object_type="contract_issue",
        object_id=issue.reference,
        actor_id=principal.user_id,
        actor_label=principal.name,
        entity=contract.entity,
        after_state={
            "contract": contract.reference,
            "type": payload.issue_type,
            "severity": payload.severity,
            "title": payload.title,
        },
    )
    return _decorate_issue(issue)


@router.get("/issues", response_model=list[IssueOut])
def list_issues(
    db: Db,
    principal: CurrentUser,
    entity: WorkingEntity,
    status: str | None = None,
    contract_id: uuid.UUID | None = None,
) -> list[IssueOut]:
    """Legal's queue of what has gone wrong across the portfolio."""
    principal.require_role(*READERS)
    stmt = select(ContractIssue).where(ContractIssue.entity == entity)
    if status == "open":
        stmt = stmt.where(ContractIssue.status.notin_(list(vocab.ISSUE_SETTLED)))
    elif status:
        stmt = stmt.where(ContractIssue.status == status)
    if contract_id:
        stmt = stmt.where(ContractIssue.contract_id == contract_id)
    rows = db.execute(stmt.order_by(ContractIssue.created_at.desc())).scalars()
    return [_decorate_issue(issue) for issue in rows]


@router.get("/contracts/{contract_id}/issues", response_model=list[IssueOut])
def contract_issues(
    contract_id: uuid.UUID, db: Db, principal: CurrentUser
) -> list[IssueOut]:
    contract = _contract(db, contract_id)
    _mine_or_legal(contract, principal)
    rows = db.execute(
        select(ContractIssue)
        .where(ContractIssue.contract_id == contract_id)
        .order_by(ContractIssue.created_at.desc())
    ).scalars()
    return [_decorate_issue(issue) for issue in rows]


@router.post("/issues/{issue_id}/triage", response_model=IssueOut)
def triage_issue(
    issue_id: uuid.UUID, payload: IssueTriage, db: Db, principal: CurrentUser
) -> IssueOut:
    """Legal picks it up: who owns it, and how bad it is on a second look."""
    principal.require_role(*READERS)
    issue = db.get(ContractIssue, issue_id)
    if issue is None:
        raise NotFound(ISSUE_NOT_FOUND)
    if issue.settled:
        raise Conflict("That issue is settled. Reopen it before reassigning it.")

    before = {"assignee": str(issue.assignee_id), "severity": issue.severity,
              "status": issue.status}

    if payload.assignee_id is not None:
        if db.get(User, payload.assignee_id) is None:
            raise ValidationFailed(
                "That person is not on the platform.",
                {"assignee_id": "Choose somebody who can be asked about it."},
            )
        issue.assignee_id = payload.assignee_id
    if payload.severity:
        issue.severity = payload.severity
    if payload.status:
        if payload.status not in vocab.ISSUE_STATUSES:
            raise ValidationFailed(
                "That is not a status.", {"status": f"One of {', '.join(vocab.ISSUE_STATUSES)}."}
            )
        if payload.status in vocab.ISSUE_SETTLED:
            raise Conflict(
                "Settling an issue goes through resolve, which requires saying what "
                "was done about it."
            )
        issue.status = payload.status

    audit.record(
        db,
        action="contract_issue_triaged",
        object_type="contract_issue",
        object_id=issue.reference,
        actor_id=principal.user_id,
        actor_label=principal.name,
        entity=issue.entity,
        before_state=before,
        after_state={"assignee": str(issue.assignee_id), "severity": issue.severity,
                     "status": issue.status},
    )
    return _decorate_issue(issue)


@router.post("/issues/{issue_id}/resolve", response_model=IssueOut)
def resolve_issue(
    issue_id: uuid.UUID, payload: IssueResolve, db: Db, principal: CurrentUser
) -> IssueOut:
    """Settle it, and say what was done."""
    principal.require_role(*LEGAL)
    issue = db.get(ContractIssue, issue_id)
    if issue is None:
        raise NotFound(ISSUE_NOT_FOUND)
    if payload.status not in vocab.ISSUE_SETTLED:
        raise ValidationFailed(
            "That is not a settled state.",
            {"status": f"One of {', '.join(sorted(vocab.ISSUE_SETTLED))}."},
        )

    allowed, reason = service.may_resolve(payload.status, payload.resolution)
    if not allowed:
        raise ValidationFailed(reason, {"resolution": reason})

    issue.status = payload.status
    issue.resolution = payload.resolution
    issue.resolved_at = datetime.now(UTC)
    issue.resolved_by_id = uuid.UUID(principal.user_id)

    if issue.raised_by_id and str(issue.raised_by_id) != principal.user_id:
        notifications.raise_in_app(
            db,
            recipient_id=issue.raised_by_id,
            entity=issue.entity,
            kind="contract_issue_resolved",
            title=f"{issue.reference} has been resolved",
            body=payload.resolution[:400],
            href="/portal/contracts",
            reference=issue.reference,
        )

    audit.record(
        db,
        action="contract_issue_resolved",
        object_type="contract_issue",
        object_id=issue.reference,
        actor_id=principal.user_id,
        actor_label=principal.name,
        entity=issue.entity,
        after_state={"status": payload.status, "resolution": payload.resolution},
    )
    return _decorate_issue(issue)


# =================================================== section 16, changes


@router.post(
    "/contracts/{contract_id}/change-requests",
    response_model=ChangeRequestOut,
    status_code=201,
)
def request_change(
    contract_id: uuid.UUID, payload: ChangeRequestCreate, db: Db, principal: CurrentUser
) -> ChangeRequestOut:
    """Ask for the paper to change.

    Section 16: no material change is implemented informally where it affects
    contractual rights. The department submits the change and its rationale;
    which instrument carries it is a legal question answered at determination.
    """
    contract = _contract(db, contract_id)
    _mine_or_legal(contract, principal)

    if contract.status in {"closed", "terminated", "lapsed"}:
        state = vocab.CONTRACT_STATUSES.get(contract.status, contract.status).lower()
        raise Conflict(
            f"{contract.reference} is {state}. A finished agreement is not varied; "
            "a new one is signed."
        )
    if payload.change_type not in vocab.CHANGE_TYPES:
        raise ValidationFailed(
            "That is not a kind of change the register recognises.",
            {"change_type": f"One of {', '.join(vocab.CHANGE_TYPES)}."},
        )

    change = ContractChangeRequest(
        entity=contract.entity,
        reference=sequences.new_change_request_reference(db),
        contract_id=contract.id,
        change_type=payload.change_type,
        rationale=payload.rationale,
        proposed_changes=payload.proposed_changes,
        financial_effect=payload.financial_effect,
        value_delta=payload.value_delta,
        value_currency=payload.value_currency or contract.value_currency,
        financial_note=payload.financial_note,
        timeline_effect=payload.timeline_effect,
        proposed_end_date=payload.proposed_end_date,
        timeline_note=payload.timeline_note,
        requested_by_id=uuid.UUID(principal.user_id),
        decision="pending",
    )
    db.add(change)
    db.flush()

    notifications.raise_for_role(
        db,
        role=Role.COUNSEL.value,
        entity=contract.entity,
        kind="change_request",
        title=f"Change requested on {contract.reference}",
        body=(
            f"{principal.name} asked for "
            f"{vocab.CHANGE_TYPES[payload.change_type].lower()}. {change.reference}."
        ),
        href="/workspace/lifecycle",
        reference=change.reference,
    )

    audit.record(
        db,
        action="contract_change_requested",
        object_type="contract_change_request",
        object_id=change.reference,
        actor_id=principal.user_id,
        actor_label=principal.name,
        entity=contract.entity,
        after_state={
            "contract": contract.reference,
            "type": payload.change_type,
            "financial_effect": payload.financial_effect,
            "timeline_effect": payload.timeline_effect,
        },
    )
    return _decorate_change(change, db)


@router.get("/change-requests", response_model=list[ChangeRequestOut])
def list_change_requests(
    db: Db, principal: CurrentUser, entity: WorkingEntity, decision: str | None = None
) -> list[ChangeRequestOut]:
    principal.require_role(*READERS)
    stmt = select(ContractChangeRequest).where(ContractChangeRequest.entity == entity)
    if decision:
        stmt = stmt.where(ContractChangeRequest.decision == decision)
    rows = db.execute(stmt.order_by(ContractChangeRequest.created_at.desc())).scalars()
    return [_decorate_change(change, db) for change in rows]


@router.get(
    "/contracts/{contract_id}/change-requests", response_model=list[ChangeRequestOut]
)
def contract_change_requests(
    contract_id: uuid.UUID, db: Db, principal: CurrentUser
) -> list[ChangeRequestOut]:
    contract = _contract(db, contract_id)
    _mine_or_legal(contract, principal)
    rows = db.execute(
        select(ContractChangeRequest)
        .where(ContractChangeRequest.contract_id == contract_id)
        .order_by(ContractChangeRequest.created_at.desc())
    ).scalars()
    return [_decorate_change(change, db) for change in rows]


@router.post("/change-requests/{change_id}/determination", response_model=ChangeRequestOut)
def determine_change(
    change_id: uuid.UUID, payload: ChangeDetermination, db: Db, principal: CurrentUser
) -> ChangeRequestOut:
    """Legal decides whether it proceeds, and which paper carries it.

    An approval **opens a new matter**. This is the decision worth reading
    twice: a variation is a document that has to be drafted, approved, signed
    and executed like any other, and the agreement that governed last March has
    to keep saying what it said then. So nothing overwrites the original. The
    new matter runs the ordinary pipeline and the contract it produces points
    back at the one it changes.
    """
    principal.require_role(Role.HEAD_OF_LEGAL, Role.ADMIN)
    change = db.get(ContractChangeRequest, change_id)
    if change is None:
        raise NotFound(CHANGE_NOT_FOUND)

    if payload.decision not in vocab.CHANGE_DECISIONS:
        raise ValidationFailed(
            "That is not a determination.",
            {"decision": f"One of {', '.join(vocab.CHANGE_DECISIONS)}."},
        )
    if payload.instrument and payload.instrument not in vocab.INSTRUMENTS:
        raise ValidationFailed(
            "That is not an instrument.",
            {"instrument": f"One of {', '.join(vocab.INSTRUMENTS)}."},
        )

    allowed, reason = service.may_decide(change, payload.decision, payload.instrument)
    if not allowed:
        raise Conflict(reason)

    contract = _contract(db, change.contract_id)
    change.decision = payload.decision
    change.instrument = payload.instrument or None
    change.decision_reason = payload.reason
    change.decided_by_id = uuid.UUID(principal.user_id)
    change.decided_at = datetime.now(UTC)

    created_matter: Matter | None = None
    if payload.decision == "approved":
        created_matter = Matter(
            entity=contract.entity,
            number=sequences.new_matter_number(
                db, contract.entity, service.CHANGE_PRACTICE
            ),
            title=service.matter_title(contract, change),
            # A variation inherits the risk of what it varies. It is the same
            # counterparty, the same subject and usually the same money, so
            # re-tiering it from scratch would be a fiction.
            risk_tier=contract.matter.risk_tier if contract.matter else RiskTier.TIER_2.value,
            status=MatterState.ACCEPTED.value,
            practice_code=service.CHANGE_PRACTICE,
            counterparty_id=contract.counterparty_id,
            requester_id=change.requested_by_id,
            responsible_lawyer_id=uuid.UUID(principal.user_id),
            value_amount=change.value_delta,
            value_currency=change.value_currency or contract.value_currency,
            privacy_flag=contract.matter.privacy_flag if contract.matter else False,
            next_action=f"Draft the {vocab.INSTRUMENTS[payload.instrument].lower()}",
        )
        db.add(created_matter)
        db.flush()
        change.resulting_matter_id = created_matter.id
        contract.status = "active"

    if change.requested_by_id:
        notifications.raise_in_app(
            db,
            recipient_id=change.requested_by_id,
            entity=change.entity,
            kind="change_determined",
            title=f"{change.reference}: {vocab.CHANGE_DECISIONS[payload.decision]}",
            body=payload.reason[:400],
            href="/portal/contracts",
            reference=change.reference,
        )

    audit.record(
        db,
        action="contract_change_determined",
        object_type="contract_change_request",
        object_id=change.reference,
        actor_id=principal.user_id,
        actor_label=principal.name,
        entity=change.entity,
        after_state={
            "decision": payload.decision,
            "instrument": change.instrument,
            "reason": payload.reason,
            "matter": created_matter.number if created_matter else None,
        },
    )
    return _decorate_change(change, db)


# ==================================================== section 17, closure


def _closure_out(db, contract: Contract) -> ClosureOut:
    rows = service.checklist(db, contract.id)
    by_key = {row.item_key: row for row in rows}
    settled, total = service.progress(rows)

    groups: list[ClosureGroupOut] = []
    for group in vocab.CLOSURE_GROUPS:
        items: list[ClosureItemOut] = []
        for definition in group.items:
            row = by_key.get(definition.key)
            if row is None:
                continue
            model = ClosureItemOut.model_validate(row)
            model.label = definition.label
            model.intent = definition.intent
            model.evidence_required = definition.evidence_required
            model.may_not_apply = definition.may_not_apply
            items.append(model)
        if items:
            groups.append(
                ClosureGroupOut(
                    key=group.key, title=group.title, intent=group.intent, items=items
                )
            )

    return ClosureOut(
        contract_id=contract.id,
        contract_reference=contract.reference,
        status=contract.status,
        opened_at=contract.closure_opened_at,
        closed_at=contract.closed_at,
        closure_note=contract.closure_note,
        settled=settled,
        total=total,
        blocking=service.blocking(db, contract) if rows else [],
        groups=groups,
    )


@router.post("/contracts/{contract_id}/closure", response_model=ClosureOut, status_code=201)
def open_closure(contract_id: uuid.UUID, db: Db, principal: CurrentUser) -> ClosureOut:
    """Begin closing an agreement, and write its checklist."""
    principal.require_role(*READERS)
    contract = _contract(db, contract_id)
    if contract.status in {"closed", "terminated", "lapsed"}:
        raise Conflict(f"{contract.reference} is already finished.")

    created = service.materialise_checklist(db, contract)
    if contract.closure_opened_at is None:
        contract.closure_opened_at = datetime.now(UTC)
    contract.status = "in_closure"
    db.flush()

    audit.record(
        db,
        action="contract_closure_opened",
        object_type="contract",
        object_id=contract.reference,
        actor_id=principal.user_id,
        actor_label=principal.name,
        entity=contract.entity,
        after_state={"items": len(created), "status": contract.status},
    )
    return _closure_out(db, contract)


@router.get("/contracts/{contract_id}/closure", response_model=ClosureOut)
def read_closure(contract_id: uuid.UUID, db: Db, principal: CurrentUser) -> ClosureOut:
    contract = _contract(db, contract_id)
    _mine_or_legal(contract, principal)
    return _closure_out(db, contract)


@router.post("/closure-items/{item_id}", response_model=ClosureOut)
def update_closure_item(
    item_id: uuid.UUID, payload: ClosureItemUpdate, db: Db, principal: CurrentUser
) -> ClosureOut:
    """Confirm one line, or record that it does not apply."""
    principal.require_role(*LEGAL)
    item = db.get(ContractClosureItem, item_id)
    if item is None:
        raise NotFound("That checklist line was not found.")

    contract = _contract(db, item.contract_id)
    if contract.closed_at is not None:
        raise Conflict(
            f"{contract.reference} is closed. Its checklist is the record of how it "
            "closed and does not change afterwards."
        )
    if payload.status not in vocab.CLOSURE_STATUSES:
        raise ValidationFailed(
            "That is not a state a checklist line can be in.",
            {"status": f"One of {', '.join(vocab.CLOSURE_STATUSES)}."},
        )

    allowed, reason = service.may_confirm(
        item, payload.status, payload.evidence_reference, payload.note
    )
    if not allowed:
        field = "note" if payload.status == "not_applicable" else "evidence_reference"
        raise ValidationFailed(reason, {field: reason})

    item.status = payload.status
    item.evidence_reference = payload.evidence_reference
    item.evidence_document_id = payload.evidence_document_id
    item.note = payload.note
    if payload.status == "outstanding":
        item.confirmed_by_id = None
        item.confirmed_at = None
    else:
        item.confirmed_by_id = uuid.UUID(principal.user_id)
        item.confirmed_at = datetime.now(UTC)

    audit.record(
        db,
        action="closure_item_recorded",
        object_type="contract_closure_item",
        object_id=f"{contract.reference}:{item.item_key}",
        actor_id=principal.user_id,
        actor_label=principal.name,
        entity=contract.entity,
        after_state={
            "status": payload.status,
            "evidence": payload.evidence_reference,
            "note": payload.note,
        },
    )
    return _closure_out(db, contract)


@router.post("/contracts/{contract_id}/close", response_model=ClosureOut)
def close_contract(
    contract_id: uuid.UUID, payload: CloseRequest, db: Db, principal: CurrentUser
) -> ClosureOut:
    """Close it, if everything the checklist required is settled.

    The refusal here is the module. A closure that can be forced is a checklist
    that will be ticked, and the line it would be ticked over is usually the
    return or deletion of personal data.
    """
    principal.require_role(Role.HEAD_OF_LEGAL, Role.ADMIN)
    principal.require_step_up("Closing a contract")
    contract = _contract(db, contract_id)

    if contract.closed_at is not None:
        raise Conflict(f"{contract.reference} is already closed.")
    if payload.status not in {"closed", "terminated", "lapsed"}:
        raise ValidationFailed(
            "That is not a way a contract ends.",
            {"status": "One of closed, terminated, lapsed."},
        )

    reasons = service.blocking(db, contract)
    if reasons:
        raise Refused(f"{contract.reference} cannot be closed yet.", reasons)

    service.close(contract, payload.status, payload.note)

    audit.record(
        db,
        action="contract_closed",
        object_type="contract",
        object_id=contract.reference,
        actor_id=principal.user_id,
        actor_label=principal.name,
        entity=contract.entity,
        after_state={"status": payload.status, "note": payload.note},
    )
    return _closure_out(db, contract)


# ======================================================== section 14, register


@router.patch("/contracts/{contract_id}/register", response_model=dict)
def update_register(
    contract_id: uuid.UUID, payload: RegisterUpdate, db: Db, principal: CurrentUser
) -> dict:
    """The register fields, section 14.

    ``user_department`` and ``contract_owner_id`` are the two whose absence
    explains why the register lived in a spreadsheet: an agreement with no named
    owner and no recorded department is one nobody can be asked about.
    """
    principal.require_role(*LEGAL)
    contract = _contract(db, contract_id)

    before = {
        "user_department": contract.user_department,
        "contract_owner_id": str(contract.contract_owner_id),
        "status": contract.status,
    }

    if payload.contract_owner_id is not None:
        if db.get(User, payload.contract_owner_id) is None:
            raise ValidationFailed(
                "That person is not on the platform.",
                {"contract_owner_id": "Choose somebody who can be asked about it."},
            )
        contract.contract_owner_id = payload.contract_owner_id
    if payload.status is not None:
        if payload.status not in vocab.CONTRACT_STATUSES:
            raise ValidationFailed(
                "That is not a contract status.",
                {"status": f"One of {', '.join(vocab.CONTRACT_STATUSES)}."},
            )
        if payload.status in {"closed", "terminated", "lapsed"}:
            raise Conflict(
                "Ending an agreement goes through closure, which checks that the "
                "data has come back."
            )
        contract.status = payload.status

    for field in (
        "user_department",
        "payment_terms",
        "key_deliverables",
        "milestones",
        "termination_deadline",
        "remarks",
    ):
        value = getattr(payload, field)
        if value is not None:
            setattr(contract, field, value)

    if payload.termination_deadline is None and contract.termination_deadline is None:
        contract.termination_deadline = service.derive_termination_deadline(
            contract.end_date, contract.notice_period_days
        )

    audit.record(
        db,
        action="contract_register_updated",
        object_type="contract",
        object_id=contract.reference,
        actor_id=principal.user_id,
        actor_label=principal.name,
        entity=contract.entity,
        before_state=before,
        after_state={
            "user_department": contract.user_department,
            "contract_owner_id": str(contract.contract_owner_id),
            "status": contract.status,
        },
    )
    return {"message": f"The register entry for {contract.reference} was updated."}
