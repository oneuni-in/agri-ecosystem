# AGRI ECOSYSTEM — DESIGN SYSTEM SPEC v1 (BINDING)
## Source of truth: docs/design-reference/preview_frontend.html (the approved mockup)
### Referenced by CLAUDE.md and SPEC D02. Claude Code sessions match THIS, not generic ShadCN defaults.

**Rule:** when the mockup and a component library default disagree, the mockup wins. When something isn't in the mockup, extend using these tokens and principles — never invent a new visual language.

---

## 1. DESIGN TOKENS (→ packages/config tailwind preset, exact values)

### 1.1 Per-site themes (switched via `data-theme` on app root)
| Token | agri.in | milk.in | organicstore.in |
|---|---|---|---|
| `--brand` | #2C6E35 | #2563A8 | #4A6B2A |
| `--brand-deep` | #1E4E26 | #174A85 | #35511C |
| `--brand-soft` | #E8F2E6 | #E9F1FA | #EFF3E4 |
| `--accent` | #E9A61C | #E9A61C | #B5541C |
| Header gradient | `linear-gradient(160deg, brand-deep, brand)` | same pattern | same pattern |

### 1.2 Shared neutrals & semantics
```
--ink:#1D2A20  --sub:#5A6A5D  --paper:#F7F8F3  --page-bg:#E9EBE2
--card:#FFFFFF --line:#E2E7DA
--call:#1E9E4A --wa:#22B45A                     (call / WhatsApp greens)
--coins-bg:#FFF3D6 --coins-fg:#8A5B00           (AgriCoins pill)
--alert-bg:#FFF6E4 --alert-line:#F0DCA8         (alert cards)
--helpband:#153A1D                              (helpline band)
Badge verified: bg #E1F3E5 / fg #156A2E
Badge sponsored: bg #FFF1D2 / fg #8A5B00
Badge cert:      bg #EAF2DC / fg #3E5A14
Rating stars fg: #C77700
```

### 1.3 Type
- Display/headings: **Bricolage Grotesque** 600/800, letter-spacing −0.02em on logo, section h2 = 20px/800
- Body: **Public Sans** 400–800, base 15px, line-height 1.5
- Vernacular fallback chain: `'Public Sans','Noto Sans Tamil','Noto Sans Devanagari',system-ui`
- `.vern` pattern: 0.78em, weight 500, opacity .85, own line — appears under EVERY category label and key CTA

### 1.4 Shape & elevation
- Radii: cards/tiles **16px** · buttons/inputs **12px** · pills **99px** · helpband/CTA tiles **18px** · icon squares **14px**
- Card: white bg, 1px `--line` border, NO shadow at rest; hover = translateY(−2px) + `0 6px 16px rgba(0,0,0,.08)`
- Searchbox: floating, `0 4px 18px rgba(0,0,0,.12)`
- Focus: 3px solid `--accent`, offset 2px (never remove)

### 1.5 Interaction minimums
- Touch targets ≥44px (mic/cam = 46px squares; action buttons ≥44px tall)
- Hover transitions ≤ .15s transform/shadow only; respect `prefers-reduced-motion`

---

## 2. COMPONENT ANATOMY (binds the 18 components of SPEC D02 to the mockup)

| SPEC D02 component | Mockup class | Must-match anatomy |
|---|---|---|
| **CategoryTile** | `.cat` | 96px min column, 16px radius, 1.5px border; 52px tinted icon square (14px radius, pastel bg per category) + 12px/700 EN label + `.vern` line; hover lift + brand border. Min-height 104px. |
| **CallButton / WhatsAppButton** | `.abtn.call / .abtn.wa` | Call = solid `--call` white text; WA = `#E6F8EC` bg, `#157A3C` text, 1.5px `#BDE8CC` border. Both flex-1, 12px radius, 800 weight, emoji-prefixed. Call/WA lead every vendor card — forms never do. |
| **Badge** | `.badge.*` | Pill, 11px/800; exact verified/sponsored/cert colors above. Sponsored is ALWAYS labeled "★ Sponsored". |
| **SearchBar (mic slot)** | `.searchbox` | White 16px-radius bar with floating shadow; 46px **accent-colored mic** (right-most) + optional cam; hint line below in white/85 on the header gradient. |
| **PincodeInput** | `.pinbox` | White 16px container, 18px/700 numeric input with .15em letter-spacing, solid brand "Find" button; GPS pill (`rgba(255,255,255,.16)` bg, white border .35) beneath. |
| **BottomNav** | `.appnav` | 5 slots, sticky bottom, white, top border + up-shadow; center **Ask AI** = 46px brand circle, raised −22px, 4px white ring, mic emoji; labels 10.5px/700. |
| **ListingCard** | `.card.lc` | Badge row → 56px tinted icon square + title 15.5px/800 + meta 12.5px (`★ rating · distance · facts`) → optional price-tag 15px/800 → action row (Call/WA/ghost). |
| **CoinsPill** | `.coins` | `--coins-bg`/`--coins-fg`, 🪙 prefix, 13px/800. Same pill on all three sites' headers. |
| **LocationPill / LangSwitcher** | `.loc-pill/.lang-pill` | Glass pills on header: `rgba(255,255,255,.16)` bg, `.3` white border, 13px/600. Lang shows "🌐 EN · த · हि". |
| **RatingStars** | `.rating` | `★ 4.7` textual pattern, #C77700, 800 — number-first, never icon-rows. |
| **Card / Modal / Toast / EmptyState / Skeleton / Button / LocationPill** | base `.card` etc. | Follow tokens §1; skeletons reserve exact final dimensions (CLS = 0). |

