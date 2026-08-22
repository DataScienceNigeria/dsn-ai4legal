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
- Inbound mail: `POST /api/v1/webhooks/mail`
- Signature completion: `POST /api/v1/webhooks/signature`

Both webhook endpoints are signed. Compute an HMAC-SHA256 of the exact request
body using `DSNLAI_WEBHOOK_SECRET` and send it as `X-Signature`. An unsigned or
mismatched call is refused.

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
