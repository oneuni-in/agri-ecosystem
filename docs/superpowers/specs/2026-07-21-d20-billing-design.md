# D20 — Billing (Razorpay, flagged) + Dunning + Business Console Shell — Design

**Date:** 2026-07-21 · **Branch:** `feat/d20-billing` · **PR target:** `dev`
**Source spec:** docs/Sprint/Sprint2 spec pack d15 d22.MD (SPEC D20)

## Context

Money-in path: businesses pay the platform for subscriptions — never goods,
never checkout. Razorpay KYC is on hold, so the entire surface ships dark
behind the `billing_enabled` feature flag (seeded false in D03, read through
`shared/flags.py` — 30 s cache, fail-closed, DB-driven so it flips without a
deploy). Build complete now; the flag flip is the launch.

Money-path code requires 🔍 human line-by-line review before merge.

Decisions taken during brainstorming:

- **Console home:** web-agri `/business/*` (absorbs the D18 leads inbox).
  Not a new app, not web-admin.
- **Tiers:** `free / growth / pro`. Free is the absence of a subscription
  row; growth and pro are paid. Placeholder prices until Pricing v1.
- **Integration style:** thin async httpx Razorpay client (no SDK), inline
  webhook processing after dedupe, worker-based dunning, script-based
  nightly reconciliation.

## 1. Schema — `billing` (one alembic migration)

Per-table grants only (0019/0020 precedent — never
`GRANT ... ON ALL TABLES IN SCHEMA`).

**`billing.subscriptions`**

| column | type | notes |
|---|---|---|
| id | UUIDv7 PK | |
| business_id | UUID, indexed | no cross-schema FK (module independence); existence validated through directory's public service interface at creation |
| tier | TEXT CHECK ('growth','pro') | free = no row |
| status | TEXT CHECK ('active','past_due','canceled') | |
| current_period_end | timestamptz | |
| razorpay_sub_id | TEXT UNIQUE, nullable | null until a live create succeeds |
| dunning_attempt | int, default 0 | |
| next_retry_at | timestamptz, nullable | |
| past_due_since | timestamptz, nullable | |
| created/updated | TimestampMixin | |

Partial unique index on `business_id` where `status != 'canceled'` — one
live subscription per business.

**`billing.invoices`**

id UUIDv7 · subscription_id FK → billing.subscriptions · amount_paise int ·
currency TEXT default 'INR' · status TEXT CHECK
('issued','paid','failed','void') · razorpay_invoice_id TEXT UNIQUE ·
pdf_key TEXT (storage key, never a URL) · period_start/period_end ·
timestamps.

**`billing.payment_events`** — the raw webhook log.

id UUIDv7 · provider TEXT default 'razorpay' · provider_event_id TEXT
**UNIQUE** (the dedupe key) · event_type TEXT · payload JSONB (scrubbed —
see §4) · outcome TEXT · received_at.

**Append-only by grant:** `REVOKE UPDATE, DELETE ON billing.payment_events
FROM app_rt`. Webhook processing happens in the same transaction as the
insert, so the row is never updated: `outcome` is written once at insert
time.

Grants: `GRANT SELECT, INSERT, UPDATE, DELETE` per table to `app_rt`, then
the payment_events revoke.

## 2. Razorpay client + configuration

`modules/billing/razorpay_client.py` — thin async wrapper over
`httpx.AsyncClient` with basic auth (`key_id:key_secret`). Only the calls we
need: create subscription, fetch subscription, cancel subscription, fetch
invoice(s). **Every live-call method checks `billing_enabled` first and
raises `BillingDisabledError` when off** — defense in depth beneath the
route-level 404. No other module imports this client. Tests use a fake
client injected at the service layer; no network in any test.

New settings (settings.py):

```
razorpay_key_id: str = ""
razorpay_key_secret: str = ""
razorpay_webhook_secret: str = ""
razorpay_plan_id_growth: str = ""   # filled after KYC + plan creation
razorpay_plan_id_pro: str = ""
dunning_retry_hours: str = "24,72,168"   # cumulative offsets from past_due_since
dunning_grace_days: int = 7              # window after last retry before cancel
billing_worker_enabled: bool = True
```

`modules/billing/tiers.py` — the single place tier vocabulary lives:
`TIERS = {"growth": ..., "pro": ...}` with display name, placeholder price
(paise), period, and which settings field holds the Razorpay plan id.
Pricing v1 edits only this file + settings values.

