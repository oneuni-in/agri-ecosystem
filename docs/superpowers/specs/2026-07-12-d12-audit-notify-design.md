# D12 — Audit Log + Notify Module: Design

Date: 2026-07-12 · Branch: `feat/d12-audit-notify` · Status: approved by owner (this session)

Source spec: SPEC D12 (audit + notify, ~5.5h). This document records the validated design
and the four owner-confirmed decisions; the implementation plan lives in
`docs/superpowers/plans/`.

## Owner decisions (confirmed 2026-07-12)

1. **Day chains are logical, not physical.** One plain append-only table; the hash chain
   restarts each UTC day. No `PARTITION BY` — revisit only if volume demands it.
2. **Email provider is ZeptoMail** (Zoho's transactional-email HTTP API — not Zoho Mail
   SMTP). Real driver behind a flag; mock driver in dev/CI.
3. **New restricted runtime role `app_rt`.** Migrations keep running as `app` (owner);
   the application connects as `app_rt`, which has no UPDATE/DELETE on schema `audit`.
4. **Event consumers run as an in-process FastAPI lifespan task**, env-gated. No separate
   worker deployment unit yet (VPS/staging work is deferred, owner-driven).

## 1. Audit core — `shared/audit.py`, schema `audit`

Audit is cross-cutting infrastructure (like `shared/events.py`, `shared/metrics.py`), so
the model + write helper + verifier live in `shared/audit.py`. Every module may import
`shared`; import-linter's "shared must not import modules" contract is untouched. There is
**no `modules/audit` package and no read API** in D12 — the spec needs a tamper-evident
write path, not an admin browser (that arrives with a later admin-console spec).

### Table `audit.entries`

UUIDv7 pk + `created_at` (no soft-delete/UGC mixins — rows are immutable):

| column | type | notes |
|---|---|---|
| `actor_user_id` | uuid, nullable | null = system actor (e.g. OTP throttle) |
| `action` | text | e.g. `admin.role_assigned`, `identity.handle_changed` |
| `target_type` | text, nullable | e.g. `user`, `handle` |
| `target_id` | text, nullable | text, not uuid — targets include handles/hashes |
| `metadata` | JSONB | ORM attribute named `meta` (`metadata` collides with SQLAlchemy) |
| `ip` | text, nullable | |
| `chain_day` | date | UTC day the entry chains under |
| `seq` | int | position within the day's chain, starts at 1 |
| `prev_hash` | text | 64-char sha256 hex |
| `entry_hash` | text | 64-char sha256 hex |

Indexes: `(chain_day, seq)` unique; `(actor_user_id)`, `(action)` for later querying.

### Chain semantics

- First entry of a day: `prev_hash = sha256("genesis:" + YYYY-MM-DD)`.
- `entry_hash = sha256(prev_hash + canonical_json({id, actor_user_id, action, target_type,
  target_id, metadata, ip, created_at_iso, chain_day, seq}))` — canonical = sorted keys,
  compact separators, no whitespace ambiguity.
- Appends serialize on `pg_advisory_xact_lock` keyed by the day string, then read the
  day's last row and insert `seq + 1`. No head-pointer table → the schema needs **zero
  UPDATE grants** and concurrent writers cannot fork the chain. This serializes audit
  writes globally within a day; acceptable because only sensitive actions are audited
  (low volume). Revisit (e.g. shard the lock) if audit write volume ever matters.

### Write helper

```python
async def audit(session, *, action, actor_user_id=None, target_type=None,
                target_id=None, metadata=None, ip=None) -> None
```

Writes in the **caller's transaction** — the audit row commits or rolls back atomically
with the action it records. PII rule carried over from D07/D11: metadata carries agri_ids
and hashes, never phone numbers (existing redaction test extends to real rows).

### Verifier

`verify_chain(session, days=None)` in `shared/audit.py` recomputes each day's chain and
returns the broken days (first bad seq + reason). `scripts/verify_audit_chain.py` wraps it
as a job (exit non-zero on breaks) and emits Prometheus metrics
(`audit_chain_days_verified_total`, `audit_chain_breaks_total`) per D05 conventions.
Cron wiring is deferred with the rest of the VPS work.

### Wiring (all four points exist today as labeled placeholders)

| call site | action |
|---|---|
| `modules/identity/admin_router.py` `_audit()` → 4 call sites | `admin.role_assigned`, `admin.role_removed`, `admin.user_suspended`, `admin.user_reactivated` |
| `modules/identity/otp_throttle.py` burst-issues hook | `otp.abuse_burst_issues` (system actor) |
| `modules/identity/otp_throttle.py` many-phones-per-IP hook | `otp.abuse_many_phones_per_ip` (system actor) |
| `modules/identity/session_router.py` `set_handle()` | `identity.handle_changed` (currently unwired — new) |

