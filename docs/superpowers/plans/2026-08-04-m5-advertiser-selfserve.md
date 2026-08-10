# M5 — Advertiser Self-Serve + Rate Card + Billing Live Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** A brand signs into the D26 Business Console, builds a campaign in a wizard (slots → categories → pincodes/tier targeting → schedule+budget → creatives → review+price → pay via Razorpay TEST), the payment lands as a signature-verified webhook that appends to a new append-only billing ledger and advances the campaign to moderation; creative approval in the D21 Ops queue activates it; it serves at the targeted pincode×category and nowhere else, with advertiser analytics from the delivery log.

**Architecture:** Ads and billing stay import-independent: ads owns campaigns/pricing/lifecycle (`modules/ads/{pricing,lifecycle,selfserve_router}.py`), billing owns money (`modules/billing/ad_orders.py`, new `billing.ad_orders` + `billing.ledger_entries` tables, Razorpay Payment Links). They talk only through two new `shared.lookups` registries (campaign-billing resolver: ads→billing reads price/status; campaign-payment hook: billing→ads flips lifecycle). Activation = `maybe_activate()` requiring BOTH `paid_at` ∧ all-creatives-approved, called from the payment hook and from the D21 `CreativeSource` decision (in the ops tx). The wizard is one new D26 console module (`app/business/ads/` + one `CONSOLE_MODULES` entry). Checkout is a hosted-`short_url` redirect (repo rule: no payment JS); e2e completes payment via a flag-gated Razorpay stub + a self-signed webhook.

**Tech Stack:** FastAPI + SQLAlchemy async + Alembic (backend/core, host Python 3.12), fpdf2 (new: GST invoice PDFs), Razorpay Payment Links REST (extend the existing hand-rolled httpx client), Next.js 15 / React 19 / Tailwind 3 tokens (apps/web-agri :3002, apps/web-admin :3004), Playwright e2e.

## Global Constraints

- Branch `feat/m5-advertiser-selfserve` (already checked out, at dev tip). NEVER commit to dev/main. Conventional commits. PR targets dev. Theme: `feat(m5): advertiser self-serve + billing`.
- Toolchain: host Python 3.12, no uv, no gh CLI (PR via credential-fill API). Node 24 / pnpm 11 / Tailwind 3.
- Backend tests: dockerised Postgres :45432 + Redis; the suite DROP/CREATEs `agri_test` — **never run two pytest processes in parallel**; storm tests (`-m slow`) always as their own run.
- Gates per task, not at the end: `mypy --strict`, `ruff check`, `ruff format`, `lint-imports` (run from `backend/core`), line length 100. `T20` bans print.
- Migrations: hand-written, next ids **0033/0034/0035**, filled `# -- THREAT/NOTES:` block, no `TODO` anywhere in the file, `op.f()` on BOTH create and drop of named constraints, clean downgrade (CI migrate_check runs up→down→up). NEVER run migrate_check locally against the dev DB (wipes it).
- `SecureRouter`: every endpoint needs a return annotation; private + rate-limited by default. **M5 adds no new public routes** (`public_routes.txt` untouched — the Razorpay webhook is already public).
- Cursor pagination only (`shared.pagination.paginate`); OFFSET is lint-banned (uppercase word ban includes raw SQL in migrations).
- Money is **integer paise** everywhere; multipliers are **basis points** (int); no floats in money math. Never name a billing model `LedgerEntry` — `check_ledger_writes` regex-matches `LedgerEntry\s*\(` repo-wide; use `BillingLedgerEntry`.
- All image handling through `shared.media.reencode_image` — any new `import PIL`/`Image.open(` outside `shared/media.py` fails `check_media_fork`. The spec's word "presigned" is overridden by the repo rule: uploads are multipart → re-encode → `storage.put_object` (this still delivers the spec's intent: type/size, re-encode, EXIF strip by construction).
- Payments through the billing module ONLY: no Razorpay import/call outside `modules/billing/`. Server-side pricing only: the client never sends an amount; every amount is recomputed server-side at checkout.
- No mutable balance column: spend derives from `budget_serves_used` (serve credits) and money from `billing.ledger_entries` only.
- Frontend: tokens only (`pnpm check:hex`), touch targets ≥44px, mobile-first (console clients use only `sm:`), `Modal` cannot be driven programmatically, web-agri has NO ToastProvider (inline status), `Button` has `flex-1` (constrain with `max-w-*`).
- Console contract: new module = `app/business/ads/page.tsx` + ONE `CONSOLE_MODULES` entry; layout edited only to extend the gate mechanism (mirror `billingVisible`).
- New notify template keys: migration seed (en/ta/hi × channels) + `EXPECTED_CHANNELS` in `test_notify_templates.py` + `EVENT_ROUTES` (+ its pin test `test_notify_consumers.py`) in the same commit.
- `prod billing_enabled stays FALSE` — flags are DB-seeded false; dev/staging flips are runtime actions (ops UI/SQL), never migration-seeded true.
- Non-negotiables (spec): NN1 e2e create→pay(test)→approve→serves at targeted pincode×category ∧ NOT elsewhere · NN2 forged/replayed webhook rejected (test) · NN3 ledger sums = Razorpay test transactions exactly (reconciliation test) · NN4 campaign IDOR: owned_by on every campaign read/write (test).
- Money path (standing rule): Tasks 8–12 files are listed for line-by-line human review in the PR body; an adversarial second-pass review runs before the PR (Task 19).

## Design decisions locked in

1. **Lifecycle states** (spec D): widen `ck_ads_campaigns_status` to `draft, pending_payment, pending_moderation, active, paused, exhausted, expired, archived`. `exhausted`/`expired` are flipped durably by the ads worker sweep (and derived in read DTOs so the UI never shows stale `active`); the serve path never needs them — `eligible_placements` already excludes by budget predicate and flight window.
2. **Activation is a conjunction**: `lifecycle.maybe_activate(campaign)` → `active` only when `paid_at IS NOT NULL` ∧ ≥1 approved creative ∧ 0 pending creatives. Called (a) from the payment hook after `pending_payment→pending_moderation`, (b) from `CreativeSource._decide` after approve — both inside the owning transaction, so there is no window where an unpaid or unmoderated campaign serves (threat: moderation bypass / activation before payment).
3. **Edit-after-approve re-moderation** (threat): any creative content change (copy/media/target_url) resets `moderation_status='pending'`; if its campaign is `active` it drops to `pending_moderation` in the same tx. Serve-side is double-safe: `eligible_placements` filters `Creative.moderation_status=='approved'` regardless of campaign status.
4. **CPM v1 = per-serve credits** (owner-visible simplification, documented in the PR): M3's `budget_serves_total/used` atomic decrement is the billing unit ("ad views"). A CPM purchase of N views sets `budget_serves_total=N`. Viewport impressions/clicks stay analytics-only. True impression-billing is deferred (would need beacon-side atomic charging).
5. **Rate card = versioned append-only config** (`ads.rate_card_versions`: `version` UNIQUE, `config` JSONB, INSERT+SELECT grants only — spec_schemas precedent). Newest version is active. Config shape (all ints): `{"cpm_paise": {"1"..."5"}, "flat_weekly_paise": {"1"..."5"}, "category_multipliers_bp": {"<slug>": bp}, "min_total_paise": int}`; missing category ⇒ 10000 bp (×1.0). Migration 0033 seeds version 1 so pricing works day-0; Ops POSTs later versions.
6. **Price = f(slot, tier, category)** via `modules/ads/pricing.py`: pricing model derives from slots (`milk_sponsored_listing` ⇒ flat_weekly, banner slots ⇒ cpm; mixing ⇒ 422). Tier for pricing = **best (lowest number) tier reached by the targeting**: explicit pincodes ⇒ `min(get_tier(p))`; `tiers` targeting ⇒ `min(tiers)`; ALL/global ⇒ 1 (all-India reach prices at T1). Category multiplier = max bp among targeted categories; ALL categories ⇒ 10000. GST added on top (`gst_rate_bp=1800` setting), integer math (`ceil` via `-(-a//b)`).
7. **Tier targeting** ("all T3 towns in TN"): `GeoTargetIn` gains `tiers: list[int]|None` (1..5, ≤5). It is a *filter* like `categories`, not a geo rung: serve computes `get_tier(pincode)` BEFORE `eligible_placements` (reorder in `router.serve`) and passes it in; `tier_matches(geo_target, tier)` excludes candidates whose `tiers` key doesn't contain the viewer's tier (no-pincode request ⇒ tier None ⇒ tier-targeted placements never match — fail closed). The 50-pincode cap stays; "ALL" = `{}` (global) unchanged.
8. **Money tables** (billing schema, migration 0034):
   - `billing.ad_orders`: one row per checkout attempt. `campaign_id`/`business_id` bare UUIDs (no cross-module FK). `status ∈ created|paid|failed|expired|refunded`; partial unique index on `campaign_id WHERE status IN ('created','paid')` (one live order per campaign; expired orders allow re-checkout). Stores the full itemized quote snapshot (JSONB) + `subtotal_paise/gst_paise/total_paise` + `razorpay_plink_id UNIQUE` + `razorpay_payment_id`.
   - `billing.ledger_entries` (model `BillingLedgerEntry`): append-only by grant AND trigger (`billing.forbid_ledger_mutation`, coins/0031 precedent). `entry_type ∈ ad_charge|ad_refund`, `amount_paise` signed (charge >0, refund <0, CHECK enforces sign), `order_id` FK, `campaign_id`, `business_id`, `razorpay_payment_id`, `meta` JSONB. Reconciliation and campaign spend read ONLY this.
   - `billing.invoices` alters: `subscription_id` nullable + `order_id` nullable FK + CHECK at least one; `invoice_number` TEXT UNIQUE (ad invoices only), `taxable_paise`, `gst_paise` (nullable — legacy sub rows stay NULL). Sequence `billing.invoice_number_seq`; number `MILK-{FY}-{seq:06d}` (Indian FY, e.g. `MILK-26-27-000001`) assigned in the webhook tx.
9. **Checkout flow**: wizard → `POST /billing/ad-orders {campaign_id, buyer_gstin?}` → billing resolves the campaign via the new lookup (fail-closed), re-quotes server-side (never trusts a client amount), creates a Razorpay **Payment Link** (`create_payment_link`; hosted `short_url` — no payment JS, D20 rule), inserts the order, calls the payment hook with `"checkout"` (ads flips `draft→pending_payment`), returns `{order, checkout_url}`. Browser redirects to Razorpay; callback returns to `/business/ads?paid=<campaign_id>` and the page polls status (webhook may lag).
10. **Webhook**: extend `HANDLED_EVENTS` with `payment_link.paid`, `payment_link.expired`, `refund.processed`, routed to `modules/billing/ad_orders.py` appliers inside the existing verified/deduped tx (signature = existing HMAC over raw body; dedupe = existing body-hash `provider_event_id`; plus order-level idempotency: already-paid order ⇒ outcome `ignored`, no second ledger row). `payment_link.paid`: FOR UPDATE order by plink id → `paid` + payment id → ledger `ad_charge` → invoice row + number → hook `"paid"` (ads: `pending_payment→pending_moderation` + `maybe_activate`). `refund.processed`: ledger `ad_refund` (negative) → order `refunded` → hook `"refunded"` (ads: pause + audit). `payment_link.expired`: order `expired` (campaign stays `pending_payment`; re-checkout allowed).
11. **Invoice PDF is async**: the webhook tx stays pure-DB. The existing billing worker tick gains `run_invoice_pdf_sweep`: finds paid ad invoices with `pdf_key IS NULL`, generates the GST PDF (fpdf2), `put_object` under private `invoices/` (NO `ensure_prefix_public_read`), sets `pdf_key`, emits `billing.ad_invoice` → notify emails it as an attachment. Email attachments: extend the `EmailDriver` protocol with `attachments: Sequence[tuple[str, bytes, str]] = ()`; `dispatch()` fetches bytes from storage when the payload carries `attachment_key` (StorageError ⇒ delivery failure ⇒ normal retry). Advertiser download route streams the PDF (regenerating on miss).
12. **Analytics** (spec E): `GET /ads/my/campaigns/{id}/stats` — exact impressions/clicks/CTR by day from the partitioned tracking tables (join `placements.campaign_id`), spend derived `price_paise × budget_serves_used ÷ budget_serves_total` (flat: full price once active), by-pincode/by-category/by-tier from `ads.delivery_decisions`. Paid campaigns bypass sampling: `log_delivery` gains `always: bool` set when `campaign.price_paise IS NOT NULL` (house/admin campaigns keep the 10% sample).
13. **e2e payment in CI**: new setting `razorpay_test_stub: bool = False` (OTP_TEST_PEEK precedent). When true, `create_payment_link` returns a canned deterministic response (`plink_test_<campaign hex>`, `short_url` = local callback) without HTTP; `fetch_payment` returns a canned captured payment. `scripts/e2e-api.mjs` sets `RAZORPAY_TEST_STUB=true` + `RAZORPAY_WEBHOOK_SECRET=whsec_e2e` + `ADS_DELIVERY_LOG_SAMPLE=1.0` and flips `billing_enabled`; the Playwright spec signs its own `payment_link.paid` webhook with that secret. A guard test asserts the stub defaults off and dev compose files never set it.
14. **Admin guard**: `POST /admin/ads/campaigns/{id}/status` refuses `active` for priced campaigns without `paid_at` (422 `payment_required`) — staff cannot accidentally activate an unpaid self-serve campaign. House/admin campaigns (`price_paise IS NULL`) keep the old behaviour.
15. **Console mount**: `ConsoleGate` union widens to `"billing" | "ads"`; layout gains `adsVisible()` probing `GET /ads/my/campaigns?limit=1` (404-while-dark, same shape as `billingVisible`). The `/api/ads` BFF proxy adds first-segment `my` **with** bearer (serve/beacons stay tokenless) and switches to raw-byte body forwarding (multipart creative upload needs the boundary preserved — catalog proxy pattern). `/api/billing` allowlist adds `ad-orders`.
16. **Dunning "wired"** = the existing D20 subscription dunning simply goes live with the flag flip (it is already built and worker-driven); one-time ad orders don't dun — a failed/abandoned link expires and the campaign sits in `pending_payment` for re-checkout. Refunds are Razorpay-dashboard-initiated, handled via webhook (decision 10). No new dunning code.

