"""geo schema v1: Tamil Nadu snapshot loads, pincode -> district + centroid
lookups are correct (D03 non-negotiable 4)."""

import csv
from decimal import Decimal
from pathlib import Path

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from shared.geo.loader import load_geo
from shared.geo.models import District, Pincode, State
from shared.geo.service import centroid_for_pincode, district_for_pincode

DATA_DIR = Path(__file__).resolve().parents[1] / "data" / "geo"


def _csv_rows(path: Path) -> int:
    with path.open(encoding="utf-8") as fh:
        return sum(1 for _ in csv.DictReader(fh))


# Tamil Nadu bounding box (generous)
TN_LAT = (Decimal("8.0"), Decimal("13.6"))
TN_LON = (Decimal("76.2"), Decimal("80.4"))


async def test_tn_snapshot_loads_with_expected_counts(db_session: AsyncSession) -> None:
    counts = await load_geo(db_session, DATA_DIR)

    assert counts.states == _csv_rows(DATA_DIR / "states.csv")
    assert counts.districts == 38  # TN has 38 districts (LGD)
    assert counts.pincodes > 1000

    assert await db_session.scalar(select(func.count()).select_from(State)) == _csv_rows(
        DATA_DIR / "states.csv"
    )
    assert await db_session.scalar(select(func.count()).select_from(District)) == 38
    assert await db_session.scalar(select(func.count()).select_from(Pincode)) == counts.pincodes


async def test_loader_is_idempotent(db_session: AsyncSession) -> None:
    first = await load_geo(db_session, DATA_DIR)
    second = await load_geo(db_session, DATA_DIR)

    assert (first.states, first.districts, first.pincodes) == (
        second.states,
        second.districts,
        second.pincodes,
    )
    assert await db_session.scalar(select(func.count()).select_from(District)) == 38


async def test_chennai_gpo_pincode_resolves_to_chennai(db_session: AsyncSession) -> None:
    await load_geo(db_session, DATA_DIR)

    district = await district_for_pincode(db_session, "600001")
    assert district is not None
    assert district.name == "Chennai"

    centroid = await centroid_for_pincode(db_session, "600001")
    assert centroid is not None
    lat, lon = centroid
    # Chennai GPO is at ~13.08N 80.29E; assert a tight box around it
    assert Decimal("12.8") < lat < Decimal("13.4")
    assert Decimal("80.0") < lon < Decimal("80.4")


async def test_all_centroids_fall_inside_tamil_nadu(db_session: AsyncSession) -> None:
    await load_geo(db_session, DATA_DIR)

    out_of_bounds = await db_session.scalar(
        select(func.count())
        .select_from(Pincode)
        .where(
            (Pincode.centroid_lat < TN_LAT[0])
            | (Pincode.centroid_lat > TN_LAT[1])
            | (Pincode.centroid_lon < TN_LON[0])
            | (Pincode.centroid_lon > TN_LON[1])
        )
    )
    assert out_of_bounds == 0


async def test_unknown_pincode_returns_none(db_session: AsyncSession) -> None:
    await load_geo(db_session, DATA_DIR)

    assert await district_for_pincode(db_session, "999999") is None
    assert await centroid_for_pincode(db_session, "999999") is None


async def test_every_district_has_at_least_one_pincode(db_session: AsyncSession) -> None:
    await load_geo(db_session, DATA_DIR)

    empty = await db_session.scalar(
        select(func.count())
        .select_from(District)
        .where(~District.id.in_(select(Pincode.district_id).distinct()))
    )
    assert empty == 0
