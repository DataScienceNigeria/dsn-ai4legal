"""The legal team's playbook and clause library workbook, M03.

Uploading checks the workbook and records what it would do. Applying writes
drafts. Publishing a playbook is the separate, authorised step that makes any
of it house position.
"""

from __future__ import annotations

import uuid
from datetime import date
from typing import Annotated

from fastapi import APIRouter, File, Response, UploadFile
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError

from app.core import audit
from app.core.deps import CurrentUser, Db
from app.core.errors import Conflict, NotFound, Refused, ValidationFailed
from app.db.models.library import LibraryImport
from app.db.models.organisation import User
from app.domain.enums import Role
from app.services import library_workbook, memory, storage

router = APIRouter(tags=["library"])

IMPORT_NOT_FOUND = "That workbook import was not found."
ISSUE_LIMIT = 2000


def _rows(count: int, one: str, many: str) -> str:
    return f"{count} {one if count == 1 else many}"


class ApplyRequest(BaseModel):
    exclude_errors: bool = False
    playbook: str | None = Field(default=None, max_length=300)


def _import_out(db, record: LibraryImport, detail: bool = True) -> dict:
    issues = record.issues or []
    errors = sum(1 for issue in issues if issue["level"] == "error")
    summary = {k: v for k, v in (record.summary or {}).items() if k != "outcomes"}
    uploaded_by = db.get(User, record.uploaded_by_id) if record.uploaded_by_id else None
    applied_by = db.get(User, record.applied_by_id) if record.applied_by_id else None
    out = {
        "id": str(record.id),
        "filename": record.filename,
        "status": record.status,
        "source_hash": record.source_hash,
        "created_at": record.created_at,
        "uploaded_by": uploaded_by.name if uploaded_by else None,
        "applied_at": record.applied_at,
        "applied_by": applied_by.name if applied_by else None,
        "errors": errors,
        "warnings": len(issues) - errors,
        "excluded_rows": len(library_workbook.excluded_rows(issues)),
        "structural": library_workbook.structural(issues),
        "summary": summary,
        "can_apply": record.status == "checked" and not library_workbook.structural(issues),
        "playbooks": [
            {
                "key": library_workbook.playbook_key(p),
                "name": p["name"],
                "clauses": len(p["required_clauses"]),
            }
            for p in (record.plan or {}).get("playbooks", [])
        ],
    }
    if detail:
        out["issues"] = issues
    return out


@router.post("/library/imports", status_code=201)
def check_workbook(
    db: Db,
    principal: CurrentUser,
    file: Annotated[UploadFile, File()],
) -> dict:
    """Check the workbook and record what it would do. Nothing else is written."""
    principal.require_role(Role.COUNSEL, Role.HEAD_OF_LEGAL, Role.ADMIN)

    data = file.file.read()
    filename = storage.sanitize_filename(file.filename, "library.xlsx")
    if not filename.lower().endswith(".xlsx"):
        raise ValidationFailed(
            "This file cannot be accepted.",
            {"file": "Upload the workbook as an Excel .xlsx file."},
        )
    if not data:
        raise ValidationFailed("This file cannot be accepted.", {"file": "The file is empty."})
    digest = storage.validate_upload(filename, library_workbook.XLSX_MEDIA_TYPE, data)

    clean, scan_detail = storage.scan_upload(data)
    if not clean:
        raise ValidationFailed(
            "This file was refused and has been quarantined.", {"file": scan_detail}
        )

    try:
        checked = library_workbook.check(data)
    except library_workbook.NotAWorkbook as exc:
        raise ValidationFailed(str(exc), {"file": str(exc)}) from exc

    summary, found = library_workbook.compare(db, checked.plan)
    issues = [issue.as_dict() for issue in [*checked.issues, *found]][:ISSUE_LIMIT]

    key = storage.upload_key("library-imports", filename)
    storage.store.put(key, data, library_workbook.XLSX_MEDIA_TYPE)

    record = LibraryImport(
        filename=filename,
        storage_key=key,
        source_hash=digest,
        uploaded_by_id=uuid.UUID(principal.user_id),
        status="checked",
        summary=summary,
        issues=issues,
        plan=checked.plan,
    )
    db.add(record)
    db.flush()

    audit.record(
        db,
        action="library_workbook_checked",
        object_type="library_import",
        object_id=str(record.id),
        actor_id=principal.user_id,
        actor_label=principal.name,
        after_state={
            "filename": filename,
            "hash": digest,
            "errors": sum(1 for i in issues if i["level"] == "error"),
            "warnings": sum(1 for i in issues if i["level"] == "warning"),
        },
    )
    out = _import_out(db, record)
    db.commit()
    return out


