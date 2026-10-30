"""Request-scoped dependencies.

Every request opens one transaction, stamps the security context on it so the
row-level security policies apply, and closes it when the response is written.
"""

import ipaddress
from collections.abc import Iterator
from typing import Annotated

from fastapi import Depends, Header, Request
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy.orm import Session

from app.core import context
from app.core.config import settings
from app.core.errors import Forbidden, PasswordChangeRequired, Unauthenticated
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
            extra={**principal.extra, "password_must_change": bool(user.password_must_change)},
        )


def _remembered(principal: Principal) -> Principal:
    """Put the session on the request context, for the audit to pick up."""
    context.attach_session(principal.session_id)
    return principal


#: What an account whose password somebody else set may still reach: who it
#: is, and the change itself.
PASSWORD_CHANGE_PATHS = frozenset({"/api/v1/auth/me", "/api/v1/auth/password"})


def _password_changed(principal: Principal, request: Request) -> Principal:
    """Refuse everything but the change while the password is somebody else's.

    Checked on the server rather than left to the interface, because a token is
    as good from a script as from the browser. Local accounts only: a federated
    account's password belongs to the directory.
    """
    if (
        settings.dsnlai_auth_mode == "local"
        and principal.extra.get("password_must_change")
        and request.url.path not in PASSWORD_CHANGE_PATHS
    ):
        raise PasswordChangeRequired(
            "Your password was set by an administrator. Choose your own before you continue."
        )
    return principal


def get_principal(
    request: Request,
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
        return _password_changed(
            _remembered(_local_account(decode_token(credentials.credentials))), request
        )

    from app.core import oidc

    try:
        return _remembered(_local_account(oidc.verify(credentials.credentials)))
    except Unauthenticated:
        # A deployment mid-migration can accept both, but only when it has been
        # told to. Off by default, because two accepted issuers is two ways in.
        if not settings.dsnlai_oidc_allow_local_fallback:
            raise
        return _remembered(decode_token(credentials.credentials))

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

def _trusted(address: str) -> bool:
    try:
        ip = ipaddress.ip_address(address)
    except ValueError:
        return False
    return any(ip in network for network in settings.trusted_proxies)


def client_ip(request: Request) -> str | None:
    """The address the request came from, as far as it can be trusted.

    X-Forwarded-For is written by whoever sent the request, so its first entry
    is whatever the client chose to put there. It is read only when the direct
    peer is a configured proxy, and then from the right: each trusted proxy
    appends the address it saw, so the right-most entry that is not one of ours
    is the client as our own proxy saw it.
    """
    peer = request.client.host if request.client else None
    forwarded = request.headers.get("x-forwarded-for")
    if not forwarded or peer is None or not _trusted(peer):
        return peer
    hops = [hop.strip() for hop in forwarded.split(",") if hop.strip()]
    for hop in reversed(hops):
        if not _trusted(hop):
            return hop
    return hops[0] if hops else peer

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
