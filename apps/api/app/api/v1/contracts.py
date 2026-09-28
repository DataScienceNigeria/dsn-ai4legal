"""Executed archive and search, M08."""

from __future__ import annotations

import uuid
from datetime import date
from typing import Annotated

from fastapi import APIRouter, File, Form, Query, Response, UploadFile
from sqlalchemy import or_, select

from app.api.v1.counterparties import find_duplicates
from app.core import audit
from app.core.deps import CurrentUser, Db, WorkingEntity
from app.core.errors import Forbidden, NotFound
from app.db.models.contract import Contract, Obligation
from app.db.models.counterparty import Counterparty
from app.db.models.document import Document
from app.db.models.matter import Matter
from app.db.models.platform import MemoryChunk
from app.domain.enums import Role
from app.schemas.common import CounterpartyBrief
from app.schemas.governance import CounterpartyCreate
from app.schemas.matters import ContractOut
from app.services import historical, storage

router = APIRouter(tags=["contracts"])


def _decorate(db, contract: Contract) -> ContractOut:
    model = ContractOut.model_validate(contract)
    if contract.counterparty_id:
        counterparty = db.get(Counterparty, contract.counterparty_id)
        if counterparty:
            model.counterparty = CounterpartyBrief.model_validate(counterparty)
    matter = db.get(Matter, contract.matter_id) if contract.matter_id else None
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
        # An agreement filed from before the platform has no blocks to search,
        # only the passages its text was read into, so those are searched too.
        matching_passages = (
            select(MemoryChunk.id)
            .where(
                MemoryChunk.source_type == "contract",
                MemoryChunk.body.ilike(pattern),
                MemoryChunk.source_reference.like(Contract.reference + " %"),
            )
            .exists()
        )
        stmt = stmt.where(
            or_(
                Contract.reference.ilike(pattern),
                Contract.counterparty_id.in_(matching_counterparties),
                Contract.id.in_(matching_documents),
                matching_passages,
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
    matter = db.get(Matter, contract.matter_id) if contract.matter_id else None

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
        "origin": contract.origin,
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


# ------------------------------------------------ signed before the platform
#
# The legal team files agreements executed before the platform existed, one or
# many at a time. Each file is read first and stored second: reading suggests
# what it is, a person confirms, and only then is anything written. The file is
# archived as it arrived and never converted into the platform's own document
# structure.

LEGAL_TEAM = (Role.COUNSEL, Role.HEAD_OF_LEGAL)


def _suggestion(value: historical.Suggestion | None) -> dict | None:
    return {"value": value.value, "source": value.source} if value else None


@router.post("/contracts/historical/read")
def read_historical(
    db: Db,
    principal: CurrentUser,
    entity: WorkingEntity,
    file: Annotated[UploadFile, File()],
) -> dict:
    """What a file appears to be, before anything is stored."""
    principal.require_role(*LEGAL_TEAM)

    data = file.file.read()
    name = file.filename or "agreement"
    content_type = file.content_type or "application/octet-stream"
    storage.validate_upload(name, content_type, data)

    digest = historical.file_hash(data)
    existing = historical.already_archived(db, entity, digest)
    reading = historical.read(name, content_type, data)

    guessed = historical.suggest_counterparty(name)
    matches = (
        find_duplicates(db, CounterpartyCreate(legal_name=guessed.value)) if guessed else []
    )
    return {
        "filename": name,
        "size_bytes": len(data),
        "hash": digest,
        "already_archived": existing.reference if existing else None,
        "readable": reading.readable,
        "kind": reading.kind,
        "unreadable_reason": reading.reason,
        "passages": len(reading.passages),
        "suggested": {
            "counterparty": _suggestion(guessed),
            "agreement_type": _suggestion(historical.suggest_type(name)),
            "effective_date": _suggestion(historical.suggest_date(reading)),
            "year": _suggestion(historical.suggest_year(name)),
        },
        "counterparty_matches": [
            {"id": str(m.id), "reference": m.reference, "legal_name": m.legal_name}
            for m in matches[:5]
        ],
    }


@router.post("/contracts/historical", status_code=201)
def archive_historical(
    db: Db,
    principal: CurrentUser,
    file: Annotated[UploadFile, File()],
    entity: Annotated[str, Form()],
    counterparty_id: Annotated[uuid.UUID, Form()],
    agreement_type: Annotated[str | None, Form()] = None,
    effective_date: Annotated[date | None, Form()] = None,
    end_date: Annotated[date | None, Form()] = None,
    value_amount: Annotated[float | None, Form()] = None,
    value_currency: Annotated[str, Form()] = "NGN",
    user_department: Annotated[str | None, Form()] = None,
    remarks: Annotated[str | None, Form()] = None,
) -> dict:
    """File one agreement signed before the platform, and read it into memory."""
    principal.require_role(*LEGAL_TEAM)
    if not principal.in_entity(entity):
        raise Forbidden("You cannot file agreements for that organisation.")

    contract, reading = historical.archive(
        db,
        principal,
        historical.ArchiveRequest(
            entity=entity,
            filename=file.filename or "agreement",
            content_type=file.content_type or "application/octet-stream",
            data=file.file.read(),
            counterparty_id=counterparty_id,
            agreement_type=agreement_type or None,
            effective_date=effective_date,
            end_date=end_date,
            value_amount=value_amount,
            value_currency=value_currency,
            user_department=(user_department or "").strip() or None,
            remarks=(remarks or "").strip() or None,
        ),
    )
    return {
        "id": str(contract.id),
        "reference": contract.reference,
        "searchable": reading.readable,
        "passages": len(reading.passages),
        "unreadable_reason": reading.reason,
    }


@router.get("/contracts/{contract_id}/original")
def original(contract_id: uuid.UUID, db: Db, principal: CurrentUser) -> Response:
    """The executed file exactly as it was archived."""
    contract = db.get(Contract, contract_id)
    if contract is None or not contract.executed_document_id:
        raise NotFound("No executed file is held for that agreement.")
    document = db.get(Document, contract.executed_document_id)
    if document is None or not document.storage_key:
        raise NotFound("No executed file is held for that agreement.")

    try:
        data = storage.store.get(document.storage_key)
    except Exception as exc:
        raise NotFound("The executed file could not be read from the archive.") from exc

    audit.record(
        db,
        action="executed_original_read",
        object_type="contract",
        object_id=contract.reference,
        actor_id=principal.user_id,
        actor_label=principal.name,
        entity=contract.entity,
    )
    media = storage.sniff(data) or (
        historical.DOCX if document.name.lower().endswith(".docx") else "application/octet-stream"
    )
    safe = document.name.replace('"', "")
    return Response(
        content=data,
        media_type=media,
        headers={
            "Content-Disposition": f'inline; filename="{safe}"',
            "X-Content-Hash": document.content_hash,
        },
    )
