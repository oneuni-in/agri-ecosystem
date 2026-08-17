"""Pure, DB-free validation of the education seed bundle (spec §8).

Imported by scripts/validate_education_seed.py and, at integration time, by
modules/education/seed_import.py. Deliberately has NO database dependency:
geo reference data is read from the committed CSVs so validation runs in CI
and on a laptop with no Postgres.
"""

from __future__ import annotations

import csv
import json
import re
from dataclasses import dataclass, field
from datetime import date
from pathlib import Path

FILES = (
    "institutions.csv",
    "programmes.csv",
    "institution_programmes.csv",
    "student_resources.csv",
    "guides.csv",
)

RESERVED_SLUGS = frozenset({"state", "abroad"})

INSTITUTION_KINDS = frozenset(
    {
        "central_agri_university",
        "state_agri_university",
        "deemed_university",
        "icar_institute",
        "private_university",
        "affiliated_college",
        "constituent_college",
        "foreign_university",
    }
)
TRUST_VALUES = frozenset({"verified", "listed"})
INSTITUTION_STATUSES = frozenset({"active", "closed", "merged"})
PROGRAMME_LEVELS = frozenset({"diploma", "ug", "pg", "phd"})
DISCIPLINES = frozenset(
    {
        "agriculture",
        "horticulture",
        "forestry",
        "fisheries",
        "dairy_tech",
        "agri_engineering",
        "agri_business",
        "veterinary",
    }
)
RESOURCE_KINDS = frozenset({"scholarship", "exam"})
RESOURCE_CATEGORIES = frozenset({"entrance", "recruitment", "language_test"})
RESOURCE_SCOPES = frozenset({"india", "international"})
GUIDE_KINDS = frozenset({"counselling", "foreign_study", "general"})


class SeedContractError(Exception):
    """Raised with EVERY violation found, so one run fixes many rows."""

    def __init__(self, violations: list[str]) -> None:
        self.violations = violations
        super().__init__("\n".join(violations))


@dataclass
class Bundle:
    institutions: list[dict[str, str]] = field(default_factory=list)
    programmes: list[dict[str, str]] = field(default_factory=list)
    institution_programmes: list[dict[str, str]] = field(default_factory=list)
    student_resources: list[dict[str, str]] = field(default_factory=list)
    guides: list[dict[str, str]] = field(default_factory=list)


def _read_csv(path: Path) -> list[dict[str, str]]:
    """Read a seed CSV into row dicts.

    Hand-edited CSVs make a stray or missing comma the single likeliest
    mistake. `csv.DictReader` doesn't error on a ragged row: an over-long row
    stashes the overflow under a `None` key as a list, and an under-long row
    fills the missing fields with `None` — either way `.strip()` below would
    crash with an opaque `AttributeError`. Catch both shapes here, at the one
    place every seed file is parsed, and fail with a violation that names the
    file and row instead of a traceback.
    """
    violations: list[str] = []
    rows: list[dict[str, str]] = []
    with path.open(encoding="utf-8", newline="") as fh:
        for line_no, row in enumerate(csv.DictReader(fh), start=2):
            if None in row:
                violations.append(
                    f"structure · {path.name} row {line_no}: has more columns than the header"
                )
            elif None in row.values():
                violations.append(
                    f"structure · {path.name} row {line_no}: has fewer columns than the header"
                )
            else:
                rows.append({k: (v or "").strip() for k, v in row.items()})
    if violations:
        raise SeedContractError(violations)
    return rows


def load_bundle(seed_dir: Path) -> Bundle:
    violations = [f"missing {name}" for name in FILES if not (seed_dir / name).is_file()]
    if violations:
        raise SeedContractError(violations)
    return Bundle(
        institutions=_read_csv(seed_dir / "institutions.csv"),
        programmes=_read_csv(seed_dir / "programmes.csv"),
        institution_programmes=_read_csv(seed_dir / "institution_programmes.csv"),
        student_resources=_read_csv(seed_dir / "student_resources.csv"),
        guides=_read_csv(seed_dir / "guides.csv"),
    )


@dataclass
class GeoReference:
    """Geo lookup built from the committed CSVs — no database."""

    states: set[str]
    districts: dict[str, set[str]]


def load_geo_reference(geo_dir: Path) -> GeoReference:
    states_by_code: dict[str, str] = {}
    for row in _read_csv(geo_dir / "states.csv"):
        states_by_code[row["lgd_code"]] = row["name"].lower()
    districts: dict[str, set[str]] = {}
    for row in _read_csv(geo_dir / "districts.csv"):
        state = states_by_code.get(row["state_lgd_code"])
        if state:
            districts.setdefault(state, set()).add(row["name"].lower())
    return GeoReference(states=set(states_by_code.values()), districts=districts)


