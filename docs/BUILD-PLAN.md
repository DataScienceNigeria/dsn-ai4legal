# Build plan, Legal Operations Platform

Traceability: every item below cites the PRD section or requirement ID it
satisfies. Design fidelity is taken from the two Claude Design canvases, which
supply 14 workspace screens and 6 portal screens.

## 1. Scope decision

The PRD specifies fifteen modules, M01 to M15. This build delivers all of them
as one running system. The platform is single-tenant for DSN and EqualyzAI. It
is not a multi-tenant product, and nothing in the data model, the permission
model or the deployment carries a tenant dimension. Entity, meaning DSN or
EqualyzAI, is the only separation boundary and it is enforced in the database.

Three PRD choices are deliberately substituted for a self-contained build, and
each keeps the seam the PRD asks for:

| PRD choice | Built as | Why |
| --- | --- | --- |
| Keycloak federating Entra ID and Google Workspace | A local token issuer, with `DSNLAI_AUTH_MODE` reserved for the OIDC path | Federation needs two live identity providers. The role model and step-up re-authentication are implemented. The OIDC verifier, MFA and SCIM are not: `DSNLAI_AUTH_MODE` only refuses local sign-in, and there is no JWKS verification behind it. |
| LiteLLM proxy in front of four providers | In-process gateway with the same routing contract and three adapters: OpenAI, a self-hosted open-weights model, and an offline fallback | Routing policy by data class is the control that matters, and it is enforced in the platform rather than delegated. Adding a provider is one class. |
| DocuSeal, n8n | Signature and connector services behind interfaces, with a working internal implementation and signed webhook endpoints | The platform is the write path either way (PRD section 12.1). |

## 2. Architecture

Modular monolith, per PRD section 10, deployed as containers.

```
apps/web    Next.js 15, React, TypeScript, Tailwind, shadcn anatomy over the DSN palette
apps/api    FastAPI, Pydantic, SQLAlchemy, Alembic
            PostgreSQL 18 with pgvector and row-level security
            Redis with Celery, plus a durable outbox table
            MinIO for objects, with object lock for executed copies
```

## 3. Work breakdown

### Phase A, foundation
1. Monorepo, Docker Compose, environment template, SonarQube configuration.
2. Data model, PRD section 9.1, all 19 record types.
3. Row-level security policies for entity separation and restricted matters
   (LOP-NFR-13, LOP-M02-US-08). The application connects as a role the policies
   apply to; migrations connect as the owner. Entity is the separation boundary,
   and it is the only one.
4. Identity, roles, entity scoping, MFA step-up, immutable audit trail (M15).

### Phase B, the spine
5. M01 intake: request types as configuration, conditional fields, mandatory-field
   blocking, attachments, privacy declaration, 60-second acknowledgment, status timeline.
6. M02 matters: triage queue, tier proposal, owner proposal, state machine,
   SLA clock, decision log, matter linking, restricted matters.
7. M03 library: clause and template versions, ranked fallbacks with authority
   levels, proposal and atomic publication, review dates, entity scoping.
8. M04 generation: deterministic merge, conditional sections, byte-identical
   reproduction, content hash, refusal when the record is not ready.
9. M07 approvals and signature: configurable chains, hash binding, invalidation
   on edit, escalation, execution, wet-ink fallback.
10. M08 archive and obligations: immutable executed record, proposed obligations
    for confirmation, reminders, renewal windows, evidence, calendar, search.

### Phase C, the AI layer
11. AI gateway: capability register, routing by data class, kill switch, shadow
    mode, gates from section 4.2, full interaction logging. OpenAI is the
    commercial provider.
12. Response envelope, PRD section 12.3, including `unsupported_segments`.
13. Grounding and retrieval, permission-filtered before ranking, hybrid keyword
    plus vector, clause-aware chunking.
14. M05 drafting, M06 redlining, M09 inbox, M10 memory, each with the human
    confirmation their capability register row requires.
15. Prompt injection handling: ingested content is data, never instruction;
    no capability can send, approve, publish or sign.

### Phase D, governance and reporting
16. M11 assessments, M12 compliance calendar, M13 counterparty and vendor.
17. M14 reporting: operational dashboard, KPI page, AI quality report, weekly update.

### Phase E, the interface
18. Portal, 6 screens: request type selection, guided form, data declaration,
    confirmation, generation preview, AI first draft.
19. Workspace, 14 screens: delivery, triage, triage detail, matters, matter,
    document, templates, review, archive, obligations, inbox, memory,
    assessment, capabilities.

### Phase F, verification
20. Tests, one or two per major feature, as instructed: state machine, tier
    engine, generation determinism, entity separation and restricted-matter
    isolation, AI envelope grounding, authority to concede.
21. SonarQube scan of both applications, findings triaged.

## 4. Non-negotiable rules carried into the code

These are enforced in the platform, not in prompts.

1. AI may recommend, an authorised human must confirm. The model layer has no
   tool that sends, approves, publishes a clause version, or signs.
2. An AI output without sources is a failed call, not a low-confidence answer.
3. Only the approved clause library is presented as house position. Novel text
   is marked as novel and unapproved everywhere it appears.
