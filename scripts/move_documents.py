"""Move every document from one storage backend to another.

    apps/api/.venv/bin/python scripts/move_documents.py --to azure
    apps/api/.venv/bin/python scripts/move_documents.py --to azure --source /path/to/folder

Reads from a local folder, by default the one DSNLAI_STORAGE_PATH names, and
writes to the backend given, with that backend's own settings from .env. Keys
are kept exactly, so every storage key in the database still resolves.

An executed copy is written under the destination's immutability policy, the
same as when it was first stored; the database says which documents those are.
Every file is read back from the destination and its hash compared before it is
counted, and nothing is deleted from the source. Running it again skips what is
already there and matches, so an interrupted move is resumed rather than redone.
"""

from __future__ import annotations

import argparse
import hashlib
import pathlib
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1] / "apps" / "api"))

from sqlalchemy import create_engine, text  # noqa: E402

from app.core.config import settings  # noqa: E402
from app.services import storage  # noqa: E402


def digest(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def immutable_keys() -> set[str]:
    engine = create_engine(settings.owner_dsn)
    with engine.connect() as connection:
        rows = connection.execute(
            text("SELECT storage_key FROM document WHERE immutable AND storage_key IS NOT NULL")
        )
        return {row[0] for row in rows}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument("--to", required=True, choices=["azure", "local"])
    parser.add_argument("--source", default=settings.dsnlai_storage_path)
    parser.add_argument("--target-path", help="Destination folder when --to is local")
    arguments = parser.parse_args()

    source = storage.LocalStore(pathlib.Path(arguments.source))
    if arguments.to == "local":
        if not arguments.target_path:
            parser.error("--target-path is required when moving to a folder.")
        target: storage.LocalStore | storage.AzureStore = storage.LocalStore(
            pathlib.Path(arguments.target_path)
        )
    else:
        target = storage.AzureStore()
    target.verify()

    keys = source.keys()
    locked = immutable_keys()
    existing = set(target.keys())
    moved = skipped = 0
    failed: list[str] = []

    for key in keys:
        data = source.get(key)
        expected = digest(data)
        try:
            if key in existing and digest(target.get(key)) == expected:
                skipped += 1
                continue
            content_type = storage.sniff(data) or "application/octet-stream"
            if key in locked:
                target.put_immutable(key, data, content_type, retain_years=7)
            else:
                target.put(key, data, content_type)
            if digest(target.get(key)) != expected:
                failed.append(f"{key}: the copy read back does not match")
                continue
            moved += 1
        except Exception as exc:
            failed.append(f"{key}: {exc}")

    print(f"{len(keys)} documents in {arguments.source}")
    print(f"{moved} moved, {skipped} already there and matching, {len(failed)} failed")
    for line in failed:
        print(f"  {line}")
    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
