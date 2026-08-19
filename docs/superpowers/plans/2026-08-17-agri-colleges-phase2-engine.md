# Agri-colleges Phase 2, Plan 1 — engine and import Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Stand up the `education` module — ORM models, migration, SELECT-only grants — and an idempotent importer that loads the 772-row seed bundle into Postgres and publishes fat events so hub search can index it.

**Architecture:** A read-only engine. Five tables in a new `education` schema, mirroring the frozen CSV contract the data track has validated against since D41. `seed_import.py` imports `scripts/education_seed_contract.py` **verbatim** — the same module `validate_education_seed` uses — so the importer cannot accept a bundle the gate rejects. Nothing in this plan touches `apps/`, so it can merge independently of A-U4.

**Tech Stack:** Python 3.12, SQLAlchemy 2 (async), Alembic, asyncpg, pytest 8, ruff (line-length 100, `T20` bans bare `print`), mypy.

**Spec:** `docs/superpowers/specs/2026-08-16-agri-colleges-design.md` (§4 data model, §8 CSV contract, §9 import pipeline, §10 gates)

## Global Constraints

- **Migration head is `0048_coins_streak`.** This plan adds `0049`. A-U4 landed `0047_ai_assistant` and `0048_coins_streak` after this plan was first written, and the numbers here were updated on 18 Aug when that merge came in. Verify with `ls backend/core/alembic/versions/` before writing — if another migration landed since, renumber again.
- **`app_rt` gets SELECT only** on every `education` table (spec §4 Grants). Every other schema grants INSERT/UPDATE/DELETE; this one must not. The importer runs as the `app` owner, not `app_rt`.
- **Modules must not import each other** (`pyproject.toml`, import-linter contract "Modules must not import each other"). `modules.education` must be added to that contract's `modules` list. It may import `shared.*` only.
- **Nothing under `apps/` is touched by this plan.** That is what lets it merge before A-U4.
- Ruff line-length **100**; lint set `E,F,I,UP,B,SIM,T20`. `T20` bans `print` — CLI output needs `# noqa: T201`, as in `scripts/import_vendor_seed.py`.
- Run `ruff format` and `ruff check --fix` **per task**, not once at the end.
- All IDs are UUIDv7 via `UUIDv7PKMixin`. Slugs are immutable via `ImmutableSlugMixin`.
- Commit in logical units. **Do not push** until the owner says "EOD push"; never merge a PR yourself.

---

### Task 1: Schema, models and grants

**Files:**
- Create: `backend/core/modules/education/__init__.py`
- Create: `backend/core/modules/education/models.py`
- Create: `backend/core/alembic/versions/0049_education_engine.py`
- Modify: `pyproject.toml` (import-linter contract list)
- Test: `backend/core/tests/test_education_models.py`

**Interfaces:**
- Consumes: `shared.db.Base`, `UUIDv7PKMixin`, `TimestampMixin`; `shared.slugs.ImmutableSlugMixin`.
- Produces: `Institution`, `Programme`, `InstitutionProgramme`, `StudentResource`, `Guide` ORM classes in schema `education`, each carrying the columns of the frozen CSV contract (spec §8) plus `id`, `created_at`, `updated_at`.

- [ ] **Step 1: Confirm the migration head**

Run: `ls backend/core/alembic/versions/*.py | sort | tail -3`
Expected: `0048_coins_streak.py` is last. If not, use the next free number everywhere below instead of `0049`.

- [ ] **Step 2: Write the failing model test**

Create `backend/core/tests/test_education_models.py`:

```python
"""education engine ORM: the five tables of spec section 4 exist, and app_rt cannot write."""

import pytest
from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine

from modules.education.models import (
    Guide,
    Institution,
    InstitutionProgramme,
    Programme,
    StudentResource,
)


async def test_all_five_tables_exist(db_session: AsyncSession) -> None:
    for model in (Institution, Programme, InstitutionProgramme, StudentResource, Guide):
        # A select against an absent table raises; reaching 0 rows proves it is there.
        assert await db_session.scalar(select(model).limit(1)) is None


async def test_institution_slug_is_unique(db_session: AsyncSession) -> None:
    from datetime import date

    def _row(name: str) -> Institution:
        return Institution(
            slug="tnau-coimbatore", name_en=name, kind="state_agri_university",
            country_code="IN", trust="verified", status="active",
            source_url="https://tnau.ac.in/", last_verified_at=date(2026, 8, 10),
        )

    db_session.add(_row("TNAU"))
    await db_session.flush()
    db_session.add(_row("Duplicate"))
    with pytest.raises(Exception):
        await db_session.flush()


async def test_app_rt_cannot_write_to_education(admin_database_url: str) -> None:
    """Spec section 4: app_rt is SELECT-only here, unlike every other schema."""
    engine = create_async_engine(admin_database_url.replace("app:", "app_rt:"))
    try:
        async with engine.connect() as conn:
            with pytest.raises(Exception) as excinfo:
                await conn.execute(
                    text(
                        "INSERT INTO education.institutions "
                        "(id, slug, name_en, kind, country_code, trust, status, "
                        " source_url, last_verified_at) "
                        "VALUES (gen_random_uuid(), 'x', 'x', 'x', 'IN', 'listed', "
                        "'active', 'https://x', '2026-01-01')"
                    )
                )
            assert "permission denied" in str(excinfo.value).lower()
    finally:
        await engine.dispose()
```

- [ ] **Step 3: Run it to verify it fails**

Run: `cd backend/core && python -m pytest tests/test_education_models.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'modules.education'`

- [ ] **Step 4: Write the models**

Create `backend/core/modules/education/__init__.py` as an empty file.

Create `backend/core/modules/education/models.py`. Column names come straight from the frozen CSV headers in spec §8 — the importer maps CSV column to model attribute one-to-one, so a rename here breaks it:

