"""Document generation and review, M04 and M06."""

from __future__ import annotations

import uuid
from datetime import UTC, date, datetime
from typing import Annotated

from fastapi import APIRouter, File, Response, UploadFile
from sqlalchemy import select, text

from app.core import audit
from app.core.deps import CurrentUser, Db, WorkingEntity
from app.core.errors import Conflict, Forbidden, NotFound, Refused, ValidationFailed
from app.db.models.contract import Approval, SignatureRequest
from app.db.models.counterparty import Counterparty
from app.db.models.document import Document, ReviewFinding, Suggestion
from app.db.models.intake import Attachment, RequestType
from app.db.models.library import ClauseVersion, Template, TemplateVersion
from app.db.models.matter import Matter
from app.db.models.organisation import Organisation
from app.db.models.platform import QualitySample
from app.domain.enums import (
    AUTHORITY_MATRIX,
    ApprovalDecision,
    AuthorityLevel,
    DocumentType,
    MatterState,
    RiskTier,
    Role,
    Severity,
    VersionStatus,
)
from app.schemas.common import Ack
from app.schemas.matters import (
    AutoIssueRequest,
    DocumentOut,
    FindingDecision,
    FindingOut,
    GenerateRequest,
)
from app.services import approvals as approval_service
from app.services import autoissue, docx_import, storage
from app.services.generation import generate, render_docx
from app.services.hashing import file_hash

DOCUMENT_NOT_FOUND = "That document was not found."

DOCX_MEDIA_TYPE = "application/vnd.openxmlformats-officedocument.wordprocessingml.document"

router = APIRouter(tags=["documents"])


def _clause_texts(db, references: list[str]) -> dict[str, dict]:
    """Only an approved, effective clause version may be merged."""
    today = date.today()
    out: dict[str, dict] = {}
    for version in db.execute(
        select(ClauseVersion).where(ClauseVersion.reference.in_(references))
    ).scalars():
        if version.status != VersionStatus.APPROVED.value:
            continue
        if version.effective_date and version.effective_date > today:
            continue
        out[version.reference] = {
            "text": version.house_position,
            "provenance": "approved_clause",
        }
    return out


def _first_address(addresses: list[dict] | None) -> str | None:
    """The counterparty's address as one line.

    A counterparty holds several addresses over time. The registered one is
    what an agreement names, and where none is marked, the first recorded is
    the best the record offers.
    """
    entries = addresses or []
    if not entries:
        return None
    chosen = next((a for a in entries if a.get("type") == "registered"), entries[0])
    if chosen.get("full"):
        return str(chosen["full"])
    parts = [
        chosen.get(field)
        for field in ("line1", "line2", "city", "state", "postcode", "country")
    ]
    joined = ", ".join(str(p).strip() for p in parts if p)
    return joined or None


COUNTERPARTY_DISCLAIMER = (
    "Counterparty paper. Nothing in this document came from an approved clause, "
    "so it is never presented as house position and cannot be approved or signed "
    "from here."
)


