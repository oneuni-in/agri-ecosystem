# M1 — Dairy Taxonomy + Verified-First + Onboarding CTA — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Expand Milk.in from three milk spec fields to the full 13-value dairy taxonomy held entirely as D17 schema config, surface it on the home page and auto-generated category pages, rank verified businesses first in every organic listing, and link brands to the existing Business Console.

**Architecture:** The taxonomy is a `category` enum field on a new milk spec-schema **version 2**, with per-option i18n labels and icon keys carried in the same `fields` JSONB via a new optional `option_meta` block on `FieldDef`. Nothing about product validation changes. `covers()` gains a leading `verified_rank` sort key (cursor widens 3 → 4 fields) and every consumer inherits it. The frontend reads the taxonomy from a newly-public schema endpoint, renders labels from the schema and icons from a key→emoji map with a fallback, so a value added later needs no code.

**Tech Stack:** Python 3.12 · FastAPI · SQLAlchemy 2 async · Alembic · Postgres 16 · pytest · Next.js 15 (App Router, RSC) · next-intl · Tailwind 3 · vitest · Playwright · pnpm 11 / Node 24.

## Global Constraints

Copied verbatim from `docs/Sprint/sprint3.5_M1-M6_milk_monetization.md` and `CLAUDE.md`. Every task's requirements implicitly include this section.

- **NO hardcoded category list anywhere.** The schema is the only source of the value set.
- **No new tables.** Migration 0029 inserts rows and updates existing ones only.
- **No retro-refactor of shipped components.** All new frontend code is atomic: `components/{atoms,molecules,organisms}`.
- **No "Recommended" label anywhere in this spec.** That is M3's rule and M3's ranking function.
- **No search index rebuild.** No change to `INDEX_SETTINGS` / `SORTABLE_ATTRIBUTES`.
- **Constitution:** SecureRouter on every route · `owned_by()` for ownership · UUIDv7 IDs · append-only ledgers · cursor pagination (OFFSET is banned by a test gate) · schema-driven config · tokens only, no raw hex in app code · Lighthouse ≥ 90 gate.
- **Git:** never commit to `main` or `dev`. Work happens on `feat/m1-taxonomy-verified` (already created, based at `dev`). Conventional commits. PR targets `dev`, never `main`.
- **`git status` zero AM before every commit.**
- **Public routes:** adding one requires a `backend/core/public_routes.txt` line in the same PR (CI diffs the file against the live registry).
- **Migrations:** every migration needs a `# -- THREAT/NOTES:` block covering downgrade data loss, locks, and rollout — a test gate enforces this.
- **i18n:** every user-visible string ships EN + TA + HI. New terms go in `docs/i18n-glossary.md`.
- **Module CLAUDE.md files are GENERATED** — edit `backend/core/scripts/gen_module_claude.py` and rerun, never hand-edit.

### Reference: the 13 category values

Used verbatim in Tasks 2, 7 and 8. Values are URL-safe slugs because they are the `/p/{value}` route segment.

| value | en | ta | hi | icon key | emoji |
|---|---|---|---|---|---|
| `milk` | Milk | பால் | दूध | `milk` | 🥛 |
| `ghee` | Ghee | நெய் | घी | `ghee` | 🍯 |
| `paneer` | Paneer | பன்னீர் | पनीर | `paneer` | 🧀 |
| `milk-powder` | Milk Powder | பால் பொடி | दूध पाउडर | `milk-powder` | 🥄 |
| `yogurt` | Yogurt | யோகர்ட் | योगर्ट | `yogurt` | 🍶 |
| `lassi` | Lassi | லஸ்சி | लस्सी | `lassi` | 🧋 |
| `curd` | Curd | தயிர் | दही | `curd` | 🍚 |
| `buttermilk` | Buttermilk | மோர் | छाछ | `buttermilk` | 🥤 |
| `cheese` | Cheese | சீஸ் | चीज़ | `cheese` | 🫕 |
| `butter` | Butter | வெண்ணெய் | मक्खन | `butter` | 🧈 |
| `cream` | Cream | கிரீம் | क्रीम | `cream` | 🍦 |
| `khoa` | Khoa | கோவா | खोया | `khoa` | 🍥 |
| `flavoured-milk` | Flavoured Milk | சுவையூட்டப்பட்ட பால் | फ्लेवर्ड दूध | `flavoured-milk` | 🍫 |

New `milk_type` option added in v2: `mixed` — Mixed / கலப்பு பால் / मिश्रित दूध.

Every emoji above is Unicode ≤ 13.0, chosen deliberately: rural Android devices render older emoji sets, and a newer glyph shows as tofu (▯). Do not substitute Unicode 14+ emoji (e.g. 🫙 🫗).

---

## File Structure

**Backend — created**

| File | Responsibility |
|---|---|
| `backend/core/alembic/versions/0029_milk_schema_v2.py` | Publish milk schema v2; backfill existing products onto it |
| `backend/core/tests/test_specs_option_meta.py` | `option_meta` parse + reject rules |
| `backend/core/tests/test_covers_verified_first.py` | NN#2 — ordering + cursor across the verified boundary |
| `backend/core/tests/test_milk_schema_v2_migration.py` | v2 contents + backfill correctness |
| `backend/core/tests/test_taxonomy_zero_code.py` | NN#1 backend half |
| `backend/core/tests/test_milk_home_categories.py` | `product_category` filter + `product_categories` + banner narrowing |
| `backend/core/tests/test_catalog_one_vs_all.py` | NN#3 — 1-product and 13-product brands |
| `backend/core/tests/test_search_verified_rerank.py` | D19 re-rank hook |

**Backend — modified**

| File | Change |
|---|---|
| `modules/directory/specs.py` | `OptionMeta` model + `FieldDef.option_meta` + cross-checks |
| `modules/directory/covers.py` | `_VERIFIED_RANK`, 4-field cursor, order + keyset predicate |
| `modules/directory/milk_home.py` | `_product_category_keys()`, `product_category` param, banner narrowing |
| `modules/directory/milk_home_schemas.py` | `product_categories` on `MilkHomeOut`, `category` on `MilkProductOut` |
| `modules/directory/catalog_router.py` | `product_category` query param; schema route `public=True` |
| `modules/search/service.py` | `_verified_first()` page re-rank |
| `backend/core/public_routes.txt` | `/catalog/verticals/{vertical}/schema` + comment |
| `backend/core/scripts/normalize_vendor_seed.py` | `MILK_SPEC_FIELDS` → v2; `product_category` column |
| `backend/core/data/seeds/coimbatore/raw_coimbatore_sheet.csv` | `product_category` column + new rows |
| `backend/core/data/seeds/coimbatore/products.csv` | regenerated |
| `backend/core/data/seeds/coimbatore/businesses.csv`, `branches.csv`, `coverage.csv` | two fixture brands |

**Frontend — created**

| File | Responsibility |
|---|---|
| `apps/web-milk/vitest.config.ts` | vitest, `environment: "node"` (mirrors `packages/ui`) |
| `apps/web-milk/lib/taxonomy.ts` | wire types, `categoriesFromSchema()`, `categoryIcon()`, `fetchProductCategories()` |
| `apps/web-milk/lib/taxonomy.test.ts` | NN#1 frontend half — pure logic |
| `apps/web-milk/components/atoms/Icon.tsx` | icon key → emoji, fallback |
| `apps/web-milk/components/atoms/Label.tsx` | EN line + vernacular line |
| `apps/web-milk/components/molecules/CategoryTile.tsx` | Link + Icon + Label |
| `apps/web-milk/components/molecules/ListBusinessCta.tsx` | console link |
| `apps/web-milk/components/organisms/CategoryTileRow.tsx` | scrollable tile row |
| `apps/web-milk/app/[locale]/p/[category]/page.tsx` | category landing |
| `apps/web-milk/app/[locale]/p/[category]/product-pincode-finder.tsx` | client wrapper for the finder closure |
| `e2e/taxonomy.spec.ts` | tile row + `/p/ghee` + CTA |

**Frontend — modified**

| File | Change |
|---|---|
| `apps/web-milk/package.json` | `test` script + `vitest` devDep |
| `apps/web-milk/app/[locale]/page.tsx` | tile row below hero |
| `apps/web-milk/app/[locale]/site-header.tsx` | static CTA link |
| `apps/web-milk/app/[locale]/site-footer.tsx` | CTA link |
| `apps/web-milk/app/[locale]/[city]/[pincode]/page.tsx` | `?product_category=` + noindex |
| `apps/web-milk/app/[locale]/[city]/[pincode]/out-of-area.tsx` | CTA in empty state |
| `apps/web-milk/lib/milk.ts` | `fetchMilkHome` gains `productCategory`; types |
| `apps/web-milk/app/sitemap.ts` | `/p/{value}` entries |
| `docs/i18n-glossary.md` | 13 category terms + `mixed` |

---

## Task 1: `option_meta` on `FieldDef`

Presentation metadata for enum options, validated at admin-write time, invisible to product validation.

**Files:**
- Modify: `backend/core/modules/directory/specs.py:28-96`
- Test: `backend/core/tests/test_specs_option_meta.py` (create)

**Interfaces:**
- Consumes: nothing.
- Produces: `class OptionMeta(BaseModel)` with `label: dict[str, str]` and `icon: str`; `FieldDef.option_meta: dict[str, OptionMeta] | None`. Serialised into `spec_schemas.fields` by the existing `f.model_dump(exclude_none=True)` in `catalog_service.create_schema_version`.

- [ ] **Step 1: Write the failing test**

Create `backend/core/tests/test_specs_option_meta.py`:

```python
"""option_meta (M1): per-enum-option i18n labels + icon key. Presentation
only - parse_fields validates it, validate_specs never reads it."""

import pytest

from modules.directory.specs import SpecValidationError, parse_fields, validate_specs

_META = {"ghee": {"label": {"en": "Ghee", "ta": "நெய்", "hi": "घी"}, "icon": "ghee"}}


def _field(**over: object) -> dict[str, object]:
    base: dict[str, object] = {
        "key": "category",
        "label": {"en": "Category"},
        "type": "enum",
        "options": ["milk", "ghee"],
        "option_meta": _META,
    }
    base.update(over)
    return base


def test_option_meta_parses_and_round_trips() -> None:
    fields = parse_fields([_field()])
    assert fields[0].option_meta is not None
    meta = fields[0].option_meta["ghee"]
    assert meta.icon == "ghee"
    assert meta.label["ta"] == "நெய்"
    # survives the dump create_schema_version uses to persist fields
    dumped = fields[0].model_dump(exclude_none=True)
    assert dumped["option_meta"]["ghee"]["label"]["hi"] == "घी"


def test_option_meta_is_optional() -> None:
    """Every schema shipped before M1 has no option_meta and stays valid."""
    fields = parse_fields([_field(option_meta=None)])
    assert fields[0].option_meta is None


def test_option_meta_rejected_on_non_enum_field() -> None:
    with pytest.raises(SpecValidationError) as exc:
        parse_fields([{"key": "fat", "label": {"en": "Fat"}, "type": "number",
                       "option_meta": _META}])
    assert exc.value.code == "invalid_field_definition"


def test_option_meta_key_must_be_a_real_option() -> None:
    with pytest.raises(SpecValidationError):
        parse_fields([_field(options=["milk"])])  # meta for "ghee", not an option


def test_option_meta_label_must_include_en() -> None:
    with pytest.raises(SpecValidationError):
        parse_fields([_field(option_meta={"ghee": {"label": {"ta": "நெய்"}, "icon": "ghee"}})])


def test_option_meta_label_rejects_unknown_locale() -> None:
    """The i18n-gap threat closes here: a bad locale never reaches a tile."""
    with pytest.raises(SpecValidationError):
        parse_fields([_field(option_meta={
            "ghee": {"label": {"en": "Ghee", "xx": "?"}, "icon": "ghee"}})])


def test_validate_specs_ignores_option_meta() -> None:
    """Product writes are unaffected: option_meta takes no part in validation."""
    fields = parse_fields([_field()])
    assert validate_specs({"category": "ghee"}, fields) == {"category": "ghee"}
    with pytest.raises(SpecValidationError) as exc:
        validate_specs({"category": "khoa"}, fields)
    assert exc.value.code == "invalid_enum_value"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd backend/core && pytest tests/test_specs_option_meta.py -v`
Expected: FAIL — `ImportError` on `OptionMeta` is not raised, but `test_option_meta_parses_and_round_trips` fails because `extra="forbid"` on `FieldDef` rejects the unknown `option_meta` key, surfacing as `SpecValidationError: invalid_field_definition`.

- [ ] **Step 3: Write minimal implementation**

In `backend/core/modules/directory/specs.py`, add `OptionMeta` above `FieldDef`:

