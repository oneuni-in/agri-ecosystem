# Agri home performance — the A-U4 W0 record

**Status: W0 diagnosis complete, remediation partially landed, exit condition
NOT met on this machine. Escalated at CP0 — see §7.**

Instrument: `pnpm perf:home` (`scripts/perf-home.mjs`), Lighthouse 12.6.1 node
API, throttling read directly from `lighthouserc.cjs` so a local number and a
CI number mean the same thing (150 ms RTT · 1638 kbps · 4× CPU · mobile).
Machine: 8 logical cores, 15.3 GB RAM with ~3.4 GB free, Docker running the API
+ Postgres + Redis. Production `next start`, never `next dev` — see §6.

---

## 1 · The two distributions W0 asked for

Five runs each, same machine, back to back, production builds, same seeded data.

| | run 1 | run 2 | run 3 | run 4 | run 5 | median | **worst** |
|---|---|---|---|---|---|---|---|
| **pre-A-U3** `e90b30c` | 0.75 | 0.73 | 0.76 | 0.69 | 0.73 | **0.73** | **0.69** |
| **A-U3 HEAD** `698d192` | 0.76 | 0.72 | 0.71 | 0.75 | 0.71 | **0.72** | **0.71** |
| **after W0** (this branch) | 0.77 | 0.75 | 0.75 | 0.74 | 0.76 | **0.75** | **0.74** |

`e90b30c` is the last commit before A-U3's first commit (`fa61863`). Its own
message reads *"AG-A8 verified — 0.95 on /"*.

### The finding: A-U3 did not cause this. It inherited it.

Pre-A-U3 and HEAD are statistically identical — pre-A-U3 is in fact marginally
*worse*. The home has been under the 0.90 floor since before A-U3 touched it,
and the 0.95 recorded at `e90b30c` has never been reproducible here.

This is the same failure mode AG-A34 uncovered for `/categories`: a number was
read once, believed, and never re-measured, while `lighthouserc.cjs` picked a
representative run and hid the rest of the distribution. The A-U3 build did not
regress the home; it made a pre-existing deficit visible by sampling it twice.

---

## 2 · Where the time actually goes

Diagnosis was done against Lighthouse's own audits, not inferred from the score.

At HEAD, before any W0 change:

| Signal | `/` | `/categories` (the page that passes) |
|---|---|---|
| server-response-time | **900 ms** | 60 ms |
| FCP | 2.4 s | 1.8 s |
| LCP | 2.8 s | 2.9 s |
| TBT | 700 ms | 420 ms |
| CLS | 0.003 | 0.004 |
| DOM elements | **1,066** | 334 |
| Style & Layout | **3,497 ms** | 2,246 ms |
| Script Evaluation | 945 ms | 747 ms |

Two things stand out and neither is what a "slow page" usually means:

