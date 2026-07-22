# D23 — Pincode-First Milk Home — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Ship Milk.in's pincode-first homepage — enter a pincode, see nearby milk vendors + brands with schema-driven type filters and a computed price banner, with three warm empty-state branches (covered / TN-no-vendors / out-of-area).

**Architecture:** A thin backend blend endpoint `GET /catalog/milk/home/{pincode}` composes the existing `covers()` (D15) + milk products (D17) + `shared.geo` (TN/non-TN) into one response carrying a server-computed 3-way `scope` discriminator, schema-driven filter keys, and a price banner parsed from free-text `price_display`. A new `leads.pincode_interest` table + public `POST /leads/pincode-interest` captures notify-me demand. web-milk renders a thin ISR home (`/`) + per-pincode results page (`/[pincode]`) against that one call, reusing `@agri/ui` components (`PincodeInput`, `LiveLocationPill`, `Card`, `Badge`, SEO toolkit).

**Tech Stack:** FastAPI + SQLAlchemy async + Alembic + pytest (backend `backend/core`); Next.js 15 App Router + Tailwind tokens + Playwright (frontend `apps/web-milk`, `@agri/ui`).

## Global Constraints

- **Endpoints private/rate-limited/validated unless explicitly `public=True`.** Public routes MUST be added to `backend/core/public_routes.txt` in the same PR (CI-gated by `scripts/dump_public_routes.py --check`).
- **All IDs UUIDv7; all lists cursor-paginated (keyset, no offset).** Pincode surfaces validate `^\d{6}$` at the FastAPI layer.
- **Migrations:** next revision is `0023`, `down_revision = "0022"`, filename `0023_<slug>.py` (`file_template = %%(rev)s_%%(slug)s`). Mandatory `# -- THREAT/NOTES:` block, no residual `TODO`. Use `pk_column()` / `timestamp_columns()` from `shared.migrations`. **Per-table `GRANT`, never `GRANT ON ALL TABLES IN SCHEMA`.**
- **Events: commit BEFORE publish**, wrap `publish` in best-effort try/except. Directory module NEVER imports notify/audit/search (import-linter independence) — cross-module effects go via bus events consumed elsewhere.
- **Never log request bodies / query strings** in the directory module (PII).
- **UI: tokens only, no raw hex** (`pnpm check:hex`). Every component uses `cn(base, className)` with semantic token classes (`bg-card`, `text-ink`, `bg-brand`, …). Milk brand = blue via `data-theme="theme-milk"`.
- **Design source of truth:** `docs/design-system.md` + `docs/design-reference/preview_frontend.html` (milk block). Icon + English + mother-tongue on every chip/CTA; Call/WA lead every vendor card.
- **web-milk has no vitest** — frontend correctness is verified by `pnpm --filter @agri/web-milk typecheck` + `build` + the Playwright E2E; backend logic is unit-tested in pytest.
- **NON-NEGOTIABLES:** (1) all three empty-state branches render correctly; (2) milk-type filters driven by the D17 schema, not hardcoded; (3) home is ISR/SSR + JSON-LD + Lighthouse ≥90; (4) price banner computes from real listings.
- **Milk types are schema-driven.** The seeded `milk` schema v1 `milk_type` enum = `cow/buffalo/a2/toned/organic`. Do NOT hardcode chips; read the option set from `active_schema("milk")`. Curd&Ghee / Home-delivery are out of scope (not milk_type values).

---

## File Structure

**Backend (`backend/core/`):**
- `alembic/versions/0023_pincode_interest.py` — new migration (create `leads.pincode_interest`).
- `modules/directory/leads_models.py` — add `PincodeInterest` model.
- `modules/directory/leads_schemas.py` — add `PincodeInterestCreateIn`, `PincodeInterestOut`.
- `modules/directory/leads_service.py` — add `record_pincode_interest(...)`.
- `modules/directory/leads_router.py` — add `POST /leads/pincode-interest`.
- `modules/directory/milk_home.py` — NEW: blend service `milk_home(...)` + `compute_price_banner(...)` + dataclasses.
- `modules/directory/milk_home_schemas.py` — NEW: `MilkHomeOut` + nested pydantic out-schemas.
- `modules/directory/catalog_router.py` — add `GET /catalog/milk/home/{pincode}`.
- `public_routes.txt` — add `/leads/pincode-interest` and `/catalog/milk/home/{pincode}`.
- `scripts/seed_e2e_milk.py` — NEW: idempotent E2E seed (owner + milk vendor + products on 641001).
- `tests/test_pincode_interest.py`, `tests/test_milk_home.py` — NEW pytest.

**Frontend (`apps/web-milk/`, `packages/ui/`):**
- `app/api/leads/[...path]/route.ts` — NEW BFF proxy (POST), mirrors the identity proxy.
- `lib/milk.ts` — NEW: `MilkHome` wire types + `fetchMilkHome()` + `MILK_TYPE_META`.
- `app/page.tsx` — REWRITE: ISR hero.
- `app/pincode-hero.tsx` — NEW client: pincode box + GPS → navigate to `/[pincode]`.
- `app/[pincode]/page.tsx` — NEW: ISR results, scope switch, JSON-LD, metadata.
- `app/[pincode]/type-filter-row.tsx` — NEW client: chips, updates `?type=`.
- `app/[pincode]/notify-me.tsx` — NEW client: notify-me form → proxy.
- `app/[pincode]/vendor-card.tsx` — NEW: presentational milk card (Call/WA).
- `app/sitemap.ts` — NEW.
- `e2e/milk-home.spec.ts` — NEW Playwright spec.
- `e2e/playwright.config.ts` — add seed to `webServer`.

---

## Task 1: `pincode_interest` table (migration + model)

**Files:**
- Create: `backend/core/alembic/versions/0023_pincode_interest.py`
- Modify: `backend/core/modules/directory/leads_models.py`
- Test: `backend/core/tests/test_pincode_interest.py` (created here, expanded in Task 2)

**Interfaces:**
- Produces: ORM model `PincodeInterest` (table `leads.pincode_interest`) with columns `id, pincode, district, contact, from_user_id, milk_type, created_at, updated_at`.

- [ ] **Step 1: Write the failing test** — `backend/core/tests/test_pincode_interest.py`

```python
import uuid

import pytest
from sqlalchemy import select

from modules.directory.leads_models import PincodeInterest


@pytest.mark.asyncio
async def test_pincode_interest_row_roundtrips(db_session):
    row = PincodeInterest(
        pincode="641001",
        district="Coimbatore",
        contact="+919876500001",
        from_user_id=None,
        milk_type="cow",
    )
    db_session.add(row)
    await db_session.flush()

    fetched = await db_session.scalar(
        select(PincodeInterest).where(PincodeInterest.id == row.id)
    )
    assert fetched is not None
    assert isinstance(fetched.id, uuid.UUID)  # UUIDv7 PK auto-assigned
    assert fetched.pincode == "641001"
    assert fetched.district == "Coimbatore"
    assert fetched.from_user_id is None
    assert fetched.created_at is not None
```

> `db_session` is the existing async-session fixture used across `backend/core/tests/`. If the fixture is named differently in this repo, match the name used in `tests/test_leads.py`.

- [ ] **Step 2: Run test — verify it fails**