def _store_counterparty_paper(
    db,
    principal,
    matter: Matter,
    *,
    filename: str,
    content_type: str,
    data: bytes,
    source: str,
) -> Document:
    """Turn their file into a document the review can walk.

    The split into blocks is the same deterministic heading and numbering split
    a template import uses, so what a reviewer reads on screen is what the
    comparison was given. Every block is marked ``counterparty``, which is what
    keeps it out of everything a generated document is eligible for.
    """
    try:
        blocks = docx_import.read_blocks(data)
    except docx_import.NotADocx as exc:
        # The comparison walks the paper clause by clause, so it needs the
        # document structure and not an image of it. A PDF is the usual case
        # here, and saying so is more use than repeating that it failed.
        hint = (
            "Counterparty paper has to be a Word file, because the review reads it "
            "clause by clause. Ask them for the .docx, or save the PDF as one."
            if filename.lower().endswith(".pdf")
            else str(exc)
        )
        raise ValidationFailed("That paper could not be read.", {"file": hint}) from exc

    if not blocks:
        raise ValidationFailed(
            "That paper could not be read.",
            {"file": "No clauses could be found in it, so there is nothing to compare."},
        )

    digest = file_hash(data)
    existing = db.execute(
        select(Document).where(
            Document.matter_id == matter.id, Document.content_hash == digest
        )
    ).scalars().first()
    if existing is not None:
        return existing

    key = f"matters/{matter.number}/counterparty/{digest[:12]}-{filename}"
    storage.store.put(key, data, content_type)

    previous = list(
        db.execute(select(Document).where(Document.matter_id == matter.id)).scalars()
    )

    document = Document(
        matter_id=matter.id,
        entity=matter.entity,
        name=filename,
        document_type=DocumentType.COUNTERPARTY.value,
        version=len(previous) + 1,
        template_version_ref=None,
        clause_versions=[],
        input_values={},
        blocks=blocks,
        content_hash=digest,
        storage_key=key,
        classification=matter.classification,
        generated_by_id=uuid.UUID(principal.user_id),
        generated_at=datetime.now(UTC),
        novel_clause_count=0,
        open_items=[COUNTERPARTY_DISCLAIMER],
        consistency_checks=[],
    )
    db.add(document)
    db.flush()

    audit.record(
        db,
        action="counterparty_paper_added",
        object_type="document",
        object_id=str(document.id),
        actor_id=principal.user_id,
        actor_label=principal.name,
        entity=matter.entity,
        after_state={
            "matter": matter.number,
            "filename": filename,
            "hash": digest,
            "clauses": len(blocks),
            "source": source,
        },
    )
    return document


@router.post("/matters/{matter_id}/paper", status_code=201)
def add_counterparty_paper(
    matter_id: uuid.UUID,
    db: Db,
    principal: CurrentUser,
    file: Annotated[UploadFile, File()],
) -> DocumentOut:
    """Upload their draft so it can be measured against the playbook.

    Scanned before it is stored, like every other upload. A file that fails the
    scan is quarantined and the refusal is recorded, because a document that
    arrived from outside is exactly where a hostile payload would be.
    """
    principal.require_role(Role.LEGAL_OPS, Role.COUNSEL, Role.HEAD_OF_LEGAL, Role.ADMIN)

    matter = db.get(Matter, matter_id)
    if matter is None:
        raise NotFound("That matter was not found.")

    data = file.file.read()
    content_type = file.content_type or DOCX_MEDIA_TYPE
    storage.validate_upload(file.filename or "", content_type, data)

    clean, scan_detail = storage.scan_upload(data)
    if not clean:
        audit.record(
            db,
            action="upload_quarantined",
            object_type="matter",
            object_id=matter.number,
            actor_id=principal.user_id,
            actor_label=principal.name,
            entity=matter.entity,
            result="failure",
            detail=scan_detail,
        )
        raise ValidationFailed(
            "This file was refused and has been quarantined.", {"file": scan_detail}
        )

    document = _store_counterparty_paper(
        db,
        principal,
        matter,
        filename=file.filename or "counterparty-paper.docx",
        content_type=content_type,
        data=data,
        source="upload",
    )
    return _to_out(document)


@router.post("/matters/{matter_id}/paper/from-attachment/{attachment_id}", status_code=201)
def adopt_attachment_as_paper(
    matter_id: uuid.UUID, attachment_id: uuid.UUID, db: Db, principal: CurrentUser
) -> DocumentOut:
    """Take paper that arrived with the request and make it reviewable.

    Most counterparty drafts arrive attached to the request rather than by
    email afterwards, and an attachment is stored evidence rather than a
    document the review can walk. This copies it across without re-uploading,
    so the reviewer is looking at the bytes the requester actually sent. The
    attachment stays where it is: it is the record of what arrived.
    """
    principal.require_role(Role.LEGAL_OPS, Role.COUNSEL, Role.HEAD_OF_LEGAL, Role.ADMIN)

    matter = db.get(Matter, matter_id)
    if matter is None:
        raise NotFound("That matter was not found.")

    attachment = db.get(Attachment, attachment_id)
    if attachment is None or attachment.request_id != matter.request_id:
        raise NotFound("That attachment is not on the request this matter came from.")

    if attachment.scan_status != "clean":
        raise Refused(
            "That attachment cannot be used as paper.",
            [f"It is recorded as {attachment.scan_status} rather than clean."],
        )

    try:
        data = storage.store.get(attachment.storage_key)
    except Exception as exc:
        # Broad on purpose. The object store raises its own error type and the
        # local fallback raises OSError, and either way the answer to the
        # caller is the same: the row says there is a file and there is not.
        raise NotFound(
            "The stored file behind that attachment could not be read."
        ) from exc

    document = _store_counterparty_paper(
        db,
        principal,
        matter,
        filename=attachment.filename,
        content_type=attachment.content_type,
        data=data,
        source=f"attachment {attachment.id}",
    )
    return _to_out(document)