```python
"""Education engine ORM models. Tables land in 0049.

Read-only by design: `app_rt` holds SELECT and nothing else (spec section 4),
because every row arrives from a reviewed seed commit, never from a user.

`trust` is the load-bearing column. A `listed` row came from a bulk national
directory and has not been checked against the institution's own page, so the
surfaces must branch on `trust` — never on whether a field happens to be
populated — before rendering a fee, a seat count or an admission route.
"""

from __future__ import annotations

import uuid
from datetime import date
from typing import Any

from sqlalchemy import Boolean, Date, ForeignKey, Integer, Numeric, Text, UniqueConstraint
from sqlalchemy.dialects import postgresql
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from shared.db import Base, TimestampMixin, UUIDv7PKMixin
from shared.geo.models import District, State
from shared.slugs import ImmutableSlugMixin

SCHEMA = "education"


class Institution(UUIDv7PKMixin, ImmutableSlugMixin, TimestampMixin, Base):
    __tablename__ = "institutions"
    __table_args__ = {"schema": SCHEMA}

    name_en: Mapped[str] = mapped_column(Text, nullable=False)
    name_ta: Mapped[str | None] = mapped_column(Text)
    name_hi: Mapped[str | None] = mapped_column(Text)
    short_name: Mapped[str | None] = mapped_column(Text)
    kind: Mapped[str] = mapped_column(Text, nullable=False)
    is_government: Mapped[bool | None] = mapped_column(Boolean)
    parent_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey(f"{SCHEMA}.institutions.id", ondelete="RESTRICT")
    )
    country_code: Mapped[str] = mapped_column(Text, nullable=False, default="IN")
    # ASYMMETRIC ON PURPOSE, and the asymmetry is the point.
    #
    # state_id is a real cross-schema FK, as spec section 4 requires. All 36
    # states are in data/geo/states.csv, so the constraint can never reject a
    # valid row, and geo.districts already declares ForeignKey("geo.states.id")
    # -- the cross-schema reference is the house idiom, not a new risk.
    #
    # district_id is NOT an FK. data/geo/districts.csv holds 38 rows, all of
    # them Tamil Nadu (state_lgd_code 33), until D65. An FK would reject a
    # valid Punjab college outright. So it stores the district's LGD code as
    # a plain integer and reads join on District.lgd_code -- district
    # filtering therefore resolves inside Tamil Nadu only today. That is a
    # data gap, not a schema bug, and it closes when D65 loads the rest.
    state_id: Mapped[uuid.UUID | None] = mapped_column(
        postgresql.UUID(as_uuid=True), ForeignKey("geo.states.id", ondelete="RESTRICT"), index=True
    )
    district_id: Mapped[int | None] = mapped_column(Integer, index=True)
    pincode: Mapped[str | None] = mapped_column(Text)
    lat: Mapped[float | None] = mapped_column(Numeric(9, 6))
    lng: Mapped[float | None] = mapped_column(Numeric(9, 6))
    address: Mapped[str | None] = mapped_column(Text)
    website: Mapped[str | None] = mapped_column(Text)
    contact_phone: Mapped[str | None] = mapped_column(Text)
    contact_email: Mapped[str | None] = mapped_column(Text)
    established_year: Mapped[int | None] = mapped_column(Integer)
    accreditation: Mapped[dict[str, Any] | None] = mapped_column(JSONB)
    trust: Mapped[str] = mapped_column(Text, nullable=False, default="listed")
    status: Mapped[str] = mapped_column(Text, nullable=False, default="active")
    merged_into_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey(f"{SCHEMA}.institutions.id", ondelete="RESTRICT")
    )
    source_url: Mapped[str] = mapped_column(Text, nullable=False)
    last_verified_at: Mapped[date] = mapped_column(Date, nullable=False)

    # Relationships exist so the read API can eager-load rather than N+1 a
    # detail page. None is lazy="selectin": a list query must not silently
    # pay for the detail page's joins. Async SQLAlchemy raises on implicit
    # lazy load, so a forgotten selectinload() fails loudly -- which is what
    # we want. Plan 2's serializer reads exactly these five.
    state: Mapped["State | None"] = relationship("State", lazy="raise")
    district: Mapped["District | None"] = relationship("District", lazy="raise")
    parent: Mapped["Institution | None"] = relationship(
        "Institution", remote_side="Institution.id", foreign_keys=[parent_id],
        back_populates="constituents", lazy="raise",
    )
    constituents: Mapped[list["Institution"]] = relationship(
        "Institution", foreign_keys=[parent_id], back_populates="parent", lazy="raise",
    )
    merged_into: Mapped["Institution | None"] = relationship(
        "Institution", remote_side="Institution.id", foreign_keys=[merged_into_id],
        lazy="raise",
    )
    offerings: Mapped[list["InstitutionProgramme"]] = relationship(
        "InstitutionProgramme", back_populates="institution", lazy="raise",
    )


class Programme(UUIDv7PKMixin, ImmutableSlugMixin, TimestampMixin, Base):
    __tablename__ = "programmes"
    __table_args__ = {"schema": SCHEMA}

    name_en: Mapped[str] = mapped_column(Text, nullable=False)
    name_ta: Mapped[str | None] = mapped_column(Text)
    name_hi: Mapped[str | None] = mapped_column(Text)
    level: Mapped[str] = mapped_column(Text, nullable=False)
    discipline: Mapped[str] = mapped_column(Text, nullable=False)
    duration_months: Mapped[int | None] = mapped_column(Integer)
    description_en: Mapped[str | None] = mapped_column(Text)
    description_ta: Mapped[str | None] = mapped_column(Text)
    description_hi: Mapped[str | None] = mapped_column(Text)


class InstitutionProgramme(UUIDv7PKMixin, TimestampMixin, Base):
    __tablename__ = "institution_programmes"
    __table_args__ = (
        UniqueConstraint("institution_id", "programme_id", name="uq_inst_prog"),
        {"schema": SCHEMA},
    )

    institution_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey(f"{SCHEMA}.institutions.id", ondelete="CASCADE"), nullable=False
    )
    programme_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey(f"{SCHEMA}.programmes.id", ondelete="RESTRICT"), nullable=False
    )
    intake_seats: Mapped[int | None] = mapped_column(Integer)
    # Integer, though spec section 4 says Numeric. DELIBERATE: every one of
    # the 277 fee values in the seed is whole rupees, nobody quotes paise in
    # an annual fee, and Numeric would put a Decimal on the wire -- which the
    # D24 covers work already had to serialize as a string to stop it
    # arriving as a float. An int is exact, JSON-native and needs no
    # convention. Recorded in the spec by Plan 2 Task 5.
    annual_fees_inr: Mapped[int | None] = mapped_column(Integer)
    fee_note: Mapped[str | None] = mapped_column(Text)
    admission_route: Mapped[str | None] = mapped_column(Text)
    source_url: Mapped[str] = mapped_column(Text, nullable=False)
    last_verified_at: Mapped[date] = mapped_column(Date, nullable=False)

    institution: Mapped["Institution"] = relationship(
        "Institution", back_populates="offerings", lazy="raise"
    )
    programme: Mapped["Programme"] = relationship("Programme", lazy="raise")


class StudentResource(UUIDv7PKMixin, ImmutableSlugMixin, TimestampMixin, Base):
    __tablename__ = "student_resources"
    __table_args__ = {"schema": SCHEMA}

    name_en: Mapped[str] = mapped_column(Text, nullable=False)
    name_ta: Mapped[str | None] = mapped_column(Text)
    name_hi: Mapped[str | None] = mapped_column(Text)
    kind: Mapped[str] = mapped_column(Text, nullable=False)
    category: Mapped[str | None] = mapped_column(Text)
    scope: Mapped[str] = mapped_column(Text, nullable=False)
    provider: Mapped[str | None] = mapped_column(Text)
    levels: Mapped[str | None] = mapped_column(Text)
    eligibility_en: Mapped[str | None] = mapped_column(Text)
    eligibility_ta: Mapped[str | None] = mapped_column(Text)
    eligibility_hi: Mapped[str | None] = mapped_column(Text)
    benefit: Mapped[str | None] = mapped_column(Text)
    applies_to: Mapped[dict[str, Any] | None] = mapped_column(JSONB)
    window: Mapped[dict[str, Any] | None] = mapped_column(JSONB)
    official_url: Mapped[str] = mapped_column(Text, nullable=False)
    last_verified_at: Mapped[date] = mapped_column(Date, nullable=False)
    status: Mapped[str] = mapped_column(Text, nullable=False, default="active")


class Guide(UUIDv7PKMixin, ImmutableSlugMixin, TimestampMixin, Base):
    __tablename__ = "guides"
    __table_args__ = {"schema": SCHEMA}

    title_en: Mapped[str] = mapped_column(Text, nullable=False)
    title_ta: Mapped[str | None] = mapped_column(Text)
    title_hi: Mapped[str | None] = mapped_column(Text)
    kind: Mapped[str] = mapped_column(Text, nullable=False)
    country_code: Mapped[str | None] = mapped_column(Text)
    state_id: Mapped[uuid.UUID | None] = mapped_column(
        postgresql.UUID(as_uuid=True), ForeignKey("geo.states.id", ondelete="RESTRICT")
    )
    summary_en: Mapped[str | None] = mapped_column(Text)
    summary_ta: Mapped[str | None] = mapped_column(Text)
    summary_hi: Mapped[str | None] = mapped_column(Text)
    steps: Mapped[list[dict[str, Any]] | None] = mapped_column(JSONB)
    # A flat list of URL strings, matching official_links_json in the seed
    # (verified against guides.csv) -- NOT a list of {label, url} objects.
    official_links: Mapped[list[str] | None] = mapped_column(JSONB)
    last_verified_at: Mapped[date] = mapped_column(Date, nullable=False)
    status: Mapped[str] = mapped_column(Text, nullable=False, default="draft")
```

