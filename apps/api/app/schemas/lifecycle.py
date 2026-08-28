"""What crosses the wire for the post-execution life of a contract."""

from __future__ import annotations

from datetime import date, datetime
from uuid import UUID

from pydantic import BaseModel, Field

from app.schemas.common import ApiModel

# ------------------------------------------------------------------- issues


class IssueCreate(BaseModel):
    issue_type: str
    severity: str
    title: str = Field(min_length=5, max_length=255)
    description: str = Field(min_length=20)
    occurred_on: date | None = None
    evidence_document_id: UUID | None = None
    evidence_note: str | None = None


class IssueTriage(BaseModel):
    """Legal picking it up: who owns it, and how bad it is on a second look."""

    assignee_id: UUID | None = None
    severity: str | None = None
    status: str | None = None


class IssueResolve(BaseModel):
    status: str
    resolution: str = Field(min_length=15)


class IssueOut(ApiModel):
    id: UUID
    entity: str
    reference: str
    contract_id: UUID
    issue_type: str
    severity: str
    title: str
    description: str
    occurred_on: date | None
    evidence_document_id: UUID | None
    evidence_note: str | None
    raised_by_name: str | None = None
    assignee_id: UUID | None
    assignee_name: str | None = None
    status: str
    resolution: str | None
    resolved_at: datetime | None
    change_request_id: UUID | None
    settled: bool = False
    created_at: datetime

    contract_reference: str | None = None
    counterparty_name: str | None = None


# ----------------------------------------------------------- change requests


class ChangeRequestCreate(BaseModel):
    change_type: str
    rationale: str = Field(min_length=20)
    proposed_changes: str = Field(min_length=10)
    financial_effect: str | None = None
    value_delta: float | None = None
    value_currency: str | None = Field(default=None, max_length=3)
    financial_note: str | None = None
    timeline_effect: str | None = None
    proposed_end_date: date | None = None
    timeline_note: str | None = None


class ChangeDetermination(BaseModel):
    """Legal's answer: whether it proceeds, and which paper carries it."""

    decision: str
    instrument: str | None = None
    reason: str = Field(min_length=10)


class ChangeRequestOut(ApiModel):
    id: UUID
    entity: str
    reference: str
    contract_id: UUID
    change_type: str
    rationale: str
    proposed_changes: str
    financial_effect: str | None
    value_delta: float | None
    value_currency: str | None
    financial_note: str | None
    timeline_effect: str | None
    proposed_end_date: date | None
    timeline_note: str | None
    requested_by_name: str | None = None
    instrument: str | None
    decision: str
    decision_reason: str | None
    decided_at: datetime | None
    resulting_matter_id: UUID | None
    created_at: datetime

    contract_reference: str | None = None
    counterparty_name: str | None = None
    resulting_matter_number: str | None = None


# ------------------------------------------------------------------ closure


class ClosureItemOut(ApiModel):
    id: UUID
    item_key: str
    group_key: str
    status: str
    evidence_document_id: UUID | None
    evidence_reference: str | None
    note: str | None
    confirmed_by_name: str | None = None
    confirmed_at: datetime | None

    label: str = ""
    intent: str = ""
    evidence_required: bool = True
    may_not_apply: bool = True


class ClosureItemUpdate(BaseModel):
    status: str
    evidence_reference: str | None = None
    evidence_document_id: UUID | None = None
    note: str | None = None


class ClosureGroupOut(BaseModel):
    key: str
    title: str
    intent: str
    items: list[ClosureItemOut]


class ClosureOut(BaseModel):
    contract_id: UUID
    contract_reference: str
    status: str
    opened_at: datetime | None
    closed_at: datetime | None
    closure_note: str | None
    settled: int
    total: int
    blocking: list[str]
    groups: list[ClosureGroupOut]


class CloseRequest(BaseModel):
    status: str = "closed"
    note: str | None = None


# ------------------------------------------------------- the register itself


class RegisterUpdate(BaseModel):
    """Section 14. What the organisation needs to run an agreement it signed."""

    user_department: str | None = Field(default=None, max_length=128)
    contract_owner_id: UUID | None = None
    payment_terms: str | None = None
    key_deliverables: str | None = None
    milestones: list[dict] | None = None
    termination_deadline: date | None = None
    remarks: str | None = None
    status: str | None = None


class VocabularyOut(BaseModel):
    """One place the interface reads the words from, so it cannot invent its own."""

    agreement_types: list[dict]
    issue_types: list[dict]
    issue_statuses: list[dict]
    change_types: list[dict]
    instruments: list[dict]
    change_decisions: list[dict]
    contract_statuses: list[dict]
    closure_statuses: list[dict]
    severities: list[str]


# ------------------------------------------------------- the legal consultant


class ConsultantReviewRequest(BaseModel):
    """Legal asking external counsel to read a draft.

    The brief is required and has a floor. "Please review" is how a consultant
    bills for reading a whole agreement to answer a question about one clause,
    and it is also how the comments come back about the wrong thing.
    """

    consultant_id: UUID
    document_id: UUID | None = None
    brief: str = Field(min_length=25)
    due_date: date | None = None


class ConsultantComments(BaseModel):
    comments: str = Field(min_length=25)


class ConsultantAssessment(BaseModel):
    """What Legal did with the comments, which is the half that binds."""

    assessment: str = Field(min_length=20)


class ConsultantReviewOut(ApiModel):
    id: UUID
    entity: str
    matter_id: UUID
    document_id: UUID | None
    consultant_id: UUID
    consultant_name: str | None = None
    brief: str
    due_date: date | None
    status: str
    comments: str | None
    returned_at: datetime | None
    assessment: str | None
    assessed_at: datetime | None
    created_at: datetime

    matter_number: str | None = None
    matter_title: str | None = None
    document_name: str | None = None
