# AGRI.IN HUB — STRUCTURAL BLUEPRINT v2 (Engines × Verticals)

**Extends:** `Agri_in_Ecosystem_Phase1_Plan_v1.md` (architecture, stack, AgriID, AgriCoins, sprint system all stand — this doc restructures and expands the Agri.in hub itself).

**The core thesis:** you listed ~35 categories. They are NOT 35 features. They are **8 reusable engines** instantiated across **N verticals through configuration**. Build the 8 engines once, then adding "drones" or "solar pumps" or "carbon credits" is a config entry + a spec schema + seed data — a day of work, not a sprint. That's the versatile core you asked for, and it's the only way one developer covers this surface area.

```
  ENGINE (built once, in code)      VERTICAL (config + data, no code)
  ┌──────────────────────────┐      ┌────────────────────────────────┐
  │ Directory Engine         │  ×   │ seeds, fertilizers, tractors,  │
  │ Catalog Engine           │      │ drones, solar, vets, labs,     │
  │ Classifieds Engine       │      │ warehouses, FPOs, agritech...  │
  │ Matchmaking Engine       │      └────────────────────────────────┘
  │ Data/Info Engine         │            = category page, filters,
  │ Content Engine           │              spec schema, lead types,
  │ Community Engine         │              ad slots, SEO templates
  │ Booking-Inquiry Engine   │
  └──────────────────────────┘
```

---

## 1. THE EIGHT ENGINES

### E1 — Directory Engine (companies & places)
Profiles for any organization or place: identity, description, media, branches (geo: state→district→pincode→village), categories, certifications, verification badge, contact/lead buttons, reviews, claim flow, subscription tier, analytics. Already spec'd in Phase 1 — this is the workhorse. **~60% of your list is this engine.**

### E2 — Catalog Engine (products with per-vertical specs)
Products attached to companies (or standalone brand pages). The hard problem: a seed variety, a tractor, and a drone have completely different spec sheets. Solved with **admin-defined spec schemas per vertical** (see §3). Includes: media, documents (brochures/manuals PDF), certifications, variants, dealer/availability mapping, comparison (up to 4, auto-generated from spec schema), reviews, FAQs, "get quote / find dealer" lead buttons.

### E3 — Classifieds Engine (user-generated listings with lifecycle)
Individual users/farmers post listings: create → moderate → active → renew/expire → sold/closed. Fields per vertical via the same spec-schema system. Photos, price/negotiable, location, seller contact reveal (login-gated + coin/limit gated), report/flag, safety tips interstitial. **No payments, no escrow — pure discovery + contact.**

### E4 — Matchmaking Engine (two-sided intent matching)
Both sides post structured intents; system matches on category × geo × attributes; both get notified; conversation happens in platform inbox; outcome feedback closes the loop. Generalizes the leads/RFQ module from Phase 1.

### E5 — Data/Info Engine (structured reference data)
Admin/pipeline-managed structured datasets rendered as browsable, searchable, geo-filtered reference sections: each dataset = schema + records + landing templates. Powers mandi, schemes, helplines, loan/insurance product tables, certification process guides.

### E6 — Content Engine
Blog/articles, news (curated + RSS), guides, webinars & events (listing, registration, reminders, recording links), all i18n, all taggable by vertical + geo so content surfaces inside the relevant vertical pages too.

### E7 — Community Engine
Forum: categories mirroring verticals, threads, replies, Q&A mode (accepted answers), expert badges (verified consultants/vets get flair), moderation queue + report flow, coin rewards for accepted answers. Deliberately simple v1 — no groups/DMs.

### E8 — Booking-Inquiry Engine
Structured service requests with slots/availability where the provider manages a calendar-lite: soil test pickup, water test, consultation slot, warehouse space request. Request → provider confirms/rejects → status tracking → review. **Inquiry-based booking: no payment through platform.** Providers settle directly.

**Cross-cutting (already in Phase 1 plan, now with bigger jobs):** Geo service (§4), Ads (§5), Search, SEO page factory (§4.3), Notifications, Reviews, Coins hooks, Moderation queue (one unified queue across E3/E6/E7 + verifications).

---

## 2. VERTICAL REGISTRY — EVERY CATEGORY YOU NAMED, MAPPED

