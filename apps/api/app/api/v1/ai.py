"""AI capability endpoints, M05, M06, M09 and M10."""

from __future__ import annotations

import uuid
from datetime import UTC, datetime

from fastapi import APIRouter, Query
from sqlalchemy import select

from app.ai import retrieval
from app.ai.capabilities import REGISTRY
from app.ai.gateway import CapabilityCall, invoke, record_human_decision
from app.core import audit
from app.core.deps import CurrentUser, Db, WorkingEntity
from app.core.errors import Conflict, NotFound, Refused
from app.db.models.contract import Contract, Obligation
from app.db.models.counterparty import Counterparty
from app.db.models.document import Document, ReviewFinding
from app.db.models.governance import Communication, ExtractedValue
from app.db.models.library import Clause, Playbook
from app.db.models.matter import DecisionRecord, Matter
from app.domain.enums import (
    CommunicationClass,
    DataClass,
    DocumentType,
    MatterState,
    ObligationStatus,
    RiskTier,
    Role,
    Severity,
    VersionStatus,
)
from app.schemas.common import Ack
from app.schemas.governance import (
    AnswerOut,
    AnswerParagraph,
    AskRequest,
    CommunicationOut,
    ConfirmFromInbox,
    CorrectClassification,
    ExtractionDecision,
    PositionHistoryEntry,
    PositionHistoryOut,
    SourceOut,
)
from app.schemas.matters import FindingOut, ObligationOut
from app.services import sequences

MESSAGE_NOT_FOUND = "That message was not found."

router = APIRouter(prefix="/ai", tags=["ai"])


def _call(capability_code: str, **kwargs) -> CapabilityCall:
    spec = REGISTRY[capability_code]
    return CapabilityCall(
        capability_code=capability_code,
        system=spec["system"],
        output_schema=spec["schema"],
        schema_name=spec["schema_name"],
        substantive=spec["substantive"],
        **kwargs,
    )


def _house_style(db, counterparty=None):
    """Load the configured house style, and treat the counterparty legal name as
    a party that earns its short form after the first mention."""
    from app.db.models.organisation import ConfigSetting
    from app.services.style import HouseStyle

    values: dict = {}
    for row in db.execute(
        select(ConfigSetting).where(
            ConfigSetting.area == "house_style", ConfigSetting.active.is_(True)
        )
    ).scalars():
        values[row.key] = (
            row.value.get("value", row.value) if isinstance(row.value, dict) else row.value
        )

    style = HouseStyle.from_config(values)
    if counterparty is not None and counterparty.trading_names:
        style.party_short_names = {
            **style.party_short_names,
            counterparty.legal_name: counterparty.trading_names[0],
        }
    return style


@router.post("/ask")
def ask(payload: AskRequest, db: Db, principal: CurrentUser, entity: WorkingEntity) -> AnswerOut:
    """A cited answer over the library, agreements and decision records, M10.

    Any statement without a citation is suppressed rather than shown. Retrieval
    filters by entity, role and matter access before ranking, so a restricted
    record never enters the candidate set.
    """
    principal.require_role(
        Role.LEGAL_OPS, Role.COUNSEL, Role.HEAD_OF_LEGAL, Role.PRIVACY, Role.ADMIN
    )

    chunks = retrieval.retrieve(
        db,
        payload.question,
        entity,
        source_types=payload.source_types or None,
        matter_id=payload.matter_id,
        limit=8,
    )

    if not chunks:
        return AnswerOut(
            interaction_id="",
            question=payload.question,
            refused=True,
            refusal_reason=(
                "No record you are able to open supports an answer to that question. "
                "Where a restricted matter is in scope, no title, snippet or citation "
                "from it can appear here, and the attempt is logged."
            ),
            note=(
                "Retrieval filters by entity, role and matter access before ranking, so "
                "records outside your access never enter the candidate set."
            ),
        )

    envelope = invoke(
        db,
        _call(
            "clause_retrieval_answer",
            entity=entity,
            data_class=DataClass.CONFIDENTIAL,
            user_content=f"Question: {payload.question}",
            context=chunks,
            matter_id=payload.matter_id,
            user_id=uuid.UUID(principal.user_id),
            input_summary=payload.question[:200],
        ),
    )

    if envelope.refused:
        return AnswerOut(
            interaction_id=envelope.interaction_id,
            question=payload.question,
            refused=True,
            refusal_reason=envelope.refusal_reason,
        )

    return AnswerOut(
        interaction_id=envelope.interaction_id,
        question=payload.question,
        paragraphs=[
            AnswerParagraph(text=p.get("text", ""), cites=p.get("cites", []))
            for p in envelope.output.get("paragraphs", [])
        ],
        sources=[SourceOut(**s.model_dump(include={"reference", "kind", "detail", "quote"}))
                 for s in envelope.sources],
        note=envelope.output.get("note"),
        suppressed_statements=int(envelope.output.get("suppressed_statements", 0)),
    )


