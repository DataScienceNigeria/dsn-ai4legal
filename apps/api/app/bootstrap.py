"""What a deployment needs before anyone can sign in, and nothing more.

The seed is demo data: fourteen accounts sharing one password that is in the
repository, a clause library, matters, contracts and correspondence. None of it
belongs in a real deployment, and two of those accounts are the administrator
and the legal lead.

This writes the other thing: the two organisations, the request types, the
capability register, the retention policies, the connector register, the KPI
definitions, and one administrator whose password the deployer sets. No clause
library and no templates, because house position is written by the legal team
rather than inherited from whoever wrote the seed.

    python -m app.bootstrap --email legal.admin@dsn.org --name "Legal Admin"

The password is read from DSNLAI_ADMIN_PASSWORD, never from the command line,
so it does not reach the shell history or the process list. Running it again
adds only what is missing, so it is safe to repeat after a failure.
"""

from __future__ import annotations

import argparse
import os
import sys

from sqlalchemy import func, select

from app.core.security import hash_password
from app.db.models.ai import Baseline
from app.db.models.intake import RequestType
from app.db.models.organisation import Organisation, User, UserEntity
from app.db.models.platform import Connector, RetentionPolicy
from app.db.session import owner_session
from app.domain.enums import Role

MINIMUM_PASSWORD = 12


def _empty(session, model) -> bool:
    return not session.execute(select(func.count()).select_from(model)).scalar_one()


def administrator(session, *, email: str, name: str, password: str, entities: list[str]) -> User:
    """The first account. Everything else is created from the interface."""
    existing = session.execute(
        select(User).where(User.work_email == email.lower())
    ).scalars().first()
    if existing is not None:
        return existing

    user = User(
        subject=email.lower(),
        name=name,
        work_email=email.lower(),
        password_hash=hash_password(password),
        roles=[Role.ADMIN.value],
        specialisms=[],
        workload=0,
        active=True,
    )
    session.add(user)
    session.flush()
    for entity in entities:
        session.add(UserEntity(user_id=user.id, entity_code=entity))
    session.flush()
    return user


def bootstrap(session, *, email: str, name: str, password: str, mailbox: str) -> list[str]:
    from app.seed import (
        seed_capabilities,
        seed_kpis,
        seed_organisations,
        seed_platform_config,
        seed_request_types,
    )

    written: list[str] = []

    if _empty(session, Organisation):
        seed_organisations(session)
        written.append("2 organisations, DSN and EAI")

    entities = [row.entity_code for row in session.execute(select(Organisation)).scalars()]
    admin = administrator(
        session, email=email, name=name, password=password, entities=entities
    )
    written.append(f"administrator {admin.work_email}")

    if _empty(session, RequestType):
        types = seed_request_types(session)
        written.append(f"{len(types)} request types")

    # Not guarded on emptiness: 0020 leaves one row on a fresh database, with
    # no owner and a withdrawn confirming role, and the register has to end up
    # correct rather than merely non-empty.
    seed_capabilities(session, admin)
    written.append("the capability register, every capability unmeasured")

    if _empty(session, RetentionPolicy) and _empty(session, Connector):
        seed_platform_config(session, admin, mailbox=mailbox)
        written.append("retention policies and the connector register")

    if _empty(session, Baseline):
        seed_kpis(session, with_baselines=False)
        written.append("the KPI definitions, with no baselines")

    return written


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument("--email", required=True, help="The first administrator's work email.")
    parser.add_argument("--name", required=True, help="Their name, as it appears on the record.")
    parser.add_argument(
        "--mailbox",
        default="legal@dsn.org",
        help="The legal mailbox the connector register is written against.",
    )
    arguments = parser.parse_args()

    password = os.environ.get("DSNLAI_ADMIN_PASSWORD", "")
    if len(password) < MINIMUM_PASSWORD:
        print(
            f"Set DSNLAI_ADMIN_PASSWORD to at least {MINIMUM_PASSWORD} characters. "
            "It is read from the environment rather than the command line so it "
            "does not reach the shell history or the process list.",
            file=sys.stderr,
        )
        return 1

    with owner_session() as session:
        written = bootstrap(
            session,
            email=arguments.email,
            name=arguments.name,
            password=password,
            mailbox=arguments.mailbox,
        )

    for line in written:
        print(f"  {line}")
    print(
        "\nSign in, enrol a second factor under Administration, then add the legal "
        "team from the People tab. There is no clause library or template yet: "
        "house position is published by the legal lead, not inherited from a seed."
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
