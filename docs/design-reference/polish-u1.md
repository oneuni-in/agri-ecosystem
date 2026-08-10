# U1 — Milk.in home rebuilt to the approved reference

Binding-proof + gap-list document for SPEC U1 (`feat/u1-milk-home-ui`).

---

## 0. Prompt-to-repo substitutions (recorded, not silently applied)

| Prompt says | Repo reality | Substitution used |
| --- | --- | --- |
| `docs/design-reference/milkin_home_reference.html` (BINDING spec) | **Does not exist** — never committed in any branch (`git log --all --diff-filter=AD` is empty for that path) | `docs/design-reference/desktop v3.html` — `<title>milk.in — home reference (U1 approved v7)</title>`, header comment `U1 APPROVED REFERENCE (v7)`, fully responsive (20 `@media` blocks, breakpoints mobile <768 / tablet 768–1023 / desktop ≥1024), numbered section comments `1 · 2 · 2b · 3 · 4 · 5 · 5c · 5d · 5b · 6 · 7 · 8 · 8f · 8g · 8b · 8c · 8d · 8e · 9 · 10a · 10b · 10c · 10 · 11 · 12` matching the prompt exactly. This **is** the binding reference under a different filename. |
| `docs/design-reference/mobile v4.html` (supplementary) | Exists | Used as the v8 mobile snapshot only (375px static mock, no CSS of its own — it inherits `var(--*)` from a host page). Reference wins on conflict. |
| `pnpm --filter @agri/web-milk lighthouse` | No `lighthouse` script in `apps/web-milk/package.json` | `node scripts/lhci-affected.mjs` (the CI gate) with `lighthouserc.cjs`; home `/` binds the Constitution floor (perf ≥ 0.90, a11y ≥ 0.95, seo ≥ 0.95). |
| "token lint (no raw hex)" | — | `pnpm check:hex` (`scripts/check-hex.mjs`) — bans hex/`rgb()` in `apps/` and `packages/ui/`; `packages/config` is the only place literals may live. |
| "M3 organic-order test" | — | `packages/ui/src/lib/sponsored.test.ts` → *"preserves organic order and identity exactly (sponsorship on)"*. Backend side: `backend/core/tests/test_ads_serve.py`. |
| "hero approved-only test" | — | `backend/core/tests/test_ads_serve.py::test_pending_creative_never_serves_on_milk_slot` (+ `test_pending_creative_never_serves`, `test_milk_slot_keys_are_registered`). |

---

## 1. Gap list — component by component

Read order followed: (1) `desktop v3.html`, (2) `/demo?theme=milk`
(`apps/web-agri/app/demo/page.tsx`), (3) the home as built today
(`apps/web-milk/app/[locale]/page.tsx` + `layout.tsx` + `site-header.tsx` +
`site-footer.tsx`).

### 1.0 Global / page shell

| | Reference | Built today | Gap |
| --- | --- | --- | --- |
| Page width | `.wrap{max-width:1180px;padding:0 20px}` | Every block is `max-w-[720px]` (home, `GlobalAdBanner`, `SiteFooter`) | **Structure.** The app is a 720px column; the reference is a 1180px desktop layout with 3-up/4-up grids. A shared `Wrap` at 1180 is required or every desktop grid below collapses. |
| Page background | `body{background:var(--paper)}` where `--paper:#FDFBF6` (cream) | `body{background:var(--page-bg)}` = `#E9EBE2` (grey-green) | **Token.** New cream token needed; `--paper` name is already taken by `#F7F8F3` across 3 apps — must not be repurposed. |
| Fonts | Bricolage Grotesque + Public Sans + Noto Sans Tamil | Same, via `fontVariables` / `--font-display` / `--font-body` | None. *(DO-NOT: no new fonts — honoured.)* |
| Focus ring | `3px solid var(--mk)` (brand) | `3px solid var(--accent)` + `outline-offset:2` | Keep the repo's (design-system.md §1.4, "never remove"). Reference deviation accepted, recorded. |
| Reduced motion | `@media(prefers-reduced-motion:reduce){*{animation:none}}` | Per-component `motion-reduce:` classes | Add the global rule alongside; both are additive. |
| Radii | `--radius:12px`, `--radius-lg:16px` | `rounded-btn:12px`, `rounded-card:16px`, `rounded-band:18px`, `rounded-pill:99px` | None — map reference `--radius`→`rounded-btn`, `--radius-lg`→`rounded-card`. |

