"""Load test against the PRD section 17 targets.

Three claims are tested, each at the scale the PRD names rather than at the
scale the demonstration dataset happens to be:

  the matter list stays under 3 seconds at p95 with 5,000 matters
  search stays under 2 seconds at p95 over the same corpus
  deterministic generation stays under 90 seconds at p95

The matters are inserted directly, because the point is to measure reading at
scale rather than to measure the intake path 5,000 times. They are inserted
under a load-test prefix and removed again unless --keep is given, so a real
dataset is never left with test rows in it.

Run it against a deployment you are allowed to load. It writes 5,000 rows.

    python scripts/loadtest.py --matters 5000 --requests 60
"""

from __future__ import annotations

import argparse
import concurrent.futures
import json
import statistics
import sys
import time
import urllib.error
import urllib.request
from dataclasses import dataclass, field

PREFIX = "LOADTEST"

TARGETS = {
    "matter list": 3.0,
    "search": 2.0,
    "generation": 90.0,
}


@dataclass
class Timing:
    name: str
    target: float
    samples: list[float] = field(default_factory=list)
    failures: int = 0

    @property
    def p95(self) -> float:
        if not self.samples:
            return float("inf")
        ordered = sorted(self.samples)
        index = min(len(ordered) - 1, round(0.95 * (len(ordered) - 1)))
        return ordered[index]

    @property
    def passed(self) -> bool:
        return self.failures == 0 and self.p95 <= self.target

    def line(self) -> str:
        if not self.samples:
            return f"{self.name}: no sample was taken."
        return (
            f"{self.name}: p95 {self.p95:.2f}s against a target of {self.target:.0f}s, "
            f"median {statistics.median(self.samples):.2f}s, "
            f"n={len(self.samples)}, failures={self.failures} "
            f"[{'pass' if self.passed else 'FAIL'}]"
        )


def call(
    base: str, path: str, token: str, entity: str, body: dict | None = None
) -> float:
    data = json.dumps(body).encode() if body is not None else None
    headers = {"Authorization": f"Bearer {token}", "X-Entity": entity}
    if data is not None:
        headers["Content-Type"] = "application/json"
    request = urllib.request.Request(f"{base}/api/v1{path}", data=data, headers=headers)
    started = time.perf_counter()
    with urllib.request.urlopen(request, timeout=180) as response:
        response.read()
    return time.perf_counter() - started


def read(base: str, path: str, token: str, entity: str):
    request = urllib.request.Request(
        f"{base}/api/v1{path}",
        headers={"Authorization": f"Bearer {token}", "X-Entity": entity},
    )
    with urllib.request.urlopen(request, timeout=60) as response:
        return json.loads(response.read())


def generation_target(base: str, token: str, entity: str) -> tuple[str, dict] | None:
    """Find a matter and an approved template that can actually generate.

    Measuring generation against a proxy would report a number that says
    nothing about the assembly path, so the real endpoint is called or the
    measurement is skipped and said to be skipped.
    """
    templates = [
        template
        for template in read(base, "/templates", token, entity)
        if template.get("current") and template["current"].get("status") == "approved"
    ]
    matters = [
        matter
        for matter in read(base, "/matters", token, entity)
        if matter.get("counterparty")
    ]
    if not templates or not matters:
        return None

    # The generator refuses where a declared variable has no value, which is
    # correct behaviour rather than a fault. The measurement supplies them so
    # what is being timed is assembly rather than the refusal path.
    supplied_by_the_matter = {
        "matter_number",
        "our_entity",
        "counterparty",
        "counterparty_jurisdiction",
        "effective_date",
        "governing_law",
        "value_amount",
        "value_currency",
        "privacy_flag",
    }
    facts: dict[str, object] = {"value_amount": 25_000_000, "value_currency": "NGN"}
    for variable in templates[0]["current"].get("variables") or []:
        name = variable.get("name")
        if not name or name in supplied_by_the_matter:
            continue
        facts[name] = "Load test value"

    return "/documents/generate", {
        "template_reference": templates[0]["current"]["reference"],
        "matter_id": matters[0]["id"],
        "facts": facts,
        "name": f"{PREFIX} generation probe",
    }


def sign_in(base: str, email: str, password: str, code: str | None) -> str:
    body = json.dumps({"email": email, "password": password, "code": code}).encode()
    request = urllib.request.Request(
        f"{base}/api/v1/auth/token",
        data=body,
        headers={"Content-Type": "application/json"},
    )
    try:
        with urllib.request.urlopen(request, timeout=30) as response:
            return json.loads(response.read())["access_token"]
    except urllib.error.HTTPError as exc:
        detail = exc.read().decode("utf-8", "replace")
        raise SystemExit(f"Sign-in failed: {detail}") from exc