@router.get("/positions/{category}")
def position_history(
    category: str, db: Db, principal: CurrentUser, entity: WorkingEntity
) -> PositionHistoryOut:
    """The current house position, its fallbacks and every recorded deviation."""
    principal.require_role(Role.LEGAL_OPS, Role.COUNSEL, Role.HEAD_OF_LEGAL, Role.ADMIN)

    clause = db.execute(
        select(Clause).where(Clause.category == category.upper())
    ).scalar_one_or_none()
    if clause is None:
        raise NotFound("That clause category was not found.")

    current = max(
        (v for v in clause.versions if v.status == VersionStatus.APPROVED.value),
        key=lambda v: (v.major, v.minor),
        default=None,
    )
    if current is None:
        raise NotFound("No approved version of that clause exists.")

    deviations: list[PositionHistoryEntry] = []
    for record in db.execute(
        select(DecisionRecord)
        .where(DecisionRecord.entity == entity)
        .order_by(DecisionRecord.decided_at.desc())
    ).scalars():
        if not any(category.upper() in ref.upper() for ref in record.clause_references or []):
            continue
        matter = db.get(Matter, record.matter_id) if record.matter_id else None
        counterparty = (
            db.get(Counterparty, record.counterparty_id) if record.counterparty_id else None
        )
        deviations.append(
            PositionHistoryEntry(
                matter_number=matter.number if matter else None,
                counterparty=counterparty.legal_name if counterparty else None,
                position_taken=record.decision,
                outcome=record.reason,
                authority=record.authority_level,
                decided_at=record.decided_at,
            )
        )

    return PositionHistoryOut(
        clause_category=clause.category,
        house_position=current.house_position,
        fallbacks=current.fallbacks or [],
        unacceptable_position=current.unacceptable_position,
        deviations=deviations,
    )


@router.get("/inbox", response_model=list[CommunicationOut])
def inbox(
    db: Db,
    principal: CurrentUser,
    entity: WorkingEntity,
    view: str = Query(default="action", pattern="^(action|watch|handled)$"),
) -> list[CommunicationOut]:
    """The action queue and the implied-work watch view are separate."""
    principal.require_role(Role.LEGAL_OPS, Role.COUNSEL, Role.HEAD_OF_LEGAL, Role.ADMIN)

    stmt = select(Communication).where(Communication.entity == entity)
    if view == "action":
        stmt = stmt.where(
            Communication.handled.is_(False), Communication.implied_work.is_(False)
        )
    elif view == "watch":
        stmt = stmt.where(
            Communication.handled.is_(False), Communication.implied_work.is_(True)
        )
    else:
        stmt = stmt.where(Communication.handled.is_(True))

    out = []
    for record in db.execute(stmt.order_by(Communication.received_at.desc()).limit(200)).scalars():
        model = CommunicationOut.model_validate(record)
        model.age_days = (datetime.now(UTC) - record.received_at).days
        out.append(model)
    return out


