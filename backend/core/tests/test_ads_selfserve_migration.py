"""M5 migration 0033: lifecycle statuses, pricing columns, rate_card_versions."""

from collections.abc import AsyncIterator

import pytest
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncEngine, create_async_engine
from sqlalchemy.pool import NullPool


@pytest.fixture
async def engine(database_url: str) -> AsyncIterator[AsyncEngine]:
    eng = create_async_engine(database_url, poolclass=NullPool)
    yield eng
    await eng.dispose()


async def test_campaign_lifecycle_statuses_accepted(engine: AsyncEngine) -> None:
    async with engine.begin() as conn:
        for status in ("pending_payment", "pending_moderation", "exhausted", "expired"):
            await conn.execute(
                text(
                    "INSERT INTO ads.campaigns"
                    " (id, advertiser_business_id, name, status, flight_start, flight_end)"
                    " VALUES (gen_random_uuid(), gen_random_uuid(), 'm5', :status,"
                    " current_date, current_date + 7)"
                ),
                {"status": status},
            )
        await conn.execute(text("DELETE FROM ads.campaigns WHERE name = 'm5'"))


async def test_campaign_bogus_status_rejected(engine: AsyncEngine) -> None:
    from sqlalchemy.exc import IntegrityError

    async with engine.connect() as conn:
        with pytest.raises(IntegrityError):
            await conn.execute(
                text(
                    "INSERT INTO ads.campaigns"
                    " (id, advertiser_business_id, name, status, flight_start, flight_end)"
                    " VALUES (gen_random_uuid(), gen_random_uuid(), 'm5', 'bogus',"
                    " current_date, current_date + 7)"
                )
            )


async def test_pricing_columns_exist_and_price_nonnegative(engine: AsyncEngine) -> None:
    from sqlalchemy.exc import IntegrityError

    async with engine.connect() as conn:
        cols = await conn.execute(
            text(
                "SELECT column_name FROM information_schema.columns"
                " WHERE table_schema='ads' AND table_name='campaigns'"
            )
        )
        names = {row[0] for row in cols}
        assert {
            "pricing_model",
            "price_paise",
            "price_subtotal_paise",
            "price_gst_paise",
            "rate_card_version",
            "paid_at",
            "daily_serve_cap",
        } <= names
        with pytest.raises(IntegrityError):
            await conn.execute(
                text(
                    "INSERT INTO ads.campaigns"
                    " (id, advertiser_business_id, name, status, flight_start, flight_end,"
                    " price_paise) VALUES (gen_random_uuid(), gen_random_uuid(), 'm5',"
                    " 'draft', current_date, current_date + 7, -1)"
                )
            )


async def test_price_subtotal_nonnegative(engine: AsyncEngine) -> None:
    from sqlalchemy.exc import IntegrityError

    async with engine.connect() as conn:
        with pytest.raises(IntegrityError):
            await conn.execute(
                text(
                    "INSERT INTO ads.campaigns"
                    " (id, advertiser_business_id, name, status, flight_start, flight_end,"
                    " price_subtotal_paise) VALUES (gen_random_uuid(), gen_random_uuid(), 'm5',"
                    " 'draft', current_date, current_date + 7, -1)"
                )
            )


async def test_price_gst_nonnegative(engine: AsyncEngine) -> None:
    from sqlalchemy.exc import IntegrityError

    async with engine.connect() as conn:
        with pytest.raises(IntegrityError):
            await conn.execute(
                text(
                    "INSERT INTO ads.campaigns"
                    " (id, advertiser_business_id, name, status, flight_start, flight_end,"
                    " price_gst_paise) VALUES (gen_random_uuid(), gen_random_uuid(), 'm5',"
                    " 'draft', current_date, current_date + 7, -1)"
                )
            )


async def test_rate_card_seeded_and_append_only(engine: AsyncEngine) -> None:
    from sqlalchemy.exc import ProgrammingError

    async with engine.connect() as conn:
        row = (
            await conn.execute(
                text("SELECT version, config FROM ads.rate_card_versions ORDER BY version DESC")
            )
        ).first()
        assert row is not None and row.version == 1
        assert set(row.config) >= {
            "cpm_paise",
            "flat_weekly_paise",
            "category_multipliers_bp",
            "min_total_paise",
        }
        # app_rt must not UPDATE/DELETE (append-only by grant)
        with pytest.raises(ProgrammingError, match="permission denied"):
            await conn.execute(text("UPDATE ads.rate_card_versions SET version = version"))
