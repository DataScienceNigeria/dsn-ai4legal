# Deploying the Legal Operations Platform

Images are built by GitHub Actions and pulled by the server. The server never
builds: it holds no toolchain, no source and no `node_modules`, and building
there was slow enough to be the thing that made a deploy hurt.

```
push to main ──▶ Actions builds api + web ──▶ GHCR ──▶ ssh ──▶ server pulls, migrates, restarts
```

Everything below is done once. After that a deploy is a push to `main`.

---

## 1. Azure Blob Storage

Signed agreements live here, and the platform refuses to start if it cannot
reach the container.

1. Create a storage account in the region Legal has approved, **used by nothing
   else**. Versioning is an account-level setting and immutability needs it, so
   sharing an account would turn versioning on for every other container in it,
   retaining a billed copy of every overwrite and delete. Keys, RBAC and
   lifecycle rules are account-scoped too, so anyone with rights over a shared
   account has rights over signed agreements.
2. Create a container, `ai4legal`. Leave any default retention policy
   off: the platform sets a seven-year policy on each executed copy, and an
   account-wide default would lock drafts and evidence that were never meant to
   be.
3. **Enable version-level immutability on it.** Executed copies are written
   under a seven-year retention policy, and Azure refuses that write if the
   container does not support it. Enable versioning first, then version-level
   immutability.
4. Give the server's identity the **Storage Blob Data Contributor** role on the
   container. Use a managed identity where the server is in Azure. Elsewhere,
   put a connection string in `AZURE_STORAGE_CONNECTION_STRING` and treat it as
   a secret with an expiry.

## 2. The server

Needs Docker with Compose v2, nginx, and a user in the `docker` group.

```bash
sudo mkdir -p /srv/dsn-ai4legal && sudo chown "$USER" /srv/dsn-ai4legal
git clone https://github.com/DataScienceNigeria/dsn-ai4legal.git /srv/dsn-ai4legal
cd /srv/dsn-ai4legal
cp deploy/.env.production.example .env
```

Then edit `.env` and replace every value marked `CHANGE`. Generate each secret
separately:

```bash
openssl rand -base64 48
```

Three of them stop the platform rather than degrading it, which is deliberate:

| Setting | What happens if it is wrong |
| --- | --- |
| `DSNLAI_SECRET_KEY` | Outside development the platform refuses to start while this is the key in the repository, because anybody who has read the repository could sign a token for any role |
| `DSNLAI_STORAGE_BACKEND=azure` | Refuses to start if the container cannot be reached, rather than accepting uploads it cannot keep |
| `DSNLAI_BACKUP_PASSPHRASE` | `scripts/backup.sh` refuses to run. Keep it somewhere other than this server |

`DSNLAI_ALLOWED_ORIGINS` stays **empty** with the nginx configuration below,
because one address serves both the interface and the API and there is no
cross-origin request to allow.

Lock the file down, since it holds every secret the platform has:

```bash
chmod 600 .env
```

## 3. nginx and TLS

`deploy/nginx/legal.dsnsandbox.com.conf` proxies `/api/` to the API on 8000 and
everything else to the interface on 3000. Change `server_name` if the address
differs.

```bash
sudo cp deploy/nginx/legal.dsnsandbox.com.conf /etc/nginx/sites-available/legal.conf
sudo ln -s /etc/nginx/sites-available/legal.conf /etc/nginx/sites-enabled/
sudo mkdir -p /var/www/certbot
sudo nginx -t && sudo systemctl reload nginx
sudo certbot --nginx -d legal.dsnsandbox.com
```

It sets `client_max_body_size 64m`. nginx defaults to 1 MB against a platform
limit of 50, so without it an ordinary signed agreement is refused by the proxy
with a 413 the interface never sees and cannot explain.

**Only 80 and 443 should be open.** The API, the interface, the database and
Redis are reached through nginx or not at all.