@router.post("/classify/{communication_id}")
def classify(
    communication_id: uuid.UUID, db: Db, principal: CurrentUser
) -> CommunicationOut:
    """Classify one message and propose a next step, M09.

    Nothing is sent and no matter is created until Legal confirms.
    """
    principal.require_role(Role.LEGAL_OPS, Role.COUNSEL, Role.HEAD_OF_LEGAL, Role.ADMIN)

    record = db.get(Communication, communication_id)
    if record is None:
        raise NotFound(MESSAGE_NOT_FOUND)

    envelope = invoke(
        db,
        _call(
            "inbox_classification",
            entity=record.entity,
            data_class=DataClass.CONFIDENTIAL,
            user_content=(
                "Classify this message and propose a next step for a person to confirm."
            ),
            untrusted=[(f"email from {record.sender}", f"{record.subject}\n\n{record.body}")],
            user_id=uuid.UUID(principal.user_id),
            input_summary=record.subject[:200],
        ),
    )

    injection = next(
        (c for c in envelope.checks if c.name == "prompt_injection" and not c.passed), None
    )
    if injection:
        record.injection_flagged = True
        record.quarantined = True
        audit.record(
            db,
            action="prompt_injection_detected",
            object_type="communication",
            object_id=str(record.id),
            actor_label="ai gateway",
            entity=record.entity,
            result="failure",
            detail=", ".join(injection.items),
        )

    record.classification_interaction_id = envelope.interaction_id
    if not envelope.refused:
        output = envelope.output
        record.classification = output.get("classification")
        record.classification_confidence = output.get("confidence")
        record.implied_work = bool(output.get("implied_work"))
        record.implied_work_phrase = output.get("implied_work_phrase")
        record.proposed_acknowledgment = output.get("acknowledgment_draft")
        record.proposed_matter_type = output.get("proposed_matter_type")
        record.proposed_priority = output.get("proposed_priority")

    model = CommunicationOut.model_validate(record)
    model.age_days = (datetime.now(UTC) - record.received_at).days
    return model


@router.post("/extract/{communication_id}")
def extract(
    communication_id: uuid.UUID, db: Db, principal: CurrentUser
) -> list[dict]:
    """Pull the facts out, each with the sentence it came from."""
    principal.require_role(Role.LEGAL_OPS, Role.COUNSEL, Role.HEAD_OF_LEGAL, Role.ADMIN)

    record = db.get(Communication, communication_id)
    if record is None:
        raise NotFound(MESSAGE_NOT_FOUND)

    envelope = invoke(
        db,
        _call(
            "fact_extraction",
            entity=record.entity,
            data_class=DataClass.CONFIDENTIAL,
            user_content="Extract the facts present in this message.",
            untrusted=[(f"email from {record.sender}", f"{record.subject}\n\n{record.body}")],
            user_id=uuid.UUID(principal.user_id),
            input_summary=record.subject[:200],
        ),
    )
    if envelope.refused:
        raise Refused("Extraction did not run.", [envelope.refusal_reason or ""])

    created = []
    for item in envelope.output.get("values", []):
        value = ExtractedValue(
            communication_id=record.id,
            field_name=item.get("field_name", "party"),
            value=item.get("value", ""),
            source_sentence=item.get("source_sentence", ""),
            confidence=item.get("confidence"),
        )
        db.add(value)
        created.append(
            {
                "field_name": value.field_name,
                "value": value.value,
                "source_sentence": value.source_sentence,
                "confidence": value.confidence,
                "interaction_id": envelope.interaction_id,
            }
        )
    return created


@router.post("/extracted/{value_id}/decision")
def decide_extracted(
    value_id: uuid.UUID, payload: ExtractionDecision, db: Db, principal: CurrentUser
) -> Ack:
    value = db.get(ExtractedValue, value_id)
    if value is None:
        raise NotFound("That extracted value was not found.")

    value.decision = payload.decision
    value.corrected_value = payload.corrected_value
    value.decided_by_id = uuid.UUID(principal.user_id)
    value.decided_at = datetime.now(UTC)
    return Ack(message=f"{value.field_name} recorded as {payload.decision}.")


