# Connecting a Google Workspace legal mailbox

Google has no equivalent of Exchange's application access policy. That single
fact decides the approach, so read the first section before registering
anything.

The platform never holds a mailbox credential. n8n reads the mailbox, hands
each message to `POST /api/v1/webhooks/mail` signed with the platform's own
secret, and the platform decides everything after that: the mailbox must be on
the approved list, the message is scanned, and nothing is classified and no
matter created until Legal opens it.

## 0. What kind of "shared mailbox" is it

Workspace uses one phrase for two different things, and only one of them can be
polled.

| What it is | Can the Gmail API read it | What to do |
| --- | --- | --- |
| **A Google Group / collaborative inbox** (`legal@dsn.org` with no licence, members read it in Groups) | **No.** A group has no mailbox. Gmail API calls against the address fail: the account does not exist to Gmail | Either give the group a licensed Gmail account instead, or add a member account the group delivers to and poll that |
| **A licensed user account** other people delegate into (Gmail → Settings → Accounts → Grant access) | Yes | This guide |
| **An alias** on somebody's account | Yes, but you would be reading that person's whole mailbox | Don't. Make it its own account |

Check which you have: Admin console → **Directory → Groups**. If
`legal@dsn.org` is listed there and not under **Users**, it is a group and step
1 will fail with a 404 on the user.

## 1. Choose how it authenticates

Two routes, and the security difference is larger than it looks.

| | **A. OAuth2 as the mailbox account** | **B. Service account with domain-wide delegation** |
| --- | --- | --- |
| What it can read | That one mailbox | **Every mailbox in the domain.** There is no way to narrow it |
| Needs | To sign in to the account once: password and its second factor | An admin to authorise the client ID once |
| Breaks when | The account's password or 2SV changes, or the token is revoked | Nothing routine |
| Suits | A shared mailbox somebody can still sign in to | An account nobody signs in to |

**Prefer A.** The whole point of the Exchange access policy in `OUTLOOK.md` is
that the connector can reach one mailbox and no other, and on Google only route
A gives that. Take route B only if signing in is genuinely impossible, and then
treat the service account key as the most sensitive credential in the
deployment: its own Google Cloud project, used by nothing else, key held by the
same people who hold the database password.

---

## Route A: OAuth2 as the mailbox account

### A1. Create the OAuth client

