# PASTE-READY CLAUDE CODE PROMPT — SPEC U1: MILK.IN HOME REBUILD TO APPROVED REFERENCE
# Repo prep BEFORE pasting: copy milkin_home_reference.html into the repo at
#   docs/ui/reference/milkin_home_reference.html   (commit it — it is the binding visual spec)
# Then open a FRESH Claude Code session in D:\agri-ecosystem and paste everything below the line.

═══════════════════════════════════════════════════════════════
## SPEC U1 — MILK.IN CONSUMER HOME → APPROVED v7 REFERENCE
   (~6h) · feat/u1-milk-home-ui · UI-ONLY
═══════════════════════════════════════════════════════════════
EXECUTION PLAN — CHECKPOINT SUB-SPRINTS (context management, MANDATORY):
Work in three passes. At the end of EACH pass: run the pass's verification commands, commit
the pass as one coherent unit (zero AM-staged files), post a short checkpoint summary
(what changed, which checks ran, screenshots taken), then PAUSE and wait for the human's
"continue" before starting the next pass. Do not read ahead into later passes' files.

  PASS 1 — FRAME: design-system tokens (cream bg/border, golden ad-border, trust-bg) added
    to the token source first · utility strip · main header (overlap fix) · full-bleed hero
    ad + milk_home_hero_xl slot config/seed · search band · category bar (overflow rule).
    Verify: token lint (no raw hex) · header at 360/768/1024/1440 screenshots · hero
    approved-only test still green · Lighthouse home.
  PASS 2 — COMMERCE CONTENT: milk-type chips · price ticker (+sellers count) · rich vendor
    grid (no dropped fields) · brands available · trust row · certified products showcase
    (accessor + seed).
    Verify: M3 organic-order test green · mutation checks: khoa schema-value, vendor price
    edit, suspend-vanish · TA/HI screenshots.
  PASS 3 — ENGAGEMENT + SHELL: stats band (cached aggregates) · how-it-works · reviews
    strip (approved-only) · popular-near-you · CTA tiles · app/PWA band · FAQ + JSON-LD ·
    family strip · footer · mobile bottom nav + safe-area padding.
    Verify: remaining mutation checks (review approve/reject, need→stat) · full-page
    screenshots desktop+mobile · Lighthouse final · full binding-proof doc complete.

TEST / VERIFY COMMANDS (run exactly these; if a script name differs in this repo, use the
repo's actual equivalent from package.json / Makefile and RECORD the substitution in the
checkpoint summary — do not silently skip):
  # frontend unit/component tests for the milk app
  pnpm --filter @agri/web-milk test
  # frontend lint + typecheck
  pnpm --filter @agri/web-milk lint && pnpm --filter @agri/web-milk typecheck
  # backend tests — MUST include M3 delivery/sponsored + ads approved-only suites
  cd backend/core && .venv\Scripts\python.exe -m pytest tests -k "m3 or ads or delivery" -q
  # full backend suite before the final PR
  cd backend/core && .venv\Scripts\python.exe -m pytest -q
  # Lighthouse gate (same budget as CI, mobile, home route)
  pnpm --filter @agri/web-milk lighthouse   # or the repo's lighthouseci script
  # dev stack + seeds when a fresh DB is needed (order matters; alembic BEFORE seeds)
  docker compose -f docker-compose.dev.yml up -d
  cd backend/core && .venv\Scripts\python.exe -m alembic upgrade head
  .venv\Scripts\python.exe scripts/load_geo.py && .venv\Scripts\python.exe scripts/seed_e2e_milk.py
  .venv\Scripts\python.exe scripts/import_vendor_seed.py
  .venv\Scripts\python.exe scripts/seed_house_ads.py --enable-flag
  .venv\Scripts\python.exe scripts/seed_sample_media.py

CONTEXT: The Milk.in home (apps/web-milk, route /en and locale siblings) works end-to-end but is
visually unfinished. A human-approved reference implementation exists at
docs/ui/reference/milkin_home_reference.html — a single self-contained file with desktop AND
mobile behavior (resize to see both). Your job is to make the REAL home page match that
reference: same section order, same tokens, same responsive behavior — but wired to the real
data sources listed per-section below. The kitchen sink at apps/web-agri /demo?theme=milk is
the component catalog; every new pattern lands there FIRST as a named section, then on the page.

