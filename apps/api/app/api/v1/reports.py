"""Reporting and analytics, M14.

Every figure is computed from lifecycle events rather than from separate entry,
and all reporting is entity-scoped by default.
"""

from __future__ import annotations

import statistics
import uuid
from datetime import UTC, date, datetime, timedelta

from fastapi import APIRouter
from sqlalchemy import func, select

from app.core import audit
from app.core.deps import CurrentUser, Db, WorkingEntity
from app.core.errors import Forbidden, NotFound
from app.db.models.ai import AIInteraction, Baseline, Capability
from app.db.models.contract import Contract, Obligation
from app.db.models.counterparty import Counterparty
from app.db.models.document import ReviewFinding
from app.db.models.governance import Communication
from app.db.models.library import ClauseVersion, TemplateVersion
from app.db.models.matter import Matter, MatterTransition
from app.db.models.organisation import User
from app.domain.enums import (
    CapabilityState,
    HumanDecision,
    MatterState,
    ObligationStatus,
    Role,
    Severity,
    VersionStatus,
)
from app.domain.sla import ClockSegment, evaluate
from app.schemas.governance import (
    AgeingBucket,
    AiQualityRow,
    BaselineUpdate,
    KpiRow,
    OperationalReport,
    OwnerLoad,
    WeeklyUpdate,
)

router = APIRouter(prefix="/reports", tags=["reports"])

OPEN_STATES = [
    MatterState.ACCEPTED.value,
    MatterState.DRAFTING.value,
    MatterState.IN_REVIEW.value,
    MatterState.ESCALATED.value,
    MatterState.IN_APPROVAL.value,
    MatterState.AWAITING_SIGNATURE.value,
    MatterState.ON_HOLD.value,
]

AGEING_BUCKETS = [(0, 2), (3, 7), (8, 14), (15, 30), (31, None)]


def _segments(db, matter_id: uuid.UUID) -> list[ClockSegment]:
    transitions = list(
        db.execute(
            select(MatterTransition)
            .where(MatterTransition.matter_id == matter_id)
            .order_by(MatterTransition.occurred_at)
        ).scalars()
    )
    segments = []
    for index, transition in enumerate(transitions):
        segments.append(
            ClockSegment(
                state=MatterState(transition.to_state),
                started_at=transition.occurred_at,
                ended_at=transitions[index + 1].occurred_at
                if index + 1 < len(transitions)
                else None,
            )
        )
    return segments


