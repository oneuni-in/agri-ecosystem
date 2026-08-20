# ★ D57 — Agri.in launch runbook

**Tag:** `v1.2.0-agri` · **Owner-only.** Promotion to `main` and the DNS cut
are the owner's, not an agent's.

Launch day is **promote + smoke + monitor**. Anything that "just needs one
more day" is a post-launch issue, not a launch task — that rule is what keeps
this page short.

---

## 0 · Go / no-go, decided BEFORE the tag

Every row is a hard gate. A red row is a no-go, not a discussion.

| Gate | State entering D57 | Where to check |
|---|---|---|
| a11y 100 on every route | OK — 9/9 | `pnpm perf:sweep` |
| SEO 100 on every indexable route | OK — 9/9 | `pnpm perf:sweep` |
| Perf >= 0.90 every route | **OPEN — owner decision** | §1 |
| Offline works | OK — 4/4 browser tests | `npx playwright test agri-pwa` |
| Coins ledger correct under concurrency | OK — cap exact, no drift | `pytest -m slow` |
| Zero Critical/High | OK — 1 Low found + fixed | §2 |
| Restore drill timed | OK — **RTO 7s** | §3 |
| Sarkari links <= 7 days | OK — 6/6, stamped 2026-08-15 | `node scripts/check-sarkari-links.mjs` |
| AI signed off or OFF | OK — **OFF** (owner, 2026-08-17) | `docs/security/agri-ai-redteam.md` |
| Every non-live vertical honestly Soon | OK | registry `soon` flags |
| Prod secrets present | **OWNER ACTION** | §4 |

---

## 1 · The one open gate: perf

`/` measures 0.71-0.75 locally against a 0.90 floor. **Do not read that as
0.71 in production.** The same machine scores `/categories` at 0.83 where CI
scores it **0.96** — a ~0.12 instrument offset on a known-green page, so
local numbers are relative, not certifications.

**What has to happen before the tag:** read the perf numbers from a CI run on
this branch, not from a laptop. If CI shows `/` below 0.90 there, that is a
real no-go, and `docs/qa/agri-perf-a1.md` §7 lists the remaining levers (the
rupee-sign to `latin-ext` font pull is the largest unattempted one, ~37.9 KB).

Decision 3 gives agri no carve-out. If the number cannot be met, the launch
moves — the threshold does not.

---

## 2 · Security posture at launch

- **AI assistant: OFF.** `agri_ai = false`. The red-team suite is structural
  (55 attacks against the real request path) but **no live model run has ever
  happened** — there is no API key. Do not flip this on launch day. The
  before-you-flip checklist is `docs/security/agri-ai-redteam.md` §6, and its
  item 2 (English-only refusal patterns against a TA/HI product) is the one
  that could actually hurt someone.
- **Audit findings this pass:** one Low, fixed — the assistant's turn cap
  counted rows by a client-supplied conversation id without scoping to the
  user. Zero Critical, zero High.
- **Money path:** one real bug found and fixed — concurrent awards bypassed
  numeric caps entirely (a `weekly_cap=5` admitted all 40). Now serialized per
  user; 40 concurrent gives exactly 5. The ledger stays append-only by trigger.

---

## 3 · Backup and rollback

**Restore drill #3, executed 2026-08-18:**

```
restore:   5s (drop+create+decrypt+pg_restore)
verify:    2s (102 tables, 61528 rows, all counts match)
total RTO: 7s
```

Run it yourself before the tag. It is two commands, and it is the only number
on this page that matters at 3am:

```bash
bash scripts/backup/backup.sh          # fresh encrypted dump
bash scripts/restore.sh                # restores to a SCRATCH db, diffs counts
```

**Rollback is the previous tag, not a fix-forward.** If the smoke test in §6
fails, re-promote the prior image tag and investigate afterwards. A launch
that is limping is worse than a launch postponed by an hour.

---

## 4 · Owner actions that block launch

None of these can be done by an agent, and none has a workaround:

1. **`AUTH_SESSION_SECRET`** in the production environment. Without it every
   authed page 500s — `/coins`, `/saved`, `/account/*`. Public pages are
   unaffected, which is exactly why this is easy to miss until someone logs in.
2. **`NEXT_PUBLIC_VAPID_PUBLIC_KEY` at BUILD time** if push should work on day
   one. It is inlined, not read at runtime, so setting it after the build does
   nothing. Without it the push card renders nothing — honest, but no
   notifications.
3. **DNS cut + TLS** for agri.in, and the rollback rehearsal that goes with it.
4. **Decide the burn side of coins.** `redeem()` exists with no route and no
   catalog, so coins currently only accumulate. That is a shippable state, but
   it should be a decision rather than an oversight.