```python
class OptionMeta(BaseModel):
    """Presentation metadata for ONE enum option (M1). Never read by
    validate_specs - it exists so a taxonomy value carries its own labels
    and icon key, and adding a value needs no frontend change."""

    model_config = ConfigDict(extra="forbid")

    label: dict[str, str]  # i18n, must include "en" (Translated locales only)
    icon: str  # icon KEY, resolved to a glyph by the frontend, never a glyph

    @field_validator("label")
    @classmethod
    def _label_i18n(cls, v: dict[str, str]) -> dict[str, str]:
        Translated.from_dict(v)  # locale allowlist + string values
        if not v.get("en"):
            raise ValueError("option label must include en")
        return v

    @field_validator("icon")
    @classmethod
    def _icon_shape(cls, v: str) -> str:
        if not _KEY_RE.fullmatch(v.replace("-", "_")):
            raise ValueError(f"bad icon key: {v!r}")
        return v
```

Add the field to `FieldDef`, immediately after `options`:

```python
    option_meta: dict[str, OptionMeta] | None = None  # enum fields only
```

Extend `FieldDef._cross_checks` — insert inside the existing `if self.type == "enum":` branch and its `elif`:

```python
    @model_validator(mode="after")
    def _cross_checks(self) -> "FieldDef":
        if self.type == "enum":
            if not self.options or len(set(self.options)) != len(self.options):
                raise ValueError("enum fields need non-empty unique options")
            if self.option_meta is not None:
                unknown = set(self.option_meta) - set(self.options)
                if unknown:
                    raise ValueError(f"option_meta for non-options: {sorted(unknown)}")
        else:
            if self.options is not None:
                raise ValueError("options only allowed on enum fields")
            if self.option_meta is not None:
                raise ValueError("option_meta only allowed on enum fields")
        if self.type != "number" and (
            self.min is not None or self.max is not None or self.unit is not None
        ):
            raise ValueError("min/max/unit only allowed on number fields")
        if self.min is not None and self.max is not None and self.min > self.max:
            raise ValueError("min > max")
        return self
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd backend/core && pytest tests/test_specs_option_meta.py tests/test_catalog_admin.py tests/test_catalog_service.py -v`
Expected: all PASS. The two existing catalog suites prove `option_meta` is additive — schemas without it are untouched.

- [ ] **Step 5: Run the repo gates**

Run: `cd backend/core && ruff format . && ruff check . && mypy . && lint-imports`
Expected: clean. Run `ruff format` **per task** — a formatting-only diff discovered at PR time is a known time sink on this repo.

- [ ] **Step 6: Commit**

```bash
git add backend/core/modules/directory/specs.py backend/core/tests/test_specs_option_meta.py
git commit -m "feat(m1): option_meta on FieldDef for per-option labels + icon key"
```

---

## Task 2: Migration 0029 — milk schema v2 + backfill

**Files:**
- Create: `backend/core/alembic/versions/0029_milk_schema_v2.py`
- Create: `backend/core/tests/test_milk_schema_v2_migration.py`
- Modify: `docs/i18n-glossary.md`

**Interfaces:**
- Consumes: `OptionMeta` shape from Task 1 (the migration writes raw dicts, but they must satisfy `parse_fields`).
- Produces: milk schema **version 2** with fields `category` (enum, required, 13 options with `option_meta`), `milk_type` (enum, **not** required, 6 options), `fat_percent`, `pack_size`. Every pre-existing `directory.products` row with `vertical_slug='milk'` carries `specs.category == "milk"` and `schema_version == 2`.

- [ ] **Step 1: Write the failing test**

Create `backend/core/tests/test_milk_schema_v2_migration.py`:

```python
"""Milk spec-schema v2 (M1): the 13-value dairy taxonomy as config, plus the
backfill that moves already-seeded products onto it."""

import uuid

import pytest
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from modules.directory import catalog_service
from modules.directory.specs import parse_fields

pytestmark = pytest.mark.asyncio

EXPECTED_CATEGORIES = [
    "milk", "ghee", "paneer", "milk-powder", "yogurt", "lassi", "curd",
    "buttermilk", "cheese", "butter", "cream", "khoa", "flavoured-milk",
]


async def test_active_milk_schema_is_v2(db_session: AsyncSession) -> None:
    schema = await catalog_service.active_schema(db_session, "milk")
    assert schema is not None
    assert schema.version == 2


async def test_category_field_carries_all_values_with_full_i18n(
    db_session: AsyncSession,
) -> None:
    schema = await catalog_service.active_schema(db_session, "milk")
    assert schema is not None
    fields = {f.key: f for f in parse_fields(schema.fields)}
    category = fields["category"]
    assert category.options == EXPECTED_CATEGORIES
    assert category.required is True
    assert category.filterable is True and category.facet is True
    assert category.option_meta is not None
    for value in EXPECTED_CATEGORIES:
        meta = category.option_meta[value]
        # i18n-gap threat: no value may ship English-only
        assert set(meta.label) == {"en", "ta", "hi"}
        assert all(meta.label[loc].strip() for loc in ("en", "ta", "hi"))
        assert meta.icon


async def test_milk_type_is_optional_in_v2_and_gained_mixed(
    db_session: AsyncSession,
) -> None:
    schema = await catalog_service.active_schema(db_session, "milk")
    assert schema is not None
    fields = {f.key: f for f in parse_fields(schema.fields)}
    milk_type = fields["milk_type"]
    assert milk_type.required is False  # a ghee product has no milk type
    # options are APPEND-ONLY: every v1 value must survive
    assert milk_type.options is not None
    for legacy in ("cow", "buffalo", "a2", "toned", "organic"):
        assert legacy in milk_type.options
    assert "mixed" in milk_type.options


async def test_v1_is_still_readable(db_session: AsyncSession) -> None:
    """Products pinned at v1 must keep rendering - versions are immutable."""
    v1 = await catalog_service.get_schema(db_session, "milk", 1)
    assert v1 is not None
    assert {f.key for f in parse_fields(v1.fields)} == {
        "milk_type", "fat_percent", "pack_size"
    }


async def test_backfill_left_no_uncategorised_milk_product(
    db_session: AsyncSession,
) -> None:
    stranded = await db_session.scalar(
        text(
            "SELECT count(*) FROM directory.products "
            "WHERE vertical_slug = 'milk' AND specs->>'category' IS NULL"
        )
    )
    assert stranded == 0


async def test_backfilled_products_are_repinned_to_v2(
    db_session: AsyncSession,
) -> None:
    stale = await db_session.scalar(
        text(
            "SELECT count(*) FROM directory.products "
            "WHERE vertical_slug = 'milk' AND specs->>'category' = 'milk' "
            "AND schema_version <> 2"
        )
    )
    assert stale == 0


async def test_backfilled_specs_still_validate_against_v2(
    db_session: AsyncSession,
) -> None:
    """A backfilled row must satisfy the version it is now pinned to."""
    from modules.directory.specs import validate_specs

    schema = await catalog_service.active_schema(db_session, "milk")
    assert schema is not None
    fields = parse_fields(schema.fields)
    rows = (
        await db_session.execute(
            text(
                "SELECT specs FROM directory.products "
                "WHERE vertical_slug = 'milk' LIMIT 50"
            )
        )
    ).all()
    for (specs,) in rows:
        validate_specs(specs, fields)  # raises on any violation


async def test_spec_schemas_remain_append_only(db_session: AsyncSession) -> None:
    """0018 revoked UPDATE/DELETE from app_rt; 0029 must not have restored it."""
    granted = await db_session.scalar(
        text(
            "SELECT count(*) FROM information_schema.role_table_grants "
            "WHERE table_schema = 'directory' AND table_name = 'spec_schemas' "
            "AND grantee = 'app_rt' AND privilege_type IN ('UPDATE', 'DELETE')"
        )
    )
    assert granted == 0
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd backend/core && pytest tests/test_milk_schema_v2_migration.py -v`
Expected: FAIL — `test_active_milk_schema_is_v2` asserts `schema.version == 2` and gets `1`.

- [ ] **Step 3: Write the migration**

Create `backend/core/alembic/versions/0029_milk_schema_v2.py`:

```python
# backend/core/alembic/versions/0029_milk_schema_v2.py
"""M1: milk spec-schema v2 - the full dairy taxonomy as config. Adds a
required `category` enum carrying per-option i18n labels + icon keys,
demotes milk_type to optional (a ghee product has no milk type) and appends
the `mixed` option, then backfills every already-seeded milk product onto
v2 with category='milk'.

Revision ID: 0029
Revises: 0028
Create Date: 2026-07-29

"""
# -- THREAT/NOTES:
# downgrade data loss: deletes the milk v2 schema row and reverts the
#   backfill (strips specs.category, re-pins schema_version to 1) for rows
#   whose category is exactly 'milk'. Products created AFTER this migration
#   in a non-milk category cannot be represented by v1 at all - downgrade
#   leaves them pinned at 2 with a now-absent schema, which renders as an
#   empty field list rather than an error (catalog_router.py:333 passes
#   `schema.fields if schema else []`). Accepted: forward-only in practice.
# locks: one INSERT into spec_schemas; one full UPDATE of
#   directory.products WHERE vertical_slug='milk' (~130 rows in the seeded
#   dev/staging DB, 0 in a fresh CI DB). Row-level locks for the duration of
#   a single small statement; no table rewrite, no index rebuild.
# rollout: spec_schemas is append-only BY GRANT (0018 revoked UPDATE/DELETE
#   from app_rt) - a taxonomy change is an INSERT of version N+1 and never
#   an edit. Options are APPEND-ONLY by contract: every v1 milk_type value
#   is repeated here, because products pinned at v1 still reference them and
#   validate_specs would reject a removed value on their next edit.
# schema-injection defence: fields JSONB below is validated by
#   modules/directory/specs.parse_fields on read AND is exercised by
#   tests/test_milk_schema_v2_migration.py, which round-trips it through
#   parse_fields and asserts full en/ta/hi coverage on every option.

from collections.abc import Sequence

import sqlalchemy as sa
import uuid6
from sqlalchemy.dialects import postgresql

from alembic import op

revision: str = "0029"
down_revision: str | None = "0028"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_uuid = postgresql.UUID(as_uuid=True)

spec_schemas_table = sa.table(
    "spec_schemas",
    sa.column("id", _uuid),
    sa.column("vertical_slug", sa.Text),
    sa.column("version", sa.Integer),
    sa.column("fields", postgresql.JSONB),
    schema="directory",
)

# (value, en, ta, hi, icon_key) - the taxonomy. Adding a value later means
# publishing version N+1 with this list extended; no code changes anywhere.
DAIRY_TAXONOMY: list[tuple[str, str, str, str, str]] = [
    ("milk", "Milk", "பால்", "दूध", "milk"),
    ("ghee", "Ghee", "நெய்", "घी", "ghee"),
    ("paneer", "Paneer", "பன்னீர்", "पनीर", "paneer"),
    ("milk-powder", "Milk Powder", "பால் பொடி", "दूध पाउडर", "milk-powder"),
    ("yogurt", "Yogurt", "யோகர்ட்", "योगर्ट", "yogurt"),
    ("lassi", "Lassi", "லஸ்சி", "लस्सी", "lassi"),
    ("curd", "Curd", "தயிர்", "दही", "curd"),
    ("buttermilk", "Buttermilk", "மோர்", "छाछ", "buttermilk"),
    ("cheese", "Cheese", "சீஸ்", "चीज़", "cheese"),
    ("butter", "Butter", "வெண்ணெய்", "मक्खन", "butter"),
    ("cream", "Cream", "கிரீம்", "क्रीम", "cream"),
    ("khoa", "Khoa", "கோவா", "खोया", "khoa"),
    ("flavoured-milk", "Flavoured Milk", "சுவையூட்டப்பட்ட பால்", "फ्लेवर्ड दूध", "flavoured-milk"),
]

# APPEND-ONLY: the first five are v1's options, repeated verbatim.
MILK_TYPES: list[tuple[str, str, str, str]] = [
    ("cow", "Cow", "பசு", "गाय"),
    ("buffalo", "Buffalo", "எருமை", "भैंस"),
    ("a2", "A2", "A2", "A2"),
    ("toned", "Toned", "டோன்ட்", "टोन्ड"),
    ("organic", "Organic", "ஆர்கானிக்", "ऑर्गेनिक"),
    ("mixed", "Mixed", "கலப்பு பால்", "मिश्रित दूध"),
]


def _option_meta(rows: list[tuple[str, ...]]) -> dict[str, dict[str, object]]:
    return {
        row[0]: {
            "label": {"en": row[1], "ta": row[2], "hi": row[3]},
            "icon": row[4] if len(row) > 4 else row[0],
        }
        for row in rows
    }


MILK_SCHEMA_V2_FIELDS: list[dict[str, object]] = [
    {
        "key": "category",
        "label": {"en": "Category", "ta": "வகை", "hi": "श्रेणी"},
        "type": "enum",
        "options": [row[0] for row in DAIRY_TAXONOMY],
        "option_meta": _option_meta(DAIRY_TAXONOMY),
        "required": True,
        "filterable": True,
        "facet": True,
        "group": "basics",
    },
    {
        "key": "milk_type",
        "label": {"en": "Milk type", "ta": "பால் வகை", "hi": "दूध का प्रकार"},
        "type": "enum",
        "options": [row[0] for row in MILK_TYPES],
        "option_meta": _option_meta(MILK_TYPES),
        # NOT required in v2: only the `milk` category has a milk type. The
        # seed normalizer enforces "milk category => milk_type present";
        # no runtime guard, because that would hardcode the taxonomy.
        "required": False,
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


def upgrade() -> None:
    op.bulk_insert(
        spec_schemas_table,
        [
            {
                "id": uuid6.uuid7(),
                "vertical_slug": "milk",
                "version": 2,
                "fields": MILK_SCHEMA_V2_FIELDS,
            }
        ],
    )
    # Backfill. Soft-deleted rows are included deliberately: an undeleted
    # product must not come back holding specs that fail its pinned schema.
    op.execute(
        """
        UPDATE directory.products
           SET specs = specs || '{"category": "milk"}'::jsonb,
               schema_version = 2
         WHERE vertical_slug = 'milk'
           AND specs->>'category' IS NULL
        """
    )


def downgrade() -> None:
    op.execute(
        """
        UPDATE directory.products
           SET specs = specs - 'category',
               schema_version = 1
         WHERE vertical_slug = 'milk'
           AND specs->>'category' = 'milk'
        """
    )
    op.execute(
        "DELETE FROM directory.spec_schemas "
        "WHERE vertical_slug = 'milk' AND version = 2"
    )
```

