"""Navigation counts and record lookup."""

from __future__ import annotations

from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field


class NavCounts(BaseModel):
    """Work outstanding behind each menu item, zero where there is none."""

    triage: int = 0
    matters: int = 0
    review: int = 0
    obligations: int = 0
    inbox: int = 0
    assessments: int = 0
    compliance: int = 0


class SearchHit(BaseModel):
    kind: str
    label: str
    reference: str
    detail: str | None = None
    href: str


class SearchResults(BaseModel):
    query: str
    hits: list[SearchHit] = Field(default_factory=list)
    searched_at: datetime


class NotificationOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    kind: str
    title: str
    body: str | None
    href: str | None
    reference: str | None
    created_at: datetime
    read_at: datetime | None


class NotificationPage(BaseModel):
    unread: int
    notifications: list[NotificationOut] = Field(default_factory=list)