@router.post("/inbox/{communication_id}/correct")
def correct_classification(
    communication_id: uuid.UUID,
    payload: CorrectClassification,
    db: Db,
    principal: CurrentUser,
) -> Ack:
    """Corrections feed the evaluation set (LOP-M09-US-02)."""
    record = db.get(Communication, communication_id)
    if record is None:
        raise NotFound(MESSAGE_NOT_FOUND)

    record.classification_corrected = True
    record.corrected_classification = CommunicationClass(payload.classification).value
    if record.classification_interaction_id:
        record_human_decision(
            db,
            record.classification_interaction_id,
            "edited",
            uuid.UUID(principal.user_id),
            f"Reclassified as {payload.classification}. {payload.reason or ''}".strip(),
        )
    return Ack(
        message="Correction recorded and added to the evaluation candidates."
    )


@router.post("/inbox/{communication_id}/confirm", status_code=201)
def confirm_from_inbox(
    communication_id: uuid.UUID,
    payload: ConfirmFromInbox,
    db: Db,
    principal: CurrentUser,
) -> dict:
    """Create a matter from correspondence, once a person confirms it."""
    principal.require_role(Role.LEGAL_OPS, Role.COUNSEL, Role.HEAD_OF_LEGAL, Role.ADMIN)

    record = db.get(Communication, communication_id)
    if record is None:
        raise NotFound(MESSAGE_NOT_FOUND)
    if record.matter_id:
        raise Conflict("This message is already linked to a matter.")

    from app.db.models.intake import RequestType

    request_type = db.execute(
        select(RequestType).where(RequestType.code == payload.request_type_code)
    ).scalar_one_or_none()
    if request_type is None:
        raise NotFound("That request type is not available.")

    now = datetime.now(UTC)
    matter = Matter(
        number=sequences.new_matter_number(db, payload.entity, request_type.practice_code),
        entity=payload.entity,
        request_type_id=request_type.id,
        practice_code=request_type.practice_code,
        title=payload.subject or record.subject,
        responsible_lawyer_id=payload.owner_id,
        priority=payload.priority,
        risk_tier=RiskTier.TIER_2.value,
        tier_rationale=["Created from correspondence, tier to be confirmed at triage."],
        status=MatterState.ACCEPTED.value,
        next_action="Confirm tier and owner",
        sla_target_hours=request_type.sla_hours,
        sla_started_at=now,
    )
    db.add(matter)
    db.flush()

    from app.db.models.matter import MatterTransition

    db.add(
        MatterTransition(
            matter_id=matter.id,
            to_state=MatterState.ACCEPTED.value,
            actor_id=uuid.UUID(principal.user_id),
            occurred_at=now,
        )
    )

    record.matter_id = matter.id
    record.handled = True

    if record.classification_interaction_id:
        record_human_decision(
            db,
            record.classification_interaction_id,
            "accepted",
            uuid.UUID(principal.user_id),
        )

    queued = False
    if payload.send_acknowledgment and record.proposed_acknowledgment:
        from app.services import notifications

        notifications.notify(
            db,
            connector_code="mail_administrative",
            recipients=[record.sender],
            subject=f"Re: {record.subject}",
            body=record.proposed_acknowledgment,
            record_reference=matter.number,
            matter_id=matter.id,
        )
        queued = True

    audit.record(
        db,
        action="matter_created_from_correspondence",
        object_type="matter",
        object_id=matter.number,
        actor_id=principal.user_id,
        actor_label=principal.name,
        entity=matter.entity,
        after_state={"communication": str(record.id), "acknowledgment_queued": queued},
    )
    return {
        "matter_number": matter.number,
        "matter_id": str(matter.id),
        "acknowledgment_queued": queued,
        "message": (
            "Matter created from correspondence. "
            + (
                "The administrative acknowledgment is queued for your send."
                if queued
                else "No acknowledgment was sent."
            )
        ),
    }