- [ ] **Step 4: Apply and run the tests**

```bash
cd backend/core && python -m alembic upgrade head
pytest tests/test_milk_schema_v2_migration.py -v
```
Expected: all PASS.

- [ ] **Step 5: Prove up/down/up (CI runs this)**

```bash
cd backend/core && python -m alembic downgrade -1 && python -m alembic upgrade head
pytest tests/test_milk_schema_v2_migration.py tests/test_catalog_migration.py -v
```
Expected: no error on either direction; tests PASS after the round trip.

- [ ] **Step 6: Add the 13 terms to the glossary**

Append to the table in `docs/i18n-glossary.md`, keeping the existing `| en | ta | hi |` column order, one row per value from the reference table at the top of this plan plus `mixed milk | கலப்பு பால் | मिश्रित दूध`. Then add a bullet under `## Notes`:

```markdown
- The dairy product taxonomy (`ghee`, `paneer`, `curd`, …) is taken verbatim
  from the milk spec-schema v2 `category` field's `option_meta`
  (`0029_milk_schema_v2.py`) — that JSONB is the source of truth and this
  table mirrors it. Do not re-translate these strings in UI code: the
  frontend renders the schema's labels directly.
```

- [ ] **Step 7: Run the gates and commit**

```bash
cd backend/core && ruff format . && ruff check . && mypy .
cd ../.. && git add backend/core/alembic/versions/0029_milk_schema_v2.py \
  backend/core/tests/test_milk_schema_v2_migration.py docs/i18n-glossary.md
git commit -m "feat(m1): milk spec-schema v2 - 13-value dairy taxonomy + backfill"
```

---

## Task 3: Verified-first `covers()`

**Files:**
- Modify: `backend/core/modules/directory/covers.py:51-64,80-124,159-184`
- Test: `backend/core/tests/test_covers_verified_first.py` (create)

**Interfaces:**
- Consumes: nothing from earlier tasks.
- Produces: `encode_covers_cursor(verified_rank: int, tier_rank: int, distance_m: int, last_id: uuid.UUID) -> str` and `decode_covers_cursor(cursor: str) -> tuple[int, int, int, uuid.UUID]` — **both signatures widen by one leading argument**. `covers()` keeps its signature. `CoversItem` is unchanged (`verification_status` is already on it).

- [ ] **Step 1: Write the failing test**

Create `backend/core/tests/test_covers_verified_first.py`:

```python
"""Verified-first covers() ordering (M1 NN#2): verification_status leads the
sort and the keyset, ahead of the D26 premium tier. Only 'verified' ranks up
- 'pending' sorts with 'unverified', so sitting in the D16 queue buys nothing
(fake-verification threat)."""

import uuid
from decimal import Decimal

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from modules.directory import service
from modules.directory.covers import covers, decode_covers_cursor, encode_covers_cursor
from modules.directory.models import Business
from shared.pagination import InvalidCursorError

pytestmark = pytest.mark.asyncio


async def _covered_business(
    session: AsyncSession,
    name: str,
    *,
    branch_at: tuple[float, float] = (10.9232, 76.9686),
    tier: str = "free",
    verification: str = "unverified",
) -> Business:
    owner = uuid.uuid4()
    business = await service.create_business(
        session, owner_user_id=owner, name=name, type_="vendor", primary_pincode="641001"
    )
    await service.set_coverage(
        session, owner_user_id=owner, business_id=business.id, pincodes=["641001"]
    )
    lat, lng = branch_at
    await service.add_branch(
        session,
        owner_user_id=owner,
        business_id=business.id,
        address="1 Main Rd",
        state="Tamil Nadu",
        district="Coimbatore",
        pincode="641001",
        lat=Decimal(str(lat)),
        lng=Decimal(str(lng)),
    )
    if tier != "free":
        business.subscription_tier = tier  # simulates the admin tier route
    if verification != "unverified":
        business.verification_status = verification  # simulates the D16 decision
    await session.flush()
    return business


async def test_verified_outranks_unverified_at_equal_relevance(
    db_session: AsyncSession, tn_geo_sample: None
) -> None:
    """NN#2: same tier, same distance - verification is the only difference."""
    await _covered_business(db_session, "Unverified")
    await _covered_business(db_session, "Verified", verification="verified")
    page = await covers(db_session, pincode="641001")
    assert [i.name for i in page.items] == ["Verified", "Unverified"]


async def test_verified_free_outranks_unverified_premium(
    db_session: AsyncSession, tn_geo_sample: None
) -> None:
    """The owner-approved order: trust leads, the paid tier follows."""
    await _covered_business(db_session, "PremiumUnverified", tier="premium")
    await _covered_business(db_session, "FreeVerified", verification="verified")
    page = await covers(db_session, pincode="641001")
    assert [i.name for i in page.items] == ["FreeVerified", "PremiumUnverified"]


async def test_pending_does_not_rank_up(
    db_session: AsyncSession, tn_geo_sample: None
) -> None:
    """The D16 queue is the ONLY path to the boost - being in it is not."""
    await _covered_business(db_session, "Pending", verification="pending")
    await _covered_business(db_session, "Verified", verification="verified")
    page = await covers(db_session, pincode="641001")
    assert [i.name for i in page.items] == ["Verified", "Pending"]


async def test_tier_then_distance_still_order_within_a_verification_band(
    db_session: AsyncSession, tn_geo_sample: None
) -> None:
    await _covered_business(
        db_session, "VerFreeNear", verification="verified"
    )
    await _covered_business(
        db_session, "VerPremFar", tier="premium", verification="verified",
        branch_at=(11.2832, 76.9686),
    )
    await _covered_business(db_session, "UnverPremNear", tier="premium")
    page = await covers(db_session, pincode="641001")
    assert [i.name for i in page.items] == ["VerPremFar", "VerFreeNear", "UnverPremNear"]


async def test_keyset_pages_across_the_verified_boundary(
    db_session: AsyncSession, tn_geo_sample: None
) -> None:
    """The half that fails silently: no gaps, no dupes, across the boundary."""
    for i in range(3):
        await _covered_business(db_session, f"Ver{i}", verification="verified")
    for i in range(3):
        await _covered_business(db_session, f"Unver{i}")
    seen: list[str] = []
    cursor: str | None = None
    for _ in range(10):
        page = await covers(db_session, pincode="641001", cursor=cursor, limit=2)
        seen.extend(i.name for i in page.items)
        cursor = page.next_cursor
        if cursor is None:
            break
    assert len(seen) == 6
    assert len(set(seen)) == 6
    assert all(n.startswith("Ver") for n in seen[:3])


async def test_cursor_round_trip_is_four_fields() -> None:
    ident = uuid.uuid4()
    encoded = encode_covers_cursor(0, 1, 4200, ident)
    assert decode_covers_cursor(encoded) == (0, 1, 4200, ident)


async def test_pre_m1_three_field_cursor_is_rejected() -> None:
    """D26 cursors in flight fail closed with a 400, not a wrong page."""
    import base64

    legacy = base64.urlsafe_b64encode(b"1:4200:" + uuid.uuid4().hex.encode()).decode().rstrip("=")
    with pytest.raises(InvalidCursorError):
        decode_covers_cursor(legacy)
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd backend/core && pytest tests/test_covers_verified_first.py -v`
Expected: FAIL — `test_verified_outranks_unverified_at_equal_relevance` returns the two businesses in insertion/id order, and `test_cursor_round_trip_is_four_fields` raises `TypeError` (3 positional args expected).

- [ ] **Step 3: Write the implementation**

In `backend/core/modules/directory/covers.py`:

Replace the two cursor helpers:

```python
def encode_covers_cursor(
    verified_rank: int, tier_rank: int, distance_m: int, last_id: uuid.UUID
) -> str:
    raw = f"{verified_rank}:{tier_rank}:{distance_m}:{last_id.hex}".encode()
    return base64.urlsafe_b64encode(raw).decode().rstrip("=")


def decode_covers_cursor(cursor: str) -> tuple[int, int, int, uuid.UUID]:
    try:
        padded = cursor + "=" * (-len(cursor) % 4)
        parts = base64.urlsafe_b64decode(padded).decode().split(":")
        if len(parts) != 4:  # pre-D26 2-field and pre-M1 3-field cursors land here
            raise ValueError(f"expected 4 fields, got {len(parts)}")
        return int(parts[0]), int(parts[1]), int(parts[2]), uuid.UUID(hex=parts[3])
    except (ValueError, TypeError) as exc:
        raise InvalidCursorError(f"malformed cursor: {cursor!r}") from exc
```

Add the rank expression next to `_TIER_RANK` (line 80):

```python
# Only 'verified' ranks up. 'pending' sorts with 'unverified' on purpose:
# the D16 admin decision is the sole path to the badge AND to this boost,
# so queueing a claim cannot buy placement (M1 threat model).
_VERIFIED_RANK = "CASE WHEN b.verification_status = 'verified' THEN 0 ELSE 1 END"
```

In `_BASE_SQL`, add the rank to the SELECT list — change the `{_TIER_RANK} AS tier_rank` line to:

```sql
       {_VERIFIED_RANK} AS verified_rank, {_TIER_RANK} AS tier_rank
```

Replace `_CURSOR_PREDICATE` and `_ORDER_LIMIT`:

```python
_CURSOR_PREDICATE = f"""
  AND ({_VERIFIED_RANK} > :cursor_verified
       OR ({_VERIFIED_RANK} = :cursor_verified AND {_TIER_RANK} > :cursor_tier)
       OR ({_VERIFIED_RANK} = :cursor_verified AND {_TIER_RANK} = :cursor_tier
           AND d.distance_m > :cursor_distance)
       OR ({_VERIFIED_RANK} = :cursor_verified AND {_TIER_RANK} = :cursor_tier
           AND d.distance_m = :cursor_distance AND b.id > :cursor_id))
"""

_ORDER_LIMIT = "\nORDER BY verified_rank, tier_rank, d.distance_m, b.id\nLIMIT :lim"
```

In `covers()`, widen the cursor unpack and the params:

```python
    if cursor is not None:
        cursor_verified, cursor_tier, cursor_distance, cursor_id = decode_covers_cursor(cursor)
        sql += _CURSOR_PREDICATE
        params |= {
            "cursor_verified": cursor_verified,
            "cursor_tier": cursor_tier,
            "cursor_distance": cursor_distance,
            "cursor_id": cursor_id,
        }
```

And the `next_cursor` build:

```python
    next_cursor = (
        encode_covers_cursor(
            0 if items[-1].verification_status == "verified" else 1,
            0 if items[-1].subscription_tier == "premium" else 1,
            items[-1].distance_m,
            items[-1].id,
        )
        if len(rows) > limit
        else None
    )
```