- [ ] **Step 5: Write the migration**

Create `backend/core/alembic/versions/0049_education_engine.py`. Read `0048_coins_streak.py` first and copy its header and revision style exactly.

The grant is the line to get right — **SELECT only**, unlike every other migration in the tree:

```python
"""education engine: five tables, SELECT-only for app_rt.

Design notes:
- New `education` schema. Nothing here is user-writable: every row arrives from a
  reviewed seed commit, so app_rt gets SELECT and nothing else. That is deliberate
  and differs from 0023/0027/0038/0045/0046/0048, which all grant DML.
- state_id is a real cross-schema FK to geo.states.id (spec section 4). All 36
  states are loaded, so the constraint cannot reject a valid row.
- district_id is deliberately NOT an FK: data/geo/districts.csv is Tamil Nadu only
  (38 rows, state 33) until D65, so a constraint would reject a valid Punjab
  college. It holds the LGD code as a plain integer and reads join on
  District.lgd_code. District filtering resolves inside TN only until then.
- No enum types. kind/trust/status are Text, validated by the seed contract, which
  rejects a bad value before the importer ever sees it.
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0049"
down_revision: str | Sequence[str] | None = "0048"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

TABLES = ("institutions", "programmes", "institution_programmes", "student_resources", "guides")

_TS = dict(server_default=sa.text("now()"), nullable=False)


def upgrade() -> None:
    op.execute("CREATE SCHEMA IF NOT EXISTS education")

    op.create_table(
        "institutions",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("slug", sa.Text(), nullable=False, unique=True),
        sa.Column("name_en", sa.Text(), nullable=False),
        sa.Column("name_ta", sa.Text()),
        sa.Column("name_hi", sa.Text()),
        sa.Column("short_name", sa.Text()),
        sa.Column("kind", sa.Text(), nullable=False),
        sa.Column("is_government", sa.Boolean()),
        sa.Column("parent_id", postgresql.UUID(as_uuid=True),
                  sa.ForeignKey("education.institutions.id", ondelete="RESTRICT")),
        sa.Column("country_code", sa.Text(), nullable=False, server_default="IN"),
        sa.Column("state_id", postgresql.UUID(as_uuid=True),
                  sa.ForeignKey("geo.states.id", ondelete="RESTRICT")),
        sa.Column("district_id", sa.Integer()),  # LGD code, not an FK -- see the docstring
        sa.Column("pincode", sa.Text()),
        sa.Column("lat", sa.Numeric(9, 6)),
        sa.Column("lng", sa.Numeric(9, 6)),
        sa.Column("address", sa.Text()),
        sa.Column("website", sa.Text()),
        sa.Column("contact_phone", sa.Text()),
        sa.Column("contact_email", sa.Text()),
        sa.Column("established_year", sa.Integer()),
        sa.Column("accreditation", postgresql.JSONB()),
        sa.Column("trust", sa.Text(), nullable=False, server_default="listed"),
        sa.Column("status", sa.Text(), nullable=False, server_default="active"),
        sa.Column("merged_into_id", postgresql.UUID(as_uuid=True),
                  sa.ForeignKey("education.institutions.id", ondelete="RESTRICT")),
        sa.Column("source_url", sa.Text(), nullable=False),
        sa.Column("last_verified_at", sa.Date(), nullable=False),
        sa.Column("created_at", sa.TIMESTAMP(timezone=True), **_TS),
        sa.Column("updated_at", sa.TIMESTAMP(timezone=True), **_TS),
        schema="education",
    )
    # /colleges filters on these together; the ISR state pages filter on state_id alone.
    op.create_index("ix_institutions_state_trust", "institutions",
                    ["state_id", "trust", "status"], schema="education")
    op.create_index("ix_institutions_kind", "institutions", ["kind"], schema="education")

    op.create_table(
        "programmes",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("slug", sa.Text(), nullable=False, unique=True),
        sa.Column("name_en", sa.Text(), nullable=False),
        sa.Column("name_ta", sa.Text()),
        sa.Column("name_hi", sa.Text()),
        sa.Column("level", sa.Text(), nullable=False),
        sa.Column("discipline", sa.Text(), nullable=False),
        sa.Column("duration_months", sa.Integer()),
        sa.Column("description_en", sa.Text()),
        sa.Column("description_ta", sa.Text()),
        sa.Column("description_hi", sa.Text()),
        sa.Column("created_at", sa.TIMESTAMP(timezone=True), **_TS),
        sa.Column("updated_at", sa.TIMESTAMP(timezone=True), **_TS),
        schema="education",
    )
    op.create_index("ix_programmes_level", "programmes", ["level", "discipline"],
                    schema="education")

    op.create_table(
        "institution_programmes",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("institution_id", postgresql.UUID(as_uuid=True),
                  sa.ForeignKey("education.institutions.id", ondelete="CASCADE"),
                  nullable=False),
        sa.Column("programme_id", postgresql.UUID(as_uuid=True),
                  sa.ForeignKey("education.programmes.id", ondelete="RESTRICT"),
                  nullable=False),
        sa.Column("intake_seats", sa.Integer()),
        sa.Column("annual_fees_inr", sa.Integer()),
        sa.Column("fee_note", sa.Text()),
        sa.Column("admission_route", sa.Text()),
        sa.Column("source_url", sa.Text(), nullable=False),
        sa.Column("last_verified_at", sa.Date(), nullable=False),
        sa.Column("created_at", sa.TIMESTAMP(timezone=True), **_TS),
        sa.Column("updated_at", sa.TIMESTAMP(timezone=True), **_TS),
        sa.UniqueConstraint("institution_id", "programme_id", name="uq_inst_prog"),
        schema="education",
    )

    op.create_table(
        "student_resources",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("slug", sa.Text(), nullable=False, unique=True),
        sa.Column("name_en", sa.Text(), nullable=False),
        sa.Column("name_ta", sa.Text()),
        sa.Column("name_hi", sa.Text()),
        sa.Column("kind", sa.Text(), nullable=False),
        sa.Column("category", sa.Text()),
        sa.Column("scope", sa.Text(), nullable=False),
        sa.Column("provider", sa.Text()),
        sa.Column("levels", sa.Text()),
        sa.Column("eligibility_en", sa.Text()),
        sa.Column("eligibility_ta", sa.Text()),
        sa.Column("eligibility_hi", sa.Text()),
        sa.Column("benefit", sa.Text()),
        sa.Column("applies_to", postgresql.JSONB()),
        sa.Column("window", postgresql.JSONB()),
        sa.Column("official_url", sa.Text(), nullable=False),
        sa.Column("last_verified_at", sa.Date(), nullable=False),
        sa.Column("status", sa.Text(), nullable=False, server_default="active"),
        sa.Column("created_at", sa.TIMESTAMP(timezone=True), **_TS),
        sa.Column("updated_at", sa.TIMESTAMP(timezone=True), **_TS),
        schema="education",
    )
    op.create_index("ix_resources_kind_scope", "student_resources",
                    ["kind", "category", "scope"], schema="education")

    op.create_table(
        "guides",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("slug", sa.Text(), nullable=False, unique=True),
        sa.Column("title_en", sa.Text(), nullable=False),
        sa.Column("title_ta", sa.Text()),
        sa.Column("title_hi", sa.Text()),
        sa.Column("kind", sa.Text(), nullable=False),
        sa.Column("country_code", sa.Text()),
        sa.Column("state_id", postgresql.UUID(as_uuid=True),
                  sa.ForeignKey("geo.states.id", ondelete="RESTRICT")),
        sa.Column("summary_en", sa.Text()),
        sa.Column("summary_ta", sa.Text()),
        sa.Column("summary_hi", sa.Text()),
        sa.Column("steps", postgresql.JSONB()),
        sa.Column("official_links", postgresql.JSONB()),
        sa.Column("last_verified_at", sa.Date(), nullable=False),
        sa.Column("status", sa.Text(), nullable=False, server_default="draft"),
        sa.Column("created_at", sa.TIMESTAMP(timezone=True), **_TS),
        sa.Column("updated_at", sa.TIMESTAMP(timezone=True), **_TS),
        schema="education",
    )
    op.create_index("ix_guides_kind_status", "guides", ["kind", "status"], schema="education")

    for table in TABLES:
        op.execute(f"GRANT SELECT ON education.{table} TO app_rt")


def downgrade() -> None:
    for table in reversed(TABLES):
        op.drop_table(table, schema="education")
    op.execute("DROP SCHEMA IF EXISTS education")
```

