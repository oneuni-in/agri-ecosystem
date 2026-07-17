# D17 — Vertical Registry + Spec-Schemas + Products + Media · Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.
>
> On approval this plan is committed to `docs/superpowers/plans/2026-07-17-d17-registry-products.md` (repo convention, first commit on the branch).

**Goal:** The extensibility core — a vertical registry, versioned JSONB spec-schemas with validate-on-write, schema-driven products with hardened public media — so Milk.in (D23) and every future vertical is a registry entry + schema, not new code.

**Architecture:** All code lives in `modules/directory` (import-linter independence makes a separate catalog module impossible today: product writes must IDOR-check `directory.businesses` ownership, and modules may never import each other). Tables go in Postgres schema `directory` (spec-sanctioned). **URL namespace is `/catalog/*`** (owner decision) so the planned Stage-B catalog-engine extraction never has to 301 product URLs. New files: `specs.py` (the validator — the shared contract), `catalog_models.py`, `catalog_service.py`, `catalog_schemas.py`, `catalog_router.py`, `catalog_admin_router.py`, migration `0018_catalog_v1.py`.

**Tech stack:** FastAPI SecureRouter, SQLAlchemy 2 async, Alembic, Pydantic v2 (field-def validation), shared.media `reencode_image` (D16 helper — reused, never forked), MinIO via shared.storage.

**Owner decisions (locked, 2026-07-17):** `/catalog/*` URL prefix · admin schema CRUD is API-only (web-admin UI arrives with Stage-B schema builder) · minimal admin product approve/reject IS included (otherwise pending-default products could never go public before D21).

## Global Constraints

