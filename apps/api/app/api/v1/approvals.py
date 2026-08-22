"""Approval routing and electronic execution, M07."""

from __future__ import annotations

import json
import logging
import uuid
from datetime import UTC, datetime

from fastapi import APIRouter, Header, Request
from sqlalchemy import select

from app.core import audit
from app.core.config import settings
from app.core.deps import AnonDb, CurrentUser, Db
from app.core.errors import Conflict, Forbidden, NotFound, Refused
from app.core.security import verify_webhook
from app.db.models.contract import (
    Approval,
    Contract,
    SignatureRequest,
)
from app.db.models.document import Document
from app.db.models.matter import Matter
from app.db.models.organisation import User
from app.domain.enums import ApprovalDecision, DocumentType, MatterState, Role
from app.schemas.common import Ack
from app.schemas.matters import (
    ApprovalDecisionRequest,
    ApprovalOut,
    SignatureOut,
    SignatureRequestCreate,
    WetInkExecution,
)
from app.services import approvals as service
from app.services import notifications, sequences
from app.services import signature as signature_service

logger = logging.getLogger(__name__)

router = APIRouter(tags=["approvals"])


def _resolve_approver(db, entity: str):
    def resolve(step: dict) -> uuid.UUID | None:
        named = step.get("user_id")
        if named:
            return uuid.UUID(named)
        role = step.get("role")
        if not role:
            return None
        for user in db.execute(select(User).where(User.active.is_(True))).scalars():
            if role in (user.roles or []) and entity in user.entity_codes:
                return user.id
        return None

    return resolve


@router.post("/matters/{matter_id}/approvals", status_code=201)
def open_approvals(
    matter_id: uuid.UUID,
    payload: SignatureRequestCreate,
    db: Db,
    principal: CurrentUser,
) -> list[ApprovalOut]:
    """Route a document for approval. Approval binds to its content hash."""
    principal.require_role(Role.LEGAL_OPS, Role.COUNSEL, Role.HEAD_OF_LEGAL, Role.ADMIN)

    matter = db.get(Matter, matter_id)
    document = db.get(Document, payload.document_id)
    if matter is None or document is None:
        raise NotFound("That matter or document was not found.")

    existing = list(
        db.execute(
            select(Approval).where(
                Approval.matter_id == matter.id,
                Approval.document_hash == document.content_hash,
                Approval.decision != ApprovalDecision.INVALIDATED.value,
            )
        ).scalars()
    )
    if existing:
        raise Conflict("This document hash is already in an approval chain.")

    request_type = matter.request_type_id
    agreement_type = "unknown"
    if request_type:
        from app.db.models.intake import RequestType

        record = db.get(RequestType, request_type)
        if record:
            agreement_type = record.agreement_type

    context = service.ChainContext(
        entity=matter.entity,
        agreement_type=agreement_type,
        risk_tier=matter.risk_tier,
        value_amount=float(matter.value_amount) if matter.value_amount else None,
        privacy_flag=matter.privacy_flag,
    )
    chain = service.resolve_chain(db, context)
    created = service.open_chain(
        db,
        matter_id=matter.id,
        document_id=document.id,
        document_hash=document.content_hash,
        chain=chain,
        context=context,
        resolve_approver=_resolve_approver(db, matter.entity),
    )
    db.flush()

    matter.status = MatterState.IN_APPROVAL.value
    matter.next_action = f"Approval chain: {chain.name}"

    for approval in service.current_step(created):
        approver = db.get(User, approval.approver_id) if approval.approver_id else None
        if approver:
            notifications.notify(
                db,
                connector_code="notification_channel",
                recipients=[approver.work_email],
                subject=f"Approval needed on {matter.number}",
                body=(
                    f"{approval.step_name} on {matter.number}.\n"
                    f"Document hash {document.content_hash[:16]}.\n"
                    f"Novel clauses: {document.novel_clause_count}.\n"
                    "Action requires authenticated single sign-on."
                ),
                record_reference=matter.number,
                matter_id=matter.id,
            )

    audit.record(
        db,
        action="approval_chain_opened",
        object_type="matter",
        object_id=matter.number,
        actor_id=principal.user_id,
        actor_label=principal.name,
        entity=matter.entity,
        after_state={"chain": chain.name, "hash": document.content_hash},
    )
    return _decorate(created)