- [ ] **Step 6: Register the module with import-linter**

In `pyproject.toml`, find the contract named `"Modules must not import each other"` and add `"modules.education"` to its `modules` list, keeping the existing order.

- [ ] **Step 7: Run the migration and the tests**

```bash
cd backend/core
python -m alembic upgrade head
python -m pytest tests/test_education_models.py -v
```
Expected: migration applies; 3 tests PASS.

Then prove the downgrade works, because a migration that cannot roll back is a migration you cannot deploy twice:
```bash
python -m alembic downgrade -1 && python -m alembic upgrade head
```

- [ ] **Step 8: Lint, type-check, commit**

```bash
cd backend/core && ruff format . && ruff check --fix . && python -m mypy . && ./.venv/Scripts/lint-imports.exe
git add backend/core/modules/education/ backend/core/alembic/versions/0049_education_engine.py backend/core/tests/test_education_models.py pyproject.toml
git commit -m "feat(education): engine schema, models and SELECT-only grants

Five tables in a new education schema, mirroring the frozen CSV contract the
data track has validated against since D41.

app_rt gets SELECT and nothing else, which differs from every other migration
in the tree. Nothing here is user-writable: rows arrive only from a reviewed
seed commit, so write access would be surface area with no use case behind it.

state_id is a real cross-schema FK to geo.states.id, as spec section 4 asks:
all 36 states are loaded, so the constraint can never reject a valid row, and
geo.districts already FKs across schemas the same way.

district_id deliberately is not one. data/geo/districts.csv is Tamil Nadu only
-- 38 rows, all state 33 -- until D65, so an FK would reject a valid Punjab
college. It holds the LGD code as a plain integer instead, and district
filtering resolves inside TN only until the rest of the geo data lands."
```

---

### Task 2: Seed import that reuses the contract verbatim

**Files:**
- Create: `backend/core/modules/education/seed_import.py`
- Test: `backend/core/tests/test_education_seed_import.py`

**Interfaces:**
- Consumes: `scripts.education_seed_contract.load_bundle`, `load_geo_reference`, `validate`, `SeedContractError`; the five models from Task 1.
- Produces:
  - `@dataclass ImportReport` with `created: dict[str, int]`, `updated: dict[str, int]`
  - `async def import_bundle(session: AsyncSession, seed_dir: Path, geo_dir: Path, *, today: date) -> ImportReport`

- [ ] **Step 1: Write the failing test**

Create `backend/core/tests/test_education_seed_import.py`:

```python
"""seed_import validates through the SAME contract module the gate uses, then upserts."""

from datetime import date
from pathlib import Path

import pytest
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from modules.education.models import Institution, Programme
from modules.education.seed_import import ImportReport, import_bundle
from scripts.education_seed_contract import SeedContractError
from shared.geo.models import District, State

SEED = Path(__file__).resolve().parents[1] / "data" / "seeds" / "education"
GEO = Path(__file__).resolve().parents[1] / "data" / "geo"
TODAY = date(2026, 8, 17)


async def test_import_loads_the_committed_bundle(db_session: AsyncSession) -> None:
    report = await import_bundle(db_session, SEED, GEO, today=TODAY)
    assert isinstance(report, ImportReport)
    assert report.created["institutions"] > 700
    assert await db_session.scalar(
        select(func.count()).select_from(Institution)
    ) == report.created["institutions"]


async def test_import_is_idempotent(db_session: AsyncSession) -> None:
    first = await import_bundle(db_session, SEED, GEO, today=TODAY)
    second = await import_bundle(db_session, SEED, GEO, today=TODAY)
    assert second.created["institutions"] == 0
    assert second.updated["institutions"] == first.created["institutions"]
    assert await db_session.scalar(
        select(func.count()).select_from(Institution)
    ) == first.created["institutions"]


async def test_import_refuses_a_bundle_the_contract_rejects(
    db_session: AsyncSession, tmp_path: Path
) -> None:
    """The importer must not hold a looser idea of valid than the gate does."""
    for name in ("institutions.csv", "programmes.csv", "institution_programmes.csv",
                 "student_resources.csv", "guides.csv"):
        (tmp_path / name).write_text("slug\n", encoding="utf-8")
    (tmp_path / "institutions.csv").write_text(
        "slug,name_en,kind,country_code,state,trust,status,source_url,last_verified_at\n"
        "abroad,Nowhere,nonsense,IN,Atlantis,verified,active,,\n",
        encoding="utf-8",
    )
    with pytest.raises(SeedContractError):
        await import_bundle(db_session, tmp_path, GEO, today=TODAY)
    assert await db_session.scalar(select(func.count()).select_from(Institution)) == 0


async def test_parent_and_programme_slugs_resolve_to_ids(db_session: AsyncSession) -> None:
    await import_bundle(db_session, SEED, GEO, today=TODAY)
    child = await db_session.scalar(
        select(Institution).where(Institution.slug == "acri-coimbatore")
    )
    parent = await db_session.scalar(
        select(Institution).where(Institution.slug == "tnau-coimbatore")
    )
    assert child is not None and parent is not None
    assert child.parent_id == parent.id
    assert await db_session.scalar(select(func.count()).select_from(Programme)) > 40


async def test_every_institution_resolves_to_a_real_state(db_session: AsyncSession) -> None:
    """state_id is an FK now, so an unresolved state is a constraint error
    rather than a silent null -- but a null is still possible if the NAME
    fails to match, and a corpus that imports with 772 null states would
    look completely healthy while every state page came up empty."""
    await import_bundle(db_session, SEED, GEO, today=TODAY)

    unresolved = await db_session.scalar(
        select(func.count())
        .select_from(Institution)
        .where(Institution.country_code == "IN", Institution.state_id.is_(None))
    )
    assert unresolved == 0, f"{unresolved} Indian institutions imported with no state"

    # And the FK points somewhere real, not at a stale id.
    assert await db_session.scalar(
        select(func.count()).select_from(Institution).join(
            State, Institution.state_id == State.id
        )
    ) > 700


async def test_the_seed_districts_are_not_silently_dropped(
    db_session: AsyncSession,
) -> None:
    """70 of the 772 rows carry a district, all Tamil Nadu, and all 70 match
    geo.districts by name. An importer that never assigned district_id would
    pass every other test in this file."""
    await import_bundle(db_session, SEED, GEO, today=TODAY)

    with_district = await db_session.scalar(
        select(func.count()).select_from(Institution).where(Institution.district_id.is_not(None))
    )
    assert with_district >= 70, f"only {with_district} rows got a district_id"

    # district_id holds an LGD code, NOT a geo.districts PK -- the join is on
    # lgd_code. Getting this backwards yields zero rows, not an error.
    joined = await db_session.scalar(
        select(func.count())
        .select_from(Institution)
        .join(District, Institution.district_id == District.lgd_code)
    )
    assert joined >= 70
```

