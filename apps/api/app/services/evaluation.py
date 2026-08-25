"""The evaluation harness, PRD section 16.

The capability register carries a metric, a gate expression and a threshold.
Until something measures them, those are a declaration rather than a control.
This runs a capability over its golden set, scores it by the metric the
register names, records the run, and lets the gate act on the result.

Scoring is deterministic and lives here rather than in a model, because a gate
whose measurement is itself generated is not a gate.
"""

from __future__ import annotations

import logging
import re
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.ai import capabilities as registry
from app.ai.gateway import CapabilityCall, invoke
from app.ai.retrieval import RetrievedChunk, retrieve
from app.core import audit
from app.db.models.ai import Capability, EvaluationRun
from app.db.models.evaluation import GoldenCase, GoldenSet
from app.db.models.platform import MemoryChunk
from app.domain.enums import CapabilityState, DataClass

logger = logging.getLogger(__name__)

NO_SET = "No active golden set exists for this capability."
NO_CASES = "The golden set holds no active cases."
NOTHING_RAN = (
    "Every case was refused before it reached a model, so there is nothing to "
    "score. A capability that could not run is not a capability that failed, "
    "and the previous score stands."
)


class NotMeasurable(RuntimeError):
    """The capability cannot be measured, and the reason says why."""


@dataclass
class CaseResult:
    reference: str
    passed: bool
    detail: str
    predicted: Any = None
    expected: Any = None


@dataclass
class Measurement:
    """What one run of a golden set produced."""

    score: float
    label: str
    results: list[CaseResult] = field(default_factory=list)
    unrunnable: int = 0

    @property
    def passed_count(self) -> int:
        return sum(1 for result in self.results if result.passed)


def _normalise(value: Any) -> str:
    return re.sub(r"\s+", " ", str(value or "")).strip().lower()


def _set_of(values: Any, key: str | None = None) -> set[str]:
    items: list[Any] = values if isinstance(values, list) else []
    if key is None:
        return {_normalise(item) for item in items if _normalise(item)}
    out: set[str] = set()
    for item in items:
        if isinstance(item, dict) and _normalise(item.get(key)):
            out.add(_normalise(item.get(key)))
    return out


def _recall(expected: set[str], predicted: set[str]) -> float:
    if not expected:
        return 1.0
    return len(expected & predicted) / len(expected)


def _precision(expected: set[str], predicted: set[str]) -> float:
    if not predicted:
        return 0.0
    return len(expected & predicted) / len(predicted)


def _macro_f1(pairs: list[tuple[str, str]]) -> float:
    """F1 per class, averaged over the classes that appear in the truth.

    Averaging over classes rather than cases stops a set dominated by one
    category from hiding a capability that cannot recognise the rest.
    """
    labels = {expected for expected, _ in pairs}
    if not labels:
        return 0.0
    scores: list[float] = []
    for label in labels:
        true_positive = sum(1 for e, p in pairs if e == label and p == label)
        false_positive = sum(1 for e, p in pairs if e != label and p == label)
        false_negative = sum(1 for e, p in pairs if e == label and p != label)
        if true_positive == 0:
            scores.append(0.0)
            continue
        precision = true_positive / (true_positive + false_positive)
        recall = true_positive / (true_positive + false_negative)
        scores.append(2 * precision * recall / (precision + recall))
    return sum(scores) / len(scores)


def _score_classification(results: list[CaseResult]) -> Measurement:
    pairs = [(_normalise(result.expected), _normalise(result.predicted)) for result in results]
    score = _macro_f1(pairs)
    action = [(e, p) for e, p in pairs if e == "action_required"]
    action_recall = sum(1 for e, p in action if p == e) / len(action) if action else 1.0
    return Measurement(
        score=round(score, 4),
        label=f"{score:.2f} macro F1, {action_recall:.2f} recall on action required",
        results=results,
    )


def _pair_score(
    results: list[CaseResult], precisions: list[float], recalls: list[float], gated: str
) -> Measurement:
    precision = sum(precisions) / len(precisions) if precisions else 0.0
    recall = sum(recalls) / len(recalls) if recalls else 0.0
    score = precision if gated == "precision" else recall
    return Measurement(
        score=round(score, 4),
        label=f"{precision:.2f} precision, {recall:.2f} recall",
        results=results,
    )


def _score_rate(results: list[CaseResult], rates: list[float], label: str) -> Measurement:
    value = sum(rates) / len(rates) if rates else 0.0
    return Measurement(score=round(value, 4), label=f"{value:.3f} {label}", results=results)


