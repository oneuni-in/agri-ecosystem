# Geo snapshot provenance (Tamil Nadu, D03)

Snapshot fetched **2026-07-09**. The CSVs in this directory are the loader's
only input (`scripts/load_geo.py`); CI never touches the network.

## states.csv, districts.csv — Local Government Directory (LGD)

- Source: Government of India Local Government Directory, published on
  data.gov.in ("Local Government Directory (LGD) - States / - Districts",
  Ministry of Panchayati Raj).
  - States: https://www.data.gov.in/resource/local-government-directory-lgd-states
    (API resource `a71e60f0-a21d-43de-a6c5-fa5d21600cdb`)
  - Districts: https://www.data.gov.in/resource/local-government-directory-lgd-districts
    (API resource `37231365-78ba-44d5-ac22-3deec40b9197`)
  - Canonical directory: https://lgdirectory.gov.in
- `lgd_code` is the LGD state/district code (Tamil Nadu = 33; 38 districts).
  These codes are stable across district renames.
- `name_ta` is empty in this snapshot: LGD's "local name" field for TN
  contains uppercase English, not Tamil script. Fill from an authoritative
  Tamil source in a later pass.

### D8 update — full-India states (2026-08-16)

States extended from Tamil Nadu only to all 28 states + 8 UTs, fetched from the
same LGD resource on 2026-08-16, for the agri-colleges national corpus.
**Districts remain Tamil Nadu only** — full-India districts/blocks/villages
still load at D65. `institutions.district_id` is nullable for this reason.

data.gov.in resource `a71e60f0-a21d-43de-a6c5-fa5d21600cdb` requires a
registered API key (the public sample key returns `"Key not authorised"`),
which this environment does not have. Per the documented fallback, the
canonical directory `https://lgdirectory.gov.in/globalviewstateforcitizen.do`
was used instead: its "LGD Codes of State/UTs" table was fetched and parsed
directly from the page's HTML (`State LGD Code`, `State Name (In English)`,
`State or UT` columns) — not retyped from memory. The page's own summary
tile also states "36" entities = "28 States" + "8 Union Territories",
matching the parsed row count. `lgd_code` 33 = Tamil Nadu, State — matches
the existing row, confirming the same code space. English names are kept
verbatim as LGD spells them (e.g. "Jammu And Kashmir", "The Dadra And Nagar
Haveli And Daman And Diu"). `name_ta` stays empty for every row, same
rationale as the TN row above.

## pincodes.csv — geonames + India Post

- Base: GeoNames postal-code dataset for India (CC BY 4.0),
  https://download.geonames.org/export/zip/IN.zip — TN post offices with
  coordinates. One row per pincode; the centroid is the mean of that
  pincode's office coordinates.
- Correction layer: GeoNames' district attribution predates the 2009/2019-21
  TN district splits (Tiruppur, Tenkasi, Kallakurichi, Ranipet, Tirupathur,
  Chengalpattu, Mayiladuthurai). Pincodes belonging to those districts are
  re-attributed using the current India Post "All India Pincode Directory
  till last month" (Department of Posts),
  https://www.data.gov.in/resource/all-india-pincode-directory-till-last-month
  (API resource `5c2f62fe-5afa-4119-a499-fec9d604d5bd`), filtered per split
  district. India Post coordinates are used only for pincodes GeoNames
  lacks, and only when they fall inside the TN bounding box.
- Known limitation: district boundaries for the remaining 31 districts
  follow GeoNames; minor boundary adjustments since its snapshot may be
  misattributed. Refresh path: re-run the full India Post directory pull
  when a keyed data.gov.in account (no 10-row page cap) is available.

## pincode_population.csv — Census 2011 PCA + GeoNames (M4)

Snapshot fetched **2026-08-04**. 19,238 rows, one per Indian pincode:
`pincode,population,grade` with `grade ∈ {town, village, district_apportioned}`.
Feeds the M4 pincode-tier classifier, which ranks pincodes by population
percentile over the whole pan-India distribution — so the file deliberately
covers all of India, not just Tamil Nadu.

### Sources

- **Pincode universe + post-office place names** — GeoNames postal-code
  dataset for India, CC BY 4.0,
  https://download.geonames.org/export/zip/IN.zip (`IN.txt`, 155,570 post
  office rows over 19,238 pincodes). Supplies each pincode's place names,
  its GeoNames `admin2_code`, and its state.
- **Tamil Nadu town/village populations** — Census of India 2011, *PCA TV:
  Primary census abstract at town, village and ward level*, one direct
  `.xlsx` download per district from the Census NADA catalog (no API key):
  catalogs **6793–6824** = the 32 Census-2011 TN districts, files
  `DDW_PCA33NN_2011_MDDS with UI.xlsx` for NN = 01…32. Examples:
  - Thiruvallur (3301): https://censusindia.gov.in/nada/index.php/catalog/6793/download/9870/DDW_PCA3301_2011_MDDS%20with%20UI.xlsx
  - Coimbatore (3331): https://censusindia.gov.in/nada/index.php/catalog/6823/download/9900/DDW_PCA3331_2011_MDDS%20with%20UI.xlsx
  - Tiruppur (3332): https://censusindia.gov.in/nada/index.php/catalog/6824/download/9901/DDW_PCA3332_2011_MDDS%20with%20UI.xlsx

  (catalog id and download id both increment by 1 per district, in the
  district order 3301…3332; browse https://censusindia.gov.in/nada/index.php/catalog/6793
  and siblings for the full list.)
