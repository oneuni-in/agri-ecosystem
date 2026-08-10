# M4 — Automatic Pincode Tiers Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Classify every Indian pincode T1–T5 (metro → extreme rural) fully automatically — v1 by census population percentiles, with a nightly verified-user re-rank hook that can promote (never demote) — exposed to delivery/rate-card through a single `get_tier(pincode)` accessor, plus an append-only change history and an Ops Console distribution histogram.

**Architecture:** Everything tier-shaped lives in `backend/core/shared/geo/` (engine-level, all verticals share it): two new tables in the `geo` schema, a classifier in `shared/geo/tiers.py`, and the accessor in `shared/geo/service.py`. The verified-user count query lives in `modules/identity/user_counts.py` (identity owns those tables); the nightly job is a one-shot CLI script (`scripts/geo_tier_nightly.py`, the `scripts/coins_integrity.py` "nightly" shape — scripts may import both `modules.*` and `shared.*`, which sidesteps the import-linter rule that `shared` must never import `modules`). Population data is a committed CSV snapshot curated from licensed census/open data (D03 style: the CSV + SOURCES.md are the artifact).

**Tech Stack:** FastAPI + SQLAlchemy async + Alembic (backend/core), pytest (dockerised test Postgres), Next.js 15 / React 19 / Tailwind 3 tokens (apps/web-admin, port 3004).

## Global Constraints