### 1.1 Tokens (reference `:root`, prompt §13) — **Pass 1**

| Reference token | Value | Status in `packages/config/tailwind/preset.js` | Action |
| --- | --- | --- | --- |
| `--mk` / `--mk-deep` / `--mk-soft` | `#2563A8` / `#174A85` / `#E9F1FA` | `--brand` / `--brand-deep` / `--brand-soft` under `theme-milk` | Exists — reuse, no change. |
| `--mk-soft-2` | `#B9D2EE` | **missing** | Used by the utility strip, header tagline, hero copy, footer body. Add. |
| `--mk-accent` / `--mk-accent-ink` | `#E9A61C` / `#4A2E00` | `--accent` exists; ink **missing** | Add accent-ink (money-button text, hotline chip, coins pill). |
| `--paper` (cream page bg) | `#FDFBF6` | name collision (`#F7F8F3`) | Add as **`--cream`** → `bg-cream`. |
| `--paper-border` (cream hairline) | `#EDE6D6` | **missing** (`--line` is `#E2E7DA`, green-grey) | Add as **`--cream-line`**. |
| `--paper-deep` | `#F4F0E6` | **missing** | Add as **`--cream-deep`** (brand-card "Nearest shops" button, §8f — Pass 2). |
| `--ad-border` (golden sponsored border) | `#E9A61C` | **missing** | Add as **`--ad-border`**. Must be its own literal, *not* `var(--accent)`: organic's accent is `#B5541C`, and a sponsored border is golden in every theme. |
| `--trust-bg` | `#FEFAF0` | **missing** (`--certgold-bg` is `#FFFBEE`, close but not equal) | Add as **`--trust-bg`** (§6 highlighted card — Pass 2). |
| `--muted` | `#8A8574` | **missing** (`--sub` is `#5A6A5D`) | Add as **`--muted`** — the reference uses it for every card sub-line; `--sub` at `.78em` is the `.vern` a11y contract and must not be re-pointed. |

Naming convention followed: lower-kebab CSS var in the `shared` block of the
preset (where `--paper`, `--line`, `--sponsored-bg` live) + a matching Tailwind
`colors` key. `--mk-soft-2` / `--mk-accent-ink` go in the per-theme block
(`--brand-soft-2`, `--accent-ink`) since they are brand-derived.

### 1.2 §1 Utility strip — **Pass 1**

| | Reference | Built today | Gap |
| --- | --- | --- | --- |
| Existence | `.util` bar above the header: tagline · spacer · "List your business" · "Advertise" · hotline chip | **Does not exist** | **Structure.** New component. |
| Colors | `background:var(--mk-deep); color:var(--mk-soft-2)`; chip `--mk-accent` on `--mk-accent-ink` | — | Needs `--brand-soft-2` + `--accent-ink` from §1.1. |
| Responsive | `@media(max-width:767px){.util .link{display:none}}` — links hide, tagline + hotline stay | — | New. |
| Hotline number | from config/env; **render slot even if empty → hide chip** | no such config | New `NEXT_PUBLIC_WHATSAPP_HOTLINE` (config-driven copy, per binding rules). |
| "List your business" | — | `ListBusinessCta` exists (header + footer variants), links D16 claim flow via `listingsHref(CONSOLE_URL)` | Reuse — add a `utility` variant, do not rebuild. |

### 1.3 §2 Main header — **Pass 1**

