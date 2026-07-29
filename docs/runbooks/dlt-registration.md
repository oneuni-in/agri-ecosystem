# DLT registration + msg91 cutover (real SMS)

**Status at D30 (2026-07-28): NOT STARTED.** This is the critical path to launch.

TRAI requires every commercial SMS sender in India to register on a DLT
(Distributed Ledger Technology) platform before a single message is delivered.
Approval is a third-party queue measured in **days to weeks** — nothing in this
repository can shorten it, and no amount of code review substitutes for it.

Because of that, D30 recorded the launch decision the spec's fallback clause
calls for: **launch D32 with signup gated**, and lift the gate when approval
lands. See "Lifting the gate" below.

---

## Why signup is gated rather than left on the mock driver

`get_sms_driver()` (`modules/identity/otp_drivers.py:100`) returns `MockDriver`
whenever `sms_provider != "msg91"`. The mock driver writes the code to an
in-process outbox and returns success. An app running it in production would
accept signups, tell every user "we sent you a code", and send nothing.

Two layers prevent that (`modules/identity/signup_gate.py`):

1. `signup_enabled` — a DB flag, the control you lift when approval lands.
2. **An invariant:** `app_env == "prod"` and `sms_provider == "mock"` refuses,
   regardless of the flag. This is deliberately not overridable, because the
   failure it prevents is silent — nobody notices until users complain that
   codes never arrive.

---

## Step 1 — register on DLT (owner, blocking, do this first)

Registration happens on a telecom operator's DLT portal (Jio, Airtel, VI and
BSNL all front the same system; msg91 can sponsor the process).

- [ ] **Principal Entity registration.** Business identity documents — GST or
      incorporation certificate, PAN, an authorised signatory. You receive a
      Principal Entity ID (PEID).
- [ ] **Header (sender ID) registration.** 6 alphanumeric characters, e.g.
      `AGRIID`. Transactional headers must relate recognisably to the brand;
      unrelated strings get rejected and you queue again.
- [ ] **Content template registration — one per purpose.** This codebase sends
      three distinct purposes and each needs its own approved template, because
      `MSG91Driver._template_id()` raises if the slot for the purpose in play is
      empty:

      | Purpose (`OtpPurpose`) | Setting slot | Used for |
      |---|---|---|
      | `login` | `msg91_template_login` | signup + login OTP |
      | `verify_email` | `msg91_template_verify_email` | email verification |
      | `sensitive_action` | `msg91_template_sensitive_action` | step-up auth |

      Register each as **Transactional/Service Implicit** (OTP is not
      promotional — promotional routing is DND-filtered and slower). Each
      template needs exactly one variable for the code, and the registered text
      must match what is sent **character for character**, including the sender
      name and any trailing brand line. A template that differs by punctuation
      is rejected at delivery time, not at registration time.

Suggested `login` template text:

```
{#var#} is your Milk.in verification code. Do not share it with anyone.
```

- [ ] Record the approved template IDs. They are opaque strings, not the text.

## Step 2 — provision the secrets

Four values, none of which belong in git. Follow `docs/runbooks/secrets.md`
(SOPS + age; `secrets/staging.env.example` is the shape).

```
SMS_PROVIDER=msg91
MSG91_AUTH_KEY=<from the msg91 console>
MSG91_SENDER_ID=<the approved 6-char header>
MSG91_TEMPLATE_LOGIN=<approved template id>
MSG91_TEMPLATE_VERIFY_EMAIL=<approved template id>
MSG91_TEMPLATE_SENSITIVE_ACTION=<approved template id>
MSG91_WEBHOOK_SECRET=<random 32+ bytes, used for the delivery webhook HMAC>
```

The driver posts to `https://control.msg91.com/api/v5/flow/` with the auth key
in an `authkey` header and a body of `template_id`, `sender`, `mobiles` (E.164
minus the `+`) and `otp`.

## Step 3 — the public-route edit that comes with the switch

Setting `SMS_PROVIDER=msg91` makes `main.create_app()` mount the delivery-status
webhook at **`/auth/otp/webhook/msg91`** (`main.py:196`). It is a public route:
msg91 cannot log in, so its only auth is an HMAC-SHA256 signature over the raw
body, checked in-handler against `MSG91_WEBHOOK_SECRET`.

- [ ] Add `/auth/otp/webhook/msg91` to `backend/core/public_routes.txt` **in the
      same change** that flips the provider. The `public-routes` CI job diffs
      that file against the live router registry and will fail otherwise — by
      design, so a reviewer sees the new public exposure rather than it
      appearing silently.

## Step 4 — verify a real send end to end (D31)

Do this on staging before production, with a real handset.

- [ ] `SMS_PROVIDER=msg91` with all six values set.
- [ ] Request a login OTP for a real number you hold.
- [ ] Confirm the SMS **arrives**, and that its text matches the registered
      template exactly — the sender header, the code, the trailing line.
- [ ] Confirm the code verifies and a session is issued.
- [ ] Confirm the delivery webhook fires and returns 200 (a wrong or missing
      `MSG91_WEBHOOK_SECRET` answers 401).
- [ ] Check `otp_send_cost_inr_total{provider="msg91"}` moved on `/metrics`.
      Budget ₹0.25 per SMS (`MSG91_COST_PER_SMS_INR`).
- [ ] Never log the body: delivery reports carry phone numbers.

## Step 5 — lifting the gate

Only after Step 4 passes on production credentials:

```sql
UPDATE public.feature_flags SET enabled = true WHERE key = 'signup_enabled';
```

Takes effect within `FLAG_CACHE_TTL_SECONDS` (30s), no deploy needed. The
prod-on-mock invariant means this is inert while `SMS_PROVIDER` is still
`mock` — which is the point: flipping the flag early cannot expose broken
signup.

- [ ] Confirm `/auth/otp/request` returns 200 rather than
      `503 signup_unavailable`.
- [ ] Confirm the web-id login page shows the phone form, not the
      "Login coming shortly" notice.

## Rolling back

Set `enabled = false` on the same flag. Signup closes within 30s and the notice
returns. Users already holding sessions are unaffected — the gate is on OTP
issuance, not on session validation.

---

## If approval has not landed by D32

The launch proceeds with signup gated. What still works without an account:
the pincode landing pages, the directory, vendor profiles, search, and the
category pages — the entire indexed SEO surface. What does not: signup, login,
posting a need, contact reveal, reviews, and the vendor console.

That trade was accepted deliberately at D30 rather than discovered at D32.