## 3. Endpoints + flag gate

All on the existing `/billing` SecureRouter. A `require_billing_enabled`
dependency raises 404 when the flag is off — request-time, because the flag
is DB-driven (contrast: MSG91's env-conditional mount, which needs a
deploy). Flag off ⇒ every route below, webhook included, is a 404 and no
code path can reach a live Razorpay call.

| route | auth | behaviour |
|---|---|---|
| POST /billing/subscriptions | business owner | validates tier + business ownership (directory public interface), creates Razorpay subscription, persists row, returns hosted checkout `short_url`. Card entry happens on Razorpay's page — no card data ever touches us. Local status is `active` with `current_period_end = NULL` until the first `subscription.charged` webhook sets the period — the 3-state enum deliberately has no pre-charge state; Razorpay's `created/authenticated` map to this active+NULL shape and reconciliation treats that pair as consistent. |
| GET /billing/subscription | business owner | current subscription for the caller's business (or none = free) |
| GET /billing/invoices | business owner | cursor-paginated invoice list |
| POST /billing/webhook/razorpay | `public=True`, signature-gated | §4 |
| GET /billing/admin/subscriptions | super_admin | cursor-paginated, coins-admin `_require_role` pattern |
| POST /billing/admin/subscriptions/{id}/cancel | super_admin | force-cancel; writes an `audit()` entry |

`public_routes.txt` gains `/billing/webhook/razorpay` with a justification
comment: provider callback, HMAC-signature-gated, flag-gated 404 when
billing is dark, body never logged.

## 4. Webhook flow (money path — 🔍 review target)

1. Flag check → 404 before reading the body.
2. Read **raw body**; compute HMAC-SHA256 with `razorpay_webhook_secret`;
   compare to `X-Razorpay-Signature` with `hmac.compare_digest`. Mismatch →
   400, increment a forgery counter, log nothing from the payload.
3. Event id from the `x-razorpay-event-id` header. `INSERT INTO
   payment_events ... ON CONFLICT (provider_event_id) DO NOTHING RETURNING
   id`. No row returned ⇒ replay ⇒ 200 immediately, zero side effects
   (**replay = one effect**, non-negotiable 1).
4. Scrub before persist: strip `card`, `vpa`, `contact`, `email`, `token`
   fields from the payload JSON (recursive key filter). "Never store card
   data" applies to the raw log; the D05 PII scrubber stays the last line of
   defence for telemetry, not a licence here.
5. Process in the **same transaction**: `SELECT ... FOR UPDATE` on the
   subscription row, apply the transition, capture notify payloads before
   commit, publish bus events after commit (D16 decision-route
   choreography).

Event handling:

| Razorpay event | effect |
|---|---|
| subscription.charged | status → active, extend current_period_end, reset dunning fields, upsert invoice, emit `billing.subscription_activated` (first) / `billing.subscription_renewed` |
| subscription.pending / charge failed | dunning entry (§5), emit `billing.payment_failed` |
| subscription.halted | treat as dunning-exhausted signal: keep local machine authoritative, sync on next tick |
| subscription.cancelled / completed | status → canceled, emit `billing.subscription_canceled` |
| invoice.paid / invoice.expired | invoice status sync |
| anything else | logged event row with outcome `ignored` |

Unknown business/subscription references: record row with outcome
`unmatched`, 200 (never 5xx a provider retry loop for our own data gap —
reconciliation catches real drift).

## 5. Dunning state machine (v5 patch)

Config-driven, flag-gated, clock-injected (`now=` parameter everywhere —
tests never sleep).

- **Failure:** `active → past_due`, `dunning_attempt = 1`,
  `past_due_since = now`, `next_retry_at = now + retry_hours[0]`, emit
  `billing.payment_failed`.
- **Tick:** `modules/billing/worker.py` (notify-worker shape:
  `python -m modules.billing.worker`, consume + periodic
  `run_due_dunning(session, now)`). For each `past_due` sub with
  `next_retry_at <= now`: re-sync state from Razorpay (Razorpay auto-retries
  the charge; our step = sync + remind), emit `billing.dunning_reminder`,
  advance `dunning_attempt`, set next offset.
- **Recovery:** a `subscription.charged` webhook at any point → active,
  dunning fields reset.