[Google Cloud console](https://console.cloud.google.com), a project of its own.

1. **APIs and services → Library → Gmail API → Enable.**
2. **OAuth consent screen.** User type **Internal** (Workspace only, so no
   verification and no test-user expiry). App name
   `DSN Legal Operations mail connector`.
3. **Scopes:** `https://www.googleapis.com/auth/gmail.readonly` and
   `https://www.googleapis.com/auth/gmail.modify`. The second is what lets the
   poll mark a message read so the next pass does not re-fetch it.
4. **Credentials → Create credentials → OAuth client ID → Web application.**
   Authorised redirect URI:
   `http://localhost:15678/rest/oauth2-credential/callback`

   That is the n8n editor as it is reached: in production, an SSH tunnel from
   local port 15678 to the server's loopback. It must equal `N8N_EDITOR_URL`
   in the server's `.env` plus `rest/oauth2-credential/callback`, because n8n
   builds the redirect from that variable. 15678 rather than 5678 because
   Windows often reserves 5678 for Hyper-V and refuses the tunnel with
   "Permission denied". Google accepts plain `http` for `localhost` only.
5. Copy the **Client ID** and **Client secret**.

### A2. Connect it in n8n

Reach n8n first (`ssh -L 15678:127.0.0.1:5678 azureuser@<server>`, then
`http://localhost:15678`). The login is the n8n owner's email; `N8N_USER` and
`N8N_PASSWORD` are ignored by n8n 1.x. If nobody knows the owner,
`docker compose ... exec n8n n8n user-management:reset` and a restart bring
back the setup screen with workflows and credentials intact.

**Credentials → New → Gmail OAuth2 API.** Paste the client ID and secret, press
**Connect my account**, and sign in **as `legal@dsn.org` itself** — not as an
administrator, and not as a member who has delegate access. A delegate's token
reads the delegate's own mailbox, which is the quiet way this ends up ingesting
the wrong inbox.

n8n stores a refresh token, so this is done once.

---

## Route B: service account with domain-wide delegation

Only where nobody can sign in to the mailbox.

### B1. The service account

1. Google Cloud console, **a dedicated project**. **Enable the Gmail API.**
2. **IAM and admin → Service accounts → Create.** Name it
   `legal-mail-connector`. No project roles are needed: the authority comes
   from the domain delegation, not from IAM.
3. **Keys → Add key → JSON.** Download it once. This file is a credential for
   every mailbox in the domain until the delegation is narrowed or removed.
4. Copy the service account's **Unique ID** (the numeric client ID) and its
   email.

### B2. The delegation

Admin console → **Security → Access and data control → API controls →
Domain-wide delegation → Add new**.

- Client ID: the numeric unique ID from B1
- OAuth scopes, comma separated:
  `https://www.googleapis.com/auth/gmail.readonly,https://www.googleapis.com/auth/gmail.modify`

This is the step that grants access to every user's mail. Record who approved
it and why, because it is the kind of grant an audit asks about.

### B3. The credential in n8n

**Credentials → New → Google Service Account API.**

| Field | Value |
| --- | --- |
| Service Account Email | From the JSON, `client_email` |
| Private Key | From the JSON, `private_key`, including the BEGIN and END lines |
| Impersonate a User | **on** |
| Email | `legal@dsn.org` |

Impersonation is what points the delegation at the one mailbox that should be
read. Getting it wrong reads somebody else's mail with no error.

---

## 2. The rest, both routes

### 2a. Set the environment and restart n8n

In the server's `.env`:

```
LEGAL_MAILBOX=legal@dsn.org
N8N_ENCRYPTION_KEY=<a generated secret>
```

`LEGAL_MAILBOX` must be the same address in three places: this variable, the
account connected or impersonated above, and the approved list below. The
compose file already passes `DSNLAI_WEBHOOK_SECRET`,
`N8N_BLOCK_ENV_ACCESS_IN_NODE=false` and `NODE_FUNCTION_ALLOW_BUILTIN=crypto`,
without which the signing step fails quietly.

```bash
cd /home/azureuser/ai4legal
docker compose -f docker-compose.yml -f deploy/docker-compose.prod.yml up -d n8n
```

### 2b. Import the workflow

**Import from file → `/workflows/gmail-shared-mailbox-poll.json`**, this
directory mounted read only inside the container. Seven nodes: the five-minute
schedule, the Gmail read of unread inbox mail with attachments, the shaping
step, the HMAC signature, the POST to the webhook, and a mark-as-read that runs
only after the platform has the message.

Open the two Gmail nodes (**Read the shared mailbox**, **Mark it read**) and
set **Authentication** to match the route taken, then pick the credential.
Nothing else needs editing.

`gmail-mailbox-poll.json` is the older IMAP variant. It needs an app password,
which Workspace increasingly refuses, and it cannot mark read reliably. Prefer
the API workflow.

### 2c. Approve the mailbox on the platform

```bash
cd /home/azureuser/ai4legal
COMPOSE="docker compose -f docker-compose.yml -f deploy/docker-compose.prod.yml"
$COMPOSE run --rm api python -m app.mailbox legal@dsn.org --entity DSN
$COMPOSE run --rm api python -m app.mailbox --list
```

Skip this and the webhook refuses every message and records the attempt.

### 2d. Test it once, by hand

Send a message with a PDF to the mailbox, leave it unread, **Execute
workflow**. The hand-off node should answer:

```json
{
  "ok": true,
  "message": "1 messages accepted, 1 attachments stored, 0 refused as unapproved mailboxes, 0 quarantined for review. Nothing is classified or actioned until Legal opens it."
}
```

| What you see | What it is |
| --- | --- |
| `404` / "Requested entity was not found" | The address is a Google Group, not a mailbox. Back to section 0 |
| `403 insufficientPermissions` | The scope. `gmail.modify` is missing, or on route B the delegation lists a different scope string |
| `401 unauthorized_client` (route B) | The delegation client ID does not match the service account's unique ID, or the impersonated address is wrong |
| Mail from the wrong mailbox | Signed in as a delegate rather than as the account, or impersonating the wrong address |
| No items, no error | Nothing is unread. The query is `is:unread in:inbox` |
| `403` at the hand-off | The signature: `DSNLAI_WEBHOOK_SECRET` in n8n does not match `DSNLAI_SECRET_KEY` on the API, or the Code node could not read `$env` |
| `422`, `These mailboxes are not approved` | Step 2c, or the address differs by a domain or a case |

Then open the platform's **Inbox**. The message is there, unclassified, waiting
for Legal. Activate the workflow.

## Afterwards

- **People read this mailbox too.** The poll takes unread messages, so anybody
  opening one in Gmail before the next pass hides it from the connector. Where
  that matters, give the workflow a label an incoming filter applies and query
  `label:to-platform` instead of `is:unread`.
- **Binary mode matters.** With `N8N_DEFAULT_BINARY_DATA_MODE=filesystem` n8n
  writes attachments to disk and the shaping step cannot read them, so it skips
  them silently. The default mode is the one that works.
- **Route B is not narrowed by anything.** Revoking it is one row in the
  domain-wide delegation table, and that is the only control there is.
- **What n8n may do is bounded** (PRD section 11.3, and the table in
  `README.md`): polling, notification, calendar, file movement. No legal logic,
  no model calls, no database credential, ever.
