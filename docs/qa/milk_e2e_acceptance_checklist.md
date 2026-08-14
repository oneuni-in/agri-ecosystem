# Milk.in — e2e acceptance checklist

**What this is.** A human-run, browser-based acceptance pass over everything merged
through U3. Signing it is the trigger for Razorpay KYC filing and M6; it is not a
substitute for CI, which has already proved the automated contracts.

**How to run it.** In a real browser, against a production build, as a real person would.
Not a session's job. Work top to bottom, mark each row PASS / FAIL / N-A, and **log
failures without fixing them as you go** — fixes land as one batch pass afterwards, then
the whole list is re-run. Fixing mid-run means you never know which state you signed.

**Environments.** Production build, host API, billing in Razorpay **test mode**. Signup
mode per the D30 DLT record. Reset ad frequency caps between repeated page loads —
`ads_freq_cap_per_day = 3` per placement per viewer, and one dev machine is one viewer.

**Accounts needed before starting:** a guest (incognito), a consumer, two vendors A and B
in different pincodes, an advertiser, a staff account, an admin.

Legend: **[BLOCKER]** = cannot sign with this failing. Everything else is logged and
triaged.

---

## A · Consumer home (U1 — 25 sections)

| # | Check | Result |
|---|---|---|
| A1 | Home loads at `/` with no console errors, at 360 / 768 / 1024 / 1440 | U4 fix landed — ready for re-run (guest 401 probes removed; polish-u1.md §9.2) |
| A2 | All 25 numbered sections render; none is an empty box | |
| A3 | Utility strip: hotline chip renders when configured, absent when not — never an empty golden box | |
| A4 | Header: EN and TA taglines do not overlap; no 3-line wrap at 360px | |
| A5 | Guest header shows Login in place of coins pill + bell + avatar | |
| A6 | §3 hero serves an approved creative; arrows and Ad tag visible; single creative = no dots, no dead space | |
| A7 | **[BLOCKER]** A pending creative never serves on any home slot | |
| A8 | §4 pincode box accepts 6 digits and routes; GPS pill resolves | |
| A9 | Typing a new pincode updates BOTH the header pill and page content — they cannot disagree | |
| A10 | §5 category bar shows live schema values incl. `khoa`; never wraps at any width 320–1920 | |
| A11 | Pinned filters (Home delivery / Organic) absent from the DOM below 1024, not merely hidden | U4 fix landed — ready for re-run (conditional markup, not `max-lg:hidden`; polish-u1.md §9.1) |
| A12 | §5b price ticker shows real ₹ bands for the current pincode; pauses on hover | |
| A13 | §5d partner banner collapses cleanly when the slot is empty | |
| A14 | §8 vendor grid: sponsored card first, golden border, `★ Sponsored` label, organic order unchanged | |
| A15 | **[BLOCKER]** Never more than 2 sponsored positions on the page | |
| A16 | Recommended shows organic-only — no paid signal can enter it | |
| A17 | §8d reviews strip shows 3 distinct businesses, never the same one repeated | |
| A18 | §8b stats: every cell has an honest source; a cell reading 0 is hidden, not shown as 0 | |
| A19 | §2b need strip appears for a signed-in user with an open need; absent for a guest | |
| A20 | Fulfil the need → strip disappears on reload | |
| A21 | §10a price-alert card: dismiss stays dismissed; blocked-notification browsers never see it | U4 fix landed — ready for re-run (30-day `milk_price_alert` cookie; polish-u1.md §9.3) |
| A22 | §10b install band: iOS shows the Add-to-Home hint, never a dead Install button | |
| A23 | §10c FAQ renders and emits FAQPage JSON-LD | |
| A24 | §12 bottom nav clears the footer; safe-area respected on a notched device | |
| A25 | Switch to `/ta` then `/hi`: zero English chrome remains (DB-driven names excepted) | |
| A26 | Reduced-motion setting stops the ticker, reveals, count-ups and shimmer | |

## B · Consumer surfaces (U1b — 7 surfaces)

| # | Check | Result |
|---|---|---|
| B1 | `/{city}/{pincode}` results render; sponsored caps and positions match the home's | |
| B2 | Search returns listings for a schema-only value (`khoa`) | |
| B3 | **[BLOCKER]** Search uses the same engine path as results — not a fork (verify sponsored caps hold) | |
| B4 | Brand page with zero covering shops in the pincode: section hidden, not empty | |
| B5 | Category page lights up from a schema value with no code change | |
| B6 | Post-need → appears on my-needs AND on the §2b home strip | |
| B7 | Sitewide footer is the 5-col grid on every consumer route — no 720px remnant survives | |
| B8 | All seven surfaces in TA and HI with no English chrome | |
| B9 | No horizontal scroll on any surface, 320–1920 | |

