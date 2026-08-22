"""Authentication, roles and step-up.

In production Keycloak federates Microsoft Entra ID and Google Workspace, and
the API verifies the resulting OIDC token. For a self-contained deployment the
API can issue its own tokens instead, selected by ``DSNLAI_AUTH_MODE``. The claim
shape is identical in both modes, so nothing downstream changes.
"""

import base64
import hashlib
import hmac
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from typing import Any

import bcrypt
from jose import JWTError, jwt

from app.core.config import settings
from app.core.errors import Forbidden, StepUpRequired, Unauthenticated
from app.domain.enums import Role

ALGORITHM = "HS256"


def _prepare(raw: str) -> bytes:
    """bcrypt truncates at 72 bytes, so the password is digested first.

    Without this a long passphrase silently loses everything past the 72nd
    byte, which weakens it without telling anyone.
    """
    return base64.b64encode(hashlib.sha256(raw.encode("utf-8")).digest())


def hash_password(raw: str) -> str:
    return bcrypt.hashpw(_prepare(raw), bcrypt.gensalt()).decode("utf-8")


def verify_password(raw: str, hashed: str) -> bool:
    try:
        return bcrypt.checkpw(_prepare(raw), hashed.encode("utf-8"))
    except ValueError:
        return False

@dataclass
class Principal:
    """The authenticated caller. Effective permission is the intersection of
    role, entity and matter access (PRD section 5.2)."""

    user_id: str
    subject: str
    name: str
    email: str
    roles: list[str]
    entities: list[str]
    authenticated_at: datetime
    session_id: str = ""
    extra: dict[str, Any] = field(default_factory=dict)

    def has_role(self, *roles: Role | str) -> bool:
        wanted = {r.value if isinstance(r, Role) else r for r in roles}
        return bool(wanted & set(self.roles))

    def require_role(self, *roles: Role | str) -> None:
        if not self.has_role(*roles):
            names = ", ".join(sorted(r.value if isinstance(r, Role) else r for r in roles))
            raise Forbidden(f"This action requires one of these roles: {names}.")

    def in_entity(self, entity: str) -> bool:
        return entity in self.entities

    @property
    def is_admin(self) -> bool:
        return self.has_role(Role.ADMIN)

    @property
    def is_head_of_legal(self) -> bool:
        return self.has_role(Role.HEAD_OF_LEGAL)

    @property
    def mfa_satisfied(self) -> bool:
        return bool(self.extra.get("mfa"))

    def require_step_up(self, action: str) -> None:
        """Signature, clause publication, restricted access and administrative
        changes all need a fresh authentication (LOP-M15-US-02).

        Where the role carries a second-factor requirement, fresh means the
        factor as well as the password. Signing in is not gated on the factor,
        because someone who cannot yet enrol still has read work to do; the
        privileged act is what the factor protects.
        """
        window = timedelta(minutes=settings.dsnlai_step_up_window_minutes)
        if datetime.now(UTC) - self.authenticated_at > window:
            raise StepUpRequired(action)

        from app.core import mfa

        if mfa.is_required_for(self.roles) and not self.mfa_satisfied:
            raise StepUpRequired(
                f"{action} with your second factor. This role requires one."
            )

def create_access_token(
    *,
    subject: str,
    user_id: str,
    name: str,
    email: str,
    roles: list[str],
    entities: list[str],
    session_id: str,
    authenticated_at: datetime | None = None,
    mfa_satisfied: bool = False,
) -> str:
    now = datetime.now(UTC)
    auth_time = authenticated_at or now
    claims = {
        "sub": subject,
        "uid": user_id,
        "name": name,
        "email": email,
        "roles": roles,
        "entities": entities,
        "sid": session_id,
        "auth_time": int(auth_time.timestamp()),
        "mfa": mfa_satisfied,
        "iat": int(now.timestamp()),
        "exp": int((now + timedelta(minutes=settings.dsnlai_access_token_minutes)).timestamp()),
        "aud": settings.dsnlai_oidc_audience,
    }
    return jwt.encode(claims, settings.dsnlai_secret_key, algorithm=ALGORITHM)

def decode_token(token: str) -> Principal:
    try:
        claims = jwt.decode(
            token,
            settings.dsnlai_secret_key,
            algorithms=[ALGORITHM],
            audience=settings.dsnlai_oidc_audience,
        )
    except JWTError as exc:
        raise Unauthenticated("The session token is not valid.") from exc

    return Principal(
        user_id=claims.get("uid", ""),
        subject=claims.get("sub", ""),
        name=claims.get("name", ""),
        email=claims.get("email", ""),
        roles=list(claims.get("roles", [])),
        entities=list(claims.get("entities", [])),
        authenticated_at=datetime.fromtimestamp(claims.get("auth_time", 0), tz=UTC),
        session_id=claims.get("sid", ""),
        extra={"mfa": bool(claims.get("mfa"))},
    )

def sign_webhook(payload: bytes, secret: str | None = None) -> str:
    """Webhooks are signed and replay-protected (PRD section 12.1)."""
    key = (secret or settings.dsnlai_secret_key).encode()
    return hmac.new(key, payload, hashlib.sha256).hexdigest()

def verify_webhook(payload: bytes, signature: str, secret: str | None = None) -> bool:
    return hmac.compare_digest(sign_webhook(payload, secret), signature)
