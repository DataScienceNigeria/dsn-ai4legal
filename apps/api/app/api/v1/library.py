"""Template and clause library, M03."""

from __future__ import annotations

import difflib
import uuid
from datetime import date
from typing import Annotated

from fastapi import APIRouter, File, Query, UploadFile
from sqlalchemy import select

from app.core import audit
from app.core.deps import CurrentUser, Db, WorkingEntity
from app.core.errors import Conflict, NotFound, ValidationFailed
from app.db.models.library import (
    Clause,
    ClauseVersion,
    Playbook,
    Template,
    TemplateImport,
    TemplateVersion,
)
from app.domain.enums import Role, VersionStatus
from app.schemas.common import Ack
from app.schemas.matters import (
    ClauseOut,
    ClauseVersionOut,
    ImportAcceptance,
    ImportCandidateAcceptance,
    TemplateOut,
    TemplateVersionOut,
    VersionDiff,
    VersionDiffLine,
    VersionProposal,
)
from app.services import docx_import, storage

router = APIRouter(tags=["library"])


def _current_clause_version(clause: Clause) -> ClauseVersion | None:
    today = date.today()
    approved = [
        v
        for v in clause.versions
        if v.status == VersionStatus.APPROVED.value
        and (v.effective_date is None or v.effective_date <= today)
    ]
    return max(approved, key=lambda v: (v.major, v.minor), default=None)


def _current_template_version(template: Template) -> TemplateVersion | None:
    today = date.today()
    approved = [
        v
        for v in template.versions
        if v.status == VersionStatus.APPROVED.value
        and (v.effective_date is None or v.effective_date <= today)
    ]
    return max(approved, key=lambda v: (v.major, v.minor), default=None)


@router.get("/clauses")
def list_clauses(
    db: Db, principal: CurrentUser, entity: WorkingEntity
) -> list[ClauseOut]:
    """A requester never sees the clause library (PRD section 5.2)."""
    principal.require_role(
        Role.LEGAL_OPS, Role.COUNSEL, Role.HEAD_OF_LEGAL, Role.PRIVACY, Role.ADMIN
    )
    clauses = list(db.execute(select(Clause).order_by(Clause.category)).scalars())
    out = []
    for clause in clauses:
        if entity not in (clause.entity_applicability or []):
            continue
        model = ClauseOut.model_validate(clause)
        current = _current_clause_version(clause)
        model.current = ClauseVersionOut.model_validate(current) if current else None
        model.versions = [ClauseVersionOut.model_validate(v) for v in clause.versions]
        out.append(model)
    return out


@router.get("/clauses/{category}")
def get_clause(category: str, db: Db, principal: CurrentUser) -> ClauseOut:
    principal.require_role(
        Role.LEGAL_OPS, Role.COUNSEL, Role.HEAD_OF_LEGAL, Role.PRIVACY, Role.ADMIN
    )
    clause = db.execute(
        select(Clause).where(Clause.category == category.upper())
    ).scalar_one_or_none()
    if clause is None:
        raise NotFound("That clause category was not found.")

    model = ClauseOut.model_validate(clause)
    current = _current_clause_version(clause)
    model.current = ClauseVersionOut.model_validate(current) if current else None
    model.versions = [ClauseVersionOut.model_validate(v) for v in clause.versions]
    return model


@router.post("/clauses/{category}/versions", response_model=ClauseVersionOut, status_code=201)
def propose_clause_version(
    category: str, payload: VersionProposal, db: Db, principal: CurrentUser
) -> ClauseVersion:
    """Proposals create a draft version rather than editing in place."""
    principal.require_role(Role.COUNSEL, Role.HEAD_OF_LEGAL, Role.ADMIN)
    clause = db.execute(
        select(Clause).where(Clause.category == category.upper())
    ).scalar_one_or_none()
    if clause is None:
        raise NotFound("That clause category was not found.")

    open_drafts = [v for v in clause.versions if v.status == VersionStatus.DRAFT.value]
    if open_drafts:
        raise Conflict(
            f"{open_drafts[0].reference} is already an open proposal on this clause. "
            "Concurrent proposals must be merged before publication."
        )

    current = _current_clause_version(clause)
    major = (current.major if current else 1)
    minor = (current.minor + 1) if current else 1

    version = ClauseVersion(
        clause_id=clause.id,
        reference=f"CLS-{clause.category}-v{major}.{minor}",
        major=major,
        minor=minor,
        status=VersionStatus.DRAFT.value,
        house_position=payload.house_position or (current.house_position if current else ""),
        fallbacks=[f.model_dump() for f in (payload.fallbacks or [])]
        or (current.fallbacks if current else []),
        unacceptable_position=payload.unacceptable_position
        or (current.unacceptable_position if current else None),
        effective_date=payload.effective_date,
        review_date=payload.review_date,
        supersedes_id=current.id if current else None,
        provenance=payload.change_summary,
    )
    db.add(version)
    db.flush()

    audit.record(
        db,
        action="clause_version_proposed",
        object_type="clause_version",
        object_id=version.reference,
        actor_id=principal.user_id,
        actor_label=principal.name,
        after_state={"summary": payload.change_summary},
    )
    return version