`_audit()` becomes a thin wrapper over `shared.audit.audit()` (call-site-for-call-site as
its docstring promises). The OTP throttle hooks run where no DB session is open; they open
a short-lived session for the audit write (they are fire-and-forget system records, not
part of a business transaction).

## 2. DB role enforcement (non-negotiable #2)

Migration `0012_audit_v1` creates the schema, the table, and role `app_rt`:

- `CREATE ROLE app_rt LOGIN NOSUPERUSER` — **idempotent** (`DO $$ ... IF NOT EXISTS`):
  roles are cluster-wide, and the test harness drops/recreates the database, not the
  cluster, so re-runs must not fail.
- Grants: `USAGE` on all schemas; full DML on every non-audit schema's tables + sequences;
  on schema `audit`: `INSERT, SELECT` **only**, plus `ALTER DEFAULT PRIVILEGES` so future
  audit tables inherit the restriction.
- Downgrade: revoke + drop role (guarded — only if no other DB depends on it), drop table,
  drop schema. `scripts/migrate_check.py` round-trip must stay green.

Runtime connection switches to `app_rt` in `docker-compose.dev.yml`, CI's pytest env, and
`tests/conftest.py`; alembic keeps `DATABASE_URL` with `app` (superuser in dev/CI — it
owns the tables and bypasses grants, which is exactly what the tamper test exploits).

Enforcement is proven, not asserted:
- Grant test: `UPDATE`/`DELETE` on `audit.entries` through the app engine (`app_rt`)
  raises `insufficient_privilege`.