@router.get("/operational")
def operational(
    db: Db, principal: CurrentUser, entity: WorkingEntity, cross_entity: bool = False
) -> OperationalReport:
    principal.require_role(
        Role.COUNSEL, Role.HEAD_OF_LEGAL, Role.MANAGEMENT, Role.ADMIN
    )
    entities = _reporting_entities(db, principal, entity, cross_entity, "operational")

    matters = list(
        db.execute(
            select(Matter).where(Matter.entity.in_(entities), Matter.status.in_(OPEN_STATES))
        ).scalars()
    )

    by_tier: dict[str, int] = {}
    by_status: dict[str, int] = {}
    ageing = {f"{low} to {high}" if high else f"{low} and over": 0 for low, high in AGEING_BUCKETS}
    breaches = 0
    near = 0
    blocked = 0
    load: dict[uuid.UUID | None, dict] = {}

    now = datetime.now(UTC)
    for matter in matters:
        by_tier[matter.risk_tier] = by_tier.get(matter.risk_tier, 0) + 1
        by_status[matter.status] = by_status.get(matter.status, 0) + 1

        days = (now - matter.created_at).days
        for low, high in AGEING_BUCKETS:
            if days >= low and (high is None or days <= high):
                key = f"{low} to {high}" if high else f"{low} and over"
                ageing[key] += 1
                break

        status = evaluate(
            _segments(db, matter.id), matter.sla_target_hours, MatterState(matter.status)
        )
        if status.breached:
            breaches += 1
        elif status.near_breach:
            near += 1
        if matter.blocker:
            blocked += 1

        row = load.setdefault(
            matter.responsible_lawyer_id, {"open": 0, "breached": 0}
        )
        row["open"] += 1
        if status.breached:
            row["breached"] += 1

    completed = list(
        db.execute(
            select(Matter).where(
                Matter.entity.in_(entities),
                Matter.status.in_(
                    [MatterState.EXECUTED.value, MatterState.ACTIVE.value]
                ),
            )
        ).scalars()
    )
    turnarounds = []
    for matter in completed:
        status = evaluate(
            _segments(db, matter.id), matter.sla_target_hours, MatterState(matter.status)
        )
        if status.elapsed_hours > 0:
            turnarounds.append(status.elapsed_hours)

    owner_rows = []
    for owner_id, counts in load.items():
        owner = db.get(User, owner_id) if owner_id else None
        owner_rows.append(
            OwnerLoad(
                owner_id=owner_id,
                owner_name=owner.name if owner else "Unassigned",
                open_matters=counts["open"],
                breached=counts["breached"],
            )
        )
    owner_rows.sort(key=lambda row: row.open_matters, reverse=True)

    overdue_obligations = db.execute(
        select(func.count())
        .select_from(Obligation)
        .where(
            Obligation.entity.in_(entities),
            Obligation.status == ObligationStatus.OPEN.value,
            Obligation.due_date < date.today(),
        )
    ).scalar_one()

    reviews_overdue = db.execute(
        select(func.count())
        .select_from(ClauseVersion)
        .where(
            ClauseVersion.status == VersionStatus.APPROVED.value,
            ClauseVersion.review_date < date.today(),
        )
    ).scalar_one() + db.execute(
        select(func.count())
        .select_from(TemplateVersion)
        .where(
            TemplateVersion.status == VersionStatus.APPROVED.value,
            TemplateVersion.review_date < date.today(),
        )
    ).scalar_one()

    return OperationalReport(
        generated_at=now,
        entity=", ".join(entities),
        open_matters=len(matters),
        by_tier=by_tier,
        by_status=by_status,
        ageing=[AgeingBucket(label=label, count=count) for label, count in ageing.items()],
        sla_breaches=breaches,
        near_breaches=near,
        blocked=blocked,
        by_owner=owner_rows,
        turnaround_median_hours=round(statistics.median(turnarounds), 1)
        if turnarounds
        else None,
        obligations_overdue=int(overdue_obligations),
        reviews_overdue=int(reviews_overdue),
    )


@router.get("/kpi")
def kpi(db: Db, principal: CurrentUser, entity: WorkingEntity) -> list[KpiRow]:
    """Every KPI against baseline and target, with the definition visible.

    No target is accepted as met without a baseline, so a KPI with no captured
    baseline reports a null current value rather than an unqualified figure.
    """
    principal.require_role(
        Role.COUNSEL, Role.HEAD_OF_LEGAL, Role.MANAGEMENT, Role.ADMIN, Role.AUDITOR
    )

    measured = _measure_kpis(db, entity)
    return [
        _kpi_row(baseline, measured.get(baseline.kpi_code))
        for baseline in db.execute(select(Baseline).order_by(Baseline.kpi_code)).scalars()
    ]