@router.get("/library/imports")
def list_imports(db: Db, principal: CurrentUser, limit: int = 20) -> list[dict]:
    principal.require_role(Role.COUNSEL, Role.HEAD_OF_LEGAL, Role.ADMIN)
    limit = max(1, min(limit, 100))
    return [
        _import_out(db, record, detail=False)
        for record in db.execute(
            select(LibraryImport).order_by(LibraryImport.created_at.desc()).limit(limit)
        ).scalars()
    ]


@router.get("/library/imports/{import_id}")
def get_import(import_id: uuid.UUID, db: Db, principal: CurrentUser) -> dict:
    principal.require_role(Role.COUNSEL, Role.HEAD_OF_LEGAL, Role.ADMIN)
    record = db.get(LibraryImport, import_id)
    if record is None:
        raise NotFound(IMPORT_NOT_FOUND)
    return _import_out(db, record)


@router.post("/library/imports/{import_id}/apply")
def apply_workbook(
    import_id: uuid.UUID,
    db: Db,
    principal: CurrentUser,
    payload: ApplyRequest | None = None,
) -> dict:
    """Write a checked workbook into the library as drafts.

    Rows with errors are left out and stay listed against the check, but only
    when the person applying says so: loading part of a workbook is a choice,
    never a surprise. A pilot loads one playbook and what it needs.

    The comparison is run again first, because the library may have moved
    since the check: a draft somebody opened in the meantime is theirs, and
    the workbook does not write over it.
    """
    principal.require_role(Role.HEAD_OF_LEGAL, Role.ADMIN)
    payload = payload or ApplyRequest()

    record = db.get(LibraryImport, import_id, with_for_update=True)
    if record is None:
        raise NotFound(IMPORT_NOT_FOUND)
    if record.status != "checked":
        raise Conflict(f"This workbook was already {record.status}. Upload it again to re-check.")
    issues = record.issues or []
    if library_workbook.structural(issues):
        raise Refused(
            "This workbook cannot be read as it is, so nothing was written.",
            [i["message"] for i in issues if i["level"] == "error" and i["row"] is None],
        )
    excluded = library_workbook.excluded_rows(issues)
    if excluded and not payload.exclude_errors:
        raise Refused(
            f"{_rows(len(excluded), 'row has', 'rows have')} errors, so nothing was written.",
            [
                "Correct them and upload the workbook again, or confirm that the valid rows "
                "load and those rows are left out."
            ],
        )

    plan = record.plan
    if payload.playbook:
        plan = library_workbook.only_playbook(record.plan, payload.playbook)
        if plan is None:
            raise ValidationFailed(
                "That playbook is not in this workbook.",
                {"playbook": "Choose one of the playbooks this check found."},
            )

    summary, found = library_workbook.compare(db, plan)
    known = {(i["sheet"], i["row"], i["message"]) for i in issues}
    new = [i for i in found if (i.sheet, i.row, i.message) not in known]
    if new:
        raise Refused(
            "The library changed since this workbook was checked, so nothing was written.",
            [issue.message for issue in new][:20],
        )

    try:
        result = library_workbook.apply(
            db, record, plan, summary.get("outcomes", {}), uuid.UUID(principal.user_id)
        )
        memory.index_precedents(db, result["precedents"])
        db.flush()
    except IntegrityError as exc:
        raise Conflict(
            "Another workbook was applied at the same moment. Upload this one again to "
            "check it against the library as it now is."
        ) from exc
    record.summary = {**summary, "pilot": payload.playbook, "rows_left_out": len(excluded)}
    if payload.playbook:
        record.status = "piloted"

    audit.record(
        db,
        action="library_workbook_applied",
        object_type="library_import",
        object_id=str(record.id),
        actor_id=principal.user_id,
        actor_label=principal.name,
        after_state={
            "filename": record.filename,
            "playbook": payload.playbook,
            "rows_left_out": [f"{sheet} row {row}" for sheet, row in excluded],
            **result["written"],
        },
    )
    out = _import_out(db, record)
    out["written"] = result["written"]
    scope = plan["playbooks"][0]["name"] if payload.playbook else "The workbook"
    left_out = (
        f" {_rows(len(excluded), 'row', 'rows')} with errors left out, listed against this check."
        if excluded
        else ""
    )
    out["message"] = (
        f"{scope} is in the library as drafts.{left_out} Nothing is house position until "
        "the Head of Legal publishes each playbook."
    )
    db.commit()
    return out


@router.get("/library/export")
def export_workbook(db: Db, principal: CurrentUser) -> Response:
    """The library as the legal team's workbook, to edit and upload again."""
    principal.require_role(Role.COUNSEL, Role.HEAD_OF_LEGAL, Role.ADMIN)
    data = library_workbook.export(db)
    audit.record(
        db,
        action="library_workbook_exported",
        object_type="library",
        object_id="workbook",
        actor_id=principal.user_id,
        actor_label=principal.name,
    )
    filename = f"Legal Playbook and Clause Library {date.today().isoformat()}.xlsx"
    return Response(
        content=data,
        media_type=library_workbook.XLSX_MEDIA_TYPE,
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )
