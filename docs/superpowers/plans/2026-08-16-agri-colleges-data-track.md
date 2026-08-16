# Agri colleges — data collection track (Phase 1) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Produce a validated, source-stamped CSV seed bundle covering all-India agricultural institutions, courses, scholarships, exams, counselling guides and foreign studies — plus the DB-free validator that enforces its honesty rules — with zero migration and zero app code, so it cannot collide with the parallel A-U2/A-U3/A-U4 workstreams.

**Architecture:** A pure-Python contract module (`scripts/education_seed_contract.py`) parses five CSVs into an in-memory `Bundle` and validates twelve rules, raising `SeedContractError` with *all* violations at once. A thin CLI wraps it. Geo reference data (states/districts) is read from the committed CSVs, not a database, so validation runs anywhere including CI. Data then arrives as batched, individually-validated data-only PRs.

**Tech Stack:** Python 3.12, stdlib `csv`/`json`/`dataclasses`, pytest 8, ruff (line-length 100, `T20` bans bare `print`), mypy.

**Spec:** `docs/superpowers/specs/2026-08-16-agri-colleges-design.md`

## Global Constraints

- **No row is authored from model memory.** Every data row is fetched from an official page and that URL goes in the row's `source_url` (spec §8). This is the single most important rule in this plan.
- Python `>=3.12`. Ruff line-length **100**; lint set `E,F,I,UP,B,SIM,T20`. `T20` bans `print` — CLI output needs `# noqa: T201`, as in `scripts/import_vendor_seed.py`.
- Run `ruff format` and `ruff check --fix` **per task**, not once at the end.
- **This phase adds no alembic migration and no app code.** Any task that seems to need one is a signal to stop and re-read the spec.
- Dates are ISO-8601 `YYYY-MM-DD`. Booleans are `true`/`false`. Empty cell = NULL. Files are UTF-8.
- Reserved institution slugs: `state`, `abroad`.
- Enum values are exactly as listed in spec §4 — no synonyms, no title case.
- Commit in logical units. **Do not push** until the owner says "EOD push" (per project memory); never merge a PR yourself.

---

### Task 1: Full-India states in `geo` (spec D8)

**Files:**
- Modify: `backend/core/data/geo/states.csv`
- Modify: `backend/core/data/geo/SOURCES.md`
- Modify: `backend/core/tests/test_geo.py:24`

**Interfaces:**
- Consumes: nothing.
- Produces: `data/geo/states.csv` containing all 28 states + 8 union territories with LGD `lgd_code`, consumed by Task 3's `load_geo_reference()` and by `scripts/load_geo.py` at integration time.

- [ ] **Step 1: Fetch the official LGD state list**

`data/geo/SOURCES.md` already documents the resource: data.gov.in resource `a71e60f0-a21d-43de-a6c5-fa5d21600cdb` ("Local Government Directory (LGD) - States"), canonical directory `https://lgdirectory.gov.in`.

**Trap (project memory):** data.gov.in caps responses at 10 rows unless `limit` is passed, and its filters are case-sensitive. Request with `&limit=100`.

If the API requires a key you do not have, fall back to the canonical listing at `https://lgdirectory.gov.in` and record in `SOURCES.md` which source was actually used. Do **not** type the list from memory — LGD codes are the whole point of using this source.

Cross-check: the result must be 36 rows (28 states + 8 UTs).

- [ ] **Step 2: Write `states.csv`**

Preserve the existing header and Tamil Nadu's row exactly (`lgd_code` 33; other code paths already reference it). Append the remaining 35, sorted by `lgd_code`:

```csv
lgd_code,name,name_ta
33,Tamil Nadu,
```

`name_ta` stays empty for all rows — the existing snapshot documents that LGD's local-name field for TN contains uppercase English, not Tamil script, and inventing Tamil transliterations here would violate the Global Constraint.

- [ ] **Step 3: Record provenance**

Append to `SOURCES.md` under `states.csv, districts.csv`:

```markdown
### D8 update — full-India states (2026-08-16)

States extended from Tamil Nadu only to all 28 states + 8 UTs, fetched from the
same LGD resource on 2026-08-16, for the agri-colleges national corpus.
**Districts remain Tamil Nadu only** — full-India districts/blocks/villages
still load at D65. `institutions.district_id` is nullable for this reason.
```

- [ ] **Step 4: Move the count assertion**

`backend/core/tests/test_geo.py:24` asserts `counts.states == 1`. Change it to prove what it was actually trying to prove — that the loader loads every row it was given:

```python
import csv
from pathlib import Path

def _csv_rows(path: Path) -> int:
    with path.open(encoding="utf-8") as fh:
        return sum(1 for _ in csv.DictReader(fh))

# in the test, replacing `assert counts.states == 1`:
assert counts.states == _csv_rows(data_dir / "states.csv")
```

Read the surrounding test first and match its existing fixture names for `data_dir`.

- [ ] **Step 5: Run the geo tests**

Run: `cd backend/core && python -m pytest tests/test_geo.py -v`
Expected: PASS. If the DB fixture skips (service down), that skip is visible and acceptable — the assertion change is still exercised when the service is up.

- [ ] **Step 6: Lint and commit**

```bash
cd backend/core && ruff format . && ruff check --fix .
git add backend/core/data/geo/states.csv backend/core/data/geo/SOURCES.md backend/core/tests/test_geo.py
git commit -m "feat(geo): all-India states for the colleges corpus (spec D8)

geo.states shipped TN-only at D03 with full-India geo scheduled for D65 —
after the agri launch. A national colleges corpus cannot FK into a one-row
table, so all 28 states + 8 UTs load now from the LGD source already
documented in SOURCES.md. Districts stay TN-only; district_id is nullable.

Additive and safe: every consumer resolves a state FROM a district or
pincode, and nothing enumerates all states.

test_geo's states==1 assertion is moved, not weakened — it now compares the
loaded count against the CSV row count, which is what it was proving."
```

---

### Task 2: Seed contract — bundle parsing

**Files:**
- Create: `backend/core/scripts/education_seed_contract.py`
- Create: `backend/core/tests/test_education_seed_contract.py`

**Interfaces:**
- Consumes: nothing.
- Produces:
  - `SeedContractError(Exception)` with attribute `violations: list[str]`
  - `@dataclass Bundle` with fields `institutions`, `programmes`, `institution_programmes`, `student_resources`, `guides` — each `list[dict[str, str]]`
  - `load_bundle(seed_dir: Path) -> Bundle`
  - `RESERVED_SLUGS: frozenset[str]`, `INSTITUTION_KINDS`, `TRUST_VALUES`, `INSTITUTION_STATUSES`, `PROGRAMME_LEVELS`, `DISCIPLINES`, `RESOURCE_KINDS`, `RESOURCE_CATEGORIES`, `RESOURCE_SCOPES`, `GUIDE_KINDS`

- [ ] **Step 1: Write the failing test**