@router.post("/documents/generate", status_code=201)
def generate_document(
    payload: GenerateRequest, db: Db, principal: CurrentUser
) -> DocumentOut:
    """Deterministic assembly from an approved template version.

    Nothing generative happens here, which is what makes tier 1 auto-issue
    defensible.
    """
    principal.require_role(Role.LEGAL_OPS, Role.COUNSEL, Role.HEAD_OF_LEGAL, Role.ADMIN)

    matter = db.get(Matter, payload.matter_id)
    if matter is None:
        raise NotFound("That matter was not found.")

    version = db.execute(
        select(TemplateVersion).where(TemplateVersion.reference == payload.template_reference)
    ).scalar_one_or_none()
    if version is None:
        raise NotFound("That template version was not found.")

    refusals: list[str] = []
    if version.status != VersionStatus.APPROVED.value:
        refusals.append(
            f"{version.reference} is {version.status}. Only an approved version may generate."
        )
    if version.effective_date and version.effective_date > date.today():
        refusals.append(
            f"{version.reference} does not take effect until {version.effective_date}."
        )

    template = db.get(Template, version.template_id)
    if template and matter.entity not in (template.entity_applicability or []):
        refusals.append(
            f"{template.code} does not apply to {matter.entity}."
        )

    counterparty = (
        db.get(Counterparty, matter.counterparty_id) if matter.counterparty_id else None
    )
    if counterparty is None:
        refusals.append("The counterparty record on this matter is incomplete.")

    if refusals:
        raise Refused("This document cannot be generated.", refusals)

    organisation = db.execute(
        select(Organisation).where(Organisation.entity_code == matter.entity)
    ).scalar_one_or_none()

    facts = {
        "matter_number": matter.number,
        "our_entity": organisation.legal_name if organisation else matter.entity,
        "our_trading_name": organisation.trading_name if organisation else None,
        "our_address": organisation.registered_address if organisation else None,
        "our_registration_number": organisation.registration_number if organisation else None,
        "our_tax_identification_number": (
            organisation.tax_identification_number if organisation else None
        ),
        "our_signatory": organisation.signatory_name if organisation else None,
        "our_signatory_title": organisation.signatory_title if organisation else None,
        "counterparty": counterparty.legal_name,
        "counterparty_jurisdiction": counterparty.jurisdiction,
        "counterparty_address": _first_address(counterparty.addresses),
        "counterparty_registration_number": counterparty.registration_number,
        "effective_date": date.today().isoformat(),
        "governing_law": organisation.default_jurisdiction if organisation else "Nigeria",
        "value_amount": float(matter.value_amount) if matter.value_amount else None,
        "value_currency": matter.value_currency,
        "privacy_flag": matter.privacy_flag,
        **payload.facts,
    }

    result = generate(
        template_reference=version.reference,
        body=version.body,
        declared_variables=version.variables,
        facts=facts,
        clause_texts=_clause_texts(db, version.clause_references or []),
        expected_parties=[facts["our_entity"], counterparty.legal_name],
    )

    # Generation is deterministic, so two callers asking for the same document
    # produce the same hash. Without this lock both pass the check below and
    # both insert, which a load test at eight concurrent callers reproduced
    # every time. The lock is transaction-scoped and released on commit.
    db.execute(
        text("SELECT pg_advisory_xact_lock(hashtextextended(:key, 0))"),
        {"key": f"generate:{matter.id}:{result.content_hash}"},
    )

    existing = db.execute(
        select(Document)
        .where(
            Document.matter_id == matter.id, Document.content_hash == result.content_hash
        )
        .order_by(Document.created_at)
    ).scalars().first()
    if existing is not None:
        return _to_out(existing)

    previous = list(
        db.execute(select(Document).where(Document.matter_id == matter.id)).scalars()
    )

    document = Document(
        matter_id=matter.id,
        entity=matter.entity,
        name=payload.name or f"{template.name if template else version.reference}, {matter.number}",
        document_type=DocumentType.DRAFT.value,
        version=len(previous) + 1,
        template_version_ref=version.reference,
        clause_versions=result.clause_references,
        input_values=result.values,
        blocks=[
            {
                "key": b.key,
                "number": b.number,
                "heading": b.heading,
                "text": b.text,
                "provenance": b.provenance,
                "source_reference": b.source_reference,
                "novel": b.novel,
            }
            for b in result.blocks
        ],
        content_hash=result.content_hash,
        classification=matter.classification,
        generated_by_id=uuid.UUID(principal.user_id),
        generated_at=datetime.now(UTC),
        novel_clause_count=result.novel_count,
        open_items=result.open_items,
        consistency_checks=[c.as_dict() for c in result.checks],
    )
    db.add(document)
    db.flush()

    if previous:
        latest = max(previous, key=lambda d: d.version)
        invalidated = approval_service.invalidate_for_hash(
            db,
            matter.id,
            latest.content_hash,
            f"A new document version {document.version} was generated.",
        )
        if invalidated:
            audit.record(
                db,
                action="approvals_invalidated",
                object_type="matter",
                object_id=matter.number,
                actor_id=principal.user_id,
                actor_label=principal.name,
                entity=matter.entity,
                detail=f"{len(invalidated)} approvals invalidated by a document edit.",
            )

    audit.record(
        db,
        action="document_generated",
        object_type="document",
        object_id=str(document.id),
        actor_id=principal.user_id,
        actor_label=principal.name,
        entity=matter.entity,
        after_state={
            "hash": document.content_hash,
            "template": version.reference,
            "clauses": result.clause_references,
        },
    )
    return _to_out(document)


