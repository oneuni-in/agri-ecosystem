# D13 — AgriCoins Ledger + Rules + Referrals — Design

**Date:** 2026-07-13
**Branch:** `feat/d13-agricoins`
**Spec source:** SPEC D13 (Phase-1 loyalty coins). 🔍 full-read day.

## Purpose & framing

Closed-loop loyalty coins. **AgriCoins are NOT money:** not purchasable, not
cashable, not P2P-transferable. This is stated in code comments and a coins
T&C stub. Architecture: an append-only ledger with mandatory idempotency;
balances are a derived, transactionally-maintained materialization.

### Guiding invariants (non-negotiables)

- **Not money.** No purchase / cash-out / P2P transfer paths — not even
  scaffolded.
- **Integer coins only** (`BIGINT`). No floating point anywhere.
- **Append-only ledger**; balances derived. Corrections are compensating
  entries only (never update/delete).
- **DB-constraint-proven idempotency** — the same idempotency key can never
  double-credit, proven by a `UNIQUE` constraint, not by application logic.
- **DB-enforced immutability** — ledger rows cannot be updated or deleted at
  the database level.
- **No cap bypass** — every award path goes through the rules engine.

## Confirmed decisions (2026-07-13)

1. **Ledger immutability:** `BEFORE UPDATE OR DELETE` trigger on
   `coins.ledger_entries` that `RAISE`s, **plus** `REVOKE UPDATE, DELETE …
   FROM app` for defense-in-depth. Chosen because the app both owns and
   connects to Postgres as a single role (`app`), and a table owner bypasses
   `REVOKE`; the trigger holds even against the owner/superuser. Fully
   reversible.
2. **Signup trigger:** add a surgical identity change — the `login` route
   emits a new `user.registered` event on new-account creation and accepts an
   optional `referral_code`. Coins consumes it. Identity is the producer;
   coins never imports identity.
3. **Worker runtime:** a standalone `python -m modules.coins.worker` consumer
   loop, added as a new `worker` service in `docker-compose.dev.yml`. Nightly
   integrity + monthly cap-reset run as separate one-shot scripts under
   `backend/core/scripts/` (mirrors `scripts/migrate_check.py`).
4. **Rule amounts (Sprint-1), confirmed as specified:**

   | rule | amount | cap |
   |---|---|---|
   | `signup_complete` | 100 | once |
   | `profile_100` | 200 | once |
   | `daily_visit` | 5 | 1/day |
   | `referral_referrer` | 250 | on referee `profile_100`; 20/month |
   | `referral_referee` | 100 | on own `profile_100` |

## Architecture

New backend module `backend/core/modules/coins/` (scaffold already exists) and
a new Postgres schema `coins`. Follows the established repo conventions:
`SecureRouter` (shared/security.py), keyset pagination (shared/pagination.py),
UUIDv7 + timestamp mixins (shared/db.py), feature flags (shared/flags.py),
`require_permission` RBAC (identity/rbac.py), Redis Streams event bus
(shared/events.py). Cross-module effects go only through the event bus.

### 1. Data model — schema `coins` (alembic `0012_coins_v1`)

| Table | Key columns | Notes |
|---|---|---|
| `ledger_entries` | id (uuidv7 PK), user_id, `delta BIGINT` (≠0), reason_code, ref_type, ref_id (nullable), `idempotency_key TEXT UNIQUE`, created_at | Append-only. Index `(user_id, id)` for keyset history. |
| `balances` | user_id PK, `balance BIGINT NOT NULL DEFAULT 0 CHECK(balance>=0)`, updated_at | Materialized per-user sum. |
| `rules` | code PK, `amount BIGINT`, `daily_cap`/`weekly_cap`/`total_cap` (nullable), `active BOOL`, `valid_from`, `valid_to` (nullable) | Seeded with Sprint-1 rules. |
| `referral_codes` | user_id PK, `code TEXT UNIQUE` | One code per user. |
| `referrals` | id, referrer_id, `referee_id UNIQUE`, code, `status` enum(pending/rewarded/voided), device_fingerprint, phone_prefix, created_at, rewarded_at, voided_at | One attribution per referee. |
| `abuse_flags` | id, referral_id, cluster_reason, `status` enum(open/reviewed/voided), details (JSON), reviewed_by, reviewed_at, created_at | Feeds the admin abuse queue. |