```python
"""Education seed contract (spec §8) — parsing."""

from pathlib import Path

import pytest

from scripts.education_seed_contract import Bundle, SeedContractError, load_bundle


def _write(seed_dir: Path, name: str, header: str, *rows: str) -> None:
    (seed_dir / name).write_text("\n".join([header, *rows]) + "\n", encoding="utf-8")


def test_load_bundle_reads_all_five_files(tmp_path: Path) -> None:
    _write(tmp_path, "institutions.csv", "slug,name_en", "tnau,Tamil Nadu Agricultural University")
    _write(tmp_path, "programmes.csv", "slug,name_en", "bsc-agriculture,B.Sc (Hons) Agriculture")
    _write(tmp_path, "institution_programmes.csv", "institution_slug,programme_slug", "tnau,bsc-agriculture")
    _write(tmp_path, "student_resources.csv", "slug,name_en", "icar-jrf,ICAR JRF")
    _write(tmp_path, "guides.csv", "slug,title_en", "icar-counselling,ICAR counselling")

    bundle = load_bundle(tmp_path)

    assert isinstance(bundle, Bundle)
    assert bundle.institutions[0]["slug"] == "tnau"
    assert bundle.programmes[0]["name_en"] == "B.Sc (Hons) Agriculture"
    assert bundle.institution_programmes[0]["programme_slug"] == "bsc-agriculture"
    assert bundle.student_resources[0]["slug"] == "icar-jrf"
    assert bundle.guides[0]["title_en"] == "ICAR counselling"


def test_load_bundle_reports_every_missing_file_at_once(tmp_path: Path) -> None:
    _write(tmp_path, "institutions.csv", "slug,name_en", "tnau,TNAU")

    with pytest.raises(SeedContractError) as excinfo:
        load_bundle(tmp_path)

    joined = "\n".join(excinfo.value.violations)
    assert "programmes.csv" in joined
    assert "guides.csv" in joined
    # All four missing files reported in one pass, not one-at-a-time.
    assert len(excinfo.value.violations) == 4
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd backend/core && python -m pytest tests/test_education_seed_contract.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'scripts.education_seed_contract'`

- [ ] **Step 3: Write minimal implementation**

```python
"""Pure, DB-free validation of the education seed bundle (spec §8).

Imported by scripts/validate_education_seed.py and, at integration time, by
modules/education/seed_import.py. Deliberately has NO database dependency:
geo reference data is read from the committed CSVs so validation runs in CI
and on a laptop with no Postgres.
"""

from __future__ import annotations

import csv
from dataclasses import dataclass, field
from pathlib import Path

FILES = (
    "institutions.csv",
    "programmes.csv",
    "institution_programmes.csv",
    "student_resources.csv",
    "guides.csv",
)

RESERVED_SLUGS = frozenset({"state", "abroad"})

INSTITUTION_KINDS = frozenset({
    "central_agri_university",
    "state_agri_university",
    "deemed_university",
    "icar_institute",
    "private_university",
    "affiliated_college",
    "constituent_college",
    "foreign_university",
})
TRUST_VALUES = frozenset({"verified", "listed"})
INSTITUTION_STATUSES = frozenset({"active", "closed", "merged"})
PROGRAMME_LEVELS = frozenset({"diploma", "ug", "pg", "phd"})
DISCIPLINES = frozenset({
    "agriculture",
    "horticulture",
    "forestry",
    "fisheries",
    "dairy_tech",
    "agri_engineering",
    "agri_business",
    "veterinary",
})
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
    with path.open(encoding="utf-8", newline="") as fh:
        return [{k: (v or "").strip() for k, v in row.items()} for row in csv.DictReader(fh)]


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
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd backend/core && python -m pytest tests/test_education_seed_contract.py -v`
Expected: PASS (2 tests)

- [ ] **Step 5: Lint and commit**

```bash
cd backend/core && ruff format . && ruff check --fix . && python -m mypy scripts/education_seed_contract.py
git add backend/core/scripts/education_seed_contract.py backend/core/tests/test_education_seed_contract.py
git commit -m "feat(education): seed bundle parsing, DB-free (spec §8)"
```

---

### Task 3: Seed contract — the twelve rules

**Files:**
- Modify: `backend/core/scripts/education_seed_contract.py`
- Modify: `backend/core/tests/test_education_seed_contract.py`

**Interfaces:**
- Consumes: `Bundle`, `SeedContractError` and the enum frozensets from Task 2.
- Produces:
  - `load_geo_reference(geo_dir: Path) -> GeoReference` where `@dataclass GeoReference` has `states: set[str]` (lowercased names) and `districts: dict[str, set[str]]` (lowercased state name → lowercased district names)
  - `validate(bundle: Bundle, geo: GeoReference, *, today: date) -> None` — raises `SeedContractError` listing every violation

Rules are numbered exactly as in spec §8 so a violation message maps to a spec line.

- [ ] **Step 1: Write the failing tests**

