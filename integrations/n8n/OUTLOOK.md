# Connecting the legal Outlook mailbox

The platform never holds a mailbox credential. n8n reads the mailbox, hands
each message to `POST /api/v1/webhooks/mail` signed with the platform's own
secret, and the platform decides everything after that: the mailbox must be on
the approved list, the message is scanned, nothing is classified and no matter
is created until Legal opens it.

Three things have to line up, and each fails differently:

| Piece | Where it lives | What a failure looks like |
| --- | --- | --- |
| The Entra application and its permission | Microsoft Entra ID | n8n cannot sign in, or Graph answers 403 |
| The n8n credential and workflow | n8n, `/workflows` | The poll runs and finds nothing |
| The approved mailbox row | The platform database | The webhook answers 200 with every message refused |

---

## 1. Register the application in Entra ID

Entra admin centre, **Applications, App registrations, New registration**.

- Name: `DSN Legal Operations mail connector`
- Supported account types: **this organisational directory only**
- Redirect URI: **Web**, `http://localhost:5678/rest/oauth2-credential/callback`

That address is the n8n editor as it is reached, which in production is an SSH
tunnel to the server's loopback. Entra accepts plain `http` for `localhost`
and for nothing else. If n8n is ever fronted by its own hostname, the redirect
URI becomes `https://<that host>/rest/oauth2-credential/callback` and both the
registration and `WEBHOOK_URL` change together.

Then, on the registration:

1. **Certificates and secrets, New client secret.** Copy the value at once: it
   is shown once. Give it a 12 or 24 month expiry and put the expiry date in
   the calendar, because a silently expired secret stops mail arriving without
   stopping anything else.
2. **API permissions, Add a permission, Microsoft Graph, Delegated:**
   `Mail.Read`, `Mail.ReadWrite`, `offline_access`, `User.Read`.
   `Mail.ReadWrite` is what lets the poll mark a message read so the next pass
   does not re-fetch it; without it use a date-bounded filter instead.
3. **Grant admin consent** for the directory. Without it the first sign-in asks
   the user for consent they are usually not allowed to give.
4. Copy the **Application (client) ID** and the **Directory (tenant) ID**.

## 2. Reach n8n

In production n8n listens on the server's loopback only. From a workstation:

```bash
ssh -L 5678:127.0.0.1:5678 azureuser@<server>
```

Then open `http://localhost:5678`. On first visit n8n asks for an owner
account: use a real address and keep the password with the other secrets.

Locally it is `http://localhost:5678` directly, with n8n started on its own
while the API runs on the host:

```bash
docker compose up -d --no-deps n8n
```

## 3. Add the credential

n8n, **Credentials, New, Microsoft Outlook OAuth2 API**.

| Field | Value |
| --- | --- |
| Client ID | The application (client) ID |
| Client Secret | The secret value from step 1 |
| Tenant / Authorisation URL | The directory (tenant) ID, where the credential asks for one |

Press **Connect my account** and sign in **as the legal mailbox account
itself**, not as an administrator. The workflow reads
`https://graph.microsoft.com/v1.0/users/{{ $env.LEGAL_MAILBOX }}/messages`, and
with a delegated token that path only resolves for the signed-in account.
Signing in as somebody else is the single most common way this ends in a 403
that looks like a permission problem.

n8n stores a refresh token, so this is done once. Re-doing it is what a client
secret expiry looks like.

## 4. Set the environment and restart n8n

In the server's `.env`:

```
LEGAL_MAILBOX=legal@dsn.org
N8N_ENCRYPTION_KEY=<a generated secret>
```

`LEGAL_MAILBOX` has to be the same address in three places: this variable, the
account signed in at step 3, and the approved list in step 6. The compose file
already passes `DSNLAI_WEBHOOK_SECRET` (the platform's own key),
`N8N_BLOCK_ENV_ACCESS_IN_NODE=false` and `NODE_FUNCTION_ALLOW_BUILTIN=crypto`,
without which the signing step fails quietly.

```bash
cd /home/azureuser/ai4legal
docker compose -f docker-compose.yml -f deploy/docker-compose.prod.yml up -d n8n
```

## 5. Import the workflow

In n8n, **Import from file**, and pick `/workflows/legal-mailbox-poll.json`,
which is this directory mounted read only inside the container. It has six
nodes: a five-minute schedule, the Outlook read, a Graph call for the
attachments, a shaping step, the HMAC signature, and the POST to the webhook.

Open the two Outlook-credentialed nodes (**Read the approved mailbox** and
**Fetch the attachments**) and select the credential from step 3. Nothing else
needs editing: the mailbox, the API address and the secret all come from the
environment.

Leave it inactive until step 7 has passed.

## 6. Approve the mailbox on the platform

The webhook refuses any mailbox not on the list and records the attempt, so
this is what stands between an ingest route and an unregistered one:

```bash
cd /home/azureuser/ai4legal
COMPOSE="docker compose -f docker-compose.yml -f deploy/docker-compose.prod.yml"
$COMPOSE run --rm api python -m app.mailbox legal@dsn.org --entity DSN
$COMPOSE run --rm api python -m app.mailbox --list
```

`--entity` decides which organisation's records the correspondence lands in,
and `--off` takes a mailbox back out without deleting anything it brought in.

## 7. Test it once, by hand

Send a message to the mailbox with a PDF attached, then **Execute workflow** in
n8n. Read the last node's answer:

```json
{
  "ok": true,
  "message": "1 messages accepted, 1 attachments stored, 0 refused as unapproved mailboxes, 0 quarantined for review. Nothing is classified or actioned until Legal opens it."
}
```

- **422**, `These mailboxes are not approved`, means step 6 was not done, or the
  address differs from `LEGAL_MAILBOX` by a domain or a case. Where some
  messages land and others are refused the call still answers 200 and the
  message says how many; the refusals are in the audit trail as
  `mailbox_ingest_refused`.
- `403` at the last node is the signature: `DSNLAI_WEBHOOK_SECRET` in n8n does
  not match `DSNLAI_SECRET_KEY` on the API, or the Code node could not read
  `$env`.
- Nothing at all from the Outlook node means the filter: it reads unread
  messages only, so a message already opened in Outlook is invisible to it.

Then open the platform's **Inbox**. The message is there, unclassified, waiting
for Legal. Activate the workflow.

## Afterwards

- **A real mailbox is large.** The poll takes 25 unread messages a pass. Point
  it at a dedicated folder rather than a person's whole inbox, which is what
  "named mailboxes only" means in practice.
- **The client secret expires.** Mail stops arriving and nothing else breaks,
  which is why the expiry belongs in a calendar rather than in a memory.
- **Attachments over 15 MB are dropped by the shaping step**, and the platform
  refuses anything over 50 MB. Neither loses the message.
- **What n8n may do is bounded** (PRD section 11.3, and the table in
  `README.md`): polling, notification, calendar, file movement. No legal logic,
  no model calls, no database credential, ever.