**Immutability:** `BEFORE UPDATE OR DELETE` trigger on `ledger_entries` that
`RAISE`s + `REVOKE UPDATE, DELETE ON coins.ledger_entries FROM app`. The
migration also seeds Sprint-1 rules, coins permissions
(`coins.rules.write`, `coins.adjust`, `coins.abuse.review`) granted to
`staff`/`super_admin` as appropriate, and feature flags.

No floating point: all coin quantities are `BIGINT`.

### 2. Core service — `service.py` (line-by-line read target)

Public interface: `award(user, rule_code, ref, idem_key)` /
`redeem(user, amount, reason, idem_key)` / `balance(user)` /
`history(user, cursor)`. Every mutation is a single transaction:

```sql
INSERT INTO coins.ledger_entries (…, idempotency_key) VALUES (…);   -- UNIQUE dup ⇒ idempotent no-op
INSERT INTO coins.balances(user_id, balance) VALUES(:u, 0) ON CONFLICT DO NOTHING;
UPDATE coins.balances SET balance = balance + :delta
  WHERE user_id = :u AND balance + :delta >= 0 RETURNING balance;    -- 0 rows on redeem ⇒ InsufficientBalance
```

- The `balances`-row lock **serializes concurrent same-user writers** → exact
  sum, no drift; different users never contend.
- A duplicate `idempotency_key` raises `IntegrityError`, which is caught; the
  existing entry is returned. **The constraint proves single-credit, not app
  logic.** (Postgres blocks the second inserter until the first commits/rolls
  back, so the returned existing row is always the committed one.)
- Redeem insufficiency rejects atomically via the 0-row guard (with
  `CHECK(balance>=0)` as a backstop) → the whole transaction rolls back and
  nothing persists.

**Alternatives considered and rejected:** `SELECT … FOR UPDATE`-then-compute
(extra round-trip, identical lock) and `SERIALIZABLE` + retry loop (throughput
cliff, retry complexity). The conditional `UPDATE` is the boring, correct
choice.

### 3. Rules engine — `rules.py` (line-by-line read target)

`award()` **always** routes through the engine; direct ledger writes outside
the service are banned by a test-gate (lint contract). The engine checks: rule
exists + `active` + within `[valid_from, valid_to)` + caps, then writes.

- **"once" / "1-per-day" caps collapse to deterministic idempotency keys**
  (`signup_complete:{user}`, `profile_100:{user}`,
  `daily_visit:{user}:{yyyy-mm-dd}`) — the `UNIQUE` constraint enforces them
  race-free, with no counting.
- Numeric caps that cannot be a key (the referral 20/month) are enforced by a
  counted check under the referrer's row lock.

### 4. Cross-module wiring — events

- **Identity change (surgical, producer side):** `login` emits
  `user.registered` (`{user_id, agri_id, referral_code?}`) on new-account
  creation and accepts an optional `referral_code` (sourced from a `?ref=`
  link → cookie in web-id). Published on the existing `identity` stream,
  best-effort after commit (mirrors the `profile.completed` precedent).
- **Standalone worker** (`python -m modules.coins.worker`, new `worker`
  service in `docker-compose.dev.yml`) runs an `EventConsumer` loop over the
  `identity` stream with its own consumer group:
  - `user.registered` → `award(signup_complete)` + record referral
    attribution (deterministic idem keys).
  - `profile.completed` → `award(profile_100)`; if the referee has a
    **pending** referral, `award(referral_referrer 250)` (subject to the
    20/month cap) + `award(referral_referee 100)`, then mark the referral
    `rewarded`. Deterministic idem keys `referral_referrer:{referral_id}` /
    `referral_referee:{referral_id}`.
  - **Reward is delayed to `profile_100`, never signup (anti-farm).**
  - Poison messages fall through to the DLQ via the bus's existing
    `reap_poison`.

