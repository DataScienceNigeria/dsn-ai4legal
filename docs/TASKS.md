# Live task list

Updated as work closes. `[x]` done, `[~]` in progress, `[ ]` not started.
Plan and rationale: [BUILD-PLAN.md](BUILD-PLAN.md).

Last updated: Phase G closed. Built, containerised, running and scanned.

The stack runs as seven containers: `db`, `redis`, `minio`, `api`, `worker`,
`web` and `n8n`. All seven report healthy, and the API serves 116 paths.

SonarQube, project `dsn-lai`: 0 bugs, 0 vulnerabilities, reliability A,
security A, maintainability A, 0 percent duplication, 108 smells across 18,179
lines, and 0 violations on new code.

One quality gate condition fails and stays failing by decision: `new_coverage`
is 23.0 against a threshold of 80. That threshold and the instruction to write
at most one or two tests per feature cannot both be met. Coverage sits between
79 and 100 percent on the domain and AI modules, which is what PRD section 16.2
actually asks for. Ahmad has decided to leave the gate alone.

Two security hotspots remain open. Hotspots are review items rather than
defects, and marking them reviewed needs a SonarQube account with the
permission this token does not carry. They are for Ahmad to clear in the
SonarQube interface.

Verified against the running stack:

- Entity separation holds. A DSN member sees no EAI matter and the reverse.
- A restricted matter is visible to the counsel named on it and absent for one
  who is not, in the list, and in retrieval.
- The audit store rejected a TRUNCATE from the application role.
- Generation is byte-identical across runs, and a conditional section changes the hash.
- With no model route configured, a grounded capability refuses rather than answers.
- A legal hold blocks deletion for every role, and lifting it is audited.
- Neither a bulk export nor a deletion can be approved by the person who raised it.
- Restricted content is refused for bulk export outright.
- An approved deletion issues a certificate carrying its own digest.
- A Word template imports as candidates whose decision is pending, never as
  house position.
- A cross-entity report is permitted only for a role holding both entities, and
  the request is written to the audit trail.

## Standing rules

- `CLAUDE.md` at the repository root carries Ahmad's rules. Read it before each
  batch of work. Current rules: no unnecessary comments in code, no em dashes,
  shadcn with dark mode, and colour from `docs/DESIGN_TOKENS.md`.
- Update this file as each task closes, in the same batch as the work.
- Update `WALKTHROUGH.md` in the same batch as any code change. It is the
  living zero to one hundred guide, and a stale one is worse than none.

## Phase A, foundation

- [X] A1 Monorepo layout, gitignore, environment template
- [X] A2 Domain vocabulary, PRD sections 5.2, 8.2, 9.2, 14.1, 14.3
- [X] A3 Matter state machine, PRD section 8.2
- [X] A4 Identifier scheme, PRD section 8.3
- [X] A5 Risk tier engine, PRD section 14.2
- [X] A6 Service clock, LOP-M02-US-04
- [X] A7 Declarative base, two engines, security context
- [X] A8 Data model, organisation, users, configuration
- [X] A9 Data model, counterparty and vendor
- [X] A10 Data model, requests, request types, attachments
- [X] A11 Data model, matters, transitions, decisions, access
- [X] A12 Data model, clause and template library, playbooks
- [X] A13 Data model, documents, findings, suggestions
- [X] A14 Data model, contracts, approvals, signature, obligations
- [X] A15 Data model, communications, assessments, compliance
- [X] A16 Data model, AI capability register and interactions
- [X] A17 Data model, audit events, outbox, idempotency, retrieval index
- [X] A18 Alembic migration, schema
- [X] A19 Alembic migration, row-level security policies
- [X] A20 Security, token issue and verify, roles, step-up
- [X] A21 Request context, dependencies, error contract
- [X] A22 Immutable audit trail, LOP-M15-US-03
- [X] A23 Idempotency keys on every mutating request, PRD section 12.1
- [X] A24 Object storage service, MinIO with object lock
- [X] A25 Docker Compose, database, cache, object store, api, web, worker

## Phase B, the spine

