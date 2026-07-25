"""Normalize a raw Coimbatore-region vendor sheet into the D27 import-CSV
contract:

    python -m scripts.normalize_vendor_seed <raw.csv> --out data/seeds/coimbatore/

**No real vendor dataset exists in this repo.** Bulk data is an owner
input that arrives before D27. This script is the TOOL the owner's raw
sheet will be run through; `data/seeds/coimbatore/*.csv` currently ships
only a small (~15 row) STARTER SAMPLE - itself produced by running this
script over a sample raw sheet, not hand-typed (see
`data/seeds/coimbatore/README.md`).

Output contract (columns the D27 loader consumes - `ref` is a stable
string key joining rows across the four files; D27 mints UUIDv7 ids from
it, `ref` itself is never a database id):

    businesses.csv: ref,name,type,category_slugs,primary_pincode,
                     description_en,description_ta,description_hi
    branches.csv:   business_ref,address,state,district,pincode,lat,lng
    coverage.csv:   business_ref,pincode
    products.csv:   business_ref,vertical_slug,name,specs_json,price_display

Deliberately absent: phone/whatsapp/email columns anywhere in the output.
Contact data enters only via the D16 claim flow, so the seed is PII-free
by construction - looks_like_pii() actively rejects any row that smuggles
contact-shaped text into ANY free-text field this script emits (name,
address, state, district, description_en/ta/hi, product name,
price_display - see _PII_CHECKED_FIELDS); rejected rows are written to
rejects.csv (gitignored - see the .gitignore in data/seeds/coimbatore/,
never committed - it holds the raw PII verbatim) with a reason, never
silently dropped.

Raw input format (this script's OWN contract - there is no owner sheet
yet, so this is the mapping layer to revisit once the real sheet's
column names are known; the validation/dedupe/rejection logic below does
not change, only which raw columns feed it):

    name, type, category_slugs, primary_pincode,
    description_en, description_ta, description_hi,
    address, state, district, pincode, lat, lng, coverage_pincodes,
    vertical_slug, product_name, specs_json,
    milk_type, fat_percent, pack_size, price_display

- category_slugs / coverage_pincodes are ";"-separated.
- pincode/lat/lng default to primary_pincode's branch when blank
  (single-branch vendor); coverage_pincodes defaults to [primary_pincode].
- vertical_slug blank => no product row emitted for that business.
- specs_json, if present, is used as-is (parsed + schema-validated).
  Otherwise, for vertical_slug == "milk" (the only vertical seeded so
  far - D17), specs are built from milk_type/fat_percent/pack_size
  (fat_percent/pack_size optional, milk_type required by the schema).

Uses stdlib csv only; the geo CSV is loaded once into a dict.
"""

import argparse
import csv
import json
import re
import sys
from collections.abc import Sequence
from dataclasses import dataclass
from pathlib import Path

from modules.directory.specs import SpecValidationError, parse_fields, validate_specs

COIMBATORE_LGD = "569"

# Explicit adjacent-district allowlist: Tiruppur (split off Coimbatore
# district in 2009 and still shares 641xxx pincodes), The Nilgiris, Erode
# and Dindigul all border Coimbatore directly. Kerala neighbours (e.g.
# Palakkad) aren't in the TN-only geo CSV, so can't be validated here.
ADJACENT_LGD_CODES = frozenset({"634", "587", "573", "572"})

BUSINESS_TYPES = frozenset({"vendor", "shop", "lab", "farm"})

# Mirrors alembic/versions/0016_directory_v1.py SEED_CATEGORIES exactly.
CATEGORY_SLUGS = frozenset(
    {"farm", "dairy", "shop", "lab", "nursery", "equipment", "service", "other"}
    # D27 dairy service categories (alembic/versions/0026_dairy_categories.py)
    | {"veterinarian", "feed-supplier", "dairy-farm", "cooperative"}
)

