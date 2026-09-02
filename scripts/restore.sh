#!/usr/bin/env bash
# Restore an encrypted archive into the running deployment, PRD section 15.
#
# This is the deliberate act that `restore-drill.sh` deliberately is not. The
# drill restores into a scratch database and drops it, so it can be run on a
# live system without touching anything. This overwrites the deployment it is
# pointed at.
#
# The audit store is restored only when asked for. It is append-only for its
# retention period, and replacing one organisation's trail with another's
# would defeat the control it exists to provide. Copying an environment for
# testing is the one case where it is the right thing to do, which is why the
# flag exists rather than the behaviour being the default.
#
#   DSNLAI_BACKUP_PASSPHRASE=... scripts/restore.sh backups/dsn-lai-....tar.gz.enc
#   DSNLAI_BACKUP_PASSPHRASE=... scripts/restore.sh --with-audit backups/....enc
#
# Requires the stack to be up: scripts/dev.sh infra, or docker compose up -d.

set -euo pipefail

WITH_AUDIT="no"
if [ "${1:-}" = "--with-audit" ]; then
  WITH_AUDIT="yes"
  shift
fi

ARCHIVE="${1:?Give the path to a .tar.gz.enc archive}"
: "${DSNLAI_BACKUP_PASSPHRASE:?Set DSNLAI_BACKUP_PASSPHRASE before restoring}"

POSTGRES_DB="${POSTGRES_DB:-dsn_lai}"
POSTGRES_USER="${POSTGRES_USER:-dsnlai_owner}"
COMPOSE="${COMPOSE:-docker compose}"
BUCKET="${MINIO_BUCKET:-dsn-lai-documents}"

WORK="$(mktemp -d)"
trap 'rm -rf "${WORK}"' EXIT

echo "Restoring ${ARCHIVE} into ${POSTGRES_DB}."
echo "This overwrites the records in that database. Ctrl-C now if that is wrong."
sleep 5

echo "Decrypting"
openssl enc -d -aes-256-cbc -pbkdf2 -iter 200000 \
  -in "${ARCHIVE}" -out "${WORK}/archive.tar.gz" \
  -pass env:DSNLAI_BACKUP_PASSPHRASE
tar -xzf "${WORK}/archive.tar.gz" -C "${WORK}"

echo "Restoring the records"
# --clean drops each object before recreating it, so a target that already
# holds a schema from `alembic upgrade head` is replaced rather than collided
# with. Errors are not fatal: the first restore into a fresh database reports
# a drop for every object that was never there.
${COMPOSE} exec -T db pg_restore --username "${POSTGRES_USER}" \
  --dbname "${POSTGRES_DB}" --clean --if-exists --no-owner --no-privileges \
  < "${WORK}/records.dump" || echo "  pg_restore reported errors; see above."

if [ "${WITH_AUDIT}" = "yes" ]; then
  echo "Restoring the audit store"
  # The trigger refuses everything but INSERT, and a restore is inserts, so it
  # passes. The table is emptied first as the owner, which is the only role
  # that may, and the reason this is not the default.
  ${COMPOSE} exec -T db psql --username "${POSTGRES_USER}" \
    --dbname "${POSTGRES_DB}" -c "TRUNCATE audit_event" >/dev/null
  ${COMPOSE} exec -T db pg_restore --username "${POSTGRES_USER}" \
    --dbname "${POSTGRES_DB}" --data-only --no-owner --no-privileges \
    --table audit_event < "${WORK}/audit.dump" \
    || echo "  the audit restore reported errors; see above."
else
  echo "Leaving the audit store alone. Pass --with-audit to replace it."
fi

echo "Restoring the object store"
tar -xf "${WORK}/objects.tar" -C "${WORK}"
${COMPOSE} exec -T minio mc alias set local http://localhost:9000 \
  "${MINIO_ACCESS_KEY:-dsn-lai-minio-access}" \
  "${MINIO_SECRET_KEY:-dsn-lai-minio-secret-dev}" >/dev/null
${COMPOSE} exec -T minio mc mb --ignore-existing "local/${BUCKET}" >/dev/null
${COMPOSE} exec -T minio rm -rf /tmp/restore >/dev/null 2>&1 || true
${COMPOSE} exec -T minio mkdir -p /tmp/restore
${COMPOSE} cp "${WORK}/objects/." minio:/tmp/restore/ >/dev/null
${COMPOSE} exec -T minio mc mirror --quiet --overwrite \
  /tmp/restore "local/${BUCKET}" >/dev/null
${COMPOSE} exec -T minio rm -rf /tmp/restore >/dev/null 2>&1 || true

echo "Checking the audit chain"
${COMPOSE} exec -T db psql --username "${POSTGRES_USER}" --dbname "${POSTGRES_DB}" \
  -At -c "select count(*) || ' audit rows' from audit_event"

echo
echo "Restored. Run the migrations once more in case the archive predates the"
echo "current head:  docker compose exec api alembic upgrade head"