def _decorate(approvals: list[Approval]) -> list[ApprovalOut]:
    actionable = {a.id for a in service.current_step(approvals)}
    out = []
    for approval in approvals:
        model = ApprovalOut.model_validate(approval)
        model.actionable = approval.id in actionable
        out.append(model)
    return out


@router.get("/matters/{matter_id}/approvals")
def list_approvals(
    matter_id: uuid.UUID, db: Db, principal: CurrentUser
) -> list[ApprovalOut]:
    approvals = list(
        db.execute(
            select(Approval)
            .where(Approval.matter_id == matter_id)
            .order_by(Approval.step_index)
        ).scalars()
    )
    return _decorate(approvals)


@router.get("/matters/{matter_id}/signature-requests", response_model=list[SignatureOut])
def list_signature_requests(
    matter_id: uuid.UUID, db: Db, principal: CurrentUser
) -> list[SignatureRequest]:
    """Open and closed signature requests on a matter, newest first."""
    return list(
        db.execute(
            select(SignatureRequest)
            .where(SignatureRequest.matter_id == matter_id)
            .order_by(SignatureRequest.created_at.desc())
        ).scalars()
    )


@router.post("/approvals/{approval_id}/decision")
def decide(
    approval_id: uuid.UUID,
    payload: ApprovalDecisionRequest,
    db: Db,
    principal: CurrentUser,
) -> ApprovalOut:
    approval = db.get(Approval, approval_id)
    if approval is None:
        raise NotFound("That approval was not found.")

    matter = db.get(Matter, approval.matter_id)
    siblings = list(
        db.execute(select(Approval).where(Approval.matter_id == approval.matter_id)).scalars()
    )
    if approval.id not in {a.id for a in service.current_step(siblings)}:
        raise Conflict("An earlier step in this chain is still outstanding.")

    caller = uuid.UUID(principal.user_id)
    is_named = approval.approver_id == caller
    is_delegate = False
    if approval.approver_id:
        named = db.get(User, approval.approver_id)
        is_delegate = bool(named and named.delegate_id == caller)
    if not (is_named or is_delegate or principal.is_admin):
        raise Forbidden("This approval step is assigned to someone else.")

    service.record_decision(approval, payload.decision, payload.comments, caller)

    if payload.decision == ApprovalDecision.REJECTED.value and matter:
        matter.status = MatterState.IN_REVIEW.value
        matter.next_action = f"Rejected at {approval.step_name}"
    elif matter and service.fully_approved(siblings, approval.document_hash):
        matter.next_action = "Ready for signature"

    audit.record(
        db,
        action="approval_decided",
        object_type="approval",
        object_id=str(approval.id),
        actor_id=principal.user_id,
        actor_label=principal.name,
        entity=matter.entity if matter else None,
        after_state={
            "decision": payload.decision,
            "hash": approval.document_hash,
            "delegate": is_delegate,
        },
    )
    return _decorate([approval])[0]


@router.post("/signature/requests", response_model=SignatureOut, status_code=201)
def request_signature(
    payload: SignatureRequestCreate, db: Db, principal: CurrentUser
) -> SignatureRequest:
    """A signature request cannot be issued for an unapproved hash."""
    principal.require_role(Role.COUNSEL, Role.HEAD_OF_LEGAL, Role.ADMIN)
    principal.require_step_up("issue a signature request")

    document = db.get(Document, payload.document_id)
    if document is None:
        raise NotFound("That document was not found.")

    approvals = list(
        db.execute(
            select(Approval).where(Approval.matter_id == document.matter_id)
        ).scalars()
    )
    service.assert_signable(approvals, document.content_hash)

    matter = db.get(Matter, document.matter_id)

    # The provider receives the rendered document rather than a template
    # reference, so what the counterparty signs is the copy whose hash the
    # approval bound to.
    provider = signature_service.selected()
    try:
        issued = provider.issue(
            document.name,
            document.content_hash,
            payload.signers,
            _render_for_signature(document),
        )
    except signature_service.ProviderRefused as exception:
        raise Conflict(str(exception)) from exception

    request = SignatureRequest(
        matter_id=document.matter_id,
        document_id=document.id,
        document_hash=document.content_hash,
        provider=issued.provider,
        external_reference=issued.external_reference,
        signers=payload.signers,
        status="sent",
        requested_by_id=uuid.UUID(principal.user_id),
    )
    db.add(request)
    db.flush()

    if matter:
        matter.status = MatterState.AWAITING_SIGNATURE.value
        matter.next_action = "Awaiting signature"

    audit.record(
        db,
        action="signature_requested",
        object_type="signature_request",
        object_id=request.external_reference,
        actor_id=principal.user_id,
        actor_label=principal.name,
        entity=matter.entity if matter else None,
        after_state={
            "hash": document.content_hash,
            "signers": len(payload.signers),
            "provider": issued.provider,
            "detail": issued.detail,
        },
    )
    return request


