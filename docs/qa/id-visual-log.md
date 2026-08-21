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

---

## P2 · `/login` — OTP step (verify-only)

Proofs: `p2-otp-fresh`, `p2-otp-wrong`, `p2-otp-locked` (× live/ref × 1280/390).
The reference has no distinct wrong-code drawing, so `p2-otp-wrong`'s ref half
is the same `otp` state — the comparison there is against the shipped copy,
not a mockup.

**Every state was reached through the real API**, never by posing the UI:

- *fresh* — a real `POST /auth/otp/request` on an unused number; the resend
  button shows the real 30 s first-rung cooldown from `otp_limits`.
- *wrong code* — six wrong digits, which `OtpInput` auto-submits; the server
  returned the real 400 and the UI showed "That code didn't work — try again".
- *locked (429)* — the phone's real daily-issue counter
  (`otp:day:phone:<e164>` in Redis) was set to its cap of 5, then a genuine
  request tripped the genuine throttle. The 429 is the server's, not a posed
  state. This deliberately costs **no** IP quota: `assert_issue_allowed`
  raises on the phone cap *before* it bumps the IP counter.

Self-check: no overflow at 390/768/1280; console clean on load. The
wrong-code step logs one browser-level 400 — that is the browser reporting an
expected non-2xx from a deliberate wrong entry, not a page defect.

### findings — the diff was NOT none

| # | Finding | Severity |
|---|---|---|
| **P2-Q1** | **The 429 copy tells the farmer to do the thing that is blocked.** Live renders "Too many attempts. **Request a new code.**" — but requesting a new code is precisely what the throttle just refused, so following the instruction fails again and burns another attempt. The reference's copy is the correct shape: "hit the OTP limit for now. Wait **14 minutes** — the code you already received still works until it expires." | **highest of this pass so far.** Misleading advice on a rate-limited credential screen. |
| **P2-Q2** | **The wait time is available and unused.** `OtpRateLimited` carries `retry_after` and `router.py` already sends it as a `Retry-After` header. The client never sees it: `lib/api.ts`'s `parse()` builds `ApiError` from the JSON body only and discards headers. Surfacing it is a small, contained change (read the header into `ApiError`, add a "wait {n} minutes" string). | Small fix, real gain — it is what makes P2-Q1's copy fixable. |
| **P2-Q3** | **The rate-limit message has no error treatment.** It renders as `text-sm text-sub`, the same weight and colour as the DPDP sentence beneath it, so a block reads as a footnote. The reference gives it a bordered danger box. | Visual, but on the one state where the user must notice. |
| **P2-Q4** | **No "change number" affordance.** The reference's OTP sub-line carries "· change number". Live has none: a farmer who mistyped a digit can only reload the page. The reference marks this step SHIPPED, so this is an ADD hiding inside a SHIP mark rather than a regression. | Real usability gap; small to add. |

I did **not** fix any of these. The prompt scopes P2 to verify-only and says a
surfaced delta is a finding — widening it into a build task is my call to
propose, not to take. P2-Q1 + P2-Q2 are one small change together and I'd
recommend doing them before launch; they are on the D57 flow.

### kept

| # | Delta | Why the live page is right |
|---|---|---|
| P2-K1 | Resend is a full-width ghost **button** live; the reference draws a text row ("Didn't get it?" · "Resend in 0:23"). | The button is a real 48 px target on the screen where a farmer on a bad SMS route taps most. The reference's text link is below the tap-target floor the rest of this app holds itself to. |
| P2-K2 | Live shows the cooldown as "Resend in 30s"; the reference shows "0:23" mm:ss. | Cosmetic; the live figure is the true remaining value from the same ladder. Recorded only so the pair does not look unexplained. |

---

## P3 · `/login` — handle step

Proofs: `p3-handle-{fresh,checking,available,taken,invalid,reserved}`
(× live/ref × 1280/390). The reference draws one handle card listing all its
states together, so each live state's ref half is that same card.