```python
from datetime import date

from scripts.education_seed_contract import (
    Bundle,
    GeoReference,
    SeedContractError,
    validate,
)

TODAY = date(2026, 8, 16)
GEO = GeoReference(
    states={"tamil nadu", "punjab"},
    districts={"tamil nadu": {"coimbatore", "chennai"}},
)


def _institution(**overrides: str) -> dict[str, str]:
    row = {
        "slug": "tnau",
        "name_en": "Tamil Nadu Agricultural University",
        "kind": "state_agri_university",
        "is_government": "true",
        "parent_slug": "",
        "country_code": "IN",
        "state": "Tamil Nadu",
        "district": "Coimbatore",
        "trust": "verified",
        "status": "active",
        "merged_into_slug": "",
        "source_url": "https://tnau.ac.in/",
        "last_verified_at": "2026-08-10",
    }
    row.update(overrides)
    return row


def _violations(bundle: Bundle) -> list[str]:
    try:
        validate(bundle, GEO, today=TODAY)
    except SeedContractError as exc:
        return exc.violations
    return []


def test_valid_bundle_raises_nothing() -> None:
    assert _violations(Bundle(institutions=[_institution()])) == []


def test_rule_1_missing_source_url() -> None:
    found = _violations(Bundle(institutions=[_institution(source_url="")]))
    assert any("rule 1" in v for v in found)


def test_rule_2_verified_without_stamp_is_caught_by_rule_1() -> None:
    # Spec rule 2 (verified needs both stamps) is a strict subset of rule 1
    # (every row needs both stamps), because `listed` rows must also cite the
    # bulk list they came from. One check enforces both; rule 2 keeps its spec
    # number for traceability but has no separate branch.
    found = _violations(Bundle(institutions=[_institution(last_verified_at="")]))
    assert any("rule 1" in v for v in found)


def test_rule_3_future_stamp_rejected() -> None:
    found = _violations(Bundle(institutions=[_institution(last_verified_at="2027-01-01")]))
    assert any("rule 3" in v for v in found)


def test_rule_4_unknown_state_rejected() -> None:
    found = _violations(Bundle(institutions=[_institution(state="Atlantis", district="")]))
    assert any("rule 4" in v for v in found)


def test_rule_4_district_for_unloaded_state_rejected() -> None:
    # Punjab is a known state, but its districts have not loaded (TN-only, D8).
    found = _violations(Bundle(institutions=[_institution(state="Punjab", district="Ludhiana")]))
    assert any("rule 4" in v for v in found)


def test_rule_4_state_without_district_is_fine() -> None:
    assert _violations(Bundle(institutions=[_institution(state="Punjab", district="")])) == []


def test_rule_5_indian_row_without_state() -> None:
    found = _violations(Bundle(institutions=[_institution(state="", district="")]))
    assert any("rule 5" in v for v in found)


def test_rule_6_reserved_slug_rejected() -> None:
    found = _violations(Bundle(institutions=[_institution(slug="abroad")]))
    assert any("rule 6" in v for v in found)


def test_rule_7_duplicate_slug_rejected() -> None:
    found = _violations(Bundle(institutions=[_institution(), _institution()]))
    assert any("rule 7" in v for v in found)


def test_rule_8_dangling_parent_slug() -> None:
    found = _violations(Bundle(institutions=[_institution(parent_slug="nowhere")]))
    assert any("rule 8" in v for v in found)


def test_rule_9_merged_without_target() -> None:
    found = _violations(Bundle(institutions=[_institution(status="merged")]))
    assert any("rule 9" in v for v in found)


def test_rule_10_listed_institution_cannot_carry_numbers() -> None:
    bundle = Bundle(
        institutions=[_institution(trust="listed")],
        programmes=[{
            "slug": "bsc-agriculture",
            "name_en": "B.Sc (Hons) Agriculture",
            "level": "ug",
            "discipline": "agriculture",
            "duration_months": "48",
        }],
        institution_programmes=[{
            "institution_slug": "tnau",
            "programme_slug": "bsc-agriculture",
            "intake_seats": "120",
            "annual_fees_inr": "",
            "fee_note": "",
            "admission_route": "",
            "source_url": "https://tnau.ac.in/admissions",
            "last_verified_at": "2026-08-10",
        }],
    )
    found = _violations(bundle)
    assert any("rule 10" in v for v in found)


def test_rule_11_unknown_enum_rejected() -> None:
    found = _violations(Bundle(institutions=[_institution(kind="Agricultural University")]))
    assert any("rule 11" in v for v in found)


def test_rule_12_foreign_country_needs_foreign_kind() -> None:
    found = _violations(Bundle(institutions=[
        _institution(
            slug="wageningen",
            country_code="NL",
            state="",
            district="",
            kind="state_agri_university",
        )
    ]))
    assert any("rule 12" in v for v in found)


def test_every_violation_reported_in_one_pass() -> None:
    found = _violations(Bundle(institutions=[
        _institution(slug="abroad", source_url="", kind="nonsense")
    ]))
    assert len(found) >= 3
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd backend/core && python -m pytest tests/test_education_seed_contract.py -v`
Expected: FAIL — `ImportError: cannot import name 'GeoReference'`

