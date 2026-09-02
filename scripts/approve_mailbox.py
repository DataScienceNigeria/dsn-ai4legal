"""Put a mailbox on the approved list, or take one off.

The list is the ingest control: the webhook refuses anything not on it and
records the attempt. There is no screen for it yet, and adding one is a
decision about who may open an ingest route rather than a form, so it lives
here where the act is deliberate and leaves an audit row like every other
change.

    python scripts/approve_mailbox.py legal@dsn.example --entity DSN
    python scripts/approve_mailbox.py legal@dsn.example --off
    python scripts/approve_mailbox.py --list
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "apps" / "api"))

from sqlalchemy import select  # noqa: E402

from app.core import audit  # noqa: E402
from app.db.models.governance import Mailbox  # noqa: E402
from app.db.session import owner_session  # noqa: E402


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("address", nargs="?", help="The mailbox address.")
    parser.add_argument("--entity", default="DSN", choices=["DSN", "EAI"])
    parser.add_argument("--provider", default="microsoft_graph")
    parser.add_argument("--off", action="store_true", help="Deactivate rather than approve.")
    parser.add_argument("--list", action="store_true", help="Show the list and stop.")
    args = parser.parse_args()

    with owner_session() as session:
        if args.list or not args.address:
            rows = session.execute(select(Mailbox).order_by(Mailbox.address)).scalars().all()
            if not rows:
                print("No mailbox is approved. Nothing can be ingested.")
            for row in rows:
                state = "active" if row.active else "off"
                polled = row.last_polled_at.isoformat() if row.last_polled_at else "never polled"
                print(f"{row.address:40} {row.entity}  {state:6} {polled}")
            return 0

        address = args.address.strip().lower()
        record = session.execute(
            select(Mailbox).where(Mailbox.address == address)
        ).scalar_one_or_none()

        before = None if record is None else {"active": record.active, "entity": record.entity}
        if record is None:
            record = Mailbox(
                address=address,
                entity=args.entity,
                provider=args.provider,
                scopes=[f"Mail.Read on {address}"],
                active=not args.off,
            )
            session.add(record)
        else:
            record.active = not args.off
            record.entity = args.entity

        audit.record(
            session,
            action="mailbox_deactivated" if args.off else "mailbox_approved",
            object_type="mailbox",
            object_id=address,
            actor_label="approve_mailbox.py",
            entity=args.entity,
            before_state=before,
            after_state={"active": record.active, "entity": record.entity},
        )
        session.commit()
        print(f"{address} is {'off' if args.off else 'approved for ' + args.entity}.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