| # | Vertical | Engines | Custom work beyond config |
|---|---|---|---|
| 1 | Seed companies & products | E1+E2 | Spec schema: crop, variety, duration, yield, season, resistance |
| 2 | Fertilizer companies & products | E1+E2 | Spec: NPK, form, dosage/acre, crops, organic/chemical |
| 3 | Pesticides / bio-pesticides / agri chemicals | E1+E2 | Spec: target pest, active ingredient, dosage, PHI, toxicity label (color band), bio/chemical flag. **Compliance note:** display-only, CIB&RC registration no. field, "follow label" disclaimers |
| 4 | Tractors / mini / EV tractors | E1+E2 | **Custom comparison UX** (bikewale-style): HP, cylinders, lift capacity, price range, EMI calc widget, dealer locator. Highest-traffic vertical — worth extra polish |
| 5 | Rotavators, harvesters, weeders, sprayers, implements, tools, agri machinery | E1+E2 | Spec schemas per equipment family (one config each) |
| 6 | Drip irrigation & companies | E1+E2 | Spec + "get system quote" lead form (acreage, crop, water source) |
| 7 | Pumps / solar / solar pumps | E1+E2 | Spec: HP, head, phase, subsidy-eligible flag → cross-links to schemes vertical |
| 8 | Drones (agri) | E1+E2 | Spec: payload, coverage/hr, DGCA type cert; + drone-service-providers as E1 service category with per-acre pricing display |
| 9 | Soil test / water test | E1+E8 | Labs directory + booking-inquiry (sample pickup slots, test menus, report upload to user account) |
| 10 | Agritech websites & apps directory | E1 | Lightweight profile variant: platform, pricing model, category, screenshots, link-out. Pure config |
| 11 | Agri loans | E5+E1 | Loan product tables (bank/NBFC, rate, tenure, collateral, KCC etc.) + lender directory + EMI calculator + "check eligibility" lead form routed to lenders. **Display + lead-gen only, zero lending** |
| 12 | Agri consulting | E1+E8 | Consultant profiles (expertise tags, languages) + consultation booking-inquiry |
| 13 | Vet consulting | E1+E8 | Vet directory + visit/tele-consult inquiry; emergency flag; links livestock vertical |
| 14 | Insurance & crop insurance | E5+E1 | PMFBY explainer + timelines + product comparison tables + insurer/agent directory + claim-process guides. Lead routing to agents |
| 15 | Warehouses & booking | E1+E8 | Spec: capacity, storage type (cold/dry/CA), commodities, WDRA reg; space-request inquiry flow |
| 16 | Agri transportation | E1+E4 | Transporter directory + load↔vehicle matchmaking (post load / post vehicle availability) |
| 17 | Govt schemes & subsidies | E5 | **Custom UX:** eligibility-filter wizard (state, landholding, crop, category) → matching schemes, docs required, how-to-apply, deadlines, official links. High-SEO, high-trust section — human-verified, dated, sourced |
| 18 | Organic certification details | E5+E1 | Process guides (NPOP/PGS/third-party), cost/timeline tables + certification-body directory. Cross-links OrganicStore.in |
| 19 | Carbon credits info & companies | E5+E1+E6 | Explainer content + project developer/aggregator directory + "register interest" lead form |
| 20 | FPO | E1 | FPO profiles: members, commodities, licenses, produce offered → ties into import/export leads |
| 21 | Farmer helpline numbers | E5 | Simple: national + state + crop/dept-wise numbers, offline-cached page (PWA), click-to-call. Build in a day, huge goodwill |
| 22 | Mandi prices | E5 custom | Already in Phase 1 plan (Agmarknet pipeline, trends, alerts) |
| 23 | Weather | E5 custom | Already in Phase 1 plan |
| 24 | Agri news | E6 | Already in Phase 1 plan |
| 25 | Dairy related | → Milk.in | Cross-ecosystem: dairy queries on agri.in surface Milk.in cards (shared search makes this free) |
| 26 | Agri import/export leads | E4 | Buy/sell trade leads: commodity, qty, port/incoterms-lite, verification-gated contact reveal (business-verified only — fraud magnet otherwise) |
| 27 | Webinars | E6 | Events subtype: registration, reminder, recording archive |
| 28 | Cattle / sheep / livestock listings | E3 | Spec: species, breed, age, lactation/yield (dairy animals), vaccination records upload, price. Moderation-heavy; safety interstitials; **no payment ever** |
| 29 | Local agri shops / machinery shops / repair & spares | E1 | Hyperlocal directory categories; pincode-first browse; "find a mechanic near me" is a killer rural use case |
| 30 | Blog (all agri fields) | E6 | Already in plan; taxonomy expanded to all verticals |
| 31 | Discussion forum | E7 | New engine, scoped v1 |
| 32 | Agri land sale / lease | E3 custom | **Map-first UX:** acreage, soil type, water source, road access, geo pin; lease vs sale; owner/broker flag; login + phone-verified to post; legal disclaimer (platform lists, never brokers). Big moderation + fraud surface — launch late, launch careful |
| 33 | Agri labour ↔ farm matchmaking | E4 custom | **Mobile-first, low-literacy UX:** voice-note job posts, icon-heavy, vernacular-first; worker profiles (skills: harvesting/spraying/tractor-op, day rate, availability, village); farm posts (work type, days, wage, food/stay); match by distance. Sensitive: no exploitation-adjacent features, report tools, wage display mandatory |
| 34 | Land ↔ lessee matchmaking | E4 | Rides on land-lease listings + intent matching |