- Branch `feat/d17-registry-products` off dev; conventional commits; PR → dev only; NEVER commit to dev/main. PR title: `feat(d17): registry + products`.
- No transactions/checkout: `price_display` is info-only text; no cart/payment scaffolding for goods.
- No per-vertical hardcoded product code — schema-driven only. No offset pagination (lint gate).
- Product specs validated against the pinned schema version; old products keep rendering after schema v2 (NN#1).
- Media EXIF-stripped (fresh-JPEG re-encode) + served off the app domain (NN#2); ONE shared media helper — `shared.media.reencode_image`, no fork (NN#3, new lint check).
- Migration `0018` next in the committed chain, linear, filename == internal revision, THREAT/NOTES block filled (NN#4).
- app_rt grants: products/registry mutable (full DML); `spec_schemas` append-only by grant (INSERT+SELECT only).
- Modules never import each other; directory never imports identity — principals via `request.state.principal`.
- Never log request bodies or query strings in this module.
- Before every commit: `git status` shows ZERO AM (staged-then-modified) files. Run `ruff format --check`, `ruff check`, `mypy .`, `lint-imports` before first push (CI-parity memory).
- Env reality: Postgres on :45432 (`DATABASE_URL` = app_rt, `DATABASE_ADMIN_URL` = app), not settings.py's 55432 default. All backend commands run from `backend/core/`.

## Existing code to reuse (do not reinvent)

| Need | Reuse | Where |
|---|---|---|
| EXIF-strip/re-encode/size/type/bomb guard | `reencode_image`, `MediaError`, `MAX_IMAGE_BYTES` | `shared/media.py` |
| Object storage | `put_object`, `get_object`, `StorageError` | `shared/storage.py` |
| Ownership IDOR gate | `get_owned_business`, `BusinessNotFoundError` | `modules/directory/service.py:87` |
| Slug machinery | `_slugify` (`service.py:37`), `ImmutableSlugMixin` | `modules/directory/service.py`, `shared/slugs.py` |
| Keyset pagination | `paginate`, `Page`, `InvalidCursorError` | `shared/pagination.py` |
| Mixins | `UUIDv7PKMixin`, `TimestampMixin`, `SoftDeleteMixin`, `UGCMixin` | `shared/db.py` |
| i18n | `Translated`, `TranslatedString`, `SUPPORTED_LOCALES` | `shared/i18n.py` |
| Flags (fail-closed) | `flag_enabled` | `shared/flags.py` (pattern: `modules/coins/admin_router.py:171`) |
| Audit (same-session) | `audit(...)`; ORM attr is `.meta` | `shared/audit.py`, D16 memory |
| Role gate (no identity import) | `_require_role` pattern | `modules/directory/admin_router.py:50` |
| Migration helpers + template | `pk_column`, `timestamp_columns`; seed patterns | `shared/migrations.py`, `alembic/versions/0016/0017` |
| Router test harness | `api` fixture (principal via `x-test-user` header), `object_store` monkeypatch fixture | `tests/test_claims_router.py:47-84` |
| Lint contracts | `tests/lint_checks.py` + `tests/test_lint_contracts.py` | extend for media-fork ban |

**Deliberate deviations from the spec text (document in PR body):**
- "presign → …" — D16 already ruled out presigned direct uploads (they'd bypass the server re-encode that IS the EXIF guarantee; PR #25). Product images use the same server-mediated multipart path.
- Schema "CRUD" — versions are **append-only** (create/read only). Updating/deleting a published version would break pinned products' rendering; enforced by grant (`REVOKE UPDATE, DELETE`). To change a schema, publish version N+1.
- No `product.created/updated` events yet — D19's indexer spec owns the event-emission seam (it must also add `business.created/updated`, which D15 never emitted). Listed as a D19 integration note in the PR body.

---

### Task 0: Branch + plan commit

- [ ] `git checkout dev && git pull && git checkout -b feat/d17-registry-products`
- [ ] Copy this plan to `docs/superpowers/plans/2026-07-17-d17-registry-products.md`
- [ ] `git add docs/superpowers/plans/2026-07-17-d17-registry-products.md && git commit -m "docs(d17): implementation plan"`

---

### Task 1: Spec-schema validator (`specs.py`) — the shared contract

**Files:**
- Create: `backend/core/modules/directory/specs.py`
- Test: `backend/core/tests/test_spec_validator.py`

**Interfaces (Produces):**
```python
MAX_SCHEMA_FIELDS = 50
MAX_SPEC_STRING_LEN = 500

class SpecValidationError(ValueError):
    def __init__(self, code: str, field: str | None = None) -> None:
        self.code = code          # machine-readable, becomes the API 422 detail
        self.field = field
        super().__init__(f"{code}: {field}" if field else code)

class FieldDef(BaseModel): ...     # full definition below

def parse_fields(raw: object) -> list[FieldDef]      # validates a fields JSONB payload
def validate_specs(specs: object, fields: list[FieldDef]) -> dict[str, object]  # returns specs as plain dict
```

- [ ] **Step 1: Write the failing tests** (`tests/test_spec_validator.py`) — pure unit, no DB. Cover, at minimum:

```python
"""D17 spec-schema validator: the contract every future vertical rides.
Unknown field rejected, wrong type rejected, version pinning is the
caller's job (service tests) - here the validator itself is hardened."""

import pytest

from modules.directory.specs import (
    MAX_SCHEMA_FIELDS,
    MAX_SPEC_STRING_LEN,
    FieldDef,
    SpecValidationError,
    parse_fields,
    validate_specs,
)

MILK_FIELDS_RAW = [
    {"key": "milk_type", "label": {"en": "Milk type"}, "type": "enum",
     "options": ["cow", "buffalo", "a2", "toned", "organic"],
     "required": True, "filterable": True, "facet": True, "group": "basics"},
    {"key": "fat_percent", "label": {"en": "Fat %"}, "type": "number",
     "unit": "%", "min": 0, "max": 15, "filterable": True, "comparable": True},
    {"key": "pack_size", "label": {"en": "Pack size"}, "type": "enum",
     "options": ["250ml", "500ml", "1l", "5l"], "filterable": True, "facet": True},
    {"key": "farm_fresh", "label": {"en": "Farm fresh"}, "type": "boolean"},
    {"key": "brand", "label": {"en": "Brand"}, "type": "string"},
]


def fields() -> list[FieldDef]:
    return parse_fields(MILK_FIELDS_RAW)


# --- parse_fields (schema-definition hardening) ---------------------------

def test_parse_valid_fields_roundtrip() -> None:
    parsed = fields()
    assert [f.key for f in parsed] == [
        "milk_type", "fat_percent", "pack_size", "farm_fresh", "brand"]

@pytest.mark.parametrize("bad", [
    "not-a-list", {}, [{"key": "x"}],                      # shape
    [{**MILK_FIELDS_RAW[0], "key": "Bad Key!"}],           # key pattern
    [{**MILK_FIELDS_RAW[0], "type": "json"}],              # unknown type
    [{**MILK_FIELDS_RAW[0], "extra_attr": 1}],             # extra=forbid
    [{**MILK_FIELDS_RAW[0], "label": {"fr": "Lait"}}],     # bad locale
    [{**MILK_FIELDS_RAW[0], "label": {"ta": "பால்"}}],      # missing en
    [{**MILK_FIELDS_RAW[0], "options": None}],             # enum w/o options
    [{**MILK_FIELDS_RAW[0], "options": []}],               # empty options
    [{**MILK_FIELDS_RAW[0], "options": ["a", "a"]}],       # dup options
    [{**MILK_FIELDS_RAW[4], "options": ["x"]}],            # options on non-enum
    [{**MILK_FIELDS_RAW[4], "min": 1}],                    # min on non-number
    [{**MILK_FIELDS_RAW[4], "unit": "kg"}],                # unit on non-number
    [{**MILK_FIELDS_RAW[1], "min": 10, "max": 1}],         # min > max
    MILK_FIELDS_RAW + MILK_FIELDS_RAW[:1],                 # duplicate key
])
def test_parse_rejects_bad_definitions(bad: object) -> None:
    with pytest.raises(SpecValidationError) as excinfo:
        parse_fields(bad)
    assert excinfo.value.code == "invalid_field_definition"

def test_parse_rejects_too_many_fields() -> None:
    many = [{**MILK_FIELDS_RAW[4], "key": f"f{i}"} for i in range(MAX_SCHEMA_FIELDS + 1)]
    with pytest.raises(SpecValidationError):
        parse_fields(many)

# --- validate_specs (write-path hardening) --------------------------------

def test_valid_specs_pass_and_normalize() -> None:
    out = validate_specs(
        {"milk_type": "a2", "fat_percent": 4.5, "farm_fresh": True, "brand": "Aavin"},
        fields())
    assert out["milk_type"] == "a2"

def test_missing_optional_fields_are_fine() -> None:
    assert validate_specs({"milk_type": "cow"}, fields()) == {"milk_type": "cow"}

@pytest.mark.parametrize("specs,code,field", [
    ("not-a-dict", "invalid_specs", None),
    ([1, 2], "invalid_specs", None),
    ({"milk_type": "cow", "hacked": 1}, "unknown_field", "hacked"),      # schema injection
    ({}, "missing_required", "milk_type"),
    ({"milk_type": "goat"}, "invalid_enum_value", "milk_type"),
    ({"milk_type": 3}, "wrong_type", "milk_type"),
    ({"milk_type": "cow", "fat_percent": "high"}, "wrong_type", "fat_percent"),
    ({"milk_type": "cow", "fat_percent": True}, "wrong_type", "fat_percent"),  # bool is not number
    ({"milk_type": "cow", "fat_percent": 99}, "out_of_range", "fat_percent"),
    ({"milk_type": "cow", "farm_fresh": "yes"}, "wrong_type", "farm_fresh"),
    ({"milk_type": "cow", "brand": 7}, "wrong_type", "brand"),
    ({"milk_type": "cow", "brand": "x" * (MAX_SPEC_STRING_LEN + 1)}, "too_long", "brand"),
    ({"milk_type": "cow", "brand": {"nested": "obj"}}, "wrong_type", "brand"),
])
def test_specs_rejections(specs: object, code: str, field: str | None) -> None:
    with pytest.raises(SpecValidationError) as excinfo:
        validate_specs(specs, fields())
    assert (excinfo.value.code, excinfo.value.field) == (code, field)
```

- [ ] **Step 2:** `python -m pytest tests/test_spec_validator.py -q` → FAIL (module missing)
- [ ] **Step 3: Implement `modules/directory/specs.py`:**

```python
"""Versioned spec-schema validation (D17) - THE contract every vertical
rides. A schema version's `fields` JSONB is parsed by parse_fields();
product specs are validated by validate_specs() on every write against the
version being pinned. Reads never re-validate: old products keep rendering
after a new schema version ships (non-negotiable 1)."""

import re

from pydantic import BaseModel, ConfigDict, ValidationError, field_validator, model_validator

from shared.i18n import Translated

MAX_SCHEMA_FIELDS = 50
MAX_SPEC_STRING_LEN = 500
_KEY_RE = re.compile(r"^[a-z][a-z0-9_]{0,63}$")


class SpecValidationError(ValueError):
    """Machine-readable rejection; .code becomes the API 422 detail."""

    def __init__(self, code: str, field: str | None = None) -> None:
        self.code = code
        self.field = field
        super().__init__(f"{code}: {field}" if field else code)


class FieldDef(BaseModel):
    model_config = ConfigDict(extra="forbid")

    key: str
    label: dict[str, str]           # i18n, must include "en" (Translated locales only)
    type: str                       # string | number | boolean | enum
    unit: str | None = None         # number fields only
    options: list[str] | None = None  # enum fields only, non-empty, unique
    min: float | None = None        # number fields only
    max: float | None = None
    required: bool = False
    filterable: bool = False
    comparable: bool = False
    facet: bool = False
    group: str | None = None

    @field_validator("key")
    @classmethod
    def _key_shape(cls, v: str) -> str:
        if not _KEY_RE.fullmatch(v):
            raise ValueError(f"bad field key: {v!r}")
        return v

    @field_validator("type")
    @classmethod
    def _known_type(cls, v: str) -> str:
        if v not in ("string", "number", "boolean", "enum"):
            raise ValueError(f"unknown field type: {v!r}")
        return v

    @field_validator("label")
    @classmethod
    def _label_i18n(cls, v: dict[str, str]) -> dict[str, str]:
        Translated.from_dict(v)     # locale allowlist + string values
        if not v.get("en"):
            raise ValueError("label must include en")
        return v

    @model_validator(mode="after")
    def _cross_checks(self) -> "FieldDef":
        if self.type == "enum":
            if not self.options or len(set(self.options)) != len(self.options):
                raise ValueError("enum fields need non-empty unique options")
        elif self.options is not None:
            raise ValueError("options only allowed on enum fields")
        if self.type != "number" and (
            self.min is not None or self.max is not None or self.unit is not None
        ):
            raise ValueError("min/max/unit only allowed on number fields")
        if self.min is not None and self.max is not None and self.min > self.max:
            raise ValueError("min > max")
        return self


def parse_fields(raw: object) -> list[FieldDef]:
    """Validate a schema version's fields payload (admin write path)."""
    if not isinstance(raw, list) or not raw or len(raw) > MAX_SCHEMA_FIELDS:
        raise SpecValidationError("invalid_field_definition")
    parsed: list[FieldDef] = []
    for item in raw:
        try:
            parsed.append(FieldDef.model_validate(item))
        except ValidationError as exc:
            key = item.get("key") if isinstance(item, dict) else None
            raise SpecValidationError("invalid_field_definition", key) from exc
    keys = [f.key for f in parsed]
    if len(set(keys)) != len(keys):
        raise SpecValidationError("invalid_field_definition")
    return parsed


def validate_specs(specs: object, fields: list[FieldDef]) -> dict[str, object]:
    """Validate product specs against a parsed schema version (write path)."""
    if not isinstance(specs, dict):
        raise SpecValidationError("invalid_specs")
    by_key = {f.key: f for f in fields}
    for key in specs:
        if key not in by_key:
            raise SpecValidationError("unknown_field", key)
    for field in fields:
        if field.required and key_missing(specs, field.key):
            raise SpecValidationError("missing_required", field.key)
    for key, value in specs.items():
        _check_value(by_key[key], value)
    return dict(specs)


def key_missing(specs: dict[str, object], key: str) -> bool:
    return key not in specs or specs[key] is None


def _check_value(field: FieldDef, value: object) -> None:
    if field.type == "string":
        if not isinstance(value, str):
            raise SpecValidationError("wrong_type", field.key)
        if len(value) > MAX_SPEC_STRING_LEN:
            raise SpecValidationError("too_long", field.key)
    elif field.type == "boolean":
        if not isinstance(value, bool):
            raise SpecValidationError("wrong_type", field.key)
    elif field.type == "number":
        # bool is an int subclass - reject it explicitly
        if isinstance(value, bool) or not isinstance(value, int | float):
            raise SpecValidationError("wrong_type", field.key)
        if (field.min is not None and value < field.min) or (
            field.max is not None and value > field.max
        ):
            raise SpecValidationError("out_of_range", field.key)
    else:  # enum
        if not isinstance(value, str):
            raise SpecValidationError("wrong_type", field.key)
        assert field.options is not None  # guaranteed by FieldDef._cross_checks
        if value not in field.options:
            raise SpecValidationError("invalid_enum_value", field.key)
```

- [ ] **Step 4:** `python -m pytest tests/test_spec_validator.py -q` → all PASS
- [ ] **Step 5:** `ruff format modules/directory/specs.py tests/test_spec_validator.py && ruff check --fix . && mypy .` → clean
- [ ] **Step 6:** Commit: `git commit -m "feat(d17): spec-schema validator - the vertical contract"`

---

### Task 2: Migration 0018 + ORM models + migration tests

**Files:**
- Create: `backend/core/alembic/versions/0018_catalog_v1.py`
- Create: `backend/core/modules/directory/catalog_models.py`
- Test: `backend/core/tests/test_catalog_migration.py`

**Interfaces (Produces):** ORM classes `Vertical` (table `directory.vertical_registry`), `SpecSchema` (`directory.spec_schemas`), `Product` (`directory.products`); enums `directory.vertical_status` (`active|hidden`), `directory.product_status` (`active|archived`). Seeds: milk vertical, milk schema v1, feature flag `catalog_schema_admin` (disabled).

- [ ] **Step 1: Write failing migration tests** (`tests/test_catalog_migration.py`, mirror `tests/test_directory_migration.py` style):

```python
"""D17 migration: catalog tables exist in schema directory, milk vertical +
schema v1 seeded, spec_schemas is append-only for app_rt (grant-level),
products/registry stay fully mutable for app_rt."""

import pytest
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

pytestmark = pytest.mark.asyncio


async def test_catalog_tables_exist(db_session: AsyncSession) -> None:
    tables = set((await db_session.execute(text(
        "SELECT tablename FROM pg_tables WHERE schemaname = 'directory'"
    ))).scalars().all())
    assert {"vertical_registry", "spec_schemas", "products"} <= tables


async def test_milk_vertical_seeded_active(db_session: AsyncSession) -> None:
    row = (await db_session.execute(text(
        "SELECT slug, status, engines_enabled->>'catalog' AS catalog "
        "FROM directory.vertical_registry WHERE slug = 'milk'"))).one()
    assert (row.slug, row.status, row.catalog) == ("milk", "active", "true")


async def test_milk_schema_v1_seeded(db_session: AsyncSession) -> None:
    row = (await db_session.execute(text(
        "SELECT version, jsonb_array_length(fields) AS n "
        "FROM directory.spec_schemas WHERE vertical_slug = 'milk'"))).one()
    assert (row.version, row.n) == (1, 3)


async def test_schema_admin_flag_seeded_disabled(db_session: AsyncSession) -> None:
    enabled = await db_session.scalar(text(
        "SELECT enabled FROM public.feature_flags WHERE key = 'catalog_schema_admin'"))
    assert enabled is False


async def test_app_rt_cannot_mutate_spec_schemas(db_session: AsyncSession) -> None:
    # db_session connects as app_rt: INSERT allowed, UPDATE/DELETE revoked
    await db_session.execute(text(
        "INSERT INTO directory.spec_schemas (id, vertical_slug, version, fields) "
        "VALUES (gen_random_uuid(), 'milk', 99, '[]'::jsonb)"))
    with pytest.raises(Exception):  # noqa: B017 - InsufficientPrivilege wrapping varies
        await db_session.execute(text(
            "UPDATE directory.spec_schemas SET version = 100 WHERE version = 99"))


async def test_app_rt_full_dml_on_products(db_session: AsyncSession) -> None:
    business_id = await db_session.scalar(text(
        "INSERT INTO directory.businesses (id, name, slug, type, primary_pincode) "
        "VALUES (gen_random_uuid(), 'P', 'prod-dml', 'vendor', '641001') RETURNING id"))
    await db_session.execute(text(
        "INSERT INTO directory.products (id, business_id, vertical_slug, schema_version, "
        "name, slug, specs) VALUES (gen_random_uuid(), :b, 'milk', 1, 'X', 'x-dml', "
        "'{}'::jsonb)"), {"b": business_id})
    row = (await db_session.execute(text(
        "SELECT status, moderation_status FROM directory.products WHERE slug = 'x-dml'"))).one()
    assert (row.status, row.moderation_status) == ("active", "pending")
    await db_session.execute(text("DELETE FROM directory.products WHERE slug = 'x-dml'"))
```

- [ ] **Step 2:** `python -m pytest tests/test_catalog_migration.py -q` → FAIL (tables missing)
- [ ] **Step 3: Write `alembic/versions/0018_catalog_v1.py`** (revision `"0018"`, down_revision `"0017"`; follow 0017's structure — `pk_column()`, `timestamp_columns()`, enums with `create_type=False` columns after explicit `sa.Enum(...).create(bind, checkfirst=True)`):

```python
# backend/core/alembic/versions/0018_catalog_v1.py
"""D17 vertical registry + versioned spec-schemas + products (catalog E2 in
basic form, hosted in schema directory). Seeds the milk vertical, milk spec
schema v1, and the catalog_schema_admin flag (disabled).

Revision ID: 0018
Revises: 0017
Create Date: 2026-07-17

"""
# -- THREAT/NOTES:
# downgrade data loss: drops products (all product listings + media keys),
#   spec_schemas (every version), vertical_registry, and the
#   catalog_schema_admin flag. Media objects in the bucket are NOT deleted
#   (orphaned keys - same accepted trade-off as D16 evidence docs).
# locks: CREATE TABLE/TYPE on empty objects, small seed inserts. Negligible.
# rollout: tables ship empty except seeds. 0013 default privileges give
#   app_rt blanket DML on new directory tables; spec_schemas then gets
#   UPDATE/DELETE REVOKED - schema versions are append-only BY GRANT
#   (a published version is pinned by products; changing it would corrupt
#   their rendering contract - publish version N+1 instead).
# schema-injection defence: fields JSONB is validated by
#   modules/directory/specs.parse_fields on every admin write; product specs
#   are validated against the pinned version on every write.
```

`upgrade()` (exact DDL):
1. `sa.Enum("active", "hidden", name="vertical_status", schema="directory").create(bind, checkfirst=True)` and `sa.Enum("active", "archived", name="product_status", schema="directory").create(bind, checkfirst=True)`.
2. `vertical_registry`: `pk_column()`, `slug` Text NOT NULL UNIQUE, `name` JSONB NOT NULL, `engines_enabled` JSONB NOT NULL server_default `'{}'`, `nav_placement` JSONB NOT NULL server_default `'{}'`, `status` vertical_status NOT NULL server_default `'active'`, `*timestamp_columns()`, schema `directory`.
3. `spec_schemas`: `pk_column()`, `vertical_slug` Text NOT NULL FK → `directory.vertical_registry.slug`, `version` sa.Integer NOT NULL, `fields` JSONB NOT NULL, `*timestamp_columns()`, `sa.UniqueConstraint("vertical_slug", "version", name="uq_spec_schemas_vertical_slug_version")`, schema `directory`.
4. `products`: `pk_column()`, `business_id` UUID NOT NULL FK → `directory.businesses.id` (index), `vertical_slug` Text NOT NULL FK → `directory.vertical_registry.slug` (index), `schema_version` sa.Integer NOT NULL, `name` Text NOT NULL, `slug` Text NOT NULL UNIQUE (index), `specs` JSONB NOT NULL server_default `'{}'`, `price_display` Text NULL, `media_keys` JSONB NOT NULL server_default `'[]'`, `status` product_status NOT NULL server_default `'active'`, `moderation_status` `postgresql.ENUM(name="moderation_status", schema="public", create_type=False)` NOT NULL server_default `'pending'`, `deleted_at` TIMESTAMP(timezone=True) NULL, `*timestamp_columns()`, schema `directory`. Extra index: `ix_directory_products_moderation_status_id` on `(moderation_status, id)` (admin queue paging).
5. Grants: `GRANT SELECT, INSERT, UPDATE, DELETE ON ALL TABLES IN SCHEMA "directory" TO app_rt` (belt-and-braces, 0016/0017 precedent) then `REVOKE UPDATE, DELETE ON directory.spec_schemas FROM app_rt`.
6. Seed milk vertical (`op.bulk_insert` on a `sa.table` helper, 0017 pattern; JSONB via `postgresql.JSONB` columns):
   - `slug="milk"`, `name={"en": "Milk", "ta": "பால்", "hi": "दूध"}`, `engines_enabled={"directory": True, "catalog": True, "reviews": True, "leads": True, "search": True}`, `nav_placement={"header": True, "order": 1}`, `status="active"`, `id=uuid6.uuid7()`.
7. Seed milk spec schema v1 (`vertical_slug="milk"`, `version=1`, `id=uuid6.uuid7()`) with `fields`:

```python
MILK_SCHEMA_V1_FIELDS = [
    {"key": "milk_type",
     "label": {"en": "Milk type", "ta": "பால் வகை", "hi": "दूध का प्रकार"},
     "type": "enum", "options": ["cow", "buffalo", "a2", "toned", "organic"],
     "required": True, "filterable": True, "facet": True, "group": "basics"},
    {"key": "fat_percent",
     "label": {"en": "Fat %", "ta": "கொழுப்பு %", "hi": "वसा %"},
     "type": "number", "unit": "%", "min": 0, "max": 15,
     "filterable": True, "comparable": True, "group": "nutrition"},
    {"key": "pack_size",
     "label": {"en": "Pack size", "ta": "பேக் அளவு", "hi": "पैक आकार"},
     "type": "enum", "options": ["250ml", "500ml", "1l", "5l", "bulk"],
     "filterable": True, "facet": True, "group": "basics"},
]
```
8. Seed flag: `INSERT INTO public.feature_flags (key, enabled, description) VALUES ('catalog_schema_admin', false, 'Gates spec-schema version creation via /admin/catalog')` (`op.execute` with literal SQL is fine — flags table has server-default timestamps).

`downgrade()`: delete flag row → `op.drop_table("products", schema="directory")` → `drop_table("spec_schemas")` → `drop_table("vertical_registry")` → drop the two enums (`checkfirst=True`).

- [ ] **Step 4: Write `modules/directory/catalog_models.py`** mirroring the migration exactly:

```python
"""Catalog ORM models (D17) - mirrors migration 0018 exactly. Hosted in the
directory module: product writes must IDOR-check business ownership, and the
module-independence contract (import-linter) forbids a separate catalog
module from reading directory tables. URL namespace is /catalog/* so the
Stage-B extraction never breaks public URLs."""

import uuid
from typing import Any

from sqlalchemy import ForeignKey, Index, Integer, Text, UniqueConstraint
from sqlalchemy.dialects import postgresql
from sqlalchemy.orm import Mapped, mapped_column

from shared.db import Base, SoftDeleteMixin, TimestampMixin, UGCMixin, UUIDv7PKMixin
from shared.i18n import Translated, TranslatedString
from shared.slugs import ImmutableSlugMixin

vertical_status_enum = postgresql.ENUM(
    "active", "hidden", name="vertical_status", schema="directory", create_type=False
)
product_status_enum = postgresql.ENUM(
    "active", "archived", name="product_status", schema="directory", create_type=False
)


class Vertical(UUIDv7PKMixin, TimestampMixin, Base):
    __tablename__ = "vertical_registry"
    __table_args__ = {"schema": "directory"}

    slug: Mapped[str] = mapped_column(Text, nullable=False, unique=True)
    name: Mapped[Translated] = mapped_column(TranslatedString, nullable=False)
    engines_enabled: Mapped[dict[str, Any]] = mapped_column(
        postgresql.JSONB, nullable=False, server_default="{}"
    )
    nav_placement: Mapped[dict[str, Any]] = mapped_column(
        postgresql.JSONB, nullable=False, server_default="{}"
    )
    status: Mapped[str] = mapped_column(
        vertical_status_enum, nullable=False, server_default="active"
    )


class SpecSchema(UUIDv7PKMixin, TimestampMixin, Base):
    """Append-only schema versions (UPDATE/DELETE revoked from app_rt in
    0018): a published version is pinned by products - publish N+1 to change."""

    __tablename__ = "spec_schemas"
    __table_args__ = (
        UniqueConstraint("vertical_slug", "version", name="uq_spec_schemas_vertical_slug_version"),
        {"schema": "directory"},
    )

    vertical_slug: Mapped[str] = mapped_column(
        Text, ForeignKey("directory.vertical_registry.slug"), nullable=False, index=True
    )
    version: Mapped[int] = mapped_column(Integer, nullable=False)
    fields: Mapped[list[dict[str, Any]]] = mapped_column(postgresql.JSONB, nullable=False)


class Product(UUIDv7PKMixin, TimestampMixin, SoftDeleteMixin, ImmutableSlugMixin, UGCMixin, Base):
    __tablename__ = "products"
    __table_args__ = (
        Index("ix_directory_products_moderation_status_id", "moderation_status", "id"),
        {"schema": "directory"},
    )

    business_id: Mapped[uuid.UUID] = mapped_column(
        postgresql.UUID(as_uuid=True),
        ForeignKey("directory.businesses.id"),
        nullable=False,
        index=True,
    )
    vertical_slug: Mapped[str] = mapped_column(
        Text, ForeignKey("directory.vertical_registry.slug"), nullable=False, index=True
    )
    schema_version: Mapped[int] = mapped_column(Integer, nullable=False)
    name: Mapped[str] = mapped_column(Text, nullable=False)
    specs: Mapped[dict[str, Any]] = mapped_column(
        postgresql.JSONB, nullable=False, server_default="{}"
    )
    price_display: Mapped[str | None] = mapped_column(Text, nullable=True)
    media_keys: Mapped[list[str]] = mapped_column(
        postgresql.JSONB, nullable=False, server_default="[]"
    )
    status: Mapped[str] = mapped_column(
        product_status_enum, nullable=False, server_default="active"
    )
```

- [ ] **Step 5:** `python -m pytest tests/test_catalog_migration.py tests/test_lint_contracts.py -q` → PASS (lint contract check confirms THREAT/NOTES present). Also run the alembic loader sanity: `python -m pytest tests/test_directory_migration.py -q` (chain still linear).
- [ ] **Step 6:** `ruff format --check . && ruff check . && mypy . && lint-imports` → clean
- [ ] **Step 7:** Commit: `git commit -m "feat(d17): migration 0018 - vertical_registry, spec_schemas, products + milk seed"`

---

### Task 3: Registry + schema service functions

**Files:**
- Create: `backend/core/modules/directory/catalog_service.py`
- Test: `backend/core/tests/test_catalog_service.py` (registry/schema half)

**Interfaces (Produces):**
```python
class VerticalNotFoundError(Exception): ...
class SchemaNotFoundError(Exception): ...

async def list_verticals(session, *, cursor=None, limit=DEFAULT_PAGE_SIZE) -> Page[Vertical]  # active only
async def get_vertical(session, slug: str) -> Vertical | None
async def active_schema(session, vertical_slug: str) -> SpecSchema | None   # MAX(version)
async def get_schema(session, vertical_slug: str, version: int) -> SpecSchema | None
async def list_schema_versions(session, vertical_slug: str) -> list[SpecSchema]  # ordered by version
async def create_schema_version(session, *, vertical_slug: str, fields_raw: object) -> SpecSchema
```

- [ ] **Step 1: Write failing tests** (in `tests/test_catalog_service.py`; use `db_session` fixture; milk vertical + v1 schema already seeded by 0018):

```python
async def test_active_schema_is_highest_version(db_session): ...
    # seeded milk v1 -> create_schema_version(fields v2) -> active_schema().version == 2

async def test_create_schema_version_validates_fields(db_session): ...
    # fields_raw=[{"key": "Bad!"}] -> SpecValidationError("invalid_field_definition")

async def test_create_schema_version_unknown_vertical(db_session): ...
    # vertical_slug="tractors" -> VerticalNotFoundError

async def test_list_verticals_hides_hidden(db_session): ...
    # insert a hidden Vertical row directly; list_verticals returns only milk
```

Each test body written out fully at implementation time following the assertions above (create v2 by passing the three seeded milk fields plus one extra `{"key": "source_farm", "label": {"en": "Source farm"}, "type": "string"}`).

- [ ] **Step 2:** Run → FAIL. **Step 3: Implement** in `catalog_service.py`:

```python
"""Catalog service (D17): vertical registry reads, append-only schema
versions, schema-validated products. Writes are owner-scoped through
modules.directory.service.get_owned_business (same-module import - this is
WHY catalog lives in the directory module)."""

import uuid
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from modules.directory.catalog_models import Product, SpecSchema, Vertical
from modules.directory.service import BusinessNotFoundError, _slugify, get_owned_business
from modules.directory.specs import parse_fields, validate_specs
from shared.pagination import DEFAULT_PAGE_SIZE, Page, paginate


class VerticalNotFoundError(Exception):
    """Unknown or hidden vertical."""


class SchemaNotFoundError(Exception):
    """Vertical has no schema version yet - products cannot be created."""


async def list_verticals(
    session: AsyncSession, *, cursor: str | None = None, limit: int = DEFAULT_PAGE_SIZE
) -> Page[Vertical]:
    return await paginate(
        session, select(Vertical).where(Vertical.status == "active"), cursor=cursor, limit=limit
    )


async def get_vertical(session: AsyncSession, slug: str) -> Vertical | None:
    return await session.scalar(select(Vertical).where(Vertical.slug == slug))


async def active_schema(session: AsyncSession, vertical_slug: str) -> SpecSchema | None:
    return await session.scalar(
        select(SpecSchema)
        .where(SpecSchema.vertical_slug == vertical_slug)
        .order_by(SpecSchema.version.desc())
        .limit(1)
    )


async def get_schema(session: AsyncSession, vertical_slug: str, version: int) -> SpecSchema | None:
    return await session.scalar(
        select(SpecSchema).where(
            SpecSchema.vertical_slug == vertical_slug, SpecSchema.version == version
        )
    )


async def list_schema_versions(session: AsyncSession, vertical_slug: str) -> list[SpecSchema]:
    rows = await session.scalars(
        select(SpecSchema)
        .where(SpecSchema.vertical_slug == vertical_slug)
        .order_by(SpecSchema.version)
    )
    return list(rows.all())


async def create_schema_version(
    session: AsyncSession, *, vertical_slug: str, fields_raw: object
) -> SpecSchema:
    """Append the next version. parse_fields raises SpecValidationError on a
    malformed definition; versions are immutable once created (grant-enforced)."""
    if await get_vertical(session, vertical_slug) is None:
        raise VerticalNotFoundError(vertical_slug)
    fields = parse_fields(fields_raw)
    current = await session.scalar(
        select(func.max(SpecSchema.version)).where(SpecSchema.vertical_slug == vertical_slug)
    )
    schema = SpecSchema(
        vertical_slug=vertical_slug,
        version=(current or 0) + 1,
        fields=[f.model_dump(exclude_none=True) for f in fields],
    )
    session.add(schema)
    await session.flush()
    return schema
```

- [ ] **Step 4:** Run tests → PASS. **Step 5:** format/lint/mypy clean. **Step 6:** Commit `feat(d17): registry + schema-version service`.

---

### Task 4: Product service — create/update/list/moderate, version pinning (NN#1)

**Files:**
- Modify: `backend/core/modules/directory/catalog_service.py` (append)
- Test: `backend/core/tests/test_catalog_service.py` (product half)

**Interfaces (Produces):**
```python
PRODUCT_MUTABLE_FIELDS = {"name", "specs", "price_display", "status"}
MAX_PRODUCT_IMAGES = 8

class ProductNotFoundError(Exception): ...

async def create_product(session, *, owner_user_id, business_id, vertical_slug,
                         name, specs, price_display=None) -> Product
async def update_product(session, *, owner_user_id, product_id, patch: dict) -> Product
async def get_owned_product(session, owner_user_id, product_id) -> Product
async def list_my_products(session, owner_user_id, business_id, *, cursor=None, limit=...) -> Page[Product]
async def add_product_image(session, *, owner_user_id, product_id, key: str) -> Product
async def remove_product_image(session, *, owner_user_id, product_id, index: int) -> Product
# public reads
async def get_public_product(session, slug: str) -> tuple[Product, Business] | None
async def list_business_products(session, business_slug: str, *, cursor=None, limit=...) -> Page[Product]
async def list_vertical_products(session, vertical_slug: str, *, cursor=None, limit=...) -> Page[Product]
# moderation (admin)
async def list_products_for_moderation(session, *, status: str, cursor=None, limit=...) -> Page[Product]
async def moderate_product(session, *, product_id, approve: bool) -> Product
```

**Semantics (locked):**
- `create_product`: `get_owned_business` (IDOR — non-owner ⇒ `BusinessNotFoundError` ⇒ 404), vertical must exist AND be `active` (else `VerticalNotFoundError`), `active_schema` must exist (else `SchemaNotFoundError`), `validate_specs` against it, **pin `schema_version = active.version`**, slug from `_slugify(name)` with `-2/-3...` suffixing against `Product` (`include_deleted=True`, copy `_free_slug` shape from `service.py:47` — local `_free_product_slug`).
- `update_product`: unknown/immutable patch keys ⇒ `ValueError` (mirrors `service.update_business`); if `"specs"` in patch ⇒ validate against the **current active** schema version and **re-pin** (a write opts into the current contract; untouched products keep their old pin — this is the version-pinning contract); `status` must be `active|archived`; **name change does NOT change slug** (immutable, no product rename endpoint in D17).
- `moderate_product`: sets `moderation_status` to `approved`/`rejected`. No FOR-UPDATE dance needed (idempotent single-column flip, unlike claim approval's multi-row choreography).
- Public reads filter: product `moderation_status == "approved"`, `status == "active"`, soft-delete default filter, and owning business `status == "active"` (join). `list_vertical_products` also requires the vertical to be `active` (hidden vertical ⇒ empty page).

- [ ] **Step 1: Write failing tests.** The critical ones in full:

```python
MILK_V2_EXTRA = {"key": "source_farm", "label": {"en": "Source farm"},
                 "type": "string", "required": True}

async def _business(session, owner):  # helper
    return await service.create_business(
        session, owner_user_id=owner, name="Coimbatore Dairy",
        type_="vendor", primary_pincode="641001")

async def test_create_product_pins_active_version(db_session):
    owner = uuid.uuid4()
    business = await _business(db_session, owner)
    product = await catalog_service.create_product(
        db_session, owner_user_id=owner, business_id=business.id,
        vertical_slug="milk", name="A2 Full Cream",
        specs={"milk_type": "a2", "fat_percent": 4.5, "pack_size": "500ml"},
        price_display="₹80/500ml")
    assert product.schema_version == 1
    assert product.moderation_status == "pending"   # UGC default
    assert product.slug == "a2-full-cream"

async def test_create_product_rejects_bad_specs(db_session):
    # specs={"milk_type": "goat"} -> SpecValidationError invalid_enum_value
    # specs={"hacked": 1, "milk_type": "cow"} -> unknown_field (schema injection)

async def test_create_product_owner_scoped_idor(db_session):
    # USER_B creating a product on USER_A's business -> BusinessNotFoundError

async def test_old_products_keep_rendering_after_schema_v2(db_session):
    """NON-NEGOTIABLE 1: version pinning honored across schema evolution."""
    owner = uuid.uuid4()
    business = await _business(db_session, owner)
    product = await catalog_service.create_product(
        db_session, owner_user_id=owner, business_id=business.id,
        vertical_slug="milk", name="Old Toned",
        specs={"milk_type": "toned"}, price_display="₹30/500ml")
    await catalog_service.moderate_product(db_session, product_id=product.id, approve=True)
    # schema evolves: v2 adds a REQUIRED field old products don't have
    v1 = await catalog_service.active_schema(db_session, "milk")
    await catalog_service.create_schema_version(
        db_session, vertical_slug="milk", fields_raw=[*v1.fields, MILK_V2_EXTRA])
    # old product still publicly renders with its pinned v1
    got = await catalog_service.get_public_product(db_session, product.slug)
    assert got is not None and got[0].schema_version == 1
    # new writes must satisfy v2
    with pytest.raises(SpecValidationError) as excinfo:
        await catalog_service.create_product(
            db_session, owner_user_id=owner, business_id=business.id,
            vertical_slug="milk", name="New Cow", specs={"milk_type": "cow"})
    assert excinfo.value.code == "missing_required"
    # editing the old product's specs re-pins to v2 and re-validates
    updated = await catalog_service.update_product(
        db_session, owner_user_id=owner, product_id=product.id,
        patch={"specs": {"milk_type": "toned", "source_farm": "Anaimalai"}})
    assert updated.schema_version == 2

async def test_public_reads_hide_pending_archived_and_suspended(db_session):
    # pending product -> get_public_product None; approve -> visible;
    # patch status=archived -> None; business suspended -> None

async def test_no_schema_no_products(db_session):
    # insert a fresh Vertical("seeds") without schema; create_product -> SchemaNotFoundError

async def test_hidden_vertical_rejects_creates_and_empties_lists(db_session): ...
async def test_slug_collision_suffixes(db_session): ...          # a2-full-cream-2
async def test_update_rejects_immutable_fields(db_session): ...  # {"slug": ...} / {"business_id": ...} -> ValueError
async def test_image_add_remove_and_cap(db_session): ...         # 8 max, 9th -> ValueError; remove by index
async def test_list_my_products_shows_pending(db_session): ...   # owner sees all statuses; keyset cursor walks
```

- [ ] **Step 2:** Run → FAIL. **Step 3: Implement** (append to `catalog_service.py`). Core write path:

```python
async def create_product(
    session: AsyncSession,
    *,
    owner_user_id: uuid.UUID,
    business_id: uuid.UUID,
    vertical_slug: str,
    name: str,
    specs: dict[str, Any],
    price_display: str | None = None,
) -> Product:
    await get_owned_business(session, owner_user_id, business_id)  # IDOR gate
    vertical = await get_vertical(session, vertical_slug)
    if vertical is None or vertical.status != "active":
        raise VerticalNotFoundError(vertical_slug)
    schema = await active_schema(session, vertical_slug)
    if schema is None:
        raise SchemaNotFoundError(vertical_slug)
    validated = validate_specs(specs, parse_fields(schema.fields))
    product = Product(
        business_id=business_id,
        vertical_slug=vertical_slug,
        schema_version=schema.version,   # pinned at write time (NN#1)
        name=name,
        slug=await _free_product_slug(session, _slugify(name)),
        specs=validated,
        price_display=price_display,
    )
    session.add(product)
    await session.flush()
    await session.refresh(product)      # server defaults: status, moderation_status
    return product
```

`get_owned_product` = `select(Product).where(Product.id == product_id)` then `get_owned_business(session, owner_user_id, product.business_id)` (parent-ownership gate, `update_branch` precedent — missing and not-yours both raise ⇒ router 404s identically). `update_product` re-pins on specs write as tested above. Public reads join `Business` on `business_id` with `Business.status == "active"`; `paginate()` for all lists (single-entity queries — for business/vertical lists select `Product` and filter by resolved business id / vertical slug). `add_product_image` appends to a **new list** (`product.media_keys = [*product.media_keys, key]` — JSONB in-place mutation is not change-tracked), cap `MAX_PRODUCT_IMAGES`.

- [ ] **Step 4:** `python -m pytest tests/test_catalog_service.py -q` → PASS. **Step 5:** format/lint/mypy. **Step 6:** Commit `feat(d17): schema-validated products - pinned versions, owner-scoped writes`.

---

### Task 5: DTOs + owner/public routers + wiring

**Files:**
- Create: `backend/core/modules/directory/catalog_schemas.py`
- Create: `backend/core/modules/directory/catalog_router.py`
- Modify: `backend/core/main.py` (import + `MODULE_ROUTERS` — add `catalog_router`, `catalog_admin_router` placeholder comes in Task 7)
- Modify: `backend/core/public_routes.txt`
- Test: `backend/core/tests/test_catalog_router.py`

**Routes (Produces):**

| Route | Auth | Notes |
|---|---|---|
| `POST /catalog/businesses/{business_id}/products` | owner | 201; SpecValidationError ⇒ 422 `{code, field}`; VerticalNotFound ⇒ 404; SchemaNotFound ⇒ 409 `no_schema` |
| `GET /catalog/my/products?business_id=` | owner | all statuses, cursor |
| `PATCH /catalog/products/{product_id}` | owner | mutable: name/specs/price_display/status |
| `GET /catalog/verticals` | **public** | active verticals (SSR nav source), cursor |
| `GET /catalog/products/{slug}` | **public** | approved+active only; includes business name/slug + schema fields for rendering |
| `GET /catalog/businesses/{slug}/products` | **public** | cursor |
| `GET /catalog/verticals/{vertical}/products` | **public** | cursor |

**DTOs** (`catalog_schemas.py`, pydantic BaseModel): `ProductCreateIn` (vertical_slug, name [1–200 chars], specs dict, price_display str|None [≤100 chars]), `ProductPatchIn` (all-optional name/specs/price_display/status), `ProductOut` (id, business_id, vertical_slug, schema_version, name, slug, specs, price_display, status, moderation_status, images: `list[str]` **absolute media-domain URLs**, created_at), `ProductPageOut`, `PublicProductOut` (drops moderation_status; adds business_name, business_slug), `ProductDetailOut` (product + `schema_fields: list[dict]` — the pinned version's fields so SSR can render labels/units/groups without a second call), `VerticalOut` (slug, name dict, engines_enabled, nav_placement), `VerticalPageOut`.

Media URL builder in `catalog_schemas.py`:
```python
def media_url(key: str) -> str:
    return f"{get_settings().media_public_base_url}/{key}"
```
(`media_public_base_url` setting lands in Task 6 — add it here as part of this task if implementing sequentially, or stub images=[] until Task 6; prefer adding the setting in this task so DTOs are final.)

**Router skeleton** (`catalog_router.py`) — mirrors `router.py`/`claims_router.py` exactly: `router = SecureRouter(prefix="/catalog", tags=["catalog"])`, same `_principal_user_id`, same exception→status mapping table as above. Public product detail:

```python
@router.get("/products/{slug}", public=True)
async def get_product_detail(slug: str, session: SessionDep) -> ProductDetailOut:
    """Public product page (SSR source for Milk.in D23). Pending/archived/
    suspended-business -> the same 404. Renders with the PINNED schema
    version - never the active one (old products must keep rendering)."""
    result = await catalog_service.get_public_product(session, slug)
    if result is None:
        raise HTTPException(status_code=404, detail="Product not found")
    product, business = result
    schema = await catalog_service.get_schema(session, product.vertical_slug, product.schema_version)
    return ProductDetailOut(
        product=_public_product_out(product, business),
        schema_fields=schema.fields if schema else [],
    )
```

- [ ] **Step 1: Failing router tests** (`tests/test_catalog_router.py`, copy the `api` + principal-header harness from `tests/test_claims_router.py:47-84`): anon create ⇒ 401; owner create ⇒ 201 with pinned version; bad specs ⇒ 422 with `{"code": "invalid_enum_value", "field": "milk_type"}` detail; IDOR create on someone else's business ⇒ 404; public detail of pending product ⇒ 404, after service-approve ⇒ 200 incl. `schema_fields`; `/catalog/verticals` lists milk without auth; both public lists paginate (create 3, limit 2, follow next_cursor); PATCH status archived hides from public list.
- [ ] **Step 2:** Run → FAIL. **Step 3:** Implement DTOs + router; add to `main.py` `MODULE_ROUTERS` (alphabetical-ish near directory entries: `catalog_router` imported as `from modules.directory.catalog_router import router as catalog_router`); append to `public_routes.txt` (each line justified in the PR):

```
/catalog/verticals
/catalog/products/{slug}
/catalog/businesses/{slug}/products
/catalog/verticals/{vertical}/products
```

- [ ] **Step 4:** `python -m pytest tests/test_catalog_router.py tests/test_main.py -q` and `python scripts/dump_public_routes.py --check` → PASS
- [ ] **Step 5:** format/lint/mypy/lint-imports. **Step 6:** Commit `feat(d17): catalog routers - owner writes + public SSR reads`.

---

### Task 6: Product media — shared helper, media-domain serving, no-fork lint gate

**Files:**
- Modify: `backend/core/settings.py` (add `media_public_base_url: str = "http://localhost:9000/agri-media"` — dev default = MinIO path-style bucket URL; prod env supplies the R2/CDN media domain)
- Modify: `backend/core/shared/storage.py` (add `ensure_prefix_public_read`)
- Modify: `backend/core/modules/directory/catalog_router.py` (image upload/delete routes)
- Modify: `backend/core/tests/lint_checks.py` + `backend/core/tests/test_lint_contracts.py` (media-fork ban)
- Test: `backend/core/tests/test_catalog_media.py`

**Interfaces (Produces):**
```python
# shared/storage.py
async def ensure_prefix_public_read(prefix: str) -> None
    # Sets an anonymous s3:GetObject bucket policy for {bucket}/{prefix}* .
    # Best-effort (try/except + warning log): dev MinIO honours it; prod R2
    # buckets are provisioned with their own public media domain.

# catalog_router.py
PRODUCT_MEDIA_PREFIX = "products/"
POST   /catalog/products/{product_id}/images          # owner; ONE file field "file"
DELETE /catalog/products/{product_id}/images/{index}  # owner
```

**Upload route flow** (the D16 evidence path, single-file — same shared helper, NN#3):
```python
@router.post("/products/{product_id}/images", status_code=201)
async def upload_product_image(
    request: Request, product_id: uuid.UUID, session: SessionDep,
    file: Annotated[UploadFile, File(description="product image (jpeg/png/webp, <=5MiB)")],
) -> ProductOut:
    data = await file.read(media.MAX_IMAGE_BYTES + 1)
    try:
        jpeg, _ = media.reencode_image(data)      # THE shared helper - EXIF gone by construction
    except media.MediaError as exc:
        raise HTTPException(status_code=422, detail=exc.code) from exc
    key = f"{PRODUCT_MEDIA_PREFIX}{uuid6.uuid7().hex}.jpg"
    await _ensure_public_media()                   # once-per-process, best-effort
    try:
        await storage.put_object(key, jpeg, "image/jpeg")   # storage before DB (avatar precedent)
    except storage.StorageError as exc:
        raise HTTPException(status_code=503, detail="storage unavailable") from exc
    try:
        product = await catalog_service.add_product_image(
            session, owner_user_id=_principal_user_id(request), product_id=product_id, key=key)
    except catalog_service.ProductNotFoundError as exc:
        raise HTTPException(status_code=404, detail="Product not found") from exc
    except ValueError as exc:                      # image cap
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    return _product_out(product)
```
`_ensure_public_media()`: module-level `_media_prefix_ready: bool` guard around `storage.ensure_prefix_public_read(PRODUCT_MEDIA_PREFIX)`.

**Lint gate (NN#3 "one shared media helper, no fork"):** add to `tests/lint_checks.py`:

```python
# Any PIL usage outside shared/media.py is a fork of the ONE media helper
# (Sprint-2 rule A5). Matches imports and direct calls; tests/fixtures are
# outside the scanned scope and may build images freely.
_MEDIA_FORK_PATTERNS = (
    re.compile(r"^\s*(from PIL|import PIL)\b"),
    re.compile(r"\bImage\.open\s*\("),
)

def check_media_fork(paths: Iterable[Path], *, allow: Container[Path]) -> list[str]:
    """Return 'file:line: source' for PIL use outside the shared media helper."""
    violations: list[str] = []
    for root in paths:
        files = [root] if root.is_file() else sorted(root.rglob("*.py"))
        for file in files:
            if file in allow:
                continue
            for lineno, line in enumerate(file.read_text(encoding="utf-8").splitlines(), 1):
                if any(pattern.search(line) for pattern in _MEDIA_FORK_PATTERNS):
                    violations.append(f"{file}:{lineno}: {line.strip()}")
    return violations
```

and to `tests/test_lint_contracts.py`:

```python
MEDIA_ALLOWED = {CORE / "shared" / "media.py"}

def test_no_media_helper_fork() -> None:
    violations = check_media_fork(
        [CORE / "main.py", CORE / "settings.py", CORE / "modules", CORE / "shared", VERSIONS],
        allow=MEDIA_ALLOWED)
    assert violations == [], (
        "shared.media.reencode_image is the ONE media helper (Sprint-2 A5); "
        "no module may re-encode images itself:\n" + "\n".join(violations))
```

- [ ] **Step 1: Failing tests** (`tests/test_catalog_media.py`, reuse `object_store` fixture pattern + EXIF-laden JPEG builder from `tests/test_media.py`):
  - upload with GPS-EXIF JPEG ⇒ 201; stored bytes (from `object_store`) re-opened via `PIL` **in the test** have `img.getexif()` empty and format JPEG (NN#2a, EXIF stripped end-to-end);
  - response `images[0]` startswith `get_settings().media_public_base_url` and does **not** start with `https://api.test` (NN#2b, off app domain);
  - stored key startswith `products/` and endswith `.jpg`;
  - text file / 6MiB body ⇒ 422 (`unsupported_type` / `too_large`); 9th image ⇒ 409; non-owner upload/delete ⇒ 404; delete by index removes the key;
  - lint tests above (fork-ban fires on a fixture snippet, clean on the tree).
- [ ] **Step 2:** Run → FAIL. **Step 3:** Implement settings field, storage helper (JSON policy via `json.dumps`, `client.set_bucket_policy`, wrap in `asyncio.to_thread`, `except Exception: logger.warning(...)` with a logger added via `shared.telemetry.get_logger`), routes, lint additions.
- [ ] **Step 4:** `python -m pytest tests/test_catalog_media.py tests/test_lint_contracts.py tests/test_media.py -q` → PASS
- [ ] **Step 5:** format/lint/mypy. **Step 6:** Commit `feat(d17): product media - shared re-encode helper, media-domain URLs, fork lint gate`.

---

### Task 7: Admin router — flag-gated schema CRUD + product moderation

**Files:**
- Create: `backend/core/modules/directory/catalog_admin_router.py`
- Modify: `backend/core/main.py` (add `catalog_admin_router` to `MODULE_ROUTERS`)
- Test: `backend/core/tests/test_catalog_admin.py`

**Routes (Produces):** `admin_router = SecureRouter(prefix="/admin/catalog", tags=["catalog-admin"])`, copying `_require_role` + audit choreography from `modules/directory/admin_router.py` (roles `staff`/`super_admin`; schema WRITES are `super_admin` + flag):

| Route | Gate | Behaviour |
|---|---|---|
| `GET /admin/catalog/schemas/{vertical_slug}` | staff/super_admin | list versions (small, unpaginated list — versions are O(10)) |
| `GET /admin/catalog/schemas/{vertical_slug}/{version}` | staff/super_admin | full fields |
| `POST /admin/catalog/schemas/{vertical_slug}` | super_admin + `flag_enabled("catalog_schema_admin")` else 403 `schema_admin_disabled` | body `{"fields": [...]}` ⇒ 201 next version; `SpecValidationError` ⇒ 422; audit `catalog.schema_created` (meta: vertical_slug, version, field_count) same-session |
| `GET /admin/catalog/products?status=pending` | staff/super_admin | moderation queue, cursor |
| `POST /admin/catalog/products/{product_id}/approve` | staff/super_admin | audit `catalog.product_approved` same-session |
| `POST /admin/catalog/products/{product_id}/reject` | staff/super_admin | body `{"note": str}` required; audit `catalog.product_rejected` (meta includes note) |

No post-commit event publish here (events deferred to D19), so no explicit-commit choreography needed — `get_session` commits at request end, audit rides the same transaction (D12 contract). Registry admin CRUD is deliberately absent (Stage-B item 64); registry changes pre-Stage-B are migrations.

- [ ] **Step 1: Failing tests** (`tests/test_catalog_admin.py`, same `api` harness; flag on = insert `FeatureFlag(key="catalog_schema_admin", enabled=True)`… the row exists seeded false, so flip via `UPDATE` + `reset_flag_cache()`):
  - anon ⇒ 401, plain user ⇒ 403 on every route; staff can read schemas but POST ⇒ 403 (role);
  - super_admin + flag OFF ⇒ 403 `schema_admin_disabled`; flag ON ⇒ 201 version 2, audit row exists (`action="catalog.schema_created"`, check via select on AuditEntry — ORM attr `.meta`);
  - malformed fields ⇒ 422; unknown vertical ⇒ 404;
  - moderation: pending product listed; approve ⇒ public GET now 200 + audit row; reject requires note ⇒ 422 without, 200 with, product stays hidden.
- [ ] **Step 2:** Run → FAIL. **Step 3:** Implement router; wire into `main.py`.
- [ ] **Step 4:** `python -m pytest tests/test_catalog_admin.py -q` → PASS. **Step 5:** format/lint/mypy/lint-imports. **Step 6:** Commit `feat(d17): admin schema versions (flag-gated) + product moderation`.

---

### Task 8: Module docs, full gates, committed-tree verify, PR

**Files:**
- Modify: `backend/core/modules/directory/CLAUDE.md` (add: catalog surface lives here — vertical registry, append-only spec schemas, schema-validated products under `/catalog/*`; product specs are validated against the pinned schema version on write, never on read; media via shared.media only)
- Modify: `docs/superpowers/plans/2026-07-17-d17-registry-products.md` (check off)

- [ ] **Step 1: Full local CI parity** (from `backend/core/`):
```
ruff format --check .   && ruff check .
mypy .
lint-imports
python -m pytest -q                       # full suite, Postgres :45432 + Redis up
python scripts/dump_public_routes.py --check
```
Expected: all green, zero warnings-as-errors surprises.
- [ ] **Step 2: Committed-tree verification** (standing rule — a green local run proves nothing about HEAD):
```
git status                                 # ZERO AM files
git archive HEAD -o %TEMP%\d17.tar         # extract to scratch dir
# in scratch: alembic upgrade head against a throwaway DB + python -m pytest -q
```
- [ ] **Step 3:** Push branch, open PR → dev titled `feat(d17): registry + products`. PR body: DoD checklist (schema-validate + media + versioning tests green; milk vertical seeded), the three owner decisions, the two documented spec deviations (no presign — D16 precedent; schema versions append-only, not full CRUD), integration-surface notes (0018 next in chain; app_rt grants incl. spec_schemas REVOKE; 4 new public routes justified; D16+D17 share `shared.media.reencode_image` — enforced by new lint gate), and fast-follows for D19 (emit `product.created/updated` + `business.created/updated` events when the indexer lands; media bucket policy is best-effort dev-only — prod media domain is R2/CDN config).

---

## Verification (DoD)

1. **NN#1 versioning:** `python -m pytest tests/test_catalog_service.py::test_old_products_keep_rendering_after_schema_v2 -v` → PASS (create under v1 → publish v2 with new required field → old product renders pinned v1; new writes need v2; edit re-pins).
2. **NN#2 media:** `python -m pytest tests/test_catalog_media.py -v` → EXIF absent from stored bytes; image URLs on `media_public_base_url`, not the API origin.
3. **NN#3 one helper:** `python -m pytest tests/test_lint_contracts.py::test_no_media_helper_fork -v` → zero PIL use outside `shared/media.py` (covers both D16 and D17 paths).
4. **NN#4 chain:** committed-tree alembic loader green from 0001→0018; `tests/test_lint_contracts.py` THREAT/NOTES + offset-ban green.
5. **Validator hardening:** `python -m pytest tests/test_spec_validator.py -q` → ~30 cases green (unknown field, wrong type incl. bool-as-number, enum membership, range, length, malformed definitions).
6. **Milk seeded:** `tests/test_catalog_migration.py` green; manual spot-check `GET /catalog/verticals` returns milk.
7. **End-to-end smoke** (compose stack up): create business → POST product with valid milk specs → 201 pending → admin approve → public `GET /catalog/products/{slug}` returns specs + schema_fields + media URL.
