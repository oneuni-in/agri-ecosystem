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