4. Retrieval filters by entity, role and matter access before ranking.
5. Generation is deterministic and reproducible by content hash.
6. Approval binds to a document hash, and any edit invalidates it.
7. A capability below its gate does not run.

## 5. Phase G, PRD gap closure

Phases A to F delivered the fifteen modules end to end. A story-by-story review
against PRD section 7 found seventeen acceptance criteria that were modelled in
the data layer but not carried through to a working path, plus four screens the
PRD asks for that the design canvases did not cover. Phase G closes them.

| Gap | PRD | What was missing |
| --- | --- | --- |
| Free-text intake | LOP-M01-US-01 | The portal listed request types with no fallback for a requester whose need does not match one. |
| Template import | LOP-M03-US-07 | No path from an existing Word template to a proposed clause breakdown with provenance. |
| Tier 1 auto-issue | LOP-M04-US-04 | `tier_1_auto_issue` was configuration with nothing reading it. |
| House style | LOP-M05-US-03 | `style_report` was a column with no engine behind it. |
| Deviation patterns | LOP-M06-US-06 | No view of which clauses are challenged most, by whom, with what outcome. |
| Risk and exposure | LOP-M14-US-03 | Reporting covered operations, KPIs and AI quality, not exposure. |
| Renewal decisions | LOP-M08-US-04 | The renewal window was computed but the decision was never captured. |
| Deadline and silence | LOP-M09-US-06 | `awaiting_response_since` was recorded and never swept. |
| Module accuracy | LOP-M09-US-07 | Correction rate was global, not per classification category. |
| Requirement versions | LOP-M12-US-04 | The columns existed with no endpoint to create a superseding version. |
| Retention and deletion | LOP-M15-US-04 | Read-only policies, no hold, no deletion request, no certificate. |
| Bulk export | LOP-M15-US-05 | The endpoint acknowledged an approval that nothing recorded or granted. |
| Cross-entity reporting | LOP-M14-US-06 | Entity scoping was absolute, so the permitted cross-entity view did not exist. |
| Disaster recovery | LOP-M15-US-07 | No backup or restore drill. |
| Four screens | M12, M13, M14, M15 | Compliance, counterparty and vendor, metrics and exposure, administration. |

Two further items are deployment rather than product: the API and web
applications now build as containers, and n8n runs as a service with the
mailbox workflow that posts to the signed ingest endpoint.


## 6. Phases I to L, closing the interface, the integrations and the gate

Phase G closed the PRD gaps in the API. What the audit after it found was that
the interface drove 70 of 125 operations and almost everything it drove was a
read: the backend was close to the PRD, and the interface covered reading it
far better than driving it.

| Phase | What it closed |
| --- | --- |
| I | Every write path the API permits is now reachable from a screen, role-gated, with the platform's refusal shown as a refusal. 144 operations, and the only ones without a screen are the two webhooks, the SCIM endpoints and the health check, none of which have a user |
| J | The integrations behind the stand-ins: OIDC verification against the issuer's keys, TOTP with recovery codes, SCIM 2.0, DocuSeal, SMTP and webhook delivery, ClamAV, and a hosted embedding model. Each keeps its stand-in as the fallback, and each stand-in reports what it actually did |
| K | The evaluation regime. Golden sets per capability, a harness that runs a capability over its set and scores it by the metric the register names, and a weekly sweep. The gate disables a capability that falls below it |
| L | Proving it: a load test at 5,000 matters against the section 17 targets, an executed restore drill, tests, and a SonarQube rescan |

### What running the checks found

Writing a test is not the same as running one. Phase L found five faults that
reading the code had not:

1. The seeded MSA template referenced three clause versions that were never
   created, so neither template could generate at all.
2. Concurrent generation created four copies of the same document, because the
   idempotency check was advisory and nothing enforced it.
3. `dsnlai_document_immutable` returned `NEW` on a DELETE, which is NULL, so
   every deletion of a non-immutable document silently did nothing and reported
   success.
4. The audit chain forked, because `record` read the previous digest before its
   own row was written, and `verify_chain` ordered by a clock that ties.
5. The backup script had a bucket name that did not match the platform's,
   aborted on an empty object store, and called a `tar` the MinIO image does
   not carry. It had never been run.

Four are fixed in code and migrations. The fifth, the audit chain, is fixed
going forward: the historical digests were left exactly as they are, because
rewriting an append-only store to make a check pass would defeat the control
the check exists to provide.

### What is still not built

Stated plainly, so nothing here is a surprise:

- Word and Google Docs round-trip, LOP-M04-US-05. SuperDoc gives in-app DOCX
  editing; opening in Word while keeping the version link is not built.
- Teams and Google Chat request links, LOP-M01-US-08, priority S.
- Live mailbox polling has been shipped as an n8n workflow and signed ingest
  endpoint, but never run against a real Microsoft Graph or Gmail account.
- Three SonarQube security hotspots need marking reviewed in the interface. The
  scanner token returns "Insufficient privileges" on the hotspots API.
- The `new_coverage` gate condition fails by decision.
