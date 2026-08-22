"""OIDC token verification, PRD section 5.1.

In production Keycloak federates Microsoft Entra ID and Google Workspace, and
this is the half that lives here: verifying the token the provider issued
against its published keys and mapping its claims onto the platform's role
model. Nothing downstream can tell the difference between a token verified here
and one this API issued itself, because the Principal is the same shape.

The key set is fetched over the network and cached. A key that has rotated is
picked up on the next miss rather than on a schedule, so a rotation does not
need a restart.
"""

from __future__ import annotations

import logging
import threading
import time
from datetime import UTC, datetime
from typing import Any

import httpx
from jose import JWTError, jwt

from app.core.config import settings
from app.core.errors import Unauthenticated
from app.core.security import Principal

logger = logging.getLogger(__name__)

_lock = threading.Lock()
_cache: dict[str, Any] = {"keys": None, "fetched_at": 0.0}

SUPPORTED_ALGORITHMS = ["RS256", "RS384", "RS512", "ES256", "ES384"]

NOT_CONFIGURED = (
    "This deployment is set to authenticate at the identity provider, but no "
    "key set is configured. Set DSNLAI_OIDC_JWKS_URL, or set "
    "DSNLAI_AUTH_MODE back to local."
)


def _discover_jwks_url() -> str:
    """Fall back to the issuer's discovery document when no URL is given."""
    if settings.dsnlai_oidc_jwks_url:
        return settings.dsnlai_oidc_jwks_url
    if not settings.dsnlai_oidc_issuer:
        raise Unauthenticated(NOT_CONFIGURED)

    url = settings.dsnlai_oidc_issuer.rstrip("/") + "/.well-known/openid-configuration"
    try:
        response = httpx.get(url, timeout=10.0)
        response.raise_for_status()
        jwks_url = response.json().get("jwks_uri")
    except (httpx.HTTPError, ValueError) as exc:
        raise Unauthenticated(
            "The identity provider's discovery document could not be read."
        ) from exc
    if not jwks_url:
        raise Unauthenticated("The discovery document names no key set.")
    return str(jwks_url)


def jwks(force: bool = False) -> dict[str, Any]:
    """The issuer's key set, cached for the configured window."""
    age = time.monotonic() - _cache["fetched_at"]
    if not force and _cache["keys"] is not None and age < settings.dsnlai_oidc_jwks_cache_seconds:
        return _cache["keys"]

    with _lock:
        url = _discover_jwks_url()
        try:
            response = httpx.get(url, timeout=10.0)
            response.raise_for_status()
            keys = response.json()
        except (httpx.HTTPError, ValueError) as exc:
            if _cache["keys"] is not None:
                # A provider that is briefly unreachable should not sign
                # everyone out, so the last good key set stands.
                logger.warning("The key set could not be refreshed. The cached one stands.")
                return _cache["keys"]
            raise Unauthenticated(
                "The identity provider's key set could not be read."
            ) from exc
        _cache["keys"] = keys
        _cache["fetched_at"] = time.monotonic()
        return keys


def _claim_list(claims: dict[str, Any], path: str) -> list[str]:
    """Read a claim that may be nested, as Keycloak's realm_access.roles is."""
    node: Any = claims
    for part in path.split("."):
        if not isinstance(node, dict):
            return []
        node = node.get(part)
    if isinstance(node, str):
        return [item.strip() for item in node.split() if item.strip()]
    if isinstance(node, list):
        return [str(item) for item in node]
    return []


def _decode(token: str, keys: dict[str, Any]) -> dict[str, Any]:
    return jwt.decode(
        token,
        keys,
        algorithms=SUPPORTED_ALGORITHMS,
        audience=settings.dsnlai_oidc_audience,
        issuer=settings.dsnlai_oidc_issuer or None,
        options={"verify_at_hash": False},
    )


def verify(token: str) -> Principal:
    """Verify a federated token and map it onto the platform's principal.

    Roles and entities come from the claims the provider was configured to
    send. A token that carries neither authenticates the person and authorises
    nothing, which is the correct outcome for an account the directory has not
    yet placed in a group.
    """
    try:
        claims = _decode(token, jwks())
    except JWTError:
        # A rotated key looks exactly like a bad signature, so try once more
        # with a fresh key set before rejecting the caller.
        try:
            claims = _decode(token, jwks(force=True))
        except JWTError as exc:
            raise Unauthenticated("That token was not accepted by this deployment.") from exc

    auth_time = claims.get("auth_time") or claims.get("iat") or 0
    return Principal(
        user_id=str(claims.get("uid") or claims.get("oid") or claims.get("sub", "")),
        subject=str(claims.get("sub", "")),
        name=str(claims.get("name") or claims.get("preferred_username") or ""),
        email=str(claims.get("email") or claims.get("upn") or "").lower(),
        roles=_claim_list(claims, settings.dsnlai_oidc_roles_claim),
        entities=_claim_list(claims, settings.dsnlai_oidc_entities_claim),
        authenticated_at=datetime.fromtimestamp(int(auth_time), tz=UTC),
        session_id=str(claims.get("sid") or claims.get("jti") or ""),
        extra={"issuer": str(claims.get("iss", "")), "federated": True},
    )
