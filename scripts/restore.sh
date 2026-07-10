#!/usr/bin/env bash
# Restore drill: decrypt a backup and restore it into a scratch database,
# then diff per-table row counts against the source DB. Exits non-zero on
# any mismatch. The printed duration is the measured RTO
# (docs/runbooks/backup-restore.md).
set -euo pipefail

PG_CONTAINER="${PG_CONTAINER:-agri-dev-postgres-1}"
PG_USER="${PG_USER:-app}"
PG_DB="${PG_DB:-agri}"
BACKUP_DIR="${BACKUP_DIR:-backups}"
SCRATCH_DB="${SCRATCH_DB:-agri_restore_drill}"
AGE_BIN="${AGE_BIN:-age}"
AGE_KEY_FILE="${AGE_KEY_FILE:-secrets/backup-age-key.txt}"

dump="${1:-$(ls -1t "$BACKUP_DIR"/agri-*.dump.age 2>/dev/null | head -1)}"
[[ -n "$dump" && -f "$dump" ]] || {
  echo "no backup found in $BACKUP_DIR" >&2
  exit 1
}
[[ -f "$AGE_KEY_FILE" ]] || {
  echo "missing $AGE_KEY_FILE (age identity)" >&2
  exit 1
}
echo "restoring: $dump -> $SCRATCH_DB"

psql_db() {
  docker exec "$PG_CONTAINER" psql -U "$PG_USER" -d "$1" -v ON_ERROR_STOP=1 -tA -c "$2"
}

counts() { # exact per-table row counts, schema-qualified, sorted
  docker exec "$PG_CONTAINER" psql -U "$PG_USER" -d "$1" -v ON_ERROR_STOP=1 -tA -c \
    "select format('select %L || ''|'' || count(*) from %I.%I;',
                   schemaname || '.' || tablename, schemaname, tablename)
       from pg_tables
      where schemaname not in ('pg_catalog', 'information_schema')
      order by 1" \
    | docker exec -i "$PG_CONTAINER" psql -U "$PG_USER" -d "$1" -v ON_ERROR_STOP=1 -tA -f -
}

start="$(date +%s)"
psql_db postgres "DROP DATABASE IF EXISTS ${SCRATCH_DB} WITH (FORCE)"
psql_db postgres "CREATE DATABASE ${SCRATCH_DB}"
"$AGE_BIN" -d -i "$AGE_KEY_FILE" "$dump" \
  | docker exec -i "$PG_CONTAINER" pg_restore -U "$PG_USER" -d "$SCRATCH_DB" \
      --no-owner --no-privileges
restore_done="$(date +%s)"

src_counts="$(counts "$PG_DB")"
dst_counts="$(counts "$SCRATCH_DB")"
if [[ "$src_counts" != "$dst_counts" ]]; then
  echo "ROW COUNT MISMATCH between $PG_DB and $SCRATCH_DB:" >&2
  diff <(echo "$src_counts") <(echo "$dst_counts") >&2 || true
  exit 1
fi
tables="$(echo "$dst_counts" | wc -l | tr -d ' ')"
rows="$(echo "$dst_counts" | awk -F'|' '{s+=$2} END {print s}')"
end="$(date +%s)"

echo "restore:   $((restore_done - start))s (drop+create+decrypt+pg_restore)"
echo "verify:    $((end - restore_done))s (${tables} tables, ${rows} rows, all counts match)"
echo "total RTO: $((end - start))s"