- **Pan-India district populations** — Census of India 2011, *PCA SD:
  Primary census abstract, India & States/UTs - State and district level*,
  NADA catalog **6191**,
  https://censusindia.gov.in/nada/index.php/catalog/6191/download/9268/DDW_PCA0000_2011_Indiastatedist.xlsx

Census material is Government of India open data (NDSAP / GODL-India);
GeoNames is CC BY 4.0. The data.gov.in catalog
"Village/Town-wise Primary Census Abstract, 2011 - TAMIL NADU" was **not**
used: it exposes no bulk download and the sample API key caps at 10 rows
per request (see the D03 note above). Census NADA was used instead — it
serves the same PCA-TV tables as direct file links.

### Method

Tamil Nadu (all 2,035 pincodes in `pincodes.csv`), per Census-2011 district:

1. Take every `TOWN`/`Urban` and `VILLAGE`/`Rural` row of the district's
   PCA-TV sheet (never `WARD`, `SUB-DISTRICT` or `DISTRICT` rows). Rows
   sharing one Town/Village code are collapsed: where out-growth rows
   (`… (M + OG) (Part)`) exist they are summed and the core `… (M)` row is
   dropped, so each person is counted once. The result reconciles to the
   sheet's own DISTRICT total exactly, for all 32 districts.
2. Normalise census unit names and GeoNames place names: lowercase, drop
   parentheticals (`(M Corp.)`, `(CT)`, `(Coimbatore)`), drop a trailing
   `H.O`/`S.O`/`B.O`, strip punctuation. A unit matches a pincode when the
   normalised census name is a leading token-run of one of that pincode's
   place names, or a whole place name is a leading token-run of the census
   name (min 5 letters). Failing that, the same comparison is retried on a
   consonant skeleton (vowels, `y`/`w`, post-consonantal `h` and doubled
   letters removed) to absorb romanisation variance — Tiruppur/Tirupur,
   Kancheepuram/Kanchipuram, Madavaram/Madhavaram. Two renames that a
   skeleton cannot bridge are aliased explicitly: Thoothukkudi→Tuticorin,
   Udhagamandalam→Ootacamund.
3. A unit matching N pincodes contributes `population / N` to each — never
   its full population to more than one pincode. A pincode that matched at
   least one town is graded `town`, else `village` if it matched a village.
4. Units that match nothing are pooled and apportioned equally over every
   pincode of the district. A census unit whose population is ≥40% of its
   district (only Chennai M Corp., which *is* Chennai district) is always
   apportioned rather than matched: a single city-wide unit carries no name
   evidence about which of the city's pincodes it covers, and matching it
   would hand the whole city to one pincode and leave the rest at zero.
5. The six post-2011 TN districts have no Census-2011 sheet of their own,
   so they are processed inside their parent district's group:
   Kallakurichi→Viluppuram, Chengalpattu→Kancheepuram, Ranipet→Vellore,
   Tirupathur→Vellore, Tenkasi→Tirunelveli, Mayiladuthurai→Nagapattinam.

Rest of India (17,203 pincodes): GeoNames `admin2_code` equals the Census
2011 all-India district code, so each district's PCA population is split
equally over its GeoNames pincodes; `grade=district_apportioned`. 400
pincodes sit in districts created after 2011 (Hapur, Morbi, Kalimpong,
Fazilka, …) or carry no `admin2_code`; those get the state PCA population
divided by the state's pincode count. Equal-split was verified to
discriminate adequately, so the post-office-count weighting held in
reserve was not needed.

Resulting grades: 759 `town`, 1,027 `village`, 249 `district_apportioned`
in TN; 17,203 `district_apportioned` elsewhere. TN rows sum to 72,147,038
against the Census TN total of 72,147,030 (per-row integer rounding).

### Known limitations

- **2011 vintage.** India has grown ~1.5%/yr since; the classifier ranks by
  percentile, so a roughly uniform undercount does not move tiers.
- **No sub-city resolution.** Census reports a municipal corporation as one
  unit, so a city's population lands on whichever of its pincodes carry the
  city name (Coimbatore, Salem, Madurai, Trichy) rather than spreading over
  every city pincode. Central pincodes therefore read high and named
  suburbs read low — directionally right for "how urban is this pincode",
  but not a residential headcount. Chennai is the extreme case: all 55 of
  its pincodes share one apportioned value.
- **Fuzzy name join.** 304 TN towns and 8,970 villages matched no pincode
  name and fell back to district apportionment; the largest are Chennai-,
  Coimbatore- and Madurai-area suburbs GeoNames does not name (Kurichi,
  Avaniapuram, Goundampalayam, Maraimalainagar).
- **Even splits.** A unit spanning several pincodes is split equally, not by
  area or households.
- **Pan-India rows are district averages.** Only Tamil Nadu is resolved to
  town/village level, so non-TN tiers are coarse. Acceptable while the
  product is TN-only; extend by pulling the PCA-TV catalogs for other
  states (same NADA pattern) when a second state launches.

### Refresh path

Re-download the three sources above, re-run the curation script (kept out
of the repo; it is a one-off, D03 style) and re-verify the discrimination
gate before committing: `641001` must stay in the top 10% of the full
distribution and the lowest-population TN pincode in the bottom 40%. When
Census 2027 PCA is published, swap the PCA-TV and PCA-SD catalogs and keep
the method unchanged.