- [ ] **Step 3: Implement `GeoReference` and `validate`**

Append to `scripts/education_seed_contract.py`:

```python
from datetime import date


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
    """
    url_key = "official_url" if "official_url" in row else "source_url"
    if not row.get(url_key) or not row.get("last_verified_at"):
        out.append(f"rule 1 · {where}: {url_key} and last_verified_at are both required")
        return
    parsed = _is_iso_date(row["last_verified_at"])
    if parsed is None:
        out.append(f"rule 3 · {where}: last_verified_at must be ISO-8601 (YYYY-MM-DD)")
    elif parsed > today:
        out.append(f"rule 3 · {where}: last_verified_at is in the future")


def _check_enum(value: str, allowed: frozenset[str], field_name: str, where: str, out: list[str]) -> None:
    if value and value not in allowed:
        out.append(f"rule 11 · {where}: {field_name}={value!r} is not one of {sorted(allowed)}")


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

    for row in bundle.institutions:
        where = f"institutions[{row.get('slug', '?')}]"
        _check_stamps(row, where, today, out)
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
            out.append(f"rule 12 · {where}: country_code={country} requires kind=foreign_university")

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
```

Note the `_check_stamps` helper picks `official_url` for `student_resources` and `source_url` elsewhere, matching the spec's column names per file.

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd backend/core && python -m pytest tests/test_education_seed_contract.py -v`
Expected: PASS — the 16 contract tests above plus the 2 parsing tests from Task 2

- [ ] **Step 5: Lint, type-check, commit**

```bash
cd backend/core && ruff format . && ruff check --fix . && python -m mypy scripts/education_seed_contract.py
git add backend/core/scripts/education_seed_contract.py backend/core/tests/test_education_seed_contract.py
git commit -m "feat(education): the twelve seed contract rules (spec §8)

Whole-bundle rejection with every violation reported in one pass. Rule 10 is
the load-bearing one: a \`listed\` (unverified) institution physically cannot
carry seats, fees or an admission route, so unverified national breadth can
never render a number a student might act on."
```

---

### Task 4: The validator CLI

**Files:**
- Create: `backend/core/scripts/validate_education_seed.py`
- Create: `backend/core/data/seeds/education/` (five header-only CSVs)
- Modify: `backend/core/tests/test_education_seed_contract.py`

**Interfaces:**
- Consumes: `load_bundle`, `load_geo_reference`, `validate`, `SeedContractError`.
- Produces: `_main(argv: list[str]) -> int` — 0 when the committed bundle is clean, 1 with violations printed. Every later data task's gate is this exit code.

- [ ] **Step 1: Write the failing test**

