"""SCIM 2.0 provisioning, PRD section 5.1 and M15.

Joiners, movers and leavers arrive from the directory rather than from a person
retyping them here. That matters most for the leaver: an account the directory
has disabled should stop working on this platform without anyone remembering to
do it.

This implements the parts of RFC 7644 a directory actually calls: Users list,
get, create, replace, patch and delete, and a read-only Groups view mapped onto
the role model. Everything is audited, because provisioning is an access change.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime
from typing import Annotated, Any

from fastapi import APIRouter, Header, Query, Response
from sqlalchemy import func, select

from app.core import audit
from app.core.config import settings
from app.core.deps import AnonDb
from app.core.errors import Conflict, Forbidden, NotFound, Unauthenticated, ValidationFailed
from app.db.models.organisation import Organisation, User, UserEntity
from app.domain.enums import Role

router = APIRouter(prefix="/scim/v2", tags=["scim"])

USER_SCHEMA = "urn:ietf:params:scim:schemas:core:2.0:User"
GROUP_SCHEMA = "urn:ietf:params:scim:schemas:core:2.0:Group"
LIST_SCHEMA = "urn:ietf:params:scim:api:messages:2.0:ListResponse"
PATCH_SCHEMA = "urn:ietf:params:scim:api:messages:2.0:PatchOp"
ENTERPRISE_SCHEMA = "urn:ietf:params:scim:schemas:extension:enterprise:2.0:User"

KNOWN_ROLES = {role.value for role in Role}
DIRECTORY = "The directory, over SCIM"


def _authorise(authorization: str | None) -> None:
    """A shared bearer token, compared in constant time.

    SCIM is a machine-to-machine interface with no user behind it, so the
    ordinary session model does not apply. It is off unless configured, because
    an unconfigured provisioning endpoint is a way to create administrators.
    """
    import hmac

    if not settings.dsnlai_scim_enabled:
        raise Forbidden("SCIM provisioning is not enabled on this deployment.")
    if not settings.dsnlai_scim_token:
        raise Forbidden("SCIM provisioning is enabled but no token is configured.")

    presented = (authorization or "").removeprefix("Bearer ").strip()
    if not presented or not hmac.compare_digest(presented, settings.dsnlai_scim_token):
        raise Unauthenticated("That provisioning token was not recognised.")


def _roles_from(payload: dict[str, Any]) -> list[str]:
    """Read roles from the SCIM roles array, keeping only ones we know.

    A directory group this platform has never heard of grants nothing. Silently
    accepting it would let a directory administrator invent a role here.
    """
    raw: list[str] = []
    for entry in payload.get("roles") or []:
        if isinstance(entry, dict) and entry.get("value"):
            raw.append(str(entry["value"]))
        elif isinstance(entry, str):
            raw.append(entry)
    return sorted({role for role in raw if role in KNOWN_ROLES})


def _entities_from(payload: dict[str, Any]) -> list[str]:
    """Entity membership travels in the enterprise extension's division."""
    extension = payload.get(ENTERPRISE_SCHEMA) or {}
    division = extension.get("division") or extension.get("organization")
    if isinstance(division, str) and division.strip():
        return [part.strip().upper() for part in division.split(",") if part.strip()]
    return [settings.dsnlai_scim_default_entity]


def _email_from(payload: dict[str, Any]) -> str:
    emails = payload.get("emails") or []
    for entry in emails:
        if isinstance(entry, dict) and entry.get("primary") and entry.get("value"):
            return str(entry["value"]).lower()
    for entry in emails:
        if isinstance(entry, dict) and entry.get("value"):
            return str(entry["value"]).lower()
    if payload.get("userName"):
        return str(payload["userName"]).lower()
    raise ValidationFailed(
        "A user needs an email address.", {"emails": "No primary email was supplied."}
    )


def _name_from(payload: dict[str, Any], email: str) -> str:
    name = payload.get("displayName")
    if isinstance(name, str) and name.strip():
        return name.strip()
    parts = payload.get("name") or {}
    joined = " ".join(
        str(parts.get(key, "")).strip()
        for key in ("givenName", "familyName")
        if parts.get(key)
    ).strip()
    return joined or email.split("@")[0]


def _to_scim(user: User) -> dict[str, Any]:
    return {
        "schemas": [USER_SCHEMA, ENTERPRISE_SCHEMA],
        "id": str(user.id),
        "externalId": user.external_id,
        "userName": user.work_email,
        "displayName": user.name,
        "active": user.active,
        "emails": [{"value": user.work_email, "primary": True, "type": "work"}],
        "roles": [{"value": role, "type": "platform"} for role in (user.roles or [])],
        ENTERPRISE_SCHEMA: {"division": ",".join(user.entity_codes)},
        "meta": {
            "resourceType": "User",
            "created": user.created_at.isoformat() if user.created_at else None,
            "lastModified": user.updated_at.isoformat() if user.updated_at else None,
            "location": f"/api/v1/scim/v2/Users/{user.id}",
        },
    }