- [ ] **Step 2: Run it to verify it fails**

Run: `cd backend/core && python -m pytest tests/test_education_seed_import.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'modules.education.seed_import'`

- [ ] **Step 3: Write the importer**

Create `backend/core/modules/education/seed_import.py`:

```python
"""Load the committed education seed bundle into Postgres.

Validation is NOT reimplemented here. This module imports
`scripts.education_seed_contract` and calls the same `validate()` the CI gate
calls, so there is exactly one definition of a valid bundle and the importer
cannot drift looser than the gate.

Idempotent by slug: a rerun updates in place rather than duplicating, which is
what makes reimporting after each seed commit safe.

Slug-to-id resolution runs in two passes, because `parent_slug` and
`merged_into_slug` may point at a row further down the same file.
"""

from __future__ import annotations

import csv
import json
import uuid
from collections.abc import Iterator
from dataclasses import dataclass, field
from datetime import date
from pathlib import Path
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from scripts.education_seed_contract import (
    SeedContractError,
    load_bundle,
    load_geo_reference,
    validate,
)
from shared.geo.models import State

from .models import Guide, Institution, InstitutionProgramme, Programme, StudentResource

_COUNTED = (
    "institutions", "programmes", "institution_programmes", "student_resources", "guides",
)


@dataclass
class ImportReport:
    created: dict[str, int] = field(default_factory=lambda: dict.fromkeys(_COUNTED, 0))
    updated: dict[str, int] = field(default_factory=lambda: dict.fromkeys(_COUNTED, 0))


def _int_or_none(v: str | None) -> int | None:
    v = (v or "").strip()
    return int(v) if v.isdigit() else None


def _json_or_none(v: str | None) -> Any:
    v = (v or "").strip()
    return json.loads(v) if v else None


def _bool_or_none(v: str | None) -> bool | None:
    return {"true": True, "false": False}.get((v or "").strip().lower())


async def _state_ids(session: AsyncSession) -> dict[str, uuid.UUID]:
    """State NAME (lowercased) -> geo.states.id.

    Read from the DATABASE, not from states.csv, because state_id is a real
    FK now and the CSV does not carry the UUID the constraint needs. This
    couples the import to geo being loaded first -- correctly so: without
    it every institution would silently import with a null state, and the
    /colleges state pages would come up empty with nothing failing.
    """
    rows = (await session.execute(select(State.name, State.id))).all()
    if not rows:
        raise SeedContractError(
            ["geo.states is empty -- run scripts/load_geo.py before importing education"]
        )
    return {name.strip().lower(): state_id for name, state_id in rows}


def _district_lgd_codes(geo_dir: Path) -> dict[str, int]:
    """District NAME (lowercased) -> LGD code, the plain integer district_id holds.

    From the CSV, not the DB, because district_id is not an FK (see models.py).
    The file is Tamil Nadu only until D65, so a college outside TN resolves to
    None here -- which is honest: we do not know its district id, and 70 of the
    772 seed rows carry a district at all, all of them Tamil Nadu.
    """
    with (geo_dir / "districts.csv").open(encoding="utf-8") as fh:
        return {row["name"].strip().lower(): int(row["lgd_code"]) for row in csv.DictReader(fh)}


async def import_bundle(
    session: AsyncSession, seed_dir: Path, geo_dir: Path, *, today: date
) -> ImportReport:
    bundle = load_bundle(seed_dir)
    geo = load_geo_reference(geo_dir)
    validate(bundle, geo, today=today)  # raises SeedContractError; nothing written

    report = ImportReport()
    state_ids = await _state_ids(session)
    district_ids = _district_lgd_codes(geo_dir)

    # Pass 1: upsert institutions, leaving the self-references for pass 2.
    known = {i.slug: i for i in (await session.scalars(select(Institution))).all()}
    for row in bundle.institutions:
        obj = known.get(row["slug"])
        if obj is None:
            obj = Institution(slug=row["slug"])
            session.add(obj)
            report.created["institutions"] += 1
        else:
            report.updated["institutions"] += 1
        obj.name_en = row["name_en"]
        obj.name_ta = row.get("name_ta") or None
        obj.name_hi = row.get("name_hi") or None
        obj.short_name = row.get("short_name") or None
        obj.kind = row["kind"]
        obj.is_government = _bool_or_none(row.get("is_government"))
        obj.country_code = row.get("country_code") or "IN"
        obj.state_id = state_ids.get((row.get("state") or "").strip().lower())
        # Was missing entirely before: the seed carries a district for 70 rows
        # and every one of them resolves, so dropping it would have quietly
        # cost the district filter its only real data.
        obj.district_id = district_ids.get((row.get("district") or "").strip().lower())
        obj.pincode = row.get("pincode") or None
        obj.address = row.get("address") or None
        obj.website = row.get("website") or None
        obj.contact_phone = row.get("contact_phone") or None
        obj.contact_email = row.get("contact_email") or None
        obj.established_year = _int_or_none(row.get("established_year"))
        obj.accreditation = _json_or_none(row.get("accreditation_json"))
        obj.trust = row["trust"]
        obj.status = row["status"]
        obj.source_url = row["source_url"]
        obj.last_verified_at = date.fromisoformat(row["last_verified_at"])
        known[row["slug"]] = obj
    await session.flush()

    # Pass 2: every slug now has an id, so the self-references can be wired.
    for row in bundle.institutions:
        obj = known[row["slug"]]
        parent = row.get("parent_slug") or ""
        merged = row.get("merged_into_slug") or ""
        obj.parent_id = known[parent].id if parent else None
        obj.merged_into_id = known[merged].id if merged else None
    await session.flush()

    progs = {p.slug: p for p in (await session.scalars(select(Programme))).all()}
    for row in bundle.programmes:
        obj = progs.get(row["slug"])
        if obj is None:
            obj = Programme(slug=row["slug"])
            session.add(obj)
            report.created["programmes"] += 1
        else:
            report.updated["programmes"] += 1
        obj.name_en = row["name_en"]
        obj.name_ta = row.get("name_ta") or None
        obj.name_hi = row.get("name_hi") or None
        obj.level = row["level"]
        obj.discipline = row["discipline"]
        obj.duration_months = _int_or_none(row.get("duration_months"))
        obj.description_en = row.get("description_en") or None
        obj.description_ta = row.get("description_ta") or None
        obj.description_hi = row.get("description_hi") or None
        progs[row["slug"]] = obj
    await session.flush()

    pairs = {
        (ip.institution_id, ip.programme_id): ip
        for ip in (await session.scalars(select(InstitutionProgramme))).all()
    }
    for row in bundle.institution_programmes:
        key = (known[row["institution_slug"]].id, progs[row["programme_slug"]].id)
        obj = pairs.get(key)
        if obj is None:
            obj = InstitutionProgramme(institution_id=key[0], programme_id=key[1])
            session.add(obj)
            report.created["institution_programmes"] += 1
        else:
            report.updated["institution_programmes"] += 1
        obj.intake_seats = _int_or_none(row.get("intake_seats"))
        obj.annual_fees_inr = _int_or_none(row.get("annual_fees_inr"))
        obj.fee_note = row.get("fee_note") or None
        obj.admission_route = row.get("admission_route") or None
        obj.source_url = row["source_url"]
        obj.last_verified_at = date.fromisoformat(row["last_verified_at"])

    res = {r.slug: r for r in (await session.scalars(select(StudentResource))).all()}
    for row in bundle.student_resources:
        obj = res.get(row["slug"])
        if obj is None:
            obj = StudentResource(slug=row["slug"])
            session.add(obj)
            report.created["student_resources"] += 1
        else:
            report.updated["student_resources"] += 1
        obj.name_en = row["name_en"]
        obj.name_ta = row.get("name_ta") or None
        obj.name_hi = row.get("name_hi") or None
        obj.kind = row["kind"]
        obj.category = row.get("category") or None
        obj.scope = row["scope"]
        obj.provider = row.get("provider") or None
        obj.levels = row.get("levels") or None
        obj.eligibility_en = row.get("eligibility_en") or None
        obj.eligibility_ta = row.get("eligibility_ta") or None
        obj.eligibility_hi = row.get("eligibility_hi") or None
        obj.benefit = row.get("benefit") or None
        obj.applies_to = _json_or_none(row.get("applies_to_json"))
        obj.window = _json_or_none(row.get("window_json"))
        obj.official_url = row["official_url"]
        obj.last_verified_at = date.fromisoformat(row["last_verified_at"])
        obj.status = row.get("status") or "active"

    guides = {g.slug: g for g in (await session.scalars(select(Guide))).all()}
    for row in bundle.guides:
        obj = guides.get(row["slug"])
        if obj is None:
            obj = Guide(slug=row["slug"])
            session.add(obj)
            report.created["guides"] += 1
        else:
            report.updated["guides"] += 1
        obj.title_en = row["title_en"]
        obj.title_ta = row.get("title_ta") or None
        obj.title_hi = row.get("title_hi") or None
        obj.kind = row["kind"]
        obj.country_code = row.get("country_code") or None
        obj.state_id = state_ids.get((row.get("state") or "").strip().lower())
        obj.summary_en = row.get("summary_en") or None
        obj.summary_ta = row.get("summary_ta") or None
        obj.summary_hi = row.get("summary_hi") or None
        obj.steps = _json_or_none(row.get("steps_json"))
        obj.official_links = _json_or_none(row.get("official_links_json"))
        obj.last_verified_at = date.fromisoformat(row["last_verified_at"])
        obj.status = row.get("status") or "draft"

    await session.flush()
    return report
```