### 5. Scheduled jobs (standalone scripts)

- `scripts/coins_integrity.py` (nightly): recompute `SUM(delta)` per user vs
  stored balance; **ANY drift** logs + emits a metric + publishes a `notify`
  alert event.
- `scripts/coins_referral_reset.py` (monthly): reset referrer monthly
  counters.
- Abuse clustering: group referrals by device fingerprint + phone prefix;
  clusters over a threshold create `abuse_flags`.

### 6. Admin & voids

- **Rules CRUD** — flag-gated (`coins.rules.write` permission + a feature
  flag).
- **Manual adjust** — dual-confirm (request returns a confirmation token; a
  second confirm call applies), requires a reason note, is audit-logged, and
  is written as a compensating/manual entry **through the service** (no direct
  writes).
- **Abuse queue** — admin reviews; **void = compensating entries only**
  (negative deltas reversing the referral awards) + mark the referral
  `voided`. Rows are never deleted.

### 7. UI

- **`CoinsPill`** — shared component in `packages/ui`, mounted in every app
  header (web-id / web-agri / web-milk / web-organic / web-admin). Reads
  `GET /coins/balance` via each app's BFF proxy; kept live by polling +
  refetch-on-focus.
- **Coins history** screen — cursor-paginated via `paginate()`; reason labels
  localized through i18n (`reason_codes.py` maps reason_code → i18n key).
- **Admin screens** — rules CRUD, manual adjust, abuse queue.

### Module layout (mirrors identity's multi-file style)

```
backend/core/modules/coins/
  models.py        # ORM: ledger_entries, balances, rules, referral_codes, referrals, abuse_flags
  service.py       # award / redeem / balance / history  (read target)
  rules.py         # rules engine + caps                  (read target)
  referrals.py     # referral codes, attribution, reward-on-profile_100
  abuse.py         # device-fingerprint + phone-prefix clustering
  integrity.py     # recompute vs stored, drift detection
  worker.py        # EventConsumer loop (python -m modules.coins.worker)
  schemas.py       # pydantic public shapes
  reason_codes.py  # reason_code → i18n label mapping
  router.py        # user endpoints: balance, history, referral code
  admin_router.py  # rules CRUD, manual adjust (dual-confirm), abuse queue
```

Plus: alembic `0012_coins_v1`, `main.py` router registration, a `worker`
service in `docker-compose.dev.yml`, and `packages/ui/CoinsPill`.

## Testing (spec part F / Definition of Done)

- **Idempotency** — same key twice = exactly one entry.
- **Concurrency storm** — 10k parallel mixed award/redeem on one user → exact
  final balance, zero negative, zero drift.
- **Cap boundaries** — once / per-day / monthly caps at their edges.
- **Referral** — attribution at signup, reward on referee `profile_100`,
  20/month referrer cap.
- **Integrity job** — detects an injected drift.
- **Lint gate** — no ledger writes outside the service.

## Threat model coverage

| Threat | Mitigation |
|---|---|
| Double-credit races | `UNIQUE(idempotency_key)` constraint (DB-proven). |
| Referral farming | Delayed reward (profile_100, not signup) + 20/month cap + device/phone clustering → abuse queue. |
| Insider manipulation | Manual adjust = dual-confirm + audit + compensating-only. |
| Balance drift | Nightly integrity recompute + alert on ANY drift. |
| Ledger tampering | `BEFORE UPDATE/DELETE` trigger + revoked grants. |

## Explicit non-goals (DO NOT)

- No purchase / cash-out / transfer paths — not even scaffolded.
- No floating point anywhere (integer coins).
- Corrections only as compensating entries.
- No direct ledger writes outside the service (lint contract).

## Scope note

Large but cohesive single spec. The implementation plan will sequence it in
phases: (1) schema + core service + idempotency/storm tests; (2) rules engine
+ events + worker; (3) referrals + abuse + integrity job; (4) UI + admin.

## Definition of Done

Storm test green at 10k; idempotency + caps + integrity tests green; ledger
service + rules engine read line-by-line; PR → dev merged.
Commit: `feat(d13): agricoins`.