**Coverage check:** every category you named is in the table. "Other related fields" = future rows in the same registry — that's the point of the design.

---

## 3. THE SPEC-SCHEMA SYSTEM (what makes E2/E3 versatile)

The single mechanism that lets one Catalog Engine serve seeds AND tractors AND drones:

```
directory.vertical_registry
  slug, name_i18n, engines_enabled[], icon, parent_vertical,
  nav_placement, seo_template_id, ad_slot_config, status

catalog.spec_schemas          (one per vertical/family, versioned)
  vertical_slug, version, fields JSONB:
    [{key:"hp", label_i18n:{}, type:"number", unit:"HP",
      filterable:true, comparable:true, required:true,
      facet:"range", group:"Engine"}, ...]

catalog.products
  company_id, vertical_slug, schema_version,
  specs JSONB (validated against schema on write),
  + standard columns (name, media, price_display, status...)
```

- **Filters, comparison tables, spec sheets, and search facets are all rendered from the schema** — zero per-vertical frontend code for the standard experience.
- Validation server-side against the schema version; schema changes are additive + versioned (old products keep rendering).
- Admin UI: create vertical → define/clone spec schema → set filters/facets → set ad slots → publish. **Claude generates the first-draft spec schema for any vertical in minutes** (e.g., "generate the spec schema JSON for rotavators per this format") — you review, tweak, ship.
- JSONB + GIN indexes handle filtering at this scale fine; promote hot fields to generated columns if a vertical gets huge (tractors likely).

Same mechanism powers E3 classifieds fields (livestock schema, land schema) and E4 intent forms.

---

## 4. LOCALIZATION & GEO ARCHITECTURE (the "relevant content by location" requirement)

### 4.1 Geo backbone
`geo.states → geo.districts → geo.blocks → geo.pincodes → geo.villages` (seed from open government datasets; pincode→district mapping table; lat/lng centroids). Every business branch, listing, intent, content item, ad campaign, and data record carries geo scope at the appropriate level.

### 4.2 User location context
Resolved in priority order: user-chosen location (persisted in AgriID profile) → GPS (with permission) → pincode entry → IP fallback (state-level). One global location switcher in the header, shared across all ecosystem sites via profile. Everything reads from this one context: home feed, directory ordering (nearest branches first), mandi (nearest markets), weather, schemes (state-filtered), news (state-tagged), ads.

### 4.3 SEO page factory (organic growth engine)
Programmatic landing pages from the matrix **vertical × geo**: `/tractors/tamil-nadu/madurai`, `/soil-testing-labs/625001`, `/agri-land-for-lease/theni`. Generated via ISR from registry + geo tables, unique intro copy per page (Claude-generated at scale, human-spot-checked), structured data (LocalBusiness/Product JSON-LD), auto-sitemaps per vertical, internal-linking mesh (vertical↔geo↔content). Thin pages (zero listings) are `noindex` until populated — no thin-content penalty. **This matrix is the moat: tens of thousands of long-tail pages no one else has.**

### 4.4 Language
Location suggests default language (TN→Tamil offer), user choice wins, stored on AgriID. UI strings + spec-field labels + content all i18n'd via the systems already in the Phase 1 plan.

---

## 5. NICHE ADVERTISING (the brand-side promise)

Extends the Phase 1 ads module. Targeting dimensions: **vertical × geo (state/district/pincode) × audience role (farmer/business/all) × language**. Inventory:

