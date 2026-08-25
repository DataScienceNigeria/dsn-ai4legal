"""Template and clause library, M03."""

from __future__ import annotations

import difflib
import re
import uuid
from datetime import UTC, date, datetime
from typing import Annotated

from fastapi import APIRouter, File, Form, Query, Response, UploadFile
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
    ClauseCreate,
    ClauseOut,
    ClauseVersionOut,
    ImportAcceptance,
    ImportCandidateAcceptance,
    TemplateOut,
    TemplatePlaceholder,
    TemplateVersionOut,
    VersionDiff,
    VersionDiffLine,
    VersionProposal,
)
from app.services import docx_import, memory, placeholders, storage
from app.services.generation import GeneratedBlock, GenerationResult, render_docx

router = APIRouter(tags=["library"])

TEMPLATE_NOT_FOUND = "That template was not found."
IMPORT_NOT_FOUND = "That import was not found."
DOCX_MEDIA_TYPE = "application/vnd.openxmlformats-officedocument.wordprocessingml.document"


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
def list_clauses(db: Db, principal: CurrentUser, entity: WorkingEntity) -> list[ClauseOut]:
    """A requester never sees the clause library (PRD section 5.2)."""
    principal.require_role(Role.COUNSEL, Role.HEAD_OF_LEGAL, Role.ADMIN)
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
    principal.require_role(Role.COUNSEL, Role.HEAD_OF_LEGAL, Role.ADMIN)
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


