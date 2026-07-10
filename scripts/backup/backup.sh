#!/usr/bin/env bash
# Postgres backup: pg_dump custom format, age-encrypted, optional R2 upload.
# Runs anywhere docker + age exist (dev box now; VPS nightly cron at launch —
# see docs/runbooks/backup-restore.md). R2 upload and the cron schedule are
# READY BUT INACTIVE until launch prep.
set -euo pipefail

PG_CONTAINER="${PG_CONTAINER:-agri-dev-postgres-1}"
PG_USER="${PG_USER:-app}"
PG_DB="${PG_DB:-agri}"
BACKUP_DIR="${BACKUP_DIR:-backups}"
RETENTION_DAYS="${RETENTION_DAYS:-30}"
AGE_BIN="${AGE_BIN:-age}"
AGE_RECIPIENTS_FILE="${AGE_RECIPIENTS_FILE:-secrets/backup-age-recipients.txt}"

[[ -f "$AGE_RECIPIENTS_FILE" ]] || {
  echo "missing $AGE_RECIPIENTS_FILE (age recipients)" >&2
  exit 1
}
mkdir -p "$BACKUP_DIR"

stamp="$(date -u +%Y%m%dT%H%M%SZ)"
out="${BACKUP_DIR}/agri-${stamp}.dump.age"

start="$(date +%s)"
docker exec "$PG_CONTAINER" pg_dump -Fc -U "$PG_USER" "$PG_DB" \
  | "$AGE_BIN" -e -R "$AGE_RECIPIENTS_FILE" -o "$out"
duration="$(($(date +%s) - start))"
size="$(du -h "$out" | cut -f1)"
echo "backup: ${out} (${size}) in ${duration}s"

# R2 upload — READY BUT INACTIVE until launch prep (docs/runbooks/backup-restore.md).
# Activation: set BACKUP_UPLOAD_ENABLED=1 + R2_BUCKET + R2_ENDPOINT and configure
# the aws CLI with R2 credentials; the bucket's 30-day lifecycle rule handles
# remote retention.
if [[ "${BACKUP_UPLOAD_ENABLED:-0}" == "1" ]]; then
  : "${R2_BUCKET:?BACKUP_UPLOAD_ENABLED=1 requires R2_BUCKET}"
  : "${R2_ENDPOINT:?BACKUP_UPLOAD_ENABLED=1 requires R2_ENDPOINT}"
  aws s3 cp "$out" "s3://${R2_BUCKET}/pg/$(basename "$out")" --endpoint-url "$R2_ENDPOINT"
  echo "uploaded to r2: s3://${R2_BUCKET}/pg/$(basename "$out")"
else
  echo "r2 upload skipped (BACKUP_UPLOAD_ENABLED != 1)"
fi

# local retention
find "$BACKUP_DIR" -name 'agri-*.dump.age' -mtime "+${RETENTION_DAYS}" -delete
