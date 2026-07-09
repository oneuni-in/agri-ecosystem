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
