"""Identifier allocation.

Identifiers are permanent and never reused, so allocation takes a row lock on a
counter rather than counting existing records, which would reissue a number
after a deletion.
"""

from __future__ import annotations

from datetime import UTC, datetime

from sqlalchemy import text
from sqlalchemy.orm import Session

from app.domain import identifiers
from app.domain.enums import Entity

COUNTER_TABLE = "identifier_counter"


def next_value(session: Session, scope: str) -> int:
    row = session.execute(
        text(
            f"INSERT INTO {COUNTER_TABLE} (scope, value) VALUES (:scope, 1) "
            "ON CONFLICT (scope) DO UPDATE SET value = "
            f"{COUNTER_TABLE}.value + 1 RETURNING value"
        ),
        {"scope": scope},
    ).scalar_one()
    return int(row)


def new_request_reference(session: Session, year: int | None = None) -> str:
    year = year or datetime.now(UTC).year
    return identifiers.request_reference(year, next_value(session, f"request:{year}"))


def new_matter_number(
    session: Session, entity: Entity | str, practice: str, year: int | None = None
) -> str:
    year = year or datetime.now(UTC).year
    entity_code = Entity(entity).value
    scope = f"matter:{entity_code}:{practice.upper()}:{year}"
    return identifiers.matter_number(entity_code, practice, year, next_value(session, scope))


def new_contract_reference(
    session: Session, entity: Entity | str, year: int | None = None
) -> tuple[str, int]:
    year = year or datetime.now(UTC).year
    entity_code = Entity(entity).value
    sequence = next_value(session, f"contract:{entity_code}:{year}")
    return identifiers.contract_id(entity_code, year, sequence), sequence


def new_counterparty_reference(session: Session) -> str:
    return identifiers.counterparty_id(next_value(session, "counterparty"))


def new_obligation_reference(session: Session, contract_sequence: int) -> str:
    scope = f"obligation:{contract_sequence}"
    return identifiers.obligation_id(contract_sequence, next_value(session, scope))


def new_assessment_reference(session: Session, year: int | None = None) -> str:
    year = year or datetime.now(UTC).year
    return identifiers.assessment_id(year, next_value(session, f"assessment:{year}"))


def new_issue_reference(session: Session, year: int | None = None) -> str:
    year = year or datetime.now(UTC).year
    return identifiers.contract_issue_id(year, next_value(session, f"contract_issue:{year}"))


def new_change_request_reference(session: Session, year: int | None = None) -> str:
    year = year or datetime.now(UTC).year
    return identifiers.change_request_id(year, next_value(session, f"change_request:{year}"))


def new_decision_sequence(session: Session) -> int:
    return next_value(session, "decision")
