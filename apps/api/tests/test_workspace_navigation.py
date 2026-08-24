"""One test for workspace navigation, as instructed.

Two rules that would be expensive to get wrong. A badge counts work waiting
rather than records held, so a count that includes a closed matter is a count
nobody can act on. And search is a lookup, not an answer: it may only surface
what the caller could already open, which here means it never crosses the
working entity.
"""

import uuid

import pytest
from fastapi.testclient import TestClient

from app.api.v1.workspace import OPEN_MATTER_STATES, TRIAGE_STATES
from app.domain.enums import MatterState
from tests.conftest import needs_database


def test_a_closed_matter_is_not_counted_as_work_waiting():
    """The badge answers "is there work here", so anything already finished is
    outside it. Counting totals would make every badge permanent."""
    assert MatterState.EXECUTED.value not in OPEN_MATTER_STATES
    assert MatterState.ARCHIVED.value not in OPEN_MATTER_STATES
    assert MatterState.CLOSED_WITHOUT_MATTER.value not in TRIAGE_STATES
    assert MatterState.RETURNED_FOR_INFORMATION.value not in TRIAGE_STATES

    assert MatterState.DRAFTING.value in OPEN_MATTER_STATES
    assert MatterState.IN_APPROVAL.value in OPEN_MATTER_STATES
    assert MatterState.SUBMITTED.value in TRIAGE_STATES


@needs_database
def test_search_never_crosses_the_working_entity():
    """A hit is a record the caller could already open. Returning one from the
    other organisation would leak its existence through the lookup that was
    built to avoid exactly that."""
    from app.main import app

    client = TestClient(app)
    token = client.post(
        "/api/v1/auth/token",
        json={"email": "adaeze.okafor@dsn.example", "password": "Lop-Demo-2026"},
    )
    if token.status_code != 200:
        pytest.skip("The demo account is not seeded in this database.")
    headers = {"Authorization": f"Bearer {token.json()['access_token']}"}

    for entity in ("DSN", "EAI"):
        found = client.get(
            "/api/v1/workspace/search",
            params={"q": "agreement"},
            headers={**headers, "X-Entity": entity},
        )
        assert found.status_code == 200
        for hit in found.json()["hits"]:
            if hit["kind"] != "matter":
                continue
            matter_id = uuid.UUID(hit["href"].rsplit("/", 1)[-1])
            record = client.get(
                f"/api/v1/matters/{matter_id}",
                headers={**headers, "X-Entity": entity},
            )
            assert record.status_code == 200
            assert record.json()["entity"] == entity
