# ID-U1 visual log — live vs `id_auth_v1.html` (A7)

One section per page, written while the page was still open, per the build
prompt's §1 loop. Every section lists three kinds of delta:

- **fixed** — the live page was wrong; corrected and re-snapshotted.
- **kept** — the live page differs and is *better* (real data, a real
  constraint the mockup did not have, or a claim the code does not support).
  Each carries its one-line justification.
- **flagged** — unresolved, or a change to something the reference marks
  SHIPPED. These are checkpoint questions, not silent decisions.

Proof pairs live in `docs/design-reference/id/proofs/` as
`<page>_{live|ref}_{1280|390}.png`. They are captured by driving real Chrome
(Playwright) against `http://localhost:3003` and the reference file at the
same two viewports, 2× DPR, full page.

Reproduce: with `pnpm --filter @agri/web-id dev` running and the dev API up,
run the harness with a shot list of `{name, path, refState}`. The Next
dev-mode indicator is hidden at capture time — it is tooling chrome that does
not exist in a production build and must not appear in a binding proof.

---

## P1 · `/login` — phone step

Proofs: `p1-phone`, `p1-phone-referral`, `p1-privacy` (× live/ref × 1280/390).
The reference's phone state always shows the referral banner, so the
`p1-phone-referral` pair is the like-for-like comparison; `p1-phone` is the
no-`?ref=` case the mockup never draws.

Self-check: no horizontal overflow at 390 / 768 / 1280
(`scrollWidth === clientWidth` at all three), console clean on all three
routes, reduced-motion unaffected (this step animates nothing).

### fixed

| # | What was wrong | Fix |
|---|---|---|
| P1-F1 | The trust strip wrapped 3+1 at 1280 where the reference runs it on one line. The cause was structural: `<main>` was capped at `max-w-[420px]`, so a strip meant to span the page was being asked to fit the card column. | `<main>` widened to `max-w-[540px]` + `items-center`; the two elements that must stay card-width (the step rail and the `Card`) now pin `max-w-[420px]` themselves. Four className edits, no re-indentation — the step machine is untouched. |
| P1-F2 | An empty brand-gradient band sat above the login card, and every page logged two console 401s. The layout mounted the notification bell for signed-out visitors: the widget handles the 401 correctly (it hides), but the *browser* still logs the failed request, and the strip rendered as an empty band with nothing in it. The reference has no such chrome. | The bell strip is now gated server-side on the presence of the `agri_sid` cookie — the widget cannot check this itself, since the cookie is httpOnly. Zero requests and zero chrome when signed out. This is the AG-A1 defect class (clean guest console) that milk.in and agri.in have each already paid for. |

### kept

| # | Delta | Why the live page is right |
|---|---|---|
| P1-K1 | The reference's DPDP sentence says "we store your number **encrypted**". The live sentence does not. | It is not true. `identity.users.phone` is a plain `Text` column — there is no column encryption. A false privacy claim on the consent line of a DPDP launch-gate surface is not a copy nit. The live sentence says only what the code does: stored to sign you in, used only for that and the alerts you ask for, never public, never sold, never revealed without consent. **Encrypting the column at rest is a real backlog item raised by this pass.** |
| P1-K2 | The reference banner names the inviter ("Murugesan invited you") with an avatar initial. The live banner is unnamed, with a 🎁 glyph. | Resolving `?ref=CODE` → a handle before sign-in means publishing a code→handle oracle on a public route; referral codes are 8 characters from a 32-character alphabet. Owner decision: the name arrives on the **done screen** (P5) instead, once there is a session to gate it behind. |
| P1-K3 | The reference says "finish signing up and you get +100 AgriCoins; he gets +250 **when you verify**". The live copy says the coins land when you complete your profile. | The reference has the timing wrong. `modules/coins/referrals.py` delays **both** rewards to the referee's `profile_100` event, never at signup — that delay is the deliberate anti-farm design. The mockup's copy would promise a payment no code path makes. |
| P1-K4 | Banner colours: reference `#E8F7EE` / `#BFE7CE` / `#0F6E42` → live `bg-brand-soft` / `border-line` / `text-brand-deep`. | The A-U1 one-off-colour policy: reference colours outside the sanctioned token set map onto existing tokens rather than entering new ones. `theme-agri`'s brand-green family is within a hair of the reference values and is semantically the right family for an AgriID surface. `check:hex` green. |
| P1-K5 | Both amounts (100 / 250) are read at render time from `GET /coins/rules`; the banner does not render at all if either is missing. | The prompt forbids hardcoded coin amounts, and A-U1 already paid for the opposite mistake. A banner whose entire job is naming a reward is better absent than approximate — there is deliberately no fallback number. |

### flagged — for CP1

| # | Observation | Why I did not change it |
|---|---|---|
| P1-Q1 | **Brand lockup shape.** The reference is a horizontal lockup (mark + "AgriID" + a small-caps "one login · …" line) with a row of three site pills below it. Live is a vertical stack: mark, "One AgriID for everything", then the sites as one text line. | Both the markup and its strings are SHIPPED and unmarked in the reference. Changing it is a design decision, not a delta to silently close. |
| P1-Q2 | **Locale switcher treatment.** The reference draws three pill buttons ("English / தமிழ் / हिन्दी") with the active one filled. Live is the `EN · த · हि` text-button row. | SHIPPED (AG-A63) and unmarked, and the live treatment is deliberate — `locale-switcher.tsx` documents why the accessible names are the glyphs (a second button named "English" would collide with the language step in Playwright strict mode). |
| P1-Q3 | **Step rail.** The reference shows fixed 26px bars plus a "Step 1 of 4" text label. Live renders four full-width `flex-1` bars with an `aria-label` and no visible text. | The reference marks the rail SHIPPED. But it draws a visible label the live page does not have, which is a real (if small) legibility difference — worth your call rather than my assumption. |
| P1-Q4 | `ui.auth.terms` is now unused in all three catalogs. | The trust strip took its place below the card and its DPDP link moved into the card. I left the string in place rather than deleting it, so restoring the old line is a one-line revert if you disagree with dropping it. |

### new this page

`/privacy` (`apps/web-id/app/privacy/page.tsx`) — the destination for the
consent line's link, tri-lingual, public and indexable (the only route in this
app that is). It has no counterpart in the reference, so its proofs are
live-only. Content is deliberately narrow: what we store, what we never do,
what you control, your DPDP rights, and why sign-in is rate-limited — the last
of which preserves the one fact the dropped `terms` line carried.
