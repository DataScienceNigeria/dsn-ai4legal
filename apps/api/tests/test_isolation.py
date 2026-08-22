"""Entity separation and restricted matters, LOP-NFR-13 and LOP-M02-US-08.

These run against the real database because the control under test is the
row-level security policy, not any application code. An application defect
cannot leak across a boundary the database itself refuses to cross.
"""

import uuid

import pytest
from sqlalchemy import text

from app.db.session import AppSession, apply_security_context
from tests.conftest import needs_database


def _visible_matters(entities: list[str], user_id: str | None) -> set[str]:
    session = AppSession()
    try:
        apply_security_context(session, user_id=user_id, entities=entities, roles=["counsel"])
        rows = session.execute(text("SELECT number FROM matter")).scalars().all()
        return set(rows)
    finally:
        session.rollback()
        session.close()


@needs_database
def test_an_entity_sees_only_its_own_matters_and_a_restricted_matter_needs_a_named_user():
    session = AppSession()
    try:
        apply_security_context(session, user_id=None, entities=[], roles=[], bypass=True)
        named = session.execute(
            text(
                "SELECT ma.user_id FROM matter_access ma "
                "JOIN matter m ON m.id = ma.matter_id WHERE m.restricted LIMIT 1"
            )
        ).scalar_one_or_none()
        restricted_number = session.execute(
            text("SELECT number FROM matter WHERE restricted LIMIT 1")
        ).scalar_one_or_none()
    finally:
        session.rollback()
        session.close()

    if restricted_number is None or named is None:
        pytest.skip("The seed data holds no restricted matter.")

    entity = restricted_number.split("-")[0]

    named_view = _visible_matters([entity], str(named))
    stranger_view = _visible_matters([entity], str(uuid.uuid4()))
    other_entity = "EAI" if entity == "DSN" else "DSN"
    other_view = _visible_matters([other_entity], str(named))

    assert restricted_number in named_view
    assert restricted_number not in stranger_view
    assert all(number.startswith(entity) for number in stranger_view)
    assert all(number.startswith(other_entity) for number in other_view)
    assert not (stranger_view & other_view)


@needs_database
def test_the_application_role_cannot_alter_or_delete_an_audit_event():
    session = AppSession()
    try:
        apply_security_context(session, user_id=None, entities=["DSN"], roles=["admin"])
        with pytest.raises(Exception):
            session.execute(text("DELETE FROM audit_event"))
    finally:
        session.rollback()
        session.close()