@router.put("/kpi/{code}", response_model=KpiRow)
def set_baseline(
    code: str, payload: BaselineUpdate, db: Db, principal: CurrentUser, entity: WorkingEntity
) -> KpiRow:
    """Record the baseline this KPI is measured from, and the target it is aimed at.

    Both were seeded, and eight of the ten arrived empty, which left most of the
    table reading "not set" against a target nobody could be held to. A baseline
    is a measurement somebody took on a date, so the date is stamped when the
    figure is written rather than asked for: it is the date the reading was
    entered, and a reading entered today did not come from last quarter.

    Nothing here computes. The current column is measured by the platform from
    what actually happened; this is only the two numbers a person has to supply
    because no system holds them.
    """
    principal.require_role(Role.HEAD_OF_LEGAL, Role.ADMIN)

    baseline = db.execute(
        select(Baseline).where(Baseline.kpi_code == code)
    ).scalar_one_or_none()
    if baseline is None:
        raise NotFound("That KPI is not in the register.")

    before = {"baseline": baseline.baseline_value, "target": baseline.phase_1_target}

    if payload.baseline_value is not None:
        baseline.baseline_value = payload.baseline_value
        baseline.baseline_captured_on = date.today()
    elif payload.clear_baseline:
        baseline.baseline_value = None
        baseline.baseline_captured_on = None

    if payload.target is not None:
        baseline.phase_1_target = payload.target

    audit.record(
        db,
        action="kpi_baseline_recorded",
        object_type="kpi_baseline",
        object_id=baseline.kpi_code,
        actor_id=principal.user_id,
        actor_label=principal.name,
        entity=entity,
        before_state=before,
        after_state={
            "baseline": baseline.baseline_value,
            "target": baseline.phase_1_target,
            "captured_on": str(baseline.baseline_captured_on)
            if baseline.baseline_captured_on
            else None,
        },
    )

    current = _measure_kpis(db, entity).get(code)
    return _kpi_row(baseline, current)


def _kpi_row(baseline: Baseline, current: float | None) -> KpiRow:
    on_track = None
    if current is not None and baseline.phase_1_target is not None:
        on_track = (
            current <= baseline.phase_1_target
            if baseline.target_direction == "down"
            else current >= baseline.phase_1_target
        )
    return KpiRow(
        code=baseline.kpi_code,
        name=baseline.name,
        unit=baseline.unit,
        measurement_method=baseline.measurement_method,
        baseline=baseline.baseline_value,
        baseline_captured_on=baseline.baseline_captured_on,
        current=current,
        phase_1_target=baseline.phase_1_target,
        phase_3_target=baseline.phase_3_target,
        direction=baseline.target_direction,
        on_track=on_track,
    )


def _measure_kpis(db, entity: str) -> dict[str, float]:
    """Compute the KPIs the platform can measure from lifecycle events."""
    measured: dict[str, float] = {}

    acknowledge: list[float] = []
    first_draft: list[float] = []
    for matter in db.execute(select(Matter).where(Matter.entity == entity)).scalars():
        transitions = list(
            db.execute(
                select(MatterTransition)
                .where(MatterTransition.matter_id == matter.id)
                .order_by(MatterTransition.occurred_at)
            ).scalars()
        )
        if not transitions:
            continue
        accepted = next(
            (t for t in transitions if t.to_state == MatterState.ACCEPTED.value), None
        )
        drafting = next(
            (t for t in transitions if t.to_state == MatterState.DRAFTING.value), None
        )
        if accepted:
            acknowledge.append(
                (accepted.occurred_at - matter.created_at).total_seconds() / 3600
            )
        if accepted and drafting:
            first_draft.append(
                (drafting.occurred_at - accepted.occurred_at).total_seconds() / 60
            )

    if acknowledge:
        measured["LOP-KPI-01"] = round(statistics.median(acknowledge), 2)
    if first_draft:
        measured["LOP-KPI-02"] = round(statistics.median(first_draft), 2)

    overdue = db.execute(
        select(func.count())
        .select_from(Obligation)
        .where(
            Obligation.entity == entity,
            Obligation.status == ObligationStatus.OPEN.value,
            Obligation.due_date < date.today(),
        )
    ).scalar_one()
    measured["LOP-KPI-07"] = float(overdue)

    return measured