## C · Vendor console (U2)

| # | Check | Result |
|---|---|---|
| C1 | Signed-out hitting a console route lands on login and RETURNS to the intended route | |
| C2 | A consumer-role session cannot render console navigation | |
| C3 | **[BLOCKER]** IDOR sweep: as vendor B, attempt vendor A's rows — read, edit, delete, list. **404 on every one, never 403, never 200** | |
| C4 | Profile edit → the public business page reflects it | |
| C5 | Listing price edit → the consumer results card changes | |
| C6 | Listing removed → soft-deleted, gone from public results, still recoverable | |
| C7 | Media upload renders publicly; a rejected file type is refused server-side, not just in the UI | |
| C8 | Coverage pincode added → the business appears in that pincode's blend | |
| C9 | Respond to a need → the consumer sees it on my-needs | |
| C10 | Review reply lands `pending` and is invisible publicly until approved | |
| C11 | Console form labels, validation messages and destructive confirms all translate | |

## D · Advertiser + money path (M5)

| # | Check | Result |
|---|---|---|
| D1 | Self-serve wizard completes end to end on a phone-sized viewport | |
| D2 | Rate card shown is the current version; a superseded version is never charged | |
| D3 | Razorpay test-mode checkout completes; webhook signature verified | |
| D4 | **[BLOCKER]** Ledger is append-only — no admin or vendor action can alter a posted row | |
| D5 | GST invoice generates with correct figures and is downloadable | |
| D6 | Reconciliation view matches the Razorpay dashboard for the test transactions | |
| D7 | House ads (NULL `price_paise`) serve without charging anything | |
| D8 | Campaign spend stops at budget; caps enforced per placement per viewer | |
| D9 | **[BLOCKER]** Creative uploaded by advertiser A cannot be attached to advertiser B's campaign | |

## E · Admin console (U3)

| # | Check | Result |
|---|---|---|
| E1 | **[BLOCKER]** Permission sweep: every admin action attempted as guest / consumer / vendor / staff — rejected **at the API**, not merely hidden in the UI | |
| E2 | Suspend a business → it vanishes from consumer results | |
| E3 | **[BLOCKER]** That suspension wrote an audit row naming the actor, the entity and the reason | |
| E4 | Reinstate → returns; both transitions visible in the audit timeline | |
| E5 | **[BLOCKER]** No UI or endpoint can edit, delete or purge an audit row — at any role | |
| E6 | Audit timeline filters by actor / action / entity / date and paginates | |
| E7 | Moderate a review → public approved-only reads change accordingly | |
| E8 | Approve a creative → it becomes servable | |
| E9 | Reports queue: handle a report end to end | |
| E10 | Pincode tiers T1–T5 read from M4's computation, not a literal | |
| E11 | Directory browse lists pincodes, vendors, shops, places from live data | |
| E12 | Payments ledger displays only — no admin action alters any row | |
| E13 | Ad performance counters move when beacons fire (reset caps between loads) | |
| E14 | An empty queue reads as success, not as an error state | |

## F · Cross-cutting

| # | Check | Result |
|---|---|---|
| F1 | **[BLOCKER]** Production build with `AUTH_SESSION_SECRET` unset degrades to guest — never 500 | |
| F2 | IdP unreachable → the consumer home still renders; no browser error page | |
| F3 | Logout on one vertical logs out everywhere (one AgriID) | |
| F4 | Coins balance is identical across every surface that shows it | |
| F5 | **[BLOCKER]** A test business carrying an agri category surfaces correctly and does NOT appear in milk results — the business/category model behaves as designed | |
| F6 | Disable an account → access is gone within one request cycle, no cache flush | |
| F7 | Lighthouse on `/`: at or above the Issue #59 floor. a11y ≥ 0.95, SEO ≥ 0.95 | |
| F8 | Lighthouse on U1b + console + admin routes: perf ≥ 0.90 | |
| F9 | Offline: the PWA serves its offline page; no white screen | |
| F10 | Data-saver toggle behaves and persists | |

---

## Sign-off

Signing this triggers **Razorpay KYC filing** and **M6** (portability proof, delta
adversarial audit, k6 with ads serving, full regression, freeze).

- [ ] Every **[BLOCKER]** row passes
- [ ] Non-blocker failures are logged with issue numbers and triaged
- [ ] Issue #59 status recorded — floor restored, or carve-out still active with its date
- [ ] The D30 DLT/SMS decision is confirmed as still governing signup mode

Run by: ______________  Date: __________  Build / commit: ______________

Result: ☐ SIGNED   ☐ NOT SIGNED — re-run required
