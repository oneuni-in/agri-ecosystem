#!/usr/bin/env bash
# WAL archive_command target — READY BUT INACTIVE until launch prep.
# Activation (docs/runbooks/backup-restore.md): set in postgres config
#   archive_mode = on
#   archive_command = '/path/to/wal-archive.sh %p %f'
# plus R2_BUCKET/R2_ENDPOINT in the environment and aws CLI credentials.
set -euo pipefail

wal_path="$1"
wal_name="$2"
: "${R2_BUCKET:?wal archiving requires R2_BUCKET}"
: "${R2_ENDPOINT:?wal archiving requires R2_ENDPOINT}"
aws s3 cp "$wal_path" "s3://${R2_BUCKET}/wal/${wal_name}" --endpoint-url "$R2_ENDPOINT"
