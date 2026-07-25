"""D27: dairy directory bulk-seed loader.

Loads the four D27 import-CSV contract files (see
`data/seeds/coimbatore/README.md` and `scripts/normalize_vendor_seed.py`,
which produces them) from a seed directory:

    businesses.csv: ref,name,type,category_slugs,primary_pincode,
                     description_en,description_ta,description_hi
    branches.csv:   business_ref,address,state,district,pincode,lat,lng
    coverage.csv:   business_ref,pincode
    products.csv:   business_ref,vertical_slug,name,specs_json,price_display

This module is split into two halves:

- The PURE half (this file, for now): `load_bundle()` parses the four
  CSVs and validates the full cross-file contract (exact headers, orphan
  refs, per-business branch/coverage minimums, ref/(name,primary_pincode)
  uniqueness, pincode shape, business type enum, specs_json shape,
  lat/lng parsing, description locale handling, coverage cap) with NO
  database access, collecting every violation across the whole bundle
  into a single `SeedContractError` so a ~150-row import reports every
  problem in one run instead of failing one row at a time.
- The DB-import half (Task 8, added to this same module) takes the
  `SeedBusiness` list `load_bundle()` returns and writes it to
  `directory.businesses` / `.branches` / `.business_coverage` /
  `.products`. Imported businesses land **ownerless and `claimable`**
  (D16's claim flow model: `owner_user_id IS NULL`, `verification_status
  = claimable`) - a bulk-seeded listing is not "owned" by anyone until a
  real vendor claims it. Category-slug validity against the live
  `directory.categories` table (the source of truth, not a hardcoded
  list) and product `specs_json` schema validation against the pinned
  catalog schema version are both DB-dependent and therefore also live
  in Task 8, not here.
"""

from __future__ import annotations

import csv
import json
import re
import uuid
from dataclasses import dataclass
from decimal import Decimal, InvalidOperation
from pathlib import Path
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from modules.directory import catalog_service
from modules.directory.models import Branch, Business, BusinessCategory, BusinessCoverage, Category
from modules.directory.search_sync import business_event_payload, product_event_payload
from modules.directory.service import MAX_COVERAGE_PINCODES, _free_slug, _slugify
from shared.i18n import Translated

PINCODE_RE = re.compile(r"^\d{6}$")
BUSINESS_TYPES = frozenset({"vendor", "shop", "lab", "farm"})
DESCRIPTION_LOCALES = ("en", "ta", "hi")

REQUIRED_HEADERS: dict[str, list[str]] = {
    "businesses.csv": [
        "ref",
        "name",
        "type",
        "category_slugs",
        "primary_pincode",
        "description_en",
        "description_ta",
        "description_hi",
    ],
    "branches.csv": ["business_ref", "address", "state", "district", "pincode", "lat", "lng"],
    "coverage.csv": ["business_ref", "pincode"],
    "products.csv": ["business_ref", "vertical_slug", "name", "specs_json", "price_display"],
}


class SeedContractError(Exception):
    """Raised by `load_bundle()` when the seed bundle violates the D27
    import-CSV contract. The message lists EVERY violation found across
    the whole bundle (not just the first), one per line, so a bad
    ~150-row import can be fixed in one pass instead of one row at a
    time."""


@dataclass(frozen=True, slots=True)
class SeedBranch:
    address: str
    state: str
    district: str
    pincode: str
    lat: Decimal | None
    lng: Decimal | None


@dataclass(frozen=True, slots=True)
class SeedProduct:
    vertical_slug: str
    name: str
    specs: dict[str, Any]
    price_display: str | None


@dataclass(frozen=True, slots=True)
class SeedBusiness:
    ref: str
    name: str
    type: str
    category_slugs: tuple[str, ...]
    primary_pincode: str
    description: dict[str, str]
    branches: tuple[SeedBranch, ...]
    coverage: tuple[str, ...]
    products: tuple[SeedProduct, ...]