- [X] B1 M01 request types as configuration, conditional fields
- [X] B2 M01 request submission, mandatory-field blocking, acknowledgment
- [X] B3 M01 attachments, type and size checks, scan, storage
- [X] B4 M01 requester status timeline
- [X] B5 M02 triage queue, tier and owner proposal
- [X] B6 M02 matter acceptance, identifier issue, SLA start
- [X] B7 M02 transitions endpoint against the state model
- [X] B8 M02 decision log
- [X] B9 M02 matter linking, reassignment, restricted matters
- [X] B10 M03 clause and template versions, fallbacks, authority
- [X] B11 M03 change proposal, differences, atomic publication
- [X] B12 M03 review dates and staleness
- [X] B13 M04 deterministic assembly, conditional sections
- [X] B14 M04 content hash, reproduction, refusal rules
- [X] B15 M04 docx and PDF rendering
- [X] B16 M07 approval chains, resolution, hash binding
- [X] B17 M07 invalidation on edit, reminders, escalation
- [X] B18 M07 signature request, webhook, cancellation, wet ink
- [X] B19 M08 executed archive, immutability, authoritative record
- [X] B20 M08 obligation proposal, confirmation, tasks
- [X] B21 M08 reminders, renewals, evidence, calendar feed
- [X] B22 M08 search across the archive

## Phase C, the AI layer

- [X] C1 Capability register, gates, kill switch, shadow mode
- [X] C2 Model routing by data class, PRD section 13.4
- [X] C3 Provider adapters, OpenAI, self-hosted, offline
- [X] C4 Response envelope, PRD section 12.3
- [X] C5 Retrieval, permission filtered before ranking
- [X] C6 Clause-aware chunking and indexing on normal work
- [X] C7 Deterministic consistency checks, LOP-M05-US-05
- [X] C8 Untrusted input handling, PRD section 13.7
- [X] C9 M05 AI first draft with clause provenance
- [X] C10 M05 in-place iteration on a selected clause
- [X] C11 M06 playbook comparison, severity ranking, absent clauses
- [X] C12 M06 suggested response per finding, clearance rules
- [X] C13 M06 tracked-change redline output
- [X] C14 M09 classification, extraction, recommended next step
- [X] C15 M09 implied work watch view, deadline and silence escalation
- [X] C16 M10 cited answers, refusal without a source
- [X] C17 M10 position history and counterparty view
- [X] C18 AI interaction logging, cost, latency, human decision

## Phase D, governance and reporting

- [X] D1 M11 assessment workflow, stages, captured fields
- [X] D2 M11 residual risk decision, conditions as tasks, reassessment
- [X] D3 M12 compliance calendar, evidence, versioned requirements
- [X] D4 M13 counterparty identity, duplicate detection, merge
- [X] D5 M13 vendor governance and renewal risk
- [X] D6 M14 operational dashboard from lifecycle events
- [X] D7 M14 KPI page against baseline and target
- [X] D8 M14 AI usage and quality report
- [X] D9 M14 weekly update generation

## Phase E, the interface

- [X] E1 Next.js scaffold, design tokens from DESIGN_TOKENS.md, shadcn primitives, dark mode
- [X] E2 Application shell, navigation, entity switch, theme
- [X] E3 Portal, request type selection
- [X] E4 Portal, guided form with conditional questions
- [X] E5 Portal, data involvement declaration
- [X] E6 Portal, confirmation and status timeline
- [X] E7 Workspace, delivery dashboard
- [X] E8 Workspace, triage queue
- [X] E9 Workspace, triage detail with tier and owner proposals
- [X] E10 Workspace, matters list
- [X] E11 Workspace, matter detail, overview, approvals, AI trace
- [X] E12 Workspace, document with SuperDoc, modes, versions, suggestions
- [X] E13 Workspace, templates and clause library
- [X] E14 Workspace, review and redlining
- [X] E15 Workspace, executed archive
- [X] E16 Workspace, obligations
- [X] E17 Workspace, inbox intelligence
- [X] E18 Workspace, institutional memory chat
- [X] E19 Workspace, assessments
- [X] E20 Workspace, AI capabilities and kill switch

