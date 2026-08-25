"""Approval routing and electronic execution, M07."""

from __future__ import annotations

import json
import logging
import uuid
from datetime import UTC, datetime

import httpx
from fastapi import APIRouter, Header, Request
from sqlalchemy import select

from app.core import audit
from app.core.config import settings
from app.core.deps import AnonDb, CurrentUser, Db
from app.core.errors import Conflict, Forbidden, NotFound, Refused, ValidationFailed
from app.core.security import verify_webhook
from app.db.models.contract import (
    Approval,
    Contract,
    SignatureRequest,
)
from app.db.models.counterparty import Counterparty
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
from app.services import memory, notifications, sequences, storage
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


def _refuse_counterparty_paper(document: Document, act: str, instead: str) -> None:
    """Their paper is evidence, not our position.

    Nothing in it came from an approved clause, so approving or executing it
    would bind the organisation to wording no clause owner ever cleared. The
    review compares it; everything else refuses it.
    """
    if document.document_type == DocumentType.COUNTERPARTY.value:
        raise Refused(
            f"Counterparty paper cannot be {act}.",
            [
                f"{document.name} is their draft, held for comparison against the "
                f"playbook. Generate our own document from an approved template and "
                f"{instead}."
            ],
        )


@router.post("/matters/{matter_id}/approvals", status_code=201)
def open_approvals(
    matter_id: uuid.UUID,
    payload: SignatureRequestCreate,
    db: Db,
    principal: CurrentUser,
) -> list[ApprovalOut]:
    """Route a document for approval. Approval binds to its content hash."""
    principal.require_role(Role.COUNSEL, Role.HEAD_OF_LEGAL, Role.ADMIN)

    matter = db.get(Matter, matter_id)
    document = db.get(Document, payload.document_id)
    if matter is None or document is None:
        raise NotFound("That matter or document was not found.")
    _refuse_counterparty_paper(document, "routed for approval", "route that instead")

    if document.immutable or document.document_type == DocumentType.EXECUTED.value:
        # Approval comes before execution, so an executed copy has nothing left
        # to approve. Opening a chain on one would invite somebody to decide
        # about an agreement that has already been signed, and record their
        # decision as though it had governed anything.
        raise Conflict(
            f"{document.name} is the executed copy. Approval happens before execution, "
            "so there is nothing here left to decide."
        )

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

    drafter = db.get(User, document.generated_by_id) if document.generated_by_id else None
    context = service.ChainContext(
        entity=matter.entity,
        agreement_type=agreement_type,
        risk_tier=matter.risk_tier,
        value_amount=float(matter.value_amount) if matter.value_amount else None,
        privacy_flag=matter.privacy_flag,
        requester_id=matter.requester_id,
        drafter_id=document.generated_by_id,
        drafter_is_head=bool(drafter and Role.HEAD_OF_LEGAL.value in (drafter.roles or [])),
        counterparty_paper=document.document_type == DocumentType.COUNTERPARTY.value,
    )
    name, steps, notes = service.derive_chain(context)
    created = service.open_chain(
        db,
        matter_id=matter.id,
        document_id=document.id,
        document_hash=document.content_hash,
        name=name,
        steps=steps,
        notes=notes,
        resolve_approver=_resolve_approver(db, matter.entity),
    )
    for approval in created:
        db.add(approval)
    db.flush()

    matter.status = MatterState.IN_APPROVAL.value
    matter.next_action = f"Approval: {name}"

    for approval in service.current_step(created):
        approver = db.get(User, approval.approver_id) if approval.approver_id else None
        if approver:
            notifications.notify(
                db,
                connector_code="notification_channel",
                recipients=[approver.work_email],
                subject=(
                    f"A draft is waiting on you, {matter.number}"
                    if approval.approver_role == "requester"
                    else f"Approval needed on {matter.number}"
                ),
                body=(
                    # The requester is not reading a hash. They are being asked
                    # whether the draft is the arrangement they asked for, and
                    # a message about novel clause counts tells them nothing
                    # about that.
                    f"Legal has prepared a draft for {matter.number}. Open My requests "
                    "in the portal to read it and confirm it is what you asked for."
                    if approval.approver_role == "requester"
                    else (
                        f"{approval.step_name} on {matter.number}.\n"
                        f"Document hash {document.content_hash[:16]}.\n"
                        f"Novel clauses: {document.novel_clause_count}.\n"
                        "Action requires authenticated single sign-on."
                    )
                ),
                record_reference=matter.number,
                matter_id=matter.id,
            )
            notifications.raise_in_app(
                db,
                recipient_id=approver.id,
                entity=matter.entity,
                kind="approval_waiting",
                title=f"{approval.step_name} on {matter.number}",
                body=(
                    f"Bound to {document.content_hash[:12]}. "
                    f"{document.novel_clause_count} novel clauses."
                ),
                href=(
                    "/portal/status"
                    if approval.approver_role == "requester"
                    else f"/workspace/matters/{matter.id}"
                ),
                reference=matter.number,
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
        after_state={
            "chain": name,
            "steps": [step["name"] for step in steps],
            "notes": notes,
            "hash": document.content_hash,
        },
    )
    return _decorate(created, db)