- [ ] **Step 4: Run the tests**

Run: `cd backend/core && python -m pytest tests/test_education_seed_import.py -v`
Expected: 4 PASS.

- [ ] **Step 5: Lint, type-check, commit**

```bash
cd backend/core && ruff format . && ruff check --fix . && python -m mypy . && ./.venv/Scripts/lint-imports.exe
git add backend/core/modules/education/seed_import.py backend/core/tests/test_education_seed_import.py
git commit -m "feat(education): idempotent seed import reusing the contract verbatim

Validation is not reimplemented. seed_import calls the same validate() the CI
gate calls, so there is one definition of a valid bundle and the importer
cannot drift looser than the gate that has guarded this data since D41.

Idempotent on slug: a rerun updates rather than duplicates, which is what makes
reimporting after a seed commit safe. Slug-to-id resolution runs in two passes
because parent_slug can point at a row further down the same file."
```

---

### Task 3: The import CLI

**Files:**
- Create: `backend/core/scripts/import_education_seed.py`
- Modify: `backend/core/tests/test_education_seed_import.py`

**Interfaces:**
- Consumes: `modules.education.seed_import.import_bundle`.
- Produces: `async def _main(argv: list[str]) -> int` — 0 on success, 1 on contract violation. `--dry-run` validates, reports, then rolls back.

- [ ] **Step 1: Write the failing test**

Append to `backend/core/tests/test_education_seed_import.py`:

```python
async def test_cli_dry_run_writes_nothing(db_session: AsyncSession, capsys) -> None:
    from scripts.import_education_seed import _main

    assert await _main(["--dry-run"]) == 0
    assert "DRY RUN" in capsys.readouterr().out
    assert await db_session.scalar(select(func.count()).select_from(Institution)) == 0
```

- [ ] **Step 2: Run it to verify it fails**

Run: `cd backend/core && python -m pytest tests/test_education_seed_import.py -k cli -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'scripts.import_education_seed'`

- [ ] **Step 3: Write the CLI**

Create `backend/core/scripts/import_education_seed.py`, mirroring `scripts/import_vendor_seed.py` for argument handling and session construction:

```python
"""Import the committed education seed bundle.

    cd backend/core
    python -m scripts.import_education_seed --dry-run
    python -m scripts.import_education_seed

Exit 0 = imported (or validated, under --dry-run). Exit 1 = contract violations
printed and nothing written. Runs as the `app` owner; app_rt holds SELECT only.
"""

from __future__ import annotations

import argparse
import asyncio
import sys
from datetime import UTC, datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from modules.education.seed_import import import_bundle  # noqa: E402
from scripts.education_seed_contract import SeedContractError  # noqa: E402
from shared.db import get_sessionmaker  # noqa: E402

_ROOT = Path(__file__).resolve().parents[1]


async def _main(argv: list[str]) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--seed-dir", type=Path, default=_ROOT / "data" / "seeds" / "education")
    parser.add_argument("--geo-dir", type=Path, default=_ROOT / "data" / "geo")
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args(argv)

    async with get_sessionmaker()() as session:
        try:
            report = await import_bundle(
                session, args.seed_dir, args.geo_dir, today=datetime.now(UTC).date()
            )
        except SeedContractError as exc:
            print(f"CONTRACT VIOLATIONS ({len(exc.violations)}) - nothing imported:")  # noqa: T201
            for violation in exc.violations:
                print(f"  {violation}")  # noqa: T201
            await session.rollback()
            return 1

        for name in report.created:
            print(  # noqa: T201
                f"  {name:<24} created {report.created[name]:>4}  "
                f"updated {report.updated[name]:>4}"
            )
        if args.dry_run:
            await session.rollback()
            print("DRY RUN - rolled back, nothing written")  # noqa: T201
        else:
            await session.commit()
            print("committed")  # noqa: T201
    return 0


def main() -> int:
    return asyncio.run(_main(sys.argv[1:]))


if __name__ == "__main__":
    raise SystemExit(main())
```

- [ ] **Step 4: Run the test and the CLI by hand**

```bash
cd backend/core
python -m pytest tests/test_education_seed_import.py -k cli -v
python -m scripts.import_education_seed --dry-run
```
Expected: test PASSES; the CLI prints per-entity counts then `DRY RUN - rolled back, nothing written`.

