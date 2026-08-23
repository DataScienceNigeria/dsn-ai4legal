"""Inbox, memory, assessment, compliance, counterparty and reporting shapes."""

from __future__ import annotations

from datetime import date, datetime
from typing import Any
from uuid import UUID

from pydantic import BaseModel, Field

from app.schemas.common import ApiModel


class ExtractedValueOut(ApiModel):
    id: UUID
    field_name: str
    value: str
    source_sentence: str
    confidence: float | None
    decision: str
    corrected_value: str | None


class CommunicationOut(ApiModel):
    id: UUID
    entity: str
    sender: str
    subject: str
    body: str
    received_at: datetime
    classification: str | None
    classification_confidence: float | None
    classification_corrected: bool
    corrected_classification: str | None
    implied_work: bool
    implied_work_phrase: str | None
    awaiting_response_since: datetime | None
    matter_id: UUID | None
    proposed_acknowledgment: str | None
    proposed_matter_type: str | None
    proposed_priority: str | None
    proposed_owner_id: UUID | None
    handled: bool
    injection_flagged: bool
    quarantined: bool
    age_days: int = 0
    extracted_values: list[ExtractedValueOut] = Field(default_factory=list)


class ClassifyRequest(BaseModel):
    communication_id: UUID


class CorrectClassification(BaseModel):
    classification: str
    reason: str | None = None


class ExtractionDecision(BaseModel):
    decision: str
    corrected_value: str | None = None


class ConfirmFromInbox(BaseModel):
    request_type_code: str
    entity: str
    subject: str | None = None
    owner_id: UUID | None = None
    priority: str = "normal"
    send_acknowledgment: bool = False


class AskRequest(BaseModel):
    question: str
    matter_id: UUID | None = None
    source_types: list[str] = Field(default_factory=list)


class AnswerParagraph(BaseModel):
    text: str
    cites: list[str] = Field(default_factory=list)


class SourceOut(BaseModel):
    reference: str
    kind: str
    detail: str | None = None
    quote: str | None = None


class AnswerOut(BaseModel):
    interaction_id: str
    question: str
    paragraphs: list[AnswerParagraph] = Field(default_factory=list)
    sources: list[SourceOut] = Field(default_factory=list)
    note: str | None = None
    refused: bool = False
    refusal_reason: str | None = None
    suppressed_statements: int = 0


class NewConversation(BaseModel):
    """Opening a thread. The first question is optional: a person may want an
    empty thread to type into, and a thread with no turns is a real state."""

    question: str | None = None
    title: str | None = None
    matter_id: UUID | None = None


class ConversationMessage(BaseModel):
    question: str
    source_types: list[str] = Field(default_factory=list)


class RenameConversation(BaseModel):
    title: str


class ConversationTurnOut(BaseModel):
    id: UUID
    sequence: int
    question: str
    answer: AnswerOut | None = None
    created_at: datetime


class ConversationBrief(BaseModel):
    id: UUID
    entity: str
    title: str
    matter_id: UUID | None = None
    matter_number: str | None = None
    message_count: int
    last_message_at: datetime | None = None
    created_at: datetime


class ConversationOut(ConversationBrief):
    turns: list[ConversationTurnOut] = Field(default_factory=list)


class PositionHistoryEntry(BaseModel):
    matter_number: str | None
    counterparty: str | None
    position_taken: str
    outcome: str | None
    authority: str | None
    decided_at: datetime | None


class PositionHistoryOut(BaseModel):
    clause_category: str
    house_position: str
    fallbacks: list[dict]
    unacceptable_position: str | None
    deviations: list[PositionHistoryEntry]


class CounterpartyOut(ApiModel):
    id: UUID
    reference: str
    legal_name: str
    aliases: list[str]
    trading_names: list[str]
    counterparty_type: str
    registration_number: str | None
    domain: str | None
    jurisdiction: str
    relationship_class: str
    risk_class: str
    negotiation_notes: str | None


class CounterpartyCreate(BaseModel):
    legal_name: str
    counterparty_type: str = "company"
    registration_number: str | None = None
    domain: str | None = None
    jurisdiction: str = "Nigeria"
    relationship_class: str = "commercial"
    contacts: list[dict] = Field(default_factory=list)
    confirm_despite_duplicates: bool = False


class DuplicateWarning(BaseModel):
    id: UUID
    reference: str
    legal_name: str
    similarity: float
    matched_on: str


class CounterpartyCreateResult(BaseModel):
    created: CounterpartyOut | None = None
    duplicates: list[DuplicateWarning] = Field(default_factory=list)
    message: str


class MergeRequest(BaseModel):
    into_id: UUID
    reason: str


class VendorOut(ApiModel):
    id: UUID
    counterparty_id: UUID
    legal_name: str | None = None
    service_owner_id: UUID | None
    security_review_status: str
    security_review_date: date | None
    open_security_findings: int
    subprocessors: list[dict]
    hosting_locations: list[str]
    renewal_date: date | None
    spend_band: str | None
    performance_notes: str | None
    assessment_expired: bool


class AssessmentStageRecord(BaseModel):
    stage: str
    owner_id: UUID | None = None
    due_date: date | None = None
    status: str = "not_started"
    completed_at: datetime | None = None
    notes: str | None = None


class AssessmentOut(ApiModel):
    id: UUID
    reference: str
    assessment_type: str
    title: str
    entity: str
    stage: str
    stage_records: list[AssessmentStageRecord]
    captured: dict[str, Any]
    risks: list[dict]
    controls: list[dict]
    testing_evidence: list[dict]
    conditions: list[dict]
    residual_risk_decision: str | None
    residual_risk_reason: str | None
    residual_risk_owner_id: UUID | None
    approved_at: datetime | None
    review_date: date | None
    product_id: UUID | None
    vendor_id: UUID | None
    contract_id: UUID | None


