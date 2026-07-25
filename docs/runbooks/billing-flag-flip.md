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
