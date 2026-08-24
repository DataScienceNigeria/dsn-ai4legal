"""Authentication.

Production federates Microsoft Entra ID and Google Workspace through Keycloak.
This endpoint group serves the local mode, where the API issues its own token
with the same claim shape.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime

from fastapi import APIRouter, Request
from pydantic import BaseModel
from sqlalchemy import select

from app.core import audit, mfa
from app.core.config import settings
from app.core.deps import AnonDb, CurrentUser, client_ip
from app.core.errors import Conflict, Unauthenticated, ValidationFailed
from app.core.security import create_access_token, verify_password
from app.db.models.organisation import User
from app.schemas.common import Ack

router = APIRouter(prefix="/auth", tags=["auth"])


class LoginRequest(BaseModel):
    email: str
    password: str
    code: str | None = None
    """The second factor, where the account has one enrolled."""


class MfaEnrolment(BaseModel):
    secret: str
    provisioning_uri: str
    #: The same URI as a scannable SVG, so nobody has to type the secret.
    provisioning_qr: str
    recovery_codes: list[str]


class MfaConfirm(BaseModel):
    code: str


class MfaStatus(BaseModel):
    #: Whether the module is in force at all. Off is off: an account that
    #: enrolled while it was on is not asked for a code, and no account can
    #: enrol while it is off. Without this the interface would keep offering
    #: enrolment for a factor nothing will ever check.
    enabled: bool
    enrolled: bool
    required: bool
    recovery_codes_remaining: int


class TokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    expires_in: int


class MeResponse(BaseModel):
    id: str
    name: str
    email: str
    initials: str
    roles: list[str]
    entities: list[str]
    step_up_valid: bool
    mfa_enrolled: bool = False
    mfa_required: bool = False


def _consume_recovery_code(user: User, code: str) -> bool:
    """A recovery code works once and is then gone from the record."""
    remaining = list(user.mfa_recovery_codes or [])
    candidate = (code or "").strip().lower()
    if candidate not in remaining:
        return False
    remaining.remove(candidate)
    user.mfa_recovery_codes = remaining
    return True


def _refuse_when_disabled() -> None:
    """One switch, one meaning.

    ``DSNLAI_MFA_ENABLED=false`` turns the module off everywhere, whether or
    not an account already holds a secret. Enrolment is refused as well as
    verification, because a factor enrolled while nothing will check it is
    worse than none: it looks like protection, and it is the state that locked
    the only administrator out of this platform once already.
    """
    if not mfa.enabled():
        raise Conflict(
            "The second factor module is switched off on this deployment. "
            "Nothing will ask for a code, so there is nothing to enrol."
        )


def _check_second_factor(
    db, user: User, code: str | None, request: Request
) -> bool:
    """Whether a second factor was actually presented and accepted.

    Enforce the factor where the account has one. Signing in is never gated on
    it, because someone who cannot yet enrol still has reading to do; the
    privileged act is what the factor protects, and ``require_step_up`` is
    where that is enforced.
    """
    if not mfa.enabled():
        # Turned off wholesale. An account that enrolled while it was on is
        # not asked for a code, because the module being off has to mean off
        # rather than off for some people.
        return False

    if not user.mfa_enrolled:
        # Not a refusal. Signing in is fine; the privileged act is what the
        # factor protects, and require_step_up is where that is enforced.
        return False

    if not code:
        raise ValidationFailed(
            "This account requires a second factor.",
            {"code": "Enter the six-digit code from your authenticator."},
        )

    counter = mfa.verify(user.mfa_secret or "", code, user.mfa_last_used_counter)
    if counter is None:
        if _consume_recovery_code(user, code):
            audit.record(
                db,
                action="mfa_recovery_code_used",
                object_type="app_user",
                object_id=str(user.id),
                actor_id=user.id,
                actor_label=user.name,
                ip_address=client_ip(request),
                detail=f"{len(user.mfa_recovery_codes or [])} codes remain.",
            )
            return True
        audit.record(
            db,
            action="mfa_failed",
            object_type="app_user",
            object_id=str(user.id),
            actor_id=user.id,
            actor_label=user.name,
            result="failure",
            ip_address=client_ip(request),
        )
        raise ValidationFailed(
            "That code was not accepted.",
            {"code": "Enter the current six-digit code, or one of your recovery codes."},
        )

    user.mfa_last_used_counter = counter
    return True


@router.post("/token")
def issue_token(payload: LoginRequest, db: AnonDb, request: Request) -> TokenResponse:
    if settings.dsnlai_auth_mode != "local":
        raise Unauthenticated(
            "This deployment authenticates at the identity provider. "
            "Present an OIDC bearer token instead."
        )

    user = db.execute(
        select(User).where(User.work_email == payload.email.lower())
    ).scalar_one_or_none()

    if user is None or not user.active or not user.password_hash:
        raise Unauthenticated("Those credentials were not recognised.")
    if not verify_password(payload.password, user.password_hash):
        audit.record(
            db,
            action="authentication_failed",
            object_type="app_user",
            object_id=str(user.id),
            actor_label=payload.email,
            result="failure",
            ip_address=client_ip(request),
        )
        raise Unauthenticated("Those credentials were not recognised.")

    factor_presented = _check_second_factor(db, user, payload.code, request)

    session_id = uuid.uuid4().hex
    user.last_login = datetime.now(UTC)

    audit.record(
        db,
        action="authenticated",
        object_type="app_user",
        object_id=str(user.id),
        actor_id=user.id,
        actor_label=user.name,
        session_id=session_id,
        ip_address=client_ip(request),
    )

    token = create_access_token(
        subject=user.subject,
        user_id=str(user.id),
        name=user.name,
        email=user.work_email,
        roles=list(user.roles or []),
        entities=user.entity_codes,
        session_id=session_id,
        mfa_satisfied=factor_presented,
    )
    return TokenResponse(
        access_token=token, expires_in=settings.dsnlai_access_token_minutes * 60
    )


@router.get("/me")
def me(principal: CurrentUser, db: AnonDb) -> MeResponse:
    user = db.execute(
        select(User).where(User.id == uuid.UUID(principal.user_id))
    ).scalar_one_or_none()
    parts = [p for p in principal.name.split() if p]
    step_up_age = datetime.now(UTC) - principal.authenticated_at
    return MeResponse(
        id=principal.user_id,
        name=principal.name,
        email=principal.email,
        initials="".join(p[0].upper() for p in parts[:2]) or "?",
        roles=principal.roles,
        entities=principal.entities,
        step_up_valid=step_up_age.total_seconds()
        < settings.dsnlai_step_up_window_minutes * 60,
        mfa_enrolled=bool(user and user.mfa_enrolled),
        mfa_required=mfa.is_required_for(principal.roles),
    )


@router.post("/step-up")
def step_up(
    payload: LoginRequest,
    principal: CurrentUser,
    db: AnonDb,
    request: Request,
) -> TokenResponse:
    """Re-authentication for signature, publication, restricted access and
    administration (LOP-M15-US-02)."""
    user = db.execute(
        select(User).where(User.id == uuid.UUID(principal.user_id))
    ).scalar_one_or_none()

    # Three different failures, and answering all of them with one sentence is
    # how a stale session came to look like a mistyped password. Each says what
    # the person can actually do about it.
    if user is None or not user.active:
        raise Unauthenticated(
            "This session belongs to an account that is no longer active. "
            "Sign in again."
        )
    if not user.password_hash:
        raise Unauthenticated(
            "This account signs in through the directory and has no password here, "
            "so it cannot re-authenticate this way."
        )
    if not verify_password(payload.password, user.password_hash):
        # Recorded. A failed re-authentication in front of a privileged act is
        # precisely the event an audit trail exists to hold, and until now the
        # refusal returned before anything was written.
        audit.record(
            db,
            action="step_up_failed",
            object_type="app_user",
            object_id=str(user.id),
            actor_id=user.id,
            actor_label=user.name,
            session_id=principal.session_id,
            ip_address=client_ip(request),
            result="failure",
            detail="The password did not match.",
        )
        raise Unauthenticated("That password was not accepted.")

    # Step-up is the moment the factor matters most, so it is demanded here
    # even where sign-in let it pass.
    factor_presented = _check_second_factor(db, user, payload.code, request)

    audit.record(
        db,
        action="step_up_authentication",
        object_type="app_user",
        object_id=str(user.id),
        actor_id=user.id,
        actor_label=user.name,
        session_id=principal.session_id,
        ip_address=client_ip(request),
    )
    token = create_access_token(
        subject=user.subject,
        user_id=str(user.id),
        name=user.name,
        email=user.work_email,
        roles=list(user.roles or []),
        entities=user.entity_codes,
        session_id=principal.session_id,
        authenticated_at=datetime.now(UTC),
        mfa_satisfied=factor_presented,
    )
    return TokenResponse(
        access_token=token, expires_in=settings.dsnlai_access_token_minutes * 60
    )


@router.get("/mfa")
def mfa_status(principal: CurrentUser, db: AnonDb) -> MfaStatus:
    user = db.execute(
        select(User).where(User.id == uuid.UUID(principal.user_id))
    ).scalar_one_or_none()
    if user is None:
        raise Unauthenticated("That account was not found.")
    return MfaStatus(
        enabled=mfa.enabled(),
        # An enrolment that survives the module being switched off is reported
        # as what it is: a stored secret nothing consults. Saying "enrolled"
        # while no code is ever demanded would be a claim about protection
        # that is not there.
        enrolled=user.mfa_enrolled and mfa.enabled(),
        required=mfa.is_required_for(list(user.roles or [])),
        recovery_codes_remaining=len(user.mfa_recovery_codes or []),
    )


@router.post("/mfa/enrol")
def enrol_mfa(
    principal: CurrentUser, db: AnonDb, request: Request, restart: bool = False
) -> MfaEnrolment:
    """Start enrolment. The factor is not active until a code confirms it.

    Activating on issue would lock someone out of their own account whenever
    the QR code failed to scan, so the secret sits unconfirmed until proven.
    """
    user = db.execute(
        select(User).where(User.id == uuid.UUID(principal.user_id))
    ).scalar_one_or_none()
    if user is None:
        raise Unauthenticated("That account was not found.")
    _refuse_when_disabled()
    if user.mfa_enrolled:
        raise Conflict(
            "A second factor is already enrolled. Remove it before enrolling another."
        )

    # An enrolment already under way is offered again rather than replaced.
    # Rotating the secret every time the dialog opened silently invalidated
    # whatever the authenticator had already been given, and left a second
    # entry on the phone under the same name as the first, so the obvious
    # recovery from a failed attempt, opening it again, was the thing that
    # guaranteed the next attempt failed too.
    if restart or not user.mfa_secret:
        user.mfa_secret = mfa.generate_secret()
        user.mfa_recovery_codes = mfa.generate_recovery_codes()
        user.mfa_last_used_counter = None
    secret = user.mfa_secret
    codes = list(user.mfa_recovery_codes or [])
    user.mfa_enrolled_at = None
    uri = mfa.provisioning_uri(secret, user.work_email)

    audit.record(
        db,
        action="mfa_enrolment_started",
        object_type="app_user",
        object_id=str(user.id),
        actor_id=user.id,
        actor_label=user.name,
        ip_address=client_ip(request),
    )
    return MfaEnrolment(
        secret=secret,
        provisioning_uri=uri,
        provisioning_qr=mfa.provisioning_qr(uri),
        recovery_codes=codes,
    )


def _why_rejected(user: User, code: str) -> str:
    """Tell the difference between a slow clock and the wrong entry.

    "That code was not accepted" is true of both and useful for neither. A
    code that belongs to this secret but to another minute is a clock; a code
    that belongs to no minute at all is a different secret, which is what a
    stale authenticator entry looks like.
    """
    drift = mfa.drift_windows(user.mfa_secret or "", code)
    if drift is None:
        return (
            "That code does not belong to this secret. If your authenticator holds more than "
            "one entry for this platform, an older one is being read: delete them, scan the "
            "code above again, and use the entry it creates."
        )
    seconds = abs(drift) * 30
    how_far = f"{seconds} seconds" if seconds < 120 else f"{round(seconds / 60)} minutes"
    direction = "behind" if drift < 0 else "ahead of"
    return (
        f"That code belongs to this secret but to a different minute: the device is roughly "
        f"{how_far} {direction} this server. Turn on automatic time on the device, wait for the "
        "next code, and try again."
    )


@router.post("/mfa/confirm")
def confirm_mfa(
    payload: MfaConfirm, principal: CurrentUser, db: AnonDb, request: Request
) -> MfaStatus:
    """Prove the authenticator holds the secret, and the factor goes live."""
    _refuse_when_disabled()
    user = db.execute(
        select(User).where(User.id == uuid.UUID(principal.user_id))
    ).scalar_one_or_none()
    if user is None or not user.mfa_secret:
        raise ValidationFailed(
            "There is no enrolment to confirm.",
            {"code": "Start enrolment before confirming it."},
        )

    counter = mfa.verify(user.mfa_secret, payload.code, user.mfa_last_used_counter)
    if counter is None:
        # Not Unauthenticated. The session is perfectly good; it is the six
        # digits that are wrong, and answering with a 401 told every client
        # that the caller had been signed out mid-enrolment.
        raise ValidationFailed(
            "That code was not accepted.",
            {"code": _why_rejected(user, payload.code)},
        )

    user.mfa_enrolled_at = datetime.now(UTC)
    user.mfa_last_used_counter = counter

    audit.record(
        db,
        action="mfa_enrolled",
        object_type="app_user",
        object_id=str(user.id),
        actor_id=user.id,
        actor_label=user.name,
        ip_address=client_ip(request),
    )
    return MfaStatus(
        enabled=mfa.enabled(),
        enrolled=True,
        required=mfa.is_required_for(list(user.roles or [])),
        recovery_codes_remaining=len(user.mfa_recovery_codes or []),
    )


@router.delete("/mfa")
def remove_mfa(
    payload: LoginRequest, principal: CurrentUser, db: AnonDb, request: Request
) -> Ack:
    """Removing the factor needs the password and the factor itself.

    Anything less would make the factor removable by whoever already holds the
    session, which is the case it exists to defend against.
    """
    user = db.execute(
        select(User).where(User.id == uuid.UUID(principal.user_id))
    ).scalar_one_or_none()
    if user is None or not user.password_hash or not verify_password(
        payload.password, user.password_hash
    ):
        raise Unauthenticated("Re-authentication failed.")
    if user.mfa_enrolled:
        _check_second_factor(db, user, payload.code, request)
    if mfa.is_required_for(list(user.roles or [])):
        raise Conflict(
            "This role requires a second factor, so it cannot be removed. "
            "Enrol a new authenticator instead."
        )

    user.mfa_secret = None
    user.mfa_enrolled_at = None
    user.mfa_recovery_codes = []
    user.mfa_last_used_counter = None

    audit.record(
        db,
        action="mfa_removed",
        object_type="app_user",
        object_id=str(user.id),
        actor_id=user.id,
        actor_label=user.name,
        ip_address=client_ip(request),
    )
    return Ack(message="The second factor is removed from this account.")