READ FIRST (in order): 1. docs/ui/reference/milkin_home_reference.html (the spec) ·
2. /demo?theme=milk source (existing catalog) · 3. the home page as built today. Produce a
gap list (component-by-component: token deviations + structure deviations) in your plan BEFORE
writing code.

DO (sections numbered as in the reference file):
 1. UTILITY STRIP: tagline · List your business · Advertise · WhatsApp hotline chip (number
    from config/env, render slot even if value empty → hide chip).
 2. MAIN HEADER: brand lockup (fixes the EN/TA overlap defect) · location selector (existing
    pincode context) · lang switcher · AgriCoins pill (live count, existing coins endpoint) ·
    notification bell (existing) · Account. NO search input in header.
 3. HERO AD: full-bleed carousel bound to D21 slot milk_home_hero_xl via existing AdSlot
    fetch path. Register the new slot via seed/config (slot registry entry, house creatives
    for it, sized 1600×420 + 750×360 mobile). "Ad" corner tag. Arrows + dots. ONE creative →
    collapse to single static banner, dots hidden, no reserved dead space. Zero CLS: reserved
    aspect-ratio box. Approved-only rendering unchanged (component already guarantees).
 4. SEARCH BAND: H1 + subline + pincode input + Find milk + use-my-location — reuse the
    existing pincode/geo logic from the current hero, restyled. This is the ONLY search on home.
 5. CATEGORY BAR: generated from D17 schema values (NO hardcoded list). Overflow rule:
    flex nowrap, horizontal scroll, hidden scrollbar, edge fade; desktop pins Home delivery +
    Organic right (margin-left:auto); <1024px the two filters are NOT rendered in the bar
    (they exist as filter chips on results pages only).
 6. ORGANIC TRUST ROW: static content component (i18n strings): NPOP / PGS-India Green /
    USDA / We-verify (highlighted). 4-up desktop, 2×2 mobile. Lands in kitchen sink as
    section "trust-row".
 7. CERTIFIED PRODUCTS: new cross-vertical showcase component. Data source: create a thin
    server util behind ONE accessor (get_showcase_products(vertical, limit)) that today reads
    seeded demo rows shaped like the future TheOrganic catalog API; NO new tables — seed via
    existing products/media engines. "Where to buy 📍" → product/brand page. Kitchen-sink
    section "product-showcase".
 8. VENDORS: existing covers()/directory data, restyled cards. Sponsored card = 2px golden
    border + floating badge, ONLY where M3 delivery injects it (positions/caps unchanged —
    do NOT touch injection logic). Badges: Recommended (organic ranking only) · Verified.
    Buttons per primitives: Call solid green, WhatsApp mint.
 9. CTA TILES: two-up — Post my need (existing D25 route) · List my business (existing D16
    claim flow) + "How to apply · எப்படி" tertiary + advertise line. Kitchen-sink "cta-tile".
10. FAMILY STRIP: milk.in · theorganic.in · AgriCoins (live coins). Links: theorganic tile
    href behind config (site not live yet → "#" + coming-soon tooltip).
11. FOOTER: 5-col desktop / stacked mobile exactly per reference. Neutrality line verbatim:
    "We list, you choose — we never sell."
12. MOBILE BOTTOM NAV: fixed, 64px + safe-area; body padding-bottom clears it so footer is
    fully visible. Center mic button routes to post-need (voice-first).
13. TOKENS: add cream page bg, cream border, golden ad-border, trust-bg to the design system
    tokens FIRST (names per system convention), then consume. No raw hex in components.
14. i18n: every new string in EN/TA/HI JSONB/message files. No English-only tiles.

TRENDING-DESIGN SECTIONS (added to reference; ALL bound to built backend, none optional):
15. PRICE TICKER (section 5b): marquee strip under category bar — reads the EXISTING D23
    price-banner computation for the active pincode (min–max per milk type from real listings).
    Pause on hover; static row when prefers-reduced-motion.
16. STATS BAND (8b): count-up numbers on scroll-into-view — real aggregates: verified-vendor
    count (directory), covered-pincode count (business_coverage), needs-answered % (D25 leads
    responded/total), daily price checks (D21/analytics events). ONE cached aggregate endpoint
    or server-side props; never client-computed from full lists. Honest numbers only — if a
    stat is embarrassing pre-launch, hide that cell via config, don't fake it.
17. HOW IT WORKS (8c): static 3-step i18n component.
18. REVIEWS STRIP (8d): 3 APPROVED reviews from the D18 reviews engine (moderation-passed
    only), mixed EN/TA, linked to their businesses. Empty state: section hidden.
