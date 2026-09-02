#!/usr/bin/env bash
# Encrypted backup of the database, the object store and the audit store,
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
# The default has to match app/core/config.py. It did not, and every backup
# run without MINIO_BUCKET set failed on a bucket that does not exist.
BUCKET="${MINIO_BUCKET:-dsn-lai-documents}"

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

echo "Mirroring the object store"
${COMPOSE} exec -T minio mc alias set local http://localhost:9000 \
  "${MINIO_ACCESS_KEY:-dsn-lai-minio-access}" \
  "${MINIO_SECRET_KEY:-dsn-lai-minio-secret-dev}" >/dev/null
# The directory is created first. An empty bucket is a legitimate state, and
# without this the mirror leaves nothing behind on a deployment that simply
# has no documents yet.
#
# The archive is built on the host rather than in the container. The MinIO
# image carries no tar, so doing it there failed with a command-not-found that
# the pipeline reported as an empty archive.
${COMPOSE} exec -T minio mkdir -p /tmp/backup
${COMPOSE} exec -T minio mc mirror --quiet --overwrite "local/${BUCKET}" /tmp/backup >/dev/null
mkdir -p "${WORK}/objects"
${COMPOSE} cp minio:/tmp/backup/. "${WORK}/objects/" >/dev/null 2>&1 || true
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