def _read_csv(path: Path, errors: list[str]) -> list[dict[str, str]]:
    """Read one contract CSV, checking its header against
    REQUIRED_HEADERS[path.name] (order-insensitive; missing or extra
    columns are both violations). Returns [] (and appends to `errors`)
    if the file is missing or the header doesn't match, so the caller
    can keep collecting violations from the OTHER files instead of
    stopping at the first bad file."""
    required = set(REQUIRED_HEADERS[path.name])
    if not path.is_file():
        errors.append(f"{path.name}: file not found")
        return []
    with path.open(newline="", encoding="utf-8") as fh:
        reader = csv.DictReader(fh)
        header = set(reader.fieldnames or [])
        missing = required - header
        extra = header - required
        if missing:
            errors.append(f"{path.name}: missing column(s) {sorted(missing)}")
        if extra:
            errors.append(f"{path.name}: unexpected column(s) {sorted(extra)}")
        if missing or extra:
            return []
        return list(reader)


def _parse_decimal(raw: str, *, field: str, ref: str, errors: list[str]) -> Decimal | None:
    value = raw.strip()
    if not value:
        return None
    try:
        return Decimal(value)
    except InvalidOperation:
        errors.append(f"branches.csv: business_ref {ref!r} has non-numeric {field} {raw!r}")
        return None


def _parse_description(row: dict[str, str], *, ref: str, errors: list[str]) -> dict[str, str]:
    description: dict[str, str] = {}
    for locale in DESCRIPTION_LOCALES:
        value = row.get(f"description_{locale}", "").strip()
        if value:
            description[locale] = value
    if "en" not in description:
        errors.append(f"businesses.csv: business ref {ref!r} is missing required description_en")
    return description