### Composite patterns (page-level, reused across sites)
- **Header stack:** gradient header → topbar (logo+tagline · pills · coins · avatar) → searchband. Milk.in swaps searchband for the **pincode hero** (`.pin-hero`: centered h1 clamp 22–32px, sub-line, pinbox, GPS pill).
- **"Today" strip** (`.myday`): auto-fit minmax(170px,1fr) cards; uppercase 11px/800 label row w/ emoji → 19px bold value → 12.5px sub. Alert variant uses alert colors.
- **Category groups** (`.catgroup-t`): uppercase 13px/800 sub-labels with trailing hairline; grid auto-fill minmax(96px,1fr); **all categories on the homepage, zero hamburgers**.
- **Helpline band** (`.helpband`): #153A1D, 18px radius, 34px icon + bold line + sub, right-aligned glowing call button (`0 4px 14px rgba(30,158,74,.4)`).
- **Big CTA tiles** (`.bc`): brand gradients (140deg), white text, 32px icon, glass "go" pill.
- **Type filter row** (`.tf`, milk): horizontally scrollable 86px min chips, 2px border, icon+label; active = brand border + brand-soft bg.
- **Product cards** (`.pc2`, organic): 110px tinted image area → cert badge → 13.5px/800 title → brand·rating line → full-width brand-colored "Where to buy 📍".
- **Cert trust bar** (`.certbar`): horizontal scroll cards; the "We verify every certificate" card gets gold treatment (#CBB77A border, #FFFBEE bg).
- **Eco strip** (`.eco-pill`): gradient pills linking sibling platforms.

---

## 3. THE 8 UX LAWS (from the mockup's design rationale — binding on every new screen)
1. **Icon + English + mother tongue** on every tile and key CTA.
2. **Nothing hidden** — no hamburger menus; scroll beats discovery.
3. **Voice first-class** — accent mic in search; Ask AI is the raised center nav button.
4. **Call > chat > form** — Call/WhatsApp lead every contact surface; forms are fallback.
5. **Trust visible** — verified/cert/sponsored badges everywhere; "verified N days ago" stamps; sponsored always labeled.
6. **Location does the filtering** — pincode is the universal control.
7. **Big targets, high contrast, numbers before adjectives** (₹55/L · 1.2 km · ★ 4.7).
8. **One design language across all three sites** — theme changes, anatomy never does.

---

## 4. IMPLEMENTATION NOTES FOR CLAUDE CODE SESSIONS
- Emoji icons are v1-official (they're colorful, universal, zero-load). Custom icon set is a later swap behind the CategoryTile icon prop — do not block on it.
- The mockup's inline styles become token references; NO raw hex in app code — tokens only (lint-checkable).
- Header gradients, glass pills, and hover lifts are part of the spec, not decoration — do not "simplify" them.
- Every screen not in the mockup (dashboards, admin, detail pages) is composed from these components + tokens; when unsure, the answer is "which existing pattern is closest?" not "what looks nice?"
- Visual regression: after D02, screenshot the demo route per theme; future PRs touching packages/ui compare against it.

## 5. WIRING (do this now, 10 minutes)
1. `docs/design-reference/preview_frontend.html` ← commit the approved mockup verbatim.
2. `docs/design-system.md` ← this file.
3. CLAUDE.md append: *"UI matches docs/design-system.md exactly; the mockup at docs/design-reference/preview_frontend.html is the visual source of truth. Tokens only — no raw hex in app code."*
4. SPEC D02 amendment — add to CONTEXT: *"Extract all tokens and component anatomy from docs/design-system.md §1–2; the demo route must be visually indistinguishable from the reference mockup's components."*