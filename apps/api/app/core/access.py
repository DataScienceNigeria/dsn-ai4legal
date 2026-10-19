"""Which records inside an entity a caller may read.

Row-level security separates the entities and hides restricted matters. It
does not separate people inside an entity: a requester in DSN could list and
download every agreement DSN holds, which is the whole legal portfolio and not
theirs to read. The rule here is the one the portal already states for
``/requests/mine`` and ``/contracts/mine``, applied to the shared endpoints.

Legal staff, auditors and management read the entity's portfolio, as the
workspace has always shown them. A consultant does too, because row-level
security already narrows them to the matters they are named on. Everyone else
reads what they are party to: a matter they asked for, own, are named on or
have an approval step on (their own or one delegated to them), the agreement
that matter produced or that they own, and the documents and obligations that
hang off those.

A record outside that is answered with 404, not 403, so the response does not
confirm that it exists.
"""

from __future__ import annotations

import uuid

from sqlalchemy import Select, or_, select
from sqlalchemy.orm import Session

from app.core.errors import NotFound
from app.core.security import Principal
from app.db.models.contract import Approval, Contract, Obligation
from app.db.models.document import Document
from app.db.models.intake import Request as RequestRecord
from app.db.models.matter import Matter, MatterAccess
from app.db.models.organisation import User
from app.domain.enums import Role

#: Roles that read the entity's whole portfolio.
PORTFOLIO_ROLES: tuple[Role, ...] = (
    Role.COUNSEL,
    Role.HEAD_OF_LEGAL,
    Role.ADMIN,
    Role.AUDITOR,
    Role.MANAGEMENT,
    Role.CONSULTANT,
)


def sees_portfolio(principal: Principal) -> bool:
    return principal.has_role(*PORTFOLIO_ROLES)


def _me(principal: Principal) -> uuid.UUID:
    return uuid.UUID(principal.user_id)


def matters_of(principal: Principal) -> Select:
    """The ids of the matters the caller is party to."""
    me = _me(principal)
    acting_for = select(User.id).where(or_(User.id == me, User.delegate_id == me))
    return select(Matter.id).where(
        or_(
            Matter.requester_id == me,
            Matter.business_owner_id == me,
            Matter.responsible_lawyer_id == me,
            Matter.request_id.in_(
                select(RequestRecord.id).where(RequestRecord.requester_id == me)
            ),
            Matter.id.in_(select(MatterAccess.matter_id).where(MatterAccess.user_id == me)),
            Matter.id.in_(
                select(Approval.matter_id).where(Approval.approver_id.in_(acting_for))
            ),
        )
    )


def contracts_of(principal: Principal) -> Select:
    """The ids of the agreements the caller is party to."""
    return select(Contract.id).where(
        or_(
            Contract.contract_owner_id == _me(principal),
            Contract.matter_id.in_(matters_of(principal)),
        )
    )


def scope_matters(stmt: Select, principal: Principal) -> Select:
    if sees_portfolio(principal):
        return stmt
    return stmt.where(Matter.id.in_(matters_of(principal)))


def scope_contracts(stmt: Select, principal: Principal) -> Select:
    if sees_portfolio(principal):
        return stmt
    return stmt.where(Contract.id.in_(contracts_of(principal)))


def scope_obligations(stmt: Select, principal: Principal) -> Select:
    if sees_portfolio(principal):
        return stmt
    return stmt.where(
        or_(
            Obligation.owner_id == _me(principal),
            Obligation.matter_id.in_(matters_of(principal)),
            Obligation.contract_id.in_(contracts_of(principal)),
        )
    )


def _matter_visible(db: Session, principal: Principal, matter_id: uuid.UUID) -> bool:
    return (
        db.execute(matters_of(principal).where(Matter.id == matter_id)).first() is not None
    )


def _contract_visible(db: Session, principal: Principal, contract_id: uuid.UUID) -> bool:
    return (
        db.execute(contracts_of(principal).where(Contract.id == contract_id)).first()
        is not None
    )


def ensure_matter(db: Session, principal: Principal, matter: Matter, message: str) -> None:
    if sees_portfolio(principal) or _matter_visible(db, principal, matter.id):
        return
    raise NotFound(message)


def ensure_contract(
    db: Session, principal: Principal, contract: Contract, message: str
) -> None:
    if sees_portfolio(principal) or _contract_visible(db, principal, contract.id):
        return
    raise NotFound(message)


def ensure_document(
    db: Session, principal: Principal, document: Document, message: str
) -> None:
    if sees_portfolio(principal):
        return
    if document.matter_id and _matter_visible(db, principal, document.matter_id):
        return
    if document.contract_id and _contract_visible(db, principal, document.contract_id):
        return
    if (
        document.matter_id is None
        and document.contract_id is None
        and document.generated_by_id is not None
        and str(document.generated_by_id) == principal.user_id
    ):
        return
    raise NotFound(message)