@router.post("/draft/{matter_id}", status_code=201)
def first_draft(
    matter_id: uuid.UUID, brief: str, db: Db, principal: CurrentUser
) -> dict:
    """A grounded first draft for a bespoke agreement, M05."""
    principal.require_role(Role.COUNSEL, Role.HEAD_OF_LEGAL, Role.ADMIN)

    matter = db.get(Matter, matter_id)
    if matter is None:
        raise NotFound("That matter was not found.")

    agreement_type = None
    if matter.request_type_id:
        from app.db.models.intake import RequestType

        request_type = db.get(RequestType, matter.request_type_id)
        if request_type:
            agreement_type = request_type.agreement_type
            if not request_type.drafting_enabled:
                raise Refused(
                    "Drafting is not enabled for this agreement type.",
                    [
                        "Availability is configurable per request type and tier, and this "
                        "type is switched off."
                    ],
                )

    chunks = retrieval.retrieve(
        db,
        f"{matter.title} {brief}",
        matter.entity,
        source_types=["clause", "template", "contract", "decision", "playbook"],
        limit=12,
    )

    counterparty = (
        db.get(Counterparty, matter.counterparty_id) if matter.counterparty_id else None
    )

    envelope = invoke(
        db,
        _call(
            "ai_first_draft",
            entity=matter.entity,
            data_class=DataClass(matter.classification),
            user_content=(
                f"Matter {matter.number}, {matter.title}.\n"
                f"Counterparty: {counterparty.legal_name if counterparty else 'not recorded'}.\n"
                f"Agreement type: {agreement_type or 'not recorded'}.\n\n"
                f"Brief from counsel:\n{brief}"
            ),
            context=chunks,
            matter_id=matter.id,
            user_id=uuid.UUID(principal.user_id),
            risk_tier=RiskTier(matter.risk_tier),
            agreement_type=agreement_type,
            input_summary=brief[:200],
        ),
    )
    if envelope.refused:
        raise Refused("No draft was produced.", [envelope.refusal_reason or ""])

    from app.services.checks import Clause as CheckClause
    from app.services.checks import run_all
    from app.services.hashing import content_hash
    from app.services.style import enforce

    clauses = envelope.output.get("clauses", [])
    checks = run_all(
        [
            CheckClause(
                number=c.get("number", ""), heading=c.get("heading", ""), text=c.get("text", "")
            )
            for c in clauses
        ],
        [counterparty.legal_name] if counterparty else None,
    )

    blocks = [
        {
            "key": f"b{index}",
            "number": c.get("number", str(index)),
            "heading": c.get("heading", ""),
            "text": c.get("text", ""),
            "provenance": c.get("provenance", "novel"),
            "source_reference": c.get("source_reference") or None,
            "novel": c.get("provenance") == "novel",
        }
        for index, c in enumerate(clauses, start=1)
    ]

    blocks, style_report = enforce(blocks, _house_style(db, counterparty))

    open_items = list(envelope.output.get("open_items", []))
    open_items.extend(
        f"{check.name.replace('_', ' ')}: {item}"
        for check in checks
        if not check.passed
        for item in check.items
    )

    document = Document(
        matter_id=matter.id,
        entity=matter.entity,
        name=envelope.output.get("title") or f"First draft, {matter.title}",
        document_type=DocumentType.DRAFT.value,
        version=1
        + len(list(db.execute(select(Document).where(Document.matter_id == matter.id)).scalars())),
        clause_versions=[
            b["source_reference"] for b in blocks if b["source_reference"]
        ],
        blocks=blocks,
        content_hash=content_hash(blocks),
        classification=matter.classification,
        generated_by_id=uuid.UUID(principal.user_id),
        generated_at=datetime.now(UTC),
        novel_clause_count=sum(1 for b in blocks if b["novel"]),
        open_items=open_items,
        style_report=style_report,
        consistency_checks=[c.as_dict() for c in checks],
    )
    db.add(document)
    db.flush()

    matter.status = MatterState.DRAFTING.value

    return {
        "document_id": str(document.id),
        "interaction_id": envelope.interaction_id,
        "novel_clause_count": document.novel_clause_count,
        "open_items": open_items,
        "style_report": style_report,
        "prior_positions": envelope.output.get("prior_positions", []),
        "sources": [s.model_dump() for s in envelope.sources],
        "checks": [c.as_dict() for c in checks],
        "requires_human": True,
        "required_role": envelope.required_role,
    }