## Phase F, verification

- [X] F1 Test, state machine transitions and reasons
- [X] F2 Test, tier derivation, highest tier wins
- [X] F3 Test, generation determinism by hash
- [X] F4 Test, entity separation and restricted-matter isolation
- [X] F5 Test, AI envelope rejects an ungrounded output
- [X] F6 Test, approval invalidation on document edit
- [X] F7 Seed data, two entities, library, matters, inbox, obligations
- [X] F8 Run the stack, migrate, seed, smoke the API and the interface
- [X] F9 SonarQube scan, both applications
- [X] F10 Triage SonarQube findings
- [X] F11 README and architecture notes

## Phase G, PRD gap closure

Found by a story-by-story review of PRD section 7 against the running build.

- [x] G1 M01 free-text request fallback that routes to triage, LOP-M01-US-01
- [x] G2 M03 Word template import, proposed clause breakdown, provenance, LOP-M03-US-07
- [x] G3 M04 tier 1 auto-issue pipeline and monthly quality sample, LOP-M04-US-04
- [x] G4 M05 house style engine and style report, LOP-M05-US-03
- [x] G5 M06 deviation pattern reporting, LOP-M06-US-06
- [x] G6 M14 risk and exposure report, LOP-M14-US-03
- [x] G7 M08 renewal decision capture, renew, renegotiate, terminate, lapse, LOP-M08-US-04
- [x] G8 M09 deadline and silence sweep in the worker, LOP-M09-US-06
- [x] G9 M09 accuracy per classification category in the AI quality report, LOP-M09-US-07
- [x] G10 M12 controlled requirement versioning with effective date, LOP-M12-US-04
- [x] G11 M15 legal hold, deletion request, second approval, deletion certificate, LOP-M15-US-04
- [x] G12 M15 bulk export record, second approver, rate limit, LOP-M15-US-05
- [x] G13 M14 cross-entity reporting behind an explicit permission, logged, LOP-M14-US-06
- [x] G14 M15 backup and restore drill, LOP-M15-US-07
- [x] G15 Alembic migration for the Phase G tables
- [x] G16 Web, metrics and exposure screen, M14
- [x] G17 Web, compliance calendar screen, M12
- [x] G18 Web, counterparty and vendor screen, M13
- [x] G19 Web, administration screen, config, users, connectors, retention, exports, audit, M15
- [x] G20 Web, portal free-text fallback
- [x] G21 API and web container images, full stack up
- [x] G22 n8n service, mailbox workflow, signed ingest, environment template
- [x] G23 Tests, one per new major feature
- [x] G24 SonarQube rescan

## Phase H, the interface

Raised after review on a 1920 wide display, where the whole interface read as
though it had been designed for a laptop and then shrunk.

- [x] H1 Type scale. The Tailwind scale had been overridden downward, so body
      copy was 12.5px and metadata 10px. Restored to the standard scale and
      moved to rem
- [x] H2 Fluid root size, 16px at 1280 wide rising to 17.5px at 1920, so the
      whole interface tracks the display instead of the browser default
- [x] H3 Controls resized to match: buttons 32 and 36 high, inputs 40, pills 24,
      table rows and card padding to suit
- [x] H4 Table column widths and pane widths converted from px to rem so they
      scale with the type rather than crowding it
- [x] H5 Responsive shell. Sidebar at lg and above, a drawer below it, closing
      on navigation and on escape
- [x] H6 Content capped at a readable width and centred, so a wide display
      gains margin rather than line length
- [x] H7 Tables scroll inside their own box, headers stay stuck while scrolling,
      and the page never scrolls sideways
- [x] H8 Navigation icons replace the PRD module codes, which were build
      traceability rather than anything a user needs. The code survives as the
      link title
- [x] H9 Navigation grouped into the work, knowledge, governance and platform
- [x] H10 Role-aware navigation. Each item declares the roles the endpoint
      behind it accepts, and a role sees only what it can use
- [x] H11 Requesters are sent to the portal rather than a workspace that would
      refuse every screen in it