| | Reference | Built today | Gap |
| --- | --- | --- | --- |
| Brand lockup | `.brand` — `flex-direction:column; line-height:1.05`, `<b>` 22px display + `<small>` 10px `--mk-soft-2` | `HeaderStack`: 22px display `leading-tight` + `<small class="mt-[-3px] block text-[11px] opacity-85">` | **Structure — this is the EN/TA overlap defect.** `mt-[-3px]` pulls the tagline up into the logo's descender box; the tagline contains Tamil (`பால்`) whose ascenders/descenders exceed the Latin em-box, so at `leading-tight` the two lines collide. Fix = drop the negative margin, use the reference's explicit two-line lockup. |
| Tagline opacity | solid `--mk-soft-2` | `opacity-85` on white | **Token.** Replace opacity with the real token (same reasoning the preset already applies to `.vern`: opacity kills contrast ratios). |
| Search input in header | **none** — "no search bar; search lives in the search band" | none (home renders `PincodeHero` below) | Compliant. `/demo` shows `HeaderStack` with a `SearchBand`+`SearchBar` — that catalog entry stays for agri.in; milk must not adopt it. |
| Location selector | `.loc` button "📍 Coimbatore · 641001 ▾" | `HeaderLocation` → `LiveLocationPill` (D19 client island, the ONE switcher) | Restyle only. Do not touch the pill's logic. |
| Lang switcher | `.lang` "EN · த · हि"; `@media(max-width:767px){.hdr .lang-mobile{display:inline}}` (v8 §28: visible on mobile, no burger) | `LocaleSwitcher` in the right cluster, inside `Suspense` | Restyle + guarantee mobile visibility. |
| Coins pill | `.coins` "🪙 1,240" on `#FEF3DC`/`#854F0B` | `CoinsBalancePill endpoint="/api/coins/balance"` (D13 live) | **Token only** — repo has `--coins-bg #FFF3D6` / `--coins-fg #8A5B00`; reference `#FEF3DC`/`#854F0B`. Keep repo tokens (already AA-checked), record deviation. |
| Bell | `.bell` + `.n` badge | `NotificationBellIsland` (live D12) | Restyle only. |
| Account / guest (v8 §27) | logged-in: avatar + "Account" (`acct-label` hidden <768). logged-out: `.btn-login` replaces coins+bell+avatar | `AuthCluster` | **Verify** the guest swap matches; contact-reveal gate (D18) untouched. |
| Order | brand · loc · spacer · lang · coins · bell · account | brand · [ListBusinessCta + loc] · ml-auto[lang · bell · coins · account] | **Structure.** `ListBusinessCta` moves up to the utility strip (§1); coins/bell order swaps. |
| CLS risk | — | `site-footer.tsx` records: a 4th item in the right cluster moved CLS 0.098→0.136 | Constraint: the utility strip must be **static server-rendered markup**, and the right cluster must not gain a hydrating island. |

### 1.4 §3 Hero ad — **Pass 1**

| | Reference | Built today | Gap |
| --- | --- | --- | --- |
| Slot | `milk_home_hero_xl`, full-bleed | `AdSlot slotKey="milk_home_hero"` in a `max-w-[720px]` box, `h-[84px]` | **Structure + config.** New slot key must be registered in `SLOT_KEYS` (`backend/core/modules/ads/service.py:20`) — config-only, zero engine change — and seeded in `scripts/seed_house_ads.py` (`MILK_SLOTS`). |
| Creative sizes | 1600×420 desktop, 750×360 mobile | copy-only house cards (`media_keys: []`) | Seed house creatives at the new sizes via the existing media engine. |
| Carousel | arrows + dots; **1 creative → single static banner, dots hidden, no dead space** | `AdCarousel` exists: scroll-snap, autoplay 6s, paused on hover/touch/hidden, never under `prefers-reduced-motion`, dots only when `count > 1` | Reuse `AdCarousel`. **Missing: prev/next arrows** (`.hero-nav`) and the **"Ad" corner tag** (`.ad-tag`, top-right) — the component renders `SponsoredBadge` top-left instead. |
| CLS | reserved aspect-ratio box | `heightClass` is a required prop (fixed-height reservation) | Compliant; needs an aspect-ratio-shaped height for full-bleed. |
| Approved-only | component already guarantees | `/ads/serve` serves approved-only + `parseServeResponse` drops unlabeled (NN1 defense in depth) | No change. Test `test_pending_creative_never_serves_on_milk_slot` must stay green. |
| Position | above the search band, full-bleed, outside `.wrap` | `GlobalAdBanner` (`milk_global_header`) sits above `children` in the layout | **Decision:** the hero is a *page* slot; `milk_global_header` stays a layout slot. Two ad units above the fold is what the reference shows (utility strip → header → hero ad); the global banner is not in the reference for home. Flagged below. |

### 1.5 §4 Search band — **Pass 1**