def seed(count: int, entity: str) -> int:
    """Insert matters directly, in one transaction, under the load-test prefix."""
    from datetime import UTC, datetime, timedelta

    from app.db.models.counterparty import Counterparty
    from app.db.models.matter import Matter
    from app.db.models.organisation import User
    from app.db.session import owner_session
    from app.domain.enums import MatterState, RiskTier
    from sqlalchemy import func, select

    with owner_session() as session:
        existing = session.execute(
            select(func.count())
            .select_from(Matter)
            .where(Matter.title.like(f"{PREFIX}%"))
        ).scalar_one()
        if existing >= count:
            print(f"{existing} load-test matters are already present.")
            return existing

        counterparty = session.execute(select(Counterparty)).scalars().first()
        owner = session.execute(select(User)).scalars().first()
        tiers = [tier.value for tier in RiskTier]
        states = [MatterState.DRAFTING.value, MatterState.IN_REVIEW.value]
        now = datetime.now(UTC)

        for index in range(existing, count):
            session.add(
                Matter(
                    number=f"{entity}-LT-{now.year}-{index:06d}",
                    entity=entity,
                    title=(
                        f"{PREFIX} services agreement {index}, "
                        "limitation of liability and payment terms"
                    ),
                    practice_code="COM",
                    risk_tier=tiers[index % len(tiers)],
                    status=states[index % len(states)],
                    counterparty_id=counterparty.id if counterparty else None,
                    responsible_lawyer_id=owner.id if owner else None,
                    sla_started_at=now - timedelta(days=index % 400),
                    value_amount=1_000_000 + index,
                    value_currency="NGN",
                )
            )
            if index % 500 == 0:
                session.flush()
        session.flush()
        total = session.execute(
            select(func.count())
            .select_from(Matter)
            .where(Matter.title.like(f"{PREFIX}%"))
        ).scalar_one()
    print(f"{total} load-test matters are in place.")
    return total


def remove() -> int:
    from app.db.models.matter import Matter
    from app.db.session import owner_session
    from sqlalchemy import delete, select

    with owner_session() as session:
        ids = list(
            session.execute(select(Matter.id).where(Matter.title.like(f"{PREFIX}%")))
            .scalars()
        )
        if ids:
            session.execute(delete(Matter).where(Matter.id.in_(ids)))
    print(f"Removed {len(ids)} load-test matters.")
    return len(ids)


def measure(
    base: str,
    token: str,
    entity: str,
    paths: list[str],
    repeats: int,
    workers: int,
    body: dict | None = None,
) -> tuple[list[float], int]:
    samples: list[float] = []
    failures = 0
    work = [paths[index % len(paths)] for index in range(repeats)]

    with concurrent.futures.ThreadPoolExecutor(max_workers=workers) as pool:
        futures = [pool.submit(call, base, path, token, entity, body) for path in work]
        for future in concurrent.futures.as_completed(futures):
            try:
                samples.append(future.result())
            except Exception as exception:  # noqa: BLE001
                failures += 1
                print(f"  a call failed: {exception}", file=sys.stderr)
    return samples, failures


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--base", default="http://localhost:8000")
    parser.add_argument("--email", default="adaeze.okafor@dsn.example")
    parser.add_argument("--password", default="Lop-Demo-2026")
    parser.add_argument("--code", default=None, help="Second factor, where enrolled.")
    parser.add_argument("--entity", default="EAI")
    parser.add_argument("--matters", type=int, default=5000)
    parser.add_argument("--requests", type=int, default=60)
    parser.add_argument("--workers", type=int, default=8)
    parser.add_argument("--keep", action="store_true", help="Leave the rows behind.")
    parser.add_argument("--clean", action="store_true", help="Remove the rows and stop.")
    arguments = parser.parse_args()

    if arguments.clean:
        remove()
        return 0

    seed(arguments.matters, arguments.entity)
    token = sign_in(arguments.base, arguments.email, arguments.password, arguments.code)

    results = [
        Timing("matter list", TARGETS["matter list"]),
        Timing("search", TARGETS["search"]),
        Timing("generation", TARGETS["generation"]),
    ]

    print(f"\nMeasuring with {arguments.requests} calls each, {arguments.workers} at a time.")

    results[0].samples, results[0].failures = measure(
        arguments.base,
        token,
        arguments.entity,
        ["/matters", "/matters?status=drafting", "/matters?tier=tier_2"],
        arguments.requests,
        arguments.workers,
    )
    results[1].samples, results[1].failures = measure(
        arguments.base,
        token,
        arguments.entity,
        [
            "/contracts?q=liability",
            "/contracts?q=payment",
            "/contracts?q=indemnity",
        ],
        arguments.requests,
        arguments.workers,
    )
    # Generation is deterministic, so repeated calls with the same facts
    # return the same hash and the same document. The assembly, the clause
    # resolution, the consistency checks and the hashing all still run.
    target = generation_target(arguments.base, token, arguments.entity)
    if target is None:
        print(
            "\nNo approved template and linked matter pair exists, so generation "
            "was not measured. That is a gap in the dataset, not a pass."
        )
        results[2].failures = 1
    else:
        path, body = target
        results[2].samples, results[2].failures = measure(
            arguments.base,
            token,
            arguments.entity,
            [path],
            max(10, arguments.requests // 3),
            min(4, arguments.workers),
            body=body,
        )

    print()
    for result in results:
        print(result.line())

    if not arguments.keep:
        print()
        remove()

    failed = [result for result in results if not result.passed]
    if failed:
        print(f"\n{len(failed)} targets were missed.")
        return 1
    print("\nEvery target was met.")
    return 0


if __name__ == "__main__":
    sys.path.insert(0, "apps/api")
    raise SystemExit(main())