# Mirrors alembic/versions/0018_catalog_v1.py MILK_SCHEMA_V1_FIELDS exactly.
# Duplicated rather than imported - migrations are one-shot scripts, not a
# stable import surface - but kept byte-for-byte identical so this script
# validates products.csv specs_json for real (modules.directory.specs is
# the actual runtime contract), not decoratively.
MILK_SPEC_FIELDS: list[dict[str, object]] = [
    {
        "key": "milk_type",
        "label": {"en": "Milk type", "ta": "பால் வகை", "hi": "दूध का प्रकार"},
        "type": "enum",
        "options": ["cow", "buffalo", "a2", "toned", "organic"],
        "required": True,
        "filterable": True,
        "facet": True,
        "group": "basics",
    },
    {
        "key": "fat_percent",
        "label": {"en": "Fat %", "ta": "கொழுப்பு %", "hi": "वसा %"},
        "type": "number",
        "unit": "%",
        "min": 0,
        "max": 15,
        "filterable": True,
        "comparable": True,
        "group": "nutrition",
    },
    {
        "key": "pack_size",
        "label": {"en": "Pack size", "ta": "பேக் அளவு", "hi": "पैक आकार"},
        "type": "enum",
        "options": ["250ml", "500ml", "1l", "5l", "bulk"],
        "filterable": True,
        "facet": True,
        "group": "basics",
    },
]

_EMAIL_RE = re.compile(r"[\w.+-]+@[\w-]+\.[A-Za-z]{2,}")
# Deliberately format-agnostic: rather than enumerate every separator a
# phone number might be written with (space/hyphen/dot/slash/parens/+ -
# and scraped vendor listings use all of them), match any contiguous run
# of digits-and-common-phone-punctuation, then gate on DIGIT COUNT alone
# (>=10 once separators are stripped). Counting digits is much harder to
# evade than matching a fixed set of formats - a fixed-format regex is
# exactly what let "987.654.3210" and "987/654/3210" slip through review.
# The {6,} floor is just a cheap pre-filter (a bare 6-digit pincode run
# stops here - digit count still has to clear 10 to actually flag).
_PHONE_RUN_RE = re.compile(r"[+()./\-\s\d]{6,}")
_SLUG_RE = re.compile(r"[^a-z0-9]+")

BUSINESS_FIELDS = (
    "ref",
    "name",
    "type",
    "category_slugs",
    "primary_pincode",
    "description_en",
    "description_ta",
    "description_hi",
)
BRANCH_FIELDS = ("business_ref", "address", "state", "district", "pincode", "lat", "lng")
COVERAGE_FIELDS = ("business_ref", "pincode")
PRODUCT_FIELDS = ("business_ref", "vertical_slug", "name", "specs_json", "price_display")

# Every free-text field this script emits into an output CSV, checked
# for smuggled contact info - "reject PII in ANY field" means every
# column that isn't a closed enum/structured value. state/district are
# raw pass-through text (not validated against an allowlist) so a
# careless raw sheet could smuggle contact info through them just as
# easily as through address; price_display ships verbatim into
# products.csv. Structured fields (pincodes/lat/lng/type/category_slugs)
# are intentionally excluded - they're expected to contain digits and
# would false-positive constantly.
_PII_CHECKED_FIELDS = (
    "name",
    "address",
    "state",
    "district",
    "description_en",
    "description_ta",
    "description_hi",
    "product_name",
    "price_display",
)


@dataclass(frozen=True, slots=True)
class GeoPincode:
    district_lgd_code: str
    lat: str
    lng: str


@dataclass(slots=True)
class NormalizedRecord:
    business: dict[str, str]
    branch: dict[str, str]
    coverage: list[dict[str, str]]
    products: list[dict[str, str]]


def load_geo(path: Path) -> dict[str, GeoPincode]:
    """Load pincodes.csv once into a dict keyed by pincode string."""
    geo: dict[str, GeoPincode] = {}
    with path.open(newline="", encoding="utf-8") as fh:
        for row in csv.DictReader(fh):
            geo[row["pincode"]] = GeoPincode(
                district_lgd_code=row["district_lgd_code"],
                lat=row["lat"],
                lng=row["lng"],
            )
    return geo


def looks_like_pii(value: str) -> bool:
    """True if value contains an email address or a phone-number-shaped
    run of digits (>=10 digits once separators are stripped, regardless
    of which punctuation - space/hyphen/dot/slash/parens - was used to
    format them)."""
    if not value:
        return False
    if _EMAIL_RE.search(value):
        return True
    return any(len(re.sub(r"\D", "", run)) >= 10 for run in _PHONE_RUN_RE.findall(value))


def validate_pincode(
    pincode: str,
    geo: dict[str, GeoPincode],
    *,
    home_lgd: str = COIMBATORE_LGD,
    allowed_adjacent: frozenset[str] = ADJACENT_LGD_CODES,
) -> str | None:
    """None if pincode is servicable (Coimbatore or the adjacent
    allowlist); else a machine-readable reject reason."""
    entry = geo.get(pincode)
    if entry is None:
        return "pincode_not_found"
    if entry.district_lgd_code != home_lgd and entry.district_lgd_code not in allowed_adjacent:
        return "pincode_outside_service_area"
    return None