- Branch `feat/m4-pincode-tiers` from `dev`. NEVER commit to dev/main. Conventional commits. PR targets dev only. Final commit message theme: `feat(m4): automatic pincode tiers`.
- Toolchain: backend host Python 3.12, no uv, no gh CLI (open the PR via the credential-fill API, D18 pattern). Node 24 / pnpm 11 / Tailwind 3.
- Backend tests need the dockerised services (Postgres on port 45432 per D13, Redis); tests DROP/CREATE the single shared `agri_test` DB — **never run two pytest processes in parallel** (D19 trap).
- `mypy --strict`, `ruff check`, `ruff format` (run per task, not at the end — D16 lesson), `lint-imports`, line length 100. Ruff `T20` bans `print` (scripts use `# noqa: T201`).
- Import-linter contracts: modules must not import each other; **`shared` must not import `modules`**. `scripts/` are exempt (precedent: `scripts/coins_integrity.py` imports `modules.coins`).
- Migrations: hand-written, next id **0032**, `down_revision="0031"`, helpers from `shared/migrations.py`, filled `# -- THREAT/NOTES:` block (a lint test fails on missing block or any `TODO` left in the file), must downgrade cleanly — CI `migrate_check` runs upgrade → downgrade base → upgrade. `op.f()` on BOTH create and drop of named constraints (M3 trap). NEVER run `scripts/migrate_check.py` against the dev DB — it wipes it (D05); verify up/down/up on a scratch DB if needed.
- `SecureRouter` refuses routes without a return annotation; endpoints are private + rate-limited by default; M4 adds **no** public routes (`public_routes.txt` untouched).
- Cursor pagination only; OFFSET is test-gated (M4's ops endpoints return aggregates/single rows, no lists — nothing to paginate).
- Frontend: tokens only, no raw hex (`pnpm check:hex`); web-admin gates: `pnpm -w typecheck`, `lint`, `check:hex`.
- Naming: "tier" already means billing subscription tier (`modules/billing/tiers.py`) — every M4 name says `pincode_tier`/`PincodeTier` except the spec-mandated accessor `get_tier` (lives in `shared.geo.service`, unambiguous by module).
- Non-negotiables (spec): NN1 641001 → T1/T2 and a village pincode → T4/T5 with zero manual steps · NN2 unknown pincode → safe default T4 + log, delivery unaffected · NN3 user-count promotion fires when threshold crossed (synthetic users) · NN4 tier change writes a history row.

## Design decisions locked in

1. **No FK from `pincode_tiers.pincode` to `geo.pincodes`.** Pan-India tier rows must exist while `geo.pincodes` stays TN-only (`tests/test_geo.py::test_all_centroids_fall_inside_tamil_nadu` hard-fails on any non-TN centroid — that test is untouched). "Stage-B dormancy" = pan-India rows live ONLY in `geo.pincode_tiers`; nothing serves them because delivery/geo lookups still key off `geo.pincodes`.
2. **`computed_at` is nullable**: NULL = row loaded from the population CSV but never classified. `tier` has server_default `'4'` so an unclassified row already equals the safe default the accessor returns for a missing row.
3. **Percentile config, not code:** `pincode_tier_percentiles: str = "99,90,60,25"` (T1 ≥ p99, T2 ≥ p90, T3 ≥ p60, T4 ≥ p25, T5 below), parsed and validated at use (the `dunning_retry_hours` pattern). Thresholds are computed over the FULL stored distribution (TN + pan-India) at run time.
4. **User re-rank = one-tier promotion, recomputed from scratch nightly.** When `user_count >= pincode_tier_user_threshold` (verified users only): `method` flips one-way to `'population+users'` and the target tier becomes `max(1, population_tier - pincode_tier_user_promotion_step)`. Recomputing from the population tier each run (not incrementing the stored tier) makes the job idempotent — no runaway promotion.
5. **Hysteresis (threat: tier flapping):** `pincode_tier_promote_only: bool = True` — an automatic change may never increase the tier number (demote); plus `tier_changed_at` column + `pincode_tier_min_change_interval_hours: int = 24` — at most one automatic change per interval. Initial classification bypasses both.
6. **History = the audit trail for automatic changes** (`geo.pincode_tier_history`, append-only by grant + trigger, `created_at` only — 0013 rule: `updated_at` on an immutable table would be a lie). `shared.audit.audit()` is used only by the admin override route (an admin action). No event-bus events — nothing consumes them yet.
7. **Admin override exists but nothing requires it:** `POST /admin/ops/pincode-tiers/{pincode}` (STAFF/SUPER_ADMIN), writes history `reason='admin_override'` + audit row. Documented v1 limitation: an override that demotes below the computed tier is re-promoted by the next nightly run (promote-only lets tiers only improve); durable overrides are v2.
8. **"Tier available to delivery"** = `ads.delivery_decisions` gains a nullable `tier SMALLINT`, filled at serve time via `get_tier()` (never a direct table read from ads). M5 rate card reads the same accessor. Missing row → `DEFAULT_TIER = 4`, logged, serve unaffected (NN2).
9. **Population snapshot provenance (threat: bad source data mis-pricing ads):** universe of pincodes from GeoNames `IN.zip` (CC BY 4.0 — already a licensed D03 source); TN populations from Census of India 2011 Primary Census Abstract town/village level (data.gov.in, NDSAP open license), name-joined within district; pan-India from district-level PCA apportioned equally per pincode (grade-marked, dormant anyway). Approximation documented in the migration docstring AND `data/geo/SOURCES.md`. The classifier refuses to write when the distribution fails sanity checks (`TierSanityError` → job exits non-zero).
10. **Signup-farming defense:** `user_count` counts only `User.phone_verified_at IS NOT NULL` + `User.status == 'active'` (+ soft-delete filtered) profiles with a server-derived pincode (profile pincode is already validated against `geo.pincodes` and unwritable as free text), and the threshold is config.

---

### Task 0: Branch + worktree + baseline

- [ ] **Step 1:** Use superpowers:using-git-worktrees to create an isolated worktree for branch `feat/m4-pincode-tiers` cut from `dev` (repo already has `.worktrees/`). All subsequent tasks run inside it.
- [ ] **Step 2:** Baseline check (docker test services must be up): `cd backend/core && python -m pytest tests/test_geo.py tests/test_ads_serve.py -q` — expect PASS before touching anything.

---

### Task 1: Population data snapshot — `data/geo/pincode_population.csv`

The riskiest task: curate a licensed per-pincode population CSV. Work in the session scratchpad (D03 style — curation scripts are one-off; the committed artifacts are the CSV, SOURCES.md, and the file-based tests).

**Files:**
- Create: `backend/core/data/geo/pincode_population.csv` (columns: `pincode,population,grade`)
- Modify: `backend/core/data/geo/SOURCES.md` (new "Pincode population (M4)" section)
- Test: `backend/core/tests/test_geo_tier_data.py`

**Interfaces:**
- Produces: the committed CSV consumed by Task 3's loader. `grade ∈ {'town','village','district_apportioned'}`. Every pincode in `data/geo/pincodes.csv` MUST appear.

- [ ] **Step 1: Fetch sources into the scratchpad** (checkpoint every download; data.gov.in sample key caps at 10 rows/request with 60s+ backoff and case-sensitive filters — D03):
  - GeoNames `https://download.geonames.org/export/zip/IN.zip` (CC BY 4.0) → the pan-India pincode universe (~19k pincodes) with place names + admin1/admin2.
  - Census 2011 PCA town/village level for Tamil Nadu: data.gov.in catalog "Village/Town-wise Primary Census Abstract, 2011 - TAMIL NADU" (`https://www.data.gov.in/catalog/villagetown-wise-primary-census-abstract-2011-tamil-nadu`) or the Census NADA per-district PCA-TV downloads (`https://censusindia.gov.in/nada/index.php/catalog/6795` and siblings — direct downloads, no API key). Record every resource id/URL used.
  - District-level PCA for pan-India: data.gov.in "Primary Census Abstract 2011 - India and States" (bulk downloadable) or NADA catalog 6191.
- [ ] **Step 2: Build the CSV** with a scratchpad script implementing, per pincode:
  - TN (every pincode in `data/geo/pincodes.csv`): normalize census town/village names and GeoNames place names (lowercase, strip punctuation/`(ct)` suffixes); join within the same district; a census unit matching a pincode's place names contributes its population to that pincode — a unit matching N pincodes splits its population evenly across them (no double counting). Matched-town rows get `grade=town`, matched-village `grade=village`. Census units that match nothing: apportion their population equally across the district's pincodes and mark those pincodes' residual additions by leaving grade at the best matched level; a pincode with NO matches at all gets `district_apportioned`.
  - Pan-India (GeoNames pincodes not in TN): district PCA population ÷ number of that district's pincodes, `grade=district_apportioned`.
- [ ] **Step 3: Verify discrimination before committing** (this is the NN1 gate — do NOT commit a snapshot that fails it):
  - `641001` present with population in the top 10% of the full combined distribution.
  - The lowest-population TN pincode is in the bottom 40%.
  - If pan-India apportioned rows swamp TN town-matched rows (equal-split can produce inflated flat values), weight the apportionment by GeoNames post-office counts per pincode and re-verify. If the data still cannot discriminate, STOP and surface to the owner — do not fabricate populations.
- [ ] **Step 4: Write `SOURCES.md` section**: snapshot date, exact resource ids/URLs, licences (NDSAP, CC BY 4.0), the join/approximation method, known limitations (2011 undercount — irrelevant to percentile ranks if roughly uniform; fuzzy name joins; even splits across multi-office pincodes), refresh path.
- [ ] **Step 5: Write the file-based tests** in `backend/core/tests/test_geo_tier_data.py`:

```python
"""M4 population snapshot integrity - pure file checks, no DB."""

import csv
from pathlib import Path

DATA_DIR = Path(__file__).resolve().parents[1] / "data" / "geo"


def _population_rows() -> dict[str, int]:
    with (DATA_DIR / "pincode_population.csv").open(encoding="utf-8") as fh:
        return {row["pincode"]: int(row["population"]) for row in csv.DictReader(fh)}


def test_every_tn_pincode_has_a_population_row() -> None:
    with (DATA_DIR / "pincodes.csv").open(encoding="utf-8") as fh:
        tn = {row["pincode"] for row in csv.DictReader(fh)}
    missing = tn - _population_rows().keys()
    assert not missing, f"TN pincodes without population: {sorted(missing)[:10]}"


def test_populations_are_sane() -> None:
    pops = _population_rows()
    assert len(pops) > 15_000  # pan-India universe loaded, not just TN
    assert all(p >= 0 for p in pops.values())
    assert pops["641001"] > 0


def test_grades_are_valid() -> None:
    with (DATA_DIR / "pincode_population.csv").open(encoding="utf-8") as fh:
        grades = {row["grade"] for row in csv.DictReader(fh)}
    assert grades <= {"town", "village", "district_apportioned"}
```

- [ ] **Step 6:** Run: `python -m pytest tests/test_geo_tier_data.py -q` — expect PASS (the tests are written against the already-built CSV; if any fail, the snapshot is wrong — fix the data, not the test).
- [ ] **Step 7:** Commit: `git add backend/core/data/geo/pincode_population.csv backend/core/data/geo/SOURCES.md backend/core/tests/test_geo_tier_data.py && git commit -m "feat(m4): census population snapshot per pincode"`

---

### Task 2: Settings + migration 0032 + ORM models

**Files:**
- Modify: `backend/core/settings.py` (new M4 block, after the M3 ads block)
- Modify: `backend/core/shared/geo/models.py` (add `PincodeTier`, `PincodeTierHistory`)
- Create: `backend/core/alembic/versions/0032_geo_pincode_tiers.py`
- Test: `backend/core/tests/test_geo_tier_migration.py`

**Interfaces:**
- Produces: `PincodeTier` (`pincode: str`, `population: int`, `population_grade: str`, `tier: int`, `user_count: int`, `computed_at: datetime | None`, `tier_changed_at: datetime | None`, `method: str`), `PincodeTierHistory` (`pincode`, `old_tier: int | None`, `new_tier: int`, `old_method: str | None`, `new_method: str`, `reason: str`, `created_at`), settings fields `pincode_tier_percentiles: str = "99,90,60,25"`, `pincode_tier_user_threshold: int = 100`, `pincode_tier_user_promotion_step: int = 1`, `pincode_tier_promote_only: bool = True`, `pincode_tier_min_change_interval_hours: int = 24`, `pincode_tier_min_rows: int = 100`, `geo_tier_job_enabled: bool = True`; `ads.delivery_decisions.tier SMALLINT NULL`.

- [ ] **Step 1: Write failing schema tests** in `backend/core/tests/test_geo_tier_migration.py`, mirroring `tests/test_ads_migration.py` style (raw SQL over `db_session`, `admin_database_url` fixture where owner creds are needed):

```python
"""M4 schema: geo.pincode_tiers + append-only history + ads tier column."""

import pytest
from sqlalchemy import text
from sqlalchemy.exc import DBAPIError
from sqlalchemy.ext.asyncio import AsyncSession


async def _columns(db_session: AsyncSession, schema: str, table: str) -> set[str]:
    rows = await db_session.execute(
        text(
            "SELECT column_name FROM information_schema.columns "
            "WHERE table_schema=:s AND table_name=:t"
        ),
        {"s": schema, "t": table},
    )
    return {r[0] for r in rows}


async def test_pincode_tiers_columns(db_session: AsyncSession) -> None:
    cols = await _columns(db_session, "geo", "pincode_tiers")
    assert {
        "pincode", "population", "population_grade", "tier",
        "user_count", "computed_at", "tier_changed_at", "method",
    } <= cols


async def test_pincode_tier_history_columns(db_session: AsyncSession) -> None:
    cols = await _columns(db_session, "geo", "pincode_tier_history")
    assert {"pincode", "old_tier", "new_tier", "old_method", "new_method", "reason"} <= cols
    assert "updated_at" not in cols  # immutable table: created_at only


async def test_tier_bounds_enforced(db_session: AsyncSession) -> None:
    with pytest.raises(DBAPIError):
        await db_session.execute(
            text(
                "INSERT INTO geo.pincode_tiers (id, created_at, updated_at, pincode,"
                " population, population_grade, tier, user_count, method)"
                " VALUES (gen_random_uuid(), now(), now(), '999999', 10, 'town', 6, 0,"
                " 'population')"
            )
        )


async def test_history_is_append_only(db_session: AsyncSession) -> None:
    await db_session.execute(
        text(
            "INSERT INTO geo.pincode_tier_history (id, created_at, pincode, old_tier,"
            " new_tier, old_method, new_method, reason)"
            " VALUES (gen_random_uuid(), now(), '641001', NULL, 2, NULL, 'population',"
            " 'initial')"
        )
    )
    with pytest.raises(DBAPIError):
        await db_session.execute(text("UPDATE geo.pincode_tier_history SET new_tier = 1"))


async def test_delivery_decisions_gained_tier(db_session: AsyncSession) -> None:
    cols = await _columns(db_session, "ads", "delivery_decisions")
    assert "tier" in cols
```

- [ ] **Step 2:** Run: `python -m pytest tests/test_geo_tier_migration.py -q` — expect FAIL (tables/columns missing).
- [ ] **Step 3: Settings block** — append to `backend/core/settings.py` after the M3 ads fields, following the house comment style:

```python
    # --- M4: automatic pincode tiers (geo) -------------------------------
    # Percentile cut points over the pincode population distribution,
    # descending: T1 >= p99, T2 >= p90, T3 >= p60, T4 >= p25, T5 below.
    # Thresholds live in config, not code (spec M4.B).
    pincode_tier_percentiles: str = "99,90,60,25"
    # Verified users (phone-verified + active) needed before a pincode's
    # method flips to population+users. Defends signup farming (threat M4).
    pincode_tier_user_threshold: int = 100
    # Tiers a threshold-crossing pincode is promoted by (bounded at T1).
    pincode_tier_user_promotion_step: int = 1
    # Hysteresis (threat: tier flapping): never auto-demote in v1, and at
    # most one automatic tier change per pincode per interval.
    pincode_tier_promote_only: bool = True
    pincode_tier_min_change_interval_hours: int = 24
    # Sanity floor: refuse to classify a distribution smaller than this
    # (threat: bad/partial source data). Tests lower it via env.
    pincode_tier_min_rows: int = 100
    # Kill switch for scripts/geo_tier_nightly.py.
    geo_tier_job_enabled: bool = True
```

- [ ] **Step 4: ORM models** — append to `backend/core/shared/geo/models.py` (reuse the file's existing imports; add `BigInteger`, `SmallInteger`, `Integer`, `TIMESTAMP`, `func` as needed):

```python
class PincodeTier(UUIDv7PKMixin, TimestampMixin, Base):
    """Automatic T1-T5 classification per pincode (M4).

    No FK to geo.pincodes: pan-India rows exist here while geo.pincodes
    stays TN-only (Stage-B dormancy). computed_at NULL = loaded from the
    population snapshot but never classified; tier defaults to 4, the same
    safe default get_tier() returns for a missing row.
    """

    __tablename__ = "pincode_tiers"
    __table_args__ = {"schema": "geo"}

    pincode: Mapped[str] = mapped_column(Text, unique=True, nullable=False)
    population: Mapped[int] = mapped_column(BigInteger, nullable=False)
    population_grade: Mapped[str] = mapped_column(Text, nullable=False)
    tier: Mapped[int] = mapped_column(SmallInteger, nullable=False, server_default="4")
    user_count: Mapped[int] = mapped_column(Integer, nullable=False, server_default="0")
    computed_at: Mapped[datetime | None] = mapped_column(
        TIMESTAMP(timezone=True), nullable=True
    )
    tier_changed_at: Mapped[datetime | None] = mapped_column(
        TIMESTAMP(timezone=True), nullable=True
    )
    method: Mapped[str] = mapped_column(Text, nullable=False, server_default="population")


class PincodeTierHistory(UUIDv7PKMixin, Base):
    """Append-only audit of tier changes (M4). created_at only - an
    updated_at column on an immutable table would be a lie (0013 rule)."""

    __tablename__ = "pincode_tier_history"
    __table_args__ = {"schema": "geo"}

    created_at: Mapped[datetime] = mapped_column(
        TIMESTAMP(timezone=True), server_default=func.clock_timestamp(), nullable=False
    )
    pincode: Mapped[str] = mapped_column(Text, nullable=False, index=True)
    old_tier: Mapped[int | None] = mapped_column(SmallInteger, nullable=True)
    new_tier: Mapped[int] = mapped_column(SmallInteger, nullable=False)
    old_method: Mapped[str | None] = mapped_column(Text, nullable=True)
    new_method: Mapped[str] = mapped_column(Text, nullable=False)
    reason: Mapped[str] = mapped_column(Text, nullable=False)
```

- [ ] **Step 5: Migration** `backend/core/alembic/versions/0032_geo_pincode_tiers.py` (`revision="0032"`, `down_revision="0031"`); follow 0004 (geo tables) + 0031 (op.f + append-only idiom):

```python
"""M4: automatic pincode tiers - geo.pincode_tiers + append-only history.

Population provenance & approximation (spec M4.A: document honestly):
- Pincode universe: GeoNames IN.zip (CC BY 4.0), the D03 source.
- TN populations: Census of India 2011 Primary Census Abstract town/village
  level (data.gov.in / Census NADA, NDSAP open licence), matched to pincodes
  by normalized place-name join within district; census units matching N
  pincodes split their population evenly (no double count); unmatched
  village population apportioned across the district's pincodes.
- Pan-India: district-level PCA apportioned per pincode (dormant, Stage-B).
- Census 2011 undercounts 2026 populations; tiers depend only on the
  DISTRIBUTION (percentiles), so a roughly uniform undercount does not move
  tier boundaries. Per-row quality recorded in population_grade. Full
  provenance: backend/core/data/geo/SOURCES.md.

# -- THREAT/NOTES:
# downgrade data loss: drops geo.pincode_tiers + geo.pincode_tier_history
#   (recomputable: scripts/load_pincode_tiers.py over the committed CSV)
#   and ads.delivery_decisions.tier (sampled analytics column).
# locks: CREATE TABLE + nullable ADD COLUMN - brief, no rewrites.
# rollout: run scripts/load_pincode_tiers.py after upgrade; until then
#   get_tier() returns the default T4 and delivery is unaffected.
"""

import sqlalchemy as sa
from alembic import op

from shared.migrations import pk_column, timestamp_columns

revision: str = "0032"
down_revision: str | None = "0031"


def upgrade() -> None:
    op.create_table(
        "pincode_tiers",
        pk_column(),
        *timestamp_columns(),
        sa.Column("pincode", sa.Text, nullable=False, unique=True),
        sa.Column("population", sa.BigInteger, nullable=False),
        sa.Column("population_grade", sa.Text, nullable=False),
        sa.Column("tier", sa.SmallInteger, nullable=False, server_default="4"),
        sa.Column("user_count", sa.Integer, nullable=False, server_default="0"),
        sa.Column("computed_at", sa.TIMESTAMP(timezone=True), nullable=True),
        sa.Column("tier_changed_at", sa.TIMESTAMP(timezone=True), nullable=True),
        sa.Column("method", sa.Text, nullable=False, server_default="population"),
        schema="geo",
    )
    # op.f(): final names - without it the metadata naming convention
    # re-wraps them and downgrade's drop cannot find them (M3 trap).
    op.create_check_constraint(
        op.f("ck_geo_pincode_tiers_tier_range"),
        "pincode_tiers", "tier BETWEEN 1 AND 5", schema="geo",
    )
    op.create_check_constraint(
        op.f("ck_geo_pincode_tiers_population"),
        "pincode_tiers", "population >= 0", schema="geo",
    )
    op.create_check_constraint(
        op.f("ck_geo_pincode_tiers_user_count"),
        "pincode_tiers", "user_count >= 0", schema="geo",
    )
    op.create_check_constraint(
        op.f("ck_geo_pincode_tiers_method"),
        "pincode_tiers",
        "method IN ('population', 'population+users')", schema="geo",
    )
    op.create_check_constraint(
        op.f("ck_geo_pincode_tiers_grade"),
        "pincode_tiers",
        "population_grade IN ('town', 'village', 'district_apportioned')", schema="geo",
    )

    op.create_table(
        "pincode_tier_history",
        pk_column(),
        # append-only: created_at only (0013 rule)
        sa.Column(
            "created_at", sa.TIMESTAMP(timezone=True),
            server_default=sa.text("clock_timestamp()"), nullable=False,
        ),
        sa.Column("pincode", sa.Text, nullable=False, index=True),
        sa.Column("old_tier", sa.SmallInteger, nullable=True),
        sa.Column("new_tier", sa.SmallInteger, nullable=False),
        sa.Column("old_method", sa.Text, nullable=True),
        sa.Column("new_method", sa.Text, nullable=False),
        sa.Column("reason", sa.Text, nullable=False),
        schema="geo",
    )
    op.create_check_constraint(
        op.f("ck_geo_pincode_tier_history_reason"),
        "pincode_tier_history",
        "reason IN ('initial', 'population_recompute', 'user_promotion',"
        " 'admin_override')",
        schema="geo",
    )
    op.create_check_constraint(
        op.f("ck_geo_pincode_tier_history_new_tier"),
        "pincode_tier_history", "new_tier BETWEEN 1 AND 5", schema="geo",
    )
    op.execute(
        """
        CREATE OR REPLACE FUNCTION geo.forbid_tier_history_mutation()
        RETURNS trigger AS $$
        BEGIN
          RAISE EXCEPTION 'geo.pincode_tier_history is append-only';
        END;
        $$ LANGUAGE plpgsql
        """
    )
    op.execute(
        "CREATE TRIGGER forbid_mutation BEFORE UPDATE OR DELETE"
        " ON geo.pincode_tier_history FOR EACH ROW"
        " EXECUTE FUNCTION geo.forbid_tier_history_mutation()"
    )
    # geo default privileges already grant app_rt DML (0013); explicit for
    # reviewability + revoke mutation on the append-only table (0031 idiom).
    op.execute("GRANT SELECT, INSERT, UPDATE, DELETE ON geo.pincode_tiers TO app_rt")
    op.execute("GRANT SELECT, INSERT ON geo.pincode_tier_history TO app_rt")
    op.execute("REVOKE UPDATE, DELETE ON geo.pincode_tier_history FROM app_rt")

    # M4.D: tier available to delivery analytics (filled via get_tier()).
    op.add_column(
        "delivery_decisions",
        sa.Column("tier", sa.SmallInteger(), nullable=True),
        schema="ads",
    )


def downgrade() -> None:
    op.drop_column("delivery_decisions", "tier", schema="ads")
    op.execute("DROP TRIGGER IF EXISTS forbid_mutation ON geo.pincode_tier_history")
    op.execute("DROP FUNCTION IF EXISTS geo.forbid_tier_history_mutation()")
    op.drop_table("pincode_tier_history", schema="geo")
    op.drop_table("pincode_tiers", schema="geo")
```

(Constraints created inside `create_table` via `sa.Column(...)`/table args don't need explicit drops — dropping the tables removes them.)
- [ ] **Step 6:** Run: `python -m pytest tests/test_geo_tier_migration.py tests/test_geo.py -q` — expect PASS (conftest re-runs `alembic upgrade head` on the recreated test DB).
- [ ] **Step 7: Settings defaults test** — append to `tests/test_geo_tier_migration.py` (precedent `test_billing_models.py::test_dunning_settings_defaults`):

```python
def test_pincode_tier_settings_defaults() -> None:
    from settings import get_settings

    s = get_settings()
    assert s.pincode_tier_percentiles == "99,90,60,25"
    assert s.pincode_tier_user_threshold == 100
    assert s.pincode_tier_promote_only is True
    assert s.geo_tier_job_enabled is True
```

- [ ] **Step 8:** `ruff format . && ruff check . && mypy .` then run the file again — PASS.
- [ ] **Step 9:** Commit: `git commit -am "feat(m4): geo.pincode_tiers schema + history + settings"`

---

### Task 3: Population loader

**Files:**
- Modify: `backend/core/shared/geo/loader.py` (add `load_pincode_population`)
- Test: `backend/core/tests/test_geo_tiers.py` (new file, first tests)

**Interfaces:**
- Consumes: Task 1's CSV, Task 2's `PincodeTier`.
- Produces: `async def load_pincode_population(session: AsyncSession, data_dir: Path) -> int` (rows upserted; new rows keep tier default 4 / `computed_at NULL`). The CLI wrapper lands in Task 4, once `classify_tiers` exists to compose with.

- [ ] **Step 1: Write failing loader tests** in `backend/core/tests/test_geo_tiers.py`:

```python
"""M4 pincode tiers: loader, classifier, accessor, recount."""

from pathlib import Path

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from shared.geo.loader import load_pincode_population
from shared.geo.models import PincodeTier

DATA_DIR = Path(__file__).resolve().parents[1] / "data" / "geo"


async def test_load_pincode_population_upserts(db_session: AsyncSession, tmp_path: Path) -> None:
    csv_path = tmp_path / "pincode_population.csv"
    csv_path.write_text(
        "pincode,population,grade\n641001,150000,town\n606755,900,village\n",
        encoding="utf-8",
    )
    assert await load_pincode_population(db_session, tmp_path) == 2
    row = await db_session.scalar(select(PincodeTier).where(PincodeTier.pincode == "641001"))
    assert row is not None
    assert row.population == 150000
    assert row.tier == 4  # server default until classified
    assert row.computed_at is None

    # idempotent re-run with an updated population
    csv_path.write_text(
        "pincode,population,grade\n641001,160000,town\n606755,900,village\n",
        encoding="utf-8",
    )
    assert await load_pincode_population(db_session, tmp_path) == 2
    await db_session.refresh(row)
    assert row.population == 160000
```

- [ ] **Step 2:** Run: `python -m pytest tests/test_geo_tiers.py -q` — expect FAIL (ImportError).
- [ ] **Step 3: Implement** in `backend/core/shared/geo/loader.py` (same idiom as the existing `load_geo` upserts; batched for the 19k-row real file):

```python
async def load_pincode_population(session: AsyncSession, data_dir: Path) -> int:
    """Upsert data/geo/pincode_population.csv into geo.pincode_tiers.

    New rows keep tier server-default 4 and computed_at NULL until
    classify_tiers() runs; re-runs only refresh population + grade.
    """
    count = 0
    batch: list[dict[str, object]] = []

    async def _flush() -> None:
        nonlocal count
        if not batch:
            return
        stmt = insert(PincodeTier).values(batch)
        await session.execute(
            stmt.on_conflict_do_update(
                index_elements=[PincodeTier.pincode],
                set_={
                    "population": stmt.excluded.population,
                    "population_grade": stmt.excluded.population_grade,
                },
            )
        )
        count += len(batch)
        batch.clear()

    with (data_dir / "pincode_population.csv").open(encoding="utf-8") as fh:
        for row in csv.DictReader(fh):
            batch.append(
                {
                    "pincode": row["pincode"],
                    "population": int(row["population"]),
                    "population_grade": row["grade"],
                }
            )
            if len(batch) >= 1000:
                await _flush()
        await _flush()
    await session.flush()
    return count
```

- [ ] **Step 4:** Run: `python -m pytest tests/test_geo_tiers.py -q` — expect PASS.
- [ ] **Step 5:** `ruff format . && ruff check . && mypy .` — PASS.
- [ ] **Step 6:** Commit: `git commit -am "feat(m4): pincode population loader"`

---

### Task 4: Classifier — `shared/geo/tiers.py` (NN1, NN4)

**Files:**
- Create: `backend/core/shared/geo/tiers.py`
- Create: `backend/core/scripts/load_pincode_tiers.py`
- Test: `backend/core/tests/test_geo_tiers.py` (extend)

**Interfaces:**
- Consumes: `PincodeTier`, `PincodeTierHistory`, settings from Task 2; `load_pincode_population` from Task 3.
- Produces (Tasks 5–7 rely on these exact names):
  - `DEFAULT_TIER: int = 4`
  - `class TierSanityError(RuntimeError)`
  - `@dataclass(frozen=True, slots=True) class TierRunResult: total: int; changed: int; skipped_hysteresis: int`
  - `def tier_percentiles(settings: Settings) -> list[float]`
  - `async def classify_tiers(session: AsyncSession, *, now: datetime, user_counts: Mapping[str, int] | None = None) -> TierRunResult`

- [ ] **Step 1: Write failing tests** — append to `tests/test_geo_tiers.py`. The settings floor is lowered via env (autouse `_reset_state` clears the settings cache between tests):

```python
import pytest

from shared.geo.models import PincodeTierHistory
from shared.geo.tiers import TierSanityError, classify_tiers, tier_percentiles


@pytest.fixture
def small_distribution(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("PINCODE_TIER_MIN_ROWS", "3")
    from settings import get_settings

    get_settings.cache_clear()


async def _seed(db_session: AsyncSession, rows: dict[str, int]) -> None:
    for pincode, population in rows.items():
        db_session.add(
            PincodeTier(pincode=pincode, population=population, population_grade="town")
        )
    await db_session.flush()


async def test_classify_assigns_tiers_and_initial_history(
    db_session: AsyncSession, small_distribution: None
) -> None:
    # 20 rows spanning 5 orders of magnitude -> percentiles discriminate
    await _seed(db_session, {f"6{i:05d}": 100 * (10 ** (i % 5)) for i in range(20)})
    from datetime import UTC, datetime

    result = await classify_tiers(db_session, now=datetime.now(UTC))
    assert result.total == 20
    assert result.changed > 0
    history = (await db_session.scalars(select(PincodeTierHistory))).all()
    assert all(h.reason == "initial" for h in history)  # NN4: change -> history row
    tiers = {
        r.pincode: r.tier for r in (await db_session.scalars(select(PincodeTier))).all()
    }
    assert set(tiers.values()) <= {1, 2, 3, 4, 5}


async def test_classify_is_idempotent(
    db_session: AsyncSession, small_distribution: None
) -> None:
    await _seed(db_session, {f"6{i:05d}": 1000 * (i + 1) for i in range(10)})
    from datetime import UTC, datetime

    now = datetime.now(UTC)
    await classify_tiers(db_session, now=now)
    before = len((await db_session.scalars(select(PincodeTierHistory))).all())
    again = await classify_tiers(db_session, now=now)
    assert again.changed == 0  # re-run writes no new history
    after = len((await db_session.scalars(select(PincodeTierHistory))).all())
    assert after == before


async def test_flat_distribution_refused(
    db_session: AsyncSession, small_distribution: None
) -> None:
    await _seed(db_session, {f"6{i:05d}": 5000 for i in range(10)})
    from datetime import UTC, datetime

    with pytest.raises(TierSanityError):
        await classify_tiers(db_session, now=datetime.now(UTC))


async def test_too_few_rows_refused(db_session: AsyncSession) -> None:
    await _seed(db_session, {"641001": 100000})
    from datetime import UTC, datetime

    with pytest.raises(TierSanityError):  # default floor is 100
        await classify_tiers(db_session, now=datetime.now(UTC))


def test_percentile_config_validated(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("PINCODE_TIER_PERCENTILES", "25,60,90,99")  # not descending
    from settings import get_settings

    get_settings.cache_clear()
    with pytest.raises(ValueError):
        tier_percentiles(get_settings())


async def test_real_snapshot_nn1(db_session: AsyncSession) -> None:
    """NN1: with the committed census snapshot, 641001 lands T1/T2 and the
    lowest-population TN pincode lands T4/T5 - zero manual steps."""
    import csv as csv_mod
    from datetime import UTC, datetime

    from shared.geo.loader import load_pincode_population

    await load_pincode_population(db_session, DATA_DIR)
    await classify_tiers(db_session, now=datetime.now(UTC))

    with (DATA_DIR / "pincodes.csv").open(encoding="utf-8") as fh:
        tn = {row["pincode"] for row in csv_mod.DictReader(fh)}
    with (DATA_DIR / "pincode_population.csv").open(encoding="utf-8") as fh:
        pops = {
            row["pincode"]: int(row["population"])
            for row in csv_mod.DictReader(fh)
            if row["pincode"] in tn
        }
    village = min(pops, key=lambda p: pops[p])  # lowest-population TN pincode

    tiers = {
        r.pincode: r.tier
        for r in (
            await db_session.scalars(
                select(PincodeTier).where(PincodeTier.pincode.in_(["641001", village]))
            )
        ).all()
    }
    assert tiers["641001"] in (1, 2)
    assert tiers[village] in (4, 5)
```

- [ ] **Step 2:** Run: `python -m pytest tests/test_geo_tiers.py -q` — expect FAIL (no `shared.geo.tiers`).
- [ ] **Step 3: Implement** `backend/core/shared/geo/tiers.py`:

```python
"""Automatic pincode tier classification (M4).

Percentile thresholds over the stored population distribution; verified-user
counts can promote (never demote, v1). All writes to geo.pincode_tiers /
geo.pincode_tier_history happen here - other modules go through
shared.geo.service.get_tier() only.
"""

import math
from collections.abc import Mapping
from dataclasses import dataclass
from datetime import datetime, timedelta

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from settings import Settings, get_settings
from shared.geo.models import PincodeTier, PincodeTierHistory
from shared.telemetry import get_logger

logger = get_logger(__name__)

DEFAULT_TIER = 4


class TierSanityError(RuntimeError):
    """Population distribution failed sanity checks; nothing was written."""


@dataclass(frozen=True, slots=True)
class TierRunResult:
    total: int
    changed: int
    skipped_hysteresis: int


def tier_percentiles(settings: Settings) -> list[float]:
    parts = [float(p) for p in settings.pincode_tier_percentiles.split(",") if p.strip()]
    if len(parts) != 4 or parts != sorted(parts, reverse=True) or not all(
        0 < p < 100 for p in parts
    ):
        raise ValueError(
            "pincode_tier_percentiles must be 4 descending percentiles in (0,100),"
            " e.g. '99,90,60,25'"
        )
    return parts


def _percentile(ordered: list[int], pct: float) -> float:
    # nearest-rank over the ascending list; len > 0 guaranteed by caller
    rank = max(0, math.ceil(len(ordered) * pct / 100.0) - 1)
    return float(ordered[rank])


def _tier_for(population: int, thresholds: list[float]) -> int:
    for tier, threshold in enumerate(thresholds, start=1):
        if population >= threshold:
            return tier
    return 5


async def classify_tiers(
    session: AsyncSession,
    *,
    now: datetime,
    user_counts: Mapping[str, int] | None = None,
) -> TierRunResult:
    """Idempotent, re-runnable classification pass (spec M4.B + M4.C).

    - population percentiles -> tier; user_counts (verified users per
      pincode) can promote by pincode_tier_user_promotion_step once
      user_count >= pincode_tier_user_threshold (method flips one-way).
    - hysteresis: promote-only (config) + min interval between automatic
      changes; initial classification bypasses both.
    - refuses to write when the distribution cannot discriminate
      (TierSanityError) - threat: bad source data mis-pricing ads.
    """
    settings = get_settings()
    percentiles = tier_percentiles(settings)
    rows = (await session.scalars(select(PincodeTier))).all()

    if len(rows) < settings.pincode_tier_min_rows:
        raise TierSanityError(
            f"{len(rows)} rows < pincode_tier_min_rows={settings.pincode_tier_min_rows}"
        )
    populations = sorted(r.population for r in rows)
    if populations[0] < 0:
        raise TierSanityError("negative population in geo.pincode_tiers")
    thresholds = [_percentile(populations, p) for p in percentiles]
    if thresholds[0] <= thresholds[-1]:
        raise TierSanityError("flat population distribution cannot discriminate tiers")

    interval = timedelta(hours=settings.pincode_tier_min_change_interval_hours)
    changed = skipped = 0
    for row in rows:
        initial = row.computed_at is None
        if user_counts is not None and row.pincode in user_counts:
            row.user_count = user_counts[row.pincode]
        boosted = row.user_count >= settings.pincode_tier_user_threshold
        new_method = (
            "population+users"
            if boosted or row.method == "population+users"
            else "population"
        )
        pop_tier = _tier_for(row.population, thresholds)
        target = (
            max(1, pop_tier - settings.pincode_tier_user_promotion_step)
            if boosted
            else pop_tier
        )
        if not initial and settings.pincode_tier_promote_only and target > row.tier:
            target = row.tier  # never auto-demote (v1)

        if target != row.tier or initial:
            recently_changed = (
                row.tier_changed_at is not None and now - row.tier_changed_at < interval
            )
            if not initial and recently_changed:
                skipped += 1
            else:
                session.add(
                    PincodeTierHistory(
                        pincode=row.pincode,
                        old_tier=None if initial else row.tier,
                        new_tier=target,
                        old_method=None if initial else row.method,
                        new_method=new_method,
                        reason=(
                            "initial"
                            if initial
                            else (
                                "user_promotion"
                                if boosted and target < pop_tier
                                else "population_recompute"
                            )
                        ),
                    )
                )
                row.tier = target
                row.tier_changed_at = now
                changed += 1
        row.method = new_method
        row.computed_at = now

    await session.flush()
    logger.info(
        "geo.tier_classify",
        extra={
            "extra_fields": {
                "total": len(rows),
                "changed": changed,
                "skipped_hysteresis": skipped,
            }
        },
    )
    return TierRunResult(total=len(rows), changed=changed, skipped_hysteresis=skipped)
```

- [ ] **Step 4:** Run: `python -m pytest tests/test_geo_tiers.py tests/test_geo_tier_data.py -q` — expect PASS. If `test_real_snapshot_nn1` fails on tier placement, the Task 1 snapshot doesn't discriminate — go back to Task 1 Step 3, do not weaken the test.
- [ ] **Step 5: CLI script** `backend/core/scripts/load_pincode_tiers.py`, mirroring `scripts/load_geo.py` (argparse `--data-dir` defaulting to `backend/core/data/geo`, same `sys.path` bootstrap, `# noqa: T201` prints). Body: open `get_sessionmaker()()`, `count = await load_pincode_population(session, data_dir)`, then `result = await classify_tiers(session, now=datetime.now(UTC))` (no `user_counts` — the nightly job owns that), `await session.commit()`, print counts, exit non-zero on `TierSanityError`. One command = load + classify = "zero manual intervention" (NN1).
- [ ] **Step 6:** `ruff format . && ruff check . && mypy .` — PASS.
- [ ] **Step 7:** Commit: `git commit -am "feat(m4): percentile tier classifier + load_pincode_tiers script"`

---

### Task 5: Accessor `get_tier` + delivery wiring (NN2)

**Files:**
- Modify: `backend/core/shared/geo/service.py` (add `get_tier`)
- Modify: `backend/core/modules/ads/service.py` (`log_delivery` gains `tier` param, writes the column)
- Modify: `backend/core/modules/ads/router.py` (`serve()` resolves tier via the accessor)
- Test: `backend/core/tests/test_geo_tiers.py` (accessor), `backend/core/tests/test_ads_serve.py` (extend)

**Interfaces:**
- Produces: `async def get_tier(session: AsyncSession, pincode: str) -> int` in `shared.geo.service` — returns the stored tier or `DEFAULT_TIER` (4) with an info log; NEVER raises (spec: no blocking delivery). This is the ONLY read path for delivery (M3 analytics) and the M5 rate card — no direct `geo.pincode_tiers` reads from modules.

- [ ] **Step 1: Write failing accessor tests** — append to `tests/test_geo_tiers.py`:

```python
async def test_get_tier_returns_stored_tier(db_session: AsyncSession) -> None:
    from shared.geo.service import get_tier

    db_session.add(
        PincodeTier(pincode="641001", population=150000, population_grade="town", tier=2)
    )
    await db_session.flush()
    assert await get_tier(db_session, "641001") == 2


async def test_get_tier_unknown_pincode_defaults_t4(db_session: AsyncSession) -> None:
    from shared.geo.service import get_tier

    assert await get_tier(db_session, "000000") == 4  # NN2: safe default, no raise
```

- [ ] **Step 2:** Run: `python -m pytest tests/test_geo_tiers.py -q` — FAIL (no `get_tier`).
- [ ] **Step 3: Implement** in `backend/core/shared/geo/service.py`, next to `district_for_pincode` (mirror its session-usage style):

```python
async def get_tier(session: AsyncSession, pincode: str) -> int:
    """M4 accessor - the ONLY way modules read pincode tiers.

    Missing row -> DEFAULT_TIER (4), logged; never raises, so delivery is
    never blocked by an unclassified pincode (spec M4 DO-NOT).
    """
    tier = await session.scalar(
        select(PincodeTier.tier).where(PincodeTier.pincode == pincode)
    )
    if tier is None:
        logger.info(
            "geo.tier_default", extra={"extra_fields": {"pincode": pincode}}
        )
        return DEFAULT_TIER
    return int(tier)
```

(Imports: `from shared.geo.models import PincodeTier` and `from shared.geo.tiers import DEFAULT_TIER`; reuse the module's existing logger or create one via `shared.telemetry.get_logger`.)
- [ ] **Step 4:** Run accessor tests — PASS.
- [ ] **Step 5: Wire into delivery.** In `modules/ads/service.py::log_delivery`, add keyword param `tier: int | None = None` and include it in the `DeliveryDecision(...)` construction. In `modules/ads/router.py::serve()`, right where `log_delivery` is called, resolve `tier = await get_tier(session, pincode)` (import `from shared.geo.service import get_tier` — the module already imports `district_for_pincode` from there) and pass it through. Match the existing call signature/ordering exactly; touch nothing else in the serve flow.
- [ ] **Step 6: Extend `tests/test_ads_serve.py`** (reuse its app/client fixtures and seeding helpers verbatim — they set `ads_delivery_log_sample=1.0`):

```python
async def test_serve_records_tier_and_unknown_pincode_defaults(
    # same fixture list as the file's existing delivery_decisions test
) -> None:
    # Serve for a pincode with NO geo.pincode_tiers row (seed helpers don't
    # create any): response must be a normal 200 served ad (NN2: delivery
    # unaffected) and the logged decision row must carry tier=4.
    ...
```

Write it concretely by copying the file's existing delivery-decision logging test and adding the `tier` assertion (`SELECT tier FROM ads.delivery_decisions` → `[4]`). Then add a second case: seed `PincodeTier(pincode=<served pincode>, tier=2, population=100000, population_grade="town")`, serve again, assert the new row logs `tier=2`.
- [ ] **Step 7:** Run: `python -m pytest tests/test_ads_serve.py tests/test_geo_tiers.py -q` — PASS.
- [ ] **Step 8:** `ruff format . && ruff check . && mypy . && lint-imports` — PASS (ads → shared.geo is an allowed direction).
- [ ] **Step 9:** Commit: `git commit -am "feat(m4): get_tier accessor + delivery decision tier logging"`

---

### Task 6: User-count recount + nightly job (NN3)

**Files:**
- Create: `backend/core/modules/identity/user_counts.py`
- Create: `backend/core/scripts/geo_tier_nightly.py`
- Test: `backend/core/tests/test_geo_tiers.py` (extend)

**Interfaces:**
- Consumes: `classify_tiers(session, now=..., user_counts=...)` from Task 4; `Profile`/`User` from `modules.identity.models`.
- Produces: `async def verified_user_counts_by_pincode(session: AsyncSession) -> dict[str, int]`; CLI `python -m scripts.geo_tier_nightly` (kill switch `geo_tier_job_enabled`, exits 1 on `TierSanityError` so an external scheduler pages — the `scripts/coins_integrity.py` "nightly" pattern; no new scheduler, per spec).

- [ ] **Step 1: Write failing tests** — append to `tests/test_geo_tiers.py`:

```python
async def test_user_promotion_fires_at_threshold(
    db_session: AsyncSession, small_distribution: None, monkeypatch: pytest.MonkeyPatch
) -> None:
    """NN3: synthetic verified users crossing the threshold promote the tier,
    flip method, and write a history row."""
    monkeypatch.setenv("PINCODE_TIER_USER_THRESHOLD", "5")
    from settings import get_settings

    get_settings.cache_clear()
    from datetime import UTC, datetime, timedelta

    await _seed(db_session, {f"6{i:05d}": 100 * (10 ** (i % 5)) for i in range(20)})
    now = datetime.now(UTC)
    await classify_tiers(db_session, now=now)
    target = await db_session.scalar(
        select(PincodeTier).where(PincodeTier.pincode == "600003")
    )
    assert target is not None
    tier_before = target.tier

    later = now + timedelta(hours=25)  # clear the min-change interval
    result = await classify_tiers(db_session, now=later, user_counts={"600003": 5})
    await db_session.refresh(target)
    assert target.user_count == 5
    assert target.method == "population+users"
    assert target.tier == max(1, tier_before - 1)
    if tier_before > 1:
        assert result.changed == 1
        promo = (
            await db_session.scalars(
                select(PincodeTierHistory).where(
                    PincodeTierHistory.reason == "user_promotion"
                )
            )
        ).all()
        assert len(promo) == 1 and promo[0].pincode == "600003"


async def test_no_auto_demote(
    db_session: AsyncSession, small_distribution: None
) -> None:
    from datetime import UTC, datetime, timedelta

    await _seed(db_session, {f"6{i:05d}": 100 * (10 ** (i % 5)) for i in range(20)})
    now = datetime.now(UTC)
    await classify_tiers(db_session, now=now)
    best = await db_session.scalar(
        select(PincodeTier).where(PincodeTier.tier == 1).limit(1)
    )
    assert best is not None
    best.population = 1  # population collapse must NOT demote (v1)
    await db_session.flush()
    await classify_tiers(db_session, now=now + timedelta(hours=25))
    await db_session.refresh(best)
    assert best.tier == 1


async def test_verified_user_counts_filters(db_session: AsyncSession) -> None:
    from modules.identity.user_counts import verified_user_counts_by_pincode

    # seed users via the identity models directly, mirroring
    # tests/test_profile_router.py seeding style:
    # 1 verified+active with pincode 641001, 1 UNverified with 641001,
    # 1 verified but suspended with 641001, 1 verified+active without pincode
    ...
    counts = await verified_user_counts_by_pincode(db_session)
    assert counts == {"641001": 1}
```

Write the seeding concretely by copying the user/profile factory idiom from `tests/test_profile_router.py` (users need unique `phone` E.164 + `agri_id`; set `phone_verified_at=datetime.now(UTC)` for verified, `status="suspended"` for the suspended one).
- [ ] **Step 2:** Run — FAIL (no `modules.identity.user_counts`).
- [ ] **Step 3: Implement** `backend/core/modules/identity/user_counts.py`:

```python
"""Verified-user counts per pincode (M4 contract for shared.geo.tiers).

Lives in identity because identity owns these tables; shared must not
import modules (import-linter), so scripts/geo_tier_nightly.py composes
this with shared.geo.tiers.classify_tiers.
"""

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from modules.identity.models import Profile, User


async def verified_user_counts_by_pincode(session: AsyncSession) -> dict[str, int]:
    """Signup-farming defense (threat M4): only phone-verified, active,
    non-deleted users with a server-derived profile pincode count."""
    rows = await session.execute(
        select(Profile.pincode, func.count())
        .join(User, User.id == Profile.user_id)
        .where(
            User.phone_verified_at.is_not(None),
            User.status == "active",
            Profile.pincode.is_not(None),
        )
        .group_by(Profile.pincode)
    )
    return {str(pincode): int(count) for pincode, count in rows}
```

(Soft-deleted users/profiles are excluded automatically by the ORM soft-delete filter.)
- [ ] **Step 4: Nightly script** `backend/core/scripts/geo_tier_nightly.py`, mirroring `scripts/coins_integrity.py` exactly (docstring, `sys.path` bootstrap if that file has one, exit codes):

```python
"""Nightly pincode-tier recompute (M4). Run: python -m scripts.geo_tier_nightly

Recounts verified users per pincode, then reclassifies tiers (promote-only,
min-interval hysteresis). Exits non-zero on a failed sanity check so a
scheduler/CI marks the run failed and pages. Kill switch:
GEO_TIER_JOB_ENABLED=false. D12 events/cron pattern - no new scheduler.
"""

import asyncio
import sys
from datetime import UTC, datetime

from modules.identity.user_counts import verified_user_counts_by_pincode
from settings import get_settings
from shared.db import get_sessionmaker
from shared.geo.tiers import TierSanityError, classify_tiers


async def _main() -> int:
    if not get_settings().geo_tier_job_enabled:
        return 0
    async with get_sessionmaker()() as session:
        counts = await verified_user_counts_by_pincode(session)
        try:
            result = await classify_tiers(
                session, now=datetime.now(UTC), user_counts=counts
            )
        except TierSanityError as exc:
            print(f"pincode tier sanity check failed: {exc}")  # noqa: T201
            return 1
        await session.commit()
    print(  # noqa: T201
        f"pincode tiers: total={result.total} changed={result.changed}"
        f" skipped_hysteresis={result.skipped_hysteresis}"
    )
    return 0


if __name__ == "__main__":
    sys.exit(asyncio.run(_main()))
```

- [ ] **Step 5: Disabled-kill-switch smoke test** — append to `tests/test_geo_tiers.py` (mirror `test_ads_maintenance.py::test_worker_tick_disabled_by_env`):

```python
async def test_nightly_job_disabled_by_env(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("GEO_TIER_JOB_ENABLED", "false")
    from settings import get_settings

    get_settings.cache_clear()
    from scripts.geo_tier_nightly import _main

    assert await _main() == 0  # returns before touching the DB
```

- [ ] **Step 6:** Run: `python -m pytest tests/test_geo_tiers.py -q` — PASS.
- [ ] **Step 7:** `ruff format . && ruff check . && mypy . && lint-imports` — PASS.
- [ ] **Step 8:** Commit: `git commit -am "feat(m4): nightly verified-user recount + promote-only re-rank"`

---

### Task 7: Ops admin endpoints (distribution, lookup, override)

**Files:**
- Modify: `backend/core/shared/geo/tiers.py` (add `TierDistribution`, `tier_distribution`, `override_tier`, `UnknownPincodeTierError`)
- Modify: `backend/core/modules/ops/admin_router.py` (three routes + DTOs)
- Test: `backend/core/tests/test_ops_admin_tiers.py`

**Interfaces:**
- Consumes: Task 4's module; ops module conventions (`require_role(request, STAFF, SUPER_ADMIN)` — ops stays import-linter-independent of identity; `shared.audit.audit`).
- Produces:
  - `@dataclass(frozen=True, slots=True) class TierDistribution: buckets: dict[int, int]; by_method: dict[str, int]; unclassified: int; total: int`
  - `async def tier_distribution(session: AsyncSession) -> TierDistribution`
  - `async def override_tier(session: AsyncSession, pincode: str, new_tier: int, *, now: datetime) -> PincodeTier` (raises `UnknownPincodeTierError` when no row)
  - Routes: `GET /admin/ops/pincode-tiers/distribution` → `TierDistributionOut`; `GET /admin/ops/pincode-tiers/{pincode}` → `PincodeTierOut` (404 when absent); `POST /admin/ops/pincode-tiers/{pincode}` body `{"tier": 1..5}` → `PincodeTierOut`.

- [ ] **Step 1: Write failing tests** in `backend/core/tests/test_ops_admin_tiers.py`, copying the app/client + role-header fixtures from the file `tests/` uses for existing ops admin routes (find the ops moderation-queue test file and mirror its auth setup exactly):
  - staff role: `GET /admin/ops/pincode-tiers/distribution` → 200, `buckets` has keys for all five tiers (zero-filled), `total` correct after seeding 3 `PincodeTier` rows.
  - non-staff principal → 403.
  - `GET /admin/ops/pincode-tiers/641001` after seeding → 200 with population/user_count/method; unknown pincode → 404.
  - `POST /admin/ops/pincode-tiers/641001` `{"tier": 1}` → 200; `geo.pincode_tier_history` gains a row with `reason='admin_override'` (NN4 for the manual path); `audit.entries` gains an action `geo.tier_override` row (query the audit table the way existing ops decision-route tests do); posting `{"tier": 9}` → 422.
- [ ] **Step 2:** Run — FAIL.
- [ ] **Step 3: Implement service side** — append to `shared/geo/tiers.py`:

```python
class UnknownPincodeTierError(LookupError):
    """No geo.pincode_tiers row for this pincode."""


@dataclass(frozen=True, slots=True)
class TierDistribution:
    buckets: dict[int, int]
    by_method: dict[str, int]
    unclassified: int
    total: int


async def tier_distribution(session: AsyncSession) -> TierDistribution:
    tier_rows = (
        await session.execute(
            select(PincodeTier.tier, func.count()).group_by(PincodeTier.tier)
        )
    ).all()
    buckets = {tier: 0 for tier in range(1, 6)}
    buckets.update({int(t): int(c) for t, c in tier_rows})
    method_rows = (
        await session.execute(
            select(PincodeTier.method, func.count()).group_by(PincodeTier.method)
        )
    ).all()
    unclassified = await session.scalar(
        select(func.count())
        .select_from(PincodeTier)
        .where(PincodeTier.computed_at.is_(None))
    )
    return TierDistribution(
        buckets=buckets,
        by_method={str(m): int(c) for m, c in method_rows},
        unclassified=int(unclassified or 0),
        total=sum(buckets.values()),
    )


async def override_tier(
    session: AsyncSession, pincode: str, new_tier: int, *, now: datetime
) -> PincodeTier:
    """Admin escape hatch (spec: exists, nothing REQUIRES it). Bypasses
    promote-only; note a demoting override is re-promoted by the next
    nightly run - durable overrides are a v2 concern."""
    row = await session.scalar(select(PincodeTier).where(PincodeTier.pincode == pincode))
    if row is None:
        raise UnknownPincodeTierError(pincode)
    if new_tier != row.tier:
        session.add(
            PincodeTierHistory(
                pincode=pincode,
                old_tier=row.tier,
                new_tier=new_tier,
                old_method=row.method,
                new_method=row.method,
                reason="admin_override",
            )
        )
        row.tier = new_tier
        row.tier_changed_at = now
    await session.flush()
    return row
```

(Add `func` to the file's sqlalchemy imports.)
- [ ] **Step 4: Implement routes** in `modules/ops/admin_router.py`. The router's prefix is `/admin`; register the decorators as `@admin_router.get("/ops/pincode-tiers/distribution")` etc. so the full paths match what the console's `getJson("/ops/pincode-tiers/distribution")` hits (`/admin/ops/...` — the same idiom as the existing `/ops/flags` route, NOT the `/moderation/*` style). Mirror the file's existing DTO/route/`require_role` style (pincode path param validated `Path(pattern=r"^\d{6}$")`; `TierOverrideIn` with `model_config = ConfigDict(extra="forbid")` and `tier: int = Field(ge=1, le=5)`). The POST route: call `override_tier(...)`, catch `UnknownPincodeTierError` → `HTTPException(404, "unknown pincode")`, write `audit(session, action="geo.tier_override", actor_user_id=<principal id, however the file's existing decision routes obtain it>, metadata={"pincode": pincode, "tier": payload.tier})`, commit the way sibling mutating routes do. Response DTO:

```python
class PincodeTierOut(BaseModel):
    pincode: str
    tier: int
    population: int
    user_count: int
    method: str
    computed_at: datetime | None
    tier_changed_at: datetime | None


class TierBucketOut(BaseModel):
    tier: int
    count: int


class TierDistributionOut(BaseModel):
    buckets: list[TierBucketOut]  # always 5 entries, T1..T5
    by_method: dict[str, int]
    unclassified: int
    total: int
```

- [ ] **Step 5:** Run: `python -m pytest tests/test_ops_admin_tiers.py -q` — PASS.
- [ ] **Step 6:** Regenerate the ops module doc if routes are listed there: `python scripts/gen_module_claude.py` (module CLAUDE.md files are generated — never hand-edit).
- [ ] **Step 7:** `ruff format . && ruff check . && mypy . && lint-imports` — PASS.
- [ ] **Step 8:** Commit: `git commit -am "feat(m4): ops pincode-tier distribution + admin override endpoints"`

---

### Task 8: Ops Console histogram panel

**Files:**
- Create: `apps/web-admin/app/ops/pincode-tiers-panel.tsx`
- Modify: `apps/web-admin/app/ops/ops-manager.tsx` (render the panel below `<FlagsPanel />`)

**Interfaces:**
- Consumes: `GET /api/admin/ops/pincode-tiers/distribution` through the existing prefix proxy (`app/api/admin/[...path]/route.ts` — zero proxy changes needed) via `getJson("/ops/pincode-tiers/distribution")` from `lib/api.ts`.

- [ ] **Step 1: Build the panel**, modeled line-for-line on `app/ops/flags-panel.tsx` (client component, load on mount, 403 → forbidden notice, `Skeleton` while loading, `Card`/`EmptyState` from `@agri/ui`). Rendering: five rows T1–T5, each a token-styled div bar — no chart library, no raw hex:

```tsx
type TierDistribution = {
  buckets: { tier: number; count: number }[];
  by_method: Record<string, number>;
  unclassified: number;
  total: number;
};

// inside the loaded state render:
const max = Math.max(1, ...dist.buckets.map((b) => b.count));
return (
  <Card>
    <h3 className="text-sm font-semibold text-ink">Pincode tiers</h3>
    <p className="text-xs text-sub">
      T1 metro &rarr; T5 extreme rural &middot; {dist.total} pincodes
      {dist.unclassified > 0 ? ` · ${dist.unclassified} unclassified` : ""}
    </p>
    <div className="mt-3 space-y-2">
      {dist.buckets.map((b) => (
        <div key={b.tier} className="flex items-center gap-2">
          <span className="w-8 text-sm text-sub">T{b.tier}</span>
          <div className="h-4 flex-1 overflow-hidden rounded-pill bg-ghost">
            <div
              className="h-full rounded-pill bg-brand"
              style={{ width: `${(b.count / max) * 100}%` }}
            />
          </div>
          <span className="w-16 text-right text-sm tabular-nums text-ink">
            {b.count}
          </span>
        </div>
      ))}
    </div>
    <p className="mt-3 text-xs text-sub">
      {Object.entries(dist.by_method)
        .map(([method, count]) => `${method}: ${count}`)
        .join(" · ")}
    </p>
  </Card>
);
```

- [ ] **Step 2:** Mount `<PincodeTiersPanel />` in `ops-manager.tsx` directly below `<FlagsPanel />`.
- [ ] **Step 3:** Verify: `pnpm -w typecheck && pnpm -w lint && pnpm check:hex` — PASS. (No new e2e spec: web-admin/port 3004 isn't in the Playwright webServer list and adding that infra is out of M4 scope — same status as the existing flags panel.)
- [ ] **Step 4:** Manual smoke (if dev stack is running): load `http://localhost:3004/ops` as a staff user, confirm the histogram renders zero-state cleanly when `geo.pincode_tiers` is empty.
- [ ] **Step 5:** Commit: `git commit -am "feat(m4): ops console pincode-tier distribution histogram"`

---

### Task 9: Full gates, docs, PR

- [ ] **Step 1: Full backend gates** (the exact pre-push list from memory): `cd backend/core && ruff format --check . && ruff check . && mypy . && lint-imports && python -m pytest -q -m "not slow"`.
- [ ] **Step 2: Frontend gates:** `pnpm -w typecheck && pnpm -w lint && pnpm -w test && pnpm check:hex`.
- [ ] **Step 3: Migration up/down/up** on a scratch DB only (`agri_migrate_check` — NEVER the dev DB, D05): create a throwaway DB, `ALEMBIC_DATABASE_URL=<scratch> alembic upgrade head && alembic downgrade base && alembic upgrade head`, drop it.
- [ ] **Step 4:** Extend the manual QA guide (`docs/qa/` — the M3-extended file) with M4 checks: run `python -m scripts.load_pincode_tiers`, confirm `/ops` histogram populates, override a pincode and see the history row.
- [ ] **Step 5:** Push branch `feat/m4-pincode-tiers`; open PR → `dev` titled `feat(m4): automatic pincode tiers` via the credential-fill API (no gh CLI). PR title must satisfy the conventional-commit title check; if CI's PR-title job replays a stale title, re-run it (known trap).
- [ ] **Step 6:** Watch the 8 required checks; fix forward on the branch. Do NOT delete any remote branch.

## Spec coverage map

- M4.A (data + table + history) → Tasks 1, 2, 3
- M4.B (percentile classification job, config thresholds, idempotent) → Task 4
- M4.C (nightly user-count re-rank, method flip, promote-only, automatic) → Task 6
- M4.D (expose: delivery accessor + ops console histogram) → Tasks 5, 7, 8
- M4.E (TN complete, pan-India dormant) → Task 1 (coverage test) + design decision 1
- NN1 → Task 4 `test_real_snapshot_nn1` · NN2 → Task 5 serve test + accessor default test · NN3 → Task 6 promotion test · NN4 → Task 4 history assertions + Task 7 override history test
- Threats: bad source data → sanity checks (Task 4) + provenance (Tasks 1, 2); signup farming → verified-only counts (Task 6) + threshold config; flapping → promote-only + `tier_changed_at` interval (Task 4)
- DO-NOTs honored: no manual primary path (admin override is optional, Task 7), licensed sources only (Task 1), no auto-demote (Task 4 + test), no delivery blocking (Task 5)