## File structure (new/modified)

Backend (`backend/core/`):
- Create: `modules/ads/pricing.py`, `modules/ads/lifecycle.py`, `modules/ads/selfserve_router.py`, `modules/ads/selfserve_schemas.py`, `modules/billing/ad_orders.py`, `modules/billing/invoice_pdf.py`, `alembic/versions/0033_ads_selfserve.py`, `alembic/versions/0034_billing_ad_orders.py`, `alembic/versions/0035_m5_notify_templates.py`
- Modify: `modules/ads/models.py`, `modules/ads/service.py` (tier filter, log_delivery `always`), `modules/ads/router.py` (serve reorder), `modules/ads/admin_router.py` (rate-card routes + status guard), `modules/ads/moderation_sources.py` (maybe_activate + re-moderation event), `modules/ads/worker.py` (lifecycle sweep), `modules/billing/models.py`, `modules/billing/razorpay_client.py`, `modules/billing/service.py` (HANDLED_EVENTS routing), `modules/billing/router.py` (ad-orders route), `modules/billing/worker.py` (invoice sweep), `modules/billing/reconcile.py`, `modules/notify/drivers.py` + `modules/notify/service.py` + `modules/notify/consumers.py` (attachments + routes), `shared/lookups.py`, `settings.py`, `main.py`, `pyproject.toml` (fpdf2)
- Tests: `tests/test_ads_pricing.py`, `tests/test_ads_selfserve.py`, `tests/test_ads_lifecycle.py`, `tests/test_ads_tier_targeting.py`, `tests/test_ads_selfserve_migration.py`, `tests/test_billing_ad_orders.py`, `tests/test_billing_ad_webhook.py`, `tests/test_billing_ledger_migration.py`, `tests/test_billing_invoice_pdf.py`, `tests/test_ads_selfserve_stats.py` (+ edits to `test_notify_templates.py`, `test_notify_consumers.py`, `test_billing_reconcile.py`, `test_ads_admin.py`, `test_ads_serve.py`)

