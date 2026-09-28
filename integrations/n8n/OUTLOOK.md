# Connecting the legal Outlook mailbox

`legal@dsn.org` is a **shared mailbox**: no password, a disabled sign-in, and
several people reading it. That decides the whole approach. A shared mailbox
cannot sign in, so the ordinary "connect my account" flow in n8n has nothing to
connect, and hanging the connector off one member's personal account makes the
mail stop the day that person leaves.

The connector therefore authenticates as the **application**, with an Entra
policy that scopes it to that one mailbox and nothing else in the tenant.

The platform never holds a mailbox credential. n8n reads the mailbox, hands
each message to `POST /api/v1/webhooks/mail` signed with the platform's own
secret, and the platform decides everything after that: the mailbox must be on
the approved list, the message is scanned, and nothing is classified and no
matter created until Legal opens it.

Four things have to line up, and each fails differently:

| Piece | Where it lives | What a failure looks like |
| --- | --- | --- |
| The Entra application and its permission | Microsoft Entra ID | No token, or Graph answers 401 |
| The application access policy | Exchange Online PowerShell | Graph answers 403 on that mailbox |
| The n8n credential and workflow | n8n, `/workflows` | The poll runs and finds nothing |
| The approved mailbox row | The platform database | The webhook answers 422, mailbox not approved |

> A fifth thing that is **not** needed: nobody signs in, so there is no
> redirect URI, no consent screen and no refresh token to lose. Only the client
> secret expires.

---

## 1. Register the application in Entra ID

Entra admin centre, **Applications, App registrations, New registration**.

- Name: `DSN Legal Operations mail connector`
- Supported account types: **this organisational directory only**
- Redirect URI: **leave empty.** Client credentials never redirect anywhere.

Then, on the registration:

1. **Certificates and secrets, New client secret.** Copy the value at once: it
   is shown once and never again. Give it a 12 or 24 month expiry and put that
   date in a calendar, because an expired secret stops mail arriving and breaks
   nothing else, so nothing else complains.
2. **API permissions, Add a permission, Microsoft Graph, Application
   permissions:** `Mail.Read`. Add `Mail.ReadWrite` as well if the poll should
   mark a message read, which the shipped workflow does so the next pass does
   not re-fetch it.
3. **Grant admin consent** for the directory. Application permissions do
   nothing at all until this is pressed.
4. Copy the **Application (client) ID** and the **Directory (tenant) ID**.

At this point the application can read **every** mailbox in the tenant. Step 2
is what takes that away, and it is not optional.

## 2. Scope it to the one mailbox

`Mail.Read` as an application permission is tenant-wide by default. An
**application access policy** restricts it to the members of one mail-enabled
security group. Exchange Online PowerShell, as an Exchange administrator:

```powershell
Connect-ExchangeOnline

# The group exists only to name what the connector may read.
New-DistributionGroup -Name "Legal mail connector scope" `
  -Alias legal-mail-connector-scope `
  -Type Security `
  -Members legal@dsn.org

New-ApplicationAccessPolicy `
  -AppId <application (client) id> `
  -PolicyScopeGroupId legal-mail-connector-scope@dsn.org `
  -AccessRight RestrictAccess `
  -Description "Reads the legal shared mailbox only."

# Prove it, both ways.
Test-ApplicationAccessPolicy -Identity legal@dsn.org  -AppId <client id>   # Granted
Test-ApplicationAccessPolicy -Identity someone@dsn.org -AppId <client id>  # Denied
```

The policy can take up to an hour to apply. Until then Graph may still answer
for other mailboxes, which is worth knowing before concluding it did not work.

Adding a second legal mailbox later means adding it to that group, not changing
anything here.

## 3. Reach n8n

In production n8n listens on the server's loopback only, since it holds the
mailbox credential. From a workstation:

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

## 4. Add the credential

n8n, **Credentials, New, OAuth2 API** (the generic one, not the Microsoft
Outlook credential, which only does the delegated flow a shared mailbox cannot
complete).

| Field | Value |
| --- | --- |
| Grant Type | **Client Credentials** |
| Access Token URL | `https://login.microsoftonline.com/<tenant id>/oauth2/v2.0/token` |
| Client ID | The application (client) ID |
| Client Secret | The secret value from step 1 |
| Scope | `https://graph.microsoft.com/.default` |
| Authentication | **Body** |