def _decorate(approvals: list[Approval], db=None) -> list[ApprovalOut]:
    actionable = {a.id for a in service.current_step(approvals)}
    names: dict[uuid.UUID, str] = {}
    if db is not None:
        wanted = {a.approver_id for a in approvals if a.approver_id}
        if wanted:
            names = {
                user.id: user.name
                for user in db.execute(select(User).where(User.id.in_(wanted))).scalars()
            }

    out = []
    for approval in approvals:
        model = ApprovalOut.model_validate(approval)
        model.actionable = approval.id in actionable
        model.approver_name = names.get(approval.approver_id) if approval.approver_id else None
        model.notes = list((approval.chain_snapshot or {}).get("notes", []))
        out.append(model)
    return out


@router.get("/matters/{matter_id}/approvals")
def list_approvals(matter_id: uuid.UUID, db: Db, principal: CurrentUser) -> list[ApprovalOut]:
    approvals = list(
        db.execute(
            select(Approval).where(Approval.matter_id == matter_id).order_by(Approval.step_index)
        ).scalars()
    )
    return _decorate(approvals, db)


def _placement_url(request: SignatureRequest) -> str | None:
    """Where a person places the fields on the page for this request.

    Only while it is out. Once it is completed, declined or cancelled there is
    nothing left to place, and a live link to a finished document invites
    somebody to change one.
    """
    if request.provider != "opensign" or request.status != "sent":
        return None
    if not request.external_reference:
        return None
    document = request.external_reference.removeprefix("OS-")
    return f"{settings.opensign_client_url.rstrip('/')}/placeHolderSign/{document}"


def _signature_out(request: SignatureRequest) -> SignatureOut:
    model = SignatureOut.model_validate(request)
    model.placement_url = _placement_url(request)
    return model


@router.get("/matters/{matter_id}/signature-requests", response_model=list[SignatureOut])
def list_signature_requests(
    matter_id: uuid.UUID, db: Db, principal: CurrentUser
) -> list[SignatureOut]:
    """Open and closed signature requests on a matter, newest first."""
    return [
        _signature_out(request)
        for request in db.execute(
            select(SignatureRequest)
            .where(SignatureRequest.matter_id == matter_id)
            .order_by(SignatureRequest.created_at.desc())
        ).scalars()
    ]