def load_bundle(seed_dir: Path) -> list[SeedBusiness]:
    """Parse + validate the four D27 contract CSVs in `seed_dir` in one
    pass, collecting ALL violations and raising a single
    `SeedContractError` listing them if any are found (a bad ~150-row
    import must report every problem in one run, not one per run)."""
    errors: list[str] = []

    business_rows = _read_csv(seed_dir / "businesses.csv", errors)
    branch_rows = _read_csv(seed_dir / "branches.csv", errors)
    coverage_rows = _read_csv(seed_dir / "coverage.csv", errors)
    product_rows = _read_csv(seed_dir / "products.csv", errors)

    if errors:
        # Header-level problems make everything below meaningless
        # (e.g. no `ref` column at all) - fail fast on those alone.
        raise SeedContractError("\n".join(errors))

    refs = [row["ref"].strip() for row in business_rows]
    ref_set = set(refs)

    seen_refs: set[str] = set()
    seen_name_pincode: set[tuple[str, str]] = set()
    for row in business_rows:
        ref = row["ref"].strip()
        if not ref:
            errors.append("businesses.csv: row has a blank ref")
            continue
        if ref in seen_refs:
            errors.append(f"businesses.csv: duplicate ref {ref!r}")
        seen_refs.add(ref)

        name = row["name"].strip()
        primary_pincode = row["primary_pincode"].strip()
        key = (name.lower(), primary_pincode)
        if key in seen_name_pincode:
            errors.append(
                f"businesses.csv: duplicate (name, primary_pincode) {name!r}, {primary_pincode!r}"
            )
        seen_name_pincode.add(key)

        btype = row["type"].strip()
        if btype not in BUSINESS_TYPES:
            errors.append(f"businesses.csv: business ref {ref!r} has invalid type {btype!r}")

        if not PINCODE_RE.match(primary_pincode):
            errors.append(
                f"businesses.csv: business ref {ref!r} has invalid primary_pincode "
                f"{primary_pincode!r}"
            )

    # Orphan-ref checks: every business_ref in branches/coverage/products
    # must exist in businesses.csv.
    for name, rows in (
        ("branches.csv", branch_rows),
        ("coverage.csv", coverage_rows),
        ("products.csv", product_rows),
    ):
        for row in rows:
            ref = row["business_ref"].strip()
            if ref and ref not in ref_set:
                errors.append(f"{name}: orphan business_ref {ref!r} not in businesses.csv")

    branches_by_ref: dict[str, list[SeedBranch]] = {}
    for row in branch_rows:
        ref = row["business_ref"].strip()
        if not ref or ref not in ref_set:
            continue
        pincode = row["pincode"].strip()
        if not PINCODE_RE.match(pincode):
            errors.append(f"branches.csv: business_ref {ref!r} has invalid pincode {pincode!r}")
        lat = _parse_decimal(row["lat"], field="lat", ref=ref, errors=errors)
        lng = _parse_decimal(row["lng"], field="lng", ref=ref, errors=errors)
        branch = SeedBranch(
            address=row["address"].strip(),
            state=row["state"].strip(),
            district=row["district"].strip(),
            pincode=pincode,
            lat=lat,
            lng=lng,
        )
        branches_by_ref.setdefault(ref, []).append(branch)

    coverage_by_ref: dict[str, list[str]] = {}
    for row in coverage_rows:
        ref = row["business_ref"].strip()
        if not ref or ref not in ref_set:
            continue
        pincode = row["pincode"].strip()
        if not PINCODE_RE.match(pincode):
            errors.append(f"coverage.csv: business_ref {ref!r} has invalid pincode {pincode!r}")
        coverage_by_ref.setdefault(ref, []).append(pincode)

    for ref, pincodes in coverage_by_ref.items():
        if len(pincodes) > MAX_COVERAGE_PINCODES:
            errors.append(
                f"coverage.csv: business_ref {ref!r} has {len(pincodes)} coverage pincodes, "
                f"exceeds MAX_COVERAGE_PINCODES ({MAX_COVERAGE_PINCODES})"
            )

    products_by_ref: dict[str, list[SeedProduct]] = {}
    for row in product_rows:
        ref = row["business_ref"].strip()
        if not ref or ref not in ref_set:
            continue
        raw_specs = row["specs_json"].strip()
        specs: dict[str, Any] = {}
        if not raw_specs:
            # Blank is not "no specs" - the normalizer always emits a
            # populated specs_json (milk_type is a required field), so a
            # blank one reaching here can only mean corrupted/hand-edited
            # input. Same violation as unparseable JSON, not a silent {}.
            errors.append(f"products.csv: business_ref {ref!r} has blank specs_json")
        else:
            try:
                parsed = json.loads(raw_specs)
            except json.JSONDecodeError:
                errors.append(
                    f"products.csv: business_ref {ref!r} has invalid specs_json {raw_specs!r}"
                )
            else:
                if not isinstance(parsed, dict):
                    errors.append(
                        f"products.csv: business_ref {ref!r} specs_json must be a JSON object, "
                        f"got {raw_specs!r}"
                    )
                else:
                    specs = parsed
        price_display = row["price_display"].strip() or None
        product = SeedProduct(
            vertical_slug=row["vertical_slug"].strip(),
            name=row["name"].strip(),
            specs=specs,
            price_display=price_display,
        )
        products_by_ref.setdefault(ref, []).append(product)

    businesses: list[SeedBusiness] = []
    for row in business_rows:
        ref = row["ref"].strip()
        if not ref:
            continue

        description = _parse_description(row, ref=ref, errors=errors)

        branches = tuple(branches_by_ref.get(ref, ()))
        if not branches:
            errors.append(f"businesses.csv: business ref {ref!r} has no branches")

        coverage = tuple(coverage_by_ref.get(ref, ()))
        if not coverage:
            errors.append(f"businesses.csv: business ref {ref!r} has no coverage pincodes")

        category_slugs = tuple(c.strip() for c in row["category_slugs"].split(";") if c.strip())

        businesses.append(
            SeedBusiness(
                ref=ref,
                name=row["name"].strip(),
                type=row["type"].strip(),
                category_slugs=category_slugs,
                primary_pincode=row["primary_pincode"].strip(),
                description=description,
                branches=branches,
                coverage=coverage,
                products=tuple(products_by_ref.get(ref, ())),
            )
        )

    if errors:
        raise SeedContractError("\n".join(errors))

    return businesses


@dataclass(frozen=True, slots=True)
class ImportOutcome:
    ref: str
    action: str  # "created" | "skipped"
    business_id: uuid.UUID


