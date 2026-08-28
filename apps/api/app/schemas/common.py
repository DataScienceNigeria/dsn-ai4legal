"""Shared response shapes."""

from __future__ import annotations

from datetime import date, datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field


class ApiModel(BaseModel):
    model_config = ConfigDict(from_attributes=True, populate_by_name=True)


class Page[T](BaseModel):
    items: list[T]
    total: int
    limit: int
    offset: int


class Ack(BaseModel):
    ok: bool = True
    message: str


class UserBrief(ApiModel):
    id: UUID
    name: str
    work_email: str
    roles: list[str] = Field(default_factory=list)


class CounterpartyBrief(ApiModel):
    id: UUID
    reference: str
    legal_name: str
    relationship_class: str


class TransitionRequest(BaseModel):
    to_state: str
    reason: str | None = None
    next_action: str | None = None


class DecisionRequest(BaseModel):
    decision: str
    reason: str
    alternatives_considered: str | None = None
    clause_references: list[str] = Field(default_factory=list)
    authority_level: str = "house"
    commercial_rationale: str | None = None
    residual_risk_accepted: bool = False
    counterparty_id: UUID | None = None


class DecisionOut(ApiModel):
    id: UUID
    sequence: int
    decision: str
    reason: str
    alternatives_considered: str | None
    clause_references: list[str]
    authority_level: str
    residual_risk_accepted: bool
    decided_at: datetime
    decided_by_id: UUID | None
    superseded_by_id: UUID | None


class AuditEventOut(ApiModel):
    """Everything the row holds.

    The trail stored the position in the chain, the before and after states,
    the address the act came from and the two digests since it was built, and
    showed six of fourteen columns. The eight it hid are the ones that answer
    what changed, from where, and whether the row can be trusted.
    """

    id: UUID
    sequence: int
    occurred_at: datetime
    actor_id: UUID | None
    actor_label: str
    entity: str | None
    object_type: str
    object_id: str | None
    action: str
    result: str
    detail: str | None
    before_state: dict | None
    after_state: dict | None
    ip_address: str | None
    session_id: str | None
    previous_digest: str | None
    digest: str


class DateRange(BaseModel):
    start: date | None = None
    end: date | None = None


class ProblemDetail(BaseModel):
    code: str
    message: str
    field_errors: dict[str, str] = Field(default_factory=dict)
    reasons: list[str] = Field(default_factory=list)