def _is_iso_date(value: str) -> date | None:
    try:
        return date.fromisoformat(value)
    except ValueError:
        return None


def _check_stamps(row: dict[str, str], where: str, today: date, out: list[str]) -> None:
    """Spec rules 1-3.

    Rule 2 (trust=verified needs both stamps) has no separate branch: it is a
    strict subset of rule 1, because `listed` rows must also cite the bulk list
    they came from. Enforcing rule 1 on every row enforces rule 2 by
    construction.

    Which column carries the citation differs by file, so it is chosen by
    column presence: `official_url` for student_resources, `source_url` for
    institutions and institution_programmes, and `official_links_json` for
    guides — whose spec §8 header deliberately has no single-URL column,
    because a counselling or foreign-study guide is assembled from an
    authority's several official pages rather than one. Rule 1 still bites
    there: a guide citing nothing is rejected exactly like a row with an empty
    `source_url`.
    """
    if "official_links_json" in row:
        raw = row.get("official_links_json", "")
        links: list[object] = []
        if raw:
            try:
                decoded = json.loads(raw)
            except ValueError:
                out.append(f"structure · {where}: official_links_json is not valid JSON")
                return
            if isinstance(decoded, list):
                links = decoded
        if not links or not row.get("last_verified_at"):
            out.append(
                f"rule 1 · {where}: official_links_json (at least one link) and "
                "last_verified_at are both required"
            )
            return
    else:
        url_key = "official_url" if "official_url" in row else "source_url"
        if not row.get(url_key) or not row.get("last_verified_at"):
            out.append(f"rule 1 · {where}: {url_key} and last_verified_at are both required")
            return
    parsed = _is_iso_date(row["last_verified_at"])
    if parsed is None:
        out.append(f"rule 3 · {where}: last_verified_at must be ISO-8601 (YYYY-MM-DD)")
    elif parsed > today:
        out.append(f"rule 3 · {where}: last_verified_at is in the future")


def _check_enum(
    value: str, allowed: frozenset[str], field_name: str, where: str, out: list[str]
) -> None:
    if value and value not in allowed:
        out.append(f"rule 11 · {where}: {field_name}={value!r} is not one of {sorted(allowed)}")


_EMAILISH = re.compile(r"^[^@\s/]+@[^@\s/]+\.[A-Za-z]{2,}$")
_DIGIT_RUN = re.compile(r"\d{7,}")


def _host(url: str) -> str:
    """Bare host of a URL, so scheme and a www. prefix don't hide a match."""
    u = (url or "").strip().lower()
    u = re.sub(r"^[a-z][a-z0-9+.-]*://", "", u)
    u = re.sub(r"^www\.", "", u)
    return u.split("/")[0].split("?")[0]


def _check_plausibility(
    row: dict[str, str], where: str, parent_sites: dict[str, str], out: list[str]
) -> None:
    """Structural sanity that the twelve spec rules do not cover.

    These are not spec rules; they are guards against classes of bad value that
    reached dev and had to be corrected afterwards, each caught by chance rather
    than by the gate:

    * an EMAIL ADDRESS in `website` -- "cdttpt.svvu@gmail.com" shipped that way;
    * a `website` identical to the row's own parent -- AISHE college records
      inherit the affiliating university's URL, and 137 rows pointed a college
      at its university's homepage;
    * a long digit run in `slug` -- a PDF parser once swallowed the next table
      column and wrote a telephone number into an immutable URL segment.

    Reported with the `structure ·` prefix, like ragged-row errors: they are
    shape problems, not violations of a numbered rule in spec section 8.
    """
    site = (row.get("website") or "").strip()
    if site and _EMAILISH.match(site):
        out.append(f"structure · {where}: website {site!r} is an email address, not a URL")

    parent = row.get("parent_slug", "")
    if site and parent:
        parent_site = parent_sites.get(parent, "")
        if parent_site and _host(site) and _host(site) == _host(parent_site):
            out.append(
                f"structure · {where}: website host {_host(site)!r} is its parent "
                f"{parent!r}'s own site, not this institution's"
            )

    digits = _DIGIT_RUN.search(row.get("slug", ""))
    if digits:
        out.append(
            f"structure · {where}: slug contains a {len(digits.group())}-digit run, "
            "which usually means a phone number leaked in from a parsed table"
        )