- [x] H12 Role gates inside screens: the kill switch, clause proposals, and
      authority to concede on a review finding
- [x] H13 Accessibility. A skip link, focus-visible rings, real touch targets,
      aria-current on the active link, and reduced-motion honoured

## Phase I, the write paths in the interface

The API accepts 125 operations. The interface drove 70 of them, and almost
every one it drove was a read. Phase I closes that: every action the API
permits is now reachable from a screen, gated by the role the endpoint accepts.

- [x] I1 Interface primitives: a modal dialog, a confirmation dialog, a
      multipart upload helper and a query-string builder in the API client
- [x] I2 Documents. Generate from a template on the matter, download the file,
      verify the stored hash against the object
- [x] I3 AI actions. First draft, counterparty paper review, redline against
      the house position, obligation extraction, and the accept, reject or
      correct decision on any interaction
- [x] I4 Approvals and signature. Approve or reject a step, request signature,
      cancel a signature request, record wet-ink execution
- [x] I5 Matters. Restrict and unrestrict, override the tier, reassign the
      responsible lawyer, link a related matter, tier 1 auto-issue
- [x] I6 Library. Propose a clause version, propose a template version, publish
      or reject a pending version, read the diff, open a clause, a template and
      a playbook in full
- [x] I7 Template import. Upload a Word template, review proposed clauses,
      accept or reject each candidate
- [x] I8 Assessments. Open one in full, complete a stage, close with a residual
      risk decision, trigger reassessment
- [x] I9 Compliance. Version a requirement with an effective date, read the
      version history
- [x] I10 Counterparties. Create a counterparty, merge a duplicate, read the
      position history for a clause category
- [x] I11 Obligations. Open a renewal task, record the renewal decision, decide
      an extracted value
- [x] I12 Inbox. Correct a classification the model got wrong
- [x] I13 Portal. Attach a file to a request
- [x] I14 Administration. Read and change configuration, record an evaluation
      result, review a monthly quality sample

## Phase J, the integrations behind the stand-ins

Each of these shipped as a working stand-in. Phase J puts the real thing behind
the same interface, so the stand-in stays as the fallback when the connector is
not configured.

- [x] J1 OIDC. JWKS verification behind `DSNLAI_AUTH_MODE`, so a federated
      token from Keycloak, Entra ID or Google Workspace is accepted and mapped
      onto the role model
- [x] J2 Multi-factor authentication. TOTP enrolment, verification, and a
      step-up that demands a factor rather than a password
- [x] J3 SCIM 2.0. Users and Groups provisioning so joiners, movers and leavers
      arrive from the directory
- [x] J4 E-signature. A DocuSeal provider behind the existing signature
      interface, with the internal simulation kept as the fallback
- [x] J5 Notification delivery. SMTP and outbound webhook transports behind the
      outbox, replacing the log-only delivery
- [x] J6 Malware scanning. A ClamAV transport behind `scan_upload`, with the
      magic-byte heuristic kept as the fallback
- [x] J7 Embeddings. A real embedding model behind `embed`, with the
      deterministic hash kept as the fallback and the dimension pinned

## Phase K, the evaluation regime

PRD section 16 requires a measured gate, not a declared one. The register
carries gates and thresholds; nothing measured them.

- [x] K1 Golden set storage: a set per capability, cases with an input and an
      expected answer, versioned and owned
- [x] K2 The harness. Runs a capability over its golden set, scores it by the
      metric the register names, and records the result
- [x] K3 The gate. A capability whose last measured score is below the gate
      refuses, and the schedule re-measures on a cadence

## Phase L, proving it

- [x] L1 Load test against the PRD section 17 targets, 5,000 matters
- [x] L2 Execute the restore drill and record the result
- [x] L3 Tests for the new work, one per feature
- [x] L4 SonarQube rescan, zero new violations. 0 bugs, 0 vulnerabilities,
      A for reliability, security and maintainability, 0.1 per cent
      duplication, coverage read correctly at 29.6 per cent. Two gate
      conditions still fail and both are outside the code: `new_coverage`, by
      Ahmad's decision, and `new_security_hotspots_reviewed`, which needs three
      hotspots marked reviewed in the SonarQube interface because the token
      returns "Insufficient privileges" on the hotspots API