@router.post("/signature/requests/{request_id}/cancel")
def cancel_signature(
    request_id: uuid.UUID, reason: str, db: Db, principal: CurrentUser
) -> Ack:
    principal.require_role(Role.COUNSEL, Role.HEAD_OF_LEGAL, Role.ADMIN)
    request = db.get(SignatureRequest, request_id)
    if request is None:
        raise NotFound("That signature request was not found.")
    if request.status == "completed":
        raise Conflict("That signature request is already complete.")

    provider = signature_service.PROVIDERS.get(
        request.provider, signature_service.PROVIDERS["internal"]
    )
    withdrawn = provider.cancel(request.external_reference or "", reason)

    request.status = "cancelled"
    request.cancelled_reason = reason

    audit.record(
        db,
        action="signature_cancelled",
        object_type="signature_request",
        object_id=request.external_reference or str(request.id),
        actor_id=principal.user_id,
        actor_label=principal.name,
        after_state={"reason": reason, "provider": request.provider},
    )
    return Ack(message=f"The signature request is cancelled. {withdrawn}")


@router.post("/webhooks/signature")
async def signature_webhook(
    http_request: Request,
    db: AnonDb,
    x_signature: str = Header(default=""),
) -> Ack:
    """Webhooks are signed and replay-protected (PRD section 12.1).

    DocuSeal signs with its own secret and its own header, so both shapes are
    accepted, each against its own key. An unsigned callback is refused
    whichever provider it claims to be from.
    """
    body = await http_request.body()
    docuseal_signature = http_request.headers.get("x-docuseal-signature", "")

    if x_signature and verify_webhook(body, x_signature):
        payload = json.loads(body)
        reference = payload.get("external_reference")
    elif docuseal_signature and settings.docuseal_webhook_secret and verify_webhook(
        body, docuseal_signature, settings.docuseal_webhook_secret
    ):
        payload = _from_docuseal(json.loads(body))
        reference = payload.get("external_reference")
    else:
        raise Forbidden("The webhook signature did not verify.")
    request = db.execute(
        select(SignatureRequest).where(SignatureRequest.external_reference == reference)
    ).scalar_one_or_none()
    if request is None:
        raise NotFound("That signature request was not found.")
    if request.status == "completed":
        return Ack(message="Already recorded.")

    request.status = "completed"
    request.completed_at = datetime.now(UTC)
    request.audit_certificate = payload.get("certificate", {})

    _archive(db, request, payload.get("certificate", {}))

    return Ack(message="Execution recorded and the agreement archived.")


def _render_for_signature(document: Document) -> bytes | None:
    """The document as a file the provider can present.

    A provider that cannot be given the exact bytes gets nothing, because
    sending it something else would break the tie between what was approved
    and what was signed.
    """
    try:
        from app.services.generation import GeneratedBlock, GenerationResult, render_docx

        result = GenerationResult(
            blocks=[
                GeneratedBlock(
                    key=block["key"],
                    number=block["number"],
                    heading=block["heading"],
                    text=block["text"],
                    provenance=block["provenance"],
                    source_reference=block.get("source_reference"),
                )
                for block in document.blocks
            ],
            values=document.input_values,
            checks=[],
            content_hash=document.content_hash,
            template_reference=document.template_version_ref or "",
            clause_references=document.clause_versions,
        )
        return render_docx(result, document.name)
    except Exception:
        logger.exception("The document could not be rendered for signature.")
        return None


