"""Shared response shapes."""

from __future__ import annotations

from datetime import date, datetime
from typing import Any
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
    id: UUID
    occurred_at: datetime
    actor_label: str
    entity: str | None
    object_type: str
    object_id: str | None
    action: str
    result: str
    detail: str | None


class DateRange(BaseModel):
    start: date | None = None
    end: date | None = None


class ProblemDetail(BaseModel):
    code: str
    message: str
    field_errors: dict[str, str] = Field(default_factory=dict)
    reasons: list[str] = Field(default_factory=list)


class ConfigValue(BaseModel):
    area: str
    key: str
    value: Any
    version: int
    description: str | None = None
