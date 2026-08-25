"""Request-scoped dependencies.

Every request opens one transaction, stamps the security context on it so the
row-level security policies apply, and closes it when the response is written.
"""

from collections.abc import Iterator
from typing import Annotated

from fastapi import Depends, Header, Request
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.errors import Forbidden, Unauthenticated
from app.core.security import Principal, decode_token
from app.db.session import AppSession, apply_security_context, owner_session
from app.domain.enums import Role

bearer = HTTPBearer(auto_error=False)


def _local_account(principal: Principal) -> Principal:
    """Bind a federated token to the platform's own record of the person.

    The directory says who they are. The platform's user record says what they
    may do, because that is what SCIM provisions and what an administrator can
    change without touching the directory. A token for someone the platform has
    never seen authenticates nobody.
    """
    from sqlalchemy import select

    from app.db.models.organisation import User

    with owner_session() as session:
        user = session.execute(
            select(User).where(User.subject == principal.subject)
        ).scalar_one_or_none()
        if user is None and principal.email:
            user = session.execute(
                select(User).where(User.work_email == principal.email)
            ).scalar_one_or_none()
        if user is None or not user.active:
            raise Unauthenticated(
                "That account is authenticated but not provisioned on this platform."
            )
        # Claims are used only where the platform holds nothing, so a directory
        # cannot quietly grant itself a role the platform did not agree to.
        return Principal(
            user_id=str(user.id),
            subject=user.subject,
            name=user.name,
            email=user.work_email,
            roles=list(user.roles or []) or principal.roles,
            entities=user.entity_codes or principal.entities,
            authenticated_at=principal.authenticated_at,
            session_id=principal.session_id,
            extra=principal.extra,
        )


def get_principal(
    credentials: Annotated[HTTPAuthorizationCredentials | None, Depends(bearer)],
) -> Principal:
    if credentials is None or not credentials.credentials:
        raise Unauthenticated()

    if settings.dsnlai_auth_mode == "local":
        # Bound to the live record, exactly as the federated path is. Trusting
        # the claims alone meant a token kept working after the account behind
        # it was deactivated or removed, until the token happened to expire,
        # and it meant a session could carry a user id that resolves to nobody:
        # every endpoint that reads only claims kept working, and the first one
        # to look the account up answered with a refusal that named the wrong
        # cause.
        return _local_account(decode_token(credentials.credentials))

    from app.core import oidc

    try:
        return _local_account(oidc.verify(credentials.credentials))
    except Unauthenticated:
        # A deployment mid-migration can accept both, but only when it has been
        # told to. Off by default, because two accepted issuers is two ways in.
        if not settings.dsnlai_oidc_allow_local_fallback:
            raise
        return decode_token(credentials.credentials)

def get_session(
    principal: Annotated[Principal, Depends(get_principal)],
) -> Iterator[Session]:
    session = AppSession()
    try:
        apply_security_context(
            session,
            user_id=principal.user_id,
            entities=principal.entities,
            roles=principal.roles,
            bypass=False,
        )
        yield session
        session.commit()
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()

def get_anonymous_session() -> Iterator[Session]:
    """For unauthenticated endpoints such as token issue and health.

    The context is empty, so row-level security hides everything.
    """
    session = AppSession()
    try:
        apply_security_context(session, user_id=None, entities=[], roles=[], bypass=True)
        yield session
        session.commit()
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()

def get_entity(
    principal: Annotated[Principal, Depends(get_principal)],
    x_entity: Annotated[str | None, Header(alias="X-Entity")] = None,
) -> str:
    """Resolve the working entity for this request.

    All reporting and listing is entity-scoped by default. A caller may only
    select an entity they are a member of.
    """
    if x_entity:
        if not principal.in_entity(x_entity):
            raise Forbidden("That entity is not available to you.")
        return x_entity
    if not principal.entities:
        raise Forbidden("Your account has no entity membership.")
    return principal.entities[0]

def client_ip(request: Request) -> str | None:
    forwarded = request.headers.get("x-forwarded-for")
    if forwarded:
        return forwarded.split(",")[0].strip()
    return request.client.host if request.client else None

def require_legal(principal: Annotated[Principal, Depends(get_principal)]) -> Principal:
    principal.require_role(Role.COUNSEL, Role.HEAD_OF_LEGAL, Role.ADMIN)
    return principal

def require_counsel(principal: Annotated[Principal, Depends(get_principal)]) -> Principal:
    principal.require_role(Role.COUNSEL, Role.HEAD_OF_LEGAL, Role.ADMIN)
    return principal

def require_admin(principal: Annotated[Principal, Depends(get_principal)]) -> Principal:
    principal.require_role(Role.ADMIN)
    return principal

CurrentUser = Annotated[Principal, Depends(get_principal)]
Db = Annotated[Session, Depends(get_session)]
AnonDb = Annotated[Session, Depends(get_anonymous_session)]
WorkingEntity = Annotated[str, Depends(get_entity)]