@router.post("/review/{matter_id}", response_model=list[FindingOut], status_code=201)
def review_counterparty_paper(
    matter_id: uuid.UUID,
    document_id: uuid.UUID,
    db: Db,
    principal: CurrentUser,
) -> list[ReviewFinding]:
    """Compare counterparty paper to the playbook and rank the difference, M06."""
    principal.require_role(Role.LEGAL_OPS, Role.COUNSEL, Role.HEAD_OF_LEGAL, Role.ADMIN)

    matter = db.get(Matter, matter_id)
    document = db.get(Document, document_id)
    if matter is None or document is None:
        raise NotFound("That matter or document was not found.")

    agreement_type = None
    if matter.request_type_id:
        from app.db.models.intake import RequestType

        request_type = db.get(RequestType, matter.request_type_id)
        agreement_type = request_type.agreement_type if request_type else None

    playbook = db.execute(
        select(Playbook).where(Playbook.agreement_type == agreement_type)
    ).scalar_one_or_none()
    if playbook is None:
        raise Refused(
            "This draft cannot be reviewed.",
            [
                "No playbook is published for this agreement type. Severity ranking is "
                "meaningless without house positions and fallbacks."
            ],
        )

    chunks = retrieval.retrieve(
        db,
        f"{agreement_type} liability confidentiality data protection termination governing law",
        matter.entity,
        source_types=["clause", "playbook"],
        limit=14,
    )

    their_text = "\n\n".join(
        f"{b.get('number', '')} {b.get('heading', '')}\n{b.get('text', '')}"
        for b in document.blocks
    )

    required = "\n".join(
        f"- {c.get('category')}: {c.get('name')}, absent severity {c.get('absent_severity')}"
        for c in playbook.required_clauses
    )

    envelope = invoke(
        db,
        _call(
            "deviation_detection",
            entity=matter.entity,
            data_class=DataClass(matter.classification),
            user_content=(
                f"Playbook for {agreement_type}, version {playbook.version}.\n"
                f"Clauses this playbook requires:\n{required}\n\n"
                "Compare the counterparty draft below against the approved clauses in the "
                "retrieved material, and report both altered terms and required clauses "
                "that are absent."
            ),
            untrusted=[("counterparty draft", their_text)],
            context=chunks,
            matter_id=matter.id,
            user_id=uuid.UUID(principal.user_id),
            risk_tier=RiskTier(matter.risk_tier),
            agreement_type=agreement_type,
            input_summary=f"Review of {document.name}",
        ),
    )
    if envelope.refused:
        raise Refused("No review was produced.", [envelope.refusal_reason or ""])

    authority_by_rank = {
        1: "fallback_1",
        2: "fallback_2",
        3: "fallback_3",
    }

    created: list[ReviewFinding] = []
    for index, item in enumerate(envelope.output.get("findings", []), start=1):
        severity = Severity(item.get("severity", "material"))
        rank = int(item.get("fallback_rank") or 0)
        fallback_authority = "outside" if severity is Severity.CRITICAL else "fallback_1"
        authority = authority_by_rank.get(rank, fallback_authority)

        finding = ReviewFinding(
            matter_id=matter.id,
            document_id=document.id,
            sequence=index,
            title=item.get("title", "Finding"),
            their_reference=item.get("their_reference"),
            clause_absent=bool(item.get("clause_absent")),
            severity=severity.value,
            clause_category=item.get("clause_category"),
            clause_version_ref=item.get("clause_version_ref"),
            their_text=item.get("their_text"),
            house_position=item.get("house_position"),
            suggested_redline=item.get("suggested_redline"),
            required_authority=authority,
            matches_preapproved_fallback=bool(item.get("matches_preapproved_fallback")),
            interaction_id=envelope.interaction_id,
        )
        db.add(finding)
        created.append(finding)

    matter.status = MatterState.IN_REVIEW.value
    matter.next_action = f"{len(created)} findings to clear"
    db.flush()
    return created