def _to_out(document: Document) -> DocumentOut:
    return DocumentOut.model_validate(document)


@router.get("/documents/{document_id}")
def get_document(document_id: uuid.UUID, db: Db, principal: CurrentUser) -> DocumentOut:
    document = db.get(Document, document_id)
    if document is None:
        raise NotFound(DOCUMENT_NOT_FOUND)
    return _to_out(document)


@router.get("/documents/{document_id}/hash")
def get_hash(document_id: uuid.UUID, db: Db, principal: CurrentUser) -> dict:
    document = db.get(Document, document_id)
    if document is None:
        raise NotFound(DOCUMENT_NOT_FOUND)
    return {
        "document_id": str(document.id),
        "content_hash": document.content_hash,
        "template_version": document.template_version_ref,
        "clause_versions": document.clause_versions,
        "immutable": document.immutable,
    }


@router.get("/documents/{document_id}/download")
def download(document_id: uuid.UUID, db: Db, principal: CurrentUser) -> Response:
    document = db.get(Document, document_id)
    if document is None:
        raise NotFound(DOCUMENT_NOT_FOUND)

    from app.services.generation import GeneratedBlock, GenerationResult

    result = GenerationResult(
        blocks=[
            GeneratedBlock(
                key=b["key"],
                number=b["number"],
                heading=b["heading"],
                text=b["text"],
                provenance=b["provenance"],
                source_reference=b.get("source_reference"),
            )
            for b in document.blocks
        ],
        values=document.input_values,
        checks=[],
        content_hash=document.content_hash,
        template_reference=document.template_version_ref or "",
        clause_references=document.clause_versions,
    )
    data = render_docx(result, document.name)

    audit.record(
        db,
        action="document_downloaded",
        object_type="document",
        object_id=str(document.id),
        actor_id=principal.user_id,
        actor_label=principal.name,
        entity=document.entity,
    )
    return Response(
        content=data,
        media_type=(
            "application/vnd.openxmlformats-officedocument.wordprocessingml.document"
        ),
        headers={
            "Content-Disposition": f'attachment; filename="{document.name}.docx"',
            "X-Content-Hash": document.content_hash,
        },
    )


