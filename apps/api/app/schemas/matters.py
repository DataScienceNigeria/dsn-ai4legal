"""Matter, library, document and contract shapes."""

from __future__ import annotations

from datetime import date, datetime
from typing import Any
from uuid import UUID

from pydantic import BaseModel, Field

from app.schemas.common import ApiModel, CounterpartyBrief


class SlaOut(BaseModel):
    target_hours: int | None
    elapsed_hours: float
    running: bool
    breached: bool
    near_breach: bool
    remaining_hours: float | None


class MatterListItem(ApiModel):
    id: UUID
    number: str
    entity: str
    title: str
    practice_code: str
    risk_tier: str
    status: str
    next_action: str | None
    due_date: date | None
    blocker: str | None
    privacy_flag: bool
    restricted: bool
    responsible_lawyer_id: UUID | None
    counterparty: CounterpartyBrief | None = None
    days_open: int = 0
    sla: SlaOut | None = None


class MatterOut(MatterListItem):
    request_id: UUID | None
    requester_id: UUID | None
    business_owner_id: UUID | None
    classification: str
    tier_rationale: list[str]
    tier_overridden: bool
    tier_override_reason: str | None
    value_amount: float | None
    value_currency: str
    state_before_hold: str | None
    permitted_transitions: list[str] = Field(default_factory=list)
    created_at: datetime


class MatterUpdate(BaseModel):
    priority: str | None = None
    next_action: str | None = None
    due_date: date | None = None
    blocker: str | None = None
    business_owner_id: UUID | None = None


class ReassignRequest(BaseModel):
    owner_id: UUID
    reason: str


class TierOverride(BaseModel):
    tier: str
    reason: str


class RestrictRequest(BaseModel):
    restricted: bool
    reason: str
    named_users: list[UUID] = Field(default_factory=list)


class LinkRequest(BaseModel):
    linked_matter_id: UUID
    link_type: str = "related"


class FallbackPosition(BaseModel):
    rank: int
    text: str
    required_authority: str
    conditions: str | None = None


class ClauseVersionOut(ApiModel):
    id: UUID
    reference: str
    major: int
    minor: int
    status: str
    house_position: str
    fallbacks: list[FallbackPosition]
    unacceptable_position: str | None
    usage_conditions: str | None
    risk_notes: str | None
    approval_date: date | None
    effective_date: date | None
    review_date: date | None


class ClauseOut(ApiModel):
    id: UUID
    category: str
    name: str
    owner_id: UUID | None
    entity_applicability: list[str]
    jurisdiction: str
    required_for_types: list[str]
    current: ClauseVersionOut | None = None
    versions: list[ClauseVersionOut] = Field(default_factory=list)


class TemplateVariable(BaseModel):
    name: str
    label: str
    type: str = "string"
    mandatory: bool = True
    source_field: str | None = None
    pattern: str | None = None
    format: str | None = None
    default: Any = None


class TemplateVersionOut(ApiModel):
    id: UUID
    reference: str
    major: int
    minor: int
    status: str
    body: list[dict]
    variables: list[TemplateVariable]
    clause_references: list[str]
    approval_date: date | None
    effective_date: date | None
    review_date: date | None
    change_summary: str | None


class TemplateOut(ApiModel):
    id: UUID
    code: str
    name: str
    agreement_type: str
    owner_id: UUID | None
    entity_applicability: list[str]
    jurisdiction: str
    current: TemplateVersionOut | None = None
    versions: list[TemplateVersionOut] = Field(default_factory=list)


class VersionProposal(BaseModel):
    change_summary: str
    house_position: str | None = None
    fallbacks: list[FallbackPosition] | None = None
    unacceptable_position: str | None = None
    body: list[dict] | None = None
    variables: list[TemplateVariable] | None = None
    effective_date: date | None = None
    review_date: date | None = None


class VersionDiffLine(BaseModel):
    kind: str
    text: str


class VersionDiff(BaseModel):
    from_reference: str
    to_reference: str
    lines: list[VersionDiffLine]


