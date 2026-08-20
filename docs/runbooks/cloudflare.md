# Cloudflare production config (WAF, bot fight, rate limits)

**Status: written at D30, NOT APPLIED.** The VPS is provisioned at D31.A and DNS
cutover is D32, so there is no origin to put these rules in front of yet. Apply
during D31 once the origin answers, and record the result there. D30's
non-negotiable 3 ("WAF + rate limits live") is therefore **not met at D30
close** — see `docs/security/milk-audit.md`.

## The rule that governs every threshold below

The application already rate-limits **60 requests / 60 seconds, per IP, per
path** (`shared/security.py:96`, `settings.py:44`). Every route on a
`SecureRouter` gets it automatically — it is inserted as the first dependency,
so there is no such thing as an unthrottled route.

**Edge limits must therefore be COARSER than the app limits, never tighter.**

If Cloudflare blocks first, the app-tier limiter stops seeing the traffic it
exists to shape: its per-path counters go quiet, the `429`s vanish from
application metrics, and the signal that tells you *which endpoint* is being
abused disappears with them. The edge is there to absorb volumetric and
distributed abuse — the kind a per-IP counter cannot see — not to do the
application's fairness work for it.

Read every threshold below as "this is the point at which we stop caring about
per-user fairness and start caring about survival".

---

## 1. Managed rules

- [ ] **Cloudflare Managed Ruleset** — on, default action.
- [ ] **OWASP Core Ruleset** — on, **paranoia level 1**, action *Managed
      Challenge* rather than Block for the first two weeks. Higher paranoia
      levels false-positive on legitimate JSON bodies; a challenge is
      recoverable, a block looks like an outage to the user.
- [ ] Review the firewall event log after 48h before raising anything.

## 2. Bot Fight Mode

- [ ] **Bot Fight Mode** — on.
- [ ] **Verified-bot allowlist** — on. Googlebot must not be challenged: the
      pincode landing pages are the entire SEO case for this launch, and a
      challenged crawler silently deindexes them. Verify with
      `Search Console → URL Inspection → Live test` after cutover.

## 3. Rate limiting rules

Ordered most-specific first.

### 3.1 `/auth/*` — the credential surface

```
expression: (http.request.uri.path matches "^/auth/")
characteristics: ip.src
period: 60s
requests: 20
action: managed_challenge
```

Tighter than elsewhere because this is where credential stuffing and OTP
enumeration land, and because a human never legitimately hits 20 auth requests
a minute. **Still coarser per-path than the app's own OTP throttle ladder**,
which is the intended order: the app's per-phone cooldowns should fire first and
be visible in metrics; this rule only catches what a single IP does across
*many* phones.

Challenge, not block: a shared NAT (a village internet café, a corporate range)
can legitimately produce bursts, and blocking would lock out everyone behind it.

### 3.2 Contact reveal — the scraping surface

```
expression: (http.request.uri.path matches "^/directory/branches/[^/]+/reveal$")
characteristics: ip.src
period: 3600s
requests: 120
action: block
timeout: 3600s
```

Block, not challenge: an authenticated user is already capped per-day server
side (`contact_reveal_daily_cap`, fail-closed). Anything reaching this rule is
churning accounts or IPs to harvest phone numbers, which is the one thing the
reveal design exists to prevent. There is no legitimate traffic shape here.

### 3.3 Public inquiry creation — audit finding §4.1

```
expression: (http.request.uri.path eq "/leads/inquiries" and http.request.method eq "POST")
characteristics: ip.src
period: 3600s
requests: 60
action: managed_challenge
```

This is the **compensating control** for `milk-audit.md` §4.1: anonymous
inquiries have no per-business cap, so a single attacker can flood one vendor's
inbox (and their notifications) at the app limiter's 60/min. Sixty per hour per
IP leaves genuine enquiry behaviour untouched — a real person sends one or two —
while making sustained flooding require real distributed infrastructure.

### 3.4 `covers()` and the public browse surface

```
expression: (http.request.uri.path matches "^/(catalog/milk/home|directory/covers)/")
characteristics: ip.src
period: 60s
requests: 300
action: managed_challenge
```

Deliberately loose — five times the app limiter. These are the pages the launch
*wants* traffic on, and a shared NAT browsing normally must never be challenged.
This exists only to stop a scraper walking every pincode in Tamil Nadu.

## 4. Country challenge

**Off at launch.** Turn it on only in response to observed abuse, not
pre-emptively.

Criteria to turn it on: sustained abusive traffic from a geography with no
plausible user base, that rules 3.1–3.4 have not absorbed, visible in the
firewall event log over at least 24h. Milk.in serves Tamil Nadu, but Indian
users travel and roam, and NRI family members legitimately browse vendor pages
for relatives — a blanket geo-challenge is a real product cost for a speculative
benefit.

## 5. Cache and origin protection

- [ ] **Always Use HTTPS** — on. WebKit will not send the `Secure` session
      cookie over http (this is the D29 finding that made iOS sign-in
      unverifiable in automation); https everywhere is what makes it work in
      production.
- [ ] **Minimum TLS 1.2**.
- [ ] Do **not** enable Cloudflare's caching for `/api/*`. Those responses carry
      per-user data; the service worker already refuses to cache them
      (`sw.js:38`) and the edge must make the same choice.
- [ ] Origin lock: once the VPS is up, restrict its firewall to Cloudflare's
      published IP ranges so the origin cannot be reached directly, bypassing
      every rule above.

## 5b. Client IP — turn this on WITH the edge, not before

Every browser request reaches the API through a Next relay, so the address the
API sees is the relay's. Per-IP rate limiting and the daily viewer pseudonym
both need the visitor's address instead, and that address is only knowable once
an edge is in front. Three settings switch it on, and they belong to the same
change as the DNS cut:

- [ ] **`TRUST_EDGE_CLIENT_IP=true`** on every web-* service. It makes the
      relays read `CF-Connecting-IP`. Leave it unset anywhere Cloudflare is not
      actually in front — without an edge, a caller can send that header
      itself and we are back to a spoofable address wearing a new name.
- [ ] **`TRUST_FORWARDED_FOR=true`** on the API.
- [ ] **`TRUSTED_PROXY_IPS`** on the API: the addresses or CIDR the relays
      connect from, e.g. the compose network `172.16.0.0/12`. The API believes
      a forwarded address only from these peers. Empty means it believes
      nobody, which is safe but collapses every visitor into one rate-limit
      bucket.

**`CF-Connecting-IP`, never `X-Forwarded-For`.** Cloudflare *appends* the real
address to a visitor-supplied `X-Forwarded-For` rather than replacing it, and
the leftmost entry — the one a naive reader takes — stays whatever the visitor
wrote. `CF-Connecting-IP` is set by Cloudflare and overwrites what arrived.
This is why the origin lock in §5 matters here too: a caller who reaches the
VPS directly bypasses the edge and supplies both headers freely.

Verify after the cut: two devices on different networks browsing the same
vendor page must produce two rows in `directory.profile_views`, not one.

## 6. After applying (D31)

- [ ] Confirm each rule fires: curl past a threshold from a throwaway IP and
      check the firewall event log names the expected rule.
- [ ] Confirm client IP resolves: `TRUSTED_PROXY_IPS` covers the relay subnet
      (§5b), or every visitor shares one bucket and profile-view counts read
      as 1/day/business.
- [ ] Confirm the app-tier `429`s still appear in application metrics for
      normal-rate abuse — if they have gone silent, an edge rule is too tight
      and is masking the signal (see the governing rule at the top).
- [ ] Confirm Googlebot is not challenged.
- [ ] Record the applied state and any threshold changes back into this file.