Finally, extend the module docstring's keyset sentence (line 8) to read `(verified_rank, tier_rank, distance_m, last_id)`.

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd backend/core && pytest tests/test_covers_verified_first.py tests/test_covers_premium_sort.py tests/test_directory_covers.py tests/test_milk_home.py -v`
Expected: all PASS. `test_covers_premium_sort.py` is the D26 suite — it must stay green, because premium still orders within a verification band.

- [ ] **Step 5: Run the gates and commit**

```bash
cd backend/core && ruff format . && ruff check . && mypy . && lint-imports
cd ../.. && git add backend/core/modules/directory/covers.py backend/core/tests/test_covers_verified_first.py
git commit -m "feat(m1): verified-first covers() ordering with a 4-field keyset cursor"
```

---

## Task 4: Milk home — `product_category` filter and `product_categories`

**Files:**
- Modify: `backend/core/modules/directory/milk_home.py:106-115,168-287`
- Modify: `backend/core/modules/directory/milk_home_schemas.py:16-21,54-62,86-92,110-120`
- Modify: `backend/core/modules/directory/catalog_router.py` (the `/milk/home/{pincode}` route)
- Test: `backend/core/tests/test_milk_home_categories.py` (create)

**Interfaces:**
- Consumes: milk schema v2 from Task 2; verified-first ordering from Task 3 (inherited, no code here).
- Produces: `milk_home(session, *, pincode, milk_type, product_category, cursor, limit)` — one new keyword-only param. `MilkHomeResult` gains `product_categories: list[str]`. `MilkHomeOut` gains `product_categories: list[str]`; `MilkProductOut` gains `category: str | None`. Route accepts `?product_category=`.

- [ ] **Step 1: Write the failing test**

Create `backend/core/tests/test_milk_home_categories.py`:

```python
"""M1 milk-home taxonomy wiring: schema-driven product_categories, the
additive ?product_category= filter (D23's ?type= is untouched), and the
price banner narrowed to category='milk' so a ghee-only seller cannot
inflate the milk seller count."""

import uuid
from dataclasses import dataclass
from decimal import Decimal

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from modules.directory import catalog_service, service
from modules.directory.milk_home import compute_price_banner, milk_home
from modules.directory.models import Business

pytestmark = pytest.mark.asyncio


@dataclass
class _P:
    business_id: uuid.UUID
    specs: dict[str, object]
    price_display: str | None


async def _vendor_with(
    session: AsyncSession, name: str, products: list[tuple[str, dict[str, object], str]]
) -> Business:
    owner = uuid.uuid4()
    business = await service.create_business(
        session, owner_user_id=owner, name=name, type_="vendor", primary_pincode="641001"
    )
    await service.set_coverage(
        session, owner_user_id=owner, business_id=business.id, pincodes=["641001"]
    )
    await service.add_branch(
        session, owner_user_id=owner, business_id=business.id, address="1 Main Rd",
        state="Tamil Nadu", district="Coimbatore", pincode="641001",
        lat=Decimal("10.9232"), lng=Decimal("76.9686"),
    )
    for product_name, specs, price in products:
        product = await catalog_service.create_product(
            session, owner_user_id=owner, business_id=business.id,
            vertical_slug="milk", name=product_name, specs=specs, price_display=price,
        )
        product.moderation_status = "approved"
    await session.flush()
    return business


async def test_product_categories_come_from_the_active_schema(
    db_session: AsyncSession, tn_geo_sample: None
) -> None:
    result = await milk_home(
        db_session, pincode="641001", milk_type=None, product_category=None,
        cursor=None, limit=20,
    )
    assert result.product_categories[0] == "all"
    assert "ghee" in result.product_categories
    assert "khoa" in result.product_categories


async def test_product_categories_present_in_empty_states(
    db_session: AsyncSession, tn_geo_sample: None
) -> None:
    """Chips must not flash/reflow when data arrives - same rule as filters."""
    out_of_area = await milk_home(
        db_session, pincode="110001", milk_type=None, product_category=None,
        cursor=None, limit=20,
    )
    assert out_of_area.scope == "out_of_area"
    assert "ghee" in out_of_area.product_categories
    no_vendors = await milk_home(
        db_session, pincode="600001", milk_type=None, product_category=None,
        cursor=None, limit=20,
    )
    assert no_vendors.scope == "tn_no_vendors"
    assert "ghee" in no_vendors.product_categories


async def test_product_category_narrows_cards(
    db_session: AsyncSession, tn_geo_sample: None
) -> None:
    await _vendor_with(db_session, "MilkOnly",
                       [("Cow Milk", {"category": "milk", "milk_type": "cow"}, "₹50/L")])
    await _vendor_with(db_session, "GheeOnly",
                       [("Pure Ghee", {"category": "ghee"}, "₹600/500ml")])
    ghee = await milk_home(
        db_session, pincode="641001", milk_type=None, product_category="ghee",
        cursor=None, limit=20,
    )
    assert [v.name for v in ghee.vendors] == ["GheeOnly"]
    assert ghee.scope == "covered"


async def test_unknown_product_category_is_treated_as_absent(
    db_session: AsyncSession, tn_geo_sample: None
) -> None:
    """D27 precedent: an unrecognised value is not a 422."""
    await _vendor_with(db_session, "MilkOnly",
                       [("Cow Milk", {"category": "milk", "milk_type": "cow"}, "₹50/L")])
    result = await milk_home(
        db_session, pincode="641001", milk_type=None, product_category="not-a-category",
        cursor=None, limit=20,
    )
    assert [v.name for v in result.vendors] == ["MilkOnly"]


async def test_type_and_product_category_compose(
    db_session: AsyncSession, tn_geo_sample: None
) -> None:
    await _vendor_with(db_session, "Both", [
        ("Cow Milk", {"category": "milk", "milk_type": "cow"}, "₹50/L"),
        ("Pure Ghee", {"category": "ghee"}, "₹600/500ml"),
    ])
    result = await milk_home(
        db_session, pincode="641001", milk_type="cow", product_category="milk",
        cursor=None, limit=20,
    )
    assert [p.name for p in result.vendors[0].products] == ["Cow Milk"]


def test_price_banner_ignores_non_milk_products() -> None:
    """seller_count must reflect milk sellers, not every dairy seller."""
    milk_seller, ghee_seller = uuid.uuid4(), uuid.uuid4()
    bands, sellers = compute_price_banner([
        _P(milk_seller, {"category": "milk", "milk_type": "cow", "pack_size": "1l"}, "₹50/L"),
        _P(ghee_seller, {"category": "ghee"}, "₹600/500ml"),
    ])
    assert [b.milk_type for b in bands] == ["cow"]
    assert sellers == 1
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd backend/core && pytest tests/test_milk_home_categories.py -v`
Expected: FAIL — `TypeError: milk_home() got an unexpected keyword argument 'product_category'`.

- [ ] **Step 3: Write the implementation**

In `backend/core/modules/directory/milk_home.py`:

Add a schema-keys helper next to `_milk_filter_keys` (after line 115):

```python
async def _product_category_keys(session: AsyncSession) -> list[str]:
    """Schema-driven category chips: ['all', *category options]. Same rule as
    _milk_filter_keys - the taxonomy is never hardcoded here (M1 NN#1)."""
    schema = await catalog_service.active_schema(session, "milk")
    if schema is None:
        return ["all"]
    for field in parse_fields(schema.fields):
        if field.key == "category" and field.options:
            return ["all", *field.options]
    return ["all"]
```

Add the field to `MilkHomeResult` (after `filters`):

```python
    product_categories: list[str]
```

Narrow the banner. Change `compute_price_banner`'s loop guard so only milk-category products contribute — replace the first two lines of the `for p in products:` body with:

```python
    for p in products:
        if p.specs.get("category") not in (None, "milk"):
            continue  # ghee/paneer/... never carry a milk price band, and must
            # not inflate seller_count under a milk-only banner (M1)
        milk_type = p.specs.get("milk_type")