@router.post("/clauses", response_model=ClauseOut, status_code=201)
def create_clause(payload: ClauseCreate, db: Db, principal: CurrentUser) -> Clause:
    """A category the library does not hold yet, with its first draft.

    Proposing a version needs a clause to propose it against, so without this
    the library could only ever be revised, never extended. The first version
    is a draft like any other and still has to be published by someone with
    the authority to do it.
    """
    principal.require_role(Role.COUNSEL, Role.HEAD_OF_LEGAL, Role.ADMIN)

    category = payload.category.strip().upper()
    existing = db.execute(select(Clause).where(Clause.category == category)).scalar_one_or_none()
    if existing is not None:
        raise Conflict(
            f"{category} already exists as {existing.name}. Propose a version on it "
            "rather than creating it again."
        )

    clause = Clause(
        category=category,
        name=payload.name.strip(),
        owner_id=uuid.UUID(principal.user_id),
        entity_applicability=payload.entity_applicability,
        jurisdiction=payload.jurisdiction,
        required_for_types=payload.required_for_types,
    )
    db.add(clause)
    db.flush()

    version = ClauseVersion(
        clause_id=clause.id,
        reference=f"CLS-{category}-v1.0",
        major=1,
        minor=0,
        status=VersionStatus.DRAFT.value,
        house_position=payload.house_position,
        fallbacks=[f.model_dump() for f in payload.fallbacks],
        unacceptable_position=payload.unacceptable_position,
        effective_date=payload.effective_date,
        review_date=payload.review_date,
        provenance=payload.change_summary or "First version of a new clause.",
    )
    db.add(version)
    db.flush()

    audit.record(
        db,
        action="clause_created",
        object_type="clause",
        object_id=category,
        actor_id=principal.user_id,
        actor_label=principal.name,
        after_state={"name": clause.name, "first_version": version.reference},
    )
    return clause


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
    major = current.major if current else 1
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
    principal.require_role(Role.COUNSEL, Role.HEAD_OF_LEGAL, Role.ADMIN)
    versions = {
        v.reference: v
        for v in db.execute(
            select(ClauseVersion).where(ClauseVersion.reference.in_([from_reference, to_reference]))
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

    return VersionDiff(from_reference=from_reference, to_reference=to_reference, lines=lines)


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
            # The old position stays in memory and is marked. A question about
            # a position we used to hold has a real answer, and the reference
            # the model cites has to keep resolving; what it must not do is
            # present it as current.
            memory.supersede(db, "clause", previous.reference, reference)

    version.status = VersionStatus.APPROVED.value
    version.approved_by_id = uuid.UUID(principal.user_id)
    version.approval_date = today
    version.effective_date = version.effective_date or today

    if clause_version is not None:
        clause = db.get(Clause, clause_version.clause_id)
        entities = (clause.entity_applicability if clause else None) or ["EAI"]
        for entity in entities:
            memory.index_clause_version(
                db,
                clause_version,
                category=clause.category if clause else "Clause",
                entity=entity,
            )

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
        message=(f"{reference} published. The previous version is superseded and remains readable.")
    )


@router.post("/versions/{reference}/reject")
def reject_version(reference: str, db: Db, principal: CurrentUser) -> Ack:
    principal.require_role(Role.HEAD_OF_LEGAL, Role.ADMIN)
    version = (
        db.execute(
            select(ClauseVersion).where(ClauseVersion.reference == reference)
        ).scalar_one_or_none()
        or db.execute(
            select(TemplateVersion).where(TemplateVersion.reference == reference)
        ).scalar_one_or_none()
    )
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
def list_templates(db: Db, principal: CurrentUser, entity: WorkingEntity) -> list[TemplateOut]:
    principal.require_role(Role.COUNSEL, Role.HEAD_OF_LEGAL, Role.ADMIN)
    out = []
    for template in db.execute(select(Template).order_by(Template.name)).scalars():
        if entity not in (template.entity_applicability or []):
            continue
        model = TemplateOut.model_validate(template)
        current = _current_template_version(template)
        model.current = _template_version_out(current) if current else None
        model.versions = [_template_version_out(v) for v in template.versions]
        out.append(model)
    return out


@router.get("/templates/{code}")
def _template_version_out(version) -> TemplateVersionOut:
    """The version, with the blanks its body actually contains.

    Derived rather than stored. A template imported from Word declares no
    variables, so the interface had nothing to ask for and generation refused
    on blanks nobody was given the chance to fill.
    """
    model = TemplateVersionOut.model_validate(version)
    model.placeholders = [
        TemplatePlaceholder(**found) for found in placeholders.in_body(version.body or [])
    ]
    return model


def get_template(code: str, db: Db, principal: CurrentUser) -> TemplateOut:
    principal.require_role(Role.COUNSEL, Role.HEAD_OF_LEGAL, Role.ADMIN)
    template = db.execute(select(Template).where(Template.code == code)).scalar_one_or_none()
    if template is None:
        raise NotFound(TEMPLATE_NOT_FOUND)

    model = TemplateOut.model_validate(template)
    current = _current_template_version(template)
    model.current = _template_version_out(current) if current else None
    model.versions = [_template_version_out(v) for v in template.versions]
    return model


@router.post("/templates/import", status_code=201)
def import_agreement_template(
    db: Db,
    principal: CurrentUser,
    entity: WorkingEntity,
    file: Annotated[UploadFile, File()],
    name: Annotated[str, Form()],
    agreement_type: Annotated[str, Form()],
    code: Annotated[str | None, Form()] = None,
) -> dict:
    """Take a Word agreement and make it a template, as a draft.

    The document is kept as the document, so it can be read and edited as
    itself, and the same file is split into blocks so generation has something
    deterministic to assemble from. Both come out of one upload, because
    asking someone to supply the paper twice is asking them to let the two
    disagree.

    It lands as a draft. Publishing it is the existing, separately authorised
    step, so importing a file still cannot put anything into production.
    """
    principal.require_role(Role.HEAD_OF_LEGAL, Role.COUNSEL, Role.ADMIN)

    data = file.file.read()
    filename = file.filename or "template.docx"
    digest = storage.validate_upload(filename, DOCX_MEDIA_TYPE, data)

    clean, scan_detail = storage.scan_upload(data)
    if not clean:
        raise ValidationFailed(
            "This file was refused and has been quarantined.", {"file": scan_detail}
        )

    try:
        candidates, provenance = docx_import.extract(data)
    except docx_import.NotADocx as exc:
        raise ValidationFailed(str(exc), {"file": str(exc)}) from exc

    template_code = (code or _code_from(name)).strip().upper()
    existing = db.execute(
        select(Template).where(Template.code == template_code)
    ).scalar_one_or_none()
    if existing is not None:
        raise Conflict(
            f"{template_code} is already {existing.name}. Propose a new version on it "
            "rather than importing it again as a second template."
        )

    key = f"templates/{entity}/{digest[:12]}-{filename}"
    storage.store.put(key, data, DOCX_MEDIA_TYPE)

    # The import record carries the provenance and the clause candidates, so
    # extracting clauses into the library stays available from the template.
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

    template = Template(
        code=template_code,
        name=name.strip(),
        agreement_type=agreement_type.strip(),
        owner_id=uuid.UUID(principal.user_id),
    )
    db.add(template)
    db.flush()

    version = TemplateVersion(
        template_id=template.id,
        reference=f"{template_code}-v1.0",
        major=1,
        minor=0,
        status=VersionStatus.DRAFT.value,
        body=[_block_from(candidate) for candidate in candidates],
        variables=_variables_in(candidates),
        clause_references=[],
        change_summary=f"Imported from {filename}.",
        provenance=f"Imported from {filename}, {len(candidates)} blocks.",
        source_key=key,
        source_hash=digest,
        import_id=record.id,
    )
    db.add(version)
    db.flush()

    audit.record(
        db,
        action="template_imported",
        object_type="template",
        object_id=template_code,
        actor_id=principal.user_id,
        actor_label=principal.name,
        entity=entity,
        after_state={"filename": filename, "blocks": len(candidates), "version": version.reference},
    )
    return {
        "code": template.code,
        "name": template.name,
        "version": version.reference,
        "blocks": len(candidates),
        "message": (
            f"{template.name} is a draft at {version.reference}. Read it, change it, and "
            "publish it when it is right. Nothing generates from a draft."
        ),
    }


def _code_from(name: str) -> str:
    """A template code from its name, when the caller does not supply one."""
    words = [word for word in re.split(r"[^A-Za-z0-9]+", name) if word]
    stem = "-".join(word[:4].upper() for word in words[:3]) or "TPL"
    return f"TPL-{stem}"[:32]


def _block_from(candidate) -> dict:
    return {
        "key": (candidate.heading or candidate.number or "block").lower().replace(" ", "_")[:40],
        "number": candidate.number,
        "heading": candidate.heading,
        "text": candidate.text,
    }


def _variables_in(candidates) -> list[dict]:
    """Merge variables the imported paper already declares as {{tokens}}."""
    found: dict[str, dict] = {}
    for candidate in candidates:
        for token in re.findall(r"\{\{\s*([a-z0-9_]+)\s*\}\}", candidate.text or "", re.I):
            key = token.lower()
            found.setdefault(
                key, {"name": key, "label": key.replace("_", " ").capitalize(), "mandatory": True}
            )
    return list(found.values())


@router.get("/templates/{code}/preview")
def preview_template(
    code: str, db: Db, principal: CurrentUser, version: str | None = None
) -> Response:
    """The template as the document it produces, in Word.

    A version is proposed against a template, so the template has to be
    readable before anyone can sensibly propose anything. Merge variables are
    left as their tokens rather than filled with sample values, because a
    preview that invents a counterparty is a different document from the one
    the template describes. Clause blocks are resolved to the text of the
    clause version the template pins, so what is read is what would issue.
    """
    principal.require_role(Role.COUNSEL, Role.HEAD_OF_LEGAL, Role.ADMIN)
    template = db.execute(select(Template).where(Template.code == code)).scalar_one_or_none()
    if template is None:
        raise NotFound(TEMPLATE_NOT_FOUND)

    if version:
        chosen = next((v for v in template.versions if v.reference == version), None)
        if chosen is None:
            raise NotFound(f"{version} is not a version of this template.")
    else:
        chosen = _current_template_version(template) or next(iter(template.versions), None)
    if chosen is None:
        raise NotFound("That template has no version to read yet.")

    if chosen.source_key:
        # Imported paper is served as the paper. Rendering it back out of the
        # blocks would return a tidied approximation of a document the reader
        # is trying to check.
        try:
            return Response(
                content=storage.store.get(chosen.source_key),
                media_type=DOCX_MEDIA_TYPE,
                headers={
                    "Content-Disposition": f'inline; filename="{template.code}.docx"',
                    "X-Template-Version": chosen.reference,
                },
            )
        except FileNotFoundError:
            pass

    blocks = [_preview_block(db, entry) for entry in (chosen.body or [])]
    result = GenerationResult(
        blocks=blocks,
        values={},
        checks=[],
        content_hash="",
        template_reference=chosen.reference,
        clause_references=list(chosen.clause_references or []),
    )
    title = f"{template.name} ({chosen.reference})"
    return Response(
        content=render_docx(result, title),
        media_type=DOCX_MEDIA_TYPE,
        headers={
            "Content-Disposition": f'inline; filename="{template.code}-{chosen.reference}.docx"',
            "X-Template-Version": chosen.reference,
        },
    )


def _preview_block(db, entry: dict) -> GeneratedBlock:
    """One block of the preview, with a pinned clause resolved to its text."""
    reference = entry.get("clause")
    text = entry.get("text", "")
    provenance = "template_text"

    if reference:
        pinned = db.execute(
            select(ClauseVersion).where(ClauseVersion.reference == reference)
        ).scalar_one_or_none()
        if pinned is None:
            text = (
                f"[{reference} is pinned here but is not in the library. "
                "Generation would refuse rather than emit this.]"
            )
            provenance = "missing_clause"
        else:
            text = pinned.house_position
            provenance = "approved_clause"

    condition = entry.get("condition")
    if condition:
        text = f"[Included only when {condition}.] {text}"

    return GeneratedBlock(
        key=entry.get("key", ""),
        number=str(entry.get("number", "")),
        heading=entry.get("heading", ""),
        text=text,
        provenance=provenance,
        source_reference=reference,
    )


@router.put("/templates/{code}/source")
def save_template_source(
    code: str,
    db: Db,
    principal: CurrentUser,
    file: Annotated[UploadFile, File()],
) -> dict:
    """Save an edit to the template's open draft.

    Only a draft. An approved version is what documents were generated from
    and what approvals were bound to, so editing one in place would change the
    past. Propose a new version instead, which is the path that exists.
    """
    principal.require_role(Role.COUNSEL, Role.HEAD_OF_LEGAL, Role.ADMIN)
    template = db.execute(select(Template).where(Template.code == code)).scalar_one_or_none()
    if template is None:
        raise NotFound(TEMPLATE_NOT_FOUND)

    draft = next(
        (v for v in template.versions if v.status == VersionStatus.DRAFT.value), None
    )
    if draft is None:
        raise Conflict(
            "This template has no open draft. Propose a change first, which creates one, "
            "and edit that."
        )

    data = file.file.read()
    digest = storage.validate_upload(f"{code}.docx", DOCX_MEDIA_TYPE, data)
    if digest == draft.source_hash:
        return {"revision": draft.reference, "saved": False, "message": "Nothing changed."}

    clean, scan_detail = storage.scan_upload(data)
    if not clean:
        raise ValidationFailed(
            "That version was refused and has not been saved.", {"file": scan_detail}
        )

    draft.source_key = f"templates/{template.code}/{draft.reference}-{digest[:12]}.docx"
    draft.source_hash = digest
    storage.store.put(draft.source_key, data, DOCX_MEDIA_TYPE)

    audit.record(
        db,
        action="template_draft_edited",
        object_type="template",
        object_id=template.code,
        actor_id=principal.user_id,
        actor_label=principal.name,
        after_state={"version": draft.reference, "hash": digest},
    )
    return {
        "revision": draft.reference,
        "saved": True,
        "saved_at": datetime.now(UTC).isoformat(),
    }


@router.post("/templates/{code}/versions", response_model=TemplateVersionOut, status_code=201)
def propose_template_version(
    code: str, payload: VersionProposal, db: Db, principal: CurrentUser
) -> TemplateVersion:
    principal.require_role(Role.COUNSEL, Role.HEAD_OF_LEGAL, Role.ADMIN)
    template = db.execute(select(Template).where(Template.code == code)).scalar_one_or_none()
    if template is None:
        raise NotFound(TEMPLATE_NOT_FOUND)

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
        # The draft starts as a copy of the document in force, so editing a
        # proposal begins from what is actually in use rather than from blank.
        source_key=current.source_key if current else None,
        source_hash=current.source_hash if current else None,
        import_id=current.import_id if current else None,
    )
    db.add(version)
    db.flush()
    return version