def _set_entities(db, user: User, codes: list[str]) -> None:
    """Membership is replaced wholesale, because that is what the directory
    is asserting. An entity the platform does not have is ignored rather than
    created, since creating one is a governance act, not a sync."""
    known = {
        code
        for (code,) in db.execute(select(Organisation.entity_code)).all()
    }
    wanted = {code for code in codes if code in known}
    existing = {membership.entity_code: membership for membership in user.entities}

    for code in wanted - set(existing):
        db.add(UserEntity(user_id=user.id, entity_code=code))
    for code in set(existing) - wanted:
        db.delete(existing[code])


def _find(db, user_id: str) -> User:
    try:
        key = uuid.UUID(user_id)
    except ValueError as exc:
        raise NotFound("That user was not found.") from exc
    user = db.get(User, key)
    if user is None:
        raise NotFound("That user was not found.")
    return user


@router.get("/Users")
def list_users(
    db: AnonDb,
    authorization: Annotated[str | None, Header()] = None,
    filter_expression: Annotated[str | None, Query(alias="filter")] = None,
    start_index: Annotated[int, Query(alias="startIndex", ge=1)] = 1,
    count: Annotated[int, Query(ge=1, le=200)] = 100,
) -> dict[str, Any]:
    """The list a directory reads before deciding what to create."""
    _authorise(authorization)

    stmt = select(User)
    # Directories filter on userName eq "..." almost exclusively, so that is
    # the one form supported. Anything else returns the unfiltered page rather
    # than pretending to have applied a filter it did not understand.
    if filter_expression and "userName" in filter_expression and " eq " in filter_expression:
        wanted = filter_expression.split(" eq ", 1)[1].strip().strip('"').lower()
        stmt = stmt.where(User.work_email == wanted)

    total = db.execute(
        select(func.count()).select_from(stmt.subquery())
    ).scalar_one()
    users = list(
        db.execute(
            stmt.order_by(User.work_email).offset(start_index - 1).limit(count)
        ).scalars()
    )
    return {
        "schemas": [LIST_SCHEMA],
        "totalResults": total,
        "startIndex": start_index,
        "itemsPerPage": len(users),
        "Resources": [_to_scim(user) for user in users],
    }


@router.get("/Users/{user_id}")
def get_user(
    user_id: str, db: AnonDb, authorization: Annotated[str | None, Header()] = None
) -> dict[str, Any]:
    _authorise(authorization)
    return _to_scim(_find(db, user_id))


@router.post("/Users", status_code=201)
def create_user(
    payload: dict[str, Any],
    db: AnonDb,
    authorization: Annotated[str | None, Header()] = None,
) -> dict[str, Any]:
    """A joiner. Roles come from the directory's groups, filtered to ones this
    platform recognises."""
    _authorise(authorization)

    email = _email_from(payload)
    existing = db.execute(
        select(User).where(User.work_email == email)
    ).scalar_one_or_none()
    if existing is not None:
        raise Conflict(f"{email} already exists on this platform.")

    user = User(
        subject=str(payload.get("externalId") or email),
        name=_name_from(payload, email),
        work_email=email,
        roles=_roles_from(payload),
        active=bool(payload.get("active", True)),
        external_id=payload.get("externalId"),
        provisioned_by="scim",
    )
    db.add(user)
    db.flush()
    _set_entities(db, user, _entities_from(payload))
    db.flush()
    # The relationship was loaded before the memberships existed, so the
    # response would otherwise show none of them.
    db.refresh(user)

    audit.record(
        db,
        action="user_provisioned",
        object_type="app_user",
        object_id=str(user.id),
        actor_label=DIRECTORY,
        after_state={"email": email, "roles": user.roles},
    )
    return _to_scim(user)


@router.put("/Users/{user_id}")
def replace_user(
    user_id: str,
    payload: dict[str, Any],
    db: AnonDb,
    authorization: Annotated[str | None, Header()] = None,
) -> dict[str, Any]:
    """A mover. The directory is asserting the whole record, so the whole
    record is replaced, including membership and roles."""
    _authorise(authorization)
    user = _find(db, user_id)
    before = {"roles": list(user.roles or []), "active": user.active}

    user.work_email = _email_from(payload)
    user.name = _name_from(payload, user.work_email)
    user.roles = _roles_from(payload)
    user.active = bool(payload.get("active", True))
    user.external_id = payload.get("externalId") or user.external_id
    user.provisioned_by = "scim"
    if not user.active and user.deprovisioned_at is None:
        user.deprovisioned_at = datetime.now(UTC)
    if user.active:
        user.deprovisioned_at = None
    _set_entities(db, user, _entities_from(payload))
    db.flush()
    db.refresh(user)

    audit.record(
        db,
        action="user_updated",
        object_type="app_user",
        object_id=str(user.id),
        actor_label=DIRECTORY,
        before_state=before,
        after_state={"roles": user.roles, "active": user.active},
    )
    return _to_scim(user)


