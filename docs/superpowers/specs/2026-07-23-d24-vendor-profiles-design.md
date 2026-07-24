 # D24 — Vendor Profiles + Tracked Contact + Map (design)

Date: 2026-07-23 · Branch: `feat/d24-vendor-profiles` · PR → dev: `feat(d24): vendor profiles`
Source spec: `docs/Sprint/sprint3_D23-D32.md` (SPEC D24).

## Scope decisions (approved)

1. **Profile page lives in web-milk** at `apps/web-milk/app/directory/businesses/[slug]/` —
   matches the canonical URLs D23 JSON-LD already emits (`https://milk.in/directory/businesses/{slug}`).
   Web-agri's generic business page is untouched.
2. **Map data**: extend `covers()` to return the nearest geocoded branch's `lat`/`lng` per item —
   no new endpoint. Existing SecureRouter rate limit + keyset pagination remain the anti-scraping defence.
3. **Delivery windows**: rendered from `Branch.hours` JSONB (+ product spec free text). Structured
   delivery-window schema is deferred until vendors can edit it (would be a milk SpecSchema bump, D17
   append-only-by-grant machinery).
4. **Map placement**: on the existing `/{pincode}` page, lazy-loaded. SSR list stays the LCP; MapLibre
   mounts client-side only on toggle / scroll-into-view.

## Backend changes (`backend/core`) — additive only

### B1. covers() coordinates
- `modules/directory/covers.py`: SQL also selects the lat/lng of the branch that produced the
  MIN-distance (nullable; businesses located via pincode-centroid fallback get `NULL` → list-only,
  not plotted).
- `CoversItem` / `CoversItemOut` gain `lat: float | None`, `lng: float | None`.
- `modules/directory/milk_home.py` propagates them onto `MilkCard`.
- Cursor format unchanged (still `(distance_m, id)`).

### B2. Reveal attribution (spec B)
- `reveal_branch_contact()` (`modules/directory/router.py`) additionally records a lead
  `Inquiry(type="contact", business_id=<revealed business>, pincode=<branch.pincode>,
  from_user_id=<caller>, payload={"source": "contact_reveal"})` via a new internal
  `leads_service.record_reveal_inquiry()`.
  - Direct insert — does **not** go through `route_inquiry()` coverage validation (the business is
    already known; its branch pincode may legitimately be outside its coverage list).
  - **Deduped per (user, business, UTC day)**: repeat reveals do not create more inquiries, so vendor
    inboxes are not spammed.
  - Emits `lead.created` (existing owner-guard applies) → vendor response stats attribute
    reveal-driven contacts.
- D18 invariants untouched: cap → ContactReveal log → numbers order; `claim_reveal_slot` unchanged;
  structured logs and `leads.contact_reveals` still carry IDs only, never phone numbers.

### B3. Public coverage pincodes
- `BusinessDetailOut` gains `coverage_pincodes: list[str]` (from `directory.business_coverage`).
  Non-PII; needed for the profile's coverage section.

## Frontend changes (`apps/web-milk`)

### F1. Vendor profile page (SSR/ISR, `revalidate = 300`)
- `app/directory/businesses/[slug]/page.tsx` server-fetches:
  `GET /directory/businesses/{slug}`, `GET /catalog/businesses/{slug}/products`,
  `GET /reviews?target_type=business&target_id=…`, `GET /reviews/summary`.
- Sections: header (name, type, `<Badge variant="verified">` when `verification_status === "verified"`),
  milk products (D17 specs + `price_display`), coverage pincodes, delivery windows from `Branch.hours`,
  reviews (read + login-gated write), tracked contact block, guest lead-form fallback.
- SEO: LocalBusiness JSON-LD with `aggregateRating` (web-agri `businessJsonLd` pattern, `<`-escaped);
  `buildMetadata` + `canonicalUrl` from `@agri/ui/seo`; 404/thin pages `noindex`.

### F2. Tracked contact + reviews (ported app-local from web-agri, per repo convention)
- `reveal-contact.tsx`: `useAgriUser` gate → guest login CTA; authed →
  `POST /api/directory/branches/{id}/reveal`; 429 → "daily limit reached"; success →
  `CallButton`/`WhatsAppButton` (`@agri/ui`) with `tel:` / `wa.me` hrefs.
- `lead-form.tsx`: guest-capable `POST /api/leads/inquiries` `type="contact"`.
- `review-form.tsx` + `reviews-section.tsx`: pending-moderation messaging, 409 already-reviewed.
- New BFF proxies in web-milk (copies of web-agri's token-attaching, path-traversal-guarded routes):
  `app/api/directory/[...path]/route.ts`, `app/api/leads/[...path]/route.ts`,
  `app/api/reviews/[[...path]]/route.ts`.
- D23 vendor cards: inert Call/WhatsApp `<span>`s become links to the profile page.

### F3. Map + list sync on `/{pincode}`
- `maplibre-gl` added to web-milk only.
- Vendor list becomes a client island receiving serialized `MilkCard[]` from the SSR page
  (server-rendered HTML remains the LCP).
- `vendor-map.tsx` via `next/dynamic({ ssr: false })`, mounted only when the user toggles map view or
  it scrolls into view — MapLibre JS never blocks the audited initial load.
- Pins from card `lat`/`lng` (null-coord vendors are list-only). Clustering via MapLibre's built-in
  GeoJSON `cluster: true` (no extra dependency).
- Sync: pin click → scroll + highlight card; card click → `flyTo` + highlight pin. Order stays
  distance-sorted (covers order).

## Tests / gates (DoD)

- **Backend pytest**: covers items carry lat/lng (and NULL fallback); reveal creates exactly one
  deduped contact inquiry per user/business/day; reveal path emits no plaintext phone in logs or
  `leads.contact_reveals` (extends D18 suite) — non-negotiable 1.
- **E2E** (`e2e/`, web-milk already in Playwright config):
  - `vendor-profile.spec.ts`: JSON-LD `<script>` parses; required LocalBusiness fields present
    (non-negotiable 2); guest sees login CTA on reveal; lead form submits.
  - `map-sync.spec.ts`: pin↔card selection sync both directions (non-negotiable 3).
- **Lighthouse** (non-negotiable 4): CI's lhci run has no backend, so the SSR profile page cannot be
  added to `scripts/lhci-affected.mjs` (same constraint D23 hit). Verified ≥90 locally with the
  backend running; result recorded in the PR. CI's existing checks unchanged.
- CI hygiene: `public_routes.txt` unchanged (no new public routes); mypy + lint-imports locally
  before push; conventional-commit PR title.

## Non-goals

- No structured delivery-window schema (deferred; needs vendor editing UX + SpecSchema bump).
- No new public endpoints; no changes to reveal caps or logging semantics.
- No Google Maps JS; no map on web-agri; no shared profile component in `@agri/ui`.
