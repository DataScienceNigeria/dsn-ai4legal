#!/usr/bin/env bash
# Quarterly restore drill, LOP-M15-US-07.
#
# A backup nobody has restored is a hope, not a recovery position. This restores
# the most recent encrypted archive into a scratch database, checks that the
# record counts and the audit chain survived, reports the elapsed time against
# the four-hour recovery objective, and then throws the scratch database away.
#
# It never touches the live database. The scratch name is fixed and distinct.
#
# Usage: scripts/restore-drill.sh [archive]

set -euo pipefail

ARCHIVE="${1:-$(ls -1t ./backups/*.enc 2>/dev/null | head -1)}"
: "${ARCHIVE:?No backup archive found. Run scripts/backup.sh first}"
: "${DSNLAI_BACKUP_PASSPHRASE:?Set DSNLAI_BACKUP_PASSPHRASE before running the drill}"

SCRATCH="dsn_lai_restore_drill"
POSTGRES_USER="${POSTGRES_USER:-dsnlai_owner}"
COMPOSE="${COMPOSE:-docker compose}"
WORK="$(mktemp -d)"
STARTED="$(date -u +%s)"
trap 'rm -rf "${WORK}"; ${COMPOSE} exec -T db dropdb --username "${POSTGRES_USER}" --if-exists "${SCRATCH}" >/dev/null 2>&1 || true' EXIT

echo "Verifying the checksum"
if [ -f "${ARCHIVE}.sha256" ]; then
  sha256sum --check --status "${ARCHIVE}.sha256" && echo "Checksum matches"
else
  echo "No checksum file beside the archive. Continuing, but record this as a finding."
fi

echo "Decrypting"
openssl enc -d -aes-256-cbc -pbkdf2 -iter 200000 \
  -in "${ARCHIVE}" -out "${WORK}/archive.tar.gz" \
  -pass env:DSNLAI_BACKUP_PASSPHRASE
tar -xzf "${WORK}/archive.tar.gz" -C "${WORK}"

echo "Creating the scratch database"
${COMPOSE} exec -T db dropdb --username "${POSTGRES_USER}" --if-exists "${SCRATCH}"
${COMPOSE} exec -T db createdb --username "${POSTGRES_USER}" "${SCRATCH}"

echo "Restoring the records"
${COMPOSE} exec -T db pg_restore --username "${POSTGRES_USER}" --dbname "${SCRATCH}" \
  --no-owner --no-privileges < "${WORK}/records.dump"

echo "Restoring the audit store"
${COMPOSE} exec -T db pg_restore --username "${POSTGRES_USER}" --dbname "${SCRATCH}" \
  --no-owner --no-privileges --data-only < "${WORK}/audit.dump"

echo
echo "Row counts in the restored copy"
${COMPOSE} exec -T db psql --username "${POSTGRES_USER}" --dbname "${SCRATCH}" -At -c "
  select 'matter', count(*) from matter
  union all select 'contract', count(*) from contract
  union all select 'document', count(*) from document
  union all select 'obligation', count(*) from obligation
  union all select 'audit_event', count(*) from audit_event
  order by 1;"

echo
echo "Audit chain check on the restored copy"
${COMPOSE} exec -T db psql --username "${POSTGRES_USER}" --dbname "${SCRATCH}" -At -c "
  with ordered as (
    select sequence, digest, previous_digest,
           lag(digest) over (order by sequence) as expected
    from audit_event
  )
  select case when count(*) = 0
    then 'The audit chain reconciles in the restored copy.'
    else count(*) || ' audit rows do not reconcile. Compare this against the same '
         || 'count on the live store: a difference means the backup lost or reordered '
         || 'events, and a match means the restore is faithful to a fault that '
         || 'predates it.'
  end
  from ordered
  where expected is not null and previous_digest is distinct from expected;"

ELAPSED=$(( $(date -u +%s) - STARTED ))
echo
echo "Restore completed in ${ELAPSED} seconds against a four-hour recovery time objective."
echo "Record the date, the archive and this output in the compliance calendar item for the drill."