1. **Vertical takeover slots** — hero + sidebar on a vertical's landing pages ("own the drones category in Maharashtra").
2. **Sponsored listings/products** — pinned rows in directory/catalog results within targeting scope, labeled "Sponsored".
3. **Contextual content slots** — in-article and in-forum-thread units matched by vertical tag.
4. **Search-adjacent** — sponsored card on relevant search results.
5. **Homepage geo slots** — the Phase 1 hero, now geo-split (different creative per state).

Self-serve dashboard flow: pick vertical(s) → geo → slot type → dates → creative upload → Razorpay pay → admin approval → live → analytics (impressions, clicks, leads attributed). Pricing model: flat-rate slots per period per scope (simple, sellable) — auctions are a Phase 3 problem. Frequency capping, share-of-voice limits per slot (max N advertisers rotating), and clear ad labeling throughout (neutrality = the brand).

---

## 6. WHERE CUSTOM BUILDS ARE GENUINELY NEEDED (budgeted, not resisted)

You're right that some categories deserve more than the template. The honest list, in priority order:

1. **Tractors & major equipment** — comparison-first UX, EMI calculator, dealer locator. (~4 extra days)
2. **Govt schemes** — eligibility wizard. (~3 days)
3. **Agri land** — map-first browse (Leaflet/MapLibre + clustering), heavy moderation tooling. (~5 days)
4. **Labour matchmaking** — low-literacy vernacular mobile UX, voice notes. (~5 days)
5. **Mandi & weather** — already custom in Phase 1 plan.
6. **Livestock** — mostly E3 config + extra moderation/safety UI. (~2 days)

Everything else: the engines carry it.

---

## 7. STAGED ROLLOUT

Phase 1 plan (60 days: AgriID, AgriCoins, shared engines E1/E2-basic/E4-leads, Agri.in hub v1, Milk.in, OrganicStore.in) **stands as Stage A**. Then:

### Stage B — Input & Equipment verticals (~Days 61–85)
- Spec-schema system full build + vertical registry + admin vertical builder (D61–66)
- SEO page factory + geo backbone completion (villages, blocks) (D67–70)
- Launch verticals 1–8 (seeds, fertilizers, pesticides, equipment families, drip, pumps/solar, drones) — config + Claude-generated schemas + seed data pipeline (D71–80)
- Tractor custom UX (comparison, EMI, dealer locator) (D81–84)
- Ads v2: vertical × niche targeting inventory (D85)
- **Gate:** 8 verticals live, 500+ companies seeded, programmatic SEO pages indexed.

### Stage C — Services & Trust verticals (~Days 86–105)
- Booking-Inquiry engine E8 (D86–89)
- Verticals 9–21: labs (soil/water), agritech directory, loans, consulting, vet, insurance, warehouses, transport, schemes (+wizard), organic cert info, carbon credits, FPO, helplines (D90–102)
- Data/Info engine hardening: dataset admin, sourcing/dating/verification workflow (D103–105)
- **Gate:** schemes wizard live, booking round-trips working, loan/insurance lead routing live.

### Stage D — Community & Content depth (~Days 106–118)
- Forum E7 (D106–110)
- Webinars/events (D111–113)
- Blog taxonomy expansion + content velocity system (Claude pipeline: 3 languages, all verticals, editorial calendar) (D114–116)
- Expert program (verified consultant/vet flair, AMA threads) (D117–118)

### Stage E — Classifieds & Matchmaking (~Days 119–140) — *deliberately last: highest fraud/moderation load, needs the trust + traffic base first*
- Classifieds engine E3 + moderation/fraud tooling (phone-verify to post, image checks, dedup, report flows) (D119–124)
- Livestock listings (D125–127)
- Land sale/lease map-first + legal framework (D128–133)
- Labour matchmaking vernacular UX (D134–139)
- Import/export trade leads (business-verified gate) (D140)

### Stage F — continuous
New verticals as registry rows, ads inventory growth, analytics products for brands, then Phase 2 ecosystem sites (Farmers.co.in, AgriMarket, etc.) which now inherit ALL engines for near-zero cost.

**Sequencing logic:** B before C because input/equipment brands are the advertisers who fund everything; C builds trust surface; D builds retention; E needs the moderation muscle and user base that B–D create.

---

## 8. THREE-AUDIENCE UX (users, brands, admin)

