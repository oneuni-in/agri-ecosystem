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