19. POPULAR NEAR YOU (8e): links to EXISTING ISR city/category pages (D23/D28 SEO routes) —
    generated from covered geo + schema values, not hardcoded.
20. APP/PWA BAND (10b): wires the EXISTING D28 install-prompt logic (beforeinstallprompt /
    iOS instructions fallback); "Install app" hidden when already installed.
21. FAQ (10c): native <details> accordion + FAQPage JSON-LD. Content i18n. The verification
    answer must state: verification can never be bought; paid = always "Sponsored".
22. MICRO-INTERACTIONS: hover lift on cards, scroll-reveal, count-up — ALL gated behind
    prefers-reduced-motion; zero layout shift; no animation library (CSS + one small
    IntersectionObserver as in the reference).
23. MILK-TYPE CHIPS (5c): icon+EN+TA filter chips (All/Cow/Buffalo/A2/Organic/Curd&ghee/
    Home delivery) — D17 milk-type values + attribute filters; horizontal scroll; drives
    the same filter state as D23's existing chip logic (restyle, don't rebuild).
24. RICH VENDOR CARDS (8): preserve the FULL card content from the current build —
    verified pill on top, rating WITH review count, distance, per-type prices prominent
    (₹55/L cow · ₹110/L A2), delivery window, coverage pincodes line. Bilingual section
    heading "Local vendors · உள்ளூர் விற்பனையாளர்கள்". Data: all fields already exist
    in directory/products/reviews — no field may be dropped in the restyle.
25. BRANDS AVAILABLE IN {pincode} (8f): brand cards (logo, prices, shop count) →
    "Nearest shops →" linking existing D24 brand pages (aavin/arokya/sakthi seeds);
    shop counts from covers(). Hidden when pincode has no brand presence.
26. DAIRY SERVICES (8g): tile row — Vet doctor / Cattle feed / Dairy farms / Chillers &
    equip. / Cooperatives — D17 business-category values linking existing /en/c/ pages.
    Schema-driven: adding a service category lights up a tile with zero code.

FINAL-VERSION ADDITIONS (v8 — all in the reference):
27. GUEST vs LOGGED-IN HEADER: logged-out renders a "Login" button in place of coins pill +
    bell + avatar (comment block in reference shows exact swap). Contact reveal gates with
    "Login to view contact" per existing D18 rule — do not weaken the gate.
28. LANGUAGE SWITCHER ON MOBILE: EN · த · हि visible in the mobile header (one tap, no
    burger menu burial). i18n switch = existing locale routes.
29. VOICE MIC in the pincode/search bar → routes into the D25 voice pipeline entry.
30. MY-NEED STATUS STRIP (2b): renders under header ONLY when the user has an active D25
    need — "Your need: {summary} — {n} vendors responded → View". Both-side status API.
31. CATEGORY-PARTNER BANNER (5d): D21 slot milk_category_banner surfacing on home,
    approved-only, always Sponsored-tagged. Empty → collapses.
32. ADVERTISE HOUSE BAND (8a2): inside the vendor results block (the vendor-acquisition
    position) — house creative, links advertiser wizard (M5). Config copy for ₹499/week.
33. PRICE-ALERT OPT-IN CARD (10a): D28 push permission flow; hidden once granted or
    unsupported. Never nag: dismissed = stays dismissed (local flag).
34. COINS NUDGE on reviews strip: "Write a review, earn 5 AgriCoins" — D13 ledger rule
    (5/week cap) already enforces; nudge copy from config.
35. SKELETON LOADING STATES: skeleton-card pattern (in reference as commented example +
    .skeleton CSS) for every data grid — same dimensions as loaded cards, zero CLS.
    Kitchen-sink section "skeleton-card".