@router.get("/matters/{matter_id}/documents")
def list_documents(
    matter_id: uuid.UUID, db: Db, principal: CurrentUser
) -> list[DocumentOut]:
    documents = db.execute(
        select(Document)
        .where(Document.matter_id == matter_id)
        .order_by(Document.version.desc())
    ).scalars()
    return [_to_out(d) for d in documents]


@router.get("/matters/{matter_id}/findings", response_model=list[FindingOut])
def list_findings(
    matter_id: uuid.UUID, db: Db, principal: CurrentUser
) -> list[ReviewFinding]:
    return list(
        db.execute(
            select(ReviewFinding)
            .where(ReviewFinding.matter_id == matter_id)
            .order_by(ReviewFinding.sequence)
        ).scalars()
    )


@router.post("/findings/{finding_id}/decision", response_model=FindingOut)
def decide_finding(
    finding_id: uuid.UUID, payload: FindingDecision, db: Db, principal: CurrentUser
) -> ReviewFinding:
    """Suggestions are drafts until a named person accepts them.

    Legal operations may clear a minor finding on a tier 2 matter when it
    matches a pre-approved fallback. Anything else escalates to counsel.
    """
    finding = db.get(ReviewFinding, finding_id)
    if finding is None:
        raise NotFound("That finding was not found.")
    matter = db.get(Matter, finding.matter_id)

    authority = AuthorityLevel(finding.required_authority)
    rule = AUTHORITY_MATRIX[authority]

    ops_clearance = (
        principal.has_role(Role.LEGAL_OPS)
        and not principal.has_role(Role.COUNSEL, Role.HEAD_OF_LEGAL, Role.ADMIN)
    )
    if ops_clearance:
        eligible = (
            matter is not None
            and matter.risk_tier == RiskTier.TIER_2.value
            and finding.severity == Severity.MINOR.value
            and finding.matches_preapproved_fallback
        )
        if not eligible:
            raise Forbidden(
                "Legal operations may clear only minor findings on a tier 2 matter that "
                "match a pre-approved fallback. This one escalates to counsel."
            )
        finding.clearance_rule = (
            "Tier 2, minor severity, matches a pre-approved fallback, cleared by Legal "
            "operations."
        )
    elif not principal.has_role(*rule["roles"]):
        raise Forbidden(
            f"Conceding this point requires {rule['label']}."
        )

    edited = (payload.edited_text or "").strip()
    if payload.decision == "edited" and not edited:
        raise Refused(
            "That decision cannot be recorded.",
            [
                "Accepting with an edit means recording the wording you are accepting. "
                "Either supply the edited text or accept the suggestion as it stands."
            ],
        )
    if edited and edited == (finding.suggested_redline or "").strip():
        # Same words as the suggestion. It was accepted, not edited, and the
        # record should say which, because attribution differs between them.
        payload.decision = "accepted"
        edited = ""

    finding.decision = payload.decision
    finding.edited_text = edited or None
    finding.decided_by_id = uuid.UUID(principal.user_id)
    finding.decided_at = datetime.now(UTC)

    if finding.interaction_id:
        from app.ai.gateway import record_human_decision

        record_human_decision(
            db,
            finding.interaction_id,
            payload.decision,
            uuid.UUID(principal.user_id),
            payload.reason,
        )

    audit.record(
        db,
        action="finding_decided",
        object_type="review_finding",
        object_id=str(finding.id),
        actor_id=principal.user_id,
        actor_label=principal.name,
        entity=matter.entity if matter else None,
        after_state={
            "decision": payload.decision,
            "authority": authority.value,
            "edited": bool(finding.edited_text),
        },
    )
    return finding