| | Reference | Built today | Gap |
| --- | --- | --- | --- |
| Container | `.search-band` — brand gradient, `rounded-lg`, inside `.wrap`, centered, `margin-top:14px` | `PincodeHero` on `bg-header-gradient` `main`, full-bleed, `max-w-[720px]` | **Structure.** Becomes a contained rounded card, not a page-wide gradient. |
| H1 + subline | `clamp(19px,2.4vw,27px)` + `.sub #CFE0F2` | `PincodeHero title/subtitle`, hardcoded EN+TA strings on the page | Restyle; strings already exist in `ui.pincode.*` (en/ta/hi) — **the page should read them instead of hardcoding**. |
| Pincode input | white `.pin-row`, `letter-spacing:2px`, "Find milk" | `PincodeInput` + `PincodeHeroFinder` (6-digit → `router.push('/{pincode}')`) | Restyle only. **Reuse the existing geo/pincode logic verbatim** (prompt: "reuse the existing pincode/geo logic from the current hero, restyled"). |
| Voice mic (v8 §29) | `.search-mic` 🎙️ button inside the pin row → D25 voice pipeline | **missing** | New — routes to `/post-need` voice entry (`post-need/voice-recorder.tsx` exists). |
| Use-my-location | `.geo` pill | `GpsPill` → `/api/identity/location` (D19) | Restyle only. |
| Only search on home | binding | compliant | None. |

### 1.6 §5 Category bar — **Pass 1**

| | Reference | Built today | Gap |
| --- | --- | --- | --- |
| Data | D17 schema values, **no hardcoded list** | `fetchProductCategories()` → `GET /catalog/verticals/milk/schema`, `option_meta` labels + icons, unknown icon → 🥛 | **Already compliant.** Reuse as-is. |
| Form | white bar, `border:1px solid var(--paper-border)`, `rounded`, **text links** with an active underline + "All 13 ›" more link | `CategoryTileRow` → `CategoryTile` **icon tiles** in a scroll row | **Structure.** The reference's home bar is a text nav; the tile row is a different pattern (it stays in the catalog / on results pages). |
| Overflow rule | `flex-wrap:nowrap; overflow-x:auto; scrollbar-width:none; ::-webkit-scrollbar{display:none}`; `>*{flex:0 0 auto}` | `overflow-x-auto` + hidden scrollbar present; **`nowrap` and `flex-none` are not set** | **Structure.** NN5 ("never wraps at any viewport 320–1920") is not currently guaranteed. |
| Edge fade | prompt §5 requires it | reference CSS has **no** fade | **Reference gap** — prompt wins (it is additive and non-conflicting). Implement with a token-driven gradient mask. |
| Pinned filters | desktop pins "🚚 Home delivery" + "🌿 Organic" right (`margin-left:auto`); `@media(max-width:1023px){display:none}` — *not rendered* below 1024 | none | New. Must be **absent from the DOM** below 1024, not merely hidden (prompt: "are NOT rendered in the bar"). |

### 1.7 Later-pass sections (recorded now, built in Pass 2 / 3)

| § | Section | Data source status | Pass |
| --- | --- | --- | --- |
| 5c | Milk-type chips | `TypeFilterRow`/`TypeFilter` in catalog; D23 chip logic at `[city]/[pincode]/type-filter-row.tsx` — **restyle, don't rebuild** | 2 |
| 5b | Price ticker | `backend/core/modules/directory/milk_home.py::compute_price_banner` **already exists** (min–max per type from real listings) | 2 |
| 5d | Category-partner banner | slot `milk_category_banner` **already registered + seeded** | 2 |
| 6 | Organic trust row | `CertBar`/`CertCard` in catalog; static i18n | 2 |
| 7 | Certified products | `ProductCard`/`ProductGrid` in catalog; needs new `get_showcase_products(vertical, limit)` accessor + seed | 2 |
| 8 | Rich vendor cards | `ListingCard` already carries `priceTag` + `extraMeta` + rating-with-count; `covers()`/directory + D18 + coverage | 2 |
| 8a2 | Advertise house band | reference has `.advertise-band` CSS but **no markup instance** — author from CSS + prompt §32 | 2 |
| 8f | Brands available | D24 brand pages + `covers()` shop counts | 2 |
| 8g | Dairy services | D17 business categories → `/en/c/` routes | 2 |
| 8b | Stats band | needs ONE cached aggregate endpoint/server prop | 3 |
| 8c | How it works | static i18n | 3 |
| 8d | Reviews strip + coins nudge | D18 approved-only; D13 5/wk rule | 3 |
| 8e | Popular near you | existing ISR city/category routes | 3 |
| 9 | CTA tiles | `BigCtaTile`/`BigCtaGrid` in catalog; D25 + D16 routes | 3 |
| 10a | Price-alert card | D28 push (`notifications/push-alerts-card.tsx` exists) | 3 |
| 10b | App/PWA band | D28 `beforeinstallprompt` (`pwa-client.tsx` exists) | 3 |
| 10c | FAQ + JSON-LD | static i18n + `FAQPage` (home currently emits WebSite+Organization only) | 3 |
| 10 | Family strip | `EcoStrip`/`EcoPill` in catalog + live coins; theorganic href behind config | 3 |
| 11 | Footer | **current footer is a 720px row with a data-saver toggle only** — reference is a 5-col grid + legal row | 3 |
| 12 | Mobile bottom nav | `BottomNav` in catalog, **not mounted in web-milk at all**; needs `64px + env(safe-area-inset-bottom)` + body padding | 3 |
| 2b | My-need status strip | D25 active-need query | 3 |
| 35 | Skeleton cards | `Skeleton` primitive exists; reference `.skeleton` shimmer CSS is commented-example only | 3 |