@router.get("/clauses/{category}/diff")
def clause_diff(
    category: str,
    db: Db,
    principal: CurrentUser,
    from_reference: str = Query(alias="from"),
    to_reference: str = Query(alias="to"),
) -> VersionDiff:
    principal.require_role(Role.LEGAL_OPS, Role.COUNSEL, Role.HEAD_OF_LEGAL, Role.ADMIN)
    versions = {
        v.reference: v
        for v in db.execute(
            select(ClauseVersion).where(
                ClauseVersion.reference.in_([from_reference, to_reference])
            )
        ).scalars()
    }
    if from_reference not in versions or to_reference not in versions:
        raise NotFound("One of those versions was not found.")

    lines = []
    for line in difflib.unified_diff(
        versions[from_reference].house_position.split("\n"),
        versions[to_reference].house_position.split("\n"),
        lineterm="",
        n=2,
    ):
        if line.startswith("+++") or line.startswith("---"):
            continue
        kind = (
            "added"
            if line.startswith("+")
            else "removed"
            if line.startswith("-")
            else "context"
            if not line.startswith("@@")
            else "hunk"
        )
        lines.append(VersionDiffLine(kind=kind, text=line.lstrip("+-")))

    return VersionDiff(
        from_reference=from_reference, to_reference=to_reference, lines=lines
    )


@router.post("/versions/{reference}/publish")
def publish_version(reference: str, db: Db, principal: CurrentUser) -> Ack:
    """Publication is a controlled act.

    It requires the clause-owner role and a fresh authentication, and it
    supersedes the previous version atomically. Counsel cannot publish alone.
    """
    principal.require_role(Role.HEAD_OF_LEGAL, Role.ADMIN)
    principal.require_step_up("publish a library version")

    clause_version = db.execute(
        select(ClauseVersion).where(ClauseVersion.reference == reference)
    ).scalar_one_or_none()
    template_version = db.execute(
        select(TemplateVersion).where(TemplateVersion.reference == reference)
    ).scalar_one_or_none()

    version = clause_version or template_version
    if version is None:
        raise NotFound("That version was not found.")
    if version.status != VersionStatus.DRAFT.value:
        raise Conflict(f"{reference} is {version.status} and cannot be published again.")

    today = date.today()
    if version.supersedes_id:
        model = ClauseVersion if clause_version else TemplateVersion
        previous = db.get(model, version.supersedes_id)
        if previous:
            previous.status = VersionStatus.SUPERSEDED.value

    version.status = VersionStatus.APPROVED.value
    version.approved_by_id = uuid.UUID(principal.user_id)
    version.approval_date = today
    version.effective_date = version.effective_date or today

    audit.record(
        db,
        action="version_published",
        object_type="clause_version" if clause_version else "template_version",
        object_id=reference,
        actor_id=principal.user_id,
        actor_label=principal.name,
        after_state={"status": VersionStatus.APPROVED.value},
    )
    return Ack(
        message=(
            f"{reference} published. The previous version is superseded and remains "
            "readable."
        )
    )