@router.get("/ai-quality")
def ai_quality(db: Db, principal: CurrentUser) -> list[AiQualityRow]:
    """Requests by capability, route, cost, latency, correction rate and gates.

    Every capability currently disabled appears with the reason.
    """
    principal.require_role(Role.ADMIN, Role.HEAD_OF_LEGAL, Role.AUDITOR)

    rows = []
    for capability in db.execute(select(Capability).order_by(Capability.name)).scalars():
        interactions = list(
            db.execute(
                select(AIInteraction).where(
                    AIInteraction.capability_code == capability.code
                )
            ).scalars()
        )
        accepted = sum(
            1 for i in interactions if i.human_decision == HumanDecision.ACCEPTED.value
        )
        edited = sum(
            1 for i in interactions if i.human_decision == HumanDecision.EDITED.value
        )
        rejected = sum(
            1 for i in interactions if i.human_decision == HumanDecision.REJECTED.value
        )
        decided = accepted + edited + rejected
        latencies = [i.latency_ms for i in interactions if i.latency_ms]

        rows.append(
            AiQualityRow(
                capability=capability.name,
                state=capability.state,
                calls=len(interactions),
                accepted=accepted,
                edited=edited,
                rejected=rejected,
                correction_rate=round((edited + rejected) / decided, 3) if decided else None,
                cost_usd=round(sum(i.cost_usd for i in interactions), 4),
                median_latency_ms=int(statistics.median(latencies)) if latencies else None,
                gate_threshold=capability.gate_threshold,
                last_score=capability.last_score,
                disabled_reason=capability.disabled_reason
                if capability.state == CapabilityState.DISABLED.value
                else None,
            )
        )
    return rows


@router.get("/weekly-update")
def weekly_update(
    db: Db, principal: CurrentUser, entity: WorkingEntity
) -> WeeklyUpdate:
    """The weekly progress update, generated rather than written.

    The figures are computed here. The legal lead reads it before it is
    circulated.
    """
    principal.require_role(Role.HEAD_OF_LEGAL, Role.MANAGEMENT, Role.ADMIN)

    end = date.today()
    start = end - timedelta(days=7)
    since = datetime.combine(start, datetime.min.time(), tzinfo=UTC)

    opened = db.execute(
        select(func.count())
        .select_from(Matter)
        .where(Matter.entity == entity, Matter.created_at >= since)
    ).scalar_one()

    executed = db.execute(
        select(func.count())
        .select_from(MatterTransition)
        .join(Matter, Matter.id == MatterTransition.matter_id)
        .where(
            Matter.entity == entity,
            MatterTransition.to_state == MatterState.EXECUTED.value,
            MatterTransition.occurred_at >= since,
        )
    ).scalar_one()

    report = operational(db, principal, entity)

    blocked = [
        f"{row.owner_name} carries {row.breached} matters past their service target."
        for row in report.by_owner
        if row.breached
    ]

    return WeeklyUpdate(
        generated_at=datetime.now(UTC),
        entity=entity,
        period_start=start,
        period_end=end,
        delivery=[
            f"{opened} matters opened and {executed} agreements executed in the period.",
            f"{report.open_matters} matters are open across {len(report.by_owner)} owners.",
        ],
        volumes=[
            f"{tier.replace('_', ' ')}: {count} open."
            for tier, count in sorted(report.by_tier.items())
        ],
        turnaround=[
            f"Median end-to-end turnaround is {report.turnaround_median_hours} hours."
            if report.turnaround_median_hours is not None
            else "No completed matter yet carries a measurable turnaround."
        ],
        blockers=blocked
        or ["No matter is past its service target."],
        next_actions=[
            f"{report.obligations_overdue} obligations are overdue and need an owner decision."
            if report.obligations_overdue
            else "No obligation is overdue.",
            f"{report.reviews_overdue} library versions are past their review date."
            if report.reviews_overdue
            else "No library version is past its review date.",
        ],
    )


def _reporting_entities(
    db, principal, entity: str, cross_entity: bool, view: str
) -> list[str]:
    """Entity scoping is the default, and crossing it is a permission.

    All reporting is entity-scoped unless the caller holds a role that may see
    both entities and asks for it explicitly, and that request is logged
    (LOP-M14-US-06).
    """
    if not cross_entity:
        return [entity]

    principal.require_role(Role.HEAD_OF_LEGAL, Role.ADMIN, Role.AUDITOR)
    entities = sorted(set(principal.entities))
    if len(entities) < 2:
        raise Forbidden(
            "A cross-entity view needs access to more than one entity, and this "
            "account has access to one."
        )

    audit.record(
        db,
        action="cross_entity_report_viewed",
        object_type="report",
        object_id=view,
        actor_id=principal.user_id,
        actor_label=principal.name,
        entity=entity,
        after_state={"entities": entities},
    )
    return entities


