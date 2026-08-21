# AG-U5 visual log — /account against the A5 reference

Every delta between what `apps/web-agri` renders and what
`docs/design-reference/agri/agri_pages_dashboard_v1.html` draws, one row per
difference, each marked **fix** (changed to match), **keep** (deliberate, with
the reason) or **flag** (owner's call).

Reference chrome — the dark A5 bar, the ROLE switcher, the `ship`/`add` tags in
the sidebar — is not product UI and is never a delta.

Proof pairs live in `docs/design-reference/agri/proofs/`.

---

## P1 · the shell

Proofs: `ag-u5-p1-shell-1280.png` · `ag-u5-p1-reference-1280.png` ·
`ag-u5-p1-shell-390.png` · `ag-u5-p1-reference-390.png`.

Captured live against `localhost:3002` (**not :3000** — AG-U5's header says
`:3000`, but `apps/web-agri/package.json` has run `next dev --port 3002` since
D26; the prompt is wrong and the port is right). Signed in as `AG-00000AA`,
a farmer account with no name, no pincode and no crops set — so several panels
render their honest empty form rather than the reference's populated one.

Self-check before comparing: **no horizontal overflow at 390, 768 or 1280**
(`documentElement.scrollWidth` 390/753/1264 against viewports 390/768/1280);
**no console errors** — the single console line is a pre-existing
`icon.svg` manifest warning that predates this pass and reproduces on the home;
reduced-motion rules present and unbroken.

| # | Delta | Verdict |
|---|---|---|
| P1-1 | **The identity card was hidden below `sm:`.** First build put the me-card behind `hidden sm:flex`, so a phone showed the nav pills and nothing about who was signed in. The reference puts the card at the head of the mobile scroll row. | **fix** — the card is `flex-none` and rides as the first pill at every width. A phone is exactly where "which account is this?" is hardest to answer. Both 390 proofs are post-fix. |
| P1-2 | **The overview rendered a `<div>`, not a `<main>`.** Every sibling — inquiries, saved, coins, notifications — opens with `<main>`; the new page did not, so the shell had no main landmark. | **fix** — `<main className="pb-4">`. One `<main>` per page and none in the layout, so mounting a module never nests two. |
| P1-3 | **Sidebar carries a "YOUR ACCOUNT" heading; the reference starts straight at the identity card.** | **keep** — `ConsoleShell` requires `heading`, and it doubles as the nav landmark's accessible name. It is `hidden sm:block`, so the mobile row matches the reference exactly; only desktop gains a label. Forking ConsoleShell to drop one line of text would cost the shared-catalog guarantee that /account and /business look like one system. |
| P1-4 | **No count badges** beside My enquiries (2) and Price alerts (4). | **keep for P1, lands in P2** — the counts are live data, and P2's stats row is where that read belongs. A badge is not a style detail, it is a number, and inventing one is the failure this repo names most often. |
| P1-5 | **Bottom-nav tab reads "Profile"; the reference says "Account".** | **flag** — "Account" is the better word now that the tab opens a dashboard rather than a profile. The label is `ui.nav.profile` in the **shared** catalogue, so changing it silently re-labels web-milk and web-organic too. Needs either an agri-only key or a deliberate cross-app rename; not a decision to slip into a shell commit. |
| P1-6 | **Topbar has "← Back to agri.in" but not the reference's "🎙️ Post a need" money button.** | **keep for P1** — the button belongs with the enquiries panel it feeds, which is P2. Shipping it into an otherwise empty overview would make the one populated thing on the page a CTA. |
| P1-7 | **Sub-line reads `district · pincode`; the reference adds "member since Mar 2026" and "Farmer account".** | **keep / deferred** — `ProfileOut` carries no created-at, so "member since" cannot be rendered without inventing it. "Farmer account" is a role label and role states are P6. |
| P1-8 | **Eyebrow reads "YOUR AGRI.IN DASHBOARD"; the reference says "ONE AGRIID · MODULES RENDER BY ROLE".** | **keep** — the reference string explains the design to a reviewer. It is reference chrome wearing product clothes. |
| P1-9 | **`/account/coins` keeps its "Home › AgriCoins" breadcrumb** inside a shell that already has a sidebar. | **flag** — harmless but redundant now. Removing it means editing a mounted module, which AG-U5's out-of-bounds forbids; worth doing in the pass that next owns that page. |
| P1-10 | **The coins "Earn AgriCoins" cards read +20 / +250 / +15 where the reference prints +5 / +25.** | **keep — the reference is wrong** and already known to be. `lib/coins.ts` records it: the mockup's figures are illustrative copy, `coins.rules` is the data, and the engine wins. Rendering the mockup's numbers would advertise a reward nobody is paid. |
| P1-11 | **Earn-card text wraps tighter than before the move** — the module lost ~192px to the sidebar at 1280. | **flag** — no overflow and nothing clipped, but the four cards are visibly cramped. It is a real consequence of mounting a full-width page into a shell, and it will apply to every module P2–P5 mounts. Worth a width pass once all of them are in, rather than tuning one page now. |
| P1-12 | **Footer "Contact us" points at `/account/notifications`.** | **flag — pre-existing, and it predates this pass**: `site-footer.tsx` linked "Contact us" to `/notifications` before AG-U5 touched anything. The move retargeted the href so it does not 308, and preserved the oddity rather than silently redefining what the footer's contact link means. A contact link that opens your own notification feed is wrong either way. |

### Verified behaviours, not deltas

- All five mounted routes return **200** for a signed-in user: `/account`,
  `/account/inquiries`, `/account/coins`, `/account/saved`,
  `/account/notifications`.
- All three old paths return **308** to their new homes (checked with `curl`
  and again in-page as `opaqueredirect`).
- The sidebar's active state is real — AgriCoins highlights on
  `/account/coins`, Overview on `/account` — and so is the bottom bar's, which
  was hardcoded to Home on every route before this pass.
- `Profile & language` leaves the app: `http://localhost:3003/account`
  (`ID_PUBLIC_ORIGIN`), rendered as a plain anchor rather than a `next/link`.
- `/account/alerts` and `/account/reviews` are in the sidebar and **404 by
  design** until P2 and P4 build them.

---

## P2 · the overview

Proofs: `ag-u5-p2-overview-1280.png` · `ag-u5-p2-overview-390.png`, against the
same `ag-u5-p1-reference-*.png` reference captures.

State driven for the capture: two mandi-digest subscriptions (636810, 641001),
three saved items, 105 coins, no enquiries and no crops — so the panels show a
mix of populated and honest-empty rather than one or the other.

Self-check: no horizontal overflow at 390 or 1280 (`scrollWidth` 390 / 1264);
console clean apart from the same pre-existing `icon.svg` manifest warning.

| # | Delta | Verdict |
|---|---|---|
| P2-1 | **The price-alerts panel does not look like the reference, because the reference draws a feature that does not exist.** A5 shows "Tomato · Coimbatore market · alert when above ₹30/kg", "Turmeric · Erode market · any change ≥ ₹5" and a "Severe weather · Coimbatore district" row — per-commodity thresholds and a weather channel. `market.PriceAlert` is keyed `(user_id, pincode)` and carries only `pincode` and `last_notified_on`. No commodity column, no threshold, no kind. | **keep — the code is right and the reference is aspirational.** `market_data/alerts.py` argues the design explicitly: the source publishes once a day, so a threshold alert is still a once-a-day message that goes *silent* on the days nothing crossed — indistinguishable, to the person waiting, from the pull having failed. Each row therefore says what a subscription is: one pincode, one digest a day. Rendering A5's design would advertise a threshold nobody can set. |
| P2-2 | **Turning an alert off was a one-way door.** Not a visual delta — a bug this panel exposed. `unsubscribe` soft-deletes, but `uq_price_alerts_user_pincode` is a plain unique on `(user_id, pincode)` that does not exclude deleted rows, and `subscribe`'s idempotency probe cannot see soft-deleted rows. So re-subscribing to a pincode you had ever turned off **500'd, permanently** — including from the home's mandi card. Unreachable before AG-U5 because no UI could unsubscribe. | **fix — in the backend.** `subscribe` now revives the soft-deleted row (`include_deleted=True`, the documented opt-out), clears `last_notified_on` so the new subscription is not born already-latched, and still counts the revival against the per-user cap. Three tests, one of which was confirmed to fail without the fix. |
| P2-3 | **Counts can read "20+" where the reference prints a bare number.** | **keep** — none of these endpoints returns a total; they are cursor-paginated. A full page means "at least this many". The reference was drawn against mock data where the total was known. |
| P2-4 | **No "🎙️ Post a need" button, which the reference puts beside "Back to agri.in".** | **keep, and worth the owner knowing why: agri has nowhere to post one.** `post-need/` and `my-needs/` exist only in `apps/web-milk`; web-agri has neither route. The needs that *do* show in the enquiries panel are real and are this person's — one AgriID across the family — they were just posted on milk.in. A button leading nowhere is worse than no button; building post-need for agri is its own pass. |
| P2-5 | **The right column is crops + saved; the reference puts the AgriCoins passbook there.** | **keep** — the passbook already ships in full at `/account/coins` (P3 mounts it, drift doc §2). Duplicating a ledger into the overview would give two readers of one balance and an eventual disagreement. |
| P2-6 | **"Last sent 2026-08-21" renders the raw ISO date.** | **flag** — correct but not localised, and it will read oddly in ta/hi. A date formatter is a shared concern (several surfaces print dates) rather than something to inline here. |
| P2-7 | **Stats sub-captions describe the category even at zero** — "SAVED ITEMS 0 / guides, articles and videos". | **keep** — the caption says what the tile counts, which is still true of an empty one, and it is how the reference's captions read. |

---

## P3 · the coins passbook

Proofs: `ag-u5-p3-coins-1280.png` · `ag-u5-p3-coins-390.png`.

**P3 was a mount, not a build** (drift doc §2): `/coins` already shipped balance,
ledger and referral share at A-U4 W2. It moved to `/account/coins` in P1 and is
verified here rather than rewritten — the out-of-bounds rule is that the shell
mounts modules and never rewrites them.

Verified live: no overflow at 390 or 1280; the earn amounts are read from
`GET /coins/rules` at render (`referral_referrer=250`, `referral_referee=100`,
`daily_visit_streak=15`, `review_approved=20`) and match what the page prints;
the ledger renders real entries; the referral code loads.

| # | Delta | Verdict |
|---|---|---|
| P3-1 | **The share is a bare CODE; the reference shows a link, `agri.in/r/murugesan`.** No `/r/[code]` route exists on web-agri, and the WhatsApp share sends the code as text. | **flag — and it is the more serious half of a bigger gap. See below.** |
| P3-2 | **Earn amounts read +20 / +250 where the reference prints +5 / +25.** | **keep — the reference is wrong**, as `lib/coins.ts` already records. The rules table is the data. |
| P3-3 | **"Attend a webinar" renders a Soon badge with no amount.** | **keep** — no `webinar_attend` rule exists, so there is no amount to print. A card promising coins nothing can award would advertise a reward nobody can earn. |

### The referral chain has no entry point — owner decision needed

Following P3-1 down: **the referral feature is complete in the backend and
unreachable from any UI.**

- `POST /auth/login` accepts `referral_code` (`session_router.py:111`), puts it
  on the `user.registered` event, and `coins/worker.py` calls
  `referrals.attribute` — which creates the `Referral` row, and `maybe_reward`
  pays both sides on the referee's `profile_100`.
- **No frontend passes `referral_code`. Anywhere.** Grepped across all five
  apps and `packages/auth-client`: the field is never set.

So today a farmer copies their code, shares it on WhatsApp, their friend signs
up — and **nothing is attributed, because no signup surface accepts a code**.
The coins page truthfully says "you both earn when they verify their number";
the mechanism that would make it true is not connected.

`agri.in/r/<code>` is exactly the missing piece — the link carries the code so
the referee never types it. **It was not built in this pass, deliberately:**

1. It spans **web-id**. The code has to survive the hop to `id.agri.in/login`
   and be included in that page's login POST. AG-U5 is scoped to
   `apps/web-agri`, and web-id's login is the surface D30's two-layer signup
   gate hardened — not somewhere to make an unreviewed change days before
   launch.
2. Building `/r/[code]` on agri alone would produce a link that **looks** like
   it attributes a referral and does not. That is worse than today's honest
   bare code, not better.

Recommendation: treat this as its own small cross-app task (agri `/r/[code]` →
web-id login carries the code → attribution assertion), sized and reviewed on
its own. Flagged rather than silently shipped half-done.
