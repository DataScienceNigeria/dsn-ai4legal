"""Test fixtures.

The isolation tests need a real PostgreSQL with the policies applied, because
the control being tested is the database policy rather than any application
code. They are skipped when no database is reachable.
"""

import pytest
from sqlalchemy import text

from app.db.session import app_engine


def _database_available() -> bool:
    try:
        with app_engine.connect() as connection:
            connection.execute(text("SELECT 1"))
        return True
    except Exception:
        return False


needs_database = pytest.mark.skipif(
    not _database_available(), reason="No database is reachable."
)
