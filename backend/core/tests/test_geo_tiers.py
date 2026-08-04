"""M4 pincode tiers: loader, classifier, accessor, recount."""

import csv as csv_mod
from datetime import UTC, datetime
from pathlib import Path

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from shared.geo.loader import load_pincode_population
from shared.geo.models import PincodeTier, PincodeTierHistory
from shared.geo.service import get_tier
from shared.geo.tiers import TierSanityError, classify_tiers, tier_percentiles

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


@pytest.fixture
def small_distribution(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("PINCODE_TIER_MIN_ROWS", "3")
    from settings import get_settings

    get_settings.cache_clear()


async def _seed(db_session: AsyncSession, rows: dict[str, int]) -> None:
    for pincode, population in rows.items():
        db_session.add(PincodeTier(pincode=pincode, population=population, population_grade="town"))
    await db_session.flush()


async def test_classify_assigns_tiers_and_initial_history(
    db_session: AsyncSession, small_distribution: None
) -> None:
    # 20 rows spanning 5 orders of magnitude -> percentiles discriminate
    await _seed(db_session, {f"6{i:05d}": 100 * (10 ** (i % 5)) for i in range(20)})

    result = await classify_tiers(db_session, now=datetime.now(UTC))
    assert result.total == 20
    assert result.changed > 0
    history = (await db_session.scalars(select(PincodeTierHistory))).all()
    assert all(h.reason == "initial" for h in history)  # NN4: change -> history row
    tiers = {r.pincode: r.tier for r in (await db_session.scalars(select(PincodeTier))).all()}
    assert set(tiers.values()) <= {1, 2, 3, 4, 5}


async def test_classify_is_idempotent(db_session: AsyncSession, small_distribution: None) -> None:
    await _seed(db_session, {f"6{i:05d}": 1000 * (i + 1) for i in range(10)})

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

    with pytest.raises(TierSanityError):
        await classify_tiers(db_session, now=datetime.now(UTC))


async def test_too_few_rows_refused(db_session: AsyncSession) -> None:
    await _seed(db_session, {"641001": 100000})

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


async def test_get_tier_returns_stored_tier(db_session: AsyncSession) -> None:
    db_session.add(
        PincodeTier(pincode="641001", population=150000, population_grade="town", tier=2)
    )
    await db_session.flush()
    assert await get_tier(db_session, "641001") == 2


async def test_get_tier_unknown_pincode_defaults_t4(db_session: AsyncSession) -> None:
    assert await get_tier(db_session, "000000") == 4  # NN2: safe default, no raise