- [x] L5 WALKTHROUGH.md brought up to date


## Phase M, after the walkthrough

- [x] **M1** Tell the two organisations apart by colour. `data-entity` on the
      root element beside the `dark` class, DSN neutral and EqualyzAI shifted a
      few points towards green, in both light and dark. Set before the first
      paint so the page never renders in the wrong organisation's colour, and
      backed by a coloured mark on the name and on the switch so the cue does
      not rest on a faint background alone. The sidebar and its navigation
      headings take the organisation's brand hue outright, blue for DSN and
      green for EqualyzAI, and `--heading` carries that hue to every page
      title as well
- [x] **M2** Configuration for every Phase J integration written into `.env`
      and `.env.example`. DocuSeal, SMTP and the signed webhook, ClamAV, the
      embedding provider, the TOTP settings and the OIDC claim mapping were all
      read by `config.py` and named in neither file, so the only way to find a
      key was to read the settings class
- [x] **M3** Sticky table header fixed. It sat 4rem below its own row and the
      first record showed through the gap, because `.table-scroll` is the
      scrollport, not the viewport
- [x] **M4** Sign out carries an icon and is red. It was a ghost button that
      read as one more piece of header furniture
- [x] **M5** The sidebar retracts to a 4.25rem icon rail, remembered per
      browser. Every item stays reachable collapsed; only the words go
- [x] **M6** Ask memory rebuilt as a real chat. `ai_conversation` and
      `ai_conversation_turn` behind it, threads listed in the window,
      self-naming titles, rename and delete, follow-up questions that resolve
      against the thread, and a per-owner row-level security policy so a
      colleague in the same role cannot read the transcript
- [x] **M7** The request form asks which organisation before anything else.
      It was inheriting whichever entity the workspace happened to be on, which
      is not a safe default for a choice that cannot be changed afterwards
- [x] **M8** A number field carries a unit. "How long should it run" was a bare
      box that could have meant weeks, months or years
- [x] **M9** The portal has exits. Its own navigation, a return to the
      workspace for anyone with one, a sign out, a cancel on the form that says
      nothing has been sent, a confirmation on every stored attachment, and a
      finish on the submitted page
- [x] **M10** Every figure on the delivery dashboard links to the records
      behind it, with the filter in the query string so the link travels
- [x] **M11** Triage shows the request on the page it is decided on, in two
      columns
- [x] **M12** Returning and closing in triage both demand a note. The API
      refuses an empty one, closing now tells the requester why, and its
      optional answer is kept on the request record
- [x] **M13** The originating request shows on the matter as well, above the
      tabs, as one shared component. It omits what the matter header and record
      card already say, and drops any answer whose text is already on the page
- [x] **M14** Seeded matters carry the request they were accepted from. The
      seed built every matter with none, so the panel was blank on all of them
      and the feature looked entity-specific when it was only ever data. The
      existing database was backfilled with the same content rather than
      reseeded
- [x] **M15** Switching organisation closes an open record and returns to that
      organisation's list, instead of leaving a matter on screen that the next
      read would refuse

## What is left, stated plainly

Phases I to M are closed. These are not:

- Word and Google Docs round-trip, LOP-M04-US-05. SuperDoc gives in-app DOCX
  editing; opening in Word while keeping the version link is not built.
- Teams and Google Chat request links, LOP-M01-US-08, priority S.
- Mailbox polling has never run against a real Microsoft Graph or Gmail
  account. The n8n workflow and the signed ingest endpoint both exist.
- Three SonarQube security hotspots need marking reviewed in the SonarQube
  interface. The scanner token returns "Insufficient privileges" on the
  hotspots API, so this cannot be done from here.
- Four historical audit rows do not reconcile and are being left that way. The
  chain forked before it was fixed; rewriting an append-only store to make the
  check pass would defeat the control the check exists to provide.
