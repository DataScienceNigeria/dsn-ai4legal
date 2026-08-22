"""Database engines and the per-request security context.

Two engines exist on purpose. ``owner_engine`` runs migrations and seeding and
is not subject to row-level security. ``app_engine`` serves requests as the
``dsnlai_app`` role, for which every policy applies. An application defect
therefore cannot leak across an entity or matter boundary (LOP-NFR-13).
"""

from collections.abc import Iterator
from contextlib import contextmanager

from sqlalchemy import Engine, create_engine, text
from sqlalchemy.orm import Session, sessionmaker

from app.core.config import settings

app_engine: Engine = create_engine(
    settings.app_dsn, pool_pre_ping=True, pool_size=10, max_overflow=20, future=True
)
owner_engine: Engine = create_engine(settings.owner_dsn, pool_pre_ping=True, future=True)

AppSession = sessionmaker(bind=app_engine, autoflush=False, expire_on_commit=False)
OwnerSession = sessionmaker(bind=owner_engine, autoflush=False, expire_on_commit=False)


def apply_security_context(
    session: Session,
    *,
    user_id: str | None,
    entities: list[str] | None,
    roles: list[str] | None,
    bypass: bool = False,
) -> None:
    """Set the session variables the row-level security policies read.

    ``SET LOCAL`` scopes the values to the current transaction, so a pooled
    connection can never carry one user's context into another user's request.
    """
    session.execute(
        text("SELECT set_config('dsnlai.user_id', :v, true)"), {"v": user_id or ""}
    )
    session.execute(
        text("SELECT set_config('dsnlai.entities', :v, true)"),
        {"v": ",".join(entities or [])},
    )
    session.execute(
        text("SELECT set_config('dsnlai.roles', :v, true)"), {"v": ",".join(roles or [])}
    )
    session.execute(
        text("SELECT set_config('dsnlai.bypass_rls', :v, true)"),
        {"v": "on" if bypass else "off"},
    )


@contextmanager
def owner_session() -> Iterator[Session]:
    """A session for migrations, seeding and platform maintenance."""
    session = OwnerSession()
    try:
        yield session
        session.commit()
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()