- [ ] **Step 5: Lint and commit**

```bash
cd backend/core && ruff format . && ruff check --fix . && python -m mypy .
git add backend/core/scripts/import_education_seed.py backend/core/tests/test_education_seed_import.py
git commit -m "feat(education): import CLI with a dry run that rolls back"
```

---

### Task 4: Fat-event publication for hub search

**Files:**
- Create: `backend/core/modules/education/search_sync.py`
- Modify: `backend/core/scripts/import_education_seed.py`
- Modify: `backend/core/modules/search/worker.py` (add the `education` stream)
- Modify: `backend/core/modules/search/indexing.py` (add the institution event types)
- Test: `backend/core/tests/test_education_search_sync.py`

**Interfaces:**
- Consumes: `shared.events.publish(stream: str, event_type: str, payload: dict) -> str`; `Institution` from Task 1.
- Produces: `def institution_snapshot(inst: Institution, state_name: str | None) -> dict[str, Any] | None`; `async def publish_institutions(rows: list[tuple[Institution, str | None]]) -> int`.

**Why a snapshot may be None:** the indexer keys deletes on a null snapshot (ADR-0007). A `listed`, `closed` or `merged` institution must not be searchable, so it publishes `snapshot: None`, which removes any document already indexed rather than leaving it stale.

- [ ] **Step 1: Write the failing test**

Create `backend/core/tests/test_education_search_sync.py`:

```python
"""Only verified, active institutions become searchable documents."""

from datetime import date

from modules.education.models import Institution
from modules.education.search_sync import institution_snapshot


def _inst(**over: object) -> Institution:
    base: dict[str, object] = dict(
        slug="tnau-coimbatore", name_en="Tamil Nadu Agricultural University",
        kind="state_agri_university", trust="verified", status="active",
        country_code="IN", source_url="https://tnau.ac.in/",
        last_verified_at=date(2026, 8, 10),
    )
    base.update(over)
    return Institution(**base)


def test_verified_active_institution_produces_a_snapshot() -> None:
    snap = institution_snapshot(_inst(), "Tamil Nadu")
    assert snap is not None
    assert snap["name"] == "Tamil Nadu Agricultural University"
    assert snap["url"] == "/colleges/tnau-coimbatore"
    assert snap["sites"] == ["agri"]


def test_listed_institution_produces_no_snapshot() -> None:
    # A listed row is unverified by definition; it must never surface in hub search.
    assert institution_snapshot(_inst(trust="listed"), "Tamil Nadu") is None


def test_closed_institution_produces_no_snapshot() -> None:
    assert institution_snapshot(_inst(status="closed"), "Tamil Nadu") is None


def test_merged_institution_produces_no_snapshot() -> None:
    assert institution_snapshot(_inst(status="merged"), "Tamil Nadu") is None
```

- [ ] **Step 2: Run it to verify it fails**

Run: `cd backend/core && python -m pytest tests/test_education_search_sync.py -v`
Expected: FAIL — no module `modules.education.search_sync`.

- [ ] **Step 3: Write search_sync**

Create `backend/core/modules/education/search_sync.py`:

```python
"""Publish institution snapshots for the D19 search worker.

SITES is duplicated from modules/directory/search_sync.py by hand. The
import-linter contract "Modules must not import each other" forbids importing
it, so a change there must be mirrored here — the same trade directory and
search already live with.

A snapshot of None means "not publicly visible". The indexer keys deletes on it
(ADR-0007), so flipping an institution to listed, closed or merged removes it
from the index on the next import instead of leaving a stale document behind.
"""

from __future__ import annotations

from typing import Any

from shared.events import publish

from .models import Institution

STREAM = "education"
SITES = ("agri",)


def institution_snapshot(inst: Institution, state_name: str | None) -> dict[str, Any] | None:
    if inst.trust != "verified" or inst.status != "active":
        return None
    return {
        "doc_id": f"institution:{inst.slug}",
        "name": inst.name_en,
        "slug": inst.slug,
        "kind": inst.kind,
        "state": state_name,
        "url": f"/colleges/{inst.slug}",
        "sites": list(SITES),
    }


async def publish_institutions(rows: list[tuple[Institution, str | None]]) -> int:
    for inst, state_name in rows:
        await publish(
            STREAM,
            "institution.updated",
            {
                "doc_id": f"institution:{inst.slug}",
                "snapshot": institution_snapshot(inst, state_name),
            },
        )
    return len(rows)
```

- [ ] **Step 4: Publish after commit, never before**

In `scripts/import_education_seed.py`, after `await session.commit()`, select every institution with its state name and call `publish_institutions`. Publishing before the commit would announce rows that a rollback then removes.

- [ ] **Step 5: Open the indexer to the new stream and event type**

**Without this step the previous four steps publish into a void.** Two independent
gates in `modules/search` drop these events today, and both must be opened or
colleges never reach hub search — while every test above still passes, because
they only assert on snapshot shape.

`modules/search/worker.py` currently reads:

```python
STREAMS = ("directory",)
```

Change it to consume the education stream as well:

```python
# "education" joins here so college documents reach the index. The stream name
# is duplicated from modules/education/search_sync.py STREAM by hand: the module
# independence contract forbids importing it.
STREAMS = ("directory", "education")
```

`modules/search/indexing.py` short-circuits on the event type at line ~110
(`if event.type not in INDEXED_EVENT_TYPES: return`). Add the institution events:

```python
INDEXED_EVENT_TYPES = frozenset(
    {
        "business.created",
        "business.updated",
        "product.created",
        "product.updated",
        "institution.created",
        "institution.updated",
    }
)
```

Check `SEARCHABLE_ATTRIBUTES` in the same file. If it names attributes that an
institution snapshot does not carry, either add the institution fields (`name`,
`kind`, `state`) or confirm Meilisearch tolerates absent attributes on a document
before relying on it.

- [ ] **Step 6: Write the test that would have caught the void**

Append to `backend/core/tests/test_education_search_sync.py`:

```python
def test_the_indexer_actually_accepts_our_event_type() -> None:
    """Guards the gap this step was added to close.

    search_sync publishes `institution.updated` onto the `education` stream.
    Both are gated in modules/search: the worker reads a fixed STREAMS tuple and
    the indexer drops any event whose type is not in INDEXED_EVENT_TYPES. If
    either forgets institutions, publishing still succeeds and nothing is ever
    indexed -- silently.
    """
    from modules.search.indexing import INDEXED_EVENT_TYPES
    from modules.search.worker import STREAMS

    from modules.education.search_sync import STREAM

    assert "institution.updated" in INDEXED_EVENT_TYPES
    assert STREAM in STREAMS
```

Note this test imports two modules, which the import-linter independence
contract forbids **for application code**. Tests are not covered by that contract
(they are not under `modules/`), so this is legal — but confirm `lint-imports`
still passes in the next step rather than assuming it.

- [ ] **Step 7: Run the tests**

Run: `cd backend/core && python -m pytest tests/test_education_search_sync.py tests/test_education_seed_import.py -v`
Expected: all PASS.

- [ ] **Step 8: Lint, type-check, commit**