### 1.8 Open flags (raised, not blocking)

1. **`milk_global_header` above the hero.** The reference's home has no global
   banner — utility strip → header → hero ad. Keeping both puts two ad units
   above the fold and adds ~90px before the search band. The layout slot is
   out of Pass 1's stated scope (`layout.tsx` is not a home-only file), so it
   is **left untouched** in Pass 1 and raised here for a human call.
2. **Coins-pill / focus-ring / `--muted` token values** differ slightly from the
   reference (repo values are the AA-checked ones). Repo tokens win; recorded
   above rather than silently changing either.
3. **1180px wrap** widens every page that adopts it. Pass 1 introduces it only
   on the home route's own sections; `GlobalAdBanner`/`SiteFooter` keep 720px
   until Pass 3 rebuilds the footer.

---

## 2. Binding proof

Per U1's rule, "wired" is demonstrated, not claimed: each row records the exact
source the section renders from, plus a mutation check.

### Pass 1

| § | Section | Renders from | Mutation check |
| --- | --- | --- | --- |
| 1 | Utility strip | `NEXT_PUBLIC_WHATSAPP_HOTLINE` (`apps/web-milk/lib/contact.ts`) · `listingsHref(CONSOLE_URL)` → D16 claim flow · `advertiseHref(CONSOLE_URL)` → M5 wizard | **Done.** Var unset in this build → the strip renders with no hotline chip (visible in every screenshot), never an empty golden box. Setting it renders the chip linking `wa.me/<digits>`. |
| 2 | Header | `HeaderLocation`→`LiveLocationPill` (D19) · `LocaleSwitcher` (locale routes) · `CoinsBalancePill` → `/api/coins/balance` (D13) · `NotificationBellIsland` → `/api/notify` (D12) · `AuthCluster` (AgriID session) | **Done.** Logged-out session renders the §27 guest state: `Login` in place of coins pill + bell + avatar (`CoinsBalancePill` returns null with no balance). Screenshots at all four widths show the guest header. |
| 3 | Hero ad | D21 slot `milk_home_hero_xl` → `AdCarousel` → `/api/ads/serve` (BFF proxy) → `GET /ads/serve` | **Done, twice over.** (a) Slot registered + seeded → `GET /ads/serve?slot=milk_home_hero_xl` returns 2 approved creatives with 1600×420 media; page renders 2 slides. (b) **Approved-only:** the dev serve-cap exhausting mid-capture made the carousel fall back to the house card with zero served creatives — the same fail-closed path a pending creative takes; asserted directly by `test_pending_creative_never_serves_on_milk_slot`, extended in this pass to cover `milk_home_hero_xl`. |
| 4 | Search band | Unchanged D19/D23 logic: `PincodeHeroFinder` → `/{pincode}`; GPS → `/api/identity/location` | **Restyle only** — no data path touched. Copy now reads `ui.pincode.*` from the i18n catalogs instead of page literals (TA/HI screenshots show the translated H1/subline). |
| 5 | Category bar | D17 vertical registry: `fetchProductCategories()` → `GET /catalog/verticals/milk/schema`, `option_meta` labels | **Done.** The live bar renders 13 entries — Milk, Ghee, Paneer, Milk Powder, Yogurt, Lassi, Curd, Buttermilk, Cheese, Butter, Cream, **Khoa**, Flavoured Milk — including `khoa`, the schema value U1's own example names. Zero code enumerates them; the icon map falls back to 🥛 for unknown keys. |