class AssessmentCreate(BaseModel):
    assessment_type: str
    title: str
    entity: str
    product_id: UUID | None = None
    vendor_id: UUID | None = None
    matter_id: UUID | None = None
    contract_id: UUID | None = None
    captured: dict[str, Any] = Field(default_factory=dict)


class StageComplete(BaseModel):
    notes: str | None = None
    captured: dict[str, Any] = Field(default_factory=dict)


class AssessmentClose(BaseModel):
    residual_risk_decision: str
    residual_risk_reason: str
    residual_risk_owner_id: UUID
    review_date: date | None = None


class ComplianceItemOut(ApiModel):
    id: UUID
    entity: str
    requirement: str
    statutory_reference: str | None
    jurisdiction: str
    filing_date: date | None
    recurrence: str
    accountable_owner_id: UUID | None
    evidence_required: bool
    evidence_reference: str | None
    filing_number: str | None
    next_due_date: date | None
    lead_time_days: int
    version: int
    effective_date: date | None
    status: str


class ComplianceCompletion(BaseModel):
    evidence_reference: str | None = None
    filing_number: str | None = None
    filed_on: date | None = None


class CapabilityOut(ApiModel):
    id: UUID
    code: str
    name: str
    module: str
    purpose: str
    max_data_class: str
    tier_ceiling: str
    human_requirement: str
    confirming_role: str
    state: str
    disabled_reason: str | None
    disabled_for_types: list[str]
    metric_name: str
    gate_expression: str
    gate_threshold: float | None
    last_score: float | None
    last_score_label: str | None
    last_evaluated_at: datetime | None
    golden_set: str | None
    passes_gate: bool = False


class GoldenCaseCreate(BaseModel):
    reference: str
    prompt: str
    context: list[dict] = Field(default_factory=list)
    expected: dict = Field(default_factory=dict)
    notes: str | None = None
    source: str | None = None


class GoldenCaseOut(ApiModel):
    id: UUID
    reference: str
    prompt: str
    context: list[dict]
    expected: dict
    notes: str | None
    source: str | None
    active: bool


class GoldenSetCreate(BaseModel):
    name: str
    description: str | None = None


class GoldenSetOut(BaseModel):
    id: UUID
    name: str
    version: int
    capability_code: str
    description: str | None
    active: bool
    cases: list[GoldenCaseOut] = Field(default_factory=list)


class EvaluationRunOut(ApiModel):
    id: UUID
    golden_set: str
    set_size: int
    score: float
    score_label: str | None
    threshold: float
    passed: bool
    detail: dict
    run_at: datetime


class CapabilityToggle(BaseModel):
    state: str
    reason: str
    agreement_type: str | None = None


class AIInteractionOut(ApiModel):
    id: UUID
    interaction_id: str
    capability_code: str
    entity: str
    matter_id: UUID | None
    data_class: str
    provider: str
    model: str
    input_tokens: int
    output_tokens: int
    cost_usd: float
    latency_ms: int
    human_decision: str
    shadow: bool
    injection_detected: bool
    refused: bool
    refusal_reason: str | None
    created_at: datetime
    retrieved_sources: list[dict]


class KpiRow(BaseModel):
    code: str
    name: str
    unit: str
    measurement_method: str
    baseline: float | None
    current: float | None
    phase_1_target: float | None
    phase_3_target: float | None
    direction: str
    on_track: bool | None = None


class AgeingBucket(BaseModel):
    label: str
    count: int


class OwnerLoad(BaseModel):
    owner_id: UUID | None
    owner_name: str
    open_matters: int
    breached: int


class OperationalReport(BaseModel):
    generated_at: datetime
    entity: str
    open_matters: int
    by_tier: dict[str, int]
    by_status: dict[str, int]
    ageing: list[AgeingBucket]
    sla_breaches: int
    near_breaches: int
    blocked: int
    by_owner: list[OwnerLoad]
    turnaround_median_hours: float | None
    obligations_overdue: int
    reviews_overdue: int


class AiQualityRow(BaseModel):
    capability: str
    state: str
    calls: int
    accepted: int
    edited: int
    rejected: int
    correction_rate: float | None
    cost_usd: float
    median_latency_ms: int | None
    gate_threshold: float | None
    last_score: float | None
    disabled_reason: str | None


class WeeklyUpdate(BaseModel):
    generated_at: datetime
    entity: str
    period_start: date
    period_end: date
    delivery: list[str]
    volumes: list[str]
    turnaround: list[str]
    blockers: list[str]
    next_actions: list[str]


class ComplianceVersion(BaseModel):
    effective_date: date
    requirement: str | None = None
    statutory_reference: str | None = None
    filing_date: date | None = None
    recurrence: str | None = None
    accountable_owner_id: UUID | None = None
    evidence_required: bool | None = None
    next_due_date: date | None = None
    lead_time_days: int | None = None


class LegalHoldRequest(BaseModel):
    hold: bool
    reason: str | None = None


class DeletionRequestCreate(BaseModel):
    record_class: str
    object_type: str
    object_reference: str
    reason: str


class ExportRequestCreate(BaseModel):
    record_class: str
    reason: str
    data_classes: list[str] = Field(default_factory=list)
    scope: dict = Field(default_factory=dict)


class SecondApproval(BaseModel):
    approve: bool
    reason: str | None = None


class MfaReset(BaseModel):
    """Clearing someone else's second factor. The reason is not optional."""

    reason: str