@router.post("/extract-obligations/{contract_id}", status_code=201)
def extract_obligations(
    contract_id: uuid.UUID, db: Db, principal: CurrentUser
) -> list[ObligationOut]:
    """Propose obligations from the executed agreement, for confirmation."""
    principal.require_role(Role.LEGAL_OPS, Role.COUNSEL, Role.HEAD_OF_LEGAL, Role.ADMIN)

    contract = db.get(Contract, contract_id)
    if contract is None:
        raise NotFound("That contract was not found.")
    if not contract.authoritative:
        raise Refused(
            "Obligations cannot be extracted from this record.",
            [
                "Obligations derive from the executed version, not a draft. This contract "
                "is not the authoritative executed record."
            ],
        )

    document = (
        db.get(Document, contract.executed_document_id)
        if contract.executed_document_id
        else None
    )
    if document is None:
        raise NotFound("The executed copy for that contract was not found.")

    text = "\n\n".join(
        f"{b.get('number', '')} {b.get('heading', '')}\n{b.get('text', '')}"
        for b in document.blocks
    )
    chunks = retrieval.retrieve(
        db, "obligations renewal notice reporting payment", contract.entity, limit=6
    )

    envelope = invoke(
        db,
        _call(
            "obligation_extraction",
            entity=contract.entity,
            data_class=DataClass(document.classification),
            user_content=f"Executed agreement {contract.reference}. Propose its obligations.",
            untrusted=[("executed agreement", text)],
            context=chunks,
            matter_id=contract.matter_id,
            user_id=uuid.UUID(principal.user_id),
            input_summary=contract.reference,
        ),
    )
    if envelope.refused:
        raise Refused("No obligations were proposed.", [envelope.refusal_reason or ""])

    from datetime import date as date_type

    sequence = int(contract.reference.split("-")[-1])
    created: list[Obligation] = []

    for item in envelope.output.get("obligations", []):
        due = None
        raw_due = item.get("due_date") or ""
        if raw_due and not item.get("event_driven"):
            try:
                due = date_type.fromisoformat(raw_due)
            except ValueError:
                due = None

        obligation = Obligation(
            reference=sequences.new_obligation_reference(db, sequence),
            contract_id=contract.id,
            matter_id=contract.matter_id,
            entity=contract.entity,
            name=item.get("name", "Obligation"),
            description=item.get("description"),
            obligation_type=item.get("obligation_type", "deliverable"),
            source_clause=item.get("source_clause"),
            source_quote=item.get("source_quote"),
            due_date=due,
            recurrence=item.get("recurrence", "none"),
            status=ObligationStatus.PROPOSED.value,
            interaction_id=envelope.interaction_id,
            decision_options=["renew", "renegotiate", "terminate", "allow_to_lapse"]
            if item.get("obligation_type") == "renewal"
            else [],
        )
        db.add(obligation)
        created.append(obligation)

    db.flush()
    return [ObligationOut.model_validate(o) for o in created]


@router.post("/interactions/{interaction_id}/decision")
def decide_interaction(
    interaction_id: str,
    decision: str,
    db: Db,
    principal: CurrentUser,
    correction: str | None = None,
) -> Ack:
    record_human_decision(
        db, interaction_id, decision, uuid.UUID(principal.user_id), correction
    )
    return Ack(message=f"Recorded as {decision}.")
