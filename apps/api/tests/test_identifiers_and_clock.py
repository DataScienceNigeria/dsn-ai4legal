"""Identifier scheme and the service clock, PRD section 8.3 and LOP-M02-US-04."""

from datetime import UTC, datetime, timedelta

from app.domain import identifiers
from app.domain.enums import Entity, MatterState
from app.domain.sla import ClockSegment, evaluate


def test_identifiers_carry_entity_and_year_and_never_depend_on_a_counterparty_name():
    """A matter identifier must not depend on a counterparty name, because
    names and spellings change while identity should not."""
    matter = identifiers.matter_number(Entity.EAI, "com", 2026, 11)
    assert matter == "EAI-COM-2026-0011"
    assert identifiers.validate("matter", matter)

    assert identifiers.contract_id("EAI", 2026, 38) == "EAI-CON-2026-0038"
    assert identifiers.request_reference(2026, 1184) == "REQ-2026-01184"
    assert identifiers.counterparty_id(47) == "CPT-0047"
    assert identifiers.obligation_id(38, 4) == "OBL-0038-04"
    assert identifiers.clause_version_id("liab", 2, 0) == "CLS-LIAB-v2.0"

    assert identifiers.validate("matter", "EAI-COMMERCIAL-2026-0011") is False


def test_the_clock_runs_only_while_the_matter_is_not_waiting_on_someone():
    """Time spent waiting on the requester does not count against the target,
    and the clock resumes without anyone restarting it."""
    start = datetime(2026, 8, 1, 9, 0, tzinfo=UTC)
    segments = [
        ClockSegment(MatterState.ACCEPTED, start, start + timedelta(hours=4)),
        ClockSegment(
            MatterState.RETURNED_FOR_INFORMATION,
            start + timedelta(hours=4),
            start + timedelta(hours=30),
        ),
        ClockSegment(MatterState.DRAFTING, start + timedelta(hours=30), start + timedelta(hours=33)),
    ]

    status = evaluate(segments, target_hours=8, current_state=MatterState.DRAFTING)

    assert status.elapsed_hours == 7
    assert status.running is True
    assert status.breached is False
    assert status.near_breach is True

    paused = evaluate(
        segments, target_hours=8, current_state=MatterState.RETURNED_FOR_INFORMATION
    )
    assert paused.running is False