def _classification_case(output: dict, expected: dict) -> CaseResult:
    predicted = _normalise(output.get("classification"))
    want = _normalise(expected.get("classification"))
    return CaseResult(
        reference="",
        passed=predicted == want,
        detail=f"Answered {predicted or 'nothing'}, expected {want}.",
        predicted=predicted,
        expected=want,
    )


def _pairs_case(predicted: set[str], want: set[str], noun: str) -> tuple[CaseResult, float, float]:
    precision = _precision(want, predicted)
    recall = _recall(want, predicted)
    missed = sorted(want - predicted)
    return (
        CaseResult(
            reference="",
            passed=recall >= 1.0 and precision >= 1.0,
            detail=(
                f"{len(want & predicted)} of {len(want)} {noun} matched"
                + (f", missed {', '.join(missed[:3])}" if missed else "")
            ),
            predicted=sorted(predicted),
            expected=sorted(want),
        ),
        precision,
        recall,
    )
def _summary_grounded_rate(output: dict, expected: dict) -> float:
    """A summary line is grounded when every number in it appears in the data."""
    allowed = {_normalise(value) for value in expected.get("figures", [])}
    lines = [
        line
        for key in ("delivery", "volumes", "turnaround", "blockers", "next_actions")
        for line in (output.get(key) or [])
    ]
    if not lines:
        return 0.0
    grounded = 0
    for line in lines:
        numbers = re.findall(r"\d[\d,.]*", str(line))
        if not numbers or all(_normalise(number) in allowed for number in numbers):
            grounded += 1
    return grounded / len(lines)


def _draft_supported_rate(output: dict) -> float:
    """One minus the unsupported statement rate, so higher is better on the
    same axis as every other metric."""
    clauses = output.get("clauses")
    if not isinstance(clauses, list) or not clauses:
        return 0.0
    unsupported = len(output.get("unsupported_segments") or [])
    novel = sum(1 for clause in clauses if isinstance(clause, dict) and clause.get("novel"))
    total = len(clauses)
    return max(0.0, 1.0 - (unsupported + novel) / total)


def _run_classification(outputs: list[tuple[GoldenCase, dict]]) -> Measurement:
    results: list[CaseResult] = []
    for case, output in outputs:
        result = _classification_case(output, case.expected)
        result.reference = case.reference
        results.append(result)
    return _score_classification(results)


def _run_extraction(outputs: list[tuple[GoldenCase, dict]]) -> Measurement:
    results, precisions, recalls = [], [], []
    for case, output in outputs:
        predicted = {
            f"{_normalise(item.get('field_name'))}={_normalise(item.get('value'))}"
            for item in (output.get("values") or [])
            if isinstance(item, dict)
        }
        want = {
            f"{_normalise(item.get('field_name'))}={_normalise(item.get('value'))}"
            for item in (case.expected.get("values") or [])
            if isinstance(item, dict)
        }
        result, precision, recall = _pairs_case(predicted, want, "values")
        result.reference = case.reference
        results.append(result)
        precisions.append(precision)
        recalls.append(recall)
    return _pair_score(results, precisions, recalls, "precision")


def _run_retrieval(outputs: list[tuple[GoldenCase, dict, list[str]]]) -> Measurement:
    results, recalls = [], []
    for case, _output, references in outputs:
        want = _set_of(case.expected.get("references"))
        predicted = {_normalise(reference) for reference in references[:5]}
        result, _precision, recall = _pairs_case(predicted, want, "sources")
        result.reference = case.reference
        results.append(result)
        recalls.append(recall)
    value = sum(recalls) / len(recalls) if recalls else 0.0
    return Measurement(score=round(value, 4), label=f"{value:.2f} recall at 5", results=results)


def _run_review(outputs: list[tuple[GoldenCase, dict]]) -> Measurement:
    """Recall on the critical deviations, with the false positive rate reported
    beside it because a review nobody trusts is a review nobody reads."""
    results, recalls, false_positive_rates = [], [], []
    for case, output in outputs:
        findings = [f for f in (output.get("findings") or []) if isinstance(f, dict)]
        predicted_critical = {
            _normalise(f.get("clause_category"))
            for f in findings
            if _normalise(f.get("severity")) == "critical"
        }
        want = _set_of(case.expected.get("critical_categories"))
        result, precision, recall = _pairs_case(predicted_critical, want, "critical findings")
        result.reference = case.reference
        results.append(result)
        recalls.append(recall)
        false_positive_rates.append(1.0 - precision if predicted_critical else 0.0)
    recall = sum(recalls) / len(recalls) if recalls else 0.0
    false_positive = (
        sum(false_positive_rates) / len(false_positive_rates) if false_positive_rates else 0.0
    )
    return Measurement(
        score=round(recall, 4),
        label=f"{recall:.2f} recall on critical, {false_positive:.2f} false positive rate",
        results=results,
    )


