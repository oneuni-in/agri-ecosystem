# Billing flag flip (billing_enabled) — pre-flight checklist

The `billing_enabled` DB flag turns the entire /billing surface on without a
deploy (request-time 404s while off). Do NOT flip it in prod before every box
below is checked. Source: PR #29 notes (D20) + D26 additions.

## From D20 (PR #29)
- [ ] Webhook rate-limit carve-out or 429 alerting (shared per-IP 60/min
      bucket vs Razorpay egress IPs).
- [ ] Checkout-initiation UI shipped (Pricing v1 — POST /billing/subscriptions
      + hosted short_url exist backend-only today).
- [ ] Razorpay creds + plan ids present in env.
- [ ] Reconcile fetch-failure counting + invoice-loop bounding reviewed.

## Added by D26 (premium tier)
- [ ] Billing → directory tier sync exists: an ACTIVE subscription must set
      `directory.businesses.subscription_tier = 'premium'` and a
      cancel/terminal-dunning transition must set it back to `'free'`
      (event consumer or explicit ops step). Until that ships, activation is
      manual: `POST /admin/directory/businesses/{id}/tier` (role-gated,
      audited as `directory.tier_set`).
- [ ] Vendors with recorded intent (`businesses.premium_requested_at IS NOT
      NULL`) get activated (and charged only per their consent flow) at
      launch — the "activate at launch" promise made by the premium console
      page.
- [ ] Note: billing tiers are `growth|pro`; the directory field is
      `free|premium`. The sync must define the mapping (any live paid tier →
      premium).

## Added by M5 (advertiser self-serve ads + ad-order billing)

M5 layers ad-order checkout (Razorpay Payment Links, one-off charges) on top
of the D20 subscription plumbing above. Same `billing_enabled` flag, same
webhook route (`POST /billing/webhook/razorpay`) — the flag flip below is a
superset of the D20 checklist, not a separate switch. `ads_enabled` (also a
DB `FeatureFlag`, `/admin/ops/flags`) is independent: it gates ad *serving*
and creative moderation, not money. A campaign can only reach `active` with
BOTH payment (`ad_orders`/ledger) AND creative moderation cleared
(`modules/ads/lifecycle.py`) — flipping `billing_enabled` alone does not
make ads serve, and flipping `ads_enabled` alone does not let anyone pay.

- [ ] **Razorpay credentials** — `RAZORPAY_KEY_ID` / `RAZORPAY_KEY_SECRET` /
      `RAZORPAY_WEBHOOK_SECRET` (settings: `razorpay_key_id`,
      `razorpay_key_secret`, `razorpay_webhook_secret`) are set to **TEST**
      mode keys. Do not put live keys in any env before the launch-day
      decision — that swap is an owner action, not something this checklist
      pre-authorizes.
- [ ] **`razorpay_test_stub` is `false`** outside e2e. It short-circuits
      `create_payment_link`/`fetch_payment`/`fetch_payment_link` to canned
      responses *before* any network call or the `billing_enabled` gate
      (`modules/billing/razorpay_client.py`). It is inert by design when
      `app_env == "prod"` (`_stub_active()` hard-ANDs against that) — a
      misconfigured prod env with the stub flag left set still makes real
      Razorpay calls, never fake ones — but staging/dev must still have it
      unset (`false`) for any test-mode walkthrough to exercise the real
      Razorpay flow (see the M5 QA section in
      `docs/qa/manual-test-d23-d29.md`).
- [ ] **`gst_rate_bp`** set to the correct GST rate in basis points (default
      `1800` = 18%) — applied on top of every ad-order subtotal
      (`modules/ads/pricing.py`).
- [ ] **`gst_seller_gstin` / `gst_seller_name` / `gst_seller_address`** set
      to the real seller particulars before the first real advertiser is
      invoiced. `gst_seller_gstin` and `gst_seller_address` default to empty
      strings; `gst_seller_name` defaults to `"Oneuni Technologies"`. A
      blank/short seller GSTIN makes `invoice_pdf._same_state()` fall back
      to treating the buyer as same-state (CGST+SGST split, never IGST) —
      that is an accepted v1 simplification for unregistered B2C buyers, not
      something to rely on for a configured seller. Invoices render "-" for
      a blank GSTIN/address either way; get these filled in before go-live
      so real invoices carry real seller details.
- [ ] **`console_base_url`** set per environment (dev default
      `http://localhost:3002`) — it seeds the Payment Link's `callback_url`
      (`{console_base_url}/business/ads?paid={campaign_id}`), the page the
      advertiser bounces back to after hosted checkout.
- [ ] **Billing worker running** (`python -m modules.billing.worker`,
      `billing_worker_enabled` true). It is not just dunning: every tick
      also runs the GST invoice PDF sweep
      (`modules.billing.ad_orders.run_invoice_pdf_sweep`) that renders and
      stores the PDF + queues the `billing.ad_invoice` notify email for
      every paid ad order. If the worker is down, advertisers pay, the
      webhook activates the campaign, but no invoice PDF/email ever goes
      out until it comes back up.
- [ ] **`scripts/billing_reconcile.py` scheduled** (nightly cron, from
      `backend/core`: `python -m scripts.billing_reconcile [--days N]`,
      default `--days 3`). It now covers ad-order ledger drift
      (`reconcile_ad_orders`) alongside the existing subscription/invoice
      check — one run, one exit code. It exits non-zero (pages the
      scheduler) on either a genuine drift *or* a Razorpay fetch failure
      during the check (`billing.reconcile_fetch_failed` /
      `billing.ad_reconcile_*` logs); it exits `0` immediately while
      `billing_enabled` is off (dark launch = zero live calls, including
      from cron).
- [ ] **`ads_enabled` and `billing_enabled` are independent flags** — both
      live in `shared.flags` / `/admin/ops/flags`, both seed `false`.
      Turning ads on without billing on means campaigns can be built and
      moderated but never checked out; turning billing on without ads on
      means orders/webhooks work but nothing serves. Decide the order
      deliberately for each environment.
- [ ] **Prod `billing_enabled` stays `FALSE`** until the launch-day decision
      (owner action) — same as the D20 rule above; M5 does not change who
      makes that call.
- [ ] **Razorpay dashboard config** (test mode until launch-day):
      - Webhook endpoint → `POST {api_origin}/billing/webhook/razorpay`,
        subscribed to `payment_link.paid`, `payment_link.expired`,
        `refund.processed` (M5) **plus** the existing subscription events
        this route already handles: `subscription.charged`,
        `subscription.pending`, `subscription.halted`,
        `subscription.cancelled`, `subscription.completed`, `invoice.paid`,
        `invoice.expired` (`modules/billing/service.py`'s `HANDLED_EVENTS`).
        Anything not in that set is accepted and ignored (`"ignored"`
        outcome), never a 4xx — but subscribing to fewer than the full list
        silently drops real state transitions.
      - Payment Links must **NOT** enable partial payments. `create_ad_order`
        never sets `accept_partial`, and `apply_payment_link_paid`'s
        amount check is a strict `amount_paise != order.total_paise`
        equality (see the `THREAT (price tamper/partial pay)` comment in
        `modules/billing/ad_orders.py`) — a partially-paid link would fail
        closed as `amount_mismatch` (order marked `failed`, no ledger entry,
        no activation) instead of reconciling a partial charge. Do not turn
        partial payments on without revisiting that check first.
