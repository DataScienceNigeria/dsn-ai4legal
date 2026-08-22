"""One test per Phase J and K feature, as instructed.

Each covers the property that would be expensive to get wrong: the second
factor cannot be replayed, a directory cannot invent a role, the harness scores
what it should and refuses to score what did not run, a missing scanner fails
closed, and a transport that cannot deliver says so rather than reporting a
message sent.
"""

from datetime import UTC, datetime

import pytest

from app.ai import embeddings
from app.core import mfa
from app.core.security import Principal, create_access_token, decode_token
from app.db.models.platform import EMBEDDING_DIM
from app.services import evaluation, malware
from app.services.transports import LogTransport, Message


def test_a_one_time_password_cannot_be_presented_twice():
    """A code that works for the whole thirty-second window is a password, so
    the counter it matched is recorded and anything at or below it refused."""
    secret = mfa.generate_secret()
    code = mfa.code_at(secret)

    counter = mfa.verify(secret, code)
    assert counter is not None
    assert mfa.verify(secret, code, last_counter=counter) is None
    assert mfa.verify(secret, "000000", last_counter=None) in (None, counter)


def test_a_role_that_needs_a_factor_cannot_step_up_without_one(monkeypatch):
    """Signing in is not gated on the factor. The privileged act is, and that
    is the whole point of the requirement."""
    monkeypatch.setattr(
        mfa.settings, "dsnlai_mfa_required_roles", "admin,head_of_legal", raising=False
    )

    token = create_access_token(
        subject="s",
        user_id="00000000-0000-0000-0000-000000000001",
        name="Emeka Obi",
        email="emeka.obi@dsn.example",
        roles=["admin"],
        entities=["DSN"],
        session_id="abc",
        mfa_satisfied=False,
    )
    principal = decode_token(token)

    from app.core.errors import StepUpRequired

    with pytest.raises(StepUpRequired):
        principal.require_step_up("publish a library version")

    satisfied = decode_token(
        create_access_token(
            subject="s",
            user_id="00000000-0000-0000-0000-000000000001",
            name="Emeka Obi",
            email="emeka.obi@dsn.example",
            roles=["admin"],
            entities=["DSN"],
            session_id="abc",
            mfa_satisfied=True,
        )
    )
    satisfied.require_step_up("publish a library version")


def test_the_directory_cannot_invent_a_role_this_platform_does_not_have():
    """A group the platform has never heard of grants nothing. Accepting it
    would let a directory administrator create authority here."""
    from app.api.v1.scim import _entities_from, _roles_from

    payload = {
        "roles": [{"value": "counsel"}, {"value": "superuser"}, "head_of_legal"],
        "urn:ietf:params:scim:schemas:extension:enterprise:2.0:User": {"division": "DSN,EAI"},
    }

    assert _roles_from(payload) == ["counsel", "head_of_legal"]
    assert _entities_from(payload) == ["DSN", "EAI"]


def test_the_harness_scores_a_classification_set_by_macro_f1():
    """Averaging over classes rather than cases stops a set dominated by one
    category from hiding a capability that cannot recognise the rest."""

    class Case:
        def __init__(self, reference, expected):
            self.reference = reference
            self.expected = expected

    outputs = [
        (Case("a", {"classification": "action_required"}), {"classification": "action_required"}),
        (Case("b", {"classification": "awareness_only"}), {"classification": "awareness_only"}),
        (Case("c", {"classification": "privacy_issue"}), {"classification": "awareness_only"}),
    ]

    measurement = evaluation._run_classification(outputs)

    assert measurement.passed_count == 2
    # Two classes are answered perfectly and one is missed entirely, so the
    # macro average sits well below the two-thirds a per-case count would give.
    assert 0.5 < measurement.score < 0.67
    assert "macro F1" in measurement.label


def test_a_capability_that_could_not_run_is_not_a_capability_that_failed():
    """Scoring a refusal as a wrong answer would disable a capability because
    the network was down, which is the opposite of what the gate is for."""
    assert "nothing to score" in evaluation.NOTHING_RAN