@router.post("/signature/requests/{request_id}/placement-session")
def placement_session(request_id: uuid.UUID, db: Db, principal: CurrentUser) -> dict:
    """A session for the placement screen, so nobody signs in twice.

    Held to the same roles that may issue a request in the first place, and
    only while the request is still out. The session it hands back is the
    platform's own account on the signing service, which is what every
    document there already belongs to, so this grants nothing that issuing the
    request did not.
    """
    principal.require_role(Role.COUNSEL, Role.HEAD_OF_LEGAL, Role.ADMIN)

    record = db.get(SignatureRequest, request_id)
    if record is None:
        raise NotFound("That signature request was not found.")
    if record.status != "sent":
        raise Conflict(f"That request is {record.status}. There is nothing left to place on it.")

    opened = signature_service.selected().placement_session()
    if opened is None:
        raise Conflict("The signing service would not open a session.")

    audit.record(
        db,
        action="placement_session_opened",
        object_type="signature_request",
        object_id=str(record.id),
        actor_id=principal.user_id,
        actor_label=principal.name,
        after_state={"reference": record.external_reference},
    )
    return {
        **opened,
        "document": (record.external_reference or "").removeprefix("OS-"),
    }


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

    # A requester confirming their own request is not exercising a legal
    # authority, so it is not gated on one. The legal lead step is, because
    # it is the sign-off that puts the organisation behind the wording.
    if approval.approver_role == Role.HEAD_OF_LEGAL.value:
        principal.require_step_up(f"Approving {approval.step_name}")

    if (
        payload.decision == ApprovalDecision.CHANGES_REQUESTED.value
        and not (payload.comments or "").strip()
    ):
        raise ValidationFailed(
            "Say what should change.",
            {
                "comments": (
                    "The drafter reads this and works from it, so a change asked for "
                    "without saying what is a message nobody can act on."
                )
            },
        )

    service.record_decision(approval, payload.decision, payload.comments, caller)

    if payload.decision == ApprovalDecision.CHANGES_REQUESTED.value and matter:
        # Back to drafting, and the step stays open. They have not decided
        # about this document; they have said this is not the document to
        # decide about. Their approval resumes when a new draft supersedes
        # this hash, which invalidates the chain and opens a fresh one.
        matter.status = MatterState.DRAFTING.value
        matter.next_action = f"Changes asked for at {approval.step_name}"
    elif payload.decision == ApprovalDecision.REJECTED.value and matter:
        matter.status = MatterState.IN_REVIEW.value
        matter.next_action = f"Rejected at {approval.step_name}"
    elif matter and service.fully_approved(siblings, approval.document_hash):
        matter.status = MatterState.AWAITING_SIGNATURE.value
        matter.next_action = "Ready for signature"

    if matter:
        # The lawyer who owns the matter is told what happened to it, and the
        # next approver is told it has reached them. A chain that advances in
        # silence is one somebody has to remember to check.
        notifications.raise_in_app(
            db,
            recipient_id=matter.responsible_lawyer_id,
            entity=matter.entity,
            kind="approval_decided",
            title=f"{approval.step_name} {payload.decision} on {matter.number}",
            body=payload.comments or matter.next_action,
            href=f"/workspace/matters/{matter.id}",
            reference=matter.number,
            matter_id=matter.id,
        )
        if payload.decision == ApprovalDecision.APPROVED.value:
            for following in service.current_step(siblings):
                if following.id == approval.id or following.approver_id is None:
                    continue
                notifications.raise_in_app(
                    db,
                    recipient_id=following.approver_id,
                    entity=matter.entity,
                    kind="approval_waiting",
                    title=f"{following.step_name} on {matter.number}",
                    body=f"{approval.step_name} has approved. This step is now yours.",
                    href=f"/workspace/matters/{matter.id}",
                    reference=matter.number,
                    matter_id=matter.id,
                )

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
    return _decorate([approval], db)[0]


