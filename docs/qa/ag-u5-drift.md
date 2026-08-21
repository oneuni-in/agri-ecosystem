# AG-U5 drift check — the A5 reference vs. dev

**Written 2026-08-21, before any AG-U5 code.** AG-U5 §0 requires this document:
`agri_pages_dashboard_v1.html` (A5 FINAL v2) was code-verified *before* ID-U1
merged, so every SHIP/ADD mark in it is an assertion about a tree that has since
moved. This re-verifies each one against `dev` at `64862fa` and records the CP0
decisions that came out of it.

Where the reference and the code disagree, **the code wins and this file says so**
— the same rule that governs coin amounts (`lib/coins.ts`: "the engine and the A1
mockup disagree, and the engine wins").

---

## 1 · Two gates, both examined

### 1a · The reference is not committed

AG-U5 opens with "Reference: `docs/design-reference/agri/agri_pages_dashboard_v1.html`.
If not committed there, STOP."

It is present on disk and readable, but **untracked** — `git status --porcelain`
reports `?? docs/design-reference/agri/agri_pages_dashboard_v1.html`, alongside
`A-U4_build_prompt.md` and `A-U4b_closeout_prompt.md`. The artefact exists; the
bookkeeping does not. **Resolution: the file is committed as part of this pass's
first commit**, so the reference the proofs are compared against is fixed in
history rather than floating in a working tree.

### 1b · The pass is running before D57 — owner override, recorded

AG-U5's schedule line reads POST-D57, and its own out-of-bounds forbids "pulling
this pass pre-D57". D57 has **not** happened:

| Evidence | Reading |
|---|---|
| `git tag` → `v0.1.0 v0.2.0 v0.3.0 v1.0.0-milk` | No `v1.2.0-agri`; D57's own definition is "merge dev → main, tag v1.2.0-agri, DNS cutover" |
| `agri-acceptance-checklist.md` AG-A66 (2026-08-20) | "device pass outstanding … owner pass **before D57**" |
| AG-A69 (2026-08-20) | "flag OFF → 404 → absent (**the D57 state**, restored)" |
| AG-A62 (2026-08-20) | "source expansion … deliberately **POST-LAUNCH**" |

**Owner decision 2026-08-21: proceed anyway.** The stated reason is that a set of
pre-launch changes — this dashboard, plus admin-panel alterations to follow — are
wanted *before* launch, which reclassifies AG-U5 from post-launch polish to
pre-launch scope. The out-of-bounds clause is consciously overridden, not
overlooked. The cost being accepted: AG-U5 competes for attention with D54–D57
launch work, and its surfaces enter the launch QA sweep late.

---

## 2 · Mark-by-mark re-verification

A5's own header claims: the pieces "already ship as SEPARATE top-level routes:
`/account/inquiries`, `/saved`, `/coins`, `/notifications`", and what the file
adds is "the SHELL that unifies them". Its sidebar anchors carry
`title="/account/inquiries"`, `title="/saved"`, `title="/coins"`,
`title="/notifications"`. Checked one at a time:

| A5 mark | Status on dev | Correction |
|---|---|---|
| `/account/inquiries` **ship** | ✅ true — `app/account/inquiries/{page,inquiries-client}.tsx` | none |
| `/saved` **ship** | ✅ true — `app/saved/page.tsx` | none |
| `/coins` **ship** | ✅ true — `app/coins/{page,coins-client}.tsx` | **understated.** The reference treats P3 "coins passbook" as a surface to build. `coins-client.tsx:6` already ships "balance, ledger, referral share" against `/api/coins/{balance,history,referral-code}`. **P3 is a mount, not a build.** |
| `/notifications` **ship** | ✅ true — `app/notifications/{page,notifications-client,push-card}.tsx` | none |
| `/account` shell to extend | ❌ **`app/account/` contains only `inquiries/`** — no `page.tsx`, no `layout.tsx` | The shell is genuinely from scratch. Nothing is being extended. |
| "My crops (**Soon**)" | ❌ the data exists | See §3.3 — crops are `Profile.interests`, and have been since ID-U1 |
| Devices panel | ✅ endpoints exist — `GET /auth/devices`, `POST /auth/devices/{revoke,label}` (`session_router.py:438,513,549`); UI pattern at `apps/web-id/app/devices/devices-manager.tsx` | Copy the row design read-only, per §0. Do not fork it. |
| "Your data" / DPDP | ✅ endpoints exist — `GET /identity/dpdp/export`, `GET/POST/DELETE /identity/dpdp/erasure`, `GET /identity/dpdp/reveals` (`dpdp_router.py:58,91,103,127,147`); UI precedent at `apps/web-id/app/account/dpdp-block.tsx` | none. Legal-page references stay plain text until D56 (consent-line rule). |
| Price alerts (management view) | ✅ `GET/POST/DELETE /market/alerts` (`market_data/router.py:170,180,192`) | none. Note `alerts.py` is a **daily digest, not a threshold** — the manage list must not imply "tell me when X crosses ₹Y". |
| Coin amounts from the rules table | ✅ already solved — `apps/web-agri/lib/coins.ts` (A-U4 W2) reads `GET /coins/rules` | **The §0 instruction is stale.** It says to port `lib/coins.ts` from web-id; web-agri has had its own since A-U4. Reuse the local one. A shared package is not required and is not proposed. |
| ⭐ My reviews | ❌ **no backend exists** | See §3.2. This is the one place AG-U5 is not a frontend-only pass. |
| Advertiser analytics strip | ✅ `app/business/analytics/` exists and reads the M2/M3 beacon counters | The rolecard links to it. "Reconciliation is an assertion" stays an assertion — one counter, two readers. |
| Checklist rows start at **AG-A47** | ❌ highest existing row is **AG-A70** | **AG-U5 rows begin at AG-A71.** |
| Shell pattern is new | ❌ it is not | `lib/console-modules.ts` + `app/business/layout.tsx` is the established registry-mounts-modules contract, with its own rule: "Never edit `app/business/layout.tsx` for a new module — extend, not fork". `/account` copies this shape. |

---

## 3 · CP0 decisions

### 3.1 · URL topology — the modules MOVE under `/account/*`

**Decision (owner, 2026-08-21): move.** `/coins` → `/account/coins`, `/saved` →
`/account/saved`, `/notifications` → `/account/notifications`.
`/account/inquiries` is already correct.

This was taken against the recommendation, and the disagreement is recorded rather
than smoothed over: A5's own sidebar hrefs point at the *unmoved* paths, and
AG-U5's out-of-bounds says the shell "mounts, never rewrites". The owner's call is
a single coherent URL family, and it is being built in full rather than half-done.

**What the move obliges — the complete sweep.** A half-move is worse than either
choice, so all of this lands together:

*Redirects (permanent, and load-bearing — see below):*
- `/coins` → `/account/coins`
- `/saved` → `/account/saved`
- `/notifications` → `/account/notifications`

*Internal links:*
- `app/agri-bottom-nav.tsx:26` — Alerts tab → `/notifications`
- `app/home-sections.tsx:688` — `/notifications`
- `app/page.tsx:719` — the coins EcoPill → `/coins`
- `app/offline/page.tsx:51` — `/saved`
- `app/business/notifications/notifications-prefs-client.tsx:119` — `/notifications`
- the `?next=` login targets inside the moved pages themselves
  (`app/coins/page.tsx:34`, `app/saved/page.tsx:47`)

*Service worker:* `public/sw.js:65` — `RUNTIME_CACHEABLE` is a `Set` of literal
paths including `/saved`. A moved route silently stops being runtime-cached, and
`app/offline/page.tsx` advertises `/saved` as available offline. Both change together
or the offline promise becomes false.

*Specs:* `e2e/agri-pwa.spec.ts:83,143` assert on `/saved` by path.

**Why the redirects are permanent, not a transition courtesy.**
`backend/core/modules/notify/drivers.py:152` hardcodes the web-push payload
`{"url": "/notifications"}`. That driver is **shared by every app** — agri, milk,
organic and id — and web-id keeps its `/notifications` at the top level. So the
literal cannot simply be repointed at `/account/notifications` without breaking the
other three. Every push notification already delivered to an agri user, and every
one sent afterwards, clicks through to `/notifications`. **The redirect is the
mechanism that keeps push working and must never be removed.** This is written down
here because it is exactly the kind of constraint a later cleanup pass deletes as
dead code.

### 3.2 · My reviews — a new author-scoped endpoint is in scope

**Decision: add `GET /reviews/mine`.**

`reviews_router.py` offers `GET /reviews` (public, keyed by `target_type` +
`target_id`) and `GET /reviews/owner` (approved reviews *about* a business I own).
Neither answers "reviews I wrote", and pending ones are absent from the public list
by definition — so the reference's ⭐ panel, which wants *published + in-moderation*,
has no data source at all.

The alternative — walking every business the user ever reviewed — is not possible
without an author index, and is recorded here only to be ruled out.

The new route follows `list_owner_reviews` exactly: principal-scoped instead of
business-scoped, same cursor pagination, same `ReviewPageOut` shape, unfiltered by
status so the author sees their own pending review. No migration.

**Consequence for the spec's framing:** AG-U5 P4 is not a frontend-only pass, and
its checklist row must carry backend evidence (tests) as well as a proof pair.

### 3.3 · "My crops" — a read view over `Profile.interests`

**Decision: neither of the two options AG-U5 §0 offers.** The spec asks whether
"My crops" becomes a view over "the farm profile's crops-from-interests" or stays a
separate Soon. The code has already answered, and it answers a third thing:

> `backend/core/modules/identity/models.py:305` — *"Crops are deliberately absent -
> they stay in `Profile.interests`, one list rather than two."*

`FarmProfile` (migration `0058`) holds land area, unit, tenure, cattle, goats,
poultry, irrigation. **No crop column exists and none is intended.** So:

- The 🌾 panel renders **`Profile.interests`** as the crop list, plus a farm summary
  (land · tenure · livestock · irrigation) from `FarmProfile`.
- It is **read-only**. Editing links out to `id.agri.in/account`, where
  `describes-block.tsx` already owns this. Identity is consumed, never rebuilt.
- The Soon treatment is **dropped**. Showing "Soon" over data the farmer has already
  entered and can see on id.agri.in would read as a broken promise, not as honesty.

This also satisfies AG-U5's out-of-bounds ban on "building both" — there is one
store, on identity, and one view, here.

---

## 4 · Corrections to the AG-U5 prompt itself

Recorded so the build follows the tree rather than the prompt where they part:

1. **§3 CP2 — "AG-A47+" is wrong.** Rows start at **AG-A71** (highest existing: AG-A70).
2. **§0 — the `lib/coins.ts` port is already done.** web-agri has had its own since
   A-U4 W2. No port, no shared package.
3. **§2 P3 — "coins passbook" is a mount, not a build.** The ledger and referral row
   ship today.
4. **§2 P4 — "my reviews" needs backend.** See §3.2.
5. **§0 — the "My crops" either/or is a false choice.** See §3.3.
6. **§2 P1 — nothing is being extended.** `app/account/` has no page or layout.

---

## 5 · Open — the owner's noticed-changes list

AG-U5 §0 closes with "the owner has noticed further drift — ask for their list at
CP0 before building." Asked 2026-08-21. The answer was that further pre-launch
changes are coming **one at a time**, starting with this dashboard and continuing
into admin-panel alterations. This section stays open and is appended to as each
item arrives; CP0 is therefore satisfied for the dashboard scope and remains open
for the rest.
