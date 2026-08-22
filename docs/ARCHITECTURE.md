# Architecture

A modular monolith at the application layer with separated service boundaries,
deployed as containers, per PRD section 10. Microservices were rejected
deliberately: the team is small and the domain is transactional, so premature
decomposition would cost more in operations than it returns.

## Layers

| Layer | Technology | Where |
| --- | --- | --- |
| Presentation | Next.js, React, TypeScript, Tailwind | `apps/web` |
| Application and API | FastAPI, Pydantic, SQLAlchemy, Alembic | `apps/api/app/api`, `app/services` |
| Domain rules | Pure Python, no framework | `apps/api/app/domain` |
| Records and vectors | PostgreSQL 18, pgvector, row-level security | `apps/api/alembic` |
| Documents | Object storage with object lock, MinIO | `app/services/storage.py` |
| Jobs and events | Redis, Celery, durable outbox table | `app/db/models/platform.py` |
| AI gateway | In-process, provider-neutral | `apps/api/app/ai` |

The domain layer holds no imports from FastAPI or SQLAlchemy. The state model,
the tier engine, the identifier scheme, the authority matrix and the service
clock are all plain functions, which is why they are the easiest part of the
system to test and the hardest to accidentally bypass.

## The two database roles

Migrations connect as the owner. Requests connect as `dsnlai_app`, a role the
row-level security policies apply to, with `FORCE ROW LEVEL SECURITY` set so
ownership is not an escape hatch. Every request opens one transaction and
stamps the caller's identity, entities and roles onto it with `SET LOCAL`, so a
pooled connection can never carry one caller's context into another's request.

Two helper functions run as `SECURITY DEFINER` with `row_security = off`. They
answer "can this caller see this matter" and return a boolean, disclosing no row
content. They exist because the policy for `matter_access` and the policy for
`matter` would otherwise call each other without end.

## The AI gateway

Every model call goes through `app/ai/gateway.py:invoke`. In order it: loads the
named capability, refuses if the capability is disabled, above its data class,
above its tier ceiling, or below its gate; selects a route permitted for the
data class; wraps untrusted material so it reads as evidence; calls the
provider; resolves each citation against what was actually retrieved; refuses if
nothing is attributable; and writes the interaction record whatever happened.

The model layer has no tool that can send, approve, publish, sign or alter
permissions. `FORBIDDEN_MODEL_ACTIONS` exists so that prohibition is testable
rather than merely true.

## Adding a provider

One class in `app/ai/providers.py` implementing `available()` and `complete()`,
and one row in `ROUTES` in `app/ai/routing.py` declaring the highest data class
it may carry. Nothing else changes.

## What is deliberately not built

Multi-tenancy. The platform serves two entities of one organisation, and entity
separation is the only boundary in the data model.