Frontend:
- Create: `apps/web-agri/app/business/ads/page.tsx`, `apps/web-agri/app/business/ads/ads-console-client.tsx`, `apps/web-agri/app/business/ads/campaign-wizard.tsx`, `apps/web-agri/app/business/ads/wizard-steps.tsx`
- Modify: `apps/web-agri/lib/console-modules.ts`, `apps/web-agri/app/business/layout.tsx` (gate), `apps/web-agri/app/api/ads/[...path]/route.ts`, `apps/web-agri/app/api/billing/[...path]/route.ts`, `apps/web-admin/app/ads/ads-manager.tsx` (rate-card panel)
- E2E: `e2e/advertiser-selfserve.spec.ts`, `scripts/e2e-api.mjs`
- Docs: `docs/qa/manual-test-d23-d29.md` sibling M5 section (follow the repo's current QA-guide layout), `docs/runbooks/billing-flag-flip.md` additions

---

### Task 0: Worktree + baseline

- [ ] **Step 1:** Use superpowers:using-git-worktrees to get an isolated workspace for `feat/m5-advertiser-selfserve` (branch already exists at dev tip; `.worktrees/` exists).
- [ ] **Step 2:** Baseline (docker test services up): `cd backend/core && python -m pytest tests/test_ads_serve.py tests/test_billing_webhook.py tests/test_ads_admin.py -q` — expect PASS before touching anything.

---

### Task 1: Migration 0033 — ads self-serve schema + seeded rate card v1

**Files:**
- Create: `backend/core/alembic/versions/0033_ads_selfserve.py`
- Modify: `backend/core/modules/ads/models.py`
- Test: `backend/core/tests/test_ads_selfserve_migration.py`

**Interfaces:**
- Produces: `Campaign` new ORM columns `pricing_model: str|None`, `price_paise: int|None` (the GST-inclusive total), `price_subtotal_paise: int|None`, `price_gst_paise: int|None` (decomposition — billing invoices read these via the lookup, never re-derive), `rate_card_version: int|None`, `paid_at: datetime|None`, `daily_serve_cap: int|None`; new model `RateCardVersion(id, version, config, created_by_user_id, created_at)` (`ads.rate_card_versions`); campaign status CHECK now admits the 8 lifecycle values. Task 2 reads `RateCardVersion`; Task 6 writes the campaign columns. (Migration/model/test steps below: add `price_subtotal_paise` and `price_gst_paise` INT NULL alongside `price_paise` everywhere `price_paise` appears, same nonneg CHECK pattern.)

- [ ] **Step 1: Write failing migration tests** (`test_ads_selfserve_migration.py`, pattern from `test_ads_migration.py` — raw SQL against `database_url` fixture):

```python
"""M5 migration 0033: lifecycle statuses, pricing columns, rate_card_versions."""

import pytest
from sqlalchemy import text
from sqlalchemy.ext.asyncio import create_async_engine
from sqlalchemy.pool import NullPool


@pytest.fixture
async def engine(database_url: str):
    eng = create_async_engine(database_url, poolclass=NullPool)
    yield eng
    await eng.dispose()


async def test_campaign_lifecycle_statuses_accepted(engine) -> None:
    async with engine.begin() as conn:
        for status in ("pending_payment", "pending_moderation", "exhausted", "expired"):
            await conn.execute(
                text(
                    "INSERT INTO ads.campaigns"
                    " (id, advertiser_business_id, name, status, flight_start, flight_end)"
                    " VALUES (gen_random_uuid(), gen_random_uuid(), 'm5', :status,"
                    " current_date, current_date + 7)"
                ),
                {"status": status},
            )
        await conn.execute(text("DELETE FROM ads.campaigns WHERE name = 'm5'"))


async def test_campaign_bogus_status_rejected(engine) -> None:
    from sqlalchemy.exc import IntegrityError

    async with engine.connect() as conn:
        with pytest.raises(IntegrityError):
            await conn.execute(
                text(
                    "INSERT INTO ads.campaigns"
                    " (id, advertiser_business_id, name, status, flight_start, flight_end)"
                    " VALUES (gen_random_uuid(), gen_random_uuid(), 'm5', 'bogus',"
                    " current_date, current_date + 7)"
                )
            )


async def test_pricing_columns_exist_and_price_nonnegative(engine) -> None:
    from sqlalchemy.exc import IntegrityError

    async with engine.connect() as conn:
        cols = await conn.execute(
            text(
                "SELECT column_name FROM information_schema.columns"
                " WHERE table_schema='ads' AND table_name='campaigns'"
            )
        )
        names = {row[0] for row in cols}
        assert {"pricing_model", "price_paise", "rate_card_version", "paid_at",
                "daily_serve_cap"} <= names
        with pytest.raises(IntegrityError):
            await conn.execute(
                text(
                    "INSERT INTO ads.campaigns"
                    " (id, advertiser_business_id, name, status, flight_start, flight_end,"
                    " price_paise) VALUES (gen_random_uuid(), gen_random_uuid(), 'm5',"
                    " 'draft', current_date, current_date + 7, -1)"
                )
            )


async def test_rate_card_seeded_and_append_only(engine) -> None:
    from sqlalchemy.exc import ProgrammingError

    async with engine.connect() as conn:
        row = (
            await conn.execute(
                text("SELECT version, config FROM ads.rate_card_versions ORDER BY version DESC")
            )
        ).first()
        assert row is not None and row.version == 1
        assert set(row.config) >= {"cpm_paise", "flat_weekly_paise", "category_multipliers_bp",
                                   "min_total_paise"}
        # app_rt must not UPDATE/DELETE (append-only by grant)
        with pytest.raises(ProgrammingError, match="permission denied"):
            await conn.execute(text("UPDATE ads.rate_card_versions SET version = version"))
```

- [ ] **Step 2: Run to verify failure**: `python -m pytest tests/test_ads_selfserve_migration.py -q` → FAIL (columns/table missing).
- [ ] **Step 3: Write the migration** `0033_ads_selfserve.py` (`revision="0033"`, `down_revision="0032"`):

```python
"""M5: campaign lifecycle statuses + pricing columns + versioned rate card.

# -- THREAT/NOTES:
# downgrade data loss: pricing columns and rate_card_versions dropped; lifecycle
#   statuses collapsed (pending_* -> draft, exhausted/expired -> archived) before
#   the CHECK is re-narrowed.
# locks: ALTER TABLE on ads.campaigns takes ACCESS EXCLUSIVE briefly; table is small.
# rollout: seeds rate card v1 so pricing works before any Ops edit. price_paise is
#   NULL for all pre-M5 (house/admin) campaigns - NULL means "not a paid campaign".
"""

import sqlalchemy as sa
from alembic import op

revision: str = "0033"
down_revision: str | None = "0032"
branch_labels = None
depends_on = None

LIFECYCLE = (
    "'draft','pending_payment','pending_moderation','active',"
    "'paused','exhausted','expired','archived'"
)

DEFAULT_RATE_CARD = {
    "cpm_paise": {"1": 30000, "2": 20000, "3": 12000, "4": 8000, "5": 5000},
    "flat_weekly_paise": {"1": 150000, "2": 100000, "3": 60000, "4": 40000, "5": 25000},
    "category_multipliers_bp": {"ghee": 12000, "paneer": 11000},
    "min_total_paise": 10000,
}


def upgrade() -> None:
    op.drop_constraint(op.f("ck_ads_campaigns_ck_ads_campaigns_status"), "campaigns",
                       schema="ads", type_="check")
    op.create_check_constraint(op.f("ck_ads_campaigns_status"), "campaigns",
                               f"status IN ({LIFECYCLE})", schema="ads")
    op.add_column("campaigns", sa.Column("pricing_model", sa.Text(), nullable=True),
                  schema="ads")
    op.add_column("campaigns", sa.Column("price_paise", sa.Integer(), nullable=True),
                  schema="ads")
    op.add_column("campaigns", sa.Column("rate_card_version", sa.Integer(), nullable=True),
                  schema="ads")
    op.add_column("campaigns", sa.Column("paid_at", sa.TIMESTAMP(timezone=True),
                                         nullable=True), schema="ads")
    op.add_column("campaigns", sa.Column("daily_serve_cap", sa.Integer(), nullable=True),
                  schema="ads")
    op.create_check_constraint(op.f("ck_ads_campaigns_price_nonneg"), "campaigns",
                               "price_paise IS NULL OR price_paise >= 0", schema="ads")
    op.create_check_constraint(op.f("ck_ads_campaigns_pricing_model"), "campaigns",
                               "pricing_model IS NULL OR pricing_model IN ('cpm','flat_weekly')",
                               schema="ads")

    op.create_table(
        "rate_card_versions",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("version", sa.Integer(), nullable=False, unique=True),
        sa.Column("config", sa.dialects.postgresql.JSONB(), nullable=False),
        sa.Column("created_by_user_id", sa.Uuid(), nullable=True),
        sa.Column("created_at", sa.TIMESTAMP(timezone=True),
                  server_default=sa.text("now()"), nullable=False),
        schema="ads",
    )
    op.execute("GRANT SELECT, INSERT ON ads.rate_card_versions TO app_rt")
    op.execute("REVOKE UPDATE, DELETE ON ads.rate_card_versions FROM app_rt")

    import json
    import uuid

    op.execute(
        sa.text(
            "INSERT INTO ads.rate_card_versions (id, version, config)"
            " VALUES (:id, 1, :config)"
        ).bindparams(id=uuid.uuid4(), config=json.dumps(DEFAULT_RATE_CARD))
    )


def downgrade() -> None:
    op.drop_table("rate_card_versions", schema="ads")
    op.drop_constraint(op.f("ck_ads_campaigns_pricing_model"), "campaigns", schema="ads",
                       type_="check")
    op.drop_constraint(op.f("ck_ads_campaigns_price_nonneg"), "campaigns", schema="ads",
                       type_="check")
    for col in ("daily_serve_cap", "paid_at", "rate_card_version", "price_paise",
                "pricing_model"):
        op.drop_column("campaigns", col, schema="ads")
    op.execute("UPDATE ads.campaigns SET status='draft'"
               " WHERE status IN ('pending_payment','pending_moderation')")
    op.execute("UPDATE ads.campaigns SET status='archived'"
               " WHERE status IN ('exhausted','expired')")
    op.drop_constraint(op.f("ck_ads_campaigns_status"), "campaigns", schema="ads",
                       type_="check")
    op.create_check_constraint(
        op.f("ck_ads_campaigns_ck_ads_campaigns_status"), "campaigns",
        "status IN ('draft','active','paused','archived')", schema="ads")
```

  **Verify the 0022 constraint's actual stored name first** (M3 trap — the metadata naming convention may have re-wrapped it): `docker exec agri-dev-postgres-1 psql -U app -d agri -c "SELECT conname FROM pg_constraint WHERE conrelid='ads.campaigns'::regclass AND contype='c'"` and use exactly that name in the `drop_constraint`. Column type for JSONB: import `from sqlalchemy.dialects import postgresql` and use `postgresql.JSONB()` (adjust the inline reference above accordingly).
- [ ] **Step 4: Add the ORM columns + model** in `modules/ads/models.py`:

```python
# on Campaign (after budget columns):
    # M5 self-serve pricing. NULL price_paise = house/admin campaign (never billed).
    pricing_model: Mapped[str | None] = mapped_column(Text, nullable=True)
    price_paise: Mapped[int | None] = mapped_column(Integer, nullable=True)
    rate_card_version: Mapped[int | None] = mapped_column(Integer, nullable=True)
    paid_at: Mapped[datetime | None] = mapped_column(TIMESTAMP(timezone=True), nullable=True)
    daily_serve_cap: Mapped[int | None] = mapped_column(Integer, nullable=True)


class RateCardVersion(UUIDv7PKMixin, Base):
    """Append-only pricing config (spec_schemas precedent): change = INSERT version N+1."""

    __tablename__ = "rate_card_versions"
    __table_args__ = {"schema": "ads"}

    version: Mapped[int] = mapped_column(Integer, nullable=False, unique=True)
    config: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False)
    created_by_user_id: Mapped[uuid.UUID | None] = mapped_column(nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        TIMESTAMP(timezone=True), server_default=func.now(), nullable=False
    )
```

- [ ] **Step 5: Run**: `python -m pytest tests/test_ads_selfserve_migration.py tests/test_ads_migration.py -q` → PASS (conftest re-runs `alembic upgrade head`). Then `mypy modules/ads/models.py && ruff check && ruff format`.
- [ ] **Step 6: Commit**: `git add -A backend/core && git commit -m "feat(m5): campaign lifecycle statuses, pricing columns, versioned rate card"`

---

### Task 2: Pricing engine — `modules/ads/pricing.py`

**Files:**
- Create: `backend/core/modules/ads/pricing.py`
- Test: `backend/core/tests/test_ads_pricing.py`

**Interfaces:**
- Consumes: `RateCardVersion` (Task 1), `shared.geo.service.get_tier(session, pincode) -> int` (M4 contract — NEVER query `geo.pincode_tiers` directly), `SLOT_KEYS` from `modules/ads/service.py`, `settings.gst_rate_bp`.
- Produces (Tasks 3/6/9 consume):
  - `class RateCardError(ValueError)` with `.code`
  - `def validate_rate_card(config: dict[str, Any]) -> None` (raises RateCardError: codes `missing_key`, `bad_tier_map`, `bad_multiplier`, `bad_min`)
  - `async def active_rate_card(session: AsyncSession) -> RateCardVersion` (highest version; raises RateCardError("no_rate_card") if table empty)
  - `def pricing_model_for_slots(slot_keys: Sequence[str]) -> str` — `"flat_weekly"` iff every slot endswith `_sponsored_listing`, `"cpm"` iff none does; mixed → RateCardError("mixed_pricing_models")
  - `async def tier_for_targeting(session: AsyncSession, geo_target: dict[str, Any]) -> int`
  - `@dataclass(frozen=True, slots=True) class QuoteLine: label: str; amount_paise: int`
  - `@dataclass(frozen=True, slots=True) class Quote: pricing_model: str; tier: int; multiplier_bp: int; serves_total: int | None; weeks: int | None; lines: tuple[QuoteLine, ...]; subtotal_paise: int; gst_paise: int; total_paise: int; rate_card_version: int`
  - `async def quote_campaign(session, *, slot_keys: Sequence[str], geo_target: dict[str, Any], categories: Sequence[str], flight_start: date, flight_end: date, serves_total: int | None) -> Quote` — cpm requires `serves_total` ≥ 1000 (RateCardError("serves_required"/"serves_too_small")); flat_weekly ignores serves and prices `weeks = ceil((flight_end - flight_start).days / 7)` (min 1); enforces `min_total_paise`.
- New setting: `gst_rate_bp: int = 1800` in `settings.py` (comment: `# M5 GST on ad sales, basis points`).

- [ ] **Step 1: Write failing tests** — key cases (use `db_session`; rate card v1 comes from the 0033 seed):

```python
"""M5 pricing: server-side only, integer paise, bp multipliers."""

import uuid
from datetime import date

import pytest

from modules.ads import pricing
from shared.geo.models import PincodeTier  # verify actual import path in shared/geo


def _ceil_div(a: int, b: int) -> int:
    return -(-a // b)


async def test_cpm_quote_priciest_tier_and_multiplier(db_session) -> None:
    # 641001 exists in geo.pincode_tiers with a real tier from the M4 snapshot;
    # write a T2 row explicitly so the assertion is deterministic.
    await pricing_test_helpers_upsert_tier(db_session, "641001", 2)
    quote = await pricing.quote_campaign(
        db_session,
        slot_keys=["milk_home_hero"],
        geo_target={"pincodes": ["641001"]},
        categories=["ghee"],
        flight_start=date(2026, 8, 10),
        flight_end=date(2026, 8, 24),
        serves_total=10_000,
    )
    # v1 card: cpm T2 = 20000 paise, ghee multiplier 12000bp
    expected_subtotal = _ceil_div(10_000 * 20000 * 12000, 1000 * 10000)
    assert quote.pricing_model == "cpm" and quote.tier == 2
    assert quote.subtotal_paise == expected_subtotal
    assert quote.gst_paise == _ceil_div(expected_subtotal * 1800, 10000)
    assert quote.total_paise == quote.subtotal_paise + quote.gst_paise
    assert quote.rate_card_version == 1


async def test_global_targeting_prices_tier1(db_session) -> None:
    quote = await pricing.quote_campaign(
        db_session, slot_keys=["milk_home_hero"], geo_target={}, categories=[],
        flight_start=date(2026, 8, 10), flight_end=date(2026, 8, 17), serves_total=1000,
    )
    assert quote.tier == 1 and quote.multiplier_bp == 10000


async def test_tier_targeting_prices_best_tier(db_session) -> None:
    quote = await pricing.quote_campaign(
        db_session, slot_keys=["milk_home_hero"],
        geo_target={"state": 33, "tiers": [3, 4]}, categories=[],
        flight_start=date(2026, 8, 10), flight_end=date(2026, 8, 17), serves_total=1000,
    )
    assert quote.tier == 3


async def test_flat_weekly_rounds_weeks_up(db_session) -> None:
    quote = await pricing.quote_campaign(
        db_session, slot_keys=["milk_sponsored_listing"],
        geo_target={"pincodes": ["641001"]}, categories=[],
        flight_start=date(2026, 8, 10), flight_end=date(2026, 8, 20),  # 10 days -> 2 weeks
        serves_total=None,
    )
    assert quote.weeks == 2 and quote.serves_total is None


async def test_mixed_slots_rejected(db_session) -> None:
    with pytest.raises(pricing.RateCardError) as exc:
        await pricing.quote_campaign(
            db_session, slot_keys=["milk_home_hero", "milk_sponsored_listing"],
            geo_target={}, categories=[], flight_start=date(2026, 8, 10),
            flight_end=date(2026, 8, 17), serves_total=1000,
        )
    assert exc.value.code == "mixed_pricing_models"


async def test_validate_rate_card_rejects_bad_config() -> None:
    good = dict(pricing.DEFAULT_CONFIG_KEYS_EXAMPLE)  # see Step 3; a valid literal dict
    for mutate, code in [
        (lambda c: c.pop("cpm_paise"), "missing_key"),
        (lambda c: c["cpm_paise"].pop("3"), "bad_tier_map"),
        (lambda c: c["cpm_paise"].update({"1": -5}), "bad_tier_map"),
        (lambda c: c["category_multipliers_bp"].update({"ghee": 0}), "bad_multiplier"),
        (lambda c: c.update({"min_total_paise": -1}), "bad_min"),
    ]:
        cfg = {k: dict(v) if isinstance(v, dict) else v for k, v in good.items()}
        mutate(cfg)
        with pytest.raises(pricing.RateCardError) as exc:
            pricing.validate_rate_card(cfg)
        assert exc.value.code == code
```

  Include a tiny module-level helper `pricing_test_helpers_upsert_tier(session, pincode, tier)` in the test file that INSERTs/UPDATEs a `geo.pincode_tiers` row via raw `text()` SQL (tests may do this; app code must not).
- [ ] **Step 2: Run to verify fail**: `python -m pytest tests/test_ads_pricing.py -q` → FAIL (module missing).
- [ ] **Step 3: Implement `pricing.py`** (~140 lines):

```python
"""M5 rate card + quoting. Server-side pricing ONLY (threat: price tampering).

All money is integer paise; multipliers are basis points. The client never sends
an amount - checkout re-quotes and stores the server number.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from datetime import date
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from modules.ads.models import RateCardVersion
from settings import get_settings
from shared.geo.service import get_tier

TIER_KEYS = ("1", "2", "3", "4", "5")
BP_ONE = 10000
MIN_CPM_SERVES = 1000
FLAT_SUFFIX = "_sponsored_listing"

# A valid config literal, used by tests and as documentation of the shape.
DEFAULT_CONFIG_KEYS_EXAMPLE: dict[str, Any] = {
    "cpm_paise": {"1": 30000, "2": 20000, "3": 12000, "4": 8000, "5": 5000},
    "flat_weekly_paise": {"1": 150000, "2": 100000, "3": 60000, "4": 40000, "5": 25000},
    "category_multipliers_bp": {"ghee": 12000},
    "min_total_paise": 10000,
}


class RateCardError(ValueError):
    def __init__(self, code: str) -> None:
        super().__init__(code)
        self.code = code


def _ceil_div(a: int, b: int) -> int:
    return -(-a // b)


def validate_rate_card(config: dict[str, Any]) -> None:
    for key in ("cpm_paise", "flat_weekly_paise", "category_multipliers_bp",
                "min_total_paise"):
        if key not in config:
            raise RateCardError("missing_key")
    for key in ("cpm_paise", "flat_weekly_paise"):
        tier_map = config[key]
        if (not isinstance(tier_map, dict) or set(tier_map) != set(TIER_KEYS)
                or not all(isinstance(v, int) and v > 0 for v in tier_map.values())):
            raise RateCardError("bad_tier_map")
    mults = config["category_multipliers_bp"]
    if not isinstance(mults, dict) or not all(
        isinstance(k, str) and isinstance(v, int) and v > 0 for k, v in mults.items()
    ):
        raise RateCardError("bad_multiplier")
    if not isinstance(config["min_total_paise"], int) or config["min_total_paise"] < 0:
        raise RateCardError("bad_min")


async def active_rate_card(session: AsyncSession) -> RateCardVersion:
    row = (
        await session.execute(
            select(RateCardVersion).order_by(RateCardVersion.version.desc()).limit(1)
        )
    ).scalar_one_or_none()
    if row is None:
        raise RateCardError("no_rate_card")
    return row


def pricing_model_for_slots(slot_keys: Sequence[str]) -> str:
    flats = [k for k in slot_keys if k.endswith(FLAT_SUFFIX)]
    if flats and len(flats) != len(slot_keys):
        raise RateCardError("mixed_pricing_models")
    return "flat_weekly" if flats else "cpm"


async def tier_for_targeting(session: AsyncSession, geo_target: dict[str, Any]) -> int:
    tiers = geo_target.get("tiers")
    if tiers:
        return min(int(t) for t in tiers)
    pincodes = geo_target.get("pincodes")
    if pincodes:
        return min([await get_tier(session, p) for p in pincodes])
    return 1  # ALL / district / state reach prices at the top tier


@dataclass(frozen=True, slots=True)
class QuoteLine:
    label: str
    amount_paise: int


@dataclass(frozen=True, slots=True)
class Quote:
    pricing_model: str
    tier: int
    multiplier_bp: int
    serves_total: int | None
    weeks: int | None
    lines: tuple[QuoteLine, ...]
    subtotal_paise: int
    gst_paise: int
    total_paise: int
    rate_card_version: int


async def quote_campaign(
    session: AsyncSession,
    *,
    slot_keys: Sequence[str],
    geo_target: dict[str, Any],
    categories: Sequence[str],
    flight_start: date,
    flight_end: date,
    serves_total: int | None,
) -> Quote:
    card = await active_rate_card(session)
    config = card.config
    model = pricing_model_for_slots(slot_keys)
    tier = await tier_for_targeting(session, geo_target)
    mults = config["category_multipliers_bp"]
    multiplier_bp = max((int(mults.get(c, BP_ONE)) for c in categories), default=BP_ONE)

    lines: list[QuoteLine] = []
    weeks: int | None = None
    if model == "cpm":
        if serves_total is None:
            raise RateCardError("serves_required")
        if serves_total < MIN_CPM_SERVES:
            raise RateCardError("serves_too_small")
        rate = int(config["cpm_paise"][str(tier)])
        subtotal = _ceil_div(serves_total * rate * multiplier_bp, 1000 * BP_ONE)
        lines.append(QuoteLine(f"{serves_total:,} ad views @ CPM T{tier}", subtotal))
    else:
        serves_total = None
        days = (flight_end - flight_start).days
        weeks = max(1, _ceil_div(days, 7))
        rate = int(config["flat_weekly_paise"][str(tier)])
        subtotal = _ceil_div(weeks * rate * multiplier_bp, BP_ONE)
        lines.append(QuoteLine(f"Sponsored listing x {weeks} wk @ T{tier}", subtotal))
    if multiplier_bp != BP_ONE:
        lines.append(QuoteLine(f"Category multiplier x{multiplier_bp / BP_ONE:g}", 0))
    if subtotal < int(config["min_total_paise"]):
        subtotal = int(config["min_total_paise"])
        lines.append(QuoteLine("Minimum order", subtotal))
    gst = _ceil_div(subtotal * get_settings().gst_rate_bp, BP_ONE)
    return Quote(
        pricing_model=model, tier=tier, multiplier_bp=multiplier_bp,
        serves_total=serves_total, weeks=weeks, lines=tuple(lines),
        subtotal_paise=subtotal, gst_paise=gst, total_paise=subtotal + gst,
        rate_card_version=card.version,
    )
```

  Add `gst_rate_bp: int = 1800` to `settings.py` in the billing block.
- [ ] **Step 4: Run**: `python -m pytest tests/test_ads_pricing.py -q` → PASS. `mypy modules/ads/pricing.py && ruff check && ruff format`.
- [ ] **Step 5: Commit**: `git commit -am "feat(m5): rate card pricing engine (tier x slot x category, integer paise)"`

---

### Task 3: Rate-card Ops surface — admin routes + web-admin panel

**Files:**
- Modify: `backend/core/modules/ads/admin_router.py`, `apps/web-admin/app/ads/ads-manager.tsx`
- Test: extend `backend/core/tests/test_ads_admin.py`

**Interfaces:**
- Consumes: `pricing.validate_rate_card`, `pricing.active_rate_card`, `RateCardVersion` (Tasks 1–2); existing `require_role`, `audit`, admin-router choreography (flush → audit → DTO-before-commit).
- Produces: `GET /admin/ads/rate-card` → `RateCardOut {version: int, config: dict, created_at: datetime}` (the active = newest version); `POST /admin/ads/rate-card` body `RateCardIn {config: dict}` → 201 `RateCardOut` (inserts version N+1; audit `ads.rate_card_published`). Version conflicts arbitrated by the UNIQUE index inside a savepoint → 409 `version_conflict` (D16 idiom).

- [ ] **Step 1: Write failing tests** in `test_ads_admin.py` (reuse its existing `api`/staff-header fixtures): `test_rate_card_get_returns_seeded_v1`, `test_rate_card_post_creates_v2_and_get_returns_it`, `test_rate_card_post_bad_config_422` (assert detail code is the `RateCardError.code`), `test_rate_card_post_requires_staff_403`, `test_rate_card_post_audited` (query `audit.entries` for action `ads.rate_card_published`).
- [ ] **Step 2: Run to verify fail**: `python -m pytest tests/test_ads_admin.py -k rate_card -q` → FAIL 404.
- [ ] **Step 3: Implement routes** in `admin_router.py` (schemas inline in `schemas.py`: `RateCardIn(config: dict[str, Any])`, `RateCardOut(version: int, config: dict[str, Any], created_at: datetime)`):

```python
@admin_router.get("/rate-card")
async def get_rate_card(request: Request, session: SessionDep) -> RateCardOut:
    require_role(request, STAFF, SUPER_ADMIN)
    try:
        card = await pricing.active_rate_card(session)
    except pricing.RateCardError as exc:
        raise HTTPException(status_code=404, detail=exc.code) from exc
    return RateCardOut(version=card.version, config=card.config, created_at=card.created_at)


@admin_router.post("/rate-card", status_code=201)
async def publish_rate_card(body: RateCardIn, request: Request,
                            session: SessionDep) -> RateCardOut:
    admin_id = require_role(request, STAFF, SUPER_ADMIN)
    try:
        pricing.validate_rate_card(body.config)
        current = await pricing.active_rate_card(session)
        next_version = current.version + 1
    except pricing.RateCardError as exc:
        if exc.code != "no_rate_card":
            raise HTTPException(status_code=422, detail=exc.code) from exc
        next_version = 1
    card = RateCardVersion(version=next_version, config=body.config,
                           created_by_user_id=admin_id)
    session.add(card)
    try:
        async with session.begin_nested():
            await session.flush()
    except IntegrityError as exc:
        raise HTTPException(status_code=409, detail="version_conflict") from exc
    await audit(session, action="ads.rate_card_published", actor_user_id=admin_id,
                target_type="rate_card", target_id=str(card.version),
                metadata={"version": card.version}, ip=_ip(request))
    out = RateCardOut(version=card.version, config=card.config, created_at=card.created_at)
    await session.commit()
    return out
```

- [ ] **Step 4: Run backend tests** → PASS; `mypy`, `ruff`, `ruff format`.
- [ ] **Step 5: web-admin panel** — add a `RateCardPanel` section to `apps/web-admin/app/ads/ads-manager.tsx` (same file, existing section pattern): fetch `GET /api/admin/ads/rate-card` (web-admin's `lib/api.ts` prefixes `/api/admin`), render the config as a `<textarea>` of pretty-printed JSON + current version chip, "Publish as v{N+1}" button POSTing `{config: JSON.parse(text)}` with inline error display (409/422 codes mapped to copy). Tokens only, `min-h-[44px]` controls, table/textarea inside `overflow-x-auto`.
- [ ] **Step 6: Frontend gates**: `pnpm -w typecheck && pnpm -w lint && pnpm check:hex` → PASS.
- [ ] **Step 7: Commit**: `git commit -am "feat(m5): ops-editable versioned rate card (admin routes + web-admin panel)"`

---

### Task 4: Tier targeting in the serve path

**Files:**
- Modify: `backend/core/modules/ads/service.py`, `backend/core/modules/ads/router.py`
- Test: `backend/core/tests/test_ads_tier_targeting.py` (+ keep `test_ads_serve.py` green)

**Interfaces:**
- Consumes: `get_tier` (M4), existing `GeoTargetIn`, `eligible_placements`, `router.serve`.
- Produces: `GeoTargetIn.tiers: list[int] | None` (1..5, `max_length=5`); `def tier_matches(geo_target: dict[str, Any], tier: int | None) -> bool`; `eligible_placements(..., tier: int | None = None)` applies it python-side (next to `category_matches`); `router.serve` computes `tier = await get_tier(session, pincode)` BEFORE `eligible_placements` and passes it (single get_tier call — reuse the value for `log_delivery`).

- [ ] **Step 1: Write failing tests** (`test_ads_tier_targeting.py`, reusing `test_ads_serve.py` fixtures/helpers by import — add the file to the `F811` per-file-ignores list in `pyproject.toml` if it imports the `api` fixture):
  - `test_tier_targeted_placement_serves_in_matching_tier`: upsert `geo.pincode_tiers` row for 641001 → tier 2; seed ad with `geo_target={"state": 33, "tiers": [2]}`; serve with `pincode=641001` → served.
  - `test_tier_targeted_placement_skipped_in_other_tier`: same ad; upsert 600001 → tier 3 (same state); serve at 600001 → `ad is None`.
  - `test_tier_targeted_placement_never_matches_without_pincode`: serve without `pincode` → `ad is None` (fail closed).
  - `test_unknown_pincode_defaults_tier4`: ad targeting `{"tiers": [4]}` + serve at `999999` (missing row ⇒ DEFAULT_TIER 4) → served.
  - `test_geo_target_tiers_validation`: admin placement create with `tiers: [0]` / `[1,2,3,4,5,1]` / `"x"` → 422.
- [ ] **Step 2: Run to verify fail.**
- [ ] **Step 3: Implement**: in `GeoTargetIn` add `tiers: list[Annotated[int, Field(ge=1, le=5)]] | None = Field(default=None, max_length=5)`. Add:

```python
def tier_matches(geo_target: dict[str, Any], tier: int | None) -> bool:
    """M5 tier targeting - a filter like categories, not a geo rung (fail closed)."""
    wanted = geo_target.get("tiers")
    if not wanted:
        return True
    return tier is not None and tier in {int(t) for t in wanted}
```

  Thread `tier` through `eligible_placements(session, *, slot_key, pincode, today, category=None, tier=None)` and add `if not tier_matches(target, tier): continue` in the candidate loop. In `router.serve`, hoist the existing `get_tier` call above `eligible_placements` and pass both `tier=tier` (eligibility) and `tier=tier` (log_delivery) from the single value.
- [ ] **Step 4: Run** `python -m pytest tests/test_ads_tier_targeting.py tests/test_ads_serve.py -q` → PASS; gates.
- [ ] **Step 5: Commit**: `git commit -am "feat(m5): tier-targeted placements (all-T3-in-state) in serve path"`

---

### Task 5: `shared.lookups` — campaign billing resolver + payment hook

**Files:**
- Modify: `backend/core/shared/lookups.py`, `backend/core/main.py` (wiring lands in Tasks 7/9)
- Test: `backend/core/tests/test_lookups_m5.py`

**Interfaces (the ads↔billing seam — exact shapes both sides code against):**

```python
@dataclass(frozen=True, slots=True)
class CampaignBillingRef:
    id: uuid.UUID
    business_id: uuid.UUID
    name: str
    status: str
    pricing_model: str | None
    price_paise: int | None          # None = unpriced (house/admin) - NOT billable
    subtotal_paise: int | None       # price decomposition: billing invoices need
    gst_paise: int | None            #   taxable vs GST without re-deriving (Task 9/10)
    paid_at: datetime | None

CampaignBillingResolver = Callable[[AsyncSession, uuid.UUID], Awaitable[CampaignBillingRef | None]]
# events: "paid" | "refunded"  (checkout's draft->pending_payment flip happens inside
# ads' own checkout-request path, not via this hook - see Task 9 note)
CampaignPaymentHook = Callable[[AsyncSession, uuid.UUID, str], Awaitable[None]]

def register_campaign_billing_resolver(resolver: CampaignBillingResolver) -> None
def register_campaign_payment_hook(hook: CampaignPaymentHook) -> None
async def resolve_campaign_billing(session, campaign_id) -> CampaignBillingRef | None  # unregistered -> None
async def notify_campaign_payment(session, campaign_id, event: str) -> None  # unregistered -> no-op (fail closed = money recorded, campaign stays pending; surfaced by reconcile)
```

Also extend `reset_lookup_resolvers()` to clear both (conftest autouse already calls it).

- [ ] **Step 1: Write failing tests**: fail-closed behaviour (unregistered resolver → None; unregistered hook → no exception), register/resolve round-trip with stub callables, reset clears them.
- [ ] **Step 2: Verify fail, implement** (mirror the existing registrar/resolver pattern in `lookups.py` exactly — module-level `_campaign_billing_resolver: CampaignBillingResolver | None = None` etc.).
- [ ] **Step 3: Run + gates + commit**: `git commit -am "feat(m5): shared lookups seam for ads<->billing (billing ref + payment hook)"`

---

### Task 6: Advertiser self-serve campaign API (create/quote/read/update) — IDOR NN4

**Files:**
- Create: `backend/core/modules/ads/selfserve_schemas.py`, `backend/core/modules/ads/selfserve_router.py`
- Modify: `backend/core/main.py` (mount router)
- Test: `backend/core/tests/test_ads_selfserve.py`

**Interfaces:**
- Consumes: `pricing.quote_campaign`/`RateCardError`, `GeoTargetIn` (now with tiers), `SLOT_KEYS`, `resolve_business`/`resolve_owned_businesses` (ownership), billing `_principal_user_id` pattern, `_require_flag` (ads flag, copy the 3-line helper — modules can't import each other).
- Produces (wizard + Tasks 7/9/13 consume):
  - Router `SecureRouter(prefix="/ads/my", tags=["ads-selfserve"])`, ALL routes private; every handler starts `await _require_flag(session)` (404-while-dark) then resolves the principal.
  - `POST /ads/my/quote` body `QuoteIn {slot_keys: list[str] (1..3, each in SLOT_KEYS), geo_target: GeoTargetIn, categories: list[str] (<=20, slug regex), flight_start: date, flight_end: date (start < end), serves_total: int|None}` → `QuoteOut` (mirror of `pricing.Quote`; lines as `[{label, amount_paise}]`). RateCardError → 422 `exc.code`.
  - `POST /ads/my/campaigns` body `CampaignCreateIn {business_id: uuid, name: str (1..80), quote fields..., daily_serve_cap: int|None (>=100), target_url: HttpsUrl str}` → 201 `MyCampaignOut`. Creates `Campaign(status='draft', pricing_model, price_paise=quote.total_paise, price_subtotal_paise=quote.subtotal_paise, price_gst_paise=quote.gst_paise, rate_card_version, budget_serves_total=quote.serves_total)` + one `Placement` per slot_key (weight 1, the shared geo_target incl. categories). Ownership: `resolve_business(session, business_id)` must return `owner_user_id == user_id` else **404** (not-yours == not-found).
  - `GET /ads/my/campaigns?business_id=&cursor=&limit=` → `Page[MyCampaignOut]` filtered to owned businesses only (via `resolve_owned_businesses`).
  - `GET /ads/my/campaigns/{id}` → `MyCampaignOut` (includes `display_status` — Task 7, placements, creatives with absolute media URLs, quote snapshot fields).
  - `PATCH /ads/my/campaigns/{id}` (draft only; else 409 `not_editable`): re-runs the quote when targeting/schedule/budget change and re-stores price fields.
  - Shared guard used by EVERY read/write in this router (NN4):

```python
async def _owned_campaign(session: AsyncSession, user_id: uuid.UUID,
                          campaign_id: uuid.UUID) -> Campaign:
    """IDOR guard: not-yours == not-found (404, never 403)."""
    campaign = await session.get(Campaign, campaign_id)
    if campaign is not None:
        ref = await resolve_business(session, campaign.advertiser_business_id)
        if ref is not None and ref.owner_user_id == user_id:
            return campaign
    raise HTTPException(status_code=404, detail="Not Found")
```

- [ ] **Step 1: Write failing tests** (`test_ads_selfserve.py`; copy the `d26_helpers` fixture idiom — add the file to F811 ignores; use `test_ads_serve._advertiser`-style real businesses via `modules.directory.service.create_business` with `owner_user_id` = the test principal):
  - happy path: quote → create draft (assert price_paise == quote total, status draft, placements created with geo_target incl. categories+tiers)
  - `test_create_rejects_unowned_business_404` (NN4), `test_get_foreign_campaign_404` (NN4 — owner A creates, principal B GETs → 404), `test_patch_foreign_campaign_404` (NN4), `test_list_only_own_campaigns` (NN4)
  - `test_flag_off_404s_everything` (no `_enable_ads` → all routes 404)
  - `test_patch_reprices_on_targeting_change`, `test_patch_nondraft_409`
  - `test_client_cannot_set_price` (`price_paise` in the POST body → 422 via `extra="forbid"` on `CampaignCreateIn`)
- [ ] **Step 2: Verify fail. Step 3: Implement** router + schemas (all Pydantic models `extra="forbid"`; `MyCampaignOut` built with explicit field mapping — remember the `copy`/`ad_copy` alias for embedded creatives). Mount in `main.py` `MODULE_ROUTERS` next to the other ads routers.
- [ ] **Step 4: Run** `python -m pytest tests/test_ads_selfserve.py -q` → PASS; gates (`lint-imports` — selfserve_router must import nothing from other modules).
- [ ] **Step 5: Commit**: `git commit -am "feat(m5): advertiser self-serve campaign API with owned_by guard on every route"`

---

### Task 7: Lifecycle engine + pause/resume + moderation wiring + worker sweep

**Files:**
- Create: `backend/core/modules/ads/lifecycle.py`
- Modify: `backend/core/modules/ads/selfserve_router.py` (pause/resume/checkout-request), `backend/core/modules/ads/moderation_sources.py`, `backend/core/modules/ads/worker.py`, `backend/core/modules/ads/admin_router.py` (status guard, decision 14), `backend/core/main.py` (register payment hook)
- Test: `backend/core/tests/test_ads_lifecycle.py` (+ extend `test_ads_moderation_source.py`, `test_ads_admin.py`)

**Interfaces:**
- Produces (`lifecycle.py`):

```python
PAYABLE_FROM = frozenset({"draft"})
async def request_checkout(session, campaign: Campaign) -> None
    # draft -> pending_payment; 409 LifecycleError("not_payable") otherwise; requires
    # price_paise is not None and >= 1 creative exists (LifecycleError("no_creatives"))
async def on_payment_event(session, campaign_id: uuid.UUID, event: str) -> None
    # the registered CampaignPaymentHook (Task 5). "paid": set paid_at=now,
    # pending_payment -> pending_moderation, then maybe_activate. "refunded":
    # active/paused/pending_* -> paused + structured log ads.campaign_refund_paused.
    # Unknown campaign: log ads.payment_hook_unmatched, return (money is recorded in
    # billing regardless; reconcile surfaces it).
async def maybe_activate(session, campaign: Campaign) -> bool
    # -> active iff paid_at and >=1 approved creative and 0 pending creatives
async def demote_to_moderation(session, campaign: Campaign) -> None
    # active -> pending_moderation (edit-after-approve re-entry)
def display_status(campaign: Campaign, *, today: date) -> str
    # active + flight_end < today -> "expired"; active + budget exhausted -> "exhausted"
async def sweep_lifecycle(session, *, today: date) -> int
    # durable flips of the two derived states; returns rows changed
class LifecycleError(Exception): code: str
```

- Moderation wiring (`moderation_sources.py::CreativeSource._decide`): after setting `approved`, load the campaign; if `campaign.status == "pending_moderation"`: `await lifecycle.maybe_activate(...)`; capture `PendingEvent("ads", "campaign.activated", {...})` on activation so notify can email (Task 12 routes it). On reject: no status change (campaign stays pending_moderation; advertiser edits + resubmits).
- Advertiser routes (selfserve_router): `POST /ads/my/campaigns/{id}/pause` (active→paused else 409), `POST /ads/my/campaigns/{id}/resume` (paused→`maybe_activate`-or-pending_moderation result; refuses when flight_end past → 409 `flight_over`), `POST /ads/my/campaigns/{id}/checkout-request` calls `request_checkout` (Task 9's billing route requires status pending_payment).
- Worker (`worker.py::worker_tick`): after `ensure_partitions`, open an app session and `await sweep_lifecycle(session, today=...)` + commit.
- Admin guard (decision 14) in `set_campaign_status`: `if body.status == "active" and campaign.price_paise is not None and campaign.paid_at is None: 422 payment_required`.
- `main.py`: `register_campaign_payment_hook(lifecycle.on_payment_event)`.

- [ ] **Step 1: Write failing tests** (`test_ads_lifecycle.py`): full conjunction matrix — paid+approved→active; paid+pending-creative→stays pending_moderation; approved-but-unpaid→stays pending_payment (activation-before-payment threat); refund pauses; display_status/sweep flips expired+exhausted; pause/resume transitions incl. 409s; extend `test_ads_moderation_source.py` with `test_approve_activates_paid_campaign` + `test_approve_does_not_activate_unpaid_campaign`; extend `test_ads_admin.py` with `test_admin_cannot_activate_unpaid_priced_campaign`.
- [ ] **Step 2: Verify fail. Step 3: Implement** (transitions are plain column updates + `session.flush()`; no commits inside lifecycle — callers own the tx per repo choreography).
- [ ] **Step 4: Run** lifecycle + moderation + admin + serve suites → PASS; gates.
- [ ] **Step 5: Commit**: `git commit -am "feat(m5): campaign lifecycle (payment AND moderation gate activation)"`

---

### Task 8: Self-serve creative upload + edit-triggered re-moderation

**Files:**
- Modify: `backend/core/modules/ads/selfserve_router.py`, `backend/core/modules/ads/selfserve_schemas.py`
- Test: extend `backend/core/tests/test_ads_selfserve.py`

**Interfaces:**
- Consumes: `shared.media.reencode_image` + `shared.storage.put_object` (catalog upload pattern verbatim — NEVER import PIL here, `check_media_fork` gate), `CopyBlock`/locale validation from `schemas.py`, `validate_target_url`, `lifecycle.demote_to_moderation`.
- Produces:
  - `POST /ads/my/campaigns/{id}/creatives` (201): multipart `file: UploadFile | None` + form fields `copy_json: str` (JSON of `{locale: {title, body}}`, validated through `CreativeIn`'s locale rules) + `target_url: str`. Flow: `_owned_campaign` → campaign status in `{draft, pending_payment, pending_moderation, active, paused}` else 409 → optional image: `read(MAX_IMAGE_BYTES+1)` → `reencode_image` (MediaError → 422 code) → key `f"ads/{uuid6.uuid7().hex}.jpg"` → `ensure_prefix_public_read("ads/")` once-per-process → `put_object` (StorageError → 503) → insert `Creative(moderation_status default 'pending')`.
  - `PATCH /ads/my/creatives/{creative_id}` (copy/target_url/replacement file): ANY content change sets `moderation_status='pending'` AND, when the campaign is `active`, calls `demote_to_moderation` **in the same tx** (edit-after-approve threat). Returns the creative with `moderation_status` so the UI shows re-review.
  - Media served via existing `media_public_base_url` URL building (creatives already do this in `_to_served`).
- [ ] **Step 1: Write failing tests**: upload happy path with `object_store` fixture (assert stored key prefix `ads/`, creative pending); oversize/unsupported → 422 `too_large`/`unsupported_type`; `test_edit_approved_creative_repends_and_demotes_campaign` — approve via `CreativeSource`, activate (paid fixture from Task 7 helpers), PATCH copy → creative pending + campaign `pending_moderation` + **serve no longer returns it** (drive `/ads/serve`); IDOR: PATCH someone else's creative → 404.
- [ ] **Step 2: Verify fail. Step 3: Implement. Step 4: Suites + gates.**
- [ ] **Step 5: Commit**: `git commit -am "feat(m5): self-serve creative upload + re-moderation on edit"`

---

### Task 9: Billing — migration 0034, Razorpay Payment Links, checkout route

**Files:**
- Create: `backend/core/alembic/versions/0034_billing_ad_orders.py`, `backend/core/modules/billing/ad_orders.py`
- Modify: `backend/core/modules/billing/models.py`, `backend/core/modules/billing/razorpay_client.py`, `backend/core/modules/billing/router.py`, `backend/core/main.py` (register billing resolver — see note), `backend/core/settings.py` (`razorpay_test_stub: bool = False`), `apps/web-agri/app/api/billing/[...path]/route.ts` (allowlist `ad-orders`)
- Test: `backend/core/tests/test_billing_ledger_migration.py`, `backend/core/tests/test_billing_ad_orders.py`

**Note on the resolver registration:** the campaign-billing resolver is ads-owned: add `async def campaign_billing_ref(session, campaign_id) -> CampaignBillingRef | None` to `modules/ads/service.py` (reads `Campaign`, maps fields) and register it in `main.create_app` next to the pauser.

**Interfaces:**
- Migration 0034 (`down_revision="0033"`):
  - `billing.ad_orders`: `id` uuid PK, `campaign_id` uuid NOT NULL, `business_id` uuid NOT NULL, `status` TEXT default `'created'` CHECK in (`created,paid,failed,expired,refunded`), `subtotal_paise`/`gst_paise`/`total_paise` INT NOT NULL CHECK ≥0, `currency` TEXT default `'INR'`, `quote` JSONB NOT NULL, `buyer_gstin` TEXT NULL, `razorpay_plink_id` TEXT UNIQUE NULL, `razorpay_payment_id` TEXT NULL (indexed), timestamps; partial unique `uq_billing_ad_orders_live` on `campaign_id WHERE status IN ('created','paid')`; normal CRUD grants.
  - `billing.ledger_entries`: `id` uuid PK, `entry_type` TEXT CHECK in (`ad_charge,ad_refund`), `amount_paise` INT NOT NULL, CHECK `(entry_type='ad_charge' AND amount_paise>0) OR (entry_type='ad_refund' AND amount_paise<0)`, `currency` default `'INR'`, `order_id` uuid FK→ad_orders NULL, `campaign_id` uuid NULL (indexed), `business_id` uuid NOT NULL, `razorpay_payment_id` TEXT NULL (indexed), `meta` JSONB default `{}`, `created_at` only (immutable table — no updated_at, 0013 rule). Append-only: `GRANT SELECT, INSERT` + `REVOKE UPDATE, DELETE` + trigger `billing.forbid_ledger_mutation()` RAISE EXCEPTION (0032 idiom); downgrade drops trigger then function.
  - `billing.invoices`: `ALTER COLUMN subscription_id DROP NOT NULL`; add `order_id` uuid FK→ad_orders NULL, `invoice_number` TEXT UNIQUE NULL, `taxable_paise` INT NULL, `gst_paise` INT NULL; CHECK `ck_billing_invoices_parent`: `subscription_id IS NOT NULL OR order_id IS NOT NULL`; `CREATE SEQUENCE billing.invoice_number_seq` (+ GRANT USAGE to app_rt; downgrade drops it, deletes ad-invoice rows before re-adding NOT NULL).
  - Filled THREAT/NOTES block (downgrade deletes ad-order/ledger/ad-invoice data — state that; locks: brief; rollout: dark behind billing_enabled).
- Models (`billing/models.py`): `AdOrder`, `BillingLedgerEntry`, `Invoice` gains the new nullable fields.
- Razorpay client additions (same `_request` plumbing, flag re-check intact):

```python
async def create_payment_link(self, *, amount_paise: int, description: str,
                              reference_id: str, callback_url: str,
                              notes: dict[str, str] | None = None) -> dict[str, Any]:
    if get_settings().razorpay_test_stub:
        return {
            "id": f"plink_test_{reference_id.replace('-', '')[:14]}",
            "short_url": callback_url,           # e2e: "checkout" bounces straight back
            "status": "created",
        }
    return await self._request("POST", "/v1/payment_links", json_body={
        "amount": amount_paise, "currency": "INR", "description": description,
        "reference_id": reference_id, "callback_url": callback_url,
        "callback_method": "get", "notes": notes or {},
    })

async def fetch_payment(self, payment_id: str) -> dict[str, Any]:
    if get_settings().razorpay_test_stub:
        return {"id": payment_id, "status": "captured", "amount": 0}
    return await self._request("GET", f"/v1/payments/{payment_id}")

async def fetch_payment_link(self, plink_id: str) -> dict[str, Any]:
    if get_settings().razorpay_test_stub:
        return {"id": plink_id, "status": "paid"}
    return await self._request("GET", f"/v1/payment_links/{plink_id}")
```

  (Stub `fetch_payment` amount 0 is overridden in reconcile tests via FakeRazorpay — the stub exists for e2e, where reconcile doesn't run.)
- `modules/billing/ad_orders.py`:

```python
async def create_ad_order(session, *, user_id: uuid.UUID, campaign_id: uuid.UUID,
                          buyer_gstin: str | None, client: Any,
                          settings: Settings) -> tuple[AdOrder, str]:
    """Checkout. Returns (order, checkout_url). Server-side re-quote is the ONLY price."""
    ref = await lookups.resolve_campaign_billing(session, campaign_id)
    if ref is None:
        raise HTTPException(status_code=404, detail="Not Found")
    owner = await lookups.resolve_business(session, ref.business_id)
    if owner is None or owner.owner_user_id != user_id:
        raise HTTPException(status_code=404, detail="Not Found")   # IDOR: not-yours==404
    if ref.price_paise is None:
        raise HTTPException(status_code=422, detail="not_billable")
    if ref.status != "pending_payment":
        raise HTTPException(status_code=409, detail="not_payable")
    # price fields were stored by ads at quote time; total recomputed defensively:
    # ads owns the quote; billing charges exactly the stored price snapshot.
    ...
```

  It inserts `AdOrder(status='created')` with subtotal/gst/total copied from the ref's stored campaign price decomposition (`CampaignBillingRef.subtotal_paise/gst_paise/price_paise` — billing never re-derives GST), calls `client.create_payment_link(amount_paise=total, reference_id=str(order.id), callback_url=f"{settings.console_base_url}/business/ads?paid={campaign_id}", description=f"Milk.in ads: {ref.name}"[:255], notes={"campaign_id": ..., "order_id": ...})`, stores `razorpay_plink_id`, savepoint-flushes (IntegrityError on the live-order partial unique → 409 `order_exists`). New setting `console_base_url: str = "http://localhost:3002"`.
- Route (`billing/router.py`): `POST /billing/ad-orders` body `AdOrderCreateIn {campaign_id: uuid, buyer_gstin: str|None (regex `^[0-9A-Z]{15}$` when present)}` → 201 `AdOrderOut {id, campaign_id, status, total_paise, checkout_url}`. Flag-gated by `_require_flag`, principal via `_principal_user_id`. Also `GET /billing/ad-orders?campaign_id=` (owner-filtered list, for the wizard's status poll). RazorpayError → 503 (existing convention).
- [ ] **Step 1: Write failing migration tests** (`test_billing_ledger_migration.py`): tables/columns exist; ledger UPDATE and DELETE both `ProgrammingError permission denied` as app_rt AND trigger-raise as admin role (`admin_database_url` fixture, coins-test pattern); sign CHECK rejects `ad_charge` ≤0 and `ad_refund` ≥0; invoice parent CHECK rejects both-NULL; sequence exists.
- [ ] **Step 2: Write failing service/route tests** (`test_billing_ad_orders.py`, FakeRazorpay object recording `create_payment_link` calls): happy checkout (campaign fixture: create via ads test helpers, `request_checkout` to pending_payment) asserts order row + plink id + checkout_url returned + amount == stored campaign total; IDOR 404 (foreign campaign); draft campaign → 409 `not_payable`; unpriced (house) campaign → 422 `not_billable`; double checkout → 409 `order_exists`; flag off → 404; client sends `total_paise` → 422 (`extra="forbid"`).
- [ ] **Step 3: Verify fail. Step 4: Implement** (migration → models → client → service → route → BFF allowlist `ALLOWED_FIRST_SEGMENTS.add("ad-orders")` in web-agri billing proxy → wire the ads-side resolver registration in `main.py`).
- [ ] **Step 5: Run** the two new suites + `test_billing_router.py` + `test_billing_migration.py` → PASS; gates incl. `lint-imports`.
- [ ] **Step 6: Commit**: `git commit -am "feat(m5): billing ad orders + append-only ledger + razorpay payment links"`

---

### Task 10: Webhook — payment_link.paid / expired / refund.processed (NN2)

**Files:**
- Modify: `backend/core/modules/billing/service.py`, `backend/core/modules/billing/ad_orders.py`
- Test: `backend/core/tests/test_billing_ad_webhook.py`

**Interfaces:**
- `service.HANDLED_EVENTS` += `{"payment_link.paid", "payment_link.expired", "refund.processed"}`; `process_webhook_event` routes them to:

```python
# ad_orders.py
async def apply_payment_link_paid(session, *, payload, now, settings) -> tuple[str, list[PendingEvent]]
async def apply_payment_link_expired(session, *, payload, now) -> tuple[str, list[PendingEvent]]
async def apply_refund_processed(session, *, payload, now) -> tuple[str, list[PendingEvent]]
```

- `apply_payment_link_paid`: extract `payment_link.entity` (id, reference_id) + `payment.entity` (id, amount); `SELECT ... FOR UPDATE` order by plink id → missing ⇒ `("unmatched", [])`; `order.status == "paid"` ⇒ `("ignored", [])` (order-level idempotency ON TOP of the event-level body-hash dedupe — Razorpay retries carry different bodies); **amount check**: `payment.amount != order.total_paise` ⇒ mark order `failed`, outcome `amount_mismatch`, NO ledger entry, NO activation (price-tamper/partial-pay defense). Else: order `paid` + `razorpay_payment_id`; insert `BillingLedgerEntry(entry_type='ad_charge', amount_paise=order.total_paise, order_id, campaign_id, business_id, razorpay_payment_id)`; insert `Invoice(order_id=..., amount_paise=total, taxable_paise=subtotal, gst_paise=gst, status='paid', invoice_number=next from sequence via `SELECT nextval('billing.invoice_number_seq')` formatted by `invoice_number_for(seq, on_date)`)`; `await lookups.notify_campaign_payment(session, order.campaign_id, "paid")`; return `("ok", [advertiser in_app/email event `billing.ad_payment_received` — routed in Task 12])`.
- `apply_refund_processed`: locate order by `payment.entity.id` → unmatched/ignored guards → insert `ad_refund` ledger row (`-amount` from the refund entity, capped at order total), order `refunded`, hook `"refunded"`.
- `apply_payment_link_expired`: order `created→expired` (paid orders ignore), no hook (campaign stays pending_payment; re-checkout allowed because the partial unique excludes `expired`).
- `def invoice_number_for(seq: int, on: date) -> str` — Indian FY label: `f"MILK-{fy0:02d}-{fy1:02d}-{seq:06d}"` where FY starts April 1. Pure + unit-tested.
- [ ] **Step 1: Write failing tests** (`test_billing_ad_webhook.py` — copy the `_signed` HMAC pattern from `test_billing_webhook.py` verbatim, monkeypatched secret + `get_settings.cache_clear()`):
  - `test_paid_webhook_end_to_end`: signed `payment_link.paid` → order paid, exactly one ledger row (+amount), invoice row with number `MILK-26-27-000001`, campaign fixture flipped `pending_payment→pending_moderation` (registered real hook via `main.create_app`) — asserts the ads↔billing seam live.
  - **NN2a** `test_forged_signature_rejected`: tampered signature → 400, zero orders/ledger rows touched.
  - **NN2b** `test_replayed_body_is_duplicate`: same signed bytes twice → second returns `{"status":"duplicate"}`, ledger count still 1.
  - **NN2c** `test_rewrapped_retry_is_ignored`: same plink id in a *different* signed body (new `_event_id`) → outcome recorded but order already paid ⇒ no second ledger row.
  - `test_amount_mismatch_no_ledger_no_activation` (payment.amount = total−1).
  - `test_refund_appends_negative_and_pauses` (campaign active fixture → paused).
  - `test_expired_allows_recheckout` (expire, then `create_ad_order` again succeeds).
  - `test_invoice_number_fy_boundary`: `invoice_number_for(7, date(2027, 3, 31))` → `MILK-26-27-000007`; `date(2027, 4, 1)` → `MILK-27-28-000007`.
- [ ] **Step 2: Verify fail. Step 3: Implement. Step 4: Run** new suite + full `test_billing_webhook.py` (regression: subscription events untouched) → PASS; gates.
- [ ] **Step 5: Commit**: `git commit -am "feat(m5): payment webhook -> ledger append -> campaign activation seam (forgery/replay hardened)"`

---

### Task 11: Reconciliation — ledger sums == Razorpay exactly (NN3)

**Files:**
- Modify: `backend/core/modules/billing/reconcile.py`, `backend/core/tests/test_billing_reconcile.py`

**Interfaces:**
- `reconcile.py` gains `async def reconcile_ad_orders(session, *, client, since: datetime) -> int` (mismatch count, logged per-order): for each ad_order `paid|refunded` updated since `since`: `fetch_payment(order.razorpay_payment_id)` → compare `payment["amount"]` (and refund sum via `payment["amount_refunded"]`) against `SELECT COALESCE(SUM(amount_paise),0) FROM billing.ledger_entries WHERE order_id=:id`. Any drift → count + structured log `billing.ad_reconcile_drift`. Also: orphan check — ledger rows whose `order_id` is NULL or unknown count as drift. Wire into the existing CLI path (`scripts/billing_reconcile.py` exits 1 on any drift, subscription or ad).
- [ ] **Step 1: Write failing tests**: FakeRazorpay holding a transactions dict; after simulating 3 paid orders + 1 refund through the Task-10 appliers, `reconcile_ad_orders` → 0 AND `sum(ledger) == sum(fake captured amounts) - refund` asserted exactly (NN3); tamper one fake amount → 1 mismatch; delete-a-ledger-row simulation is impossible (append-only) — instead insert an extra bogus ledger row as admin role and assert drift detected.
- [ ] **Step 2: Verify fail → implement → run → gates.**
- [ ] **Step 3: Commit**: `git commit -am "feat(m5): ad-order ledger reconciliation against razorpay"`

---

### Task 12: GST invoice PDF + email attachments + notify templates (migration 0035)

**Files:**
- Create: `backend/core/modules/billing/invoice_pdf.py`, `backend/core/alembic/versions/0035_m5_notify_templates.py`
- Modify: `backend/core/pyproject.toml` (add `fpdf2>=2.8`), `backend/core/modules/notify/drivers.py`, `backend/core/modules/notify/service.py`, `backend/core/modules/notify/consumers.py`, `backend/core/modules/billing/worker.py`, `backend/core/modules/billing/router.py` (download route), `backend/core/settings.py`
- Test: `backend/core/tests/test_billing_invoice_pdf.py` (+ edits: `test_notify_templates.py` `EXPECTED_CHANNELS`, `test_notify_consumers.py` `EVENT_ROUTES` pin, `test_billing_worker.py`)

**Interfaces:**
- New settings (billing block): `gst_seller_gstin: str = ""`, `gst_seller_name: str = "Oneuni Technologies"`, `gst_seller_address: str = ""` (comment: shown on ad invoices; empty in dev is fine).
- `invoice_pdf.py`: `def render_invoice_pdf(*, invoice_number: str, issued_on: date, seller: tuple[str, str, str], buyer_name: str, buyer_gstin: str | None, lines: list[tuple[str, int]], taxable_paise: int, gst_paise: int, total_paise: int) -> bytes` — fpdf2, A4, plain table, "SAC 998365 — Sale of internet advertising space" line, CGST/SGST split when seller+buyer GSTIN share state code else IGST 18%, amounts formatted `₹{paise/100:,.2f}` (display only — inputs stay ints). Pure function, no I/O.
- Worker sweep (`worker.py::worker_tick` after dunning): `run_invoice_pdf_sweep(session, *, now) -> tuple[int, list[PendingEvent]]` in `ad_orders.py`: paid ad invoices with `pdf_key IS NULL` (limit 20/tick) → build lines from the order's `quote` JSONB → `render_invoice_pdf` → `put_object(f"invoices/{invoice.id.hex}.pdf", pdf, "application/pdf")` (**no** public-read on this prefix) → set `pdf_key` → append `("billing.ad_invoice", {user_id/locale/email via resolve_business+resolve_contact, "vars": {"invoice_number", "total", "business_name"}, "attachment_key": key, "attachment_filename": f"{invoice_number}.pdf"})`. StorageError: skip row, retry next tick.
- Notify attachments: `EmailDriver.send` gains `attachments: Sequence[tuple[str, bytes, str]] = ()` (filename, bytes, mime); `MockEmailDriver.outbox` entries become `(to, subject, body, attachment_names: tuple[str, ...])`; `ZeptoMailDriver` adds base64 `"attachments": [{"name", "content", "mime_type"}]` when present. `dispatch()`: when `request.payload.get("attachment_key")` and email channel fires, `bytes = await storage.get_object(key)` (StorageError → mark that delivery failed → existing retry machinery).
- Advertiser download: `GET /billing/ad-invoices/{invoice_id}/pdf` (private, flag-gated, owner-checked via order.business_id → resolve_business) → `Response(pdf, media_type="application/pdf", headers={"content-disposition": f'attachment; filename="{invoice_number}.pdf"'})`; regenerates on missing `pdf_key`.
- Migration 0035: seed `notify.templates` (0021 SEED_TEMPLATES pattern, en/ta/hi):
  - `ad_invoice` (email + in_app): subject "Your Milk.in ads invoice {invoice_number}", body mentions {business_name}, {total}.
  - `campaign_activated` (email + in_app): "Your campaign {campaign_name} is live".
  - `creative_rejected` (in_app): "A creative on {campaign_name} needs changes".
- `consumers.py`: `STREAMS` += `"ads"` (first consumer of that stream — the Task 7 `campaign.activated` and existing `creative.rejected` events become deliverable); `EVENT_ROUTES` += `{"billing.ad_invoice": ("ad_invoice", frozenset({"email"})), "campaign.activated": ("campaign_activated", frozenset({"email"})), "creative.rejected": ("creative_rejected", frozenset())}`. **Ads-side payload duty**: Task 7's captured events must carry `user_id`/`locale`/`email` resolved via lookups (billing `_pending_notification` pattern) — verify and patch `moderation_sources.py`/`lifecycle.py` accordingly here.
- [ ] **Step 1: `pip install -e .[dev]`** after adding fpdf2 (host py3.12).
- [ ] **Step 2: Write failing tests**: `render_invoice_pdf` returns bytes starting `%PDF` + smoke-parse text via fpdf2 output length; FY/state-code CGST-vs-IGST branch; sweep: paid invoice without pdf_key → object stored under `invoices/`, pdf_key set, one `billing.ad_invoice` pending event with attachment_key (uses `object_store` fixture); dispatch with attachment: MockEmailDriver outbox carries the filename; StorageError → delivery failed row; download route owner-only (404 foreign); `EXPECTED_CHANNELS`/`EVENT_ROUTES` pins updated (they FAIL until edited — that's the gate working).
- [ ] **Step 3: Verify fail → implement → run** (notify + billing suites) → PASS; gates.
- [ ] **Step 4: Commit**: `git commit -am "feat(m5): gst invoice pdf, email attachments, m5 notify templates"`

---

### Task 13: Advertiser analytics (spec E)

**Files:**
- Modify: `backend/core/modules/ads/service.py` (`log_delivery` `always` flag), `backend/core/modules/ads/router.py` (pass it), `backend/core/modules/ads/selfserve_router.py` (stats route)
- Test: `backend/core/tests/test_ads_selfserve_stats.py`

**Interfaces:**
- `log_delivery(..., always: bool = False)`: `if not always` keep the sampling gate; serve passes `always=cand.campaign.price_paise is not None`.
- `GET /ads/my/campaigns/{id}/stats?days=7|30|90` (DaysQuery `Annotated[Literal[7,30,90], BeforeValidator(int)]` — D26 Pydantic trap) → `CampaignStatsOut`:

```python
class CampaignStatsOut(BaseModel):
    days: int
    serves_used: int
    serves_total: int | None
    spend_paise: int          # cpm: price*used//total (0 when total 0); flat: price once active/terminal
    impressions: int
    clicks: int
    ctr_bp: int               # clicks*10000//impressions, 0-safe
    by_day: list[DayRow]      # {day: date, impressions: int, clicks: int}
    by_pincode: list[KeyCount]   # {key: str, serves: int} from delivery_decisions
    by_category: list[KeyCount]
    sampled: bool             # False for priced campaigns (always-logged)
```

  Impressions/clicks: one raw `text()` GROUP BY day query per table over `placement_id IN (campaign's placements)` + `occurred_at >= now()-days` (admin stats pattern; ≤90 days keeps partition pruning). by_pincode/by_category: GROUP BY on `ads.delivery_decisions WHERE campaign_id=:id AND occurred_at >= ...` with NULL→`"unknown"`, each capped `LIMIT 20 ORDER BY count DESC` (bounded payload; note the cap in the DTO docstring).
- [ ] **Step 1: Failing tests**: seed a priced campaign + serves (drive `/ads/serve` with sample=0 setting to prove `always` bypasses it) + beacon rows inserted directly; assert counts, ctr_bp math, spend proportionality, by_pincode/by_category rows, IDOR 404, `sampled` flag false for priced / true for house.
- [ ] **Step 2: Verify fail → implement → run → gates.**
- [ ] **Step 3: Commit**: `git commit -am "feat(m5): advertiser campaign analytics from tracking + delivery log"`

---

### Task 14: Frontend plumbing — proxies, console registry, gate

**Files:**
- Modify: `apps/web-agri/app/api/ads/[...path]/route.ts`, `apps/web-agri/lib/console-modules.ts`, `apps/web-agri/app/business/layout.tsx`
- Test: typecheck + existing `e2e/bff-path-traversal.spec.ts` conventions (add cases in Task 17's spec)

- [ ] **Step 1: Ads proxy**: `ALLOWED_FIRST_SEGMENTS = new Set(["serve", "impressions", "clicks", "my"])`. When `path[0] === "my"`: require session (`await auth.getAccessToken()`, 401 without) and attach bearer; keep serve/beacons tokenless; keep the agri_loc pincode override ONLY for `serve`. Switch body forwarding from `req.text()` to the catalog proxy's raw-bytes pattern (`Buffer.from(await req.arrayBuffer())`, forward original `content-type`, 30 MiB cap) so multipart creative upload survives.
- [ ] **Step 2: Console entry + gate**: `ConsoleGate = "billing" | "ads"`; append `{ id: "ads", title: "Advertise", href: "/business/ads", gate: "ads" }` to `CONSOLE_MODULES`; in `layout.tsx` add `adsVisible()` probing `${API}/ads/my/campaigns?limit=1` with bearer (`response.status !== 404`, try/catch false) and filter both gates. This is the sanctioned gate-mechanism extension, not a per-module layout edit.
- [ ] **Step 3:** `pnpm -w typecheck && pnpm -w lint && pnpm check:hex` → PASS. **Step 4: Commit**: `git commit -am "feat(m5): ads console mount + authenticated self-serve proxy"`

---

### Task 15: Campaign wizard UI — steps 1–4 (objective → categories → pincodes → schedule/budget) with live quote

**Files:**
- Create: `apps/web-agri/app/business/ads/page.tsx`, `apps/web-agri/app/business/ads/ads-console-client.tsx`, `apps/web-agri/app/business/ads/campaign-wizard.tsx`, `apps/web-agri/app/business/ads/wizard-steps.tsx`

**Interfaces:**
- `page.tsx`: standard console page (metadata noindex, `auth.getServerUser()` → `redirect("/api/auth/login?next=/business/ads")`, `<main className="mx-auto max-w-3xl px-4 py-6">`, h1 "Advertise", renders `<AdsConsoleClient />`).
- `ads-console-client.tsx`: business selector (D26 idiom: `getJson("/api/directory/businesses?limit=50")` + native select with `FIELD`/`LABEL` consts), campaign list (`getJson("/api/ads/my/campaigns?business_id=...")`, cursor Load-more, hand-rolled status chips: draft/pending payment/in review/live/paused/finished/expired mapped to `bg-line`/`bg-sponsored-bg`/`bg-verified-bg`/`bg-alert-bg` pills), "New campaign" button → mounts `<CampaignWizard businessId=... onDone=refresh />`, plus per-campaign detail expand (Task 16). All fetches through `lib/api` helpers with `ApiError.detailData` mapping; inline `AlertNotice`/`OkNotice` (no toasts on web-agri).
- `campaign-wizard.tsx`: hand-rolled stepper (no ui primitive exists): `const STEPS = ["Goal", "Categories", "Areas", "Schedule & budget", "Creatives", "Review & pay"] as const;` state `step: number` + one `draft` object; header = `role="group"` pill row (analytics DaysQuery pattern) showing progress, `aria-current="step"`; Back/Next buttons `min-h-[44px] max-w-[240px]`; every step a component in `wizard-steps.tsx`. Mobile-first single column; only `sm:` breakpoints.
- Steps 1–4 (this task):
  - **Goal**: radio-style cards (hand-rolled, `role="radiogroup"`): "Banner ads" (slot picklist checkboxes of the 5 milk banner slots with plain-language labels) vs "Sponsored listing" (`milk_sponsored_listing`). Mixing prevented by construction.
  - **Categories**: "All categories" toggle vs multi-select checkbox grid of the 13 M1 slugs (labels fetched from `/api/catalog/verticals/milk/schema` option_meta like products-client does; fallback slug text).
  - **Areas**: three modes (radiogroup): "All of India" (`{}`), "Specific pincodes" (chip input: 6-digit validated, ≤50, `PincodeInput`-style numeric field + Add button + removable chips), "By town tier" (state fixed TN=33 v1 + tier checkboxes 1–5 with plain labels "Big cities (T1)" … "Villages (T5)").
  - **Schedule & budget**: two `<input type="date">` (start < end validated inline), for cpm: serves presets (10k/25k/50k/100k radio pills) + custom number ≥1000, optional daily cap number; for flat: read-only computed weeks line.
  - **Live quote rail**: debounced (400ms) `postJson("/api/ads/my/quote", …)` on any change from step 2 onward; renders itemized `lines[]`, subtotal, GST, total (`rupees()` helper `₹${(p/100).toLocaleString("en-IN")}`); RateCardError codes mapped to friendly copy; quote failure never blocks navigation until Review.
  - Draft persistence: "Next" from step 4 POSTs `/api/ads/my/campaigns` (first time) or PATCHes (edits) so creatives (Task 16) have a campaign id; server errors inline.
- [ ] **Step 1: Build it.** **Step 2:** `pnpm -w typecheck && pnpm -w lint && pnpm check:hex` → PASS. Manual smoke: `pnpm --filter @agri/web-agri dev` (:3002) with backend up + flags on, walk steps 1–4 at 375px width (devtools) — no horizontal scroll, all controls ≥44px.
- [ ] **Step 3: Commit**: `git commit -am "feat(m5): campaign wizard steps 1-4 with live server-priced quote"`

---

### Task 16: Wizard steps 5–6 + campaign management + analytics view

**Files:**
- Modify: `apps/web-agri/app/business/ads/wizard-steps.tsx`, `campaign-wizard.tsx`, `ads-console-client.tsx`

- [ ] **Step 1: Creatives step**: per-creative card — image `<input type="file" accept="image/jpeg,image/png,image/webp">` (claim-form pattern: FormData `file` + `copy_json` + `target_url`, raw fetch to `/api/ads/my/campaigns/{id}/creatives`), copy fields en (required) + ta/hi (optional, all-or-nothing per locale like the admin form), target URL (https validated client-side too), preview via local `URL.createObjectURL`, 422 code mapping (`too_large`, `unsupported_type`, locale errors). List existing creatives with moderation chips (pending/approved/rejected) and Edit (re-moderation warning copy: "Editing sends this ad for review again").
- [ ] **Step 2: Review & pay step**: read-only summary of every choice + final itemized quote (recomputed via the campaign GET — server truth, not client state) + optional GSTIN input (15-char uppercase) + "Pay ₹X securely with Razorpay" button → `postJson("/api/ads/my/campaigns/{id}/checkout-request")` then `postJson("/api/billing/ad-orders", {campaign_id, buyer_gstin})` → `window.location.assign(checkout_url)`. Below the button: "You'll be redirected to Razorpay. Your ads go live after payment and a quick review."
- [ ] **Step 3: Return-from-checkout polling**: `ads-console-client` reads `useSearchParams()` `paid` param → shows a status banner polling `GET /api/ads/my/campaigns/{id}` every 3s (max 20 tries, cancelled-guard) until status leaves `pending_payment` → "Payment received — your ads are in review" (or timeout copy pointing at the campaign list).
- [ ] **Step 4: Campaign detail panel**: status chip + display_status, Pause/Resume buttons (POST, 409 mapping), budget bar (`used/total` serves, div-bar tokens), analytics section (stats GET: StatTile grid impressions/clicks/CTR/spend + by-pincode and by-category `PincodeRows`-style lists + day table in `overflow-x-auto`, DaysQuery pill row), invoice link when available (`/api/billing/ad-invoices/{id}/pdf` via plain `<a>` — add `ad-invoices` to the billing proxy allowlist **now**), "sampled" footnote only for house campaigns.
- [ ] **Step 5:** typecheck/lint/check:hex; manual mobile smoke of steps 5–6. **Step 6: Commit**: `git commit -am "feat(m5): wizard creatives + pay + campaign management and analytics"`

---

### Task 17: E2E — create → pay(test) → approve → serves targeted-only (NN1)

**Files:**
- Create: `e2e/advertiser-selfserve.spec.ts`
- Modify: `scripts/e2e-api.mjs`

- [ ] **Step 1: Seeds/env** in `scripts/e2e-api.mjs`: add to the uvicorn env `RAZORPAY_TEST_STUB: "true"`, `RAZORPAY_WEBHOOK_SECRET: "whsec_e2e"`, `ADS_DELIVERY_LOG_SAMPLE: "1.0"`; after the existing house-ads step, flip `billing_enabled` the same way `ads_enabled` is flipped (extend `seed_house_ads.py --enable-flag` to accept `--enable-billing-flag`, or a 5-line sibling script — pick whichever keeps `refuse_in_prod` semantics; the flag flip refuses in prod, matching the existing pattern).
- [ ] **Step 2: Write the spec** (desktop project + one `@matrix`-tagged mobile wizard-walk):

```ts
// e2e/advertiser-selfserve.spec.ts — NN1: create -> pay(test) -> approve -> targeted serve
import crypto from "node:crypto";
import { expect, test } from "@playwright/test";
import { AGRI, API, apiAs, completeLoginUi, randomPhone, resetOtpThrottle,
         staffApi } from "./helpers";

const SECRET = "whsec_e2e";

function signed(body: object): { raw: string; headers: Record<string, string> } {
  const raw = JSON.stringify(body);
  const signature = crypto.createHmac("sha256", SECRET).update(raw).digest("hex");
  return { raw, headers: { "x-razorpay-signature": signature,
    "x-razorpay-event-id": `evt_e2e_${Date.now()}`, "content-type": "application/json" } };
}
```

  Flow (single `test.setTimeout(240_000)` walk, port-8000 docker container stopped per the M2 trap — `scripts/e2e-api.mjs` owns :8000):
  1. New phone → login on `${AGRI}/business/ads` → create a business (listings page helper from `vendor-dashboard.spec.ts`) with `primary_pincode: "641001"`.
  2. Wizard: banner goal (home hero slot) → category `ghee` → specific pincode `641001` → dates today..+14, 10k views → creative upload (tiny PNG fixture via `page.setInputFiles` buffer) + en copy + `https://example.com/offer` → Review shows a non-zero ₹ total → Pay click captures the `checkout_url` navigation (stub bounces back to `/business/ads?paid=...`).
  3. Read the order via `apiAs(phone)` `GET /billing/ad-orders?campaign_id=...` → grab `razorpay_plink_id` + `total_paise`; POST the signed `payment_link.paid` webhook body (plink entity id + reference_id + payment entity `{id: "pay_e2e_1", amount: total_paise}`) to `${API}/billing/webhook/razorpay` → expect `{status:"ok"}`.
  4. UI poll shows "in review"; `staffApi()` → `GET /admin/moderation/queue?type=creative` → approve the creative → campaign GET shows `active`.
  5. **Serve assertions** (request `/ads/serve` directly with query params — no cookie ambiguity): `slot=milk_home_hero&pincode=641001&category=ghee` → served ad's `target_url` contains `example.com/offer`; `pincode=600001` (same state, different pincode) → that creative absent; `pincode=641001&category=milk` → absent; no `pincode` → absent. (House ads may serve alongside — assert on OUR creative's presence/absence, not `ad === null`.)
  6. **NN2 in e2e**: re-POST the identical signed body → `{status:"duplicate"}`; POST a tampered-amount body with a **wrong** signature → 400.
  7. Advertiser stats GET shows `serves_used >= 1` and `by_pincode` containing 641001.
- [ ] **Step 3: Run**: `docker stop agri-dev-api-1; pnpm e2e -- advertiser-selfserve.spec.ts; docker start agri-dev-api-1` → PASS. Then the console regression: `pnpm e2e -- vendor-dashboard.spec.ts` (billing-dark test there asserts 404s — it now needs the flag OFF assertion adjusted **only if** e2e-api enables billing globally; if so, update that test to expect 200/JSON instead of 404 and note it in the PR).
- [ ] **Step 4: Commit**: `git commit -am "test(m5): e2e advertiser flow incl. targeted-serve negative assertions"`

---

### Task 18: Docs + dev/staging go-live notes

**Files:**
- Modify: `docs/runbooks/billing-flag-flip.md`; extend the current manual-QA guide (the file QA sections have landed in through M3/M4 — locate via `Grep "M4" docs/qa/`) with an M5 section.

- [ ] **Step 1: Runbook additions**: M5 pre-flip checklist deltas — `RAZORPAY_WEBHOOK_SECRET`/keys must be TEST keys until launch; `gst_seller_gstin/name/address` set; `console_base_url` set per env; `razorpay_test_stub` MUST be false outside e2e; billing worker must be running (invoice PDFs + dunning); reconcile CLI in cron with ad-order coverage; prod `billing_enabled` stays FALSE until the launch-day decision (owner action).
- [ ] **Step 2: QA guide**: manual walk mirroring Task 17 with real Razorpay TEST checkout (stub off, real test keys): wizard on a phone, pay with Razorpay test card, verify webhook activation, Ops approve, targeted serve, invoice email w/ PDF, refund from Razorpay dashboard → campaign paused, `/admin/ads/rate-card` publish v2 → new quotes change.
- [ ] **Step 3: Commit**: `git commit -am "docs(m5): billing go-live runbook + manual qa additions"`

---

### Task 19: Full gates, adversarial money-path review, PR

- [ ] **Step 1: Full backend suite** (single process): `cd backend/core && python -m pytest -q -m "not slow"` → 0 failures. Then storm as its own run: `python -m pytest -q -m slow` (includes the existing budget-race storm now exercising priced campaigns).
- [ ] **Step 2: Full static gates**: `mypy .` (strict), `ruff check .`, `ruff format --check .`, `lint-imports`, `python scripts/dump_public_routes.py --check` (must be clean — no new public routes), `pnpm -w typecheck && pnpm -w lint && pnpm check:hex`, `pnpm --filter @agri/web-milk test` (untouched but cheap regression).
- [ ] **Step 3: E2E full**: `docker stop agri-dev-api-1; pnpm e2e; docker start agri-dev-api-1` → all specs green.
- [ ] **Step 4: Adversarial second pass (standing money-path rule)**: dispatch superpowers:requesting-code-review / the feature-dev:code-reviewer agent over the diff of Tasks 9–12 with an explicit adversary brief: forge/replay/rewrap webhooks, race double-pay vs dedupe, negative/zero/overflow amounts, IDOR on every `/ads/my/*` + `/billing/ad-orders` + invoice download, price tampering via PATCH-after-quote, activation without payment, ledger mutation paths. Fix or explicitly accept each finding in writing.
- [ ] **Step 5: PR** (credential-fill API pattern, target `dev`, title `feat(m5): advertiser self-serve + billing`): body includes — MONEY PATH files list for line-by-line human review (`modules/billing/{ad_orders,razorpay_client,service,invoice_pdf,reconcile}.py`, `modules/ads/{pricing,lifecycle}.py`, migrations 0033/0034), the CPM=serve-credits v1 simplification, the vendor-dashboard billing-dark test change if made, PRE-FLAG-FLIP checklist link, and the reviewer instruction that prod `billing_enabled` stays FALSE.

## Self-review notes (spec coverage)

- Spec A (wizard, all 6 steps incl. media pipeline): Tasks 15–16 + 8 (upload). "Presigned" replaced by the repo's hardened multipart flow — same guarantees, documented in Global Constraints.
- Spec B (rate card f(slot,tier,category), Ops-editable, versioned, live itemized price; CPM banners / flat-weekly sponsored; no auction): Tasks 1–3, 15.
- Spec C (billing un-dark dev/staging, TEST-mode e2e order→payment→webhook→ledger→activate, failed/refund+dunning, GST PDF emailed): Tasks 9–12, 17, 18. Dunning = existing D20 machinery goes live (decision 16).
- Spec D (lifecycle, atomic budget at serve (M3 reused), pause/resume, edit→re-moderation): Tasks 1, 7, 8.
- Spec E (analytics by pincode+category from M3 delivery log + D21 tracking): Task 13.
- INTEGRATION: D26 mount (Task 14), payments only via billing (checkout route + lint-imports), ledger append-only (0034 trigger+grant), D21 queue unchanged (CreativeSource extended, approval flow identical), prod flag stays false (Task 18).
- DO-NOTs honored: no live-mode Razorpay (test keys/stub only), signature verification untouched-and-tested, no balance column (ledger + serve-credits only), activation gated on payment∧moderation (Task 7 matrix test), no auction.
- NN1→Task 17, NN2→Task 10+17, NN3→Task 11, NN4→Task 6 (+IDOR probes in 8/9/12/13).
- Type-consistency spot-checks: price decomposition flows Campaign columns (Task 1) → `CampaignBillingRef` (Task 5) → AdOrder/Invoice (Tasks 9–10) with no re-derivation; `lifecycle.on_payment_event` signature matches `CampaignPaymentHook`; `tier_matches`/`log_delivery(always=)` threaded through router in Tasks 4/13.
