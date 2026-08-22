"""Saved conversations for Ask memory, M10.

The control worth testing is not that a thread can be written. It is that a
thread written by one person cannot be read by another holding the same role,
because the transcript was assembled under the first person's access and a
shared role is not shared access.
"""

import uuid

from sqlalchemy import text

from app.db.session import AppSession, apply_security_context
from tests.conftest import needs_database


def _counsel_pair() -> tuple[str, str, str]:
    session = AppSession()
    try:
        apply_security_context(session, user_id=None, entities=[], roles=[], bypass=True)
        rows = session.execute(
            text(
                "SELECT DISTINCT ON (u.id) u.id::text, ue.entity_code, u.work_email "
                "FROM app_user u JOIN user_entity ue ON ue.user_id = u.id "
                "WHERE 'counsel' = ANY (u.roles) ORDER BY u.id, ue.entity_code"
            )
        ).all()
        same_entity = [r for r in rows if r[1] == rows[0][1]]
        return same_entity[0][0], same_entity[1][0], rows[0][1]
    finally:
        session.rollback()
        session.close()


@needs_database
def test_a_conversation_belongs_to_one_person_and_a_peer_in_the_same_role_cannot_read_it():
    owner, peer, entity = _counsel_pair()
    conversation_id = uuid.uuid4()

    writer = AppSession()
    try:
        apply_security_context(writer, user_id=owner, entities=[entity], roles=["counsel"])
        writer.execute(
            text(
                "INSERT INTO ai_conversation (id, entity, title, owner_id, message_count) "
                "VALUES (:id, :entity, 'Liability caps', :owner, 1)"
            ),
            {"id": conversation_id, "entity": entity, "owner": owner},
        )
        writer.execute(
            text(
                "INSERT INTO ai_conversation_turn "
                "(id, conversation_id, sequence, question, answer) "
                "VALUES (:id, :conversation, 1, 'Have we ever accepted uncapped liability?', '{}')"
            ),
            {"id": uuid.uuid4(), "conversation": conversation_id},
        )
        writer.commit()
    finally:
        writer.close()

    try:
        reader = AppSession()
        try:
            apply_security_context(reader, user_id=owner, entities=[entity], roles=["counsel"])
            assert (
                reader.execute(
                    text("SELECT count(*) FROM ai_conversation WHERE id = :id"),
                    {"id": conversation_id},
                ).scalar_one()
                == 1
            )
            assert (
                reader.execute(
                    text("SELECT count(*) FROM ai_conversation_turn WHERE conversation_id = :id"),
                    {"id": conversation_id},
                ).scalar_one()
                == 1
            )
        finally:
            reader.rollback()
            reader.close()

        intruder = AppSession()
        try:
            apply_security_context(intruder, user_id=peer, entities=[entity], roles=["counsel"])
            assert (
                intruder.execute(
                    text("SELECT count(*) FROM ai_conversation WHERE id = :id"),
                    {"id": conversation_id},
                ).scalar_one()
                == 0
            )
            # The turn carries no owner of its own. It has to be unreachable
            # through the parent, or the transcript leaks while the thread hides.
            assert (
                intruder.execute(
                    text("SELECT count(*) FROM ai_conversation_turn WHERE conversation_id = :id"),
                    {"id": conversation_id},
                ).scalar_one()
                == 0
            )
        finally:
            intruder.rollback()
            intruder.close()
    finally:
        cleanup = AppSession()
        try:
            apply_security_context(cleanup, user_id=None, entities=[], roles=[], bypass=True)
            cleanup.execute(
                text("DELETE FROM ai_conversation WHERE id = :id"), {"id": conversation_id}
            )
            cleanup.commit()
        finally:
            cleanup.close()
