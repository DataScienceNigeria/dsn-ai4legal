# n8n workflows

n8n is plumbing, not the platform. This boundary is stated explicitly because it
is the most likely place for architectural drift (PRD section 11.3).

| Permitted here | Not permitted here |
| --- | --- |
| Mail polling and hand-off to the platform API | Legal decision logic, tier assignment, approval routing |
| Notification fan-out to Teams, Chat, email, SMS | Storing the only copy of any legal record |
| Calendar event creation and updates | Direct model calls that bypass the AI gateway |
| File movement between the platform and Drive or SharePoint | Direct database writes |
| Scheduled triggers that call platform endpoints | Holding credentials outside the secret manager |
| Small transformations and format conversion in transit | Sending any substantive external communication |

## How a workflow talks to the platform

Every call goes to the API. There is no database credential in n8n, and there
never should be.

- Base address inside the compose network: `http://api:8000`
- Base address while the API runs on the host with reload:
  `http://host.docker.internal:8000`
- Inbound mail: `POST /api/v1/webhooks/mail`
- Signature completion: `POST /api/v1/webhooks/signature`

Both addresses are read from `DSNLAI_API_BASE_URL`, so a workflow should use
that expression rather than a literal one. `docker-compose.override.yml` points
it at the host gateway during development, because the `api` container is not
running then and `api:8000` resolves to nothing. Start n8n on its own with
`docker compose up -d --no-deps n8n`.

Both webhook endpoints are signed. Compute an HMAC-SHA256 of the exact request
body using `DSNLAI_WEBHOOK_SECRET` and send it as `X-Signature`. An unsigned or
mismatched call is refused.

## What the container has to be given

Four environment variables, all set in `docker-compose.override.yml` for local
development. Three of them fail quietly rather than loudly, which is worth
knowing before an hour goes into the wrong place.

| Variable | Why |
| --- | --- |
| `DSNLAI_API_BASE_URL` | Where the platform is. `api:8000` in the built stack, the host gateway during development |
| `DSNLAI_WEBHOOK_SECRET` | The signing key. A wrong one is a 403 from the webhook, not an error in n8n |
| `LEGAL_MAILBOX` | The mailbox being read. It has to match a row on the approved list or every message is refused |
| `N8N_BLOCK_ENV_ACCESS_IN_NODE=false` | Code nodes read `$env`. Blocked, the secret reads as undefined and the signature simply fails to verify |
| `NODE_FUNCTION_ALLOW_BUILTIN=crypto` | Code nodes run in an isolated VM with no built-ins. Without this, signing fails with "Module 'crypto' is disallowed" |

## Reading a real mailbox

A mailbox with twenty thousand messages and thousands unread will not survive a
bare `["UNSEEN"]` search: the IMAP node pulls every match, with attachments,
into memory in one pass, and the execution dies out of memory without ever
saying so plainly. Bound the search, and prefer a dedicated folder or label
over somebody's whole inbox, which is what "read named mailboxes only" means in
practice.

- `customEmailConfig` takes node-imap search criteria, so
  `["UNSEEN", ["SINCE", "28-Aug-2026"]]` narrows it to a date
- **Fetch Only New Emails** stops the backlog being re-swept, and needs the
  node at version 2.1 or later. Pinned at 2, the option is not applied and
  nothing says why

## Mail ingest payload

```json
{
  "messages": [
    {
      "external_id": "AAMkAGI2...",
      "mailbox": "legal@dsn.example",
      "sender": "adaeze.obi@kanopartners.example",
      "subject": "Partnership, next steps",
      "body": "Please conclude the partnership before 18 August.",
      "received_at": "2026-08-20T09:14:00Z",
      "participants": [{ "name": "Adaeze Obi", "address": "adaeze.obi@kanopartners.example" }]
    }
  ]
}
```

The platform refuses any mailbox that is not on the approved list, records the
attempt, and scans every message for instruction-like content before it is
stored. Nothing is classified, and no matter is created, until Legal opens it.

## Importing

Open n8n at `http://localhost:5678`, then import from `/workflows` inside the
container, which is this directory mounted read only.