```python
from scripts.validate_education_seed import _main


def test_cli_passes_on_the_committed_bundle() -> None:
    # The committed seed bundle must ALWAYS validate — this is the gate every
    # data PR has to pass.
    assert _main([]) == 0


def test_cli_reports_violations_and_exits_nonzero(tmp_path: Path, capsys) -> None:
    for name in (
        "institutions.csv",
        "programmes.csv",
        "institution_programmes.csv",
        "student_resources.csv",
        "guides.csv",
    ):
        (tmp_path / name).write_text("slug\n", encoding="utf-8")
    (tmp_path / "institutions.csv").write_text(
        "slug,name_en,kind,country_code,state,trust,status,source_url,last_verified_at\n"
        "abroad,Nowhere,nonsense,IN,Atlantis,verified,active,,\n",
        encoding="utf-8",
    )

    assert _main(["--seed-dir", str(tmp_path)]) == 1
    printed = capsys.readouterr().out
    assert "rule 6" in printed
    assert "rule 4" in printed
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd backend/core && python -m pytest tests/test_education_seed_contract.py -v -k cli`
Expected: FAIL — `ModuleNotFoundError: No module named 'scripts.validate_education_seed'`

- [ ] **Step 3: Create the header-only seed bundle**

Create each file under `backend/core/data/seeds/education/` with exactly the spec §8 header and no rows:

```
institutions.csv:
slug,name_en,name_ta,name_hi,short_name,kind,is_government,parent_slug,country_code,state,district,pincode,lat,lng,address,website,contact_phone,contact_email,established_year,accreditation_json,trust,status,merged_into_slug,source_url,last_verified_at

programmes.csv:
slug,name_en,name_ta,name_hi,level,discipline,duration_months,description_en,description_ta,description_hi

institution_programmes.csv:
institution_slug,programme_slug,intake_seats,annual_fees_inr,fee_note,admission_route,source_url,last_verified_at

student_resources.csv:
slug,name_en,name_ta,name_hi,kind,category,scope,provider,levels,eligibility_en,eligibility_ta,eligibility_hi,benefit,applies_to_json,window_json,official_url,last_verified_at,status

guides.csv:
slug,title_en,title_ta,title_hi,kind,country_code,state,summary_en,summary_ta,summary_hi,steps_json,official_links_json,last_verified_at,status
```

- [ ] **Step 4: Write the CLI**

```python
"""Validate the committed education seed bundle against the spec §8 contract.

    cd backend/core
    python -m scripts.validate_education_seed             # the committed bundle
    python -m scripts.validate_education_seed --seed-dir /tmp/batch

Exit 0 = clean. Exit 1 = violations printed, one per line. No database is
required: geo reference data is read from data/geo/*.csv.
"""

from __future__ import annotations

import argparse
import sys
from datetime import UTC, datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from scripts.education_seed_contract import (  # noqa: E402
    SeedContractError,
    load_bundle,
    load_geo_reference,
    validate,
)

_ROOT = Path(__file__).resolve().parents[1]


def _main(argv: list[str]) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--seed-dir", type=Path, default=_ROOT / "data" / "seeds" / "education")
    parser.add_argument("--geo-dir", type=Path, default=_ROOT / "data" / "geo")
    args = parser.parse_args(argv)

    try:
        bundle = load_bundle(args.seed_dir)
        validate(
            bundle,
            load_geo_reference(args.geo_dir),
            today=datetime.now(UTC).date(),
        )
    except SeedContractError as exc:
        print(f"CONTRACT VIOLATIONS ({len(exc.violations)}) - nothing importable:")  # noqa: T201
        for violation in exc.violations:
            print(f"  {violation}")  # noqa: T201
        return 1

    print(  # noqa: T201
        f"bundle OK: {len(bundle.institutions)} institutions, "
        f"{len(bundle.programmes)} programmes, "
        f"{len(bundle.institution_programmes)} institution-programmes, "
        f"{len(bundle.student_resources)} resources, {len(bundle.guides)} guides"
    )
    return 0


def main() -> int:
    return _main(sys.argv[1:])


if __name__ == "__main__":
    raise SystemExit(main())
```

- [ ] **Step 5: Run tests to verify they pass**