def _run_obligations(outputs: list[tuple[GoldenCase, dict]]) -> Measurement:
    results, recalls, precisions = [], [], []
    for case, output in outputs:
        predicted = {
            _normalise(item.get("name"))
            for item in (output.get("obligations") or [])
            if isinstance(item, dict) and item.get("due_date")
        }
        want = _set_of(case.expected.get("dated_obligations"))
        result, precision, recall = _pairs_case(predicted, want, "dated obligations")
        result.reference = case.reference
        results.append(result)
        recalls.append(recall)
        precisions.append(precision)
    return _pair_score(results, precisions, recalls, "recall")


def _run_draft(outputs: list[tuple[GoldenCase, dict]]) -> Measurement:
    results, rates = [], []
    for case, output in outputs:
        rate = _draft_supported_rate(output)
        rates.append(rate)
        results.append(
            CaseResult(
                reference=case.reference,
                passed=rate >= 0.98,
                detail=f"{1 - rate:.3f} of clauses were unsupported or novel.",
            )
        )
    return _score_rate(results, rates, "supported")


def _run_summary(outputs: list[tuple[GoldenCase, dict]]) -> Measurement:
    results, rates = [], []
    for case, output in outputs:
        rate = _summary_grounded_rate(output, case.expected)
        rates.append(rate)
        results.append(
            CaseResult(
                reference=case.reference,
                passed=rate >= 0.95,
                detail=f"{rate:.2f} of lines were attributable to the supplied figures.",
            )
        )
    return _score_rate(results, rates, "attributable")


def _run_grounded_answer(outputs: list[tuple[GoldenCase, dict, list[str]]]) -> Measurement:
    """Recall at five is the gated number, so the answer is measured by what it
    retrieved rather than by how it reads."""
    return _run_retrieval(outputs)


NEEDS_SOURCES = {"clause_retrieval_answer"}

SCORERS: dict[str, Callable[..., Measurement]] = {
    "inbox_classification": _run_classification,
    "fact_extraction": _run_extraction,
    "clause_retrieval_answer": _run_grounded_answer,
    "ai_first_draft": _run_draft,
    "deviation_detection": _run_review,
    "obligation_extraction": _run_obligations,
    "management_summary": _run_summary,
}


def active_set(session: Session, code: str) -> GoldenSet | None:
    return (
        session.execute(
            select(GoldenSet)
            .where(GoldenSet.capability_code == code, GoldenSet.active.is_(True))
            .order_by(GoldenSet.version.desc())
        )
        .scalars()
        .first()
    )


def _chunks(session: Session, case: GoldenCase, entity: str) -> list[RetrievedChunk]:
    """A case with its own context is measuring the model. A case without it is
    measuring retrieval as well, so the real index is queried."""
    if not case.context:
        return retrieve(session, case.prompt, entity, limit=8)

    chunks: list[RetrievedChunk] = []
    for rank, item in enumerate(case.context, start=1):
        if not isinstance(item, dict):
            continue
        chunk = MemoryChunk(
            entity=entity,
            source_type=item.get("kind", "approved_clause"),
            source_reference=item.get("reference", "UNKNOWN"),
            source_detail=item.get("detail"),
            title=item.get("title", item.get("reference", "Golden case context")),
            body=item.get("text", ""),
        )
        chunks.append(RetrievedChunk(chunk=chunk, score=1.0 / rank))
    return chunks


def _invoke_case(session: Session, capability: Capability, case: GoldenCase, entity: str):
    definition = registry.REGISTRY[capability.code]
    call = CapabilityCall(
        capability_code=capability.code,
        entity=entity,
        data_class=DataClass(capability.max_data_class),
        system=definition["system"],
        user_content=case.prompt,
        output_schema=definition["schema"],
        schema_name=definition["schema_name"],
        context=_chunks(session, case, entity),
        substantive=False,
        input_summary=f"Golden case {case.reference}",
        evaluation=True,
    )
    return invoke(session, call)