**Users/farmers:** location-first home (My Location strip: weather, nearest mandi, local shops, state schemes) → vertical browse → saved items/alerts (price alerts, scheme deadlines, new listings in my pincode) → one inbox (leads, bookings, forum replies) → coins everywhere. PWA, vernacular, low-data mode (image lazy/quality toggle).

**Brands/companies — one Business Console** (single dashboard regardless of vertical): listings & branches, products (schema-driven forms), leads/RFQ/booking inbox with response-time stats, ads campaign manager, subscription & invoices, analytics (views/clicks/leads by geo), verification center. A tractor dealer and a soil lab see the same console with different modules lit up — **build once**.

**Admin — one Ops Console:** vertical builder (registry + schema editor), unified moderation queue (all engines), verification queue, dataset manager (schemes/loans/helplines with source+date fields), ads approval, content studio (Claude-assisted drafting/translation built into the editor), coins rules, feature flags/kill switches, analytics.

---

## 9. THE REAL BOTTLENECK: DATA, NOT CODE (AI strategy beyond coding)

With engines built, the platform lives or dies on **seeded, accurate, localized data**. This is where Claude Max + other AI tools multiply hardest:

1. **Company/product seeding pipeline:** source lists (public directories, brand websites, govt registries like CIB&RC for pesticides, WDRA for warehouses) → Claude-assisted extraction/normalization into import CSVs → your review → bulk import → brands later claim listings (claim = the growth loop + coin reward).
2. **Spec-sheet extraction:** brochure PDFs → Claude → schema-validated product specs. Hundreds of tractors/pumps/seeds populated per week.
3. **Schemes/loans/helplines datasets:** Claude drafts from official sources with citations → you verify against source → published with "last verified" date stamps (trust marker).
4. **Content factory:** editorial calendar per vertical × season (sowing calendars, pest alerts by region/month) → Claude drafts → review → tri-language publish.
5. **SEO copy at scale:** unique geo×vertical page intros, meta, FAQs — generated, spot-checked, shipped.
6. **Moderation assist:** Claude API classification pass on classifieds/forum posts (spam/fraud/prohibited signals) → flags to your queue; you stay final arbiter.
7. **Translation memory:** maintained glossary (agri terms EN↔TA↔HI) keeps AI translations consistent across the whole platform.

Rule stays from Phase 1: AI drafts, you approve — especially anything trust-sensitive (schemes, dosages, loan terms, safety content). Pesticide dosage pages and scheme eligibility get human sign-off, always.

---

## 10. WHAT THIS CHANGES IN THE DATA MODEL (delta from Phase 1 plan)

New: `directory.vertical_registry`, `catalog.spec_schemas`, `catalog.products.specs JSONB` (replaces per-vertical taxonomy tables — supersedes the Phase 1 §5 note), `classifieds.*` (listings, moderation, reports), `match.intents` + `match.matches` (generalizing leads), `booking.*` (services, slots, requests), `forum.*`, `geo.*` full hierarchy, `data.datasets` + `data.records` (generic info-engine storage), `ads.targeting` extended (vertical, role, language). Everything else from Phase 1 stands.

---

## 11. POSITIONING (baked into product, not just pitch)

"Competitor to no one, platform for all" is a product requirement, not a tagline: agritech apps get listed (vertical #10) rather than treated as rivals; brands compete with each other *on* the platform, never *with* it; the platform never sells, lends, insures, brokers, or transports — it displays, verifies, matches, and routes. Every vertical page carries clear "platform is not the seller/provider" framing, ads are always labeled, and organic results are never pay-to-rank (paid = separate labeled slots). Neutrality is the moat that makes every brand willing to be here.

---

## 12. IMMEDIATE NEXT STEPS

1. Confirm this engine × vertical structure and the B→E stage order (or reorder verticals by your market read — the registry makes reordering free).
2. Phase 1 Sprint 3 (shared engines) absorbs one change now: build the **vertical registry + spec-schema system** in its basic form during D23–25 instead of fixed taxonomies — costs ~1 extra day in Phase 1, saves ~10 in Stage B.
3. Pick the first 3 flagship verticals for seeding depth (recommendation: **tractors, seeds, drones** — high search volume, advertiser-rich, spec-friendly).
4. On confirmation: I produce the spec-schema JSON drafts for the first 8 verticals + the Stage B work-package specs in your Claude Code prompt format.