@router.post("/documents/{document_id}/redline")
def produce_redline(document_id: uuid.UUID, db: Db, principal: CurrentUser) -> Ack:
    """Write accepted suggestions back as tracked changes."""
    principal.require_role(Role.COUNSEL, Role.HEAD_OF_LEGAL, Role.ADMIN)
    document = db.get(Document, document_id)
    if document is None:
        raise NotFound(DOCUMENT_NOT_FOUND)

    accepted = list(
        db.execute(
            select(Suggestion).where(
                Suggestion.document_id == document.id, Suggestion.decision == "accepted"
            )
        ).scalars()
    )
    if not accepted:
        raise Conflict("No suggestions on this document have been accepted.")

    blocks = {b["key"]: dict(b) for b in document.blocks}
    tracked = []
    for suggestion in accepted:
        block = blocks.get(suggestion.block_key)
        if block is None:
            continue
        block["text"] = suggestion.proposed_text
        block["tracked_change"] = {
            "author": principal.name,
            "original": suggestion.original_text,
            "reason": suggestion.rationale,
            "novel": suggestion.novel,
        }
        tracked.append(suggestion.block_key)

    redline = Document(
        matter_id=document.matter_id,
        entity=document.entity,
        name=f"{document.name}, redline",
        document_type=DocumentType.REDLINE.value,
        version=document.version + 1,
        template_version_ref=document.template_version_ref,
        clause_versions=document.clause_versions,
        input_values=document.input_values,
        blocks=list(blocks.values()),
        content_hash="",
        classification=document.classification,
        generated_by_id=uuid.UUID(principal.user_id),
        generated_at=datetime.now(UTC),
        novel_clause_count=sum(1 for s in accepted if s.novel),
        supersedes_id=document.id,
    )
    from app.services.hashing import content_hash

    redline.content_hash = content_hash(redline.blocks, redline.template_version_ref)
    db.add(redline)

    return Ack(
        message=(
            f"Redline produced with {len(tracked)} tracked changes, attributed to "
            f"{principal.name}. Approvals against the previous hash are invalidated."
        )
    )


@router.post("/matters/{matter_id}/auto-issue", status_code=201)
def auto_issue(
    matter_id: uuid.UUID,
    payload: AutoIssueRequest,
    db: Db,
    principal: CurrentUser,
) -> dict:
    """Issue a tier 1 document without a drafting cycle, LOP-M04-US-04.

    Auto-issue is deterministic assembly plus a signature request, nothing more.
    Every reason it might not be safe is checked first, and the issued document
    joins the monthly quality sample so automation stays under review.
    """
    principal.require_role(Role.LEGAL_OPS, Role.COUNSEL, Role.HEAD_OF_LEGAL, Role.ADMIN)

    matter = db.get(Matter, matter_id)
    if matter is None:
        raise NotFound("That matter was not found.")

    request_type = (
        db.get(RequestType, matter.request_type_id) if matter.request_type_id else None
    )
    version = db.execute(
        select(TemplateVersion).where(TemplateVersion.reference == payload.template_reference)
    ).scalar_one_or_none()
    if version is None:
        raise NotFound("That template version was not found.")

    document = generate_document(
        GenerateRequest(
            matter_id=matter.id,
            template_reference=payload.template_reference,
            facts=payload.facts,
            name=payload.name,
        ),
        db,
        principal,
    )

    record = db.get(Document, document.id)
    outstanding = len(
        list(
            db.execute(
                select(Approval).where(
                    Approval.matter_id == matter.id,
                    Approval.decision == ApprovalDecision.PENDING.value,
                )
            ).scalars()
        )
    )

    eligibility = autoissue.assess(
        auto_issue_configured=bool(request_type and request_type.tier_1_auto_issue),
        risk_tier=matter.risk_tier,
        template_status=version.status,
        template_effective_date=version.effective_date,
        novel_clause_count=record.novel_clause_count,
        open_items=record.open_items or [],
        outstanding_approvals=outstanding,
        counterparty_complete=matter.counterparty_id is not None,
    )
    if not eligibility.permitted:
        audit.record(
            db,
            action="auto_issue_refused",
            object_type="matter",
            object_id=matter.number,
            actor_id=principal.user_id,
            actor_label=principal.name,
            entity=matter.entity,
            result="failure",
            detail="; ".join(eligibility.reasons),
        )
        raise Refused("This document cannot be auto-issued.", list(eligibility.reasons))

    signature = SignatureRequest(
        matter_id=matter.id,
        document_id=record.id,
        document_hash=record.content_hash,
        provider="internal",
        external_reference=f"SIG-{uuid.uuid4().hex[:12]}",
        signers=payload.signers,
        status="sent",
        requested_by_id=uuid.UUID(principal.user_id),
    )
    db.add(signature)

    matter.status = MatterState.AWAITING_SIGNATURE.value
    matter.next_action = "Awaiting signature, issued automatically"

    sample = QualitySample(
        entity=matter.entity,
        period=autoissue.sample_period(),
        object_type="document",
        object_reference=record.content_hash,
        reason=(
            f"Tier 1 auto-issue on {matter.number} from {version.reference} with no "
            "human review at the point of issue."
        ),
    )
    db.add(sample)

    audit.record(
        db,
        action="document_auto_issued",
        object_type="document",
        object_id=str(record.id),
        actor_id=principal.user_id,
        actor_label=principal.name,
        entity=matter.entity,
        after_state={
            "matter": matter.number,
            "template": version.reference,
            "signature_reference": signature.external_reference,
            "quality_sample_period": sample.period,
        },
    )

    return {
        "document_id": str(record.id),
        "content_hash": record.content_hash,
        "signature_reference": signature.external_reference,
        "quality_sample_period": sample.period,
        "message": (
            f"{matter.number} was issued from {version.reference} without a drafting "
            "cycle and sent for signature. It is in the quality sample for "
            f"{sample.period}."
        ),
    }