### NON-NEGOTIABLES status after Pass 1

| # | NN | Status |
| --- | --- | --- |
| 1 | Side-by-side vs reference at 360/768/1024/1440 | **Captured** — `docs/design-reference/u1/home-after-{w}.png` vs `reference-{w}.png`. Pass-1 sections match; the page is intentionally short of §6 onward. One open deviation: §1.8 item 1. |
| 2 | Lighthouse ≥90 mobile on home, hero live | **Not verified locally.** Measured 0.82 (range 0.76–0.86 across 6 runs) on a box also running Docker, the API and two Next servers; the LCP element alternated between the hero image and the search-band `<h1>` at essentially the same LCP, i.e. variance, not the ad. `lhci autorun` cannot complete on Windows at all (chrome-launcher `EPERM` deleting its temp profile — the documented local gap), so the CI job is the arbiter. a11y **1.00**, SEO **1.00**, best-practices 0.96, **CLS 0.0084**. |
| 3 | TA/HI without layout break | **Captured** at 360 + 1440 (`home-after-{ta,hi}-{360,1440}.png`). |
| 4 | Existing tests green | **Yes.** 260 backend ads/delivery tests; workspace lint + typecheck + tests (10/10, 4/4). Includes the M3 organic-order test and both approved-only tests. |
| 5 | Category bar never wraps 320–1920 | **Enforced in the component**, not left to callers: `flex-nowrap` + `whitespace-nowrap` + `[&>*]:flex-none` on the scroller. Measured: filters stay pinned right at 1024/1440, absent below 1024. |

### Defects found and fixed during Pass 1 verification