5. **Rotate `app_rt`, and fill the application secrets.** Migration 0013
   creates the runtime database role with the password `app_rt`, which is
   published in this repository; every secret in the new "application secrets"
   block of `secrets/staging.env.example` (`OTP_PEPPER`, the two beacon
   secrets, the MinIO keys) likewise ships with a working dev default. On the
   database, once per environment:

   ```sql
   ALTER ROLE app_rt PASSWORD '<the value that goes in DATABASE_URL>';
   ```

   `shared/startup_checks.py` refuses to boot with `APP_ENV=prod` while any of
   them is still the published value, and the error names every offending
   variable at once — so this is now self-enforcing rather than a step someone
   has to remember. It is listed here because a failed boot at launch is a
   worse way to discover it than a checklist. Note `OTP_PEPPER` invalidates
   in-flight OTPs when it changes: set it before traffic, not during.

---

## 4b · Build from a CLEAN cache, or you ship stale prices

Found in the live-Chrome walkthrough on 2026-08-18, on a production build.

`/mandi` rendered **3 commodities dated 2026-08-15** while
`GET /market/commodities` returned **6, all as_of 2026-08-17**. Deleting
`apps/web-agri/.next/cache/fetch-cache` and restarting produced all six at the
correct date immediately.

The mechanism, and why it is a deploy concern rather than a code bug:

- `/mandi` and `/mandi/[commodity]` declare `export const revalidate = 3600`,
  so they are ISR — **prerendered at build time**.
- `next build` resolves their fetches through `.next/cache/fetch-cache`. If
  that cache carries old entries, the build **bakes stale data into the
  prerendered HTML**.
- ISR then serves that stale page for a full hour before regenerating.

So a build that reuses a warm `.next/cache` can ship a mandi page that is days
old and missing more than half its commodities, and nothing about the build
output or the running app says so. Prices are the point of this page; a farmer
comparing a two-day-old rate against today's is worse served than one shown
nothing.

**Before the launch build:**

```
rm -rf apps/web-agri/.next/cache        # or build in a clean container
pnpm --filter @agri/web-agri build
curl -s localhost:3002/mandi | grep -o '2026-[0-9-]*' | sort -u   # sanity-check the date
```

CI builds in a fresh runner and is not exposed to this. A local or
cache-reusing deploy is.

## 5 · Launch sequence

```
1. Confirm §0. Any red row -> stop.
2. Read CI perf numbers for this branch (§1). Below 0.90 -> stop.
3. bash scripts/backup/backup.sh        # a dump from BEFORE the change
4. Owner merges dev -> main, tags v1.2.0-agri
5. Deploy. Watch the first 200s and 500s, not dashboard averages.
6. Smoke, in order (§6)
7. Monitor for 2h (§7)
```

## 6 · Smoke test — by hand, in a real browser

Not a script. A script asserts what it was told to; a person notices what is
wrong.

| # | Check | Pass looks like |
|---|---|---|
| 1 | `/` in EN, TA, HI | mandi prices, weather, real numbers on the earn cards |
| 2 | `/` at 360px | no horizontal scroll, bottom nav clear of content |
| 3 | Search "seeds" | agri results, plus the milk.in rail underneath |
| 4 | `/helplines`, tap a number | the phone dialer opens |
| 5 | Airplane mode, reload `/helplines` | numbers still there |
| 6 | Airplane mode, go to `/directory` | offline shell, links to what IS cached |
| 7 | Log in, `/coins` | a balance and a referral code render |
| 8 | `/ask` | honest "not switched on yet" — **NOT** a chat box |
| 9 | Any scheme card | opens the official `.gov.in` portal |
| 10 | View source on `/` | JSON-LD present, canonical is `agri.in` |

**If #8 shows a chat box, stop the launch.** It means `agri_ai` is on, and
nothing has ever red-teamed the live model.

## 7 · First two hours

Watch, in this order:

1. **5xx rate** — anything sustained above zero is a rollback conversation.
2. **`/health/deep`** — the DB and Redis half of it, not just the 200.
3. **p95 on `/`** — the page W0 spent a whole work package on.
4. **Sentry** — new issue TYPES, not issue counts.
5. **A real phone on mobile data**, not office wifi. The product is for people
   on 3G at a mandi gate, and that is the only way to see what they see.

## 8 · Known-and-accepted at launch

State these to anyone who asks, rather than discovering them under pressure:

- The AI assistant is off, and the entry surface says so.
- Coins accumulate; there is nothing to spend them on yet.
- Federated search covers agri + milk. Organic has no index — that site does
  not exist yet (D63-74).
- The knowledge corpus is 15 approved items. Thin, and honest about it.
- **AG-A27 (video) has ZERO rows.** The code path and its tests are green; no
  curator has published a video. Owner-deferred, not silently green.
- Three helpline numbers still carry their 2026-08-14 verification date and
  want an owner dial-check.
