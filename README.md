# DSN Legal AI

The legal operations platform for Data Science Nigeria and EqualyzAI.

One rule sits above every other requirement, and it is enforced in code rather
than asked for in a prompt: **AI may recommend, an authorised human must
confirm.** No component can independently give legal advice, accept risk,
approve a contract, sign a document, or send a substantive external
communication.

## Running it

Everything runs as a container. One command brings up the database, cache,
object store, API, worker, interface and n8n, migrating and seeding on first
start:

```bash
cp .env.example .env
docker compose up -d --build
```

| Service    | Address               | What it is                                   |
| ---------- | --------------------- | -------------------------------------------- |
| `web`    | http://localhost:3004 | The interface                                |
| `api`    | http://localhost:8000 | FastAPI, OpenAPI at`/api/v1/docs`          |
| `worker` | no port               | Celery worker and beat, the scheduled sweeps |
| `n8n`    | http://localhost:5678 | Plumbing only, mailbox polling               |
| `db`     | localhost:5434        | PostgreSQL 18 with pgvector                  |
| `minio`  | http://localhost:9101 | Object store console                         |

Sign in as `adaeze.okafor@dsn.example` with the password `Lop-Demo-2026`. Other
seeded accounts are listed on the sign-in page and show the same platform under
different roles.

`NEXT_PUBLIC_API_BASE_URL` is inlined into the web bundle at image build time,
so it has to be an address the browser can reach, not a container name. Change
it and rebuild the web image rather than restarting it.

To work on the code directly instead, the infrastructure runs in containers and
the two applications run on the host with reload, which is the only arrangement
where a change shows up without a rebuild.

```bash
scripts/dev.sh
```

That starts the containers, migrates, seeds if the database is empty, and
brings up the API, the Celery worker and the interface. It prints every address
and writes a log per process to `.dev/`. `scripts/dev.sh stop` stops the host
processes and leaves the containers running; `scripts/dev.sh infra` brings up
only the containers.

The first run needs the two toolchains installed:

```bash
cd apps/api
uv venv --python 3.12 .venv
uv pip install -e ".[dev]"
cp ../../.env .env

cd ../web
npm install
```

Three things about this arrangement are worth knowing.

The **API container stays down**. It would hold port 8000 against the host
process, and the two serve different builds. The same applies to the web
container and port 3004: do not run both.

**n8n starts with `--no-deps`**, because its compose dependency is the API
container that is deliberately not running. `docker-compose.override.yml`
points it at `host.docker.internal:8000` so a workflow reaches the API that is
actually up.

The **worker is not optional** for anything on a schedule: the inbox watch,
obligation reminders, the evaluation sweep and the outbox all live there.

## Backup and restore

`scripts/backup.sh` writes an encrypted archive of the database, the audit
store and the object store. `scripts/restore-drill.sh` restores the most recent
archive into a scratch database, checks the row counts and the audit chain, and
reports the elapsed time against the four-hour recovery objective. Both need
`DSNLAI_BACKUP_PASSPHRASE` in the environment. The drill is quarterly and is
tracked as a compliance item.

## The AI layer

OpenAI is the commercial provider. With no `OPENAI_API_KEY` set the gateway
falls back to an offline adapter that **refuses rather than answers**, so every
screen is exercisable with no external call and no spend. That refusal is the
correct behaviour, not a degraded one: an output without sources is a failed
call.

Restricted content never reaches a commercial provider; it goes to a self-hosted model or nowhere.

## Controls you can verify

Each of these is a test or a database policy rather than a claim.

| Control                                      | Where it lives                                                                       |
| -------------------------------------------- | ------------------------------------------------------------------------------------ |
| Entity separation and restricted matters     | PostgreSQL row-level security,`alembic/versions/0003`, `tests/test_isolation.py` |
| Append-only audit trail                      | Table grant plus a trigger, with a chained digest per row                            |
| Deterministic generation                     | `tests/test_generation.py`, byte-identical archive output                          |
| Approval binds to a content hash             | `tests/test_approvals.py`                                                          |
| Grounding, routing and no-action             | `tests/test_ai_envelope.py`                                                        |
| Tier derivation and authority to concede     | `tests/test_tiering.py`, `app/domain/enums.py`                                   |
| House style is enforced, not suggested       | `tests/test_phase_g.py`, `app/services/style.py`                                 |
| Tier 1 auto-issue stops at any deviation     | `tests/test_phase_g.py`, `app/services/autoissue.py`                             |
| Imported clauses arrive as proposals         | `tests/test_phase_g.py`, `app/services/docx_import.py`                           |
| Nobody approves their own export or deletion | `app/api/v1/admin.py`, refused by user identity                                    |
| A legal hold outranks every role             | `app/api/v1/admin.py`, refused before the request is written                       |

```bash
cd apps/api && .venv/bin/pytest tests/ -q
```

## Licence note

The document editing surface uses SuperDoc, which is AGPL-3.0. That is
compatible with internal use. If the platform is ever distributed, or offered
to an external organisation as a hosted service, the AGPL network clause
applies and a commercial licence should be taken before that happens.