def _apply_operation(user: User, operation: Any) -> None:
    """Apply one SCIM patch operation, ignoring anything unrecognised.

    A directory that sends an attribute this platform does not model should not
    fail the whole sync, and it should not quietly change something else.
    """
    if not isinstance(operation, dict):
        return

    path = str(operation.get("path") or "").lower()
    value = operation.get("value")
    if str(operation.get("op", "")).lower() == "remove" and path == "active":
        value = False

    if path == "active" or (isinstance(value, dict) and "active" in value):
        active = value.get("active") if isinstance(value, dict) else value
        user.active = str(active).lower() not in {"false", "0", "none"}
    elif path == "roles" and isinstance(value, list):
        user.roles = _roles_from({"roles": value})
    elif path == "displayname" and isinstance(value, str):
        user.name = value


@router.patch("/Users/{user_id}")
def patch_user(
    user_id: str,
    payload: dict[str, Any],
    db: AnonDb,
    authorization: Annotated[str | None, Header()] = None,
) -> dict[str, Any]:
    """The operation a directory uses to disable a leaver.

    Entra ID and Google Workspace both express deactivation as a patch setting
    active to false, so this is the path that matters most.
    """
    _authorise(authorization)
    user = _find(db, user_id)
    before = {"active": user.active, "roles": list(user.roles or [])}

    for operation in payload.get("Operations") or []:
        _apply_operation(user, operation)

    if not user.active and user.deprovisioned_at is None:
        user.deprovisioned_at = datetime.now(UTC)
    if user.active:
        user.deprovisioned_at = None
    db.flush()

    audit.record(
        db,
        action="user_updated" if user.active else "user_deprovisioned",
        object_type="app_user",
        object_id=str(user.id),
        actor_label=DIRECTORY,
        before_state=before,
        after_state={"active": user.active, "roles": user.roles},
    )
    return _to_scim(user)


@router.delete("/Users/{user_id}", status_code=204)
def delete_user(
    user_id: str, db: AnonDb, authorization: Annotated[str | None, Header()] = None
) -> Response:
    """A leaver is deactivated, never deleted.

    The record is on decisions, approvals and the audit chain. Removing the row
    would break attribution on work that was validly done, so the account stops
    working and stays readable.
    """
    _authorise(authorization)
    user = _find(db, user_id)
    user.active = False
    user.deprovisioned_at = datetime.now(UTC)
    db.flush()

    audit.record(
        db,
        action="user_deprovisioned",
        object_type="app_user",
        object_id=str(user.id),
        actor_label=DIRECTORY,
        after_state={"active": False},
        detail="Deactivated rather than deleted, so attribution survives.",
    )
    return Response(status_code=204)


@router.get("/Groups")
def list_groups(
    db: AnonDb, authorization: Annotated[str | None, Header()] = None
) -> dict[str, Any]:
    """The platform's roles, as groups, so a directory can map onto them.

    Read only. A group is a property of this platform's authority model, not
    something a directory gets to invent.
    """
    _authorise(authorization)

    members: dict[str, list[dict[str, str]]] = {role: [] for role in sorted(KNOWN_ROLES)}
    for user in db.execute(select(User).where(User.active.is_(True))).scalars():
        for role in user.roles or []:
            if role in members:
                members[role].append({"value": str(user.id), "display": user.name})

    groups = [
        {
            "schemas": [GROUP_SCHEMA],
            "id": role,
            "displayName": role,
            "members": people,
            "meta": {"resourceType": "Group", "location": f"/api/v1/scim/v2/Groups/{role}"},
        }
        for role, people in members.items()
    ]
    return {
        "schemas": [LIST_SCHEMA],
        "totalResults": len(groups),
        "startIndex": 1,
        "itemsPerPage": len(groups),
        "Resources": groups,
    }


@router.get("/ServiceProviderConfig")
def service_provider_config() -> dict[str, Any]:
    """What this endpoint supports, so a directory can configure itself.

    Unauthenticated by design: RFC 7644 says this document is discoverable, and
    it reveals nothing beyond which operations exist.
    """
    return {
        "schemas": ["urn:ietf:params:scim:schemas:core:2.0:ServiceProviderConfig"],
        "documentationUri": "https://datatracker.ietf.org/doc/html/rfc7644",
        "patch": {"supported": True},
        "bulk": {"supported": False, "maxOperations": 0, "maxPayloadSize": 0},
        "filter": {"supported": True, "maxResults": 200},
        "changePassword": {"supported": False},
        "sort": {"supported": False},
        "etag": {"supported": False},
        "authenticationSchemes": [
            {
                "type": "oauthbearertoken",
                "name": "OAuth Bearer Token",
                "description": "A shared bearer token issued to the directory.",
            }
        ],
    }