def measure(session: Session, capability: Capability, entity: str = "EAI") -> Measurement:
    """Run every active case in the capability's set and score the outcome."""
    if capability.code not in SCORERS:
        raise NotMeasurable(
            f"{capability.name} has no scorer, so it cannot be measured automatically."
        )
    if capability.gate_threshold is None:
        raise NotMeasurable(
            f"{capability.name} has no gate defined, so a result cannot be assessed."
        )

    golden = active_set(session, capability.code)
    if golden is None:
        raise NotMeasurable(NO_SET)
    cases = [case for case in golden.cases if case.active]
    if not cases:
        raise NotMeasurable(NO_CASES)

    scorer = SCORERS[capability.code]
    needs_sources = capability.code in NEEDS_SOURCES
    payloads: list = []
    refusals: list[str] = []

    for case in cases:
        envelope = _invoke_case(session, capability, case, entity)
        # A refusal is the route failing, not the capability answering badly.
        # Scoring it as a wrong answer would disable a capability because the
        # network was down, which is the opposite of what the gate is for.
        if envelope.refused:
            refusals.append(envelope.refusal_reason or "The call was refused.")
            continue
        if needs_sources:
            payloads.append(
                (case, envelope.output, [source.reference for source in envelope.sources])
            )
        else:
            payloads.append((case, envelope.output))

    if not payloads:
        raise NotMeasurable(f"{NOTHING_RAN} {refusals[0] if refusals else ''}".strip())

    measurement = scorer(payloads)
    if refusals:
        measurement.label += f", {len(refusals)} of {len(cases)} cases could not be run"
        measurement.unrunnable = len(refusals)
    return measurement


def record(
    session: Session,
    capability: Capability,
    measurement: Measurement,
    golden_set_name: str,
    set_size: int,
    actor_id: str | None = None,
    actor_label: str = "The evaluation schedule",
) -> EvaluationRun:
    """Write the result and let the gate act on it.

    A capability that falls below its gate is disabled here rather than at the
    point of use, so it stops running everywhere at once and says why.
    """
    passed = measurement.score >= (capability.gate_threshold or 0.0)
    run = EvaluationRun(
        capability_id=capability.id,
        golden_set=golden_set_name,
        set_size=set_size,
        score=measurement.score,
        score_label=measurement.label,
        threshold=capability.gate_threshold or 0.0,
        passed=passed,
        detail={
            "unrunnable": measurement.unrunnable,
            "cases": [
                {
                    "reference": result.reference,
                    "passed": result.passed,
                    "detail": result.detail,
                }
                for result in measurement.results
            ],
        },
        run_at=datetime.now(UTC),
    )
    session.add(run)

    capability.last_score = measurement.score
    capability.last_score_label = measurement.label
    capability.last_evaluated_at = run.run_at
    capability.golden_set = golden_set_name

    auto_disables = not passed and capability.gate_enforced
    if auto_disables and capability.state == CapabilityState.ENABLED.value:
        capability.state = CapabilityState.DISABLED.value
        capability.disabled_reason = (
            f"Scored {measurement.score:.3f} against a gate of {capability.gate_threshold} "
            f"on the {golden_set_name} set of {set_size} cases. Disabled automatically."
        )

    audit.record(
        session,
        action="capability_evaluated",
        object_type="capability",
        object_id=capability.code,
        actor_id=actor_id,
        actor_label=actor_label,
        after_state={
            "score": measurement.score,
            "label": measurement.label,
            "set": golden_set_name,
            "cases": set_size,
            "passed": passed,
            "state": capability.state,
        },
    )
    return run


def run(
    session: Session,
    capability: Capability,
    entity: str = "EAI",
    actor_id: str | None = None,
    actor_label: str = "The evaluation schedule",
) -> EvaluationRun:
    """Measure a capability and record the result in one step."""
    golden = active_set(session, capability.code)
    if golden is None:
        raise NotMeasurable(NO_SET)
    measurement = measure(session, capability, entity)
    return record(
        session,
        capability,
        measurement,
        golden.name,
        len(measurement.results),
        actor_id=actor_id,
        actor_label=actor_label,
    )


def sweep(session: Session, entity: str = "EAI") -> list[dict]:
    """Re-measure every capability that has an active set.

    A capability nobody has measured for a quarter is not a capability anyone
    can defend, so the schedule does it whether or not anyone remembers.
    """
    outcomes: list[dict] = []
    for capability in session.execute(select(Capability)).scalars():
        try:
            result = run(session, capability, entity)
        except NotMeasurable as exception:
            outcomes.append(
                {"capability": capability.code, "measured": False, "reason": str(exception)}
            )
            continue
        except Exception:
            logger.exception("The evaluation of %s failed.", capability.code)
            outcomes.append(
                {
                    "capability": capability.code,
                    "measured": False,
                    "reason": "The run failed. The previous score stands.",
                }
            )
            continue
        outcomes.append(
            {
                "capability": capability.code,
                "measured": True,
                "score": result.score,
                "passed": result.passed,
            }
        )
    return outcomes
