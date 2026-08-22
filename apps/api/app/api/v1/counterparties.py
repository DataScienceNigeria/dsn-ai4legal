"""Counterparty and vendor governance, M13."""

from __future__ import annotations

import uuid

from fastapi import APIRouter, Query
from sqlalchemy import func, select

from app.core import audit
from app.core.deps import CurrentUser, Db
from app.core.errors import Conflict, NotFound
from app.db.models.contract import Contract
from app.db.models.counterparty import Counterparty, Vendor
from app.db.models.matter import DecisionRecord, Matter
from app.domain.enums import Role
from app.schemas.common import Ack
from app.schemas.governance import (
    CounterpartyCreate,
    CounterpartyCreateResult,
    CounterpartyOut,
    DuplicateWarning,
    MergeRequest,
    VendorOut,
)
from app.services import sequences

COUNTERPARTY_NOT_FOUND = "That counterparty was not found."

router = APIRouter(tags=["counterparties"])

DUPLICATE_THRESHOLD = 0.45


def find_duplicates(db, payload: CounterpartyCreate) -> list[DuplicateWarning]:
    """Fuzzy matching on name, registration number and domain."""
    warnings: list[DuplicateWarning] = []

    if payload.registration_number:
        for row in db.execute(
            select(Counterparty).where(
                Counterparty.registration_number == payload.registration_number
            )
        ).scalars():
            warnings.append(
                DuplicateWarning(
                    id=row.id,
                    reference=row.reference,
                    legal_name=row.legal_name,
                    similarity=1.0,
                    matched_on="registration number",
                )
            )

    if payload.domain:
        for row in db.execute(
            select(Counterparty).where(Counterparty.domain == payload.domain)
        ).scalars():
            if not any(w.id == row.id for w in warnings):
                warnings.append(
                    DuplicateWarning(
                        id=row.id,
                        reference=row.reference,
                        legal_name=row.legal_name,
                        similarity=1.0,
                        matched_on="domain",
                    )
                )

    similarity = func.similarity(Counterparty.legal_name, payload.legal_name)
    for row, score in db.execute(
        select(Counterparty, similarity)
        .where(similarity > DUPLICATE_THRESHOLD)
        .order_by(similarity.desc())
        .limit(5)
    ):
        if not any(w.id == row.id for w in warnings):
            warnings.append(
                DuplicateWarning(
                    id=row.id,
                    reference=row.reference,
                    legal_name=row.legal_name,
                    similarity=round(float(score), 3),
                    matched_on="legal name",
                )
            )
    return warnings


@router.get("/counterparties", response_model=list[CounterpartyOut])
def list_counterparties(
    db: Db, principal: CurrentUser, search: str | None = Query(default=None)
) -> list[Counterparty]:
    stmt = select(Counterparty).where(Counterparty.merged_into_id.is_(None))
    if search:
        stmt = stmt.where(Counterparty.legal_name.ilike(f"%{search}%"))
    return list(db.execute(stmt.order_by(Counterparty.legal_name).limit(200)).scalars())


@router.post("/counterparties", status_code=201)
def create_counterparty(
    payload: CounterpartyCreate, db: Db, principal: CurrentUser
) -> CounterpartyCreateResult:
    """Creation warns on likely duplicates and offers merge instead."""
    principal.require_role(Role.LEGAL_OPS, Role.COUNSEL, Role.HEAD_OF_LEGAL, Role.ADMIN)

    duplicates = find_duplicates(db, payload)
    if duplicates and not payload.confirm_despite_duplicates:
        return CounterpartyCreateResult(
            duplicates=duplicates,
            message=(
                f"{len(duplicates)} existing counterparties look like this one. "
                "Merge into one of them, or confirm that this is a separate entity."
            ),
        )

    record = Counterparty(
        reference=sequences.new_counterparty_reference(db),
        legal_name=payload.legal_name,
        counterparty_type=payload.counterparty_type,
        registration_number=payload.registration_number,
        domain=payload.domain,
        jurisdiction=payload.jurisdiction,
        relationship_class=payload.relationship_class,
        contacts=payload.contacts,
    )
    db.add(record)
    db.flush()

    audit.record(
        db,
        action="counterparty_created",
        object_type="counterparty",
        object_id=record.reference,
        actor_id=principal.user_id,
        actor_label=principal.name,
        after_state={"legal_name": record.legal_name},
    )
    return CounterpartyCreateResult(
        created=CounterpartyOut.model_validate(record),
        message=f"{record.reference} created.",
    )


@router.get("/counterparties/{counterparty_id}", response_model=CounterpartyOut)
def get_counterparty(
    counterparty_id: uuid.UUID, db: Db, principal: CurrentUser
) -> Counterparty:
    record = db.get(Counterparty, counterparty_id)
    if record is None:
        raise NotFound(COUNTERPARTY_NOT_FOUND)
    return record


