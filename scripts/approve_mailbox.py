"""Approve a mailbox from a checkout. The command itself is app.mailbox.

Kept because the path is in older notes, and because running it from the
repository root is what a developer reaches for. In a deployment the image
carries no scripts directory, so there it is:

    docker compose ... run --rm api python -m app.mailbox legal@dsn.org --entity DSN
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "apps" / "api"))

from app.mailbox import main  # noqa: E402

if __name__ == "__main__":
    raise SystemExit(main())