**Every state came from the real `/auth/handle/check`**, which is a private
endpoint — so each capture run performs a real signup (OTP requested, code
read from the mock driver's log line) to have a session at all. Verified
server verdicts:

| State | Typed | Server said | Rendered |
|---|---|---|---|
| reserved | `aavin` | `reserved` | "@aavin is reserved" |
| taken | `annai` | `taken` | "@annai is taken — try one of these:" |
| invalid_format | `ab@xy` | `invalid_format` | "4–20 characters: a–z, 0–9 and _" |
| ok | `green_field_1280` | `ok` | "@green_field_1280 is available" |
| checking | — | (in flight) | "Checking…" |

`reserved` says *reserved* and nothing else — no reason, no neighbouring
entries, no hint at the list's contents. The blocklist is a brand-squatting
defence and enumerating it would defeat it.

Self-check: 390 captures are exactly 780 px wide at 2× DPR — no horizontal
overflow. Console clean.

### built

Rules line beside the label (`4–20 · a–z 0–9 _`), read *before* typing rather
than earned by breaking them · the `@` rendered inside the field · all five
states each pinned to a server code and coloured by outcome · the
one-change-ever warning with its reason, placed at **pick time**.

The warning's placement is the substantive choice. `set_handle` flips
`agri_id_changed_once`, so **this pick *is* the one change** — telling a
farmer about it later, on `/account`, would be describing a door that already
shut. (This is also why the A7 profile card's "you haven't used yours" is
wrong for anyone who picked at signup; see P7.)

### fixed

| # | What was wrong | Fix |
|---|---|---|
| P3-F1 | My first cut put the `@` in a sibling box beside the input. The design system's focus ring (`:focus-visible`, 3 px accent, marked "never remove") belongs to the *input*, so on focus it painted straight over the `@` and cut the glyph in half. Caught in the first snapshot. | The `@` moved *inside* the field as an absolutely-positioned, `pointer-events-none` prefix with the input padded past it — which is exactly how the reference builds `.handlewrap`. Ring intact, glyph intact. |
| P3-F2 | Suggestion chips rendered under an **available** handle, contradicting the line right above them: the farmer was told the name was theirs and then offered three alternatives to it. | Chips hide on `available`. They belong to a rejection — the taken message ends "try one of these:" and these are the these. |

### flagged — for CP1

| # | Observation | Why I did not change it |
|---|---|---|
| P3-Q1 | **`checkHandle` fires one request per keystroke.** There is no debounce, so typing a 12-character handle issues ~9 authenticated checks. Harmless at dev volume, wasteful at launch, and it is what makes the "checking" flicker visible at all. | Debouncing means restructuring the shipped check, which the prompt scopes out of this pass. Small, self-contained fast-follow. |
| P3-Q2 | **Handle subtitle is thinner than the reference's.** A7 explains that the handle is what appears on reviews and questions, shows the referral link shape `agri.in/r/<handle>`, and says the phone number stays private. Live says only "Your public name across the family of apps". | Shipped copy, unmarked. The reference's version is better and I'd take it, but replacing shipped strings is your call. |
| P3-Q3 | **`already_changed` renders the invalid-format copy.** `saveHandle` maps any non-matching detail to `invalidFormat`, so a 409 `already_changed` would tell the user their handle has bad characters. Unreachable at signup (the first pick is always allowed) — but reachable from `/account`'s Change button. | Belongs to P7, where the Change path is actually built; noted so it is not discovered twice. |

---

## P4 · `/login` — language step (verify-only)

Proofs: `p4-language` (× live/ref × 1280/390). Reached by a real signup and
then skipping the handle pick. Self-check: 780 px at 2× DPR (no overflow),
console clean, rail correctly shows all four steps complete.

Zero app changes, as scoped. Three findings:

| # | Finding | Note |
|---|---|---|
| **P4-Q1** | **The subtitle is missing.** The reference says "Everything — pages, alerts, the morning mandi summary — arrives in this language. **Change it any time.**" Live shows the heading and the tiles alone. Both halves of that sentence do work: the first says what the choice actually controls (not just this screen), and the second removes the fear of getting it wrong — which is exactly the fear a one-tap-commits screen creates. | The single most worthwhile addition on this step. |
| **P4-Q2** | **No selected state, and no confirm.** Live commits the moment a tile is tapped, so no tile ever renders as chosen and there is no Finish button; the reference shows a highlighted tile plus a separate "Finish →". One tap is fewer taps, and I would keep that — but combined with P4-Q1's absence, a farmer who taps Hindi by accident gets no signal about what just happened or that it is reversible. | Keep one-tap; the reassurance belongs in copy, not an extra button. |
| P4-Q3 | Tiles render the shared `CategoryTile` (emoji + tint square + name + vernacular); the reference draws letter glyphs (`த` / `A` / `हि`). | Component-level, shipped, and consistent with the rest of the family. Recorded, not a defect. |

---

## P5 · done screen (new state)

Proofs: `p5-done` (× live/ref × 1280/390). Captured from a **real** signup
driven end to end — OTP requested, code read from the mock driver, handle
picked, Tamil chosen — arriving at `?ref=5KJN7H2R`, a real referral code
belonging to `@dummy`. The inviter line on the proof is a live resolution
through the new endpoint, not a posed string.

Self-check: 780 px at 2× DPR (no overflow), console clean.

### behaviour verified, not just drawn

A screenshot cannot show any of this, so each was driven and asserted:

| Guarantee | Evidence |
|---|---|
| Reduced motion leaves the burst complete | `opacity: 1`, `transform: none`, `animation-name: none`, 64×64, visible — the final state, not a removed element |
| Auto-continue fires | countdown ran out unattended → landed on `/devices` |
| A safe `?next=` still resumes | `?next=/authorize?...` → the Continue button landed on `/authorize` |
| The redirect is the *same* redirect | `git diff` shows **no** changed line touching `safeNext(`, `window.location.assign` or `router.push` — the four-line body matched as unchanged context when it moved from `finish()` into `performRedirect()`. `safeNext` itself is untouched, so the unsafe-`next` drop is unchanged by construction. |

### decisions inside this screen

| # | Decision | Why |
|---|---|---|
| P5-D1 | **The coins line renders only for an actual signup.** A returning login reaches this screen too (both paths call `finish("done")`), and for them the heading reads "You are signed in" with no bonus line. | `signup_complete` is once-ever. Announcing "+100 signup bonus" to someone who signed up last year promises coins the ledger will never pay. |
| P5-D2 | **The inviter is named here, not on the phone step.** Resolved through the new private `GET /coins/referral/resolve`. | The pre-auth banner cannot name anyone without publishing a code→handle oracle (P1-K2). Behind a session, the same walk costs a login and a rate-limit budget. The endpoint returns the handle **only**, comes through `shared.lookups` (coins may not read `identity.users` — import-linter contract), declines to name you to yourself, and answers `{handle: null}` rather than 404 for an unknown code so it cannot be used to test whether a code exists. |
| P5-D3 | **Auto-continue is a visible countdown on the button**, not a silent timer. Pressing the button skips the wait. | An unannounced redirect reads as a crash. The countdown also makes the 6 s legible as a choice rather than a stall. |
| P5-D4 | The amount comes from `signup_complete` in the rules table; the block is absent if the rule is missing. | Same rule as the referral banner — no invented figures, no fallback. |

### fixed

| # | What was wrong | Fix |
|---|---|---|
| P5-F1 | The ✅ rendered as the literal text `✅`. JSX **text children** are not string literals, so escape sequences in them are not interpreted — the site icons were fine because those live in a real string literal inside `SITES`. | Real glyphs in the JSX text. Caught on the first capture. |
| P5-F2 | At 390 in Tamil, the site-strip taglines ran straight over their card borders into the neighbouring tile. Tamil and Hindi taglines are single long words with no break opportunity, so the grid column could not wrap them. | `break-words` on the tagline. Note this never showed up in the page-level overflow check — the page width stayed at exactly 780 px throughout; only the *card* was overrun. A width assertion is not a layout check. |

### flagged — for CP1

| # | Observation | Note |
|---|---|---|
| P5-Q1 | **The notification bell strip now appears on the done screen** (with a "1" badge — the signup notification). The reference draws this screen with no chrome at all. | It is the P1-F2 gate working as written: the session cookie exists by now, so the strip renders. It is honest, but a green bar with an unread badge above "Your AgriID is ready" is chrome the reference deliberately does not have. Cleanest fix is to keep the login route chrome-free regardless of session, which needs the strip moved out of the root layout. Your call. |
| P5-Q2 | **Returning users also get this screen**, with a 6 s countdown, on every login. | The prompt says the screen renders after `finish("done")`, and both paths call it — so I built it that way. But it does add an interstitial to the common path. Skipping straight through for returning users is a one-line change if you'd prefer it. |

### testing note

The dev IP's daily OTP counter (`otp:day:ip:172.19.0.1`, cap 20) was exhausted
by this pass's capture runs and **reset once** in Redis to continue. Recorded
because it is real throttle state that was cleared: it is local-only abuse
protection in front of a mock SMS driver, no message was ever sent, and no
product behaviour was altered — the 429 proof in P2 was captured against the
genuine phone-cap throttle before this.

---

## P6 · gated (503) + locked (429) — verify-only

Proofs: `p6-gated` (× live/ref × 1280/390). The locked half was captured with
P2 (`p2-otp-locked`) against the genuine phone-cap throttle; its findings are
recorded there (P2-Q1…Q3) rather than repeated here.

The gated state was reached the real way: `signup_enabled` flipped to `false`
in `public.feature_flags`, waited out the 30 s flag cache, confirmed the API
returned `503 signup_unavailable`, captured, then **flipped back and
re-verified with a live 200**. No UI was posed.

Correct and unchanged: the rail and the trust strip both hide while gated —
there is no progress through a closed flow, and "free forever" under a shut
door reads as an advertisement for something you cannot have. The screen is
an explanation, not an error, exactly as the code comment intends.

### findings

| # | Finding | Severity |
|---|---|---|
| **P6-Q1** | **The gated screen names the wrong site.** The live copy reads "We're finishing SMS verification with our provider. **The rest of Milk.in works without an account.**" — on `id.agri.in`, the shared login for all three sites. A farmer who bounced here from agri.in or theorganic.in is told to go use a dairy site. The string is a D30 leftover from when the gate was written for milk.in alone. | **Real bug on a launch-gate screen**, and the cheapest fix in this pass — one string, three catalogs. It needs to name the family or the site the visitor came from, not one sibling. |
| P6-Q2 | **No notify-me capture.** The reference offers a phone field and "Notify me — one SMS when sign-ups open. Nothing else, ever." Live explains and stops, so a farmer turned away at the door leaves no way to be told when it opens. The machinery exists (D23 pincode-interest / notify). | A feature ADD on a page the prompt scopes as verify-only, so flagged rather than built. Worth it only if sign-ups are actually gated at launch. |
| P6-Q3 | The reference gives the card a 🌱 and centres it; live is a plain left-aligned card. | Cosmetic. Recorded for completeness. |

---

## CP1 follow-ups (owner-approved)

Four changes taken after the CP1 walkthrough. Proofs for `p2-otp-locked`,
`p4-language` and `p6-gated` were re-captured against the new copy.

| # | Change | Detail |
|---|---|---|
| CP1-1 | **The 429 now names a real wait** (closes P2-Q1 + P2-Q2). `ApiError` carries `retryAfter`, read from the `Retry-After` header the throttles have always sent and this client used to discard. The copy no longer says "request a new code" — the action the throttle had just refused. | Verified live against both throttles: the daily phone cap renders "Wait about **24 hours**", the resend cooldown renders "Wait about **1 minute**". |
| CP1-2 | **The gated screen names the family, not one sibling** (closes P6-Q1). Was: "The rest of **Milk.in** works without an account", on id.agri.in. Now names agri.in, milk.in and theorganic.in and what stays free on them. | Re-captured with the flag genuinely flipped, then flipped back and re-verified with a live 200. |
| CP1-3 | **The language step has its subtitle** (closes P4-Q1): what the choice governs, and that it is reversible — which is the half that matters on a step committing on tap. | Rendered in the re-captured proof. |
| CP1-4 | **Returning users skip the done screen** (closes P5-Q2). `verifyAndLogin`'s existing-user branch calls `performRedirect()` directly, exactly as the flow behaved before this pass. | Verified live: an existing account landed straight on `/devices`, done screen never mounted. |

Two bugs in my *own* first cut of CP1-1, both caught by re-capturing rather
than by reading the diff:

- **"Wait about 1440 minutes."** The per-phone cap is a full 24 h, and minutes
  is the wrong unit for it. Anything an hour or over is now said in hours.
- **"Wait about 1 minutes."** No plural handling. Both strings are now ICU
  plurals in all three catalogs.

The `isNewUser` guard on the coins line is deliberately kept even though
returning users can no longer reach that screen. It costs nothing and the
thing it prevents — announcing a signup bonus the ledger will never pay — is
worth a dead branch.

P5-Q1 (the bell strip on the done screen) stands as built, per your call.

---

## P7 · `/account` — profile

Proofs: `p7-profile` (a 100 %-complete account), `p7-profile-partial` (30 %,
where the missing line and the reward pill do their work), and
`p7-profile-handle` (the change panel open on a real `reserved` verdict)
— × live/ref × 1280/390.

Every value on these proofs came from the server: each capture signs in for
real and fills the profile through the real API from inside the authenticated
page, including a real multipart PNG upload.

Self-check: `scrollWidth === clientWidth` at both sizes, console clean.

### built

| Item | Note |
|---|---|
| **@handle block** | The one identity field this app owns and the shipped page never showed. Read-only, with a Change button that appears only when the change is still available. Changing it re-uses the login step's live `/auth/handle/check`, so nobody spends a once-ever allowance discovering a name is taken. The validation strings are the login step's own — not copies — so `reserved` cannot come to mean two different things on two screens. |
| **Completion reward + what's missing** | "+200 AgriCoins at 100%" (from the `profile_100` rule at render time) and "Still missing: your location, your name, an interest, a photo". The bar used to be a percentage with no next action. |
| **"District only — never your pincode"** | Under the Location visibility row. "Location" without saying how much of it is the difference between a district and a doorstep. |
| **Interests explainer** | What interests *do* — pick what you see first, never public unless you turn the switch on. The shipped hint only said how many you may add, which answers a question nobody asked. |

### fixed

| # | What was wrong | Fix + evidence |
|---|---|---|
| P7-F1 | **Two contradictory save models on one page.** Name had a Save button while language, interests and every toggle applied instantly, so the page taught two different rules about when a change had taken. | Everything is instant-apply. Name commits on a 900 ms debounce and on blur; success is a per-section "Saved" flash beside the control that changed, rather than a toast that fires constantly and never says *which* field took. Failures still toast — those must interrupt. **Verified live:** zero Save buttons on the page, flash appeared after typing simply stopped, the value survived a reload, and the bar moved 30 % to 45 % with "your name" dropping out of the missing line. |
| P7-F2 | **The photo was a tick.** `ProfileOut` carried `has_avatar` and no way to see the image. | A real thumbnail, served by a new **owner-scoped** `GET /identity/profile/avatar`. Verified live: `naturalWidth/Height` 8x8 of the uploaded PNG, `content-type: image/png`, `cache-control: private`. |

### the seeded "sample" chip — there is no seeder

The FIX asks to remove the chip "and whatever seed put it there". **No such
seed exists.** Nothing in the repo writes interests — not the migrations, not
`scripts/`, not any fixture. The chip is a single hand-inserted row in the dev
database, on `AG-0000002` (your own dev account), almost certainly left over
from D11 credential-fill testing: `identity.profiles` for `AG-0000002` holds
`interests = ["sample"]`.

I did not touch it: it is your account's data, in dev only, and there is no
code change that would prevent it recurring because no code caused it. Say the
word and it is one UPDATE. Nothing ships with it.

### decisions

| # | Decision | Why |
|---|---|---|
| P7-D1 | **`missing` is computed on the server**, sharing one reading of the profile with the score (`completion.py`'s `_present`). | The bar and the line beside it are two renderings of one truth. Deriving the list in the client would let them disagree the moment a weight moves — and the client cannot see `phone_verified` at all. |
| P7-D2 | **The avatar is served through the API, not a public media URL.** The `avatars/` prefix stays private; only `products/` is public-read. | Catalog images take the media-domain route because a product photo is meant to be public. A face is not, and it has its own visibility switch *on this very page* — publishing it to a public-read prefix would leave that switch governing whether the URL is **shown** rather than whether the image can be **fetched**. |
| P7-D3 | **The handle rule renders in the state it is actually in.** A7's card says "One change ever — you haven't used yours" unconditionally. | Signup's pick **is** the one change (`set_handle` flips `agri_id_changed_once`), so for anyone who picked a handle at signup the truthful line is "already used, this is permanent". Both states are in the proofs. The Change button also **fails closed**: if `/auth/me` cannot be read, it hides rather than offering an irreversible action we are not sure the account still has. |

### deferred by construction

**The DPDP block is not on this page yet.** The prompt requires it wired to
W4's endpoints and explicitly forbids dead buttons, so it lands at CP3 with
those endpoints, and `/account` gets re-snapshotted then. Everything else in
P7 is complete.

### flagged — for CP2

| # | Observation | Note |
|---|---|---|
| P7-Q1 | **Every visibility switch defaults to off** for a new account, including Name. The reference shows Name, Location and Photo on, Interests off. | Privacy-safe as it stands, and the visibility card is marked SHIP, so I left the defaults alone. But it means a brand-new profile is invisible on reviews and answers by default, which may not be what you want. |

---

## P8 · `/devices`

Proofs: `p8-devices` (three real sessions from three real device profiles),
`p8-devices-mixed` (an account with real cross-site app sessions),
`p8-devices-stale` (the collapse), plus the counted confirm for each
— × live/ref × 1280/390.

Self-check: no overflow at either size, console clean.

### the fix, and what it cost

Every row used to read "web / web" or "web-admin / web-admin" — the OAuth
client id printed twice, with no time, no place and no way to tell eight
dev-login rows apart. A row now answers all four questions it should:

| Question | Where it comes from | Proof |
|---|---|---|
| **which site** | `kind` already carried it (`"web"`, or the client_id) — a mapping, no backend change | `p8-devices-mixed`: id.agri.in, agri.in and milk.in pills side by side |
| **what device** | NEW: a stored `device_kind` (migration 0054) | `p8-devices`: "Android - Chrome", "Mac - Firefox", "Windows - Chrome", each derived from the UA that actually minted that session |
| **where** | existing geoip | **not shown, and cannot be** — see below |
| **when** | `last_seen_at` / `created_at`, relative | "Active now", "9 days ago", "15 days ago" |

Plus: a "This device" chip, rename moved behind a ✎ tap (zero permanent
inputs on the page — asserted), stale sessions dimmed and folded into "▸ 2
older sessions", and a sign-out-everywhere confirm that names the count
("End 3 other sessions?"). Every sign-out is the existing backchannel
logout; no new session machinery.

### why a stored description and not a `user_agent` column

Sessions have never kept a raw UA — only `device_fingerprint`, a one-way
SHA-256 that cannot answer "what device is this?". A `user_agent` column
would have worked and was the obvious move. It is not what shipped: a full
UA is a high-entropy fingerprint at rest, and this screen needs exactly one
recognisable sentence. The description is derived once at session creation
and only it is stored, so the row keeps **strictly less** about the visitor
than the alternative while answering the question the screen asks.
`device_fingerprint` keeps doing the security job. There is a test asserting
the raw UA never lands on the row.

Parsing is deliberately shallow, and unrecognised agents return `None` →
"Unknown device". A wrong-but-plausible label is worse than a vague one. The
ordering traps are unit-tested, because a naive scan gets all three wrong:
Android UAs contain "Linux", every Chrome UA contains "Safari", and Edge's
contains "Chrome".

### "where" is not achievable as specced

`shared/geoip.py` resolves **subdivisions (state)**, not districts, and only
when a GeoLite2 mmdb is provisioned — an owner/VPS action that is on your
deferred list, so in dev it is off entirely and `place` is `None` on every
row. The field is in the payload and the UI omits it when absent, so the row
degrades to site + device + time. The reference's "Coimbatore" is a
district; the best this can ever say is "Tamil Nadu", and only once the mmdb
exists.

### findings

| # | Finding | Severity |
|---|---|---|
| **P8-Q1** | **Rows are sessions, not devices — and the page is called "Your devices".** A real dev account shows **28 live rows**, because every login mints a new `sessions_web` row and nothing dedupes by `device_fingerprint`. Signing in from the same phone ten times produces ten rows. My fix makes each row legible; it does not reduce their number, and at 28 rows legibility is not enough. | **The biggest remaining issue on this page.** The 30-day stale collapse does not help — these were all 7–15 days old. |
| P8-Q2 | I did **not** fix P8-Q1, and deliberately. The obvious fix (group by fingerprint, show the newest) would make "Sign out" a lie: revoking the group's newest session leaves its siblings alive, and fixing *that* means either a revoke-by-fingerprint action or capping live sessions per device at login — both squarely "new session machinery", which this pass is told not to add. | Needs your call. My recommendation is the login-time cap: one live web session per fingerprint per site, which makes rows ≈ devices honestly. |
| P8-Q3 | The reference's rows show a **place** on every row. Ours cannot until the mmdb is provisioned, and then only at state level. | Sequenced behind the VPS work. |

### testing note

Two sessions on the capture account were aged to 45 days in the database to
demonstrate the stale collapse — nothing in dev is old enough to trigger it
naturally. That is real state, changed to exercise a real code path, and it
is recorded here rather than left implicit. The dev IP's daily OTP counter
was also reset once more during this page's captures.

---

## CP2 decisions (owner)

**P8-Q1 / P8-Q2 — the 28 rows: logged as a fast-follow, P8 ships as built.**
Chosen as the option that does not weaken safety, and the reasoning is worth
keeping because the alternatives look safer than they are:

- Capping live sessions per device at login, and grouping rows with a
  revoke-by-fingerprint action, both make `device_fingerprint` load-bearing
  for a **destructive** decision. Its own docstring says it is "deliberately
  coarse - it distinguishes 'my laptop' from 'a stolen token replayed
  elsewhere', not one user from another": two different Windows/Chrome
  machines produce the same fingerprint. A login-time cap would therefore
  silently end a session on a genuinely different device, and a grouped sign
  out would revoke more than the row it sits on describes.
- Grouping also **merges two real devices into one row**, which can hide a
  rogue session — the precise thing this page exists to reveal.
- Lowering the stale threshold to ~7 days folds recent sessions out of
  immediate view, which is the same problem in a smaller form.

Shipping as built changes no security-relevant behaviour: every session stays
individually visible, individually revocable, and now correctly labelled.
The cardinality problem is real and stays open as its own scoped work, with a
session-lifecycle decision behind it rather than a display change.

**P7 — both items left alone**, per your call: the "sample" chip stays in
your dev data (no code produced it, nothing ships with it) and the visibility
switches keep defaulting to off, which is the privacy-safe direction.