BACKEND BINDING TABLE (UI section → built source; a section may NOT ship on mock data):
  Hero ad............... D21 slot milk_home_hero_xl (new slot config + house creatives)
  Search band........... existing pincode/geo context (D19/D23)
  Category bar/tiles.... D17 vertical registry schema values
  Price ticker.......... D23 price-banner query (per pincode)
  Trust row............. static i18n (content component)
  Certified products.... showcase accessor over products/media engines (seeded, TheOrganic-shaped)
  Milk-type chips....... D17 milk-type values (existing D23 filter state)
  Vendors grid.......... covers()/directory + products (per-type prices) + D18 (rating+count)
                         + coverage + delivery attrs — full card, no dropped fields;
                         M3 injection render-only restyle
  Brands available...... D24 brand pages + covers() shop counts (hide if none in pincode)
  Dairy services........ D17 business categories → existing /en/c/ routes
  Header auth state..... AgriID session (guest → Login button; D18 reveal gate)
  My-need strip......... D25 need status (active-need query, both-side status)
  Partner banner........ D21 slot milk_category_banner (approved only)
  Advertise band........ house creative → M5 advertiser wizard route; ₹ copy from config
  Price-alert card...... D28 push permission + subscription
  Coins nudge........... D13 coins rule (5/week) · copy from config
  Stats band............ cached aggregates: directory · coverage · D25 leads · analytics
  Reviews strip......... D18 reviews (approved only)
  Popular near you...... ISR city/category routes (existing)
  CTA tiles............. D25 post-need route · D16 claim flow
  App band.............. D28 PWA install prompt
  FAQ................... static i18n + FAQPage JSON-LD
  Coins pill / family... coins endpoint (D13) · config links
  Bottom nav Ask/mic.... D25 voice-first post-need route

BINDING PROOF (mandatory — "wired" must be demonstrated, not claimed):
For EVERY section in the table above, docs/ui/polish-u1.md must record: (a) the exact
endpoint / server function / query the section renders from, and (b) a mutation check —
change the underlying data in the dev DB or via the existing admin, reload, show the UI
changed. Examples of the required checks:
  · Add schema value "khoa" via D17 registry → appears in category bar + type chips, zero code
  · Edit a vendor's price/coverage in the console → home vendor card updates (after ISR window)
  · Approve a new house creative in /ads → hero carousel picks it up; set to pending → gone
  · Post + respond to a need → needs-answered stat moves (or cached window documented)
  · Approve a review in /ops → eligible for reviews strip; reject → never renders
  · Suspend a business in /ops → its card vanishes from home vendors/brands
  · Change rate-card/₹499 line via config → CTA tile + footer text update (config-driven copy)
Hardcoded arrays, inline literals standing in for DB values, or copied seed data inside
components = FAIL, even if pixels match the reference. The ONLY static content allowed:
trust row, how-it-works, FAQ (i18n content components), and config-driven strings.
Server components / existing API proxies per current app architecture — no new client-side
fetch patterns where the page already uses SSR/ISR.

INTEGRATION SURFACE: AdSlot/D21 (new slot key config only — zero engine change) · D17 schema
(category bar + tiles read values) · covers()/directory (vendor data untouched) · M3 injection
(render layer restyle only; organic order byte-identical — existing test must stay green) ·
coins endpoint (header + family strip) · D25/D16 routes (CTAs are doors, not new flows) ·
kitchen sink (every new pattern added as named section — demo and product may never disagree).
DO NOT: no API/schema/migration changes (exception: seed/config entries for slot + showcase
demo data) · no touching delivery/injection/tracking logic · no search bar in header · no
hardcoded category list · no raw hex · no new fonts · no localStorage · no third-party UI kits ·
no autoplay without prefers-reduced-motion respect.
NON-NEGOTIABLES: 1. side-by-side match: real home vs reference at 360/768/1024/1440px
(screenshots into docs/ui/polish-u1.md, before + after) · 2. Lighthouse ≥90 mobile on home
with hero carousel live · 3. TA/HI render without layout break on every section (screenshots) ·
4. existing tests green, ESPECIALLY M3 organic-order-identical and approved-creative-only ·
5. category bar never wraps at any viewport 320–1920px (test or documented manual check).
THREAT MODEL: CLS from hero/category bar (reserved boxes) · regression into delivery logic
disguised as styling (diff review: only view-layer files may change beyond tokens/seeds/config) ·
i18n gaps · kitchen-sink drift (new components missing from demo page).
DoD: gap list → build → 5 NNs green → screenshots in docs/ui/polish-u1.md → STOP. Do NOT
proceed to other pages. Present the home before/after for human approval. Same-day PR → dev:
`feat(u1): milk.in home rebuilt to approved v7 reference`.

── AFTER APPROVAL (separate sessions, same rules): U1b = remaining consumer surfaces
(city/pincode, brand, category, post-need, my-needs, search, footer sitewide) to the same
catalog; then U2 (vendor console + identity), U3 (admin) per the pack.