```bash
cd backend/core && ruff format . && ruff check --fix . && python -m mypy . && ./.venv/Scripts/lint-imports.exe
git add backend/core/modules/education/search_sync.py backend/core/tests/test_education_search_sync.py backend/core/scripts/import_education_seed.py
git commit -m "feat(education): publish institution snapshots for hub search

Only verified active institutions get a snapshot. A listed row is unverified by
definition, so it must never be findable in hub search; listed, closed and
merged rows publish a null snapshot, which the indexer treats as a delete
(ADR-0007) and so clears any stale document.

Published after commit, never before: publishing first would announce rows that
a rollback then removes.

SITES is duplicated from directory/search_sync.py by hand because the module
independence contract forbids importing it.

modules/search is edited too, and it had to be: the worker read a fixed
STREAMS tuple of (directory,) and the indexer dropped any event type outside
business.*/product.*. Publishing alone would have written college events onto a
stream nobody consumes, carrying a type the indexer discards -- and every test
would still have passed, because they assert on snapshot shape. A test now
pins both gates open."
```

---

### Task 5: Freshness reporter, module notes, acceptance rows

**Files:**
- Create: `backend/core/scripts/education_freshness.py`
- Modify: `backend/core/scripts/gen_module_claude.py` (add the `education` entry, then run it)
- Generated: `backend/core/modules/education/CLAUDE.md` (**never hand-written** — see Step 3)
- Modify: `docs/qa/agri-acceptance-checklist.md`

**Interfaces:**
- Consumes: `Institution`, `StudentResource`, `Guide`.
- Produces: `async def _main(argv: list[str]) -> int` — prints rows whose `last_verified_at` is older than `--days` (default 180), oldest first, then a total. Always exits 0: this reports, it does not gate.

- [ ] **Step 1: Write the script**

Create `backend/core/scripts/education_freshness.py`:

```python
"""Report education rows whose verification stamp has aged.

Dev-only by design (spec section 9): no worker, no UI state, no alerting. It
prints what needs rechecking before launch and exits 0 either way -- this
reports, it does not gate. A stale stamp is not a broken row; it is a row whose
source should be opened again.
"""

from __future__ import annotations

import argparse
import asyncio
import sys
from datetime import UTC, datetime, timedelta
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from sqlalchemy import select  # noqa: E402

from modules.education.models import Guide, Institution, StudentResource  # noqa: E402
from shared.db import get_sessionmaker  # noqa: E402

_TABLES = (
    ("institutions", Institution, "slug"),
    ("student_resources", StudentResource, "slug"),
    ("guides", Guide, "slug"),
)


async def _main(argv: list[str]) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--days", type=int, default=180)
    args = parser.parse_args(argv)
    cutoff = datetime.now(UTC).date() - timedelta(days=args.days)

    total = 0
    async with get_sessionmaker()() as session:
        for label, model, key in _TABLES:
            rows = (
                await session.scalars(
                    select(model)
                    .where(model.last_verified_at < cutoff)
                    .order_by(model.last_verified_at)
                )
            ).all()
            for row in rows:
                print(  # noqa: T201
                    f"  {label:<20} {getattr(row, key):<44} {row.last_verified_at}"
                )
            total += len(rows)
    print(f"{total} row(s) stamped before {cutoff}")  # noqa: T201
    return 0


def main() -> int:
    return asyncio.run(_main(sys.argv[1:]))


if __name__ == "__main__":
    raise SystemExit(main())
```

- [ ] **Step 2: Prove it reads the column**

```bash
cd backend/core
python -m scripts.education_freshness --days 1
python -m scripts.education_freshness --days 3650
```
Expected: `--days 1` lists every row (stamps are 2026-08-17 or earlier); `--days 3650` lists none. That difference is the assertion.

- [ ] **Step 3: Add education to the module-notes generator, then run it**

`modules/*/CLAUDE.md` is **generated**, not written. `scripts/gen_module_claude.py`
says so on line 3 — "Edit MODULES / TEMPLATE here and rerun; never hand-edit the
generated files." A hand-written `modules/education/CLAUDE.md` would survive review
and then be silently overwritten the next time anyone regenerates, taking every
education-specific warning with it.

Add an entry to the `MODULES` dict in `backend/core/scripts/gen_module_claude.py`,
keeping the key order alphabetical-ish/consistent with its neighbours:

```python
    "education": {
        "purpose": "Agri-colleges vertical: institutions, programmes, exams,
"
        "scholarships and counselling guides. Read-only - every row arrives
"
        "from a reviewed seed commit, never from a user.",
        "spec": "docs/superpowers/specs/2026-08-16-agri-colleges-design.md.",
        "pii_note": "holds no personal data - institutions are public records",
        "extra_never": "- Never write from the app: app_rt holds SELECT only on
"
        "  education.* (spec section 4). Enabling CRUD is an explicit grant
"
        "  change, reviewed on its own.
"
        "- Never duplicate validation here. scripts/education_seed_contract.py
"
        "  is the single source of truth and seed_import.py imports it verbatim,
"
        "  so the importer cannot accept a bundle the CI gate rejects.
"
        "- Never render a fee, a seat count or an admission route for a row
"
        "  whose trust is 'listed'. Branch on trust, never on whether a field
"
        "  happens to be populated.
"
        "- Never let SITES in search_sync.py drift from directory's copy - it is
"
        "  hand-mirrored because the independence contract forbids the import.",
    },
```

Then run it and commit **both** files:

Run: `cd backend/core && python scripts/gen_module_claude.py`
Expected: `wrote .../modules/education/CLAUDE.md` among the other module lines. The
other modules' files must come back byte-identical — `git status` should show only
`modules/education/CLAUDE.md` as new. If any other module's file shows as modified,
someone hand-edited it earlier; stop and report rather than committing the reversion.

- [ ] **Step 4: Add acceptance rows**

Add rows to `docs/qa/agri-acceptance-checklist.md` for: migration applies and downgrades cleanly; `app_rt` cannot write; import is idempotent; dry run writes nothing; a `listed` institution produces no search document.

- [ ] **Step 5: Lint and commit**

```bash
cd backend/core && ruff format . && ruff check --fix . && python -m mypy .
git add backend/core/scripts/education_freshness.py backend/core/scripts/gen_module_claude.py \n  backend/core/modules/education/CLAUDE.md docs/qa/agri-acceptance-checklist.md
git commit -m "feat(education): freshness reporter, module notes, acceptance rows"
```

---

## Plan 1 exit criteria

- [ ] `python -m alembic upgrade head` applies `0049`; `downgrade -1` then `upgrade head` both succeed.
- [ ] `python -m pytest tests/test_education_models.py tests/test_education_seed_import.py tests/test_education_search_sync.py -v` passes.
- [ ] `python -m scripts.import_education_seed --dry-run` reports ~772 institutions and writes nothing.
- [ ] `python -m scripts.import_education_seed` imports; a rerun reports 0 created and the same count updated.
- [ ] `ruff check .`, `ruff format --check .`, `python -m mypy .`, `lint-imports` all clean.
- [ ] `app_rt` cannot INSERT into any `education` table.
- [ ] **No file under `apps/` was touched.**

## What is NOT in this plan

Plan 2 (public API, spec §5) and Plan 3 (surfaces, search indexing, registry flip, and the 36-tile assertion move) are separate documents. Plan 3 is the only one that competes with A-U4 for the registry and the e2e specs, and per the owner's decision the build waits for A-U4 to merge.

## Open item carried from the data track

Depth is 32%: 246 of 772 institutions carry any course, seat or fee row, and 439 institutions are `trust=listed`, which per spec §6 render no numbers and are `noindex`. The engine does not care, but Plan 3's surfaces will look thin outside Tamil Nadu, Maharashtra, Kerala, Punjab and Rajasthan. Worth raising with the owner before D58 QA rather than at it.