Run: `cd backend/core && python -m pytest tests/test_pincode_interest.py -v`
Expected: FAIL — `ImportError: cannot import name 'PincodeInterest'` (and, once imported, the table won't exist).

- [ ] **Step 3: Add the model** — append to `backend/core/modules/directory/leads_models.py`

```python
class PincodeInterest(UUIDv7PKMixin, TimestampMixin, Base):
    """Warm empty-state demand capture (D23). Unlike Inquiry this has NO
    business_id — it exists precisely when no vendor covers the pincode
    (tn_no_vendors) or the pincode is non-TN (out_of_area). Feeds seeding
    priority; never routed to a vendor inbox."""

    __tablename__ = "pincode_interest"
    __table_args__ = (
        Index("ix_leads_pincode_interest_pincode_id", "pincode", "id"),
        {"schema": "leads"},
    )

    pincode: Mapped[str] = mapped_column(Text, nullable=False)
    district: Mapped[str | None] = mapped_column(Text, nullable=True)
    contact: Mapped[str | None] = mapped_column(Text, nullable=True)
    from_user_id: Mapped[uuid.UUID | None] = mapped_column(
        postgresql.UUID(as_uuid=True), nullable=True
    )
    milk_type: Mapped[str | None] = mapped_column(Text, nullable=True)
```

> `uuid`, `Index`, `Text`, `postgresql`, `Mapped`, `mapped_column`, `Base`, `TimestampMixin`, `UUIDv7PKMixin` are already imported at the top of `leads_models.py` (verify; add any missing).

- [ ] **Step 4: Create the migration** — `backend/core/alembic/versions/0023_pincode_interest.py`

```python
"""pincode interest: warm empty-state demand capture (D23).

Revision ID: 0023
Revises: 0022
Create Date: 2026-07-22

"""
# -- THREAT/NOTES:
# - Guest-writable demand log (public POST /leads/pincode-interest,
#   optional_auth). Rows carry only what the submitter volunteers
#   (pincode + optional contact/milk_type) plus a nullable from_user_id
#   when authed - no coverage routing, no vendor inbox, no PII beyond the
#   optional contact string.
# - downgrade drops the whole demand history (seeding-priority signal loss).
# - leads schema + app_rt default privileges exist since 0001/0013; the
#   explicit per-table GRANT below keeps the profile reviewable (0020
#   precedent). NEVER a blanket GRANT ON ALL TABLES IN SCHEMA.

from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op
from shared.migrations import pk_column, timestamp_columns

revision: str = "0023"
down_revision: str | None = "0022"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_uuid = postgresql.UUID(as_uuid=True)


def upgrade() -> None:
    op.create_table(
        "pincode_interest",
        pk_column(),
        sa.Column("pincode", sa.Text, nullable=False),
        sa.Column("district", sa.Text, nullable=True),
        sa.Column("contact", sa.Text, nullable=True),
        sa.Column("from_user_id", _uuid, nullable=True),
        sa.Column("milk_type", sa.Text, nullable=True),
        *timestamp_columns(),
        schema="leads",
    )
    op.create_index(
        "ix_leads_pincode_interest_pincode_id",
        "pincode_interest",
        ["pincode", "id"],
        schema="leads",
    )
    op.execute("GRANT SELECT, INSERT, UPDATE, DELETE ON leads.pincode_interest TO app_rt")


def downgrade() -> None:
    op.drop_table("pincode_interest", schema="leads")
```

- [ ] **Step 5: Apply the migration & run the test**

Run: `cd backend/core && alembic upgrade head && python -m pytest tests/test_pincode_interest.py -v`
Expected: `alembic upgrade` reports `0022 -> 0023`; test PASS.

- [ ] **Step 6: Verify migration lint contract**

Run: `cd backend/core && python -m pytest tests/test_lint_contracts.py -v`
Expected: PASS (no residual `TODO`, filename == revision, chain intact).

- [ ] **Step 7: Commit**

```bash
git add backend/core/alembic/versions/0023_pincode_interest.py backend/core/modules/directory/leads_models.py backend/core/tests/test_pincode_interest.py
git commit -m "feat(d23): leads.pincode_interest table + model"
```

---

## Task 2: notify-me endpoint (`POST /leads/pincode-interest`)

**Files:**
- Modify: `backend/core/modules/directory/leads_schemas.py`
- Modify: `backend/core/modules/directory/leads_service.py`
- Modify: `backend/core/modules/directory/leads_router.py`
- Modify: `backend/core/public_routes.txt`
- Test: `backend/core/tests/test_pincode_interest.py` (expand)

**Interfaces:**
- Consumes: `PincodeInterest` (Task 1); `district_for_pincode` from `shared.geo.service`; `publish` from `shared.events`; `optional_auth`, `SecureRouter` from `shared.security`.
- Produces: service `record_pincode_interest(session, *, pincode, contact, milk_type, from_user_id) -> PincodeInterest`; route `POST /leads/pincode-interest` returning `PincodeInterestOut{id, pincode, district, created_at}`.

- [ ] **Step 1: Write the failing tests** — append to `backend/core/tests/test_pincode_interest.py`

```python
@pytest.mark.asyncio
async def test_post_pincode_interest_anonymous_tn(client):
    resp = await client.post(
        "/leads/pincode-interest",
        json={"pincode": "641001", "contact": "+919876500001", "milk_type": "cow"},
    )
    assert resp.status_code == 201
    body = resp.json()
    assert body["pincode"] == "641001"
    assert body["district"] == "Coimbatore"  # derived from geo (TN)


@pytest.mark.asyncio
async def test_post_pincode_interest_non_tn_has_null_district(client):
    resp = await client.post("/leads/pincode-interest", json={"pincode": "110001"})
    assert resp.status_code == 201
    assert resp.json()["district"] is None  # non-TN: geo cannot resolve a district


@pytest.mark.asyncio
async def test_post_pincode_interest_bad_pincode_422(client):
    resp = await client.post("/leads/pincode-interest", json={"pincode": "64100"})
    assert resp.status_code == 422
```

> `client` is the existing httpx AsyncClient fixture (see `tests/test_leads.py`). The seeded geo fixture already loads TN pincodes incl. 641001 → Coimbatore; 110001 is not in geo. If `641001`/`Coimbatore` differ in the test geo fixture, adjust to a pincode the fixture actually seeds.

- [ ] **Step 2: Run — verify fail**

Run: `cd backend/core && python -m pytest tests/test_pincode_interest.py -k "post_pincode" -v`
Expected: FAIL — 404 (route not registered).

- [ ] **Step 3: Add schemas** — append to `backend/core/modules/directory/leads_schemas.py`

```python
class PincodeInterestCreateIn(BaseModel):
    pincode: str = Field(pattern=PINCODE_PATTERN)
    contact: str | None = Field(default=None, max_length=120)
    milk_type: str | None = Field(default=None, max_length=40)


class PincodeInterestOut(BaseModel):
    id: uuid.UUID
    pincode: str
    district: str | None
    created_at: datetime
```

> `BaseModel`, `Field`, `uuid`, `datetime`, `PINCODE_PATTERN` are already imported in `leads_schemas.py` (Task-0 extraction confirms). Note: no free-text `state`/`district` accepted from the client — `district` is derived server-side.

- [ ] **Step 4: Add the service function** — append to `backend/core/modules/directory/leads_service.py`

```python
from sqlalchemy import select as _select  # if `select` not already imported at top

from shared.geo.models import State
from shared.geo.service import district_for_pincode

from modules.directory.leads_models import PincodeInterest


async def record_pincode_interest(
    session: AsyncSession,
    *,
    pincode: str,
    contact: str | None,
    milk_type: str | None,
    from_user_id: uuid.UUID | None,
) -> PincodeInterest:
    """Persist a warm-empty-state demand row. Derives district from geo when
    the pincode is TN (non-TN → district stays None). No coverage routing —
    this row exists BECAUSE there is no covering vendor."""
    district = await district_for_pincode(session, pincode)
    row = PincodeInterest(
        pincode=pincode,
        district=district.name if district is not None else None,
        contact=contact,
        milk_type=milk_type,
        from_user_id=from_user_id,
    )
    session.add(row)
    await session.flush()
    return row
```

> `AsyncSession`, `uuid`, `select` already imported at the top of `leads_service.py` (Task-0 extraction). `State` import is not strictly needed here (district name suffices); include only if used.

- [ ] **Step 5: Add the route** — append to `backend/core/modules/directory/leads_router.py`

```python
from modules.directory.leads_schemas import (  # extend existing import
    PincodeInterestCreateIn,
    PincodeInterestOut,
)


@router.post(
    "/pincode-interest",
    public=True,
    status_code=201,
    dependencies=[Depends(optional_auth)],
)
async def create_pincode_interest(
    request: Request, body: PincodeInterestCreateIn, session: SessionDep
) -> PincodeInterestOut:
    principal = getattr(request.state, "principal", None)
    row = await leads_service.record_pincode_interest(
        session,
        pincode=body.pincode,
        contact=body.contact,
        milk_type=body.milk_type,
        from_user_id=principal.user_id if principal is not None else None,
    )
    out = PincodeInterestOut(
        id=row.id, pincode=row.pincode, district=row.district, created_at=row.created_at
    )
    await session.commit()  # commit BEFORE announcing (repo-wide ordering rule)
    await _publish_best_effort(
        "pincode_interest.created",
        {"pincode": row.pincode, "district": row.district, "milk_type": row.milk_type},
    )
    return out
```

- [ ] **Step 6: Register the public route** — add to `backend/core/public_routes.txt`

Add this line (grouped with the other `/leads` entries):

```
/leads/pincode-interest
```

- [ ] **Step 7: Run the tests + public-routes check**

Run: `cd backend/core && python -m pytest tests/test_pincode_interest.py -v && python scripts/dump_public_routes.py --check`
Expected: all tests PASS; public-routes check reports no diff.

- [ ] **Step 8: Commit**

```bash
git add backend/core/modules/directory/leads_schemas.py backend/core/modules/directory/leads_service.py backend/core/modules/directory/leads_router.py backend/core/public_routes.txt backend/core/tests/test_pincode_interest.py
git commit -m "feat(d23): public POST /leads/pincode-interest notify-me capture"
```

---

## Task 3: price-banner computation (pure helper)

**Files:**
- Create: `backend/core/modules/directory/milk_home.py`
- Test: `backend/core/tests/test_milk_home.py` (created here)

**Interfaces:**
- Produces: `@dataclass PriceBand(milk_type: str, low: int, high: int, unit: str | None)`; `compute_price_banner(products: list[ProductLike]) -> tuple[list[PriceBand], int]` where the int is `seller_count`. `ProductLike` is any object with `.specs: dict`, `.price_display: str | None`, `.business_id`.

- [ ] **Step 1: Write the failing test** — `backend/core/tests/test_milk_home.py`

```python
import uuid
from dataclasses import dataclass

import pytest

from modules.directory.milk_home import PriceBand, compute_price_banner


@dataclass
class _P:
    business_id: uuid.UUID
    specs: dict
    price_display: str | None


def _biz():
    return uuid.uuid4()


def test_price_banner_groups_by_type_and_ranges():
    b1, b2 = _biz(), _biz()
    products = [
        _P(b1, {"milk_type": "cow", "pack_size": "1l"}, "₹52/L"),
        _P(b2, {"milk_type": "cow", "pack_size": "1l"}, "₹60/L"),
        _P(b1, {"milk_type": "buffalo", "pack_size": "1l"}, "₹68/L"),
    ]
    bands, seller_count = compute_price_banner(products)
    by_type = {b.milk_type: b for b in bands}
    assert by_type["cow"] == PriceBand(milk_type="cow", low=52, high=60, unit="1l")
    assert by_type["buffalo"] == PriceBand(milk_type="buffalo", low=68, high=68, unit="1l")
    assert seller_count == 2  # two distinct businesses


def test_price_banner_skips_unparseable_and_typeless():
    b = _biz()
    products = [
        _P(b, {"milk_type": "cow", "pack_size": "1l"}, "call for price"),  # no ₹number
        _P(b, {"pack_size": "1l"}, "₹40/L"),  # no milk_type
        _P(b, {"milk_type": "a2", "pack_size": "500ml"}, "₹95/500ml"),
    ]
    bands, seller_count = compute_price_banner(products)
    assert [b.milk_type for b in bands] == ["a2"]
    assert bands[0] == PriceBand(milk_type="a2", low=95, high=95, unit="500ml")
    assert seller_count == 1


def test_price_banner_unit_none_when_pack_sizes_differ():
    b = _biz()
    products = [
        _P(b, {"milk_type": "cow", "pack_size": "1l"}, "₹52/L"),
        _P(b, {"milk_type": "cow", "pack_size": "500ml"}, "₹28/500ml"),
    ]
    bands, _ = compute_price_banner(products)
    assert bands[0].unit is None  # mixed pack sizes → no single unit
```

- [ ] **Step 2: Run — verify fail**

Run: `cd backend/core && python -m pytest tests/test_milk_home.py -k price_banner -v`
Expected: FAIL — `ImportError: cannot import name 'compute_price_banner'`.

- [ ] **Step 3: Implement the helper** — `backend/core/modules/directory/milk_home.py`

```python
"""Milk homepage blend (D23): compose covers() + milk products + geo into a
single pincode response with a 3-way scope discriminator, schema-driven
filter keys, and a price banner parsed from free-text price_display.

Milk-specific glue only — reuses covers/catalog/geo, rebuilds nothing.
The directory module must not import notify/audit/search (import-linter)."""

import re
import uuid
from dataclasses import dataclass
from typing import Protocol

_RUPEE_RE = re.compile(r"₹\s*(\d+)")


class ProductLike(Protocol):
    business_id: uuid.UUID
    specs: dict
    price_display: str | None


@dataclass(frozen=True, slots=True)
class PriceBand:
    milk_type: str
    low: int
    high: int
    unit: str | None


def _rupees(text: str | None) -> list[int]:
    if not text:
        return []
    return [int(n) for n in _RUPEE_RE.findall(text)]


def compute_price_banner(products: list[ProductLike]) -> tuple[list[PriceBand], int]:
    """Group parseable ₹ prices by milk_type → (low, high) band per type.
    unit = the shared pack_size when uniform for that type, else None.
    seller_count = distinct businesses among the passed products.
    Products with no milk_type or no parseable ₹ number are skipped from
    bands (best-effort — price_display is free text)."""
    prices: dict[str, list[int]] = {}
    packs: dict[str, set[str]] = {}
    for p in products:
        milk_type = p.specs.get("milk_type")
        nums = _rupees(p.price_display)
        if not milk_type or not nums:
            continue
        prices.setdefault(milk_type, []).extend(nums)
        pack = p.specs.get("pack_size")
        if isinstance(pack, str):
            packs.setdefault(milk_type, set()).add(pack)

    bands: list[PriceBand] = []
    for milk_type, nums in prices.items():
        pack_set = packs.get(milk_type, set())
        unit = next(iter(pack_set)) if len(pack_set) == 1 else None
        bands.append(PriceBand(milk_type=milk_type, low=min(nums), high=max(nums), unit=unit))

    seller_count = len({p.business_id for p in products})
    return bands, seller_count
```

- [ ] **Step 4: Run — verify pass**

Run: `cd backend/core && python -m pytest tests/test_milk_home.py -k price_banner -v`
Expected: 3 tests PASS.

- [ ] **Step 5: Commit**

```bash
git add backend/core/modules/directory/milk_home.py backend/core/tests/test_milk_home.py
git commit -m "feat(d23): milk price-banner computation helper"
```

---

## Task 4: milk-home blend service (`milk_home()`)

**Files:**
- Modify: `backend/core/modules/directory/milk_home.py`
- Test: `backend/core/tests/test_milk_home.py` (expand)

**Interfaces:**
- Consumes: `covers` from `modules.directory.covers`; `catalog_service.active_schema`; `parse_fields` from `modules.directory.specs`; `Product` from `modules.directory.catalog_models`; `district_for_pincode`, `State` from `shared.geo`; `compute_price_banner` (Task 3).
- Produces:
  - `@dataclass MilkCard(id, name, slug, type, verification_status, subscription_tier, distance_m, products: list[Product])`
  - `@dataclass MilkHomeResult(scope, district, state, filters: list[str], bands: list[PriceBand], seller_count, vendors: list[MilkCard], brands: list[MilkCard], next_cursor)`
  - `async def milk_home(session, *, pincode, milk_type: str | None, cursor: str | None, limit: int) -> MilkHomeResult`

- [ ] **Step 1: Write the failing test** — append to `backend/core/tests/test_milk_home.py`

```python
from modules.directory import milk_home as milk_home_mod


@pytest.mark.asyncio
async def test_milk_home_out_of_area_non_tn(db_session):
    result = await milk_home_mod.milk_home(
        db_session, pincode="110001", milk_type=None, cursor=None, limit=20
    )
    assert result.scope == "out_of_area"
    assert result.district is None
    assert result.vendors == [] and result.brands == []
    # filters are still schema-driven even when out of area
    assert result.filters[0] == "all"
    assert "cow" in result.filters


@pytest.mark.asyncio
async def test_milk_home_tn_no_vendors(db_session):
    # a TN pincode present in geo but with NO business coverage
    result = await milk_home_mod.milk_home(
        db_session, pincode="641999", milk_type=None, cursor=None, limit=20
    )
    assert result.scope == "tn_no_vendors"
    assert result.district is not None  # geo resolved a TN district
    assert result.vendors == [] and result.brands == []


@pytest.mark.asyncio
async def test_milk_home_covered(db_session, seed_milk_vendor):
    # seed_milk_vendor fixture: a `vendor` covering 641001 with ≥1 approved milk product
    result = await milk_home_mod.milk_home(
        db_session, pincode="641001", milk_type=None, cursor=None, limit=20
    )
    assert result.scope == "covered"
    assert result.seller_count >= 1
    assert len(result.vendors) >= 1
    assert result.bands, "price banner computed from real listings"


@pytest.mark.asyncio
async def test_milk_home_filters_match_schema(db_session):
    result = await milk_home_mod.milk_home(
        db_session, pincode="641001", milk_type=None, cursor=None, limit=20
    )
    schema = await __import__(
        "modules.directory.catalog_service", fromlist=["active_schema"]
    ).active_schema(db_session, "milk")
    from modules.directory.specs import parse_fields

    options = next(
        f.options for f in parse_fields(schema.fields) if f.key == "milk_type"
    )
    assert result.filters == ["all", *options]
```

> Fixtures: `db_session` (async session), `seed_milk_vendor` (creates owner + `vendor` on 641001 + approved milk products; add to `tests/conftest.py` if absent — mirror `scripts/make_business.py` create/moderate calls). `641999` must be a TN pincode present in the test geo fixture with no coverage — pick one the geo fixture actually seeds; adjust the literal if needed.

- [ ] **Step 2: Run — verify fail**

Run: `cd backend/core && python -m pytest tests/test_milk_home.py -k "milk_home" -v`
Expected: FAIL — `AttributeError: module ... has no attribute 'milk_home'`.

- [ ] **Step 3: Implement the blend** — append to `backend/core/modules/directory/milk_home.py`

```python
from typing import Literal

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from modules.directory import catalog_service
from modules.directory.catalog_models import Product
from modules.directory.covers import covers
from modules.directory.specs import parse_fields
from shared.geo.models import State
from shared.geo.service import district_for_pincode

_VENDOR_TYPES = {"vendor", "farm"}
Scope = Literal["covered", "tn_no_vendors", "out_of_area"]


@dataclass(frozen=True, slots=True)
class MilkCard:
    id: uuid.UUID
    name: str
    slug: str
    type: str
    verification_status: str
    subscription_tier: str
    distance_m: int
    products: list[Product]


@dataclass(frozen=True, slots=True)
class MilkHomeResult:
    scope: Scope
    district: str | None
    state: str | None
    filters: list[str]
    bands: list[PriceBand]
    seller_count: int
    vendors: list[MilkCard]
    brands: list[MilkCard]
    next_cursor: str | None


async def _milk_filter_keys(session: AsyncSession) -> list[str]:
    """Schema-driven chip keys: ['all', *milk_type options]. Reads the
    active D17 milk schema — never hardcoded (NON-NEGOTIABLE #2)."""
    schema = await catalog_service.active_schema(session, "milk")
    if schema is None:
        return ["all"]
    for field in parse_fields(schema.fields):
        if field.key == "milk_type" and field.options:
            return ["all", *field.options]
    return ["all"]


async def milk_home(
    session: AsyncSession,
    *,
    pincode: str,
    milk_type: str | None,
    cursor: str | None,
    limit: int,
) -> MilkHomeResult:
    filters = await _milk_filter_keys(session)

    district = await district_for_pincode(session, pincode)
    if district is None:
        # non-TN / unlisted pincode → warm out-of-area state (NOT an error)
        return MilkHomeResult(
            scope="out_of_area", district=None, state=None, filters=filters,
            bands=[], seller_count=0, vendors=[], brands=[], next_cursor=None,
        )
    state = await session.scalar(select(State).where(State.id == district.state_id))
    state_name = state.name if state is not None else None

    page = await covers(session, pincode=pincode, cursor=cursor, limit=limit)
    business_ids = [item.id for item in page.items]
    if not business_ids:
        return MilkHomeResult(
            scope="tn_no_vendors", district=district.name, state=state_name,
            filters=filters, bands=[], seller_count=0, vendors=[], brands=[],
            next_cursor=None,
        )

    products = list(
        await session.scalars(
            select(Product).where(
                Product.business_id.in_(business_ids),
                Product.vertical_slug == "milk",
                Product.moderation_status == "approved",
                Product.status == "active",
                Product.deleted_at.is_(None),
            )
        )
    )
    by_biz: dict[uuid.UUID, list[Product]] = {}
    for product in products:
        by_biz.setdefault(product.business_id, []).append(product)

    if not by_biz:
        return MilkHomeResult(
            scope="tn_no_vendors", district=district.name, state=state_name,
            filters=filters, bands=[], seller_count=0, vendors=[], brands=[],
            next_cursor=None,
        )

    # Banner + seller_count are UNFILTERED (reflect all milk on offer here).
    bands, seller_count = compute_price_banner(products)

    vendors: list[MilkCard] = []
    brands: list[MilkCard] = []
    for item in page.items:
        biz_products = by_biz.get(item.id)
        if not biz_products:
            continue  # covering business with no milk products → not a card
        if milk_type and milk_type != "all":
            biz_products = [p for p in biz_products if p.specs.get("milk_type") == milk_type]
            if not biz_products:
                continue  # filtered out — scope stays 'covered', card dropped
        card = MilkCard(
            id=item.id, name=item.name, slug=item.slug, type=item.type,
            verification_status=item.verification_status,
            subscription_tier=item.subscription_tier, distance_m=item.distance_m,
            products=biz_products,
        )
        (vendors if item.type in _VENDOR_TYPES else brands).append(card)

    return MilkHomeResult(
        scope="covered", district=district.name, state=state_name, filters=filters,
        bands=bands, seller_count=seller_count, vendors=vendors, brands=brands,
        next_cursor=page.next_cursor,
    )
```

- [ ] **Step 4: Run — verify pass**

Run: `cd backend/core && python -m pytest tests/test_milk_home.py -v`
Expected: all PASS (price-banner + 4 blend tests).

- [ ] **Step 5: Commit**

```bash
git add backend/core/modules/directory/milk_home.py backend/core/tests/test_milk_home.py backend/core/tests/conftest.py
git commit -m "feat(d23): milk-home blend service + scope discriminator"
```

---

## Task 5: `GET /catalog/milk/home/{pincode}` endpoint

**Files:**
- Create: `backend/core/modules/directory/milk_home_schemas.py`
- Modify: `backend/core/modules/directory/catalog_router.py`
- Modify: `backend/core/public_routes.txt`
- Test: `backend/core/tests/test_milk_home.py` (expand with HTTP tests)

**Interfaces:**
- Consumes: `milk_home()` (Task 4).
- Produces: HTTP `GET /catalog/milk/home/{pincode}?type=&cursor=` → `MilkHomeOut`. This is the wire contract the web-milk frontend renders against (mirror the field names in `lib/milk.ts`, Task 8).

- [ ] **Step 1: Write the failing tests** — append to `backend/core/tests/test_milk_home.py`

```python
@pytest.mark.asyncio
async def test_http_milk_home_out_of_area(client):
    resp = await client.get("/catalog/milk/home/110001")
    assert resp.status_code == 200
    body = resp.json()
    assert body["scope"] == "out_of_area"
    assert body["location"] is None
    assert body["filters"][0] == "all"


@pytest.mark.asyncio
async def test_http_milk_home_tn_no_vendors(client):
    resp = await client.get("/catalog/milk/home/641999")
    assert resp.status_code == 200
    body = resp.json()
    assert body["scope"] == "tn_no_vendors"
    assert body["location"]["district"] is not None
    assert body["vendors"] == [] and body["brands"] == []


@pytest.mark.asyncio
async def test_http_milk_home_covered(client, seed_milk_vendor):
    resp = await client.get("/catalog/milk/home/641001")
    assert resp.status_code == 200
    body = resp.json()
    assert body["scope"] == "covered"
    assert len(body["vendors"]) >= 1
    assert body["price_banner"]["seller_count"] >= 1
    assert body["price_banner"]["lines"], "banner computed from listings"


@pytest.mark.asyncio
async def test_http_milk_home_bad_pincode_422(client):
    resp = await client.get("/catalog/milk/home/64100")
    assert resp.status_code == 422  # Path pattern ^\d{6}$
```

- [ ] **Step 2: Run — verify fail**

Run: `cd backend/core && python -m pytest tests/test_milk_home.py -k http_milk_home -v`
Expected: FAIL — 404 (route not registered).

- [ ] **Step 3: Add the out-schemas** — `backend/core/modules/directory/milk_home_schemas.py`

```python
import uuid
from typing import Literal

from pydantic import BaseModel

from modules.directory.milk_home import MilkCard, MilkHomeResult


class MilkProductOut(BaseModel):
    milk_type: str | None
    fat_percent: float | None
    pack_size: str | None
    price_display: str | None


class MilkCardOut(BaseModel):
    id: uuid.UUID
    name: str
    slug: str
    type: str
    verification_status: str
    subscription_tier: str
    distance_m: int
    products: list[MilkProductOut]


class PriceBandOut(BaseModel):
    milk_type: str
    low: int
    high: int
    unit: str | None


class PriceBannerOut(BaseModel):
    lines: list[PriceBandOut]
    seller_count: int


class MilkLocationOut(BaseModel):
    pincode: str
    district: str
    state: str | None


class MilkHomeOut(BaseModel):
    scope: Literal["covered", "tn_no_vendors", "out_of_area"]
    location: MilkLocationOut | None
    filters: list[str]
    price_banner: PriceBannerOut | None
    vendors: list[MilkCardOut]
    brands: list[MilkCardOut]
    next_cursor: str | None


def _card_out(card: MilkCard) -> MilkCardOut:
    return MilkCardOut(
        id=card.id, name=card.name, slug=card.slug, type=card.type,
        verification_status=card.verification_status,
        subscription_tier=card.subscription_tier, distance_m=card.distance_m,
        products=[
            MilkProductOut(
                milk_type=p.specs.get("milk_type"),
                fat_percent=p.specs.get("fat_percent"),
                pack_size=p.specs.get("pack_size"),
                price_display=p.price_display,
            )
            for p in card.products
        ],
    )


def milk_home_out(pincode: str, result: MilkHomeResult) -> MilkHomeOut:
    location = (
        MilkLocationOut(pincode=pincode, district=result.district, state=result.state)
        if result.district is not None
        else None
    )
    price_banner = (
        PriceBannerOut(
            lines=[
                PriceBandOut(milk_type=b.milk_type, low=b.low, high=b.high, unit=b.unit)
                for b in result.bands
            ],
            seller_count=result.seller_count,
        )
        if result.scope == "covered"
        else None
    )
    return MilkHomeOut(
        scope=result.scope, location=location, filters=result.filters,
        price_banner=price_banner,
        vendors=[_card_out(c) for c in result.vendors],
        brands=[_card_out(c) for c in result.brands],
        next_cursor=result.next_cursor,
    )
```

- [ ] **Step 4: Add the route** — append to `backend/core/modules/directory/catalog_router.py`

```python
from typing import Annotated  # if not already imported

from fastapi import Path  # extend existing fastapi import

from modules.directory import milk_home as milk_home_module
from modules.directory.milk_home_schemas import MilkHomeOut, milk_home_out
from shared.pagination import DEFAULT_PAGE_SIZE, InvalidCursorError


@router.get("/milk/home/{pincode}", public=True)
async def milk_home(
    pincode: Annotated[str, Path(pattern=r"^\d{6}$")],
    session: SessionDep,
    type: str | None = None,
    cursor: str | None = None,
    limit: LimitQuery = DEFAULT_PAGE_SIZE,
) -> MilkHomeOut:
    """Pincode-first milk blend (D23): vendors + brands + schema-driven
    filters + computed price banner, with a 3-way empty-state scope.
    Public + keyset-only + rate-limited (pincode-enumeration defence)."""
    try:
        result = await milk_home_module.milk_home(
            session, pincode=pincode, milk_type=type, cursor=cursor, limit=limit
        )
    except InvalidCursorError as exc:
        raise HTTPException(status_code=400, detail="invalid cursor") from exc
    return milk_home_out(pincode, result)
```

> `router`, `SessionDep`, `LimitQuery`, `HTTPException` already exist in `catalog_router.py` (Task-0 extraction). `DEFAULT_PAGE_SIZE`/`InvalidCursorError` may already be imported — dedupe.

- [ ] **Step 5: Register the public route** — add to `backend/core/public_routes.txt`

```
/catalog/milk/home/{pincode}
```

> Confirm the exact registered path string by running the check in Step 6 — SecureRouter records the path template; match it verbatim.

- [ ] **Step 6: Run tests + public-routes check + typecheck**

Run: `cd backend/core && python -m pytest tests/test_milk_home.py -v && python scripts/dump_public_routes.py --check && mypy modules/directory/milk_home.py modules/directory/milk_home_schemas.py`
Expected: all PASS; no public-routes diff; mypy clean.

- [ ] **Step 7: Commit**

```bash
git add backend/core/modules/directory/milk_home_schemas.py backend/core/modules/directory/catalog_router.py backend/core/public_routes.txt backend/core/tests/test_milk_home.py
git commit -m "feat(d23): GET /catalog/milk/home/{pincode} blend endpoint"
```

---

## Task 6: E2E seed script (owner + milk vendor on 641001)

**Files:**
- Create: `backend/core/scripts/seed_e2e_milk.py`

**Interfaces:**
- Produces: idempotent CLI `python -m scripts.seed_e2e_milk` (or `python scripts/seed_e2e_milk.py`) that guarantees a `vendor` business covering `641001` with ≥1 approved milk product exists, creating its owner user if needed. Used by the Playwright `webServer` (Task 14).

- [ ] **Step 1: Write the seed script** — `backend/core/scripts/seed_e2e_milk.py`

```python
"""Idempotent E2E seed (D23): ensure a milk vendor covers 641001 so the
milk-home 'covered' branch renders deterministically. Safe to run repeatedly
(checks by slug/phone before creating). Mirrors scripts/make_business.py."""

import asyncio

from sqlalchemy import select

from modules.directory import catalog_service, service
from modules.directory.models import Business
from modules.identity.models import User
from shared.db import get_sessionmaker

_OWNER_PHONE = "+919000000023"
_SLUG_HINT = "e2e-milk-vendor-641001"
_PRODUCTS = [
    ("Fresh Cow Milk", {"milk_type": "cow", "fat_percent": 4.2, "pack_size": "1l"}, "₹55/L"),
    ("Buffalo Milk", {"milk_type": "buffalo", "fat_percent": 6.5, "pack_size": "1l"}, "₹70/L"),
]


async def _ensure_owner(session) -> User:
    owner = await session.scalar(select(User).where(User.phone == _OWNER_PHONE))
    if owner is None:
        owner = User(phone=_OWNER_PHONE, handle="e2e_milk_owner")
        session.add(owner)
        await session.flush()
    return owner


async def run() -> None:
    sessionmaker = get_sessionmaker()
    async with sessionmaker() as session:
        existing = await session.scalar(
            select(Business).where(Business.name == "E2E Milk Vendor")
        )
        if existing is not None:
            print("seed_e2e_milk: already present, nothing to do")  # noqa: T201
            return

        owner = await _ensure_owner(session)
        business = await service.create_business(
            session, owner_user_id=owner.id, name="E2E Milk Vendor",
            type_="vendor", primary_pincode="641001",
            description={"en": "Deterministic E2E milk vendor."},
        )
        await service.add_branch(
            session, owner_user_id=owner.id, business_id=business.id,
            address="1 E2E Road", state="Tamil Nadu", district="Coimbatore",
            pincode="641001", phone="+919876500023", whatsapp="+919876500023",
        )
        await service.set_coverage(
            session, owner_user_id=owner.id, business_id=business.id, pincodes=["641001"]
        )
        for name, specs, price in _PRODUCTS:
            product = await catalog_service.create_product(
                session, owner_user_id=owner.id, business_id=business.id,
                vertical_slug="milk", name=name, specs=specs, price_display=price,
            )
            await catalog_service.moderate_product(session, product_id=product.id, approve=True)
        await session.commit()
        print(f"seed_e2e_milk: created {business.slug}")  # noqa: T201


if __name__ == "__main__":
    asyncio.run(run())
```

> Verify `User(phone=..., handle=...)` matches the identity model's required columns (it may need more, e.g. status). If direct `User(...)` construction is rejected, call the identity signup/service helper used by `tests/conftest.py` to mint a user instead. Verify `catalog_service.create_product` / `moderate_product` signatures against `catalog_service.py` (Task-0 extraction shows the make_business.py call shape).

- [ ] **Step 2: Run it against the dev DB (twice — idempotency check)**

Run: `cd backend/core && python scripts/seed_e2e_milk.py && python scripts/seed_e2e_milk.py`
Expected: first run prints `created ...`; second prints `already present, nothing to do`.

- [ ] **Step 3: Verify the endpoint now returns covered**

Run: `curl -s http://127.0.0.1:8000/catalog/milk/home/641001 | python -m json.tool | head -20`
Expected: `"scope": "covered"` with ≥1 vendor. (Requires the API running; skip if not up locally.)

- [ ] **Step 4: Commit**

```bash
git add backend/core/scripts/seed_e2e_milk.py
git commit -m "test(d23): idempotent E2E milk-vendor seed for 641001"
```

---

## Task 7: BFF proxy for notify-me (`/api/leads/*`)

**Files:**
- Create: `apps/web-milk/app/api/leads/[...path]/route.ts`

**Interfaces:**
- Produces: same-origin `POST /api/leads/pincode-interest` → forwards to `${API}/leads/pincode-interest` with optional bearer. Consumed by the notify-me form (Task 11).

- [ ] **Step 1: Create the proxy** — `apps/web-milk/app/api/leads/[...path]/route.ts`

```ts
/**
 * BFF proxy: browser -> same-origin /api/leads/* -> FastAPI /leads/* with the
 * session bearer attached HERE, server-side (tokens never touch JS). Mirrors
 * the guest-capable /api/identity proxy: /leads/pincode-interest is public
 * (optional_auth), so an absent token forwards WITHOUT an Authorization header
 * rather than 401-ing — the backend enforces auth on protected /leads paths.
 */
import type { NextRequest } from "next/server";
import { NextResponse } from "next/server";

import { auth } from "@/lib/auth";

const API = process.env.API_BASE_URL ?? "http://127.0.0.1:8000";

export async function POST(
  req: NextRequest,
  ctx: { params: Promise<{ path: string[] }> },
): Promise<NextResponse> {
  const { path } = await ctx.params;
  if (path.some((segment) => segment === ".." || segment === "." || segment === "")) {
    return NextResponse.json({ detail: "invalid_path" }, { status: 400 });
  }
  const token = await auth.getAccessToken(); // null for guests — fine
  const url = new URL(`${API}/leads/${path.map(encodeURIComponent).join("/")}`);
  url.search = req.nextUrl.search;
  const upstream = await fetch(url, {
    method: "POST",
    headers: {
      ...(token ? { authorization: `Bearer ${token}` } : {}),
      "content-type": "application/json",
    },
    body: await req.text(),
    cache: "no-store",
  });
  const body = (await upstream.json().catch(() => ({}))) as Record<string, unknown>;
  return NextResponse.json(body, { status: upstream.status });
}
```

- [ ] **Step 2: Typecheck**

Run: `pnpm --filter @agri/web-milk typecheck`
Expected: PASS.

- [ ] **Step 3: Commit**

```bash
git add apps/web-milk/app/api/leads/[...path]/route.ts
git commit -m "feat(d23): web-milk BFF proxy for /leads notify-me"
```

---

## Task 8: web-milk data layer (`lib/milk.ts`)

**Files:**
- Create: `apps/web-milk/lib/milk.ts`

**Interfaces:**
- Produces: TS wire types mirroring `MilkHomeOut` (Task 5); `fetchMilkHome(pincode, type?)`; `MILK_TYPE_META` (key → display); `priceBannerText(banner)`.

- [ ] **Step 1: Create the data layer** — `apps/web-milk/lib/milk.ts`

```ts
const API = process.env.API_BASE_URL ?? "http://127.0.0.1:8000";

export type MilkScope = "covered" | "tn_no_vendors" | "out_of_area";

export interface MilkProduct {
  milk_type: string | null;
  fat_percent: number | null;
  pack_size: string | null;
  price_display: string | null;
}
export interface MilkCard {
  id: string;
  name: string;
  slug: string;
  type: string;
  verification_status: string;
  subscription_tier: string;
  distance_m: number;
  products: MilkProduct[];
}
export interface PriceBand {
  milk_type: string;
  low: number;
  high: number;
  unit: string | null;
}
export interface MilkHome {
  scope: MilkScope;
  location: { pincode: string; district: string; state: string | null } | null;
  filters: string[];
  price_banner: { lines: PriceBand[]; seller_count: number } | null;
  vendors: MilkCard[];
  brands: MilkCard[];
  next_cursor: string | null;
}

/** Display metadata for a schema-driven milk_type KEY. The filter SET is
 * schema-driven (backend); icon + vernacular are presentation, keyed by the
 * backend value with a graceful fallback for unknown future keys. */
export const MILK_TYPE_META: Record<string, { en: string; vern: string; icon: string }> = {
  all: { en: "All", vern: "எல்லாம்", icon: "🥛" },
  cow: { en: "Cow", vern: "பசு", icon: "🐄" },
  buffalo: { en: "Buffalo", vern: "எருமை", icon: "🐃" },
  a2: { en: "A2", vern: "", icon: "✨" },
  toned: { en: "Toned", vern: "", icon: "🥛" },
  organic: { en: "Organic", vern: "", icon: "🌿" },
};

export function milkTypeMeta(key: string) {
  return MILK_TYPE_META[key] ?? { en: key, vern: "", icon: "🥛" };
}

/** "Cow ₹52–60 · Buffalo ₹68 · 32 sellers found" from real listings. */
export function priceBannerText(banner: NonNullable<MilkHome["price_banner"]>): string {
  const parts = banner.lines.map((b) => {
    const range = b.low === b.high ? `₹${b.low}` : `₹${b.low}–${b.high}`;
    const unit = b.unit ? `/${b.unit}` : "";
    return `${milkTypeMeta(b.milk_type).en} ${range}${unit}`;
  });
  return `${parts.join(" · ")} · ${banner.seller_count} sellers found`;
}

/** Server-side public read — direct to backend (not the BFF proxy). Returns
 * null on any failure so the page renders a graceful state, never a crash. */
export async function fetchMilkHome(pincode: string, type?: string): Promise<MilkHome | null> {
  const qs = type && type !== "all" ? `?type=${encodeURIComponent(type)}` : "";
  try {
    const res = await fetch(`${API}/catalog/milk/home/${encodeURIComponent(pincode)}${qs}`, {
      next: { revalidate: 300 },
    });
    if (!res.ok) return null;
    return (await res.json()) as MilkHome;
  } catch {
    return null;
  }
}
```

- [ ] **Step 2: Typecheck**

Run: `pnpm --filter @agri/web-milk typecheck`
Expected: PASS.

- [ ] **Step 3: Commit**

```bash
git add apps/web-milk/lib/milk.ts
git commit -m "feat(d23): web-milk milk-home data layer + types"
```

---

## Task 9: vendor card + type-filter row + notify-me (client pieces)

**Files:**
- Create: `apps/web-milk/app/[pincode]/vendor-card.tsx`
- Create: `apps/web-milk/app/[pincode]/type-filter-row.tsx`
- Create: `apps/web-milk/app/[pincode]/notify-me.tsx`

**Interfaces:**
- Consumes: `MilkCard`, `MilkHome["filters"]`, `milkTypeMeta` (Task 8); `Card`, `Badge` from `@agri/ui`.
- Produces: `<VendorCard card>`, `<TypeFilterRow pincode filters active>`, `<NotifyMe pincode district?>` — used by the pincode page (Task 10).

- [ ] **Step 1: VendorCard** — `apps/web-milk/app/[pincode]/vendor-card.tsx`

```tsx
import { Badge, Card } from "@agri/ui";

import { milkTypeMeta, type MilkCard } from "@/lib/milk";

/** ListingCard anatomy (design-system §2): badge → tinted icon + title +
 * meta → price tag → Call/WA action row (Call/WA lead every card, UX law 4). */
export function VendorCard({ card }: { card: MilkCard }) {
  const km = (card.distance_m / 1000).toFixed(1);
  const priceLine = card.products
    .filter((p) => p.price_display)
    .map((p) => `${p.price_display} ${milkTypeMeta(p.milk_type ?? "").en}`.trim())
    .join(" · ");
  return (
    <Card className="flex flex-col gap-1.5 p-4">
      {card.verification_status === "verified" ? <Badge variant="verified">✔ Verified</Badge> : null}
      <h3 className="text-[15.5px] font-extrabold leading-[1.3] text-ink">{card.name}</h3>
      <p className="text-[12.5px] text-sub">{km} km away</p>
      {priceLine ? <p className="text-[15px] font-extrabold text-ink">{priceLine}</p> : null}
      <div className="mt-1 flex gap-2">
        <span className="flex-1 rounded-btn bg-call py-2 text-center text-[13px] font-extrabold text-white">
          📞 Call
        </span>
        <span className="flex-1 rounded-btn border border-wa-border bg-wa-bg py-2 text-center text-[13px] font-extrabold text-wa-fg">
          WhatsApp
        </span>
      </div>
    </Card>
  );
}
```

> Call/WA are visually-complete but inert in D23 (tracked contact + reveal land in D24). Confirm the token class names (`bg-call`, `bg-wa-bg`, `text-wa-fg`, `border-wa-border`) against `packages/config/tailwind/preset.js`; adjust to the exact token names if they differ. Do NOT introduce raw hex.

- [ ] **Step 2: TypeFilterRow** — `apps/web-milk/app/[pincode]/type-filter-row.tsx`

```tsx
"use client";

import { cn } from "@agri/ui";
import Link from "next/link";

import { milkTypeMeta } from "@/lib/milk";

/** `.tf` row (design-system): horizontally scrollable chips, icon + label +
 * vernacular; active = brand border + brand-soft bg. Filters via ?type= (SSR
 * reads it) — no client fetch, shareable URL, no offset paging. */
export function TypeFilterRow({
  pincode,
  filters,
  active,
}: {
  pincode: string;
  filters: string[];
  active: string;
}) {
  return (
    <div
      role="group"
      aria-label="Milk type"
      className="flex gap-2 overflow-x-auto pb-1"
      data-testid="type-filter-row"
    >
      {filters.map((key) => {
        const meta = milkTypeMeta(key);
        const on = key === active || (key === "all" && active === "all");
        const href = key === "all" ? `/${pincode}` : `/${pincode}?type=${key}`;
        return (
          <Link
            key={key}
            href={href}
            aria-current={on ? "true" : undefined}
            className={cn(
              "flex min-w-[86px] flex-col items-center gap-0.5 rounded-card border-2 px-3 py-2 text-center",
              on ? "border-brand bg-brand-soft" : "border-line bg-card",
            )}
          >
            <span className="text-lg">{meta.icon}</span>
            <span className="text-[12px] font-extrabold text-ink">{meta.en}</span>
            {meta.vern ? <span className="text-[11px] text-sub">{meta.vern}</span> : null}
          </Link>
        );
      })}
    </div>
  );
}
```

> Confirm `bg-brand-soft` token exists in the preset (design-system references brand-soft bg for active chips); if the token name differs, use the correct one.

- [ ] **Step 3: NotifyMe** — `apps/web-milk/app/[pincode]/notify-me.tsx`

```tsx
"use client";

import { useState } from "react";

/** Warm empty-state demand capture. POSTs to the same-origin BFF proxy
 * (Task 7) → public /leads/pincode-interest. Never an error surface. */
export function NotifyMe({ pincode }: { pincode: string }) {
  const [status, setStatus] = useState<"idle" | "sending" | "done" | "error">("idle");
  const [contact, setContact] = useState("");

  async function submit(e: React.FormEvent) {
    e.preventDefault();
    setStatus("sending");
    try {
      const res = await fetch("/api/leads/pincode-interest", {
        method: "POST",
        headers: { "content-type": "application/json" },
        body: JSON.stringify({ pincode, contact: contact.trim() || undefined }),
      });
      setStatus(res.ok ? "done" : "error");
    } catch {
      setStatus("error");
    }
  }

  if (status === "done") {
    return (
      <p className="text-[14px] font-bold text-ink" data-testid="notify-done">
        🎉 Thanks — we'll tell you the moment milk vendors reach {pincode}.
      </p>
    );
  }

  return (
    <form onSubmit={submit} className="flex flex-col gap-2 sm:flex-row" data-testid="notify-me">
      <input
        type="text"
        inputMode="tel"
        value={contact}
        onChange={(e) => setContact(e.target.value)}
        placeholder="Phone or email (optional)"
        aria-label="Contact for notification"
        className="flex-1 rounded-btn border border-line bg-card px-3 py-2.5 text-[14px] text-ink"
      />
      <button
        type="submit"
        disabled={status === "sending"}
        className="rounded-btn bg-brand px-5 py-2.5 text-[14px] font-extrabold text-white disabled:opacity-50"
      >
        Notify me
      </button>
    </form>
  );
}
```

- [ ] **Step 4: Typecheck**

Run: `pnpm --filter @agri/web-milk typecheck`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add apps/web-milk/app/[pincode]/vendor-card.tsx apps/web-milk/app/[pincode]/type-filter-row.tsx apps/web-milk/app/[pincode]/notify-me.tsx
git commit -m "feat(d23): milk vendor card, type-filter row, notify-me form"
```

---

## Task 10: pincode results page (`/[pincode]`, ISR)

**Files:**
- Create: `apps/web-milk/app/[pincode]/page.tsx`

**Interfaces:**
- Consumes: `fetchMilkHome`, `priceBannerText` (Task 8); `VendorCard`, `TypeFilterRow`, `NotifyMe` (Task 9); `buildMetadata`, `canonicalUrl` from `@agri/ui/seo`; `notFound` from `next/navigation`.
- Produces: the ISR route rendering all three scope branches + JSON-LD + metadata.

- [ ] **Step 1: Create the page** — `apps/web-milk/app/[pincode]/page.tsx`

```tsx
import { buildMetadata, canonicalUrl } from "@agri/ui/seo";
import type { Metadata } from "next";
import { notFound } from "next/navigation";

import { fetchMilkHome, priceBannerText, type MilkHome } from "@/lib/milk";

import { NotifyMe } from "./notify-me";
import { TypeFilterRow } from "./type-filter-row";
import { VendorCard } from "./vendor-card";

const SITE = "https://milk.in";
export const revalidate = 300;

const PIN_RE = /^\d{6}$/;

export async function generateMetadata({
  params,
}: {
  params: Promise<{ pincode: string }>;
}): Promise<Metadata> {
  const { pincode } = await params;
  if (!PIN_RE.test(pincode)) return { title: "Milk.in", robots: { index: false, follow: true } };
  const data = await fetchMilkHome(pincode);
  const place = data?.location ? `${data.location.district} (${pincode})` : pincode;
  const covered = data?.scope === "covered";
  return buildMetadata({
    title: `Milk in ${place} — Milk.in`,
    description: `Cow, buffalo, A2 & organic milk vendors and brands near ${place}.`,
    canonical: canonicalUrl(SITE, `/${pincode}`),
    siteName: "Milk.in",
    // Thin/empty pincode pages self-noindex until they have real listings.
    noIndex: !covered,
  });
}

/** ItemList of LocalBusiness — hand-built (no itemList builder in @agri/ui/seo).
 * `<` escaped so listing content can never close the script tag. */
function itemListJsonLd(pincode: string, data: MilkHome): string {
  const cards = [...data.vendors, ...data.brands];
  const graph = {
    "@context": "https://schema.org",
    "@type": "ItemList",
    name: `Milk vendors in ${data.location?.district ?? pincode}`,
    itemListElement: cards.map((c, i) => ({
      "@type": "ListItem",
      position: i + 1,
      item: {
        "@type": "LocalBusiness",
        name: c.name,
        url: canonicalUrl(SITE, `/directory/businesses/${c.slug}`),
        ...(data.location
          ? {
              address: {
                "@type": "PostalAddress",
                addressLocality: data.location.district,
                addressRegion: data.location.state ?? "Tamil Nadu",
                postalCode: pincode,
                addressCountry: "IN",
              },
            }
          : {}),
      },
    })),
  };
  return JSON.stringify(graph).replaceAll("<", "\\u003c");
}

export default async function PincodePage({
  params,
  searchParams,
}: {
  params: Promise<{ pincode: string }>;
  searchParams: Promise<{ type?: string }>;
}) {
  const { pincode } = await params;
  if (!PIN_RE.test(pincode)) notFound();
  const { type = "all" } = await searchParams;
  const data = await fetchMilkHome(pincode, type);
  if (!data) notFound(); // backend unreachable / 400 — genuine error, not a warm state

  // ---- Warm empty states (features, never error screens) ----
  if (data.scope === "out_of_area") {
    return (
      <main className="mx-auto flex w-full max-w-[720px] flex-col gap-3 px-4 py-8" data-testid="scope-out-of-area">
        <h1 className="font-display text-[22px] font-extrabold text-ink">
          We're live in Tamil Nadu right now
        </h1>
        <p className="text-[15px] text-sub">
          {pincode} isn't in our coverage yet — more areas coming soon. Leave your number and we'll
          reach out when milk vendors arrive.
        </p>
        <NotifyMe pincode={pincode} />
      </main>
    );
  }
  if (data.scope === "tn_no_vendors") {
    const place = data.location ? `${data.location.district} (${pincode})` : pincode;
    return (
      <main className="mx-auto flex w-full max-w-[720px] flex-col gap-3 px-4 py-8" data-testid="scope-tn-no-vendors">
        <h1 className="font-display text-[22px] font-extrabold text-ink">
          No milk vendors in {place} yet
        </h1>
        <p className="text-[15px] text-sub">
          Be the first to know when a dairy lists here — or list your own dairy.
        </p>
        <NotifyMe pincode={pincode} />
      </main>
    );
  }

  // ---- Covered ----
  const filteredEmpty = data.vendors.length === 0 && data.brands.length === 0;
  return (
    <main className="mx-auto flex w-full max-w-[720px] flex-col gap-5 px-4 py-6" data-testid="scope-covered">
      <script type="application/ld+json" dangerouslySetInnerHTML={{ __html: itemListJsonLd(pincode, data) }} />
      <h1 className="font-display text-[22px] font-extrabold text-ink">
        Milk in {data.location?.district ?? pincode}
      </h1>
      <TypeFilterRow pincode={pincode} filters={data.filters} active={type} />

      {data.price_banner ? (
        <div className="rounded-card border border-dashed border-line bg-brand-soft px-3 py-2 text-[13px] text-ink" data-testid="price-banner">
          <b>Today in {pincode}:</b> {priceBannerText(data.price_banner)}
        </div>
      ) : null}

      {filteredEmpty ? (
        <p className="text-[14px] text-sub" data-testid="filtered-empty">
          No {type} milk listed here yet — <a className="font-bold text-brand-deep" href={`/${pincode}`}>see all</a>.
        </p>
      ) : (
        <>
          {data.vendors.length > 0 ? (
            <section className="flex flex-col gap-2.5">
              <h2 className="font-display text-[16px] font-extrabold text-ink">Local vendors</h2>
              <div className="grid gap-3 sm:grid-cols-2">
                {data.vendors.map((c) => <VendorCard key={c.id} card={c} />)}
              </div>
            </section>
          ) : null}
          {data.brands.length > 0 ? (
            <section className="flex flex-col gap-2.5">
              <h2 className="font-display text-[16px] font-extrabold text-ink">Brands &amp; shops nearby</h2>
              <div className="grid gap-3 sm:grid-cols-2">
                {data.brands.map((c) => <VendorCard key={c.id} card={c} />)}
              </div>
            </section>
          ) : null}
        </>
      )}
    </main>
  );
}
```

- [ ] **Step 2: Typecheck + build**

Run: `pnpm --filter @agri/web-milk typecheck && pnpm --filter @agri/web-milk build`
Expected: PASS (build compiles the dynamic route).

- [ ] **Step 3: Manual smoke (API + web-milk running)**

Run: `pnpm --filter @agri/web-milk dev` then visit `http://localhost:3000/110001` (out-of-area), `http://localhost:3000/641999` (tn-no-vendors), `http://localhost:3000/641001` (covered, after Task 6 seed).
Expected: the three distinct branches render; no console errors; view-source shows JSON-LD on the covered page and `noindex` meta on the empty ones.

- [ ] **Step 4: Commit**

```bash
git add apps/web-milk/app/[pincode]/page.tsx
git commit -m "feat(d23): /[pincode] ISR results page + three empty states + JSON-LD"
```

---

## Task 11: pincode-first home (`/`, ISR hero)

**Files:**
- Create: `apps/web-milk/app/pincode-hero.tsx`
- Modify (rewrite): `apps/web-milk/app/page.tsx`

**Interfaces:**
- Consumes: `PincodeInput`, `GpsPill` from `@agri/ui`; `parseLocationResponse` from `@agri/ui`; `buildMetadata`, `canonicalUrl` from `@agri/ui/seo`.
- Produces: ISR home rendering the hero + `WebSite`/`Organization` JSON-LD.

- [ ] **Step 1: Create the hero client** — `apps/web-milk/app/pincode-hero.tsx`

```tsx
"use client";

import { GpsPill, PincodeInput } from "@agri/ui";
import { useRouter } from "next/navigation";
import { useState } from "react";

/** Hero pincode box (mockup `.pinbox` + `.gps`). Submitting navigates to the
 * ISR results route /[pincode]; GPS resolves via the identity BFF proxy then
 * navigates. Distinct from the header LiveLocationPill (that's the switcher). */
export function PincodeHero() {
  const router = useRouter();
  const [pincode, setPincode] = useState("");

  function go(next: string) {
    if (/^\d{6}$/.test(next)) router.push(`/${next}`);
  }

  function useGps() {
    if (typeof navigator === "undefined" || !navigator.geolocation) return;
    navigator.geolocation.getCurrentPosition(async (pos) => {
      const { latitude, longitude } = pos.coords;
      try {
        const res = await fetch(`/api/identity/location?lat=${latitude}&lng=${longitude}`, {
          credentials: "include",
        });
        if (!res.ok) return;
        const body = (await res.json()) as { pincode?: string | null };
        if (body.pincode) go(body.pincode);
      } catch {
        /* GPS resolve failed — user can still type a pincode */
      }
    });
  }

  return (
    <div className="flex flex-col items-center gap-3">
      <form
        onSubmit={(e) => {
          e.preventDefault();
          go(pincode);
        }}
        className="w-full"
      >
        <PincodeInput
          findLabel="Find milk"
          aria-label="Enter pincode"
          placeholder="Enter pincode"
          value={pincode}
          findDisabled={pincode.length !== 6}
          onFind={() => go(pincode)}
          onChange={(e) => setPincode(e.target.value.replace(/\D/g, ""))}
        />
      </form>
      <GpsPill type="button" onClick={useGps}>
        📍 Or use my location · என் இடம்
      </GpsPill>
    </div>
  );
}
```

- [ ] **Step 2: Rewrite the home** — `apps/web-milk/app/page.tsx`

```tsx
import { buildMetadata, canonicalUrl } from "@agri/ui/seo";
import type { Metadata } from "next";

import { PincodeHero } from "./pincode-hero";

const SITE = "https://milk.in";
export const revalidate = 3600; // static hero; no per-visitor data

export const metadata: Metadata = buildMetadata({
  title: "Milk near you — all options, one place | Milk.in",
  description: "Enter your pincode to find cow, buffalo, A2 and organic milk vendors, brands and farm-fresh delivery near you across Tamil Nadu.",
  canonical: canonicalUrl(SITE, "/"),
  siteName: "Milk.in",
});

/** WebSite + Organization — hand-built (no webSite/organization builder in
 * @agri/ui/seo). `<` escaped so it can never close the script tag. */
function homeJsonLd(): string {
  const graph = {
    "@context": "https://schema.org",
    "@graph": [
      { "@type": "WebSite", name: "Milk.in", url: SITE },
      { "@type": "Organization", name: "Milk.in", url: SITE },
    ],
  };
  return JSON.stringify(graph).replaceAll("<", "\\u003c");
}

export default function HomePage() {
  return (
    <main className="bg-gradient-to-b from-brand-deep to-brand">
      <script type="application/ld+json" dangerouslySetInnerHTML={{ __html: homeJsonLd() }} />
      <section className="mx-auto flex w-full max-w-[720px] flex-col items-center gap-4 px-4 py-14 text-center">
        <h1 className="font-display text-[clamp(22px,5vw,32px)] font-extrabold text-white">
          Milk near you — all options, one place
        </h1>
        <p className="text-[15px] text-white/85">
          உங்கள் பகுதியில் உள்ள எல்லா பால் · brands, local vendors, farm-fresh delivery
        </p>
        <PincodeHero />
      </section>
    </main>
  );
}
```

> Confirm `from-brand-deep`/`to-brand` gradient utilities resolve against the token colors (the mockup hero is a `linear-gradient(160deg, --mk-deep, --mk)`). If Tailwind gradient-from/to tokens aren't wired for these names, use an inline `style` with `var(--brand-deep)`/`var(--brand)` — those CSS vars are token-defined, not raw hex, so `check:hex` stays clean.

- [ ] **Step 3: Typecheck + build + hex check**

Run: `pnpm --filter @agri/web-milk typecheck && pnpm --filter @agri/web-milk build && pnpm --filter @agri/web-milk check:hex`
Expected: all PASS.

- [ ] **Step 4: Commit**

```bash
git add apps/web-milk/app/pincode-hero.tsx apps/web-milk/app/page.tsx
git commit -m "feat(d23): pincode-first ISR home hero + JSON-LD"
```

---

## Task 12: sitemap

**Files:**
- Create: `apps/web-milk/app/sitemap.ts`

**Interfaces:**
- Produces: `app/sitemap.ts` default export → home + curated launch-pincode landing URLs. (Dynamic covered-pincode enumeration lands D28.)

- [ ] **Step 1: Create the sitemap** — `apps/web-milk/app/sitemap.ts`

```ts
import type { MetadataRoute } from "next";

const SITE = "https://milk.in";

// Curated launch pincodes (Coimbatore metro). Full covered-pincode
// enumeration + per-pincode landing detail lands D28.
const LAUNCH_PINCODES = ["641001", "641002", "641004", "641012", "641045"];

export default function sitemap(): MetadataRoute.Sitemap {
  return [
    { url: `${SITE}/`, changeFrequency: "daily", priority: 1 },
    ...LAUNCH_PINCODES.map((p) => ({
      url: `${SITE}/${p}`,
      changeFrequency: "daily" as const,
      priority: 0.8,
    })),
  ];
}
```

- [ ] **Step 2: Typecheck + build (verify /sitemap.xml emitted)**

Run: `pnpm --filter @agri/web-milk build`
Expected: build output lists `/sitemap.xml`.

- [ ] **Step 3: Commit**

```bash
git add apps/web-milk/app/sitemap.ts
git commit -m "feat(d23): web-milk sitemap (home + launch pincodes)"
```

---

## Task 13: E2E — three empty-state branches render

**Files:**
- Create: `e2e/milk-home.spec.ts`
- Modify: `e2e/playwright.config.ts` (add seed to `webServer`)

**Interfaces:**
- Consumes: the running web-milk on `http://localhost:3000` + seeded data (Task 6).

- [ ] **Step 1: Wire the seed into Playwright** — modify `e2e/playwright.config.ts`

Add a `webServer` entry BEFORE the web-milk entry so the milk vendor exists when milk boots (the API entry already ran migrations + geo load):

```ts
    {
      // D23: deterministic milk vendor on 641001 for the 'covered' branch.
      command: "pnpm --filter @agri/core-backend run seed:e2e-milk",
      // one-shot seed: no server to wait on — treat its own port check as the API's health
      url: "http://127.0.0.1:8000/health",
      reuseExistingServer: true,
    },
```

> This assumes a `seed:e2e-milk` script. If the backend package has no npm script runner, instead run the seed inside the existing `e2e:api` command (append `&& python scripts/seed_e2e_milk.py` to that script in the root `package.json`). Pick whichever matches how `pnpm run e2e:api` is defined — the goal is: seed runs once, after migrations, before the milk-home tests.

- [ ] **Step 2: Write the spec** — `e2e/milk-home.spec.ts`

```ts
import { expect, test } from "@playwright/test";

// web-milk runs on :3000 but the Playwright baseURL is web-id (:3003),
// so every navigation here uses an absolute URL.
const MILK = "http://localhost:3000";

test.describe("D23 milk pincode home — three empty-state branches", () => {
  test("(a) covered TN pincode with a seeded vendor shows results", async ({ page }) => {
    await page.goto(`${MILK}/641001`);
    await expect(page.getByTestId("scope-covered")).toBeVisible();
    await expect(page.getByTestId("type-filter-row")).toBeVisible();
    await expect(page.getByTestId("price-banner")).toBeVisible();
    await expect(page.getByRole("heading", { name: /Local vendors/i })).toBeVisible();
  });

  test("(b) valid TN pincode with no vendors shows the warm district state + notify-me", async ({ page }) => {
    await page.goto(`${MILK}/641999`);
    await expect(page.getByTestId("scope-tn-no-vendors")).toBeVisible();
    await expect(page.getByText(/No milk vendors in/i)).toBeVisible();
    await expect(page.getByTestId("notify-me")).toBeVisible();
  });

  test("(c) non-TN pincode shows the out-of-area state + notify-me", async ({ page }) => {
    await page.goto(`${MILK}/110001`);
    await expect(page.getByTestId("scope-out-of-area")).toBeVisible();
    await expect(page.getByText(/live in Tamil Nadu/i)).toBeVisible();
    await expect(page.getByTestId("notify-me")).toBeVisible();
  });

  test("notify-me submits from the out-of-area state", async ({ page }) => {
    await page.goto(`${MILK}/110001`);
    await page.getByRole("button", { name: /notify me/i }).click();
    await expect(page.getByTestId("notify-done")).toBeVisible();
  });
});
```

> `641999` must be a TN pincode present in geo with no coverage — align with the value used in the pytest fixtures (Task 4). If the geo dataset doesn't contain `641999`, pick a seeded TN pincode that has no business coverage.

- [ ] **Step 3: Run the E2E**

Run: `pnpm e2e -- milk-home.spec.ts`
Expected: 4 tests PASS. (Playwright boots API + seed + web-id + web-milk + web-organic per the config.)

- [ ] **Step 4: Commit**

```bash
git add e2e/milk-home.spec.ts e2e/playwright.config.ts
git commit -m "test(d23): E2E three empty-state branches + notify-me"
```

---

## Task 14: full-gate verification + PR

**Files:** none (verification + PR).

- [ ] **Step 1: Backend gates**

Run: `cd backend/core && python -m pytest -q && mypy modules/directory shared && ruff check . && ruff format --check . && python scripts/dump_public_routes.py --check`
Expected: all green.

- [ ] **Step 2: Frontend gates**

Run: `pnpm --filter @agri/web-milk typecheck && pnpm --filter @agri/web-milk lint && pnpm --filter @agri/web-milk build && pnpm --filter @agri/web-milk check:hex && pnpm --filter @agri/ui test`
Expected: all green.

- [ ] **Step 3: import-linter (module independence) + lint-imports**

Run: `cd backend/core && lint-imports`
Expected: PASS — `milk_home` imports only covers/catalog/specs/geo, never notify/audit/search.

- [ ] **Step 4: Lighthouse (local, matches the CI gate)**

Run the repo's Lighthouse CI command against `http://localhost:3000/` and `http://localhost:3000/641001` (with API + seed + web-milk running). Expected: performance/SEO/best-practices/a11y each ≥ 90. If a metric dips: check CLS (skeletons/reserved dimensions), ensure JSON-LD + metadata land in `<head>` (the `htmlLimitedBots`/`Chrome-Lighthouse` config already handles streamed metadata), and that the hero image/gradient isn't render-blocking.

- [ ] **Step 5: git status zero + committed-tree verify, then push + PR**

```bash
git status --short          # expect empty
git log --oneline dev..HEAD # review the D23 commits
git push -u origin feat/d23-milk-home
gh pr create --base dev --title "feat(d23): milk pincode home" --body "$(cat <<'EOF'
## D23 — Pincode-First Milk Home + Empty-State Contract

Backend blend endpoint `GET /catalog/milk/home/{pincode}` (covers + products +
geo → 3-way scope, schema-driven filters, computed price banner), public
`POST /leads/pincode-interest` notify-me capture (new `leads.pincode_interest`,
migration 0023), and web-milk ISR home `/` + `/[pincode]` results with JSON-LD.

### Non-negotiables
- ✅ Three empty-state branches render (pytest + E2E: 641001 seeded / 641999 no-vendor / 110001 non-TN)
- ✅ Milk-type filters driven by the D17 `active_schema("milk")` set, not hardcoded
- ✅ Home ISR/SSR + JSON-LD + Lighthouse ≥90
- ✅ Price banner computed from real `price_display` listings

🤖 Generated with [Claude Code](https://claude.com/claude-code)
EOF
)"
```
Expected: PR opens against `dev` (never `main`).

---

## Self-Review

**Spec coverage** (D23 A–F + non-negotiables):
- A. Pincode-first hero (ISR) + GPS → Task 11 (`page.tsx`, `PincodeHero`). ✅
- B. Three-way empty-state contract → Task 4 (scope logic), Task 10 (render), Task 13 (E2E). ✅
- C. TypeFilterRow schema-driven → Task 4 (`_milk_filter_keys`), Task 9 (`TypeFilterRow`). ✅
- D. Price-range banner from listings → Task 3 (`compute_price_banner`), Task 10 (render). ✅
- E. Location wired (persist + LocationPill) → **already implemented** by `LiveLocationPill` + `header-location.tsx` (no new task); the hero adds its own navigate-to-pincode box (Task 11). Cookie/profile-persist paths are the existing D19 code. ✅
- F. SEO (SSR/ISR, JSON-LD, sitemap) → Task 10 (pincode JSON-LD/noindex), Task 11 (home JSON-LD), Task 12 (sitemap). ✅
- Notify-me persistence → Tasks 1–2. ✅
- Threat model (rate-limit, keyset, validation, no PII) → inherited from SecureRouter + `^\d{6}$` guards + public-only directory data (Global Constraints). ✅

**Placeholder scan:** every code step contains full code; `TODO`-free (migration THREAT block is prose, not a TODO). Verification-only steps (Task 14) reference the repo's existing gate commands. Remaining `>`-annotations are reviewer caveats to confirm exact token/fixture names against the live repo, not deferred work.

**Type consistency:** `MilkHomeResult`/`MilkCard` (Task 4) → `milk_home_out`/`MilkHomeOut` (Task 5) → `MilkHome`/`MilkCard` TS (Task 8) → page render (Task 10). Field names align across all layers: `scope`, `location{pincode,district,state}`, `filters: string[]`, `price_banner{lines,seller_count}`, `vendors`/`brands`, `next_cursor`. `compute_price_banner` returns `(list[PriceBand], int)` consumed identically in Tasks 4 and 5. `record_pincode_interest` signature matches its Task-2 caller.

**Known confirm-in-repo points** (flagged inline with `>`): async-session/client fixture names; a TN pincode that is in geo but uncovered (`641999` placeholder); exact WA/call token class names; `User(...)` construction vs an identity helper in the seed; the `seed:e2e-milk` wiring vs appending to `e2e:api`. These are name-alignment checks, not design gaps.
