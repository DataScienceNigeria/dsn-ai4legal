"""AI capability register and interaction log, PRD sections 13.2 and 16.3.

Every AI use in the platform is a named capability with an owner, a tier
ceiling, a permitted data class, a route and a gate. Nothing runs as an unnamed
model call.
"""

import uuid
from datetime import date, datetime

from sqlalchemy import Boolean, Date, DateTime, Float, ForeignKey, Integer, String, Text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.dialects.postgresql import UUID as PgUUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base, Timestamped, UUIDPrimaryKey
from app.domain.enums import CapabilityState, DataClass, HumanDecision


class Capability(UUIDPrimaryKey, Timestamped, Base):
    """One row of the capability register.

    A capability that falls below its threshold on the golden set is disabled
    until it passes again (PRD section 4.2). Disablement is instant, per
    capability and per agreement type, and needs no deployment.
    """

    __tablename__ = "capability"

    code: Mapped[str] = mapped_column(String(64), unique=True, nullable=False, index=True)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    module: Mapped[str] = mapped_column(String(8), nullable=False)
    purpose: Mapped[str] = mapped_column(Text, nullable=False)
    owner_id: Mapped[uuid.UUID | None] = mapped_column(
        PgUUID(as_uuid=True), ForeignKey("app_user.id", ondelete="SET NULL")
    )
    max_data_class: Mapped[str] = mapped_column(
        String(16), default=DataClass.CONFIDENTIAL.value, nullable=False
    )
    tier_ceiling: Mapped[str] = mapped_column(String(16), default="tier_3")
    human_requirement: Mapped[str] = mapped_column(Text, nullable=False)
    confirming_role: Mapped[str] = mapped_column(String(32), default="counsel")
    state: Mapped[str] = mapped_column(
        String(16), default=CapabilityState.SHADOW.value, nullable=False, index=True
    )
    disabled_reason: Mapped[str | None] = mapped_column(Text)
    disabled_for_types: Mapped[list[str]] = mapped_column(JSONB, default=list)

    metric_name: Mapped[str] = mapped_column(String(64), default="accuracy")
    gate_expression: Mapped[str] = mapped_column(String(128), default="")
    gate_threshold: Mapped[float | None] = mapped_column(Float)
    last_score: Mapped[float | None] = mapped_column(Float)
    last_score_label: Mapped[str | None] = mapped_column(String(64))
    last_evaluated_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    golden_set: Mapped[str | None] = mapped_column(String(64))

    prompt_reference: Mapped[str | None] = mapped_column(String(128))
    tools_allowed: Mapped[list[str]] = mapped_column(JSONB, default=list)

    evaluations: Mapped[list["EvaluationRun"]] = relationship(
        back_populates="capability", cascade="all, delete-orphan"
    )

    @property
    def passes_gate(self) -> bool:
        if self.gate_threshold is None or self.last_score is None:
            return False
        return self.last_score >= self.gate_threshold

class EvaluationRun(UUIDPrimaryKey, Timestamped, Base):
    """A run of a golden set against a capability, PRD section 16.1."""

    __tablename__ = "evaluation_run"

    capability_id: Mapped[uuid.UUID] = mapped_column(
        PgUUID(as_uuid=True), ForeignKey("capability.id", ondelete="CASCADE"), nullable=False
    )
    golden_set: Mapped[str] = mapped_column(String(64), nullable=False)
    set_size: Mapped[int] = mapped_column(Integer, default=0)
    score: Mapped[float] = mapped_column(Float, nullable=False)
    score_label: Mapped[str | None] = mapped_column(String(64))
    threshold: Mapped[float] = mapped_column(Float, nullable=False)
    passed: Mapped[bool] = mapped_column(Boolean, default=False)
    detail: Mapped[dict] = mapped_column(JSONB, default=dict)
    run_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)

    capability: Mapped[Capability] = relationship(back_populates="evaluations")