Run: `cd backend/core && python -m pytest tests/test_education_seed_contract.py -v`
Expected: PASS (all tests, including both CLI tests)

Then run the CLI by hand:
Run: `cd backend/core && python -m scripts.validate_education_seed`
Expected: `bundle OK: 0 institutions, 0 programmes, 0 institution-programmes, 0 resources, 0 guides`

- [ ] **Step 6: Lint and commit**

```bash
cd backend/core && ruff format . && ruff check --fix . && python -m mypy scripts/
git add backend/core/scripts/validate_education_seed.py backend/core/data/seeds/education/ backend/core/tests/test_education_seed_contract.py
git commit -m "feat(education): seed validator CLI + empty bundle skeleton

test_cli_passes_on_the_committed_bundle is the gate every data PR must pass:
the committed bundle always validates, so a bad row cannot reach dev."
```

---

## Data collection tasks (5–10)

These produce no code. Each one's gate is identical and non-negotiable:

```bash
cd backend/core && python -m scripts.validate_education_seed && python -m pytest tests/test_education_seed_contract.py -v
```

**Every row must carry the URL it was fetched from.** If a fact cannot be found on an official page, the row ships as `listed` without that fact — it is never estimated, and never carried over from a similar institution.

Work in batches small enough to review: one commit per source or per state, never one giant commit.

### Task 5: Canonical `programmes` catalog

**Files:** Modify `backend/core/data/seeds/education/programmes.csv`

- [ ] **Step 1:** Fetch the degree-programme lists published by ICAR and two or three state agricultural universities. Take the programme *names* from those pages.
- [ ] **Step 2:** Write ~40 rows spanning `level` × `discipline`: UG (B.Sc (Hons) Agriculture, Horticulture, Forestry, Fisheries, B.Tech Agricultural Engineering, B.Tech Dairy Technology, B.V.Sc & A.H., B.Sc Sericulture, B.Sc Food Technology, B.Sc Agri Business Management), PG and PhD equivalents, and diplomas. Slugs are kebab-case (`bsc-hons-agriculture`, `btech-agri-engineering`).
- [ ] **Step 3:** Leave `name_ta` / `name_hi` empty unless an official page publishes them. Fill `duration_months` only where stated.
- [ ] **Step 4:** Run the gate. Expected: `bundle OK: 0 institutions, ~40 programmes, ...`
- [ ] **Step 5:** Commit — `data(education): canonical programme catalog from ICAR + SAU listings`

### Task 6: Tier-1 institutions — the universities

**Files:** Modify `backend/core/data/seeds/education/institutions.csv`

- [ ] **Step 1:** Fetch the ICAR accreditation listing and the UGC recognized-university list. Extract every central agricultural university, state agricultural university, ICAR deemed university and ICAR research institute.
- [ ] **Step 2:** For each, open its own site to confirm name, `established_year`, `website`, address, `state`, `district` and NAAC/ICAR accreditation. `trust=verified` only when confirmed on the institution's own page; `source_url` is that page.
- [ ] **Step 3:** `district` is filled **only for Tamil Nadu** — rule 4 rejects districts for states whose districts have not loaded. Non-TN rows carry `state` and leave `district` empty.
- [ ] **Step 4:** Run the gate after each batch of ~15 rows.
- [ ] **Step 5:** Commit per batch — `data(education): ICAR/SAU universities, batch N (verified)`

### Task 7: Tamil Nadu depth

**Files:** Modify `institutions.csv`, `institution_programmes.csv`

- [ ] **Step 1:** From TNAU's constituent and affiliated college listings, add each TN college as an institution with `parent_slug` pointing at its university and `kind` of `constituent_college` or `affiliated_college`.
- [ ] **Step 2:** For each TN college confirmed on an official page, add `institution_programmes` rows carrying `intake_seats`, `annual_fees_inr`, `fee_note` and `admission_route`, each with **its own** `source_url` + `last_verified_at` — these stamp the *fee page*, not the college page.
- [ ] **Step 3:** Any college you could not confirm stays `trust=listed` with **no** programme rows carrying numbers (rule 10 enforces this — if the validator rejects the batch, the data is wrong, not the rule).
- [ ] **Step 4:** Run the gate. **Step 5:** Commit per batch.

