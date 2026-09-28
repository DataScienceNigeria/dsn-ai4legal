#!/usr/bin/env bash
# Copy every document out of a MinIO bucket into a folder, before MinIO goes.
#
# MinIO is no longer part of the platform. Anything already stored in it has to
# be carried into the folder the local backend reads, or moved on to Azure with
# scripts/move_documents.py, before the container is removed. Keys are kept
# exactly, so every storage_key in the database still resolves.
#
#   scripts/export_minio.sh [target folder]
#
# Reads MINIO_ACCESS_KEY, MINIO_SECRET_KEY and MINIO_BUCKET from .env. Needs the
# minio container running. Counts and checks every file before it reports done.
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
TARGET="${1:-$ROOT/storage}"
CONTAINER="${MINIO_CONTAINER:-$(docker ps --format '{{.Names}}' | grep -m1 -- '-minio-')}"

value() { grep -E "^$1=" "$ROOT/.env" | tail -1 | cut -d= -f2-; }
ACCESS="$(value MINIO_ACCESS_KEY)"
SECRET="$(value MINIO_SECRET_KEY)"
BUCKET="$(value MINIO_BUCKET)"
BUCKET="${BUCKET:-dsn-lai-documents}"

[ -n "$CONTAINER" ] || { echo "No MinIO container is running." >&2; exit 1; }

docker exec "$CONTAINER" sh -c "
  rm -rf /tmp/export && mkdir -p /tmp/export &&
  mc alias set src http://localhost:9000 '$ACCESS' '$SECRET' >/dev/null &&
  mc mirror --quiet src/$BUCKET /tmp/export >/dev/null
"
expected="$(docker exec "$CONTAINER" sh -c "mc ls --recursive src/$BUCKET | wc -l" | tr -d ' ')"

mkdir -p "$TARGET"
docker cp "$CONTAINER:/tmp/export/." "$TARGET/"
docker exec "$CONTAINER" rm -rf /tmp/export

copied="$(find "$TARGET" -type f | wc -l | tr -d ' ')"
if [ "$copied" -lt "$expected" ]; then
  echo "Only $copied of $expected documents arrived in $TARGET. MinIO has not been changed." >&2
  exit 1
fi
echo "$expected documents copied into $TARGET."