@router.post("/versions/{reference}/reject")
def reject_version(reference: str, db: Db, principal: CurrentUser) -> Ack:
    principal.require_role(Role.HEAD_OF_LEGAL, Role.ADMIN)
    version = db.execute(
        select(ClauseVersion).where(ClauseVersion.reference == reference)
    ).scalar_one_or_none() or db.execute(
        select(TemplateVersion).where(TemplateVersion.reference == reference)
    ).scalar_one_or_none()
    if version is None:
        raise NotFound("That version was not found.")

    version.status = VersionStatus.WITHDRAWN.value
    audit.record(
        db,
        action="version_rejected",
        object_type="version",
        object_id=reference,
        actor_id=principal.user_id,
        actor_label=principal.name,
    )
    return Ack(message=f"{reference} withdrawn. The current version is unchanged.")


@router.get("/templates")
def list_templates(
    db: Db, principal: CurrentUser, entity: WorkingEntity
) -> list[TemplateOut]:
    principal.require_role(
        Role.LEGAL_OPS, Role.COUNSEL, Role.HEAD_OF_LEGAL, Role.PRIVACY, Role.ADMIN
    )
    out = []
    for template in db.execute(select(Template).order_by(Template.name)).scalars():
        if entity not in (template.entity_applicability or []):
            continue
        model = TemplateOut.model_validate(template)
        current = _current_template_version(template)
        model.current = TemplateVersionOut.model_validate(current) if current else None
        model.versions = [TemplateVersionOut.model_validate(v) for v in template.versions]
        out.append(model)
    return out


@router.get("/templates/{code}")
def get_template(code: str, db: Db, principal: CurrentUser) -> TemplateOut:
    principal.require_role(
        Role.LEGAL_OPS, Role.COUNSEL, Role.HEAD_OF_LEGAL, Role.PRIVACY, Role.ADMIN
    )
    template = db.execute(
        select(Template).where(Template.code == code)
    ).scalar_one_or_none()
    if template is None:
        raise NotFound("That template was not found.")

    model = TemplateOut.model_validate(template)
    current = _current_template_version(template)
    model.current = TemplateVersionOut.model_validate(current) if current else None
    model.versions = [TemplateVersionOut.model_validate(v) for v in template.versions]
    return model


@router.post("/templates/{code}/versions", response_model=TemplateVersionOut, status_code=201)
def propose_template_version(
    code: str, payload: VersionProposal, db: Db, principal: CurrentUser
) -> TemplateVersion:
    principal.require_role(Role.COUNSEL, Role.HEAD_OF_LEGAL, Role.ADMIN)
    template = db.execute(
        select(Template).where(Template.code == code)
    ).scalar_one_or_none()
    if template is None:
        raise NotFound("That template was not found.")

    open_drafts = [v for v in template.versions if v.status == VersionStatus.DRAFT.value]
    if open_drafts:
        raise Conflict(
            f"{open_drafts[0].reference} is already an open proposal. Concurrent "
            "proposals must be merged before publication."
        )

    current = _current_template_version(template)
    major = current.major if current else 1
    minor = (current.minor + 1) if current else 1

    version = TemplateVersion(
        template_id=template.id,
        reference=f"{template.code}-v{major}.{minor}",
        major=major,
        minor=minor,
        status=VersionStatus.DRAFT.value,
        body=payload.body if payload.body is not None else (current.body if current else []),
        variables=[v.model_dump() for v in (payload.variables or [])]
        or (current.variables if current else []),
        clause_references=current.clause_references if current else [],
        effective_date=payload.effective_date,
        review_date=payload.review_date,
        supersedes_id=current.id if current else None,
        change_summary=payload.change_summary,
    )
    db.add(version)
    db.flush()
    return version


@router.get("/library/review-due")
def review_due(db: Db, principal: CurrentUser, within_days: int = 30) -> list[dict]:
    """Owners are notified 30 days before a review date, and overdue reviews
    appear on the dashboard (LOP-M03-US-05)."""
    principal.require_role(Role.LEGAL_OPS, Role.COUNSEL, Role.HEAD_OF_LEGAL, Role.ADMIN)
    from datetime import timedelta

    horizon = date.today() + timedelta(days=within_days)
    due: list[dict] = []

    for version in db.execute(
        select(ClauseVersion).where(
            ClauseVersion.status == VersionStatus.APPROVED.value,
            ClauseVersion.review_date.is_not(None),
            ClauseVersion.review_date <= horizon,
        )
    ).scalars():
        due.append(
            {
                "reference": version.reference,
                "kind": "clause",
                "review_date": version.review_date,
                "overdue": version.review_date < date.today(),
            }
        )

    for version in db.execute(
        select(TemplateVersion).where(
            TemplateVersion.status == VersionStatus.APPROVED.value,
            TemplateVersion.review_date.is_not(None),
            TemplateVersion.review_date <= horizon,
        )
    ).scalars():
        due.append(
            {
                "reference": version.reference,
                "kind": "template",
                "review_date": version.review_date,
                "overdue": version.review_date < date.today(),
            }
        )

    return sorted(due, key=lambda row: row["review_date"])