@router.get("/exposure")
def exposure(
    db: Db,
    principal: CurrentUser,
    entity: WorkingEntity,
    cross_entity: bool = False,
) -> dict:
    """Risk and exposure, LOP-M14-US-03.

    Deviations accepted by severity and by the authority that cleared them, the
    clauses conceded most often, and contracts sitting on an unusual liability
    position.

    Obligations falling due used to be counted here and are not exposure. This
    report answers what we agreed to that was not our position; an obligation
    inside its notice period is work nobody has done yet, which is a different
    question wearing the same clothes. The renewal and notice deadlines that are
    legal's own reach the calendar feed and the reminders, which is where a
    date that has not passed belongs.
    """
    principal.require_role(Role.HEAD_OF_LEGAL, Role.COUNSEL, Role.ADMIN, Role.AUDITOR)
    entities = _reporting_entities(db, principal, entity, cross_entity, "exposure")

    matter_ids = [
        row[0]
        for row in db.execute(select(Matter.id).where(Matter.entity.in_(entities))).all()
    ]

    findings = (
        list(
            db.execute(
                select(ReviewFinding).where(ReviewFinding.matter_id.in_(matter_ids))
            ).scalars()
        )
        if matter_ids
        else []
    )
    conceded = [f for f in findings if f.decision == "accepted"]

    by_severity: dict[str, int] = {}
    by_authority: dict[str, int] = {}
    by_clause: dict[str, dict] = {}
    for finding in conceded:
        by_severity[finding.severity] = by_severity.get(finding.severity, 0) + 1
        by_authority[finding.required_authority] = (
            by_authority.get(finding.required_authority, 0) + 1
        )
        key = finding.clause_category or "uncategorised"
        row = by_clause.setdefault(
            key, {"clause_category": key, "conceded": 0, "critical_or_material": 0}
        )
        row["conceded"] += 1
        if finding.severity in {Severity.CRITICAL.value, Severity.MATERIAL.value}:
            row["critical_or_material"] += 1

    unusual = [
        {
            "reference": contract.reference,
            "agreement_type": contract.agreement_type,
            "value_amount": float(contract.value_amount) if contract.value_amount else None,
            "value_currency": contract.value_currency,
            "reason": reason,
        }
        for contract, reason in _unusual_liability(db, entities)
    ]

    return {
        "entities": entities,
        "deviations_accepted": len(conceded),
        "by_severity": by_severity,
        "by_authority": by_authority,
        "clauses_conceded": sorted(
            by_clause.values(), key=lambda row: row["conceded"], reverse=True
        ),
        "unusual_liability_positions": unusual,
        "note": (
            "Exposure is counted from findings legal accepted, so a deviation "
            "that was rejected does not appear here, and one nobody has ruled "
            "on yet does not appear either."
        ),
    }


def _unusual_liability(db, entities: list[str]) -> list[tuple]:
    """A liability position is unusual when the matter behind it conceded a
    critical or material liability finding, or when the contract carries no
    liability position at all."""
    results: list[tuple] = []
    contracts = list(
        db.execute(select(Contract).where(Contract.entity.in_(entities))).scalars()
    )
    for contract in contracts:
        findings = list(
            db.execute(
                select(ReviewFinding).where(
                    ReviewFinding.matter_id == contract.matter_id,
                    ReviewFinding.clause_category == "LIAB",
                )
            ).scalars()
        )
        conceded = [f for f in findings if f.decision == "accepted"]
        if any(f.severity in {Severity.CRITICAL.value, Severity.MATERIAL.value} for f in conceded):
            results.append((contract, "A critical or material liability deviation was accepted."))
        elif any(f.clause_absent for f in findings):
            results.append((contract, "The agreement carries no limitation of liability."))
    return results


