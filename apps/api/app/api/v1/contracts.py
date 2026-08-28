"""Executed archive and search, M08."""

from __future__ import annotations

import uuid
from datetime import date

from fastapi import APIRouter, Query
from sqlalchemy import or_, select

from app.core import audit
from app.core.deps import CurrentUser, Db, WorkingEntity
from app.core.errors import NotFound
from app.db.models.contract import Contract, Obligation
from app.db.models.counterparty import Counterparty
from app.db.models.document import Document
from app.db.models.matter import Matter
from app.schemas.common import CounterpartyBrief
from app.schemas.matters import ContractOut

router = APIRouter(tags=["contracts"])


def _decorate(db, contract: Contract) -> ContractOut:
    model = ContractOut.model_validate(contract)
    if contract.counterparty_id:
        counterparty = db.get(Counterparty, contract.counterparty_id)
        if counterparty:
            model.counterparty = CounterpartyBrief.model_validate(counterparty)
    matter = db.get(Matter, contract.matter_id)
    if matter:
        model.matter_number = matter.number

    # A varied agreement is two documents and the register has to show both.
    if contract.amends_contract_id:
        original = db.get(Contract, contract.amends_contract_id)
        model.amends_reference = original.reference if original else None
    return model


@router.get("/contracts/mine")
def my_contracts(
    db: Db, principal: CurrentUser, entity: WorkingEntity
) -> list[ContractOut]:
    """The agreements this person's matters produced.

    Section 15 of the guide puts day-to-day performance with the department that
    asked for the work, and a person cannot be accountable for a record they
    cannot open. Theirs and nobody else's: a department lead is not legal staff
    and the portfolio is not theirs to read.
    """
    stmt = (
        select(Contract)
        .join(Matter, Matter.id == Contract.matter_id)
        .where(
            Contract.entity == entity,
            Matter.requester_id == uuid.UUID(principal.user_id),
        )
        .order_by(Contract.effective_date.desc().nulls_last())
    )
    return [_decorate(db, contract) for contract in db.execute(stmt).scalars()]


@router.get("/contracts")
def search_contracts(
    db: Db,
    principal: CurrentUser,
    entity: WorkingEntity,
    q: str | None = Query(default=None),
    agreement_type: str | None = None,
    counterparty_id: uuid.UUID | None = None,
    matter_id: uuid.UUID | None = None,
    value_min: float | None = None,
    value_max: float | None = None,
    effective_from: date | None = None,
    effective_to: date | None = None,
    obligation_status: str | None = None,
    limit: int = Query(default=100, le=500),
) -> list[ContractOut]:
    """Search across counterparty, type, entity, value, dates and obligations.

    Row-level security applies the restricted-matter rules, so a restricted
    agreement is absent rather than redacted.
    """
    stmt = select(Contract).where(Contract.entity == entity)

    if agreement_type:
        stmt = stmt.where(Contract.agreement_type == agreement_type)
    if counterparty_id:
        stmt = stmt.where(Contract.counterparty_id == counterparty_id)
    if matter_id:
        stmt = stmt.where(Contract.matter_id == matter_id)
    if value_min is not None:
        stmt = stmt.where(Contract.value_amount >= value_min)
    if value_max is not None:
        stmt = stmt.where(Contract.value_amount <= value_max)
    if effective_from:
        stmt = stmt.where(Contract.effective_date >= effective_from)
    if effective_to:
        stmt = stmt.where(Contract.effective_date <= effective_to)
    if obligation_status:
        stmt = stmt.where(
            Contract.id.in_(
                select(Obligation.contract_id).where(Obligation.status == obligation_status)
            )
        )
    if q:
        pattern = f"%{q}%"
        matching_counterparties = select(Counterparty.id).where(
            Counterparty.legal_name.ilike(pattern)
        )
        matching_documents = select(Document.contract_id).where(
            Document.blocks.cast(__import__("sqlalchemy").Text).ilike(pattern)
        )
        stmt = stmt.where(
            or_(
                Contract.reference.ilike(pattern),
                Contract.counterparty_id.in_(matching_counterparties),
                Contract.id.in_(matching_documents),
            )
        )

    stmt = stmt.order_by(Contract.executed_at.desc().nulls_last()).limit(limit)
    return [_decorate(db, c) for c in db.execute(stmt).scalars()]


@router.get("/contracts/{contract_id}")
def get_contract(
    contract_id: uuid.UUID, db: Db, principal: CurrentUser
) -> ContractOut:
    contract = db.get(Contract, contract_id)
    if contract is None:
        raise NotFound("That contract was not found.")
    return _decorate(db, contract)


@router.get("/contracts/{contract_id}/provenance")
def provenance(contract_id: uuid.UUID, db: Db, principal: CurrentUser) -> dict:
    """What was signed, from which template and clauses, and by whom."""
    contract = db.get(Contract, contract_id)
    if contract is None:
        raise NotFound("That contract was not found.")

    document = (
        db.get(Document, contract.executed_document_id)
        if contract.executed_document_id
        else None
    )
    matter = db.get(Matter, contract.matter_id)

    audit.record(
        db,
        action="contract_provenance_read",
        object_type="contract",
        object_id=contract.reference,
        actor_id=principal.user_id,
        actor_label=principal.name,
        entity=contract.entity,
    )
    return {
        "reference": contract.reference,
        "matter_number": matter.number if matter else None,
        "content_hash": contract.content_hash,
        "authoritative": contract.authoritative,
        "executed_at": contract.executed_at,
        "executed_outside_platform": contract.executed_outside_platform,
        "template_version": document.template_version_ref if document else None,
        "clause_versions": document.clause_versions if document else [],
        "novel_clause_count": document.novel_clause_count if document else 0,
        "signature_certificate": contract.signature_certificate,
        "immutable": document.immutable if document else False,
    }