def validate(bundle: Bundle, geo: GeoReference, *, today: date) -> None:
    out: list[str] = []

    institution_slugs = {r.get("slug", "") for r in bundle.institutions}
    programme_slugs = {r.get("slug", "") for r in bundle.programmes}

    for name, rows in (
        ("institutions", bundle.institutions),
        ("programmes", bundle.programmes),
        ("student_resources", bundle.student_resources),
        ("guides", bundle.guides),
    ):
        seen: set[str] = set()
        for row in rows:
            slug = row.get("slug", "")
            if slug in seen:
                out.append(f"rule 7 · {name}: duplicate slug {slug!r}")
            seen.add(slug)
            if slug in RESERVED_SLUGS:
                out.append(f"rule 6 · {name}: {slug!r} is a reserved route segment")

    parent_sites = {
        r.get("slug", ""): (r.get("website") or "").strip() for r in bundle.institutions
    }

    for row in bundle.institutions:
        where = f"institutions[{row.get('slug', '?')}]"
        _check_stamps(row, where, today, out)
        _check_plausibility(row, where, parent_sites, out)
        _check_enum(row.get("kind", ""), INSTITUTION_KINDS, "kind", where, out)
        _check_enum(row.get("trust", ""), TRUST_VALUES, "trust", where, out)
        _check_enum(row.get("status", ""), INSTITUTION_STATUSES, "status", where, out)

        country = row.get("country_code", "IN") or "IN"
        state = row.get("state", "").lower()
        district = row.get("district", "").lower()
        if country == "IN":
            if not state:
                out.append(f"rule 5 · {where}: an Indian institution needs a state")
            elif state not in geo.states:
                out.append(f"rule 4 · {where}: state {row['state']!r} is not in geo.states")
            elif district and district not in geo.districts.get(state, set()):
                out.append(
                    f"rule 4 · {where}: district {row['district']!r} is not loaded for "
                    f"{row['state']!r} (districts are Tamil Nadu only until D65)"
                )
        elif row.get("kind") != "foreign_university":
            out.append(
                f"rule 12 · {where}: country_code={country} requires kind=foreign_university"
            )

        parent = row.get("parent_slug", "")
        if parent and parent not in institution_slugs:
            out.append(f"rule 8 · {where}: parent_slug {parent!r} names no institution")
        merged_into = row.get("merged_into_slug", "")
        if row.get("status") == "merged" and not merged_into:
            out.append(f"rule 9 · {where}: status=merged requires merged_into_slug")
        if merged_into and merged_into not in institution_slugs:
            out.append(f"rule 8 · {where}: merged_into_slug {merged_into!r} names no institution")

    for row in bundle.programmes:
        where = f"programmes[{row.get('slug', '?')}]"
        _check_enum(row.get("level", ""), PROGRAMME_LEVELS, "level", where, out)
        _check_enum(row.get("discipline", ""), DISCIPLINES, "discipline", where, out)

    listed = {r.get("slug", "") for r in bundle.institutions if r.get("trust") == "listed"}
    for row in bundle.institution_programmes:
        inst = row.get("institution_slug", "")
        where = f"institution_programmes[{inst}/{row.get('programme_slug', '?')}]"
        _check_stamps(row, where, today, out)
        if inst not in institution_slugs:
            out.append(f"rule 8 · {where}: institution_slug {inst!r} names no institution")
        if row.get("programme_slug", "") not in programme_slugs:
            out.append(f"rule 8 · {where}: programme_slug names no programme")
        if inst in listed and any(
            row.get(f) for f in ("intake_seats", "annual_fees_inr", "admission_route")
        ):
            out.append(
                f"rule 10 · {where}: institution is `listed` (unverified) and may not carry "
                "seats, fees or an admission route"
            )

    for row in bundle.student_resources:
        where = f"student_resources[{row.get('slug', '?')}]"
        _check_stamps(row, where, today, out)
        _check_enum(row.get("kind", ""), RESOURCE_KINDS, "kind", where, out)
        _check_enum(row.get("category", ""), RESOURCE_CATEGORIES, "category", where, out)
        _check_enum(row.get("scope", ""), RESOURCE_SCOPES, "scope", where, out)
        for level in filter(None, (row.get("levels", "") or "").split(",")):
            _check_enum(level.strip(), PROGRAMME_LEVELS, "levels", where, out)

    for row in bundle.guides:
        where = f"guides[{row.get('slug', '?')}]"
        _check_stamps(row, where, today, out)
        _check_enum(row.get("kind", ""), GUIDE_KINDS, "kind", where, out)

    if out:
        raise SeedContractError(out)