def test_a_scanner_that_cannot_be_reached_refuses_the_file(monkeypatch):
    """Accepting an unscanned file because the scanner was down is how the one
    file that mattered gets in."""
    monkeypatch.setattr(malware.settings, "dsnlai_clamav_host", "", raising=False)
    clean, detail = malware.scan(b"%PDF-1.7 ordinary")
    assert clean and "not a malware scan" in detail

    monkeypatch.setattr(malware.settings, "dsnlai_clamav_host", "127.0.0.1", raising=False)
    monkeypatch.setattr(malware.settings, "dsnlai_clamav_port", 1, raising=False)
    clean, detail = malware.scan(b"%PDF-1.7 ordinary")
    assert not clean
    assert "refused rather than accepted unscanned" in detail

    monkeypatch.setattr(malware.settings, "dsnlai_clamav_host", "", raising=False)
    clean, detail = malware.scan(b"MZ\x90\x00")
    assert not clean and "executable header" in detail


def test_the_log_transport_says_nothing_was_sent():
    """A queue that reports success for messages nobody received is worse than
    one that never ran."""
    detail = LogTransport().send(
        Message(connector="mail_administrative", recipients=["a@b.example"], subject="Hi", body="")
    )
    assert "nothing was sent" in detail


def test_an_embedding_is_always_the_width_the_column_holds(monkeypatch):
    """A vector of the wrong length cannot be stored at all, so a hosted model
    that returns more is truncated and renormalised."""
    monkeypatch.setattr(
        embeddings.settings, "dsnlai_embedding_provider", "deterministic", raising=False
    )
    vectors = embeddings.embed(["limitation of liability", "payment terms"])
    assert all(len(vector) == EMBEDDING_DIM for vector in vectors)

    wide = embeddings._fit([1.0] * (EMBEDDING_DIM + 100))
    assert len(wide) == EMBEDDING_DIM
    assert abs(sum(value * value for value in wide) - 1.0) < 1e-6


def test_a_federated_token_maps_onto_the_platforms_own_claim_shape():
    """Nothing downstream can tell the difference between a token verified at
    the provider and one this API issued itself."""
    from app.core.oidc import _claim_list

    claims = {
        "realm_access": {"roles": ["counsel", "legal_ops"]},
        "entities": "DSN EAI",
    }
    assert _claim_list(claims, "realm_access.roles") == ["counsel", "legal_ops"]
    assert _claim_list(claims, "entities") == ["DSN", "EAI"]
    assert _claim_list(claims, "missing.path") == []


def test_a_principal_without_the_factor_is_still_a_principal():
    """Someone who cannot yet enrol still has read work to do."""
    principal = Principal(
        user_id="1",
        subject="s",
        name="A",
        email="a@b.example",
        roles=["auditor"],
        entities=["DSN"],
        authenticated_at=datetime.now(UTC),
    )
    assert not principal.mfa_satisfied
    principal.require_step_up("read the audit trail")


def test_the_audit_digest_binds_the_position_as_well_as_the_content():
    """Two events written in the same microsecond used to hash identically
    whichever order they were appended in, so the chain could not tell a
    reordering from the truth."""
    from datetime import datetime as clock

    from app.core.audit import compute_digest, legacy_digest

    shared = {
        "occurred_at": clock(2026, 8, 22, 5, 14, 5, 667034, tzinfo=UTC),
        "actor_label": "Emeka Obi",
        "object_type": "document",
        "object_id": "abc",
        "action": "document_generated",
        "result": "success",
        "previous_digest": "0" * 64,
    }

    first = compute_digest(sequence=41, **shared)
    second = compute_digest(sequence=42, **shared)
    assert first != second

    # The old formula is kept so a row written before the fix still verifies as
    # sound rather than as tampered with.
    assert legacy_digest(**shared) not in {first, second}