@router.get("/playbooks/{agreement_type}")
def get_playbook(agreement_type: str, db: Db, principal: CurrentUser) -> dict:
    principal.require_role(Role.LEGAL_OPS, Role.COUNSEL, Role.HEAD_OF_LEGAL, Role.ADMIN)
    playbook = db.execute(
        select(Playbook).where(Playbook.agreement_type == agreement_type)
    ).scalar_one_or_none()
    if playbook is None:
        raise NotFound("No playbook is published for that agreement type.")
    return {
        "agreement_type": playbook.agreement_type,
        "name": playbook.name,
        "version": playbook.version,
        "required_clauses": playbook.required_clauses,
    }


@router.post("/template-imports", status_code=201)
def import_template(
    db: Db,
    principal: CurrentUser,
    entity: WorkingEntity,
    file: Annotated[UploadFile, File()],
    agreement_type: str | None = None,
) -> dict:
    """Import an existing Word template and propose a clause breakdown.

    The proposal is exactly that. Nothing here enters the library as house
    position: a clause owner accepts each candidate individually, and every
    accepted candidate lands as a draft version that still has to be published
    (LOP-M03-US-07).
    """
    principal.require_role(Role.HEAD_OF_LEGAL, Role.COUNSEL, Role.ADMIN)

    data = file.file.read()
    filename = file.filename or "template.docx"
    content_type = file.content_type or "application/octet-stream"
    digest = storage.validate_upload(filename, content_type, data)

    clean, scan_detail = storage.scan_upload(data)
    if not clean:
        raise ValidationFailed(
            "This file was refused and has been quarantined.", {"file": scan_detail}
        )

    try:
        candidates, provenance = docx_import.extract(data)
    except docx_import.NotADocx as exc:
        raise ValidationFailed(str(exc), {"file": str(exc)}) from exc

    key = f"imports/{entity}/{digest[:12]}-{filename}"
    storage.store.put(key, data, content_type)

    record = TemplateImport(
        filename=filename,
        entity=entity,
        agreement_type=agreement_type,
        storage_key=key,
        source_hash=digest,
        uploaded_by_id=uuid.UUID(principal.user_id),
        proposed_clauses=[candidate.as_dict() for candidate in candidates],
        provenance={**provenance, "filename": filename, "uploaded_by": principal.name},
    )
    db.add(record)
    db.flush()

    audit.record(
        db,
        action="template_imported",
        object_type="template_import",
        object_id=str(record.id),
        actor_id=principal.user_id,
        actor_label=principal.name,
        entity=entity,
        after_state={"filename": filename, "candidates": len(candidates)},
    )

    return {
        "import_id": str(record.id),
        "filename": filename,
        "candidate_count": len(candidates),
        "proposed_clauses": record.proposed_clauses,
        "provenance": record.provenance,
        "message": (
            f"{len(candidates)} candidate clauses were extracted from {filename}. "
            "None is approved. Accept the ones that reflect house position and they "
            "become draft versions for publication."
        ),
    }


@router.get("/template-imports")
def list_imports(db: Db, principal: CurrentUser, entity: WorkingEntity) -> list[dict]:
    principal.require_role(Role.HEAD_OF_LEGAL, Role.COUNSEL, Role.ADMIN)
    return [
        {
            "id": str(record.id),
            "filename": record.filename,
            "agreement_type": record.agreement_type,
            "status": record.status,
            "candidate_count": len(record.proposed_clauses or []),
            "accepted_count": record.accepted_count,
            "created_at": record.created_at,
        }
        for record in db.execute(
            select(TemplateImport)
            .where(TemplateImport.entity == entity)
            .order_by(TemplateImport.created_at.desc())
        ).scalars()
    ]


