"""Request and intake shapes, M01."""

from __future__ import annotations

from datetime import date, datetime
from typing import Any
from uuid import UUID

from pydantic import BaseModel, Field

from app.schemas.common import ApiModel


class FieldDefinition(BaseModel):
    name: str
    label: str
    type: str = "string"
    help_text: str | None = None
    options: list[str] = Field(default_factory=list)
    mandatory: bool = False
    #: Shown only when this expression is true against the answers so far.
    condition: str | None = None
    progressive: bool = False
    pattern: str | None = None


class RequestTypeOut(ApiModel):
    id: UUID
    code: str
    business_label: str
    description: str | None
    agreement_type: str
    practice_code: str
    fields: list[FieldDefinition]
    mandatory_fields: list[str]
    sla_hours: int
    sort_order: int


class RequestCreate(BaseModel):
    request_type_code: str
    entity: str
    subject: str
    purpose: str | None = None
    proposed_counterparty: str | None = None
    counterparty_id: UUID | None = None
    required_date: date | None = None
    value_amount: float | None = None
    value_currency: str = "NGN"
    personal_data: bool = False
    special_category_data: bool = False
    third_party_confidential: bool = False
    leaves_nigeria: bool = False
    answers: dict[str, Any] = Field(default_factory=dict)


class AttachmentOut(ApiModel):
    id: UUID
    filename: str
    content_type: str
    size_bytes: int
    scan_status: str
    created_at: datetime


class RequestOut(ApiModel):
    id: UUID
    reference: str
    entity: str
    subject: str
    purpose: str | None
    status: str
    proposed_counterparty: str | None
    required_date: date | None
    value_amount: float | None
    value_currency: str
    privacy_flag: bool
    personal_data: bool
    special_category_data: bool
    leaves_nigeria: bool
    suggested_tier: str | None
    tier_rationale: list[str]
    suggested_owner_id: UUID | None
    owner_rationale: str | None
    acknowledged_at: datetime | None
    created_at: datetime
    answers: dict[str, Any]
    attachments: list[AttachmentOut] = Field(default_factory=list)


class TimelineEntry(BaseModel):
    stage: str
    label: str
    occurred_at: datetime | None
    current: bool = False
    owner_first_name: str | None = None


class RequestStatusOut(BaseModel):
    """What a requester sees. No other requester's data is visible."""

    reference: str
    subject: str
    status: str
    stage_label: str
    owner_first_name: str | None
    expected_date: date | None
    last_update: datetime
    matter_number: str | None
    timeline: list[TimelineEntry]


class TriageProposal(BaseModel):
    tier: str
    tier_rationale: list[str]
    tier_1_eligible: bool
    triggers_privacy_assessment: bool
    proposed_owner: UUID | None
    owner_rationale: str | None


class AcceptRequest(BaseModel):
    tier: str | None = None
    tier_change_reason: str | None = None
    owner_id: UUID | None = None
    practice_code: str | None = None
    priority: str = "normal"
    restricted: bool = False


class ReturnRequest(BaseModel):
    reason: str
    missing_information: list[str] = Field(default_factory=list)


class CloseRequest(BaseModel):
    reason: str
    answer: str | None = None