@router.get("/quality-sample")
def quality_sample(
    db: Db, principal: CurrentUser, entity: WorkingEntity, period: str | None = None
) -> list[dict]:
    """What tier 1 automation issued, and whether anyone has looked at it yet."""
    principal.require_role(Role.HEAD_OF_LEGAL, Role.COUNSEL, Role.ADMIN, Role.AUDITOR)

    stmt = select(QualitySample).where(QualitySample.entity == entity)
    if period:
        stmt = stmt.where(QualitySample.period == period)
    return [
        {
            "id": str(row.id),
            "period": row.period,
            "object_type": row.object_type,
            "object_reference": row.object_reference,
            "reason": row.reason,
            "reviewed": row.reviewed,
            "outcome": row.outcome,
            "notes": row.notes,
            "created_at": row.created_at,
        }
        for row in db.execute(stmt.order_by(QualitySample.created_at.desc())).scalars()
    ]


@router.post("/quality-sample/{sample_id}/review")
def review_sample(
    sample_id: uuid.UUID,
    outcome: str,
    db: Db,
    principal: CurrentUser,
    notes: str | None = None,
) -> Ack:
    principal.require_role(Role.HEAD_OF_LEGAL, Role.COUNSEL, Role.ADMIN)

    sample = db.get(QualitySample, sample_id)
    if sample is None:
        raise NotFound("That sample was not found.")
    if outcome not in {"sound", "minor_issue", "material_issue"}:
        raise Refused(
            "That outcome is not recognised.",
            ["Record the outcome as sound, minor_issue or material_issue."],
        )

    sample.reviewed = True
    sample.reviewer_id = uuid.UUID(principal.user_id)
    sample.reviewed_at = datetime.now(UTC)
    sample.outcome = outcome
    sample.notes = notes

    audit.record(
        db,
        action="quality_sample_reviewed",
        object_type="quality_sample",
        object_id=str(sample.id),
        actor_id=principal.user_id,
        actor_label=principal.name,
        entity=sample.entity,
        after_state={"outcome": outcome},
    )
    return Ack(message=f"Sample recorded as {outcome.replace('_', ' ')}.")