@router.get("/library/review-due")
def review_due(db: Db, principal: CurrentUser, within_days: int = 30) -> list[dict]:
    """Owners are notified 30 days before a review date, and overdue reviews
    appear on the dashboard (LOP-M03-US-05)."""
    principal.require_role(Role.COUNSEL, Role.HEAD_OF_LEGAL, Role.ADMIN)
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
    principal.require_role(Role.COUNSEL, Role.HEAD_OF_LEGAL, Role.ADMIN)
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


@router.get("/template-imports/{import_id}")
def get_import(import_id: uuid.UUID, db: Db, principal: CurrentUser) -> dict:
    """One import with its candidate clauses, so each can be decided on."""
    principal.require_role(Role.HEAD_OF_LEGAL, Role.COUNSEL, Role.ADMIN)
    record = db.get(TemplateImport, import_id)
    if record is None:
        raise NotFound(IMPORT_NOT_FOUND)
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
        raise NotFound(IMPORT_NOT_FOUND)

    candidates = list(record.proposed_clauses or [])
    created: list[str] = []

    for accepted in payload.accepted:
        if accepted.index >= len(candidates):
            raise ValidationFailed(
                "That candidate is not in this import.",
                {"index": f"The import holds {len(candidates)} candidates."},
            )
        version = _draft_from_candidate(db, principal, record, candidates[accepted.index], accepted)
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