class GenerateRequest(BaseModel):
    template_reference: str
    matter_id: UUID
    facts: dict[str, Any] = Field(default_factory=dict)
    name: str | None = None


class BlockOut(BaseModel):
    key: str
    number: str
    heading: str
    text: str
    provenance: str
    source_reference: str | None
    novel: bool


class CheckOut(BaseModel):
    name: str
    passed: bool
    detail: str
    items: list[str] = Field(default_factory=list)


class DocumentOut(ApiModel):
    id: UUID
    matter_id: UUID | None
    name: str
    document_type: str
    version: int
    template_version_ref: str | None
    clause_versions: list[str]
    content_hash: str
    classification: str
    immutable: bool
    novel_clause_count: int
    open_items: list[str]
    blocks: list[BlockOut]
    consistency_checks: list[CheckOut]
    generated_at: datetime | None


class ApprovalOut(ApiModel):
    id: UUID
    step_index: int
    step_name: str
    step_mode: str
    approver_id: UUID | None
    approver_role: str | None
    decision: str
    comments: str | None
    document_hash: str
    due_at: datetime | None
    decided_at: datetime | None
    invalidated_by_event: str | None
    actionable: bool = False


class ApprovalDecisionRequest(BaseModel):
    decision: str
    comments: str | None = None


class SignatureRequestCreate(BaseModel):
    document_id: UUID
    signers: list[dict] = Field(default_factory=list)


class SignatureOut(ApiModel):
    id: UUID
    document_id: UUID
    document_hash: str
    provider: str
    external_reference: str | None
    signers: list[dict]
    status: str
    completed_at: datetime | None


class WetInkExecution(BaseModel):
    document_id: UUID
    signature_date: date
    signatories: list[str]
    reason: str


class ContractOut(ApiModel):
    id: UUID
    reference: str
    matter_id: UUID
    entity: str
    agreement_type: str
    effective_date: date | None
    end_date: date | None
    renewal_type: str
    notice_period_days: int | None
    value_amount: float | None
    value_currency: str
    governing_law: str
    signature_status: str
    executed_at: datetime | None
    content_hash: str | None
    authoritative: bool
    executed_outside_platform: bool
    counterparty: CounterpartyBrief | None = None


class ObligationOut(ApiModel):
    id: UUID
    reference: str
    name: str
    description: str | None
    obligation_type: str
    source_clause: str | None
    source_quote: str | None
    owner_id: UUID | None
    due_date: date | None
    recurrence: str
    lead_time_days: int
    evidence_required: bool
    evidence_reference: str | None
    status: str
    completed_at: datetime | None
    decision_options: list[str]
    decision_taken: str | None
    contract_id: UUID | None
    days_until_due: int | None = None
    overdue: bool = False


class ObligationDecision(BaseModel):
    decision: str
    edited_name: str | None = None
    edited_due_date: date | None = None
    owner_id: UUID | None = None
    reason: str | None = None


class ObligationCompletion(BaseModel):
    evidence_reference: str | None = None
    evidence_note: str | None = None
    decision_taken: str | None = None


class FindingOut(ApiModel):
    id: UUID
    sequence: int
    title: str
    their_reference: str | None
    clause_absent: bool
    severity: str
    clause_category: str | None
    clause_version_ref: str | None
    their_text: str | None
    house_position: str | None
    suggested_redline: str | None
    required_authority: str
    matches_preapproved_fallback: bool
    decision: str
    decided_at: datetime | None
    clearance_rule: str | None


class FindingDecision(BaseModel):
    decision: str
    edited_text: str | None = None
    reason: str | None = None


class ImportCandidateAcceptance(BaseModel):
    index: int
    category: str | None = None
    text: str | None = None


class ImportAcceptance(BaseModel):
    accepted: list[ImportCandidateAcceptance] = Field(default_factory=list)
    rejected: list[int] = Field(default_factory=list)


class AutoIssueRequest(BaseModel):
    template_reference: str
    facts: dict = Field(default_factory=dict)
    signers: list[dict] = Field(default_factory=list)
    name: str | None = None