1. **Nothing is render-blocked in the classic sense.** `render-blocking-resources`
   reports 0 ms of savings and every JS chunk is priority `Low`. `inlineCss`
   (the issue-#45 fix) is doing its job.
2. **LCP is not a rendering problem, it is a BANDWIDTH problem.** The LCP
   element is the hero house-ad `<b>` — plain text, `Load Delay 0 ms`,
   `Load Time 0 ms`, and a `Render Delay` of ~1.9–2.6 s. Under
   `throttlingMethod: "simulate"` (Lantern), simulated LCP is approximately the
   time to drain every non-`Low`-priority byte through the throttled pipe. It
   is a byte budget.

### The blocking byte budget at HEAD

| Resource | Bytes | Priority | Share |
|---|---|---|---|
| 4 webfonts | 106,524 | VeryHigh | 45% |
| Document | 97,611 | VeryHigh | 42% |
| `/favicon.ico` | 29,966 | High | 13% |
| **Total blocking** | **234,101** | | |

At the configured 1474 kbps (~184 KB/s) that is ~1.27 s of pure drain before
the largest paint can be recorded.

### Two concrete defects fell out of that table

**(a) `/favicon.ico` 404s, and the 404 is a 132 KB HTML page.** web-agri had no
icon at all, so every visitor requested `/favicon.ico`, and Next answered with
the full HTML 404 — 29,966 transferred bytes at `High` priority, in the
critical path, on every cold load. Fixed by `app/icon.svg` (1,312 bytes).

**(b) The rupee sign downloads 37.9 KB of font.** Fonts download on glyph
*usage* via `unicode-range`. The four faces on this page are **all Latin** — no
Tamil or Devanagari despite the vernacular tile lines. Two of them are the
`latin-ext` subsets of Bricolage Grotesque and Public Sans (19,125 B + 18,757 B),
and the only rendered character that falls inside their declared range is
**`₹` U+20B9**, matched by the range's `u+20ad-20c0` span.

This is the issue-#45 Devanagari bug wearing a different costume — there, two
header strings pulled 121 KB of Noto Sans Devanagari onto every page. The
difference is that `₹` is not incidental: it is on every mandi price, every
scheme card and every product line of an Indian agriculture marketplace. It
cannot be SVG-substituted the way `हिं` and `दूध` were. **This lever is
identified, quantified and NOT yet taken** — see §7.

---

## 3 · What W0 changed, and what each change bought

| Change | Measured effect |
|---|---|
| `app/icon.svg` replaces the 404 favicon | **−28.7 KB** of blocking bytes |
| Explicit cache window per data class (`lib/home-data.ts`) + `force-dynamic` removed | server-response **900 ms → 350 ms** |
| `cache()` around every read | six sections share ONE `/market/today` call |
| Below-fold sections behind Suspense + A1 shimmer skeletons | FCP spread **622 ms → 141 ms**; score spread 0.05 → 0.03 |
| `content-visibility` moved onto the boundary wrapper | recovered a ~200 ms TBT regression the refactor introduced |

Net: median **0.72 → 0.75**, worst sample **0.71 → 0.74**, and CLS held at
**0.003 on all five runs**.

`force-dynamic` deserves a note: it was redundant (the route reads `cookies()`,
which already makes it dynamic) and actively harmful, because it downgrades
every fetch default to no-store — the revalidate windows the reads declared
were never taking effect. Removing it is most of the 550 ms server-side win.

---

## 4 · Streaming did not help the score, and here is the honest reason

The build prompt prescribes streaming as the structural fix. It is now
implemented, and on this metric **it is approximately neutral** — the gain in
the table above comes mostly from the favicon and the cache windows.

Three measured attempts:

| Structure | median | CLS worst |
|---|---|---|
| everything streamed, incl. above-fold | 0.65 | **0.102** |
| + `content-visibility` restored | 0.67 | **0.103** |
| above-fold awaited, below-fold streamed | 0.75 | 0.003 |

Two lessons, both paid for:

1. **Never put the LCP element behind a Suspense boundary.** The hero is the
   LCP element. Behind a boundary its fallback paints early and React then
   *replaces* it when the ad serve resolves — so the largest paint is recorded
   at the swap, not the first paint. LCP went 2830–3383 ms → 3415–3748 ms.
   Streaming the largest element cannot help, because the swap *is* the paint
   being measured.
2. **Above the fold, "renders first" and "streams" are opposites.** Streaming
   the TODAY strip swapped a skeleton for content above the fold and put CLS at
   0.103 on two of five runs against a 0.003 baseline.

The reason streaming cannot move this particular number is in §2: simulated LCP
is a *byte* budget, and streaming reorders bytes rather than removing them —
the skeletons and extra flight chunks add ~38 KB.

**It is kept anyway**, for reasons that are not score-chasing: AG-A36 requires
it; it is a genuine improvement for real users on real networks (Lantern is a
model — issue #45 recorded a page that simulated poorly and *observed* ~150 ms);
and it is the structure W2/W3 need in order to add coins and notifications to
this page without re-blocking first byte. That trade is recorded here rather
than buried.

---

## 5 · The instrument reads ~0.12 low — and that is the blocker

`/categories` is the control. CI enforced these medians on PR #81:
`/categories` **0.96**, every run ≥ 0.91.

Same page, same commit, this machine, same session as the final `/` run above:

| | min | median | max |
|---|---|---|---|
| `/categories` on CI (PR #81) | — | **0.96** | — |
| `/categories` here | 0.80 | **0.84** | 0.86 |

**A known-green page reads 0.12 lower here than in CI.** The local instrument
is *precise* — spread is only 0.02–0.06 across five runs — but it is *biased*
low, and the bias is a property of the machine, not of the page: `/categories`
has a 3× smaller DOM and the same fonts, and still cannot reach 0.90 here.

That is the structural obstacle. **No page-level change can produce five green
runs on this machine**, because the page that CI says is comfortably green
cannot produce them either. Even deleting every webfont (106 KB, ~578 ms of LCP
drain) would not close a 0.12 gap that a 334-element page also fails to close.

Applying the measured +0.12 offset, `/` after W0 projects to roughly **0.87 in
CI** — better than the 0.72-equivalent it started at, and still short of 0.90.
The offset is an approximation, not a certification.

---

## 6 · Two traps worth not re-paying for

- **A `next dev` server was squatting on port 3002** from an earlier session.
  It answers 200 and looks right; the tell is unhashed chunk names
  (`/_next/static/chunks/app/page.js`) and no `BUILD_ID` in the HTML. The first
  TTFB samples taken against it read 1.15–2.25 s and were discarded. Every
  number in this file is from `next start` on a clean build, verified by hashed
  chunk names. This is the U2 build-vs-dev `.next` trap; `NEXT_DIST_DIR` exists
  to avoid it.
- **The Lighthouse CLI's Windows EPERM crash is avoidable.** `perf:home` drives
  the node API and owns Chrome's teardown, so the EPERM race — which fires
  *after* results are in hand — is swallowed instead of losing the run. AG-A34
  recorded local Lighthouse as unusable on this machine; it is usable.

---

## 7 · Open, and why it is at CP0 rather than in a commit

**The W0 exit condition — five consecutive `/` runs ≥ 0.90 — is not met, and
cannot be met on this machine.** Per the build prompt this is escalated as a
finding, not renegotiated as a threshold. Decision 3 stands; nothing here asks
for a carve-out, and the 0.90 gate is untouched.

Two things need an owner decision:

1. **Which instrument certifies AG-A35.** Local runs cannot, on the evidence in
   §5. CI can — it is the authority that already gates the other six agri
   routes. The proposal is to add `/` to CI's assertion matrix at 0.90 and let
   the PR run be the record, with `pnpm perf:home` kept as the fast relative
   instrument for engineering.
2. **The `₹` font lever (§2b) is identified but unattempted** — 37.9 KB, ~18%
   of the remaining blocking budget, worth roughly 200 ms of LCP. Every option
   costs something real: `local()`-backed `@font-face` overrides depend on
   fragile cascade ordering under `inlineCss`; per-occurrence SVG substitution
   would put dozens of nodes into the hottest section of the page; declaring
   `latin-ext` as a preloaded subset forces the download app-wide across
   web-milk and web-organic too (issue #45's recorded blast-radius warning).
   None should be picked without the owner, and it is the last identified lever
   before the gap is machine, not page.