## 4. GitHub

**Repository variables** (Settings, Secrets and variables, Actions, Variables):

| Variable | Value |
| --- | --- |
| `NEXT_PUBLIC_API_BASE_URL` | `https://legal.dsnsandbox.com` |
| `PUBLIC_URL` | `https://legal.dsnsandbox.com` |

The first is inlined into the interface bundle when the image is built, so
changing it needs a rebuild rather than a restart. The build refuses to run if
it is unset, because the interface would be built calling `localhost` and would
work for nobody but somebody sitting on the server.

**Repository secrets:**

| Secret | Value |
| --- | --- |
| `DEPLOY_HOST` | The server's address |
| `DEPLOY_USER` | The deploy user |
| `DEPLOY_SSH_KEY` | Its private key, whole file including the header line |
| `DEPLOY_PATH` | `/srv/dsn-ai4legal` |

Make the key for this and nothing else:

```bash
ssh-keygen -t ed25519 -C "github-actions-deploy" -f deploy_key -N ""
ssh-copy-id -i deploy_key.pub user@server      # then paste deploy_key into the secret
rm deploy_key deploy_key.pub
```

Create an environment named `production` (Settings, Environments) and add
required reviewers if you want a deploy to wait for a person.

## 5. First run

The workflow runs migrations, but a fresh database has no organisations, no
request types and nobody to sign in as. Bootstrap it once, on the server:

```bash
cd /srv/dsn-ai4legal
COMPOSE="docker compose -f docker-compose.yml -f deploy/docker-compose.prod.yml"

read -rsp "First administrator password: " ADMIN_PASSWORD; echo
DSNLAI_ADMIN_PASSWORD="$ADMIN_PASSWORD" $COMPOSE run --rm \
  -e DSNLAI_ADMIN_PASSWORD api \
  python -m app.bootstrap --email legal.admin@dsn.org --name "Legal Administrator"
unset ADMIN_PASSWORD
```

That writes the two organisations, the request types, the capability register
with every capability unmeasured, the retention policies, the connector
register and the KPI definitions, plus one administrator. It writes **no clause
library and no templates**: house position is published by the legal lead, not
inherited from a seed.

**`python -m app.seed` is demo data and refuses to run here.** Every account it
creates shares one password that is in the repository, the administrator and
the legal lead among them.

Then sign in, enrol a second factor under Administration, and add the legal
team from the People tab.

## 6. Deploying

Push to `main`. The workflow builds both images, tags them with the commit,
pushes to GHCR, and the server pulls, migrates and restarts. It then asks the
public address for `/api/v1/health` until it answers, and says so if the answer
shows the deployment is not on Azure storage.

**Rolling back** is the same workflow run by hand: Actions, Deploy, Run
workflow, and give an earlier commit SHA as `image_tag`. The build is skipped
and the server pulls that pair. A migration is not undone by this, so a rollback
across one needs the migration considered on its own.

## 7. Afterwards

**Check the backup before you need it.** `scripts/backup.sh` writes an
encrypted archive of the database and the audit store, separately, and on Azure
leaves the documents to the container's own versioning and immutability.
`scripts/restore-drill.sh` restores into a scratch database and recomputes the
audit chain. A backup nobody has restored is a hope. Put the backup on a timer
and run the drill quarterly, which is itself a compliance item in the platform.

**Two things are configured to do nothing until you point them somewhere:**

- `DSNLAI_NOTIFY_TRANSPORT=log` writes notifications to the log and reports
  them as written to the log rather than as sent. Obligation reminders will not
  reach anybody until this is `smtp`.
- `OPENSIGN_SMTP_*` must point at a real relay. Signature links are emailed to
  people outside the organisation, and Mailpit, the mailbox that goes nowhere,
  is excluded from this deployment for that reason.

**Before real matters:** the platform's own DPIA and a penetration test are
both gates in the PRD, section 21, and neither has been done.