@router.get("/template-imports/{import_id}")
def get_import(import_id: uuid.UUID, db: Db, principal: CurrentUser) -> dict:
    """One import with its candidate clauses, so each can be decided on."""
    principal.require_role(Role.HEAD_OF_LEGAL, Role.COUNSEL, Role.ADMIN)
    record = db.get(TemplateImport, import_id)
    if record is None:
        raise NotFound("That import was not found.")
    return {
        "id": str(record.id),
        "filename": record.filename,
        "agreement_type": record.agreement_type,
        "status": record.status,
        "source_hash": record.source_hash,
        "accepted_count": record.accepted_count,
        "created_at": record.created_at,
        "candidates": record.proposed_clauses or [],
    }


def _clause_for_category(
    db, principal, record: TemplateImport, candidate: dict, category: str
) -> Clause:
    clause = db.execute(select(Clause).where(Clause.category == category)).scalar_one_or_none()
    if clause is not None:
        return clause

    clause = Clause(
        category=category,
        name=candidate.get("heading") or category,
        owner_id=uuid.UUID(principal.user_id),
        entity_applicability=[record.entity],
    )
    db.add(clause)
    db.flush()
    return clause


def _draft_from_candidate(
    db,
    principal,
    record: TemplateImport,
    candidate: dict,
    accepted: ImportCandidateAcceptance,
) -> ClauseVersion:
    """Create the draft version a single accepted candidate becomes.

    The provenance line names the file, the paragraph range and the source hash,
    so the imported text can always be traced back to the document it came from.
    """
    category = accepted.category or candidate.get("proposed_category")
    if not category:
        raise ValidationFailed(
            "A candidate needs a clause category before it can be accepted.",
            {"category": f"Candidate {accepted.index} has no category."},
        )

    clause = _clause_for_category(db, principal, record, candidate, category)
    major = max((v.major for v in clause.versions), default=0) + 1
    version = ClauseVersion(
        clause_id=clause.id,
        reference=f"CLS-{category}-v{major}.0",
        major=major,
        minor=0,
        status=VersionStatus.DRAFT.value,
        house_position=accepted.text or candidate.get("text", ""),
        provenance=(
            f"Imported from {record.filename}, paragraphs "
            f"{candidate.get('first_paragraph')} to {candidate.get('last_paragraph')}, "
            f"source hash {record.source_hash[:12]}."
        ),
    )
    db.add(version)
    candidate["decision"] = "accepted"
    candidate["created_version"] = version.reference
    return version


@router.post("/template-imports/{import_id}/accept")
def accept_import_candidates(
    import_id: uuid.UUID,
    payload: ImportAcceptance,
    db: Db,
    principal: CurrentUser,
) -> dict:
    """Turn accepted candidates into draft clause versions, never approved ones."""
    principal.require_role(Role.HEAD_OF_LEGAL, Role.ADMIN)

    record = db.get(TemplateImport, import_id)
    if record is None:
        raise NotFound("That import was not found.")

    candidates = list(record.proposed_clauses or [])
    created: list[str] = []

    for accepted in payload.accepted:
        if accepted.index >= len(candidates):
            raise ValidationFailed(
                "That candidate is not in this import.",
                {"index": f"The import holds {len(candidates)} candidates."},
            )
        version = _draft_from_candidate(
            db, principal, record, candidates[accepted.index], accepted
        )
        created.append(version.reference)

    rejected = set(payload.rejected)
    for index, candidate in enumerate(candidates):
        if candidate.get("decision") == "pending" and index in rejected:
            candidate["decision"] = "rejected"

    record.proposed_clauses = candidates
    record.accepted_count = sum(1 for c in candidates if c.get("decision") == "accepted")
    record.decided_by_id = uuid.UUID(principal.user_id)
    if all(c.get("decision") != "pending" for c in candidates):
        record.status = "decided"

    audit.record(
        db,
        action="template_import_decided",
        object_type="template_import",
        object_id=str(record.id),
        actor_id=principal.user_id,
        actor_label=principal.name,
        entity=record.entity,
        after_state={"created": created, "rejected": payload.rejected},
    )

    return {
        "created_versions": created,
        "message": (
            f"{len(created)} draft versions were created. Each is a draft until it is "
            "published, so nothing imported is house position yet."
        ),
    }