```

The `None` case keeps any pre-backfill row behaving as it did.

Update the docstring of `compute_price_banner` to say so:

```python
    """Group parseable ₹ prices by milk_type → (low, high) band per type.
    Only products in the `milk` category contribute (M1): other dairy
    categories have no milk price band and must not inflate seller_count.
    ...
```

In `milk_home()`, change the signature and every `MilkHomeResult(...)` construction. Signature:

```python
async def milk_home(
    session: AsyncSession,
    *,
    pincode: str,
    milk_type: str | None,
    product_category: str | None,
    cursor: str | None,
    limit: int,
) -> MilkHomeResult:
```

At the top of the body, next to `filters`:

```python
    filters = await _milk_filter_keys(session)
    product_categories = await _product_category_keys(session)
    # An unrecognised value is treated as absent, never a 422 (D27 precedent).
    if product_category is not None and product_category not in product_categories:
        product_category = None
```

Add `product_categories=product_categories,` to **all four** `MilkHomeResult(...)` returns (out_of_area, the two tn_no_vendors branches, and covered).

In the card loop, filter by category **before** the milk_type filter:

```python
        if product_category and product_category != "all":
            biz_products = [
                p for p in biz_products if p.specs.get("category") == product_category
            ]
            if not biz_products:
                continue
        if milk_type and milk_type != "all":
```

In `backend/core/modules/directory/milk_home_schemas.py`:

```python
class MilkProductOut(BaseModel):
    category: str | None
    milk_type: str | None
    fat_percent: float | None
    pack_size: str | None
    price_display: str | None
```

…and in `_card_out`, add `category=p.specs.get("category"),` as the first argument to `MilkProductOut(...)`. Add to `MilkHomeOut` after `filters`:

```python
    product_categories: list[str]
```

…and to `milk_home_out`'s return: `product_categories=result.product_categories,`.

In `backend/core/modules/directory/catalog_router.py`, the milk-home route gains the query param and passes it through — add `product_category: Annotated[str | None, Query(max_length=64)] = None,` to the signature and `product_category=product_category,` to the `milk_home_module.milk_home(...)` call.

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd backend/core && pytest tests/test_milk_home_categories.py tests/test_milk_home.py tests/test_milk_coverage_pincodes.py -v`
Expected: all PASS. `test_milk_home.py` is the D23 suite; if it fails on `milk_home()` arity, add `product_category=None` at those call sites — the wire contract for `filters`/`?type=` must not change.

- [ ] **Step 5: Run the gates and commit**

```bash
cd backend/core && ruff format . && ruff check . && mypy . && lint-imports
cd ../.. && git add backend/core/modules/directory/milk_home.py \
  backend/core/modules/directory/milk_home_schemas.py \
  backend/core/modules/directory/catalog_router.py \
  backend/core/tests/test_milk_home_categories.py backend/core/tests/test_milk_home.py
git commit -m "feat(m1): additive product_category filter + schema-driven category chips"
```

---

## Task 5: Publish the schema route

**Files:**
- Modify: `backend/core/modules/directory/catalog_router.py:280-298`
- Modify: `backend/core/public_routes.txt`
- Test: `backend/core/tests/test_taxonomy_zero_code.py` (create)

**Interfaces:**
- Consumes: `option_meta` (Task 1), milk v2 (Task 2), `product_categories` (Task 4).
- Produces: `GET /catalog/verticals/{vertical}/schema` reachable with no auth, returning `SchemaVersionOut` (`vertical_slug`, `version`, `fields`, `created_at`). This is the frontend's taxonomy source in Task 7.

- [ ] **Step 1: Write the failing test**

Create `backend/core/tests/test_taxonomy_zero_code.py`:

```python
"""M1 NON-NEGOTIABLE 1, backend half: a value added to the schema reaches
every consumer with zero code changes. Publishing v3 in-test is the whole
proof - nothing below names the new value anywhere but the schema payload."""

import uuid
from collections.abc import AsyncIterator

import httpx
import pytest
from fastapi import Request
from sqlalchemy.ext.asyncio import AsyncSession

from main import create_app
from modules.directory import catalog_service, service
from modules.directory.specs import parse_fields
from shared.db import get_session
from shared.security import register_principal_resolver

pytestmark = pytest.mark.asyncio

NEW_VALUE = "shrikhand"


@pytest.fixture
async def client(db_session: AsyncSession) -> AsyncIterator[httpx.AsyncClient]:
    app = create_app()

    async def _session_override() -> AsyncIterator[AsyncSession]:
        yield db_session

    async def _resolver(request: Request, session: AsyncSession) -> object | None:
        return None  # anonymous: the route under test must be public

    app.dependency_overrides[get_session] = _session_override
    register_principal_resolver(_resolver)
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="https://api.test") as http:
        yield http


async def _publish_v3(session: AsyncSession) -> None:
    """Add ONE value to the active schema and republish. This is the only
    action a real taxonomy change takes."""
    active = await catalog_service.active_schema(session, "milk")
    assert active is not None
    fields = [f.model_dump(exclude_none=True) for f in parse_fields(active.fields)]
    for field in fields:
        if field["key"] == "category":
            field["options"] = [*field["options"], NEW_VALUE]
            field["option_meta"] = {
                **field["option_meta"],
                NEW_VALUE: {
                    "label": {"en": "Shrikhand", "ta": "ஸ்ரீகண்ட்", "hi": "श्रीखंड"},
                    "icon": "shrikhand",
                },
            }
    await catalog_service.create_schema_version(
        session, vertical_slug="milk", fields_raw=fields
    )


async def test_schema_route_is_public(client: httpx.AsyncClient) -> None:
    res = await client.get("/catalog/verticals/milk/schema")
    assert res.status_code == 200
    assert res.json()["vertical_slug"] == "milk"


async def test_new_value_appears_in_the_public_schema_payload(
    client: httpx.AsyncClient, db_session: AsyncSession
) -> None:
    await _publish_v3(db_session)
    res = await client.get("/catalog/verticals/milk/schema")
    assert res.status_code == 200
    body = res.json()
    assert body["version"] == 3
    category = next(f for f in body["fields"] if f["key"] == "category")
    assert NEW_VALUE in category["options"]
    meta = category["option_meta"][NEW_VALUE]
    assert set(meta["label"]) == {"en", "ta", "hi"}
    assert meta["icon"] == "shrikhand"


async def test_new_value_appears_in_milk_home_filters(
    client: httpx.AsyncClient, db_session: AsyncSession, tn_geo_sample: None
) -> None:
    await _publish_v3(db_session)
    res = await client.get("/catalog/milk/home/641001")
    assert res.status_code == 200
    assert NEW_VALUE in res.json()["product_categories"]


async def test_new_value_is_accepted_as_a_product_spec(
    db_session: AsyncSession, tn_geo_sample: None
) -> None:
    await _publish_v3(db_session)
    owner = uuid.uuid4()
    business = await service.create_business(
        db_session, owner_user_id=owner, name="Sweet Dairy", type_="shop",
        primary_pincode="641001",
    )
    product = await catalog_service.create_product(
        db_session, owner_user_id=owner, business_id=business.id, vertical_slug="milk",
        name="Elaichi Shrikhand", specs={"category": NEW_VALUE}, price_display="₹80/200g",
    )
    assert product.specs["category"] == NEW_VALUE
    assert product.schema_version == 3
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd backend/core && pytest tests/test_taxonomy_zero_code.py -v`
Expected: FAIL — `test_schema_route_is_public` gets 401, because the route is on a `SecureRouter` without `public=True`.

- [ ] **Step 3: Write the implementation**

In `backend/core/modules/directory/catalog_router.py`, change the decorator on `get_vertical_schema` (line 280) to `@router.get("/verticals/{vertical}/schema", public=True)` and expand its docstring:

```python
    """The active spec-schema for a vertical. PUBLIC (M1): the milk taxonomy
    (category options + their i18n labels and icon keys) is what web-milk's
    home tile row and /p/{category} pages render, and both are SSR/ISR with
    no user session. Admin-authored config with no PII; rate-limited like
    every public route. One source, read by both the D26 console and the
    public site - a second endpoint would drift."""
```

In `backend/core/public_routes.txt`, insert after the `/catalog/verticals/{vertical}/products` line:

```
# /catalog/verticals/{vertical}/schema: the active spec-schema (M1) - the
# dairy taxonomy's values, i18n labels and icon keys. Config only, no PII;
# web-milk's home tile row and /p/{category} pages SSR from it.
/catalog/verticals/{vertical}/schema
```

- [ ] **Step 4: Run tests to verify they pass**

```bash
cd backend/core && pytest tests/test_taxonomy_zero_code.py tests/test_vertical_schema_route.py -v
python scripts/dump_public_routes.py --check
```
Expected: tests PASS; the public-routes check reports no diff.

- [ ] **Step 5: Run the gates and commit**

```bash
cd backend/core && ruff format . && ruff check . && mypy . && lint-imports
cd ../.. && git add backend/core/modules/directory/catalog_router.py \
  backend/core/public_routes.txt backend/core/tests/test_taxonomy_zero_code.py
git commit -m "feat(m1): publish the vertical schema route - the taxonomy is public config"
```

---

## Task 6: Search verified re-rank (D19 hook)

**Files:**
- Modify: `backend/core/modules/search/service.py:102-110`
- Test: `backend/core/tests/test_search_verified_rerank.py` (create)

**Interfaces:**
- Consumes: nothing from earlier tasks.
- Produces: `_verified_first(hits: list[dict[str, Any]]) -> list[dict[str, Any]]` — a stable partition, applied inside `run_search` to the returned page. No index settings change.

- [ ] **Step 1: Write the failing test**

Create `backend/core/tests/test_search_verified_rerank.py`:

```python
"""M1 spec C, search half: verified hits lead each returned page. A stable
partition applied AFTER Meili returns - the index is untouched (no
sortableAttributes change, no reindex), so Meili's relevance order is
preserved exactly within each partition."""

from modules.search.service import _verified_first


def _hit(name: str, verified: bool | None) -> dict[str, object]:
    return {"id": name, "name": name, "verified": verified}


def test_verified_hits_lead() -> None:
    hits = [_hit("a", False), _hit("b", True), _hit("c", False), _hit("d", True)]
    assert [h["name"] for h in _verified_first(hits)] == ["b", "d", "a", "c"]


def test_relevance_order_is_preserved_within_each_partition() -> None:
    hits = [_hit(n, n in {"b", "d"}) for n in "abcdef"]
    result = [h["name"] for h in _verified_first(hits)]
    assert result[:2] == ["b", "d"]          # verified, in Meili's order
    assert result[2:] == ["a", "c", "e", "f"]  # unverified, in Meili's order


def test_missing_verified_field_sorts_with_unverified() -> None:
    """A doc indexed before `verified` existed must not rank up."""
    hits = [_hit("legacy", None), _hit("ver", True)]
    assert [h["name"] for h in _verified_first(hits)] == ["ver", "legacy"]


def test_empty_page_is_handled() -> None:
    assert _verified_first([]) == []
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd backend/core && pytest tests/test_search_verified_rerank.py -v`
Expected: FAIL — `ImportError: cannot import name '_verified_first'`.

- [ ] **Step 3: Write the implementation**

In `backend/core/modules/search/service.py`, add above `run_search`:

```python
def _verified_first(hits: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Stable partition of ONE result page: verified businesses lead (M1).

    Deliberately not a Meili sort. `verified` is filterable but not
    sortable, and M1 forbids an index rebuild - so this reorders the page
    that was already fetched. Limitation, stated rather than hidden: a
    verified result on page 3 is NOT pulled onto page 1. Promoting
    `verified` to a sortable attribute is a settings change plus a full
    reindex, out of scope here."""
    return [h for h in hits if h.get("verified")] + [
        h for h in hits if not h.get("verified")
    ]
```

In `run_search`, change line 105 from `items = hits[:limit]` to:

```python
    items = _verified_first(hits[:limit])
```

`has_more` and `next_start` are computed from the raw `hits` and stay untouched — re-ranking is display-only and must not disturb the offset arithmetic.

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd backend/core && pytest tests/test_search_verified_rerank.py -v && pytest -q -m "not slow" -k search`
Expected: all PASS.

- [ ] **Step 5: Confirm the index settings are untouched**

Run: `git diff --stat backend/core/modules/search/indexing.py`
Expected: **empty output.** Any diff here breaks the "no search index rebuild" constraint.

- [ ] **Step 6: Run the gates and commit**

```bash
cd backend/core && ruff format . && ruff check . && mypy . && lint-imports
cd ../.. && git add backend/core/modules/search/service.py backend/core/tests/test_search_verified_rerank.py
git commit -m "feat(m1): verified-first re-rank of each search page (no reindex)"
```

---

## Task 7: Seed — taxonomy coverage and the item-4 fixtures

**Files:**
- Modify: `backend/core/scripts/normalize_vendor_seed.py:99-135,275-325`
- Modify: `backend/core/data/seeds/coimbatore/raw_coimbatore_sheet.csv`
- Regenerate: `backend/core/data/seeds/coimbatore/products.csv`, `businesses.csv`, `branches.csv`, `coverage.csv`
- Test: `backend/core/tests/test_catalog_one_vs_all.py` (create)

**Interfaces:**
- Consumes: milk v2 (Task 2).
- Produces: seed data where every one of the 13 categories has ≥ 1 Coimbatore listing; two fixture brands — `Kovai Ghee House` (exactly one product) and `Coimbatore Dairy Mart` (all thirteen).

- [ ] **Step 1: Write the failing test**

Create `backend/core/tests/test_catalog_one_vs_all.py`:

```python
"""M1 NON-NEGOTIABLE 3 (spec item 4): a brand selling ONE product and a brand
selling ALL of them both render correctly. Built on real seed-shaped data,
not synthetic scaffolding."""

import uuid
from decimal import Decimal

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from modules.directory import catalog_service, service
from modules.directory.milk_home import milk_home
from modules.directory.specs import parse_fields

pytestmark = pytest.mark.asyncio


async def _all_categories(session: AsyncSession) -> list[str]:
    schema = await catalog_service.active_schema(session, "milk")
    assert schema is not None
    field = next(f for f in parse_fields(schema.fields) if f.key == "category")
    assert field.options is not None
    return list(field.options)


async def _brand(
    session: AsyncSession, name: str, categories: list[str]
) -> tuple[uuid.UUID, str]:
    owner = uuid.uuid4()
    business = await service.create_business(
        session, owner_user_id=owner, name=name, type_="shop", primary_pincode="641001"
    )
    await service.set_coverage(
        session, owner_user_id=owner, business_id=business.id, pincodes=["641001"]
    )
    await service.add_branch(
        session, owner_user_id=owner, business_id=business.id, address="1 Main Rd",
        state="Tamil Nadu", district="Coimbatore", pincode="641001",
        lat=Decimal("10.9232"), lng=Decimal("76.9686"),
    )
    for category in categories:
        specs: dict[str, object] = {"category": category}
        if category == "milk":
            specs["milk_type"] = "cow"
        product = await catalog_service.create_product(
            session, owner_user_id=owner, business_id=business.id, vertical_slug="milk",
            name=f"{name} {category}", specs=specs, price_display="₹100",
        )
        product.moderation_status = "approved"
    await session.flush()
    return business.id, business.slug


async def test_one_product_brand_renders(
    db_session: AsyncSession, tn_geo_sample: None
) -> None:
    _, slug = await _brand(db_session, "Kovai Ghee House", ["ghee"])
    page = await catalog_service.list_business_products(db_session, slug)
    assert len(page.items) == 1
    assert page.items[0].specs["category"] == "ghee"


async def test_all_products_brand_renders(
    db_session: AsyncSession, tn_geo_sample: None
) -> None:
    categories = await _all_categories(db_session)
    _, slug = await _brand(db_session, "Coimbatore Dairy Mart", categories)
    page = await catalog_service.list_business_products(db_session, slug, limit=100)
    assert {p.specs["category"] for p in page.items} == set(categories)


async def test_both_brands_appear_on_their_category_pages(
    db_session: AsyncSession, tn_geo_sample: None
) -> None:
    categories = await _all_categories(db_session)
    await _brand(db_session, "Kovai Ghee House", ["ghee"])
    await _brand(db_session, "Coimbatore Dairy Mart", categories)
    ghee = await milk_home(
        db_session, pincode="641001", milk_type=None, product_category="ghee",
        cursor=None, limit=50,
    )
    assert {b.name for b in ghee.brands} == {"Kovai Ghee House", "Coimbatore Dairy Mart"}
    khoa = await milk_home(
        db_session, pincode="641001", milk_type=None, product_category="khoa",
        cursor=None, limit=50,
    )
    assert {b.name for b in khoa.brands} == {"Coimbatore Dairy Mart"}


async def test_one_product_brand_is_absent_from_other_categories(
    db_session: AsyncSession, tn_geo_sample: None
) -> None:
    await _brand(db_session, "Kovai Ghee House", ["ghee"])
    paneer = await milk_home(
        db_session, pincode="641001", milk_type=None, product_category="paneer",
        cursor=None, limit=50,
    )
    assert paneer.brands == []
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd backend/core && pytest tests/test_catalog_one_vs_all.py -v`
Expected: FAIL — `SpecValidationError: missing_required: category` is not raised, but `test_all_products_brand_renders` fails because the seed's brands do not yet carry the other twelve categories. `list_business_products(session, business_slug, *, cursor, limit)` returns only `approved` + `active` products, which is why `_brand` flips `moderation_status` — do not add a new service function for this test.

- [ ] **Step 3: Teach the normalizer about categories**

In `backend/core/scripts/normalize_vendor_seed.py`, replace the `MILK_SPEC_FIELDS` constant so it mirrors **v2** byte-for-byte. Copy `MILK_SCHEMA_V2_FIELDS` verbatim out of `backend/core/alembic/versions/0029_milk_schema_v2.py` (including `option_meta`), and update the comment above it to name 0029 rather than 0018.

Then, in `_build_product`, read the new column. Replace the `elif vertical_slug == "milk":` block's opening with:

```python
    elif vertical_slug == "milk":
        specs = {}
        product_category = raw.get("product_category", "").strip().lower()
        if not product_category:
            # Required, deliberately with no default: an uncategorised seed row
            # would render nowhere. Seed quality is a stated M1 threat.
            return None, "missing_product_category"
        specs["category"] = product_category
        milk_type = raw.get("milk_type", "").strip().lower()
        if milk_type:
            specs["milk_type"] = milk_type
```