1. **EN/TA header overlap (the defect §2 names).** Cause: `-mt-[3px]` + `leading-tight` pulled the tagline into the logo's box; the tagline carries Tamil/Devanagari whose ascenders exceed the Latin em-box. Fixed with a real two-line lockup (own line-heights, 1.35 on the tagline).
2. **Header 3-line wrap at 360px.** The single-row header let the tagline wrap, turning a 56px bar into ~100px. Fixed with `whitespace-nowrap` + a `max-sm:hidden` English half (the mobile reference shows only `பால் · दूध` here).
3. **Location pill collapsed to a circle at 360px.** Below `sm` it drops its label and the bare `📍 ▾` wrapped onto two lines. Fixed with `whitespace-nowrap` on the shared glass pill.
4. **Two axe `color-contrast` failures** (a11y 0.96 → **1.00**):
   `--brand-soft-2` on the flat `--brand` header measured **3.94:1** (the reference's own pairing is under AA) → tagline uses `--brand-soft` (7.4:1); `--brand-soft-2` stays correct on `--brand-deep` in the utility strip.
   White on the glass location pill over flat `--brand` measured **4.34:1** → the pill is now plain text on the header, which is what the reference (`.loc{color:var(--mk-soft)}`) specifies anyway (7.4:1).
5. **Carousel arrows escaped the hero box and inflated it.** The preset's `.tap-target` utility sets `position: relative` and, being emitted after Tailwind's core utilities, silently beats `absolute`. Both arrows fell into normal flow, stacked below the carousel, and added 2×32px to it — the reserved box measured 333px instead of 269px at 1024. Fixed by giving the arrows a 44px transparent button around a 32px disc instead of `.tap-target`. Hero now measures exactly 3.81 (1600/420) at both 1024 and 1440. **`.tap-target` must never be combined with `absolute`.**
6. **Arrows invisible over light creatives.** The reference's translucent-white disc vanishes on arbitrary artwork; now a solid ink disc.

## 3. Screenshots

`docs/design-reference/u1/`, regenerated by `node scripts/capture-u1.mjs`
(which resets the dev serve-cap before each page load — otherwise the 3/day
per-placement cap exhausts mid-sweep and later shots capture the house
fallback instead of a served creative).

| File | What |
| --- | --- |
| `home-after-{360,768,1024,1440}.png` | The real home, after Pass 1 |
| `reference-{360,768,1024,1440}.png` | The approved reference at the same widths |
| `home-after-{ta,hi}-{360,1440}.png` | NN3 locale proof |
| `home-after-full-{360,1440}.png` | Full-page record |

**Before:** the pre-U1 home is the parent commit of this branch's first Pass-1
commit; its four-viewport capture is pending a rebuild at that commit and is
recorded here as outstanding rather than claimed.

---

## 4. Full-reference build (passes 2 + 3, merged at the owner's direction)

The owner redirected from the pass-by-pass plan to "make it match the
reference, fully bound and fully localised". Every remaining section shipped in
one pass. Sections build from **one server-side aggregate** (`lib/home.ts`
`fetchHomeData()`); there is no client fetch and no mock row on the page.

| § | Section | Renders from |
| --- | --- | --- |
| 5b | Price ticker | D23 `compute_price_banner()` via `/catalog/milk/home/{pincode}` — real ₹ bands from approved listings |
| 5c | Milk-type chips | schema `filters` array + D17 `milk_type` `option_meta` labels |
| 5d | Partner banner | D21 slot `milk_category_banner`, approved-only, collapses when empty |
| 6 | Trust row | static i18n content component (allowed) |
| 7 | Certified products | `getShowcaseProducts()` — the ONE accessor, over `/catalog/verticals/{v}/products` |
| 8 | Vendor grid | `covers()` blend + D18 `/reviews/summary` (rating **and** count) + M3.C `recommended` |
| 8a2 | Advertise band | house copy → M5 wizard, rate from config |
| 8f | Brands available | same blend's `shop` cards; hidden when the pincode has none |
| 8g | Dairy services | D17 business categories → existing `/c/{category}` pages |
| 8b | Stats band | real aggregates; a cell with no honest source is not rendered |
| 8c | How it works | static i18n |
| 8d | Reviews strip | D18 per-business reviews (public reads are approved-only), composed across the page's businesses |
| 8e | Popular near you | D28 covered-pincode feed → existing ISR city pages |
| 9 | CTA tiles | D25 post-need + D16 claim flow; ₹ from config |
| 10c | FAQ | static i18n + FAQPage JSON-LD from the same strings |
| 10 | Family strip | live coins route; theorganic tile behind config → "coming soon" |
| 11 | Footer | 5-col, neutrality line verbatim, categories from D17 |
| 12 | Bottom nav | fixed 64px + safe-area; `<body>` reserves the height so the footer clears it |

### Localisation (owner requirement: a locale switch leaves no English behind)

`/en` renders the reference including its designed Tamil accents; `/ta` and
`/hi` render entirely in that language. Fixed in this pass: the pincode box
(placeholder, Find button, GPS pill), the utility-strip and brand taglines, the
`Login` label, the `★ Sponsored` badge, the data-saver ON/OFF words, and the
`/week` rate suffix — all now read from the catalogs.

`Badge variant="sponsored"` gained an optional `label`: the disclosure still
cannot be omitted or replaced with arbitrary children (empty/whitespace falls
back to "★ Sponsored"), it can only be **translated**.

**Verified in a real Chromium** (`node scripts/verify-u1.mjs`):

| Locale | Sections rendered | Console errors | Untranslated UI chrome |
| --- | --- | --- | --- |
| en | 34 | 0 | 92 (expected — this page *is* English) |
| **ta** | 34 | 0 | **0** |
| **hi** | 34 | 0 | **0** |

The probe deliberately excludes DB-driven text. Business names, product names,
review bodies and district names are stored in one language and are **not**
translatable strings — Tamil pages legitimately show "Sri Balaji Milk Supply"
and "Milk in Salem".

**NN5 proven by measurement**: the category bar holds 14 items on exactly one
row (`contentRows: 1`, constant 44px height) at 320/360/414/480/640/768/1024/
1280/1440/1600/1920 — `wrapsAt: []`.

### Harness traps that produced false greens (all now asserted against)

An earlier run reported "0 untranslated strings in every locale" — from a page
that had never rendered. Three separate causes, each of which turns a
non-result into something indistinguishable from a pass:

1. `waitUntil: "networkidle"` never settles (coins pill, notification bell and
   ad carousel all poll), so the navigation ended on `chrome-error://` and
   every probe returned empty.
2. next-intl writes a `NEXT_LOCALE` cookie, so a `/` visit after a `/ta` one
   redirected mid-run and destroyed the execution context. Each page now gets
   its own browser context.
3. **`AuthCluster`'s silent-SSO probe navigates the TOP-LEVEL window** to the
   AgriID IdP (`:3003`, `prompt=none`). With that app not running the tab
   landed on the browser error page ~1s after render — blanking the page after
   the "did it load?" check had already passed. The harness now answers that
   request with `204` (stay put) and **re-asserts after the capture**.

Point 3 is a pre-existing D10 behaviour, not something U1 introduced, but it is
worth an owner decision: **if the IdP is unreachable, the consumer home blanks
into a browser error page.** Recorded here, not fixed — it is outside U1's
view-layer scope.

### 4a. Location is now one shared value (owner request)

The home renders from **the visitor's own pincode**, not a build-time constant.

| Case | Header pill | Page content |
| --- | --- | --- |
| First-time guest (no login, no pincode typed, no GPS) | `📍 Coimbatore · 641001 ✏️` | 641001 — 5 vendors, "Brands available in 641001" |
| After typing `636810` in the §4 box | `📍 Dharmapuri · 636810 ✏️` | 636810 — 1 vendor, brands section correctly hidden |

Both measured in a real browser, not asserted.

One value, one owner: `resolveHomePincode()` reads the `agri_loc` cookie (D19)
and falls back to `DEFAULT_LOCATION` config. The §4 pincode box now *sets* that
cookie through the same `/api/identity/location` endpoint the header pill uses
— so the server stays the validator, and header and content cannot disagree.
The `✏️` next to the pincode is the explicit change affordance the owner asked
for; the D27 category pages keep the old navigate-only behaviour via the
`setsLocation` opt-in.

`DEFAULT_LOCATION` lives in its own module (`lib/default-location.ts`) because
both sides need it and `lib/home.ts` is server-only — importing that into the
client header island would drag `API_BASE_URL` and server `fetch` into the
browser bundle.

**Cost of going per-visitor, measured.** The location-bound sections stream
behind three Suspense boundaries whose skeletons reserve the loaded dimensions
(§35), so the shell, hero and search band never wait on the blend:

- **TTFB 26–44 ms**, full response 42–61 ms warm / 283 ms for a cold pincode.
- **CLS 0.0016** unthrottled, **0.0070** at 4× CPU throttling — *better* than
  the 0.0084 measured before the change, and far under the 0.1 "good" bar.

**Lighthouse could not be run for this change.** It now fails `PAGE_HUNG` on
this machine against *every* route including `/offline`, the simplest page in
the app — so it is the local Lighthouse environment, not the home page. (The
same box also cannot complete `lhci autorun` at all: chrome-launcher `EPERM`.)
Two audits are therefore outstanding and CI remains the arbiter. What is *not*
outstanding is the metric this change actually put at risk — CLS — which is
measured above.

### Open items and deviations

1. **`milk_global_header` unmounted — owner-approved.** It sat in the shared
   layout, is absent from the reference, and stacked a second ad unit directly
   above the §3 hero. The slot key and its house creatives still exist in the
   engine, so re-mounting it on the routes that have no hero of their own is a
   one-line change whenever that inventory is wanted back.
2. **M3 sponsored injection is not on the home vendor grid.** The home is ISR;
   injecting a per-viewer ad would cache one advertiser for everyone for an
   hour and break impression caps. Injection stays on the dynamic
   `/{city}/{pincode}` results page, where it already lives — U1 forbids
   touching that logic, and this respects it. The §8a2 house band ships in the
   vendor block as specified.
3. ~~The home renders a configured pincode~~ — **resolved**, see §4a: the home
   now renders the visitor's own pincode and the header cannot disagree with
   the content.
4. **House-ad art is generated from the English copy.** Ad *copy* is per-locale
   in the DB, but `seed_sample_media.py` renders one image from the `en`
   variant, so the hero art reads English on `/ta`. Dev seed art only; real
   advertisers upload their own creative.
5. **Delivery window and coverage-pincode lines** from the reference's vendor
   card are not on the `covers()` wire payload, so they are not rendered rather
   than faked.