def _make_ref(name: str, pincode: str) -> str:
    slug = _SLUG_RE.sub("-", name.lower()).strip("-")
    return f"{slug}-{pincode}"


def _build_product(
    ref: str, vertical_slug: str, raw: dict[str, str]
) -> tuple[dict[str, str] | None, str | None]:
    product_name = " ".join(raw.get("product_name", "").split())
    if not product_name:
        return None, "missing_product_name"

    raw_specs_json = raw.get("specs_json", "").strip()
    specs: dict[str, object]
    if raw_specs_json:
        try:
            specs = json.loads(raw_specs_json)
        except json.JSONDecodeError:
            return None, "invalid_specs_json"
    elif vertical_slug == "milk":
        specs = {}
        milk_type = raw.get("milk_type", "").strip().lower()
        if milk_type:
            specs["milk_type"] = milk_type
        fat_percent = raw.get("fat_percent", "").strip()
        if fat_percent:
            try:
                specs["fat_percent"] = float(fat_percent)
            except ValueError:
                return None, "invalid_fat_percent"
        pack_size = raw.get("pack_size", "").strip().lower()
        if pack_size:
            specs["pack_size"] = pack_size
    else:
        # TODO(D27): once a second vertical is seeded, give it the same
        # treatment as milk below (a *_SPEC_FIELDS constant + a
        # validate_specs() call) instead of shipping unvalidated specs.
        specs = {}

    if vertical_slug == "milk":
        try:
            validate_specs(specs, parse_fields(MILK_SPEC_FIELDS))
        except SpecValidationError as exc:
            return None, f"invalid_specs:{exc.code}:{exc.field or ''}"

    product = {
        "business_ref": ref,
        "vertical_slug": vertical_slug,
        "name": product_name,
        "specs_json": json.dumps(specs, sort_keys=True),
        "price_display": raw.get("price_display", "").strip(),
    }
    return product, None


def normalize_row(
    raw: dict[str, str],
    geo: dict[str, GeoPincode],
    *,
    valid_types: frozenset[str] = BUSINESS_TYPES,
    valid_categories: frozenset[str] = CATEGORY_SLUGS,
) -> tuple[NormalizedRecord | None, str | None]:
    """Validate + normalize one raw vendor-sheet row.

    Returns (record, None) on success or (None, reason) on rejection;
    reason is a short machine-readable code written to rejects.csv.
    """
    name = " ".join(raw.get("name", "").split())
    if not name:
        return None, "missing_name"

    text_values = {
        "name": name,
        "address": raw.get("address", ""),
        "state": raw.get("state", ""),
        "district": raw.get("district", ""),
        "description_en": raw.get("description_en", ""),
        "description_ta": raw.get("description_ta", ""),
        "description_hi": raw.get("description_hi", ""),
        "product_name": raw.get("product_name", ""),
        "price_display": raw.get("price_display", ""),
    }
    for field_name in _PII_CHECKED_FIELDS:
        if looks_like_pii(text_values[field_name]):
            return None, f"pii_detected:{field_name}"

    btype = raw.get("type", "").strip().lower()
    if btype not in valid_types:
        return None, f"invalid_type:{btype or 'blank'}"

    categories = [c.strip().lower() for c in raw.get("category_slugs", "").split(";") if c.strip()]
    if not categories:
        return None, "missing_category"
    unknown = [c for c in categories if c not in valid_categories]
    if unknown:
        return None, f"invalid_category:{','.join(unknown)}"

    primary_pincode = raw.get("primary_pincode", "").strip()
    reject = validate_pincode(primary_pincode, geo)
    if reject:
        return None, f"{reject}:primary_pincode"

    branch_pincode = raw.get("pincode", "").strip() or primary_pincode
    branch_reject = validate_pincode(branch_pincode, geo)
    if branch_reject:
        return None, f"{branch_reject}:branch_pincode"

    geo_entry = geo[branch_pincode]
    lat = raw.get("lat", "").strip() or geo_entry.lat
    lng = raw.get("lng", "").strip() or geo_entry.lng

    coverage_raw = [p.strip() for p in raw.get("coverage_pincodes", "").split(";") if p.strip()]
    coverage_pincodes = coverage_raw or [primary_pincode]
    for pin in coverage_pincodes:
        cov_reject = validate_pincode(pin, geo)
        if cov_reject:
            return None, f"{cov_reject}:coverage_pincode:{pin}"

    ref = _make_ref(name, primary_pincode)

    business = {
        "ref": ref,
        "name": name,
        "type": btype,
        "category_slugs": ";".join(categories),
        "primary_pincode": primary_pincode,
        "description_en": " ".join(raw.get("description_en", "").split()),
        "description_ta": " ".join(raw.get("description_ta", "").split()),
        "description_hi": " ".join(raw.get("description_hi", "").split()),
    }
    branch = {
        "business_ref": ref,
        "address": " ".join(raw.get("address", "").split()),
        "state": raw.get("state", "").strip() or "Tamil Nadu",
        "district": raw.get("district", "").strip() or "Coimbatore",
        "pincode": branch_pincode,
        "lat": lat,
        "lng": lng,
    }
    coverage = [{"business_ref": ref, "pincode": pin} for pin in dict.fromkeys(coverage_pincodes)]

    products: list[dict[str, str]] = []
    vertical_slug = raw.get("vertical_slug", "").strip().lower()
    if vertical_slug:
        product, reason = _build_product(ref, vertical_slug, raw)
        if reason:
            return None, reason
        assert product is not None
        products.append(product)

    return (
        NormalizedRecord(business=business, branch=branch, coverage=coverage, products=products),
        None,
    )