…leaving the `fat_percent` / `pack_size` handling below it untouched. Add one guard after that block, before the `validate_specs` call:

```python
    if vertical_slug == "milk" and specs.get("category") == "milk" and "milk_type" not in specs:
        # v2 cannot express "required only for this category", so the seed
        # tool enforces it. A milk listing with no type has no price band.
        return None, "missing_milk_type_for_milk_category"
```

- [ ] **Step 4: Add the column and the rows to the raw sheet**

In `backend/core/data/seeds/coimbatore/raw_coimbatore_sheet.csv`:

1. Add `product_category` to the header, immediately before `milk_type`.
2. Fill `milk` for every existing product row.
3. Add product rows for the remaining twelve categories against existing brands that plausibly sell them — Aavin (`ghee`, `paneer`, `curd`, `butter`, `khoa`), and spread `milk-powder`, `yogurt`, `lassi`, `buttermilk`, `cheese`, `cream`, `flavoured-milk` across the other seeded brands. Every new row needs `product_name`, `price_display`, and the `description_ta` / `description_hi` conventions already used by its business rows.
4. Add the two fixture businesses with their branch + coverage columns, exactly as existing multi-row businesses are written:
   - `Kovai Ghee House` — type `shop`, one product, category `ghee`.
   - `Coimbatore Dairy Mart` — type `shop`, thirteen products, one per category.

Use the labels from this plan's reference table for any Tamil/Hindi product naming so the seed and the schema agree.

- [ ] **Step 5: Regenerate and validate the seed**

```bash
cd backend/core
python scripts/normalize_vendor_seed.py
python scripts/import_vendor_seed.py --dry-run
```
Expected: the normalizer reports zero violations (it collects **all** violations into one `SeedContractError`, so a clean run means every row validated against v2); the dry-run import reports the new businesses and products with no error.

- [ ] **Step 6: Load into the dev DB and run the tests**

```bash
cd backend/core && python scripts/import_vendor_seed.py
pytest tests/test_catalog_one_vs_all.py tests/test_milk_home_categories.py -v
```
Expected: all PASS.

- [ ] **Step 7: Assert every category is actually covered**

```bash
cd backend/core && python -c "
import csv, json, collections
rows = list(csv.DictReader(open('data/seeds/coimbatore/products.csv', encoding='utf-8')))
seen = collections.Counter(json.loads(r['specs_json']).get('category') for r in rows)
print(sorted(seen.items()))
missing = {'milk','ghee','paneer','milk-powder','yogurt','lassi','curd','buttermilk','cheese','butter','cream','khoa','flavoured-milk'} - set(seen)
print('MISSING:', missing or 'none')
"
```
Expected: `MISSING: none`. If not, go back to Step 4 — this is the DoD's "every category value seeded".

- [ ] **Step 8: Run the gates and commit**

```bash
cd backend/core && ruff format . && ruff check . && mypy .
cd ../.. && git add backend/core/scripts/normalize_vendor_seed.py \
  backend/core/data/seeds/coimbatore/ backend/core/tests/test_catalog_one_vs_all.py
git commit -m "feat(m1): seed every dairy category + one-product and all-products brands"
```

---

## Task 8: Frontend taxonomy library and atoms

**Files:**
- Create: `apps/web-milk/vitest.config.ts`, `apps/web-milk/lib/taxonomy.ts`, `apps/web-milk/lib/taxonomy.test.ts`
- Create: `apps/web-milk/components/atoms/Icon.tsx`, `apps/web-milk/components/atoms/Label.tsx`
- Create: `apps/web-milk/components/molecules/CategoryTile.tsx`
- Create: `apps/web-milk/components/organisms/CategoryTileRow.tsx`
- Modify: `apps/web-milk/package.json`

**Interfaces:**
- Consumes: the public schema route from Task 5.
- Produces:
  - `interface ProductCategory { value: string; label: string; vern: string; icon: string }`
  - `categoriesFromSchema(payload: unknown, locale: string): ProductCategory[]`
  - `categoryIcon(key: string): string`
  - `fetchProductCategories(locale: string): Promise<ProductCategory[]>`
  - `<Icon icon={string} />`, `<Label en={string} vern={string} />`, `<CategoryTile category={ProductCategory} />`, `<CategoryTileRow categories={ProductCategory[]} />`

- [ ] **Step 1: Add the test runner**

In `apps/web-milk/package.json`, add `"test": "vitest run"` to `scripts` and `"vitest": "4.1.10"` to `devDependencies` (pin to the exact version `packages/ui` already uses — a second version would churn the lockfile and can trip the `pnpm audit` gate).

Create `apps/web-milk/vitest.config.ts` — mirrors `packages/ui/vitest.config.ts` exactly:

```ts
import { defineConfig } from "vitest/config";

export default defineConfig({
  test: {
    environment: "node",
    include: ["lib/**/*.test.ts"],
  },
});
```

`environment: "node"` is deliberate: no jsdom, no testing-library, no new dependencies. All taxonomy logic lives in pure functions so it is testable without a DOM. Turbo's `test` task picks this package up automatically — CI job A already runs `turbo run lint typecheck test build`, so **no workflow change is needed**.

Run: `pnpm install`

- [ ] **Step 2: Write the failing test**

Create `apps/web-milk/lib/taxonomy.test.ts`:

```ts
import { describe, expect, it } from "vitest";

import { categoriesFromSchema, categoryIcon } from "./taxonomy";

const schema = {
  vertical_slug: "milk",
  version: 2,
  fields: [
    {
      key: "category",
      type: "enum",
      options: ["milk", "ghee"],
      option_meta: {
        milk: { label: { en: "Milk", ta: "பால்", hi: "दूध" }, icon: "milk" },
        ghee: { label: { en: "Ghee", ta: "நெய்", hi: "घी" }, icon: "ghee" },
      },
    },
    { key: "fat_percent", type: "number" },
  ],
};

describe("categoriesFromSchema", () => {
  it("reads values, labels and icons out of the schema", () => {
    expect(categoriesFromSchema(schema, "en")).toEqual([
      { value: "milk", label: "Milk", vern: "பால்", icon: "🥛" },
      { value: "ghee", label: "Ghee", vern: "நெய்", icon: "🍯" },
    ]);
  });

  it("renders the requested locale as the primary label", () => {
    const [milk] = categoriesFromSchema(schema, "hi");
    expect(milk.label).toBe("दूध");
  });

  it("falls back to en when the locale is missing from a label", () => {
    const partial = {
      fields: [
        {
          key: "category",
          type: "enum",
          options: ["khoa"],
          option_meta: { khoa: { label: { en: "Khoa" }, icon: "khoa" } },
        },
      ],
    };
    expect(categoriesFromSchema(partial, "ta")[0].label).toBe("Khoa");
  });

  it("NON-NEGOTIABLE 1: a value added to the schema needs no code change", () => {
    const withNewValue = {
      fields: [
        {
          key: "category",
          type: "enum",
          options: ["milk", "shrikhand"],
          option_meta: {
            milk: { label: { en: "Milk", ta: "பால்" }, icon: "milk" },
            shrikhand: { label: { en: "Shrikhand", ta: "ஸ்ரீகண்ட்" }, icon: "shrikhand" },
          },
        },
      ],
    };
    const result = categoriesFromSchema(withNewValue, "ta");
    expect(result.map((c) => c.value)).toEqual(["milk", "shrikhand"]);
    expect(result[1].label).toBe("ஸ்ரீகண்ட்"); // label ships from the schema
    expect(result[1].icon).toBe("🥛"); // unknown icon key → documented fallback
  });

  it("uses the option value when an option carries no metadata at all", () => {
    const bare = { fields: [{ key: "category", type: "enum", options: ["lassi"] }] };
    expect(categoriesFromSchema(bare, "en")).toEqual([
      { value: "lassi", label: "lassi", vern: "", icon: "🧋" },
    ]);
  });

  it("returns nothing when the schema has no category field", () => {
    expect(categoriesFromSchema({ fields: [{ key: "fat_percent" }] }, "en")).toEqual([]);
  });

  it("survives a malformed payload rather than throwing", () => {
    expect(categoriesFromSchema(null, "en")).toEqual([]);
    expect(categoriesFromSchema({ fields: "nope" }, "en")).toEqual([]);
  });
});

describe("categoryIcon", () => {
  it("maps known keys", () => {
    expect(categoryIcon("paneer")).toBe("🧀");
  });

  it("falls back for unknown keys", () => {
    expect(categoryIcon("not-a-real-key")).toBe("🥛");
  });
});
```

- [ ] **Step 3: Run test to verify it fails**

Run: `cd apps/web-milk && pnpm test`
Expected: FAIL — cannot resolve `./taxonomy`.

- [ ] **Step 4: Write the implementation**

Create `apps/web-milk/lib/taxonomy.ts`:

```ts
const API = process.env.API_BASE_URL ?? "http://127.0.0.1:8000";

/**
 * The dairy product taxonomy (M1). The VALUE SET, its labels and its icon
 * keys all come from the D17 milk spec-schema — `GET
 * /catalog/verticals/milk/schema`. Nothing here enumerates categories:
 * adding one to the schema must light it up everywhere with no code change
 * (NON-NEGOTIABLE 1).
 */
export interface ProductCategory {
  value: string;
  label: string;
  vern: string;
  icon: string;
}

/**
 * icon KEY → glyph. Presentation only, and deliberately not exhaustive:
 * an unknown key falls back to 🥛, so a brand-new schema value renders with
 * its correct label immediately and only its glyph is a follow-up.
 *
 * Every glyph is Unicode ≤ 13.0 on purpose — rural Android devices ship
 * older emoji fonts and a newer codepoint renders as tofu (▯).
 */
const CATEGORY_ICONS: Record<string, string> = {
  milk: "🥛",
  ghee: "🍯",
  paneer: "🧀",
  "milk-powder": "🥄",
  yogurt: "🍶",
  lassi: "🧋",
  curd: "🍚",
  buttermilk: "🥤",
  cheese: "🫕",
  butter: "🧈",
  cream: "🍦",
  khoa: "🍥",
  "flavoured-milk": "🍫",
};

const FALLBACK_ICON = "🥛";

export function categoryIcon(key: string): string {
  return CATEGORY_ICONS[key] ?? FALLBACK_ICON;
}

interface SchemaOptionMeta {
  label?: Record<string, string>;
  icon?: string;
}

/** The vernacular second line: Tamil for en/ta readers, Hindi for hi. */
function vernacularFor(label: Record<string, string>, locale: string, primary: string): string {
  const vern = locale === "hi" ? label.hi : label.ta;
  return vern && vern !== primary ? vern : "";
}

export function categoriesFromSchema(payload: unknown, locale: string): ProductCategory[] {
  const fields = (payload as { fields?: unknown } | null)?.fields;
  if (!Array.isArray(fields)) return [];
  const field = fields.find(
    (f) => (f as { key?: string })?.key === "category",
  ) as { options?: unknown; option_meta?: Record<string, SchemaOptionMeta> } | undefined;
  if (!field || !Array.isArray(field.options)) return [];
  const meta = field.option_meta ?? {};
  return field.options
    .filter((value): value is string => typeof value === "string")
    .map((value) => {
      const label = meta[value]?.label ?? {};
      const primary = label[locale] ?? label.en ?? value;
      return {
        value,
        label: primary,
        vern: vernacularFor(label, locale, primary),
        icon: categoryIcon(meta[value]?.icon ?? value),
      };
    });
}

/**
 * Server-side public read — direct to the backend, NOT the BFF proxy, with
 * ISR caching. Returns [] on any failure so a build with no backend still
 * succeeds and self-heals at the next revalidate (same contract as
 * `fetchCoveredPincodes` in lib/milk.ts, which sitemap generation relies on).
 */
export async function fetchProductCategories(locale: string): Promise<ProductCategory[]> {
  try {
    const res = await fetch(`${API}/catalog/verticals/milk/schema`, {
      next: { revalidate: 3600 },
    });
    if (!res.ok) return [];
    return categoriesFromSchema(await res.json(), locale);
  } catch {
    return [];
  }
}
```

- [ ] **Step 5: Run test to verify it passes**

Run: `cd apps/web-milk && pnpm test`
Expected: all PASS.

- [ ] **Step 6: Write the atoms, molecule and organism**

`apps/web-milk/components/atoms/Icon.tsx`:

```tsx
/** Atom: a decorative glyph. `aria-hidden` because the adjacent Label
 * already carries the accessible name — announcing both would read the
 * category twice. */
export function Icon({ glyph }: { glyph: string }) {
  return (
    <span aria-hidden="true" className="text-[26px] leading-none">
      {glyph}
    </span>
  );
}
```

`apps/web-milk/components/atoms/Label.tsx`:

```tsx
/** Atom: primary label with an optional vernacular second line. `vern`
 * carries the `.vern` class the design system uses for Tamil/Hindi copy. */
export function Label({ en, vern }: { en: string; vern?: string }) {
  return (
    <span className="flex flex-col items-center gap-0.5 text-center">
      <span className="text-[12px] font-bold leading-tight text-ink">{en}</span>
      {vern ? <span className="vern text-[11px] leading-tight text-sub">{vern}</span> : null}
    </span>
  );
}
```

`apps/web-milk/components/molecules/CategoryTile.tsx`:

```tsx
import { Link } from "@/i18n/navigation";
import type { ProductCategory } from "@/lib/taxonomy";

import { Icon } from "../atoms/Icon";
import { Label } from "../atoms/Label";

/** Molecule: one tappable category. Icon-first, then the schema's label.
 * `min-w`/`min-h` keep the tap target at the 44px floor the design system
 * requires (the D11 tap-target finding). */
export function CategoryTile({ category }: { category: ProductCategory }) {
  return (
    <Link
      href={`/p/${category.value}`}
      prefetch={false}
      data-testid={`category-tile-${category.value}`}
      className="flex min-h-[76px] min-w-[76px] shrink-0 flex-col items-center justify-center gap-1 rounded-card border border-line bg-card px-2 py-2 no-underline"
    >
      <Icon glyph={category.icon} />
      <Label en={category.label} vern={category.vern} />
    </Link>
  );
}
```

`apps/web-milk/components/organisms/CategoryTileRow.tsx`:

```tsx
import type { ProductCategory } from "@/lib/taxonomy";

import { CategoryTile } from "../molecules/CategoryTile";

/**
 * Organism: the home category row. A server component — no client JS, no
 * images, no hydration island, so it costs the LCP path nothing beyond its
 * own markup (NON-NEGOTIABLE 4).
 *
 * Renders nothing when the taxonomy is unavailable (backend down at build
 * time), so the page still builds and self-heals on the next revalidate.
 */
export function CategoryTileRow({
  categories,
  heading,
}: {
  categories: ProductCategory[];
  heading: string;
}) {
  if (categories.length === 0) return null;
  return (
    <nav aria-label={heading} data-testid="category-tile-row" className="w-full">
      <ul className="flex list-none gap-2 overflow-x-auto px-4 pb-2 [scrollbar-width:none] [&::-webkit-scrollbar]:hidden">
        {categories.map((category) => (
          <li key={category.value}>
            <CategoryTile category={category} />
          </li>
        ))}
      </ul>
    </nav>
  );
}
```

- [ ] **Step 7: Verify the gates**

```bash
cd apps/web-milk && pnpm lint && pnpm typecheck && pnpm test
cd ../.. && node scripts/check-hex.mjs
```
Expected: all clean. `check:hex` is a **root** script — it fails on any raw hex colour in app code; every colour above is a token (`text-ink`, `bg-card`, `border-line`).

- [ ] **Step 8: Commit**

```bash
git add apps/web-milk/package.json apps/web-milk/vitest.config.ts \
  apps/web-milk/lib/taxonomy.ts apps/web-milk/lib/taxonomy.test.ts \
  apps/web-milk/components/ pnpm-lock.yaml
git commit -m "feat(m1): taxonomy lib + atomic Icon/Label/CategoryTile/CategoryTileRow"
```

---

## Task 9: Home tile row and `/p/[category]` pages

**Files:**
- Modify: `apps/web-milk/app/[locale]/page.tsx`
- Create: `apps/web-milk/app/[locale]/p/[category]/page.tsx`
- Create: `apps/web-milk/app/[locale]/p/[category]/product-pincode-finder.tsx`
- Modify: `apps/web-milk/app/sitemap.ts`

**Interfaces:**
- Consumes: `fetchProductCategories`, `ProductCategory`, `CategoryTileRow` (Task 8).
- Produces: `/[locale]/p/[category]` routes; `/{city}/{pincode}?product_category={value}` as the finder target consumed by Task 10.

- [ ] **Step 1: Add the row to the home page**

In `apps/web-milk/app/[locale]/page.tsx`, add the imports:

```tsx
import { CategoryTileRow } from "@/components/organisms/CategoryTileRow";
import { fetchProductCategories } from "@/lib/taxonomy";
```

In `HomePage`, after `setRequestLocale(locale);`:

```tsx
  const categories = await fetchProductCategories(locale);
```

And render the row directly below the `</PincodeHero>` close, above the post-need CTA:

```tsx
      <div className="mx-auto w-full max-w-[720px] pt-4">
        <CategoryTileRow categories={categories} heading="Dairy categories" />
      </div>
```

`revalidate = 3600` already sits at the top of this file, and `fetchProductCategories` caches with the same window — the page stays statically rendered (`○`).

- [ ] **Step 2: Verify home is still statically rendered**

```bash
cd apps/web-milk && rm -rf .next && pnpm build
```
Expected: the route table shows `○ /[locale]` (static), **not** `ƒ` (dynamic). A regression to `ƒ` breaks D23's next-intl static fix and tanks Lighthouse. `rm -rf .next` is required — a stale build reads stale validator paths.

- [ ] **Step 3: Write the category landing page**

Create `apps/web-milk/app/[locale]/p/[category]/product-pincode-finder.tsx`:

```tsx
"use client";

import { PincodeHeroFinder } from "../../pincode-hero";

/**
 * `page.tsx` here is a Server Component, so it cannot pass an inline
 * `hrefForPincode` closure to the client-only `PincodeHeroFinder`
 * (functions are not serializable across the RSC boundary — Next throws at
 * prerender time). This thin client wrapper takes the serializable category
 * value and builds the closure on the client. Mirrors
 * `app/[locale]/c/[category]/category-pincode-finder.tsx`.
 */
export function ProductPincodeFinder({ category }: { category: string }) {
  return (
    <PincodeHeroFinder
      hrefForPincode={(pincode) => `/${pincode}?product_category=${category}`}
    />
  );
}
```

`/{pincode}` 301s to `/{city}/{pincode}` preserving the query string (`app/[locale]/[city]/page.tsx`), so the finder does not need the district to build a link.

Create `apps/web-milk/app/[locale]/p/[category]/page.tsx`:

```tsx
import { buildMetadata, canonicalUrl } from "@agri/ui/seo";
import type { Metadata } from "next";
import { notFound } from "next/navigation";
import { setRequestLocale } from "next-intl/server";

import { routing } from "@/i18n/routing";
import { fetchProductCategories } from "@/lib/taxonomy";

import { ProductPincodeFinder } from "./product-pincode-finder";

const SITE = "https://milk.in";

export const revalidate = 3600;

/**
 * `true` on purpose (M1 NON-NEGOTIABLE 1): a category added to the schema
 * AFTER this deploy still renders, on demand, with no rebuild. Unknown
 * values 404 below, so this is not an open door.
 */
export const dynamicParams = true;

export async function generateStaticParams() {
  const categories = await fetchProductCategories("en");
  return routing.locales.flatMap((locale) =>
    categories.map((category) => ({ locale, category: category.value })),
  );
}

type Params = Promise<{ locale: string; category: string }>;

export async function generateMetadata({ params }: { params: Params }): Promise<Metadata> {
  const { locale, category } = await params;
  const match = (await fetchProductCategories(locale)).find((c) => c.value === category);
  if (!match) return { title: "Milk.in" };
  return buildMetadata({
    title: `${match.label} near you — Milk.in`,
    description: `Find ${match.label} from verified dairy brands, local vendors and farms near you across Tamil Nadu.`,
    canonical: canonicalUrl(SITE, `/p/${category}`),
    siteName: "Milk.in",
  });
}

/**
 * CollectionPage — hand-built, following the precedent in
 * `app/[locale]/c/[category]/page.tsx`. `<` escaped so it can never close
 * the script tag.
 */
function collectionJsonLd(name: string, canonical: string): string {
  return JSON.stringify({
    "@context": "https://schema.org",
    "@type": "CollectionPage",
    name,
    url: canonical,
  }).replaceAll("<", "\\u003c");
}

export default async function ProductCategoryPage({ params }: { params: Params }) {
  const { locale, category } = await params;
  setRequestLocale(locale);
  const match = (await fetchProductCategories(locale)).find((c) => c.value === category);
  if (!match) notFound();
  const canonical = canonicalUrl(SITE, `/p/${category}`);
  return (
    <main className="mx-auto flex w-full max-w-[720px] flex-col gap-5 px-4 py-6">
      <script
        type="application/ld+json"
        dangerouslySetInnerHTML={{ __html: collectionJsonLd(match.label, canonical) }}
      />
      <h1 className="font-display text-[22px] font-extrabold text-ink">
        {match.label} near you
      </h1>
      {match.vern ? <p className="vern text-[15px] text-sub">{match.vern}</p> : null}
      <ProductPincodeFinder category={category} />
    </main>
  );
}
```

- [ ] **Step 4: Add the pages to the sitemap**

In `apps/web-milk/app/sitemap.ts`, import `fetchProductCategories` and append one entry per category (`${SITE}/p/${value}`) alongside the existing static entries. Follow whatever `changeFrequency`/`priority` convention the file already uses for `/c/*` entries; if the file has no backend call yet, the `[]`-on-failure contract means a backend outage degrades to the existing static list rather than failing the build.

- [ ] **Step 5: Verify the build and the routes**

```bash
cd apps/web-milk && rm -rf .next && pnpm lint && pnpm typecheck && pnpm build
```
Expected: build succeeds; the route table lists `/[locale]/p/[category]` with prerendered paths for all 13 values × 3 locales.

- [ ] **Step 6: Prove the build survives a dead backend**

```bash
cd apps/web-milk && rm -rf .next && API_BASE_URL=http://127.0.0.1:9 pnpm build
```
Expected: **build still succeeds.** The home row renders empty and `/p/*` prerenders nothing, both by design. A failure here means a `try/catch` is missing.

- [ ] **Step 7: Commit**

```bash
git add "apps/web-milk/app/[locale]/page.tsx" "apps/web-milk/app/[locale]/p/" apps/web-milk/app/sitemap.ts
git commit -m "feat(m1): home category tile row + auto-generated /p/[category] pages"
```

---

## Task 10: Pincode page filtering

**Files:**
- Modify: `apps/web-milk/lib/milk.ts:104-120` and the `MilkHome`/`MilkProduct` interfaces
- Modify: `apps/web-milk/app/[locale]/[city]/[pincode]/page.tsx`

**Interfaces:**
- Consumes: `product_category` wire contract (Task 4); `/p/*` finder target (Task 9).
- Produces: `fetchMilkHome(pincode: string, type?: string, productCategory?: string)` — one new trailing optional parameter, so every existing call site is unchanged.

- [ ] **Step 1: Extend the wire mirror**

In `apps/web-milk/lib/milk.ts`:

```ts
export interface MilkProduct {
  category: string | null;
  milk_type: string | null;
  fat_percent: number | null;
  pack_size: string | null;
  price_display: string | null;
}
```

Add to `MilkHome`, immediately after `filters`:

```ts
  product_categories: string[];
```

And widen the fetcher:

```ts
export async function fetchMilkHome(
  pincode: string,
  type?: string,
  productCategory?: string,
): Promise<MilkHome | null> {
  const qs = new URLSearchParams();
  if (type && type !== "all") qs.set("type", type);
  if (productCategory && productCategory !== "all") {
    qs.set("product_category", productCategory);
  }
  const suffix = qs.toString() ? `?${qs}` : "";
  try {
    const res = await fetch(`${API}/catalog/milk/home/${encodeURIComponent(pincode)}${suffix}`, {
      next: { revalidate: 300 },
    });
    if (!res.ok) return null;
    return (await res.json()) as MilkHome;
  } catch {
    return null;
  }
}
```

- [ ] **Step 2: Read the param on the pincode page**

In `apps/web-milk/app/[locale]/[city]/[pincode]/page.tsx`:

1. Widen the `searchParams` type on both the metadata function and the page component to include `product_category?: string`.
2. Destructure it: `const { type = "all", category, product_category } = await searchParams;`
3. Pass it through: `fetchMilkHome(pincode, type, product_category)`.
4. In `generateMetadata`, add `product_category` to the condition that already sets `robots: { index: false }` for `?category=`, and keep the canonical pointing at the bare `/{city}/{pincode}` — a filtered view is never the indexable URL.

Do **not** add a category chip row to this page. The spec puts tiles on home; the pincode page consumes the param that `/p/*` sends it. A second chip row here is scope the spec did not ask for.

- [ ] **Step 3: Verify**

```bash
cd apps/web-milk && rm -rf .next && pnpm lint && pnpm typecheck && pnpm build
```
Expected: clean.

Then, with the backend and web-milk running locally:

```bash
curl -s "http://127.0.0.1:8000/catalog/milk/home/641001?product_category=ghee" | head -c 400
curl -s -o /dev/null -w "%{http_code}\n" "http://localhost:3000/coimbatore/641001?product_category=ghee"
```
Expected: the API response's vendor/brand lists contain only ghee sellers; the page returns 200.