@dataclass(frozen=True, slots=True)
class ImportReport:
    outcomes: list[ImportOutcome]
    event_payloads: list[tuple[str, dict[str, Any]]]  # (event_type, payload) - publish AFTER commit

    @property
    def created(self) -> int:
        return sum(1 for o in self.outcomes if o.action == "created")

    @property
    def skipped(self) -> int:
        return sum(1 for o in self.outcomes if o.action == "skipped")


async def import_seed(session: AsyncSession, bundle: list[SeedBusiness]) -> ImportReport:
    """Idempotent DB import of a `load_bundle()`-produced bundle. Imported
    businesses land OWNERLESS and claimable (D16: `owner_user_id IS NULL`) -
    a bulk-seeded listing is not "owned" by anyone until a real vendor
    claims it. Idempotency key is `(name, primary_pincode)` - a re-run finds
    the existing row and reports "skipped" rather than duplicating it.

    Never commits - the caller owns the commit/rollback (the D27 CLI's
    dry-run mode relies on being able to roll back after inspecting the
    report)."""
    # 1. Resolve every category slug used by the bundle in ONE query - the
    # live directory.categories table is the source of truth, not a
    # hardcoded list.
    wanted_slugs: set[str] = set()
    for seed in bundle:
        wanted_slugs.update(seed.category_slugs)
    slug_to_id: dict[str, uuid.UUID] = {}
    if wanted_slugs:
        rows = (
            await session.execute(
                select(Category.slug, Category.id).where(Category.slug.in_(wanted_slugs))
            )
        ).all()
        slug_to_id = {slug: cat_id for (slug, cat_id) in rows}
    unknown_slugs = wanted_slugs - slug_to_id.keys()
    if unknown_slugs:
        raise SeedContractError(f"unknown category slug(s): {sorted(unknown_slugs)}")

    outcomes: list[ImportOutcome] = []
    created_business_ids: list[uuid.UUID] = []
    created_product_ids: list[uuid.UUID] = []

    for seed in bundle:
        existing = await session.scalar(
            select(Business.id).where(
                Business.name == seed.name,
                Business.primary_pincode == seed.primary_pincode,
                Business.deleted_at.is_(None),
            )
        )
        if existing is not None:
            outcomes.append(ImportOutcome(ref=seed.ref, action="skipped", business_id=existing))
            continue

        business = Business(
            owner_user_id=None,  # ownerless / claimable, D16
            name=seed.name,
            slug=await _free_slug(session, _slugify(seed.name)),
            type=seed.type,
            primary_pincode=seed.primary_pincode,
            description=Translated.from_dict(seed.description) if seed.description else None,
        )
        session.add(business)
        await session.flush()
        await session.refresh(business)  # load server-side defaults (status, tier, ...)

        for branch in seed.branches:
            session.add(
                Branch(
                    business_id=business.id,
                    address=branch.address,
                    state=branch.state,
                    district=branch.district,
                    pincode=branch.pincode,
                    lat=branch.lat,
                    lng=branch.lng,
                )
            )
        for pincode in seed.coverage:
            session.add(BusinessCoverage(business_id=business.id, pincode=pincode))
        for slug in seed.category_slugs:
            session.add(BusinessCategory(business_id=business.id, category_id=slug_to_id[slug]))
        await session.flush()

        for product in seed.products:
            built = await catalog_service._build_product(
                session,
                business_id=business.id,
                vertical_slug=product.vertical_slug,
                name=product.name,
                specs=product.specs,
                price_display=product.price_display,
            )
            await catalog_service.moderate_product(session, product_id=built.id, approve=True)
            created_product_ids.append(built.id)

        created_business_ids.append(business.id)
        outcomes.append(ImportOutcome(ref=seed.ref, action="created", business_id=business.id))

    # 3. Capture fat-event payloads for CREATED rows only, AFTER flush and
    # BEFORE any commit (ORM attrs expire on commit).
    event_payloads: list[tuple[str, dict[str, Any]]] = []
    for business_id in created_business_ids:
        event_payloads.append(
            ("business.created", await business_event_payload(session, business_id))
        )
    for product_id in created_product_ids:
        event_payloads.append(("product.created", await product_event_payload(session, product_id)))

    return ImportReport(outcomes=outcomes, event_payloads=event_payloads)
