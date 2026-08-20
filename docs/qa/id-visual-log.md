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
