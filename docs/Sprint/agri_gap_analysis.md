# Agri.in — gap analysis vs. what Indian farmers actually use most

**Additive only — nothing in the A1–A4 references, the 34-vertical registry, or the A-U1→A-U4
plan is removed or descoped by this document.** Each gap is classified P0 (cheap, before D69),
P1 (absorb into A-U2/A-U3), or P2 (post-launch backlog / registry candidates). Grounded in the
current reference kit + repo registry + a sweep of the most-used Indian agri apps and
highest-traffic farmer lookups (AgroStar, DeHaat, Plantix-class crop doctors, CHC/FARMS
machinery rental, mandi price apps, land-records portals, AgriStack).

---

## 1 · Highest-impact gaps (features farmers use constantly that we don't have yet)

### G1 · Machinery rental / Custom Hiring Centres — **P0 tile, P2 full vertical**
The single biggest miss. Govt pushes CHC/FARMS "Uber for tractors" hard; rental demand is
massive among small holders who can't buy. We show one "rent or buy" chip on a power-weeder
card but have NO rental vertical.
**Add:** registry entry `machinery-rental` (E1 directory of CHCs + rental providers, later E8
booking). P0: Soon tile in Inputs & Equipment group (35th entry — registry is data, adding is
config). P2: full surface at Stage B alongside equipment.

### G2 · Land records (Patta/Chitta/FMB, Bhulekh) — **P0 as info/links, never storage**
Among the highest-traffic rural lookups in TN and nationally. We have land *classifieds*
(Stage E) but nothing helping the daily "check my patta" need.
**Add:** E5 info page "Land records · நில ஆவணங்கள்" — plain-language guides + deep links to
official state portals (TN eServices first). We link, we never fetch or store records (DPDP +
scope). Cheap, huge SEO, fits the sarkari-links hub below.

### G3 · Sarkari links + status hub — **P0**
"PM-Kisan status", "PMFBY status", "AgriStack registration", "Soil Health Card download" are
top recurring queries. We show PM-Kisan in the Today strip but there's no one hub.
**Add:** E5 page "Govt portals & status checks" — verified deep links with last-verified
stamps (pmkisan.gov.in status, PMFBY, AgriStack farmer registry, SHC portal, eNAM
registration, state agri dept). One page, pure data, no engine work.

### G4 · Crop doctor — photo pest/disease diagnosis — **P2, safety-gated**
The defining feature of the most-installed agri apps (Plantix-class, AgroStar "Agridoctor").
Our Ask-AI is text-only and dosage answers are human-gated — correctly so.
**Add (backlog):** photo-based diagnosis as an AI-module roadmap item AFTER the D61 safety
frame ships; interim P1: seasonal pest ALERTS (E5/E6 advisory, human-written — the fall
armyworm card in the reference becomes a real content type).

### G5 · "My crops" stage-based advisory — **P2**
BharatAgri/DeHaat's retention engine: pick your crops + sowing date → stage-wise tasks and
alerts. We have generic guides.
**Add (backlog):** crop profile on AgriID (crops × acreage × sowing window) feeding
personalized advisory + notifications. Big win, needs E6 depth first.

### G6 · Calculators & tools — **P0 for 2–3, P1 rest**
Universally used, cheap, offline-friendly: seed-rate, fertilizer-dose (NPK from SHC values),
pesticide dilution, tractor EMI (exists on product page — surface it standalone), sowing-date.
**Add:** "Tools · கருவிகள்" section — P0: EMI + seed-rate + fertilizer-dose v1 as static
client-side calculators (no backend), one registry entry `tools`.

### G7 · Used equipment marketplace — **P2 registry candidate**
Used-tractor traffic rivals new-tractor traffic (TractorJunction pattern). Our Stage E
classifieds cover livestock + land but not second-hand equipment.
**Add:** registry entry `used-equipment` under Stage E classifieds (same fraud core, photos,
phone-verified posting). Natural sibling of livestock.

### G8 · MSP table + eNAM + market arrivals — **P1 (A-U2 scope, same worker)**
We show prices; farmers also check MSP (is the trader below MSP?), mandi ARRIVAL volumes
(gauge glut), and eNAM basics.
**Add to A-U2 mandi worker scope:** MSP dataset page (seasonal, source PIB/CACP + date),
arrivals quintals per market where Agmarknet provides it, MSP overlay line on price cards
("modal ₹23 · MSP ₹24.3" — the reference already hints this), eNAM guide in G3 hub.