@router.post("/signature/requests", response_model=SignatureOut, status_code=201)
def request_signature(
    payload: SignatureRequestCreate, db: Db, principal: CurrentUser
) -> SignatureOut:
    """A signature request cannot be issued for an unapproved hash."""
    principal.require_role(Role.COUNSEL, Role.HEAD_OF_LEGAL, Role.ADMIN)
    principal.require_step_up("issue a signature request")

    document = db.get(Document, payload.document_id)
    if document is None:
        raise NotFound("That document was not found.")
    _refuse_counterparty_paper(document, "sent for signature", "send that instead")

    approvals = list(
        db.execute(select(Approval).where(Approval.matter_id == document.matter_id)).scalars()
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
    db.flush()
    return _signature_out(request)


@router.post("/signature/requests/{request_id}/cancel")
def cancel_signature(request_id: uuid.UUID, reason: str, db: Db, principal: CurrentUser) -> Ack:
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
    # OpenSign signs its callbacks with whatever secret its webhook is
    # configured with, sent in this header. Both shapes are accepted, each
    # against its own key, and an unsigned callback is refused whichever
    # provider it claims to be from.
    opensign_signature = http_request.headers.get(
        "x-opensign-signature"
    ) or http_request.headers.get("x-webhook-signature", "")

    if x_signature and verify_webhook(body, x_signature):
        payload = json.loads(body)
        reference = payload.get("external_reference")
    elif (
        opensign_signature
        and settings.opensign_webhook_secret
        and verify_webhook(body, opensign_signature, settings.opensign_webhook_secret)
    ):
        payload = _from_opensign(json.loads(body))
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


def _from_opensign(payload: dict) -> dict:
    """Translate an OpenSign callback into the shape this endpoint already reads.

    OpenSign posts the document object it changed. The reference is its Parse
    object id, prefixed the same way the adapter prefixes it when the request
    is issued, so the two ends agree without either knowing the other's shape.
    """
    body = payload.get("body") or payload.get("data") or payload
    reference = body.get("objectId") or payload.get("objectId")
    return {
        "external_reference": f"OS-{reference}",
        "certificate": {
            "provider": "opensign",
            "event": payload.get("event") or payload.get("event_type"),
            "audit_trail": body.get("AuditTrail") or [],
            "signed_url": body.get("SignedUrl"),
            "completed_at": body.get("completedAt") or body.get("updatedAt"),
            "signers": body.get("Signers") or [],
        },
    }


def _fetch_signed(certificate: dict) -> tuple[bytes | None, bytes | None]:
    """The signed PDF and its certificate of completion, pulled back here.

    Held rather than linked. The platform is the authoritative archive, and an
    archive that is a link into somebody else's service is an archive until
    that service is retired, reconfigured or its signed URL expires. The
    signature is only visible on the PDF the service stamped: our own blocks
    are the unsigned text they were before anybody signed anything.
    """

    def pull(url: str | None) -> bytes | None:
        if not url:
            return None
        try:
            response = httpx.get(url, timeout=120.0, follow_redirects=True)
            response.raise_for_status()
        except httpx.HTTPError as exc:
            logger.warning("The signed copy could not be fetched from %s: %s", url, exc)
            return None
        return response.content

    return pull(certificate.get("signed_url")), pull(certificate.get("certificate_url"))


def _archive(db, request: SignatureRequest, certificate: dict) -> Contract:
    """On completion the executed copy becomes the authoritative record."""
    document = db.get(Document, request.document_id)
    matter = db.get(Matter, request.matter_id)

    signed, completion = _fetch_signed(certificate)
    if signed:
        # Under object lock, because this is the copy an argument is settled
        # against. Written before the document is marked immutable: the
        # immutability trigger refuses an update afterwards, which is the
        # point of it.
        key = f"executed/{matter.number}/{document.content_hash[:16]}.pdf"
        storage.store.put_immutable(key, signed, "application/pdf")
        document.storage_key = key
        certificate = {**certificate, "stored_key": key, "stored_bytes": len(signed)}
    else:
        logger.warning(
            "No signed copy was stored for %s. The record says executed and the "
            "signed document is only at the signing service.",
            matter.number,
        )

    if completion:
        key = f"executed/{matter.number}/{document.content_hash[:16]}-certificate.pdf"
        storage.store.put_immutable(key, completion, "application/pdf")
        certificate = {**certificate, "certificate_key": key}

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

    # Memory is written by the work that produces it. An agreement executed
    # this morning has to be answerable this afternoon; indexing on a schedule
    # would leave a window where the platform holds an answer it will not give.
    memory.index_contract(
        db,
        contract,
        matter=matter,
        counterparty=db.get(Counterparty, matter.counterparty_id)
        if matter.counterparty_id
        else None,
    )
    memory.index_contract_clauses(db, contract, document, matter=matter)

    matter.status = MatterState.EXECUTED.value
    # What is actually true. It used to say "Confirm the proposed obligations"
    # while nothing had proposed any: extraction is a separate, substantive AI
    # call that a person asks for, so the executed contract arrives with none
    # and the matter pointed at a step that did not exist.
    matter.next_action = "Extract the obligations from the executed contract"

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
def wet_ink(matter_id: uuid.UUID, payload: WetInkExecution, db: Db, principal: CurrentUser) -> Ack:
    """A manual fallback for execution outside the platform.

    Metadata completeness rules still apply.
    """
    principal.require_role(Role.COUNSEL, Role.HEAD_OF_LEGAL, Role.ADMIN)
    principal.require_step_up("record a wet-ink execution")

    matter = db.get(Matter, matter_id)
    document = db.get(Document, payload.document_id)
    if matter is None or document is None:
        raise NotFound("That matter or document was not found.")
    _refuse_counterparty_paper(document, "recorded as executed", "record that instead")
    if not payload.signatories:
        raise Refused(
            "This execution cannot be recorded.",
            ["At least one signatory must be named."],
        )

    document.document_type = DocumentType.EXECUTED.value
    document.immutable = True

    reference, _ = sequences.new_contract_reference(db, matter.entity)
    wet_ink = Contract(
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
    db.add(wet_ink)
    db.flush()
    memory.index_contract(
        db,
        wet_ink,
        matter=matter,
        counterparty=db.get(Counterparty, matter.counterparty_id)
        if matter.counterparty_id
        else None,
    )
    memory.index_contract_clauses(db, wet_ink, document, matter=matter)
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