@router.get("/counterparties/{counterparty_id}/history")
def counterparty_history(
    counterparty_id: uuid.UUID, db: Db, principal: CurrentUser
) -> dict:
    """All matters, contracts, positions and concessions, in date order."""
    principal.require_role(Role.LEGAL_OPS, Role.COUNSEL, Role.HEAD_OF_LEGAL, Role.ADMIN)
    record = db.get(Counterparty, counterparty_id)
    if record is None:
        raise NotFound(COUNTERPARTY_NOT_FOUND)

    matters = list(
        db.execute(
            select(Matter)
            .where(Matter.counterparty_id == counterparty_id)
            .order_by(Matter.created_at.desc())
        ).scalars()
    )
    contracts = list(
        db.execute(
            select(Contract)
            .where(Contract.counterparty_id == counterparty_id)
            .order_by(Contract.executed_at.desc().nulls_last())
        ).scalars()
    )
    decisions = list(
        db.execute(
            select(DecisionRecord)
            .where(DecisionRecord.counterparty_id == counterparty_id)
            .order_by(DecisionRecord.decided_at.desc())
        ).scalars()
    )

    return {
        "counterparty": CounterpartyOut.model_validate(record).model_dump(),
        "matters": [
            {
                "number": m.number,
                "title": m.title,
                "status": m.status,
                "tier": m.risk_tier,
                "created_at": m.created_at,
            }
            for m in matters
        ],
        "contracts": [
            {
                "reference": c.reference,
                "agreement_type": c.agreement_type,
                "executed_at": c.executed_at,
                "value_amount": float(c.value_amount) if c.value_amount else None,
            }
            for c in contracts
        ],
        "concessions": [
            {
                "sequence": d.sequence,
                "decision": d.decision,
                "reason": d.reason,
                "authority_level": d.authority_level,
                "decided_at": d.decided_at,
            }
            for d in decisions
        ],
        "negotiation_notes": record.negotiation_notes,
    }


@router.post("/counterparties/{counterparty_id}/merge")
def merge(
    counterparty_id: uuid.UUID,
    payload: MergeRequest,
    db: Db,
    principal: CurrentUser,
) -> Ack:
    """Merges retain both prior identifiers as aliases."""
    principal.require_role(Role.COUNSEL, Role.HEAD_OF_LEGAL, Role.ADMIN)

    source = db.get(Counterparty, counterparty_id)
    target = db.get(Counterparty, payload.into_id)
    if source is None or target is None:
        raise NotFound(COUNTERPARTY_NOT_FOUND)
    if source.id == target.id:
        raise Conflict("A counterparty cannot be merged into itself.")

    target.aliases = sorted(
        set(target.aliases or [])
        | set(source.aliases or [])
        | {source.legal_name, source.reference}
    )
    source.merged_into_id = target.id

    for matter in db.execute(
        select(Matter).where(Matter.counterparty_id == source.id)
    ).scalars():
        matter.counterparty_id = target.id
    for contract in db.execute(
        select(Contract).where(Contract.counterparty_id == source.id)
    ).scalars():
        contract.counterparty_id = target.id

    audit.record(
        db,
        action="counterparty_merged",
        object_type="counterparty",
        object_id=source.reference,
        actor_id=principal.user_id,
        actor_label=principal.name,
        after_state={"into": target.reference, "reason": payload.reason},
    )
    return Ack(
        message=(
            f"{source.reference} merged into {target.reference}. Both identifiers are "
            "retained as aliases."
        )
    )


@router.get("/vendors")
def list_vendors(db: Db, principal: CurrentUser) -> list[VendorOut]:
    principal.require_role(
        Role.LEGAL_OPS, Role.COUNSEL, Role.HEAD_OF_LEGAL, Role.PRIVACY, Role.ADMIN
    )
    names = {
        row.id: row.legal_name for row in db.execute(select(Counterparty)).scalars()
    }
    rows = []
    for vendor in db.execute(select(Vendor)).scalars():
        model = VendorOut.model_validate(vendor)
        model.legal_name = names.get(vendor.counterparty_id)
        rows.append(model)
    return rows


@router.get("/vendors/{vendor_id}/renewal-risk")
def renewal_risk(vendor_id: uuid.UUID, db: Db, principal: CurrentUser) -> dict:
    """A renewal task surfaces outstanding findings and expired assessments."""
    principal.require_role(
        Role.LEGAL_OPS, Role.COUNSEL, Role.HEAD_OF_LEGAL, Role.PRIVACY, Role.ADMIN
    )
    vendor = db.get(Vendor, vendor_id)
    if vendor is None:
        raise NotFound("That vendor was not found.")

    counterparty = db.get(Counterparty, vendor.counterparty_id)
    blockers: list[str] = []
    if vendor.open_security_findings:
        blockers.append(
            f"{vendor.open_security_findings} outstanding security findings."
        )
    if vendor.assessment_expired:
        blockers.append("The privacy or AI assessment has expired.")
    if vendor.performance_notes:
        blockers.append("Unresolved performance or incident notes are on the record.")

    return {
        "vendor_id": str(vendor.id),
        "counterparty": counterparty.legal_name if counterparty else None,
        "renewal_date": vendor.renewal_date,
        "clear_to_renew": not blockers,
        "blockers": blockers,
    }
