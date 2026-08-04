"""Idempotent loader for the committed geo snapshot CSVs.

CSV formats (see backend/core/data/geo/SOURCES.md for provenance):
    states.csv:    lgd_code,name,name_ta
    districts.csv: lgd_code,state_lgd_code,name,name_ta
    pincodes.csv:  pincode,district_lgd_code,lat,lng
"""

import csv
from dataclasses import dataclass
from decimal import Decimal
from pathlib import Path

from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession

from shared.geo.models import District, Pincode, PincodeTier, State


@dataclass(frozen=True, slots=True)
class GeoLoadCounts:
    states: int
    districts: int
    pincodes: int


def _read(data_dir: Path, name: str) -> list[dict[str, str]]:
    with open(data_dir / name, newline="", encoding="utf-8") as fh:
        return list(csv.DictReader(fh))


async def load_geo(session: AsyncSession, data_dir: Path) -> GeoLoadCounts:
    """Upsert the snapshot; safe to re-run (natural keys: lgd_code, pincode)."""
    states = _read(data_dir, "states.csv")
    for row in states:
        await session.execute(
            insert(State)
            .values(
                lgd_code=int(row["lgd_code"]),
                name=row["name"],
                name_ta=row["name_ta"] or None,
            )
            .on_conflict_do_update(
                index_elements=[State.lgd_code],
                set_={"name": row["name"], "name_ta": row["name_ta"] or None},
            )
        )

    state_ids = dict((await session.execute(select(State.lgd_code, State.id))).tuples().all())

    districts = _read(data_dir, "districts.csv")
    for row in districts:
        await session.execute(
            insert(District)
            .values(
                lgd_code=int(row["lgd_code"]),
                state_id=state_ids[int(row["state_lgd_code"])],
                name=row["name"],
                name_ta=row["name_ta"] or None,
            )
            .on_conflict_do_update(
                index_elements=[District.lgd_code],
                set_={"name": row["name"], "name_ta": row["name_ta"] or None},
            )
        )

    district_ids = dict(
        (await session.execute(select(District.lgd_code, District.id))).tuples().all()
    )

    pincodes = _read(data_dir, "pincodes.csv")
    for row in pincodes:
        values = {
            "district_id": district_ids[int(row["district_lgd_code"])],
            "centroid_lat": Decimal(row["lat"]),
            "centroid_lon": Decimal(row["lng"]),
        }
        await session.execute(
            insert(Pincode)
            .values(pincode=row["pincode"], **values)
            .on_conflict_do_update(index_elements=[Pincode.pincode], set_=values)
        )

    await session.flush()
    return GeoLoadCounts(states=len(states), districts=len(districts), pincodes=len(pincodes))


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
