"""The AI response contract, PRD section 12.3.

Every AI endpoint returns this envelope, so that no consumer can present a
model output without its provenance. An output without sources is a failed
call, not a low-confidence answer.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from pydantic import BaseModel, Field


class Source(BaseModel):
    """An ordered reference to the record supporting an element of the output."""

    reference: str = Field(description="Clause, template, matter, contract or decision identifier")
    kind: str = Field(
        description="approved_clause, template, executed_contract, decision, playbook"
    )
    detail: str | None = None
    quote: str | None = None
    score: float | None = None

class Check(BaseModel):
    """A deterministic validation run on the output before presentation."""

    name: str
    passed: bool
    detail: str | None = None
    items: list[str] = Field(default_factory=list)

class Route(BaseModel):
    """Provider, model, version and parameters used, and the data class the
    call was permitted for."""

    provider: str
    model: str
    version: str | None = None
    parameters: dict[str, Any] = Field(default_factory=dict)
    permitted_data_class: str

class Cost(BaseModel):
    input_tokens: int = 0
    output_tokens: int = 0
    usd: float = 0.0
    latency_ms: int = 0

class AIEnvelope(BaseModel):
    """The single response shape for every AI capability."""

    interaction_id: str
    capability: str
    output: dict[str, Any]
    sources: list[Source] = Field(default_factory=list)
    unsupported_segments: list[str] = Field(default_factory=list)
    confidence: float | None = None
    checks: list[Check] = Field(default_factory=list)
    route: Route
    cost: Cost = Field(default_factory=Cost)
    requires_human: bool = True
    required_role: str | None = None
    refused: bool = False
    refusal_reason: str | None = None
    shadow: bool = False
    notice: str | None = None

class UngroundedOutput(ValueError):
    """Raised when a substantive output carries no source at all.

    Grounded or silent: ungrounded generation is a defect, not a feature
    (PRD section 3.2).
    """

@dataclass
class EnvelopeBuilder:
    """Assembles an envelope and enforces the grounding rule on completion."""

    interaction_id: str
    capability: str
    route: Route
    required_role: str | None = None
    shadow: bool = False
    substantive: bool = True

    output: dict[str, Any] = field(default_factory=dict)
    sources: list[Source] = field(default_factory=list)
    unsupported_segments: list[str] = field(default_factory=list)
    checks: list[Check] = field(default_factory=list)
    cost: Cost = field(default_factory=Cost)
    confidence: float | None = None
    notice: str | None = None

    def add_source(self, source: Source) -> None:
        if not any(s.reference == source.reference for s in self.sources):
            self.sources.append(source)

    def add_check(self, name: str, passed: bool, detail: str | None = None,
                  items: list[str] | None = None) -> None:
        self.checks.append(Check(name=name, passed=passed, detail=detail, items=items or []))

    def refuse(self, reason: str) -> AIEnvelope:
        """A refusal is a valid outcome and carries no output."""
        return AIEnvelope(
            interaction_id=self.interaction_id,
            capability=self.capability,
            output={},
            sources=self.sources,
            route=self.route,
            cost=self.cost,
            requires_human=True,
            required_role=self.required_role,
            refused=True,
            refusal_reason=reason,
            shadow=self.shadow,
            checks=self.checks,
        )

    def build(self) -> AIEnvelope:
        if self.substantive and not self.sources:
            raise UngroundedOutput(
                f"The {self.capability} capability produced an output with no retrieved "
                "source. An output without sources is a failed call."
            )
        return AIEnvelope(
            interaction_id=self.interaction_id,
            capability=self.capability,
            output=self.output,
            sources=self.sources,
            unsupported_segments=self.unsupported_segments,
            confidence=self.confidence,
            checks=self.checks,
            route=self.route,
            cost=self.cost,
            requires_human=True,
            required_role=self.required_role,
            shadow=self.shadow,
            notice=self.notice,
        )