- Tamper test: mutate a row through the privileged `app` connection → `verify_chain()`
  flags exactly that day (detection, not just hashing — non-negotiable #1).

## 3. Notify engine — `modules/notify`, schema `notify`

### Tables (`0013_notify_v1`)

- `templates`: `key`, `channel` enum (`in_app|sms|email`), `locale` (`en|ta|hi`),
  `subject` (nullable, email only), `body` with `{var}` placeholders;
  unique `(key, channel, locale)`.
- `notifications`: `user_id`, `template_key`, `payload` JSONB, `read_at` nullable,
  `created_at`. The in-app record; one row per user-visible notification.
- `deliveries`: `notification_id` FK, `channel`, `status` (`pending|sent|failed|dead`),
  `attempts`, `next_attempt_at`, `provider_ref`, `cost` numeric, `last_error`.
- `preferences`: pk `(user_id, channel)`, `enabled` bool. **In-app cannot be disabled**;
  SMS/email default **enabled** (rows record opt-outs) — these are security-relevant
  transactional alerts, not marketing.

### Flow — modules emit events, never sends (non-negotiable #3)

Producing modules publish domain events on the bus and know nothing about notify:

| event | template key | channels seeded |
|---|---|---|
| `identity.signup_completed` | `welcome` | in_app, email |
| `identity.login_new_device` | `login_new_device` | in_app, sms, email |
| `identity.role_changed` | `role_changed` | in_app |
| `notify.announce` | `generic_announce` | in_app, email |

None of these events is published today — D12 adds the `publish()` calls in identity
(signup completion, session creation from an unseen device, admin role change) alongside
the audit wiring. Notify's consumer (consumer group on the identity/notify streams) maps
event → template key + recipient + payload, then dispatches:

1. **Per-user rate cap** (Redis counter; default 30 notifications per user per hour,
   settings-overridable; over-cap drops with a metric — the harassment mitigation from
   the threat model).
2. Insert `notifications` row (in-app, always).
3. For sms/email: user preference on? feature flag on? locale row exists (fallback
   ta/hi → en)? → insert `deliveries` row → driver send → mark `sent`/`failed`.

### Rendering (template-variable injection defense)

Strict `{var}`-only substitution from the payload: regex-based, no `str.format`
(kills format-spec/attribute-access injection), missing variable is a hard error, values
are coerced to `str` and HTML-escaped for the email channel. User-controlled payload
values can never alter template structure.

### Drivers — `modules/notify/drivers.py`

Mirrors D07's single-selection-point pattern (`get_sms_driver()`):

- SMS: `MockSmsDriver` now (inspectable outbox). Identity's MSG91 OTP driver is
  OTP-template-specific and cross-module-import-banned; a real generic SMS adapter lands
  when a real need arrives.
- Email: `MockEmailDriver` + `ZeptoMailDriver` (httpx POST to ZeptoMail's transactional
  API), selected by `settings.email_provider` and gated by DB flag `notify.email_enabled`
  (flag pattern from `shared/flags.py`, fail-closed).

Lint contract: an explicit import-linter **forbidden** contract — nothing outside
`modules.notify` may import `modules.notify.drivers` — so the failure names the rule
(the general independence contract already implies it).

### Delivery retry + dead-letter

The worker retries `failed` deliveries whose `next_attempt_at` is due, exponential
backoff (e.g. 1m → 5m → 25m), max attempts → status `dead` + metric
(`notify_deliveries_dead_total`). Bus-level poison messages additionally fall into the
existing Redis `:dlq` stream via `reap_poison()`.

### Worker

FastAPI lifespan starts one asyncio task: poll notify consumer group → dispatch → ack;
poll due retries; `reap_poison()` periodically. Gated by `NOTIFY_WORKER_ENABLED`
(on in dev compose, **off in tests** — tests call the consumer/engine functions directly
for determinism).

### API (SecureRouter, private, rate-limited, cursor-paginated)

- `GET /notify/notifications` (cursor)
- `POST /notify/notifications/{id}/read`, `POST /notify/notifications/read-all`
- `GET /notify/unread-count`
- `GET /notify/preferences`, `PUT /notify/preferences`

All owner-scoped via `require_auth` principal; no new public routes.

## 4. Notification center UI

- **`packages/ui`** (exported from `index.ts`, showcased on `/demo`, vitest unit tests):
  - `NotificationBell` — presentational: 🔔 emoji glyph (design-system precedent),
    `tap-target` (44px), `aria-label`, numeric unread pill (new mini-primitive; `Badge`'s
    variant union is marketing-locked and not reusable).
  - `NotificationsPanel` — composite list: `Card` rows, mark-read / mark-all-read,
    cursor "load more", `EmptyState`, `Skeleton`; takes injected fetch helpers
    (devices-manager pattern).
- **Data wiring:** the bell is a client island that waits for `useAgriUser()` to resolve,
  then fetches unread-count once + on window focus. **No polling** — the bell lives in
  the shared header on `/`, which is under the Lighthouse ≥0.90 budget; it must follow
  `AuthCluster`'s async no-render-while-loading pattern.
- **Per app:**
  - web-agri / web-milk / web-organic: new `/api/notify/[...path]/route.ts` BFF proxy
    (copy of web-admin's bearer pattern — access tokens stay server-side), bell in
    `site-header.tsx` `right` slot, `/notifications` page mounting the panel.
  - web-id: no shared header — bell mounts in its layout header area; API rides the
    existing `/api/id/*` cookie rewrite; own `/notifications` page.
  - web-admin: out of D12 scope (spec: 3 public apps + web-id).
- **i18n:** `ui.notifications.*` strings in the shared catalog
  (`packages/ui/src/i18n/messages/{en,ta,hi}.json`).

## 5. Seed templates + locale completeness (non-negotiable #4)

`0013_notify_v1` seeds the four template keys (channels per the table in §3) × en/ta/hi,
`bulk_insert` style like 0011's permission seeding. A pytest asserts every distinct
`(key, channel)` present in the table has all three locales — runs in the normal backend
CI job, so an incomplete seed fails CI.

## 6. Tests

| test | proves |
|---|---|
| chain happy path | hashes link, per-day genesis, seq ordering |
| tamper detection | privileged UPDATE of one row → `verify_chain()` flags that day |
| grant enforcement | app_rt UPDATE/DELETE → `insufficient_privilege` |
| preference routing | SMS opted out → in-app row exists, no sms delivery row |
| rendering ×3 locales | correct body per locale + fallback to en |
| injection escape | payload value containing `{`, `}`, HTML → inert in output |
| retry/backoff | fail → failed + next_attempt_at per schedule; fail×max → `dead` |
| rate cap | over-cap events drop in-app rows beyond N, metric increments |
| locale completeness | every seeded (key, channel) has en+ta+hi |
| redaction (extends existing) | audit rows for admin/OTP actions carry agri_ids, never phones |

## Known traps carried in

- `app_rt` role is cluster-wide: migration must be idempotent; conftest recreates the DB
  but not the role; downgrade must not break `migrate_check`.
- `metadata` column name vs SQLAlchemy `Base.metadata` — ORM attribute `meta`.
- New singletons (driver outboxes, worker state, flag cache interplay) need reset hooks in
  `tests/conftest.py`'s autouse `_reset_state`.
- Migration files need filled THREAT/NOTES blocks (lint gate).
- New i18n keys must land in all three JSON files or the UI falls back silently.
- Bell must not regress Lighthouse home budgets (no polling, no blocking fetch, 44px).

## Out of scope (spec DO NOT)

Push notifications (PWA push at D28) · marketing/bulk sends · audit read API/UI ·
real SMS adapter for notify · VPS/staging deployment of the worker.
