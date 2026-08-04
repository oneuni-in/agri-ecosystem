"""M4 pincode tiers: loader, classifier, accessor, recount."""

import csv as csv_mod
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from modules.identity.models import Profile, User
from modules.identity.user_counts import verified_user_counts_by_pincode
from scripts.geo_tier_nightly import _main
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


async def test_user_promotion_fires_at_threshold(
    db_session: AsyncSession, small_distribution: None, monkeypatch: pytest.MonkeyPatch
) -> None:
    """NN3: synthetic verified users crossing the threshold promote the tier,
    flip method, and write a history row."""
    monkeypatch.setenv("PINCODE_TIER_USER_THRESHOLD", "5")
    from settings import get_settings

    get_settings.cache_clear()

    await _seed(db_session, {f"6{i:05d}": 100 * (10 ** (i % 5)) for i in range(20)})
    now = datetime.now(UTC)
    await classify_tiers(db_session, now=now)
    target = await db_session.scalar(select(PincodeTier).where(PincodeTier.pincode == "600003"))
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
                select(PincodeTierHistory).where(PincodeTierHistory.reason == "user_promotion")
            )
        ).all()
        assert len(promo) == 1 and promo[0].pincode == "600003"


async def test_no_auto_demote(db_session: AsyncSession, small_distribution: None) -> None:
    await _seed(db_session, {f"6{i:05d}": 100 * (10 ** (i % 5)) for i in range(20)})
    now = datetime.now(UTC)
    await classify_tiers(db_session, now=now)
    best = await db_session.scalar(select(PincodeTier).where(PincodeTier.tier == 1).limit(1))
    assert best is not None
    best.population = 1  # population collapse must NOT demote (v1)
    await db_session.flush()
    await classify_tiers(db_session, now=now + timedelta(hours=25))
    await db_session.refresh(best)
    assert best.tier == 1


async def test_verified_user_counts_filters(db_session: AsyncSession) -> None:
    # 1 verified+active with pincode 641001, 1 UNverified with 641001,
    # 1 verified but suspended with 641001, 1 verified+active without pincode
    verified_active = User(
        phone="+919876500001", agri_id="AG-9000101", phone_verified_at=datetime.now(UTC)
    )
    unverified = User(phone="+919876500002", agri_id="AG-9000102")
    verified_suspended = User(
        phone="+919876500003",
        agri_id="AG-9000103",
        phone_verified_at=datetime.now(UTC),
        status="suspended",
    )
    verified_no_pincode = User(
        phone="+919876500004", agri_id="AG-9000104", phone_verified_at=datetime.now(UTC)
    )
    db_session.add_all([verified_active, unverified, verified_suspended, verified_no_pincode])
    await db_session.flush()

    db_session.add_all(
        [
            Profile(user_id=verified_active.id, pincode="641001"),
            Profile(user_id=unverified.id, pincode="641001"),
            Profile(user_id=verified_suspended.id, pincode="641001"),
            Profile(user_id=verified_no_pincode.id, pincode=None),
        ]
    )
    await db_session.flush()

    counts = await verified_user_counts_by_pincode(db_session)
    assert counts == {"641001": 1}


async def test_full_snapshot_resets_stale_user_count(
    db_session: AsyncSession, small_distribution: None, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Task 4 review fix: user_counts is a FULL snapshot - a pincode absent
    from it (e.g. its last verified user unverified/left) must reset to 0,
    not keep a stale boosted count. Tier stays put (promote-only)."""
    monkeypatch.setenv("PINCODE_TIER_USER_THRESHOLD", "5")
    from settings import get_settings

    get_settings.cache_clear()

    await _seed(db_session, {f"6{i:05d}": 100 * (10 ** (i % 5)) for i in range(20)})
    now = datetime.now(UTC)
    await classify_tiers(db_session, now=now)
    target = await db_session.scalar(select(PincodeTier).where(PincodeTier.pincode == "600003"))
    assert target is not None

    boosted_at = now + timedelta(hours=25)
    await classify_tiers(db_session, now=boosted_at, user_counts={"600003": 5})
    await db_session.refresh(target)
    assert target.user_count == 5
    tier_after_boost = target.tier

    reset_at = boosted_at + timedelta(hours=25)
    await classify_tiers(db_session, now=reset_at, user_counts={})  # empty snapshot != None
    await db_session.refresh(target)
    assert target.user_count == 0
    assert target.tier == tier_after_boost  # promote-only: no auto-demote


async def test_hysteresis_skips_within_interval(
    db_session: AsyncSession, small_distribution: None, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A would-be change inside pincode_tier_min_change_interval_hours is
    counted and skipped instead of applied."""
    monkeypatch.setenv("PINCODE_TIER_USER_THRESHOLD", "5")
    from settings import get_settings

    get_settings.cache_clear()

    await _seed(db_session, {f"6{i:05d}": 100 * (10 ** (i % 5)) for i in range(20)})
    now = datetime.now(UTC)
    await classify_tiers(db_session, now=now)
    target = await db_session.scalar(select(PincodeTier).where(PincodeTier.pincode == "600003"))
    assert target is not None
    tier_before = target.tier

    soon = now + timedelta(hours=1)  # well within the 24h min-change interval
    result = await classify_tiers(db_session, now=soon, user_counts={"600003": 5})
    await db_session.refresh(target)
    assert result.skipped_hysteresis >= 1
    assert target.tier == tier_before  # change was skipped, not applied


async def test_nightly_job_disabled_by_env(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("GEO_TIER_JOB_ENABLED", "false")
    from settings import get_settings

    get_settings.cache_clear()

    assert await _main() == 0  # returns before touching the DB