- **Exhaustion:** schedule consumed **and**
  `now > past_due_since + last_offset + grace_days` → cancel at Razorpay
  (live call, flag-gated), local `canceled`, emit
  `billing.subscription_canceled`.
- Worker no-ops entirely (no reads, no calls) when `billing_enabled` is
  off or `billing_worker_enabled` is false.

**Notify wiring** (D18 lesson: templates and routes land together): add
`"billing"` to notify `STREAMS`; `EVENT_ROUTES` entries + seeded templates
for `dunning_payment_failed`, `dunning_reminder`, `subscription_canceled`,
`subscription_activated` — email + in-app. Billing events are
self-contained (D12 contract): billing resolves the owner's email/locale
via identity's public service interface at emit time; payloads carry
destination, are used once, never logged.

## 6. Reconciliation (nightly)

`scripts/billing_reconcile.py`, coins_integrity shape, cron-run nightly.
For every local non-canceled subscription with a `razorpay_sub_id`: fetch
remote, compare status + period end; same for invoice paid-status. Any
mismatch → structured log (ids only), `billing_reconcile_mismatch_total`
Prometheus counter, non-zero exit code. Flag off → exit 0 immediately,
zero live calls. Non-negotiable 4's test injects a divergent fake-client
state and asserts detection.

## 7. Business Console shell — web-agri `/business/*`

`apps/web-agri/app/business/layout.tsx` becomes the console shell:
server-side auth gate (redirect to login), fetches owned-business context
and subscription tier, renders module navigation from a registry.

**Mount contract** (the AuthCluster lesson applied to dashboards):
`apps/web-agri/lib/console-modules.ts` exports an ordered list of

```ts
{ id, title, href, requires?: { business?: true, minTier?: "growth"|"pro", flag?: string } }
```

A later spec adds a console module by (1) adding its route segment under
`app/business/<module>/`, (2) appending one registry entry. The layout is
never edited for a new module — extend, not fork.

- D18's `/business/inbox` is absorbed as the first registered module
  (page untouched, now rendered inside the shell).
- D15 listings and D17 products get registry entries pointing at their
  existing management surfaces (mount points, not rebuilds).
- New `/business/billing` page: subscription card (tier, status, period
  end, placeholder pricing from a tiers endpoint), cursor-paginated invoice
  list. Registry entry declares `flag: "billing_enabled"` → flag off means
  absent from nav **and** the page itself 404s (server-side flag read
  through the backend flags API). No client-side Razorpay JS anywhere in
  this spec — checkout is a redirect to Razorpay's hosted `short_url`.

Design tokens only; layout matches docs/design-system.md.

## 8. Threat model → mechanism map

| threat | mechanism |
|---|---|
| webhook forgery | HMAC-SHA256 over raw body, constant-time compare, secret from env |
| replay | `payment_events.provider_event_id` UNIQUE + ON CONFLICT DO NOTHING short-circuit |
| state drift | nightly reconciliation + mismatch metric |
| premature charging | flag gates routes (404), client (raises), worker (no-op), console (hidden); plan ids empty until KYC |
| card data at rest | hosted checkout only + payload scrub before persist |
| PII in logs | body never logged; ids-only structured logs; D05 scrubber as backstop |

## 9. Test matrix (maps to non-negotiables + DoD)

1. **Signature:** bad/missing HMAC → 400, no payment_events row.
2. **Idempotency:** same event id delivered twice → one row, one state
   effect (replay test).
3. **Flag off:** every /billing route + webhook → 404; client method →
   `BillingDisabledError`; worker tick and reconcile script no-op; console
   nav omits billing module.
4. **Dunning transitions:** failed → past_due (+schedule set) → reminders
   on due ticks → canceled on exhaustion+grace; charged-during-past_due →
   active with fields reset.
5. **Reconciliation:** injected mismatch detected (log + counter + exit).
6. **Append-only grant:** app_rt UPDATE/DELETE on payment_events fails
   (0015-style grant test).
7. **Scrub:** webhook payload containing card/vpa/contact/email → stored
   payload lacks them.
8. **Audit:** admin cancel writes an audit entry.
9. Gates: mypy + lint-imports locally before first push; ruff-format per
   task; Lighthouse unaffected (console is noindex, auth-gated — no public
   page added).

## Out of scope

Goods/checkout of any kind · card storage · real pricing numbers
(Pricing v1) · ads console (D21) · VPS cron installation (owner-driven,
deferred) · live Razorpay credentials.