- [ ] **Step 4: Confirm the noindex rule**

```bash
curl -s "http://localhost:3000/coimbatore/641001?product_category=ghee" | grep -o '<meta name="robots"[^>]*>'
```
Expected: a `noindex` robots tag.

- [ ] **Step 5: Commit**

```bash
git add apps/web-milk/lib/milk.ts "apps/web-milk/app/[locale]/[city]/[pincode]/page.tsx"
git commit -m "feat(m1): pincode page honours ?product_category= (noindex, canonical unchanged)"
```

---

## Task 11: "List your dairy business" CTA

**Files:**
- Create: `apps/web-milk/components/molecules/ListBusinessCta.tsx`
- Modify: `apps/web-milk/app/[locale]/site-header.tsx`, `apps/web-milk/app/[locale]/site-footer.tsx`
- Modify: `apps/web-milk/app/[locale]/[city]/[pincode]/out-of-area.tsx` and the `tn_no_vendors` empty state
- Modify: `apps/web-milk/.env.example` (or the app's existing env sample) and `docker-compose*.yml` / staging env where `API_BASE_URL` for web-milk is set

**Interfaces:**
- Consumes: nothing from earlier tasks.
- Produces: `<ListBusinessCta variant="header" | "footer" | "block" />`.

- [ ] **Step 1: Write the component**

Create `apps/web-milk/components/molecules/ListBusinessCta.tsx`:

```tsx
const CONSOLE = process.env.NEXT_PUBLIC_CONSOLE_URL ?? "http://localhost:3002";

/**
 * Molecule: the front door for brands. A cross-origin link to the EXISTING
 * D16 claim/create flow in the Business Console (`apps/web-agri/app/business/*`)
 * — a door, not a new flow. No new route, no new backend surface.
 *
 * Deliberately a plain <a>, not a hydrating island: `site-footer.tsx`
 * records that a fourth item in the header's right cluster moved CLS from
 * 0.098 to 0.136 as the islands populated. A static link is in the initial
 * HTML and cannot shift.
 */
export function ListBusinessCta({
  variant = "block",
}: {
  variant?: "header" | "footer" | "block";
}) {
  const className =
    variant === "block"
      ? "block rounded-card border border-line bg-card px-4 py-3 text-center text-[14px] font-bold text-ink no-underline"
      : "text-[13px] font-bold text-ink no-underline";
  return (
    <a href={`${CONSOLE}/business/listings`} className={className} data-testid="list-business-cta">
      List your dairy business{" "}
      <span className="vern font-normal text-sub">· உங்கள் வணிகத்தைப் பதிவு செய்யுங்கள்</span>
    </a>
  );
}
```

- [ ] **Step 2: Place it**

- **Footer** (`site-footer.tsx`): render `<ListBusinessCta variant="footer" />` before the `LowDataToggle`, and change the `<footer>` class from `justify-end` to `items-center justify-between` so the two sit at opposite ends.
- **Header** (`site-header.tsx`): pass it via `HeaderStack`'s existing left/tagline area, **not** the `right` cluster. Check `HeaderStack`'s prop list first (`grep -n "HeaderStack" -A 20 packages/ui/src/*.tsx`); if it has no slot outside `right`, render the CTA as the first child of the existing `location` slot instead. Do not add a fourth element to `right`.
- **Empty states**: render `<ListBusinessCta />` (block variant) in `out-of-area.tsx` and in the `tn_no_vendors` branch of `[pincode]/page.tsx`, below the existing notify-me control.

- [ ] **Step 3: Declare the env var**

Add `NEXT_PUBLIC_CONSOLE_URL=http://localhost:3002` to web-milk's env sample, and set it wherever web-milk's `API_BASE_URL` is set for compose/staging. `NEXT_PUBLIC_` is required — this value is read during client-side render of the header.

- [ ] **Step 4: Measure the Lighthouse impact**

```bash
cd apps/web-milk && rm -rf .next && pnpm build && pnpm start &
cd ../.. && pnpm exec lhci autorun --collect.url=http://localhost:3000/
```
Expected: **CLS must not regress** versus the pre-CTA number. Absolute local scores are not evidence — this machine floors at ~0.79–0.83 for pages that pass at ≥ 0.90 in CI. Compare CLS to a run of the same command on `dev`.

If CLS regressed, apply the stated fallback: add `hidden sm:inline` to the header variant's `className`. Do not lower the Lighthouse threshold and do not soft-disable the gate.

- [ ] **Step 5: Verify and commit**

```bash
cd apps/web-milk && pnpm lint && pnpm typecheck && pnpm test
cd ../.. && node scripts/check-hex.mjs
git add apps/web-milk/components/molecules/ListBusinessCta.tsx "apps/web-milk/app/[locale]/"
git commit -m "feat(m1): list-your-dairy-business CTA in header, footer and empty states"
```

---

## Task 12: End-to-end proof, docs, and the PR

**Files:**
- Create: `e2e/taxonomy.spec.ts`
- Modify: `backend/core/scripts/gen_module_claude.py`
- Modify: `backend/core/scripts/seed_e2e_milk.py`

**Interfaces:**
- Consumes: every prior task.
- Produces: a green branch and a PR to `dev`.

- [ ] **Step 1: Give the e2e seed a category**

`backend/core/scripts/seed_e2e_milk.py:57-58` builds products with `{"milk_type": ..., "fat_percent": ..., "pack_size": ...}`. Add `"category": "milk"` to each, or the seed will 422 against v2's required field. Add one ghee product to the same covered vendor so `/p/ghee` has content at 641001.

- [ ] **Step 2: Write the e2e spec**

Create `e2e/taxonomy.spec.ts`:

```ts
import { expect, test } from "@playwright/test";

// web-milk runs on :3000 but the Playwright baseURL is web-id (:3003),
// so every navigation here uses an absolute URL.
import { MILK, waitForHeaderSettled } from "./helpers";

test.describe("M1 dairy taxonomy", () => {
  test("home renders the category tile row from schema values", async ({ page }) => {
    await page.goto(`${MILK}/`);
    await waitForHeaderSettled(page);
    await expect(page.getByTestId("category-tile-row")).toBeVisible();
    await expect(page.getByTestId("category-tile-milk")).toBeVisible();
    await expect(page.getByTestId("category-tile-ghee")).toBeVisible();
  });

  test("a tile navigates to its category page", async ({ page }) => {
    await page.goto(`${MILK}/`);
    await waitForHeaderSettled(page);
    await page.getByTestId("category-tile-ghee").click();
    await expect(page).toHaveURL(/\/p\/ghee$/);
    await expect(page.getByRole("heading", { level: 1 })).toContainText(/ghee/i);
  });

  test("the category page finder lands on a filtered pincode view", async ({ page }) => {
    await page.goto(`${MILK}/p/ghee`);
    await page.getByRole("textbox").first().fill("641001");
    await page.getByRole("button", { name: /find|தேடு/i }).first().click();
    await expect(page).toHaveURL(/product_category=ghee/);
  });

  test("the list-your-business CTA points at the console", async ({ page }) => {
    await page.goto(`${MILK}/`);
    await waitForHeaderSettled(page);
    const cta = page.getByTestId("list-business-cta").first();
    await expect(cta).toBeVisible();
    await expect(cta).toHaveAttribute("href", /\/business\/listings$/);
  });

  test("the Tamil home renders Tamil category labels", async ({ page }) => {
    await page.goto(`${MILK}/ta`);
    await waitForHeaderSettled(page);
    await expect(page.getByTestId("category-tile-ghee")).toContainText("நெய்");
  });
});
```

- [ ] **Step 3: Run the e2e suite**

```bash
pnpm run e2e:api &
pnpm run e2e -- taxonomy.spec.ts
```
Expected: all PASS. If the finder's button or textbox selector does not match, read `apps/web-milk/app/[locale]/pincode-hero.tsx` and use its real accessible names — do not add test-only attributes to shipped components.

Note: `e2e/map-sync.spec.ts` fails **locally only** (seed markers overlap the e2e fixture at 641001's centroid); CI's isolated DB is unaffected. Do not "fix" it.

- [ ] **Step 4: Regenerate the module CLAUDE.md**

`backend/core/modules/directory/CLAUDE.md` is generated. Edit the directory-module description in `backend/core/scripts/gen_module_claude.py` to mention the M1 taxonomy (schema v2's `category` field, the public schema route, verified-first `covers()`), then:

```bash
cd backend/core && python scripts/gen_module_claude.py
git diff --stat backend/core/modules/*/CLAUDE.md
```
Expected: only the directory (and search, if you described the re-rank) module docs change.

- [ ] **Step 5: Run the full local gate set**

```bash
cd backend/core && ruff format --check . && ruff check . && mypy . && lint-imports
pytest -q -m "not slow"
pytest -q -m "slow"          # storm suite, its OWN run — inline it and 25 downstream tests fail
python scripts/dump_public_routes.py --check
cd ../.. && pnpm exec turbo run lint typecheck test build
node scripts/check-hex.mjs
```
Expected: everything green. Run `mypy` and `lint-imports` **before the first push** — they are the two gates that most often fail after a PR is already open.

- [ ] **Step 6: Verify the four non-negotiables explicitly**

```bash
cd backend/core && pytest tests/test_taxonomy_zero_code.py tests/test_covers_verified_first.py tests/test_catalog_one_vs_all.py -v
cd ../apps/web-milk && pnpm test
```
Expected: NN#1 (backend + frontend halves), NN#2, NN#3 all green. NN#4 (Lighthouse ≥ 90 on home) is decided by the CI `lighthouse` job — CI is the arbiter, per Task 11 Step 4.

- [ ] **Step 7: Confirm the tree is clean and push**

```bash
git status --short
```
Expected: empty (the standing rule is `git status` zero AM before every commit).

```bash
git push -u origin feat/m1-taxonomy-verified
```

- [ ] **Step 8: Open the PR to `dev`**

Open a PR **targeting `dev`, never `main`**, titled `feat(m1): dairy taxonomy + verified-first + onboarding CTA`.

This repo has no `gh` CLI; PRs are opened via `git credential fill` → the GitHub API, and the token must be **exported** so child processes see it.

The PR body must record the five accepted risks from the design doc's §8 verbatim — the cursor break, `milk_type` losing `required` (and the price-banner narrowing), the newly-public schema route, the header-CTA Lighthouse trade-off, and the page-local search re-rank — plus the known follow-ups: a native-speaker pass on the model-authored TA/HI category labels, and the duplicate-free but tunable emoji map.

- [ ] **Step 9: Watch CI**

All required checks must be green before requesting review. For a transient failure, use *re-run failed jobs* rather than pushing an empty commit.

---

## Self-Review

**Spec coverage** — every M1 requirement maps to a task:

| Spec item | Task |
|---|---|
| A. Taxonomy as D17 schema values, i18n labels + icon key, no hardcoded lists | 1, 2 |
| B. Home tile row (organism ← molecule ← atoms), category page auto-generated, ISR + JSON-LD, noindex rule | 8, 9, 10 |
| C. Verified-first ranking on category pages, `covers()`, D19 search hook | 3, 4 (inherited), 6 |
| D. "List your dairy business" CTA in header, footer, zero-coverage empty state | 11 |
| E. Seed every category value, TA/HI complete | 7 |
| Integration surface: filters (D23), profiles (D24), dashboard (D26), search facets (D19) | 4, 5, 6, 7 |
| NN#1 add-a-schema-value, zero code | 5 (backend), 8 (frontend), 12 (e2e) |
| NN#2 verified outranks unverified at equal relevance | 3 |
| NN#3 one-product and all-products brands | 7 |
| NN#4 Lighthouse ≥ 90 on home | 9 (build check), 11 (CLS measurement), 12 (CI) |
| THREAT: fake verification pressure | 3 (`pending` does not rank up) |
| THREAT: seed quality | 7 (`missing_product_category` is a hard error) |
| THREAT: i18n gaps | 1 (`Translated.from_dict` at write time), 2 (test asserts en/ta/hi on all 13) |

**Type consistency** — checked across tasks: `encode_covers_cursor`/`decode_covers_cursor` widen to four fields in Task 3 and nothing else calls them; `milk_home(..., product_category=...)` in Task 4 matches the call in Tasks 7 and 12's tests; `ProductCategory` fields (`value`, `label`, `vern`, `icon`) are identical in `taxonomy.ts`, `CategoryTile`, `CategoryTileRow` and the `/p` page; `product_category` is the wire name in the API, the query string and the `fetchMilkHome` parameter (`productCategory` in camelCase on the TS side only, converted at the fetch boundary).

**D26 note for the reviewer:** the Business Console's product form reads `/catalog/verticals/milk/schema` and will start showing the `category` field with no console code change — that is the integration surface working as designed, and it is worth clicking through once before merge.
