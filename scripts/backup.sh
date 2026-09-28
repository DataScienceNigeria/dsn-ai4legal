#!/usr/bin/env bash
# Encrypted backup of the database, the documents and the audit store,
# LOP-M15-US-07 and PRD section 15.
#
# The audit store is dumped separately from the rest of the database. It is
# append-only for its retention period, so a restore that quietly replaced it
# would defeat the control it exists to provide: keeping it in its own file
# makes restoring it a deliberate act.
#
# Usage: scripts/backup.sh [destination]
# Requires DSNLAI_BACKUP_PASSPHRASE in the environment.

set -euo pipefail

DESTINATION="${1:-./backups}"
STAMP="$(date -u +%Y%m%dT%H%M%SZ)"
WORK="$(mktemp -d)"
trap 'rm -rf "${WORK}"' EXIT

: "${DSNLAI_BACKUP_PASSPHRASE:?Set DSNLAI_BACKUP_PASSPHRASE before running a backup}"

POSTGRES_DB="${POSTGRES_DB:-dsn_lai}"
POSTGRES_USER="${POSTGRES_USER:-dsnlai_owner}"
COMPOSE="${COMPOSE:-docker compose}"
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
setting() { grep -E "^$1=" "${ROOT}/.env" 2>/dev/null | tail -1 | cut -d= -f2-; }
BACKEND="${DSNLAI_STORAGE_BACKEND:-$(setting DSNLAI_STORAGE_BACKEND)}"
BACKEND="${BACKEND:-local}"
HOST_PATH="${DSNLAI_STORAGE_PATH:-$(setting DSNLAI_STORAGE_PATH)}"
HOST_PATH="${HOST_PATH:-${ROOT}/storage}"

mkdir -p "${DESTINATION}"

echo "Dumping the records, excluding the audit store"
${COMPOSE} exec -T db pg_dump \
  --username "${POSTGRES_USER}" \
  --dbname "${POSTGRES_DB}" \
  --format custom \
  --exclude-table-data 'audit_event' \
  > "${WORK}/records.dump"

echo "Dumping the audit store"
${COMPOSE} exec -T db pg_dump \
  --username "${POSTGRES_USER}" \
  --dbname "${POSTGRES_DB}" \
  --format custom \
  --table 'audit_event' \
  > "${WORK}/audit.dump"

mkdir -p "${WORK}/objects"
if [ "${BACKEND}" = "azure" ]; then
  # Azure keeps its own recovery position: blob versioning, soft delete and the
  # immutability policy on every executed copy. Copying the container into
  # this archive would duplicate that under weaker protection, so the archive
  # carries the records and the audit store and says so.
  echo "Documents are in Azure Blob Storage and are not copied into this archive."
  echo "Their recovery rests on the container's versioning, soft delete and immutability."
elif [ -n "$(${COMPOSE} ps -q api 2>/dev/null)" ]; then
  echo "Copying the documents out of the api container"
  ${COMPOSE} cp api:/var/lib/dsn-lai/storage/. "${WORK}/objects/" >/dev/null
else
  echo "Copying the documents from ${HOST_PATH}"
  [ -d "${HOST_PATH}" ] && cp -a "${HOST_PATH}/." "${WORK}/objects/"
fi
echo "$(find "${WORK}/objects" -type f | wc -l | tr -d ' ') documents in the archive"
tar -cf "${WORK}/objects.tar" -C "${WORK}" objects

ARCHIVE="${DESTINATION}/dsn-lai-${STAMP}.tar.gz"
tar -czf "${ARCHIVE}" -C "${WORK}" records.dump audit.dump objects.tar

echo "Encrypting"
openssl enc -aes-256-cbc -pbkdf2 -iter 200000 -salt \
  -in "${ARCHIVE}" -out "${ARCHIVE}.enc" \
  -pass env:DSNLAI_BACKUP_PASSPHRASE
rm -f "${ARCHIVE}"

sha256sum "${ARCHIVE}.enc" > "${ARCHIVE}.enc.sha256"

echo "Backup written to ${ARCHIVE}.enc"
echo "Recovery objectives, PRD section 15: RPO 1 hour, RTO 4 hours."
echo "Restore is tested quarterly with scripts/restore-drill.sh."