@router.get("/deviation-patterns")
def deviation_patterns(
    db: Db,
    principal: CurrentUser,
    entity: WorkingEntity,
    cross_entity: bool = False,
) -> list[dict]:
    """Which clauses are challenged most, by which counterparty class, with what
    outcome, so the playbook is revised on evidence (LOP-M06-US-06)."""
    principal.require_role(Role.HEAD_OF_LEGAL, Role.COUNSEL, Role.ADMIN, Role.AUDITOR)
    entities = _reporting_entities(db, principal, entity, cross_entity, "deviation-patterns")

    matters = {
        matter.id: matter
        for matter in db.execute(select(Matter).where(Matter.entity.in_(entities))).scalars()
    }
    if not matters:
        return []

    classes = {
        row.id: row.relationship_class
        for row in db.execute(select(Counterparty)).scalars()
    }

    patterns: dict[tuple[str, str], dict] = {}
    for finding in db.execute(
        select(ReviewFinding).where(ReviewFinding.matter_id.in_(list(matters)))
    ).scalars():
        matter = matters[finding.matter_id]
        counterparty_class = classes.get(matter.counterparty_id) or "no counterparty"
        key = (finding.clause_category or "uncategorised", counterparty_class)
        row = patterns.setdefault(
            key,
            {
                "clause_category": key[0],
                "counterparty_class": key[1],
                "challenged": 0,
                "accepted": 0,
                "rejected": 0,
                "undecided": 0,
                "absent": 0,
            },
        )
        row["challenged"] += 1
        if finding.decision == "accepted":
            row["accepted"] += 1
        elif finding.decision == "rejected":
            row["rejected"] += 1
        else:
            row["undecided"] += 1
        if finding.clause_absent:
            row["absent"] += 1

    # Undecided findings are counted as challenged and left out of the rate. A
    # point nobody has ruled on says nothing about whether the position holds,
    # and folding it in either way would make the number agree with whoever is
    # slowest to decide.
    for row in patterns.values():
        decided = row["accepted"] + row["rejected"]
        row["concession_rate"] = round(row["accepted"] / decided, 3) if decided else None

    return sorted(patterns.values(), key=lambda row: row["challenged"], reverse=True)


@router.get("/inbox-accuracy")
def inbox_accuracy(
    db: Db, principal: CurrentUser, entity: WorkingEntity, days: int = 90
) -> dict:
    """Accuracy per classification category, LOP-M09-US-07.

    A correction is a false positive for the category the platform suggested and
    a false negative for the category Legal chose instead, which is what makes
    the two columns add up to something a gate can be read against.
    """
    principal.require_role(Role.ADMIN, Role.HEAD_OF_LEGAL, Role.AUDITOR, Role.COUNSEL)

    since = datetime.now(UTC) - timedelta(days=days)
    messages = list(
        db.execute(
            select(Communication).where(
                Communication.entity == entity,
                Communication.classification.is_not(None),
                Communication.created_at >= since,
            )
        ).scalars()
    )

    categories: dict[str, dict] = {}

    def row_for(name: str) -> dict:
        return categories.setdefault(
            name,
            {
                "category": name,
                "suggested": 0,
                "confirmed": 0,
                "false_positive": 0,
                "false_negative": 0,
            },
        )

    for message in messages:
        suggested = row_for(message.classification)
        suggested["suggested"] += 1
        if message.classification_corrected and message.corrected_classification:
            suggested["false_positive"] += 1
            row_for(message.corrected_classification)["false_negative"] += 1
        else:
            suggested["confirmed"] += 1

    for row in categories.values():
        total = row["suggested"]
        row["precision"] = round(row["confirmed"] / total, 3) if total else None
        recall_base = row["confirmed"] + row["false_negative"]
        row["recall"] = round(row["confirmed"] / recall_base, 3) if recall_base else None

    corrected = sum(1 for m in messages if m.classification_corrected)
    return {
        "window_days": days,
        "messages": len(messages),
        "correction_rate": round(corrected / len(messages), 3) if messages else None,
        "categories": sorted(categories.values(), key=lambda row: row["suggested"], reverse=True),
        "gate": (
            "The module may not be extended to new mailboxes or categories until "
            "its gate in PRD section 4.2 is met."
        ),
    }
