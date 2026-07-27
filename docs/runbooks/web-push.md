# Web push enablement (VAPID + notify.push_enabled)

D28 shipped the push channel dark. Two independent switches must both be on
before a single push leaves the building:

1. **VAPID keys in env** — `get_push_driver()` (`modules/notify/drivers.py`)
   returns `MockPushDriver` unless BOTH `vapid_public_key` and
   `vapid_private_key` are non-empty. This is the code-level kill switch.
2. **`notify.push_enabled` DB flag** — checked per send inside `dispatch()`.
   Seeded `false` by migration 0027. This is the ops-level kill switch,
   flippable without a deploy (same pattern as `notify.email_enabled`).

Turning either off stops push immediately; in-app notifications are
unaffected either way.

## 1. Generate a keypair

`py_vapid` ships with `pywebpush`, so the backend venv already has it. Run
from `backend/core` (Windows path shown; use `.venv/bin/python` on Linux):

```bash
./.venv/Scripts/python.exe -c "
from py_vapid import Vapid02, b64urlencode
from cryptography.hazmat.primitives import serialization
v = Vapid02(); v.generate_keys()
print('VAPID_PUBLIC_KEY =', b64urlencode(v.public_key.public_bytes(
    serialization.Encoding.X962, serialization.PublicFormat.UncompressedPoint)))
print('VAPID_PRIVATE_KEY =', b64urlencode(
    v.private_key.private_numbers().private_value.to_bytes(32, 'big')))
"
```

The **public** key is the browser's `applicationServerKey` — safe to expose.
The **private** key is a real secret: `.env` / sops only, never a committed
file, never a log line.

**Rotating keys invalidates every stored subscription.** Existing endpoints
were minted against the old public key and will start failing; browsers must
re-subscribe. Only rotate on compromise, and expect
`notify.push_subscriptions` to drain via the 404/410 prune path.

## 2. Wire the env

Backend — `backend/core/.env` (gitignored):

```
VAPID_PUBLIC_KEY=<public>
VAPID_PRIVATE_KEY=<private>
VAPID_SUBJECT=mailto:no-reply@agri.in
```

Frontend — `apps/web-milk/.env.local` (gitignored). The subscribe card on
`/notifications` hides itself entirely while this is empty:

```
NEXT_PUBLIC_VAPID_PUBLIC_KEY=<same public key>
NEXT_PUBLIC_ENABLE_SW=1   # dev only; prod always registers the SW
```

`NEXT_PUBLIC_*` is inlined at BUILD time — a staging/prod deploy needs the
value present during `next build`, not just at runtime.

For staging, both backend keys belong in `secrets/staging.sops.env`
(see `secrets.md`); the public key additionally goes in the build env.

## 3. Flip the flag

```bash
docker exec agri-dev-postgres-1 psql -U app -d agri \
  -c "UPDATE public.feature_flags SET enabled = true WHERE key = 'notify.push_enabled'"
```

There is no admin API for flags today — SQL is the interface (same as
`billing_enabled`, see `billing-flag-flip.md`). The flag cache is per-process
and reset per request scope; a running API picks the change up without a
restart.

To kill push in a hurry, set it back to `false` — that is the fastest lever,
faster than redeploying without keys.

## 4. Verify

```bash
# driver selection actually flipped (prints WebPushDriver when keys are set)
cd backend/core && ./.venv/Scripts/python.exe -c "
from modules.notify.drivers import get_push_driver; print(type(get_push_driver()).__name__)"

# flag is on
docker exec agri-dev-postgres-1 psql -U app -d agri \
  -c "SELECT key, enabled FROM public.feature_flags WHERE key='notify.push_enabled'"
```

Then in a browser on `http://localhost:3000/notifications` (logged in): the
"Lead & reply alerts" card should be visible with a **Turn on** button.
Accepting the permission prompt POSTs to `/notify/push/subscriptions`; confirm
a row landed:

```bash
docker exec agri-dev-postgres-1 psql -U app -d agri \
  -c "SELECT left(endpoint, 40) || '...', ua_label, created_at FROM notify.push_subscriptions"
```

A real end-to-end send requires the browser's push service (FCM / Mozilla /
Apple) to be reachable — subscribing contacts Google from the dev machine.
Trigger one by having a vendor respond to a lead (`lead.responded`), or
dispatch directly in a shell.

### What you cannot verify headlessly

Headless Chromium reports `Notification.permission === "denied"` even after
Playwright's `grantPermissions(["notifications"])`, and it has no FCM channel,
so `pushManager.subscribe()` cannot complete. Automated checks can prove the
card un-hides, the SW registers and activates, and the driver switches to
`WebPushDriver` — but the browser→push-service handshake and an actually
delivered notification need a REAL browser profile. Do that step by hand once
per environment.

## Guard rails already in place

- **SSRF allowlist** (`modules/notify/push_endpoints.py`): subscription
  endpoints must be https on a known push host, enforced on write AND again
  before every send. Do not relax this to "make a test device work" — add the
  host to the allowlist instead.
- **Tests always use the mock.** `tests/conftest.py` blanks the VAPID env vars
  so provisioning local keys can't turn the suite into live FCM traffic.
- **Preference-gated**: `push` is a toggleable channel, opt-out per user via
  `PUT /notify/preferences`. The per-user hourly cap (30) applies as usual.
- **Endpoints are never logged** — same class as `deliveries.destination`.

## Known gaps

- The notify worker still has the D12 bus-redelivery gap (a once-failed event
  is neither redelivered nor DLQ'd). Delivery-level retry/backoff DOES apply
  to push, so a transient FCM failure retries; a lost bus event does not.
- iOS only supports web push from an INSTALLED PWA (16.4+). The card shows an
  "install first" hint there rather than a broken button.