def _from_docuseal(payload: dict) -> dict:
    """Translate a DocuSeal callback into the shape this endpoint already reads."""
    data = payload.get("data") or payload
    submission = data.get("submission") or {}
    reference = submission.get("id") or data.get("submission_id") or data.get("id")
    return {
        "external_reference": f"DS-{reference}",
        "certificate": {
            "provider": "docuseal",
            "event": payload.get("event_type"),
            "audit_log_url": submission.get("audit_log_url") or data.get("audit_log_url"),
            "completed_at": data.get("completed_at"),
            "submitters": data.get("submitters") or submission.get("submitters") or [],
        },
    }


def _archive(db, request: SignatureRequest, certificate: dict) -> Contract:
    """On completion the executed copy becomes the authoritative record."""
    document = db.get(Document, request.document_id)
    matter = db.get(Matter, request.matter_id)

    document.document_type = DocumentType.EXECUTED.value
    document.immutable = True

    reference, sequence = sequences.new_contract_reference(db, matter.entity)
    agreement_type = "unknown"
    if matter.request_type_id:
        from app.db.models.intake import RequestType

        record = db.get(RequestType, matter.request_type_id)
        if record:
            agreement_type = record.agreement_type

    contract = Contract(
        reference=reference,
        matter_id=matter.id,
        entity=matter.entity,
        counterparty_id=matter.counterparty_id,
        agreement_type=agreement_type,
        effective_date=datetime.now(UTC).date(),
        value_amount=matter.value_amount,
        value_currency=matter.value_currency,
        signature_status="executed",
        executed_document_id=document.id,
        executed_at=datetime.now(UTC),
        content_hash=document.content_hash,
        signature_certificate=certificate,
        authoritative=True,
    )
    db.add(contract)
    db.flush()

    matter.status = MatterState.EXECUTED.value
    matter.next_action = "Confirm the proposed obligations"

    audit.record(
        db,
        action="agreement_executed",
        object_type="contract",
        object_id=reference,
        actor_label="signature service",
        entity=matter.entity,
        after_state={"hash": document.content_hash, "matter": matter.number},
    )
    return contract


@router.post("/matters/{matter_id}/execute-wet-ink")
def wet_ink(
    matter_id: uuid.UUID, payload: WetInkExecution, db: Db, principal: CurrentUser
) -> Ack:
    """A manual fallback for execution outside the platform.

    Metadata completeness rules still apply.
    """
    principal.require_role(Role.COUNSEL, Role.HEAD_OF_LEGAL, Role.ADMIN)
    principal.require_step_up("record a wet-ink execution")

    matter = db.get(Matter, matter_id)
    document = db.get(Document, payload.document_id)
    if matter is None or document is None:
        raise NotFound("That matter or document was not found.")
    if not payload.signatories:
        raise Refused(
            "This execution cannot be recorded.",
            ["At least one signatory must be named."],
        )

    document.document_type = DocumentType.EXECUTED.value
    document.immutable = True

    reference, _ = sequences.new_contract_reference(db, matter.entity)
    db.add(
        Contract(
            reference=reference,
            matter_id=matter.id,
            entity=matter.entity,
            counterparty_id=matter.counterparty_id,
            agreement_type="unknown",
            effective_date=payload.signature_date,
            value_amount=matter.value_amount,
            value_currency=matter.value_currency,
            signature_status="executed",
            executed_document_id=document.id,
            executed_at=datetime.now(UTC),
            content_hash=document.content_hash,
            executed_outside_platform=True,
            execution_reason=payload.reason,
            authoritative=True,
            signature_certificate={"signatories": payload.signatories},
        )
    )
    matter.status = MatterState.EXECUTED.value

    audit.record(
        db,
        action="agreement_executed_outside_platform",
        object_type="contract",
        object_id=reference,
        actor_id=principal.user_id,
        actor_label=principal.name,
        entity=matter.entity,
        after_state={"reason": payload.reason, "signatories": payload.signatories},
    )
    return Ack(message=f"Execution recorded as {reference}.")
