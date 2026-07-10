# Runbook: Postgres backup & restore

## What exists
- `scripts/backup/backup.sh` — `pg_dump -Fc` piped into `age` (encrypt-only,
  recipients file); local retention prunes files older than `RETENTION_DAYS`
  (default 30). R2 upload is coded but **INACTIVE** until
  `BACKUP_UPLOAD_ENABLED=1` + `R2_BUCKET` + `R2_ENDPOINT` are set.
- `scripts/restore.sh` — decrypts the newest (or given) `.dump.age`, restores
  into a scratch DB (`agri_restore_drill`), and diffs exact per-table row
  counts against the source. Non-zero exit on any mismatch (the mismatch path
  is itself tested: an extra table in the source makes the drill fail).
- `scripts/backup/wal-archive.sh` — WAL `archive_command` target for R2.
  **INACTIVE** until launch prep.

Env contract shared by both scripts: `PG_CONTAINER` (default
`agri-dev-postgres-1`; staging uses `agri-staging-postgres-1`), `PG_USER`,
`PG_DB`, `BACKUP_DIR`, `AGE_BIN` (full path to age when not on PATH),
`AGE_RECIPIENTS_FILE` / `AGE_KEY_FILE`.

## Restore drill #1 — 2026-07-10, local Docker Postgres (agri-dev)
The VPS is not provisioned yet (owner decision,
docs/runbooks/staging-deploy.md), so drill #1 ran against the real dev
database — actually executed, not simulated. Drill #2 re-runs this on the VPS
against a nightly dump during launch prep.

| measurement | value |
|---|---|
| dump size (age-encrypted) | 76 KB |
| backup (pg_dump + encrypt) | 1 s |
| restore (drop+create+decrypt+pg_restore) | 2 s |
| verification (row-count diff) | 1 s |
| **total RTO** | **3 s** |
| tables / rows verified | 7 / 2,077 |
| schema revision restored | alembic 0006 |

Data at drill time: D03 geo snapshot (1 state, 38 districts, 2,035 pincodes)
plus feature flags — the full dataset the platform has today. These timings
scale with data volume; re-measure at drill #2 and before launch.

Drill log (verbatim):

```text
backup: backups/agri-20260710T100203Z.dump.age (76K) in 1s
r2 upload skipped (BACKUP_UPLOAD_ENABLED != 1)
restoring: backups/agri-20260710T100203Z.dump.age -> agri_restore_drill
DROP DATABASE
CREATE DATABASE
restore:   2s (drop+create+decrypt+pg_restore)
verify:    1s (7 tables, 2077 rows, all counts match)
total RTO: 3s
```

Drill gotcha discovered: `python scripts/migrate_check.py` run against the
dev DB wipes data (its downgrade pass drops tables). Reload with
`python scripts/load_geo.py` afterwards, or point migrate_check at a
throwaway DB via `DATABASE_URL`.

## Keys
- Dev drill keypair: `secrets/backup-age-key.txt` (identity) +
  `secrets/backup-age-recipients.txt` (public key). Both gitignored; dev-only.
  Regenerate with `age-keygen -o secrets/backup-age-key.txt`.
- Production keypair: generated OFFLINE by the owner and stored offline;
  only the **recipient (public key)** goes to the VPS. Losing the identity
  file means backups are unrecoverable — that is the point of the drill.
- Windows note: winget installs age at
  `%LOCALAPPDATA%\Microsoft\WinGet\Packages\FiloSottile.age_*\age\age.exe`;
  pass it via `AGE_BIN` if `age` is not on PATH.

## ACTIVATE AT LAUNCH PREP (owner-driven, in order)
1. Create the R2 bucket; apply the 30-day lifecycle rule:
   `{"Rules":[{"ID":"pg-30d","Status":"Enabled","Filter":{"Prefix":"pg/"},"Expiration":{"Days":30}},{"ID":"wal-30d","Status":"Enabled","Filter":{"Prefix":"wal/"},"Expiration":{"Days":30}}]}`
2. On the VPS: install `age` + `aws` CLI; place the production age recipient
   at `secrets/backup-age-recipients.txt`; export `BACKUP_UPLOAD_ENABLED=1`,
   `R2_BUCKET`, `R2_ENDPOINT` (account-specific), and R2 credentials for aws.
3. Nightly cron (VPS): `10 21 * * * cd ~/agri-ecosystem && PG_CONTAINER=agri-staging-postgres-1 bash scripts/backup/backup.sh >> ~/backup.log 2>&1`
   (21:10 UTC = 02:40 IST, low traffic).
4. Enable WAL archiving in the staging/prod postgres:
   `archive_mode=on`, `archive_command='.../wal-archive.sh %p %f'`.
5. Run RESTORE DRILL #2 on the VPS against last night's dump; add a second
   row to the timing table above.

## Failure playbook
- Backup script exits non-zero → nothing was pruned (prune runs last); rerun.
- Restore mismatch → the printed diff shows which tables diverge. A dump taken
  while migrations were running is the usual cause; take a fresh dump.
- Lost dev key → regenerate keypair, take a fresh backup; old local dumps are
  disposable. Production keys are the owner's offline responsibility.