class AIInteraction(UUIDPrimaryKey, Timestamped, Base):
    """One model call and the human decision that followed it.

    Prompt, source, model route, user, time, output and final decision are all
    recorded (PRD section 3.2, log everything that matters).
    """

    __tablename__ = "ai_interaction"

    interaction_id: Mapped[str] = mapped_column(String(64), unique=True, nullable=False, index=True)
    capability_code: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    entity: Mapped[str] = mapped_column(String(3), nullable=False, index=True)
    matter_id: Mapped[uuid.UUID | None] = mapped_column(
        PgUUID(as_uuid=True), ForeignKey("matter.id", ondelete="SET NULL"), index=True
    )
    user_id: Mapped[uuid.UUID | None] = mapped_column(
        PgUUID(as_uuid=True), ForeignKey("app_user.id", ondelete="SET NULL")
    )
    prompt_reference: Mapped[str | None] = mapped_column(String(128))
    input_digest: Mapped[str] = mapped_column(String(64), nullable=False)
    input_summary: Mapped[str | None] = mapped_column(Text)
    data_class: Mapped[str] = mapped_column(String(16), nullable=False)
    retrieved_sources: Mapped[list[dict]] = mapped_column(JSONB, default=list)
    output_reference: Mapped[str | None] = mapped_column(String(128))
    output: Mapped[dict] = mapped_column(JSONB, default=dict)
    unsupported_segments: Mapped[list[str]] = mapped_column(JSONB, default=list)
    checks: Mapped[list[dict]] = mapped_column(JSONB, default=list)
    confidence: Mapped[float | None] = mapped_column(Float)

    provider: Mapped[str] = mapped_column(String(32), nullable=False)
    model: Mapped[str] = mapped_column(String(64), nullable=False)
    model_version: Mapped[str | None] = mapped_column(String(64))
    parameters: Mapped[dict] = mapped_column(JSONB, default=dict)
    permitted_data_class: Mapped[str] = mapped_column(String(16), nullable=False)

    input_tokens: Mapped[int] = mapped_column(Integer, default=0)
    output_tokens: Mapped[int] = mapped_column(Integer, default=0)
    cost_usd: Mapped[float] = mapped_column(Float, default=0.0)
    latency_ms: Mapped[int] = mapped_column(Integer, default=0)

    requires_human: Mapped[bool] = mapped_column(Boolean, default=True)
    required_role: Mapped[str | None] = mapped_column(String(32))
    human_decision: Mapped[str] = mapped_column(
        String(16), default=HumanDecision.PENDING.value, index=True
    )
    correction_detail: Mapped[str | None] = mapped_column(Text)
    decided_by_id: Mapped[uuid.UUID | None] = mapped_column(
        PgUUID(as_uuid=True), ForeignKey("app_user.id", ondelete="SET NULL")
    )
    decided_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    shadow: Mapped[bool] = mapped_column(Boolean, default=False, index=True)
    injection_detected: Mapped[bool] = mapped_column(Boolean, default=False, index=True)
    refused: Mapped[bool] = mapped_column(Boolean, default=False)
    refusal_reason: Mapped[str | None] = mapped_column(Text)

class Baseline(UUIDPrimaryKey, Timestamped, Base):
    """Captured baselines for the KPI set, PRD sections 4.1 and 17.1.

    No target is accepted as met without one.
    """

    __tablename__ = "kpi_baseline"

    kpi_code: Mapped[str] = mapped_column(String(24), unique=True, nullable=False)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    unit: Mapped[str] = mapped_column(String(32), default="hours")
    measurement_method: Mapped[str] = mapped_column(Text, nullable=False)
    baseline_value: Mapped[float | None] = mapped_column(Float)
    baseline_captured_on: Mapped[date | None] = mapped_column(Date)
    phase_1_target: Mapped[float | None] = mapped_column(Float)
    phase_3_target: Mapped[float | None] = mapped_column(Float)
    target_direction: Mapped[str] = mapped_column(String(8), default="down")