### Task 8: Scholarships and exams

**Files:** Modify `student_resources.csv`

- [ ] **Step 1:** Entrance (`category=entrance`): ICAR AIEEA/JRF/SRF, CUET-UG, state entrance tests — from ICAR, NTA and state authority pages.
- [ ] **Step 2:** Recruitment (`category=recruitment`): IBPS AFO, NABARD Grade A, FCI, state agriculture officer — from each body's official page. *(Owner action 3 in the spec: confirm this layer is wanted.)*
- [ ] **Step 3:** Scholarships (`kind=scholarship`, `scope=india`): ICAR, national merit, state and category schemes, from official scheme portals.
- [ ] **Step 4:** International (`scope=international`): language/aptitude tests (`category=language_test`) and agri scholarships abroad.
- [ ] **Step 5:** `window_json` carries `{"opens": ..., "closes": ..., "session": ...}` **only** when the official page states dates for a named session. An expired window is fine — it is stamped and honest; an invented one is not.
- [ ] **Step 6:** Run the gate. **Step 7:** Commit per category.

### Task 9: Counselling and foreign-study guides

**Files:** Modify `guides.csv`

- [ ] **Step 1:** `kind=counselling`: ICAR/CUET counselling and the major state authorities including Tamil Nadu. `steps_json` is an ordered array of `{"title": ..., "body": ..., "links": [...]}`, each step describing one real round or action from the authority's own information bulletin.
- [ ] **Step 2:** `kind=foreign_study`: one guide per target country (Netherlands, Australia, Germany, USA, New Zealand, Canada), covering entry requirements, tests and timelines, from official national study portals.
- [ ] **Step 3:** Anything incomplete stays `status=draft` — draft guides 404 on the public route, so an unfinished guide is invisible rather than misleading.
- [ ] **Step 4:** Run the gate. **Step 5:** Commit per guide.

### Task 10: Tier-2 breadth + foreign institutions

**Files:** Modify `institutions.csv`

- [ ] **Step 1:** From each university's own published college list, add constituent/affiliated colleges nationally as `trust=listed`, with `source_url` pointing at that list and `last_verified_at` set to the fetch date. Top up from AISHE where a university publishes no list.
- [ ] **Step 2:** Add notable agricultural universities abroad with `country_code` set and `kind=foreign_university` (rule 12 enforces the pairing), `state`/`district` empty.
- [ ] **Step 3:** Run the gate after each state or source.
- [ ] **Step 4:** Commit per source — `data(education): listed breadth, <source> (unverified tier)`
- [ ] **Step 5:** Final full-bundle run, and record the counts in the PR body.

---

## Phase 1 exit criteria

- [ ] `python -m scripts.validate_education_seed` exits 0 on the committed bundle.
- [ ] `python -m pytest tests/test_education_seed_contract.py tests/test_geo.py -v` passes.
- [ ] `ruff check .`, `ruff format --check .`, `python -m mypy scripts/` clean.
- [ ] `data/geo/states.csv` has 36 rows; `SOURCES.md` records the D8 fetch.
- [ ] Every row in every seed file has a non-empty `source_url`/`official_url` and `last_verified_at`.
- [ ] No alembic migration and no file under `apps/` or `backend/core/modules/` was touched by this phase.
- [ ] Owner has spot-checked a sample of Tier-1 rows against their `source_url` (spec owner action 4).

**Phase 2 (integration, D54–57)** is planned separately at D53, against the repo state A-U2/A-U3/A-U4 will have produced. Its content is already fixed by spec §4–§10: `education` module + migration + SELECT-only grants, `seed_import.py` reusing this contract module verbatim, the public routes, the `/colleges` surfaces, search indexing, the registry row, and the move of the 36-tile assertion.