### G9 · Multi-market price compare — **P1**
Reference shows one market per commodity. The real decision is "Coimbatore vs Pollachi vs
Tiruppur today for my tomato."
**Add to A-U2:** nearby-markets compare view on the commodity page (data already in the
worker; UI = one table). Do not change the home cards — additive drill-down.

### G10 · Rainfall, monsoon progress, dam/reservoir levels — **P1/P2**
TN farmers track Mettur level religiously; rainfall-vs-normal drives every Kharif decision.
**Add:** A-U2 weather scope gets rainfall actuals + monsoon-departure from Open-Meteo/IMD
data (P1). Dam levels (TN WRD data) = P2 exploratory — source reliability check first.

### G11 · Livestock/poultry daily-care content — **P1 content packs**
Vets (Stage C) and livestock classifieds (Stage E) exist, but the daily-use need is
vaccination schedules, feed charts, milk-yield tips — content, not directory.
**Add:** E6 seasonal packs include livestock/poultry care series (EN/TA/HI). Poultry is huge
in western TN (Namakkal) — also add registry candidates `poultry` and `fisheries` (P2,
config-only entries under an expanded Stage B/C group).

### G12 · Nurseries & saplings — **P2 registry candidate**
Horticulture saplings/nursery plants are a top purchase category (fruit saplings, vegetable
seedlings, coconut). Fits E1+E2 exactly like seeds.
**Add:** registry entry `nurseries` (Stage B sibling of seeds).

---

## 2 · Data/information gaps on surfaces we already have (all additive)

- **Mandi cards:** arrivals volume + MSP overlay (G8) · WhatsApp-share chip per price card —
  price sharing is the organic growth loop of every mandi app (P0, one button, reuses share
  primitive).
- **Weather:** sunrise/sunset (spray timing), rainfall last-7-days actual mm (P1).
- **Schemes:** documents-required list per scheme + application steps (some in reference
  copy already; make it a structured E5 field, P1) · state filter when >1 state ships.
- **Product page:** brochure/manual link field in spec-schema (P1, schema addition) · dealer
  stock-status field (P2 — needs dealer input discipline).
- **Knowledge:** video as a first-class content type in E6 (the reference's one video card →
  a `video` content kind with duration + language fields; YouTube embeds, P1). Farmer media
  consumption is video-first.
- **Helplines:** add KCC (Kisan Call Centre) top-queries FAQ links + PMFBY 72-hour
  claim-intimation notice on the insurance deadline chip (P0 copy change).
- **Offline (PWA):** cache last-fetched mandi prices + saved items alongside helplines
  (already planned; explicitly list mandi cache in A-U4 PWA parity, P1).
- **AgriStack:** farmer-registry explainer in G3 hub (P0) — becoming the gateway ID for
  scheme delivery; farmers will search it.

## 3 · Explicitly considered, deliberately NOT added (with reasoning — nothing removed)
- **Selling produce / market linkage transactions** (DeHaat/ODOP model): violates the
  founding fence — discovery and leads only, never payments/logistics. Trade leads (Stage E)
  is the compliant sibling.
- **Land-record fetching/storage:** legal + DPDP surface; links only (G2).
- **Commodity futures/speculation content:** financial-advice exposure; MSP + spot prices
  suffice.
- **In-app paid teleconsultation:** payments fence; listing + direct contact stays.
- **Electricity feeder schedules:** data availability is state-fragmented and unreliable;
  park until a stable source exists (revisit P2).

## 4 · Where each P0 lands (no plan rewrites — these slot into existing checkpoints)
- **A-U1 absorbs:** G1 Soon tile · G3 hub page (E5 static data) · G2 land-records page (same
  hub) · G6 calculators v1 (static) · WhatsApp-share chips · PMFBY 72-hr notice copy ·
  registry entries added as data (`machinery-rental`, `tools`; grid renders from registry so
  the 34→36 change is config).
- **A-U2 absorbs:** G8 MSP/arrivals · G9 compare view · G10 rainfall · G12/G11 registry
  candidate entries (Soon tiles).
- **A-U3 absorbs:** video content type · pest-alert advisory type · livestock content packs.
- **Post-launch backlog gains:** crop doctor (photo) · my-crops advisory · used-equipment ·
  poultry/fisheries/nurseries full surfaces · dam levels · feeder schedules.