def dedupe(
    accepted: list[tuple[dict[str, str], NormalizedRecord]],
) -> tuple[list[NormalizedRecord], list[tuple[dict[str, str], str]]]:
    """Dedupe by (name, primary_pincode); first occurrence wins."""
    seen: set[tuple[str, str]] = set()
    kept: list[NormalizedRecord] = []
    dupes: list[tuple[dict[str, str], str]] = []
    for raw_row, record in accepted:
        key = (record.business["name"].lower(), record.business["primary_pincode"])
        if key in seen:
            dupes.append((raw_row, "duplicate"))
            continue
        seen.add(key)
        kept.append(record)
    return kept, dupes


def _write_csv(path: Path, fieldnames: Sequence[str], rows: list[dict[str, str]]) -> None:
    with path.open("w", newline="", encoding="utf-8") as fh:
        writer = csv.DictWriter(fh, fieldnames=list(fieldnames))
        writer.writeheader()
        writer.writerows(rows)


def run(raw_path: Path, out_dir: Path, geo_path: Path) -> tuple[int, int]:
    """Normalize raw_path into out_dir's four contract CSVs + rejects.csv.
    Returns (accepted_count, rejected_count)."""
    geo = load_geo(geo_path)

    accepted: list[tuple[dict[str, str], NormalizedRecord]] = []
    rejects: list[dict[str, str]] = []

    with raw_path.open(newline="", encoding="utf-8") as fh:
        reader = csv.DictReader(fh)
        raw_fieldnames = list(reader.fieldnames or [])
        for raw_row in reader:
            record, reason = normalize_row(raw_row, geo)
            if reason:
                rejects.append({**raw_row, "reject_reason": reason})
            else:
                assert record is not None
                accepted.append((raw_row, record))

    kept, dupes = dedupe(accepted)
    for raw_row, reason in dupes:
        rejects.append({**raw_row, "reject_reason": reason})

    out_dir.mkdir(parents=True, exist_ok=True)
    _write_csv(out_dir / "businesses.csv", BUSINESS_FIELDS, [r.business for r in kept])
    _write_csv(out_dir / "branches.csv", BRANCH_FIELDS, [r.branch for r in kept])
    _write_csv(out_dir / "coverage.csv", COVERAGE_FIELDS, [c for r in kept for c in r.coverage])
    _write_csv(out_dir / "products.csv", PRODUCT_FIELDS, [p for r in kept for p in r.products])
    _write_csv(out_dir / "rejects.csv", [*raw_fieldnames, "reject_reason"], rejects)

    return len(kept), len(rejects)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("raw_csv", type=Path, help="raw vendor sheet to normalize")
    parser.add_argument("--out", type=Path, required=True, help="output directory for the CSVs")
    parser.add_argument(
        "--geo",
        type=Path,
        default=Path(__file__).resolve().parents[1] / "data" / "geo" / "pincodes.csv",
        help="geo pincodes.csv to validate against (default: backend/core/data/geo/pincodes.csv)",
    )
    args = parser.parse_args(argv)
    accepted, rejected = run(args.raw_csv, args.out, args.geo)
    print(  # noqa: T201 - CLI output
        f"normalized {accepted} businesses, rejected {rejected} rows -> {args.out}"
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