`.default` is not a placeholder: it is the literal scope that means "every
application permission already consented for this application". Asking for
`Mail.Read` by name fails in the client-credentials flow.

Name it `Microsoft Graph, legal mailbox`. There is no sign-in step; n8n fetches
a token when a node first runs.

## 5. Set the environment and restart n8n

In the server's `.env`:

```
LEGAL_MAILBOX=legal@dsn.org
N8N_ENCRYPTION_KEY=<a generated secret>
```

`LEGAL_MAILBOX` must be the same address in three places: this variable, the
group member in step 2, and the approved list in step 6. The compose file
already passes `DSNLAI_WEBHOOK_SECRET` (the platform's own key),
`N8N_BLOCK_ENV_ACCESS_IN_NODE=false` and `NODE_FUNCTION_ALLOW_BUILTIN=crypto`,
without which the signing step fails quietly.

```bash
cd /home/azureuser/ai4legal
docker compose -f docker-compose.yml -f deploy/docker-compose.prod.yml up -d n8n
```

## 6. Import the workflow

In n8n, **Import from file**, and pick
`/workflows/outlook-shared-mailbox-poll.json` — this directory, mounted read
only inside the container. Nine nodes: the five-minute schedule, a Graph call
for unread messages in the shared mailbox's Inbox, a split, a Graph call for
each message's attachments, the shaping step, the HMAC signature, the POST to
the webhook, and a mark-as-read that runs only after the platform has the
message.

Open the three HTTP nodes (**List unread in the shared mailbox**, **Fetch the
attachments**, **Mark it read**) and select the credential from step 4.
Nothing else needs editing: the mailbox, the API address and the signing secret
all come from the environment.

`legal-mailbox-poll.json` is the delegated variant, for an ordinary personal
mailbox. It is the wrong one here.

Leave the workflow inactive until step 8 has passed.

## 7. Approve the mailbox on the platform

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

## 8. Test it once, by hand

Send a message to the shared mailbox with a PDF attached, leave it unread, then
**Execute workflow**. The hand-off node should answer:

```json
{
  "ok": true,
  "message": "1 messages accepted, 1 attachments stored, 0 refused as unapproved mailboxes, 0 quarantined for review. Nothing is classified or actioned until Legal opens it."
}
```

| What you see | What it is |
| --- | --- |
| `401` at the first Graph call | The credential: wrong tenant in the token URL, a stale secret, or the scope not `.default` |
| `403 ErrorAccessDenied` at the first Graph call | Step 2. Either the policy has not applied yet, or the mailbox is not in the group. `Test-ApplicationAccessPolicy` settles it |
| No items, no error | Nothing is unread. The poll reads unread only, so a message somebody has already opened in Outlook is invisible to it |
| `403` at the hand-off | The signature: `DSNLAI_WEBHOOK_SECRET` in n8n does not match `DSNLAI_SECRET_KEY` on the API, or the Code node could not read `$env` |
| `422`, `These mailboxes are not approved` | Step 7 was not done, or the address differs by a domain or a case |

Then open the platform's **Inbox**. The message is there, unclassified, waiting
for Legal. Activate the workflow.

## Afterwards

- **Shared mailboxes are read by people too.** The poll takes unread messages,
  so anybody opening a message in Outlook before the next pass hides it from
  the connector for good. Where that matters, point the workflow at a dedicated
  folder an Outlook rule files into, and have Legal work from the platform
  rather than from the mailbox.
- **The client secret expires.** Mail stops arriving and nothing else breaks.
  Rotating it is a new secret in step 1 and a paste into step 4. Consider a
  certificate instead, which lasts longer and never appears in a text field.
- **Marking read happens after the hand-off, never before.** A failed pass
  leaves everything unread and the next one re-reads it; the platform drops a
  repeat by `external_id`, so a double delivery costs nothing.
- **Attachments over 15 MB are dropped by the shaping step**, and the platform
  refuses anything over 50 MB. Neither loses the message.
- **What n8n may do is bounded** (PRD section 11.3, and the table in
  `README.md`): polling, notification, calendar, file movement. No legal logic,
  no model calls, no database credential, ever.
