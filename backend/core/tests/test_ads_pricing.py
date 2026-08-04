"""M5 pricing: server-side only, integer paise, bp multipliers."""

from collections.abc import Callable
from datetime import date
from typing import Any

import pytest
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from modules.ads import pricing

pytestmark = pytest.mark.asyncio


def _ceil_div(a: int, b: int) -> int:
    return -(-a // b)


async def pricing_test_helpers_upsert_tier(session: AsyncSession, pincode: str, tier: int) -> None:
    """Write a geo.pincode_tiers row via raw SQL (tests may; app code must not -
    the only sanctioned read is shared.geo.service.get_tier)."""
    await session.execute(
        text(
            "INSERT INTO geo.pincode_tiers"
            " (id, pincode, population, population_grade, tier, computed_at)"
            " VALUES (gen_random_uuid(), :pincode, 1000, 'town', :tier, now())"
            " ON CONFLICT (pincode) DO UPDATE SET tier = EXCLUDED.tier,"
            " computed_at = EXCLUDED.computed_at"
        ),
        {"pincode": pincode, "tier": tier},
    )


async def test_cpm_quote_priciest_tier_and_multiplier(db_session: AsyncSession) -> None:
    # 641001 exists in geo.pincode_tiers with a real tier from the M4 snapshot;
    # write a T2 row explicitly so the assertion is deterministic.
    await pricing_test_helpers_upsert_tier(db_session, "641001", 2)
    quote = await pricing.quote_campaign(
        db_session,
        slot_keys=["milk_home_hero"],
        geo_target={"pincodes": ["641001"]},
        categories=["ghee"],
        flight_start=date(2026, 8, 10),
        flight_end=date(2026, 8, 24),
        serves_total=10_000,
    )
    # v1 card: cpm T2 = 20000 paise, ghee multiplier 12000bp
    expected_subtotal = _ceil_div(10_000 * 20000 * 12000, 1000 * 10000)
    assert quote.pricing_model == "cpm" and quote.tier == 2
    assert quote.subtotal_paise == expected_subtotal
    assert quote.gst_paise == _ceil_div(expected_subtotal * 1800, 10000)
    assert quote.total_paise == quote.subtotal_paise + quote.gst_paise
    assert quote.rate_card_version == 1


async def test_global_targeting_prices_tier1(db_session: AsyncSession) -> None:
    quote = await pricing.quote_campaign(
        db_session,
        slot_keys=["milk_home_hero"],
        geo_target={},
        categories=[],
        flight_start=date(2026, 8, 10),
        flight_end=date(2026, 8, 17),
        serves_total=1000,
    )
    assert quote.tier == 1 and quote.multiplier_bp == 10000


async def test_tier_targeting_prices_best_tier(db_session: AsyncSession) -> None:
    quote = await pricing.quote_campaign(
        db_session,
        slot_keys=["milk_home_hero"],
        geo_target={"state": 33, "tiers": [3, 4]},
        categories=[],
        flight_start=date(2026, 8, 10),
        flight_end=date(2026, 8, 17),
        serves_total=1000,
    )
    assert quote.tier == 3


async def test_flat_weekly_rounds_weeks_up(db_session: AsyncSession) -> None:
    quote = await pricing.quote_campaign(
        db_session,
        slot_keys=["milk_sponsored_listing"],
        geo_target={"pincodes": ["641001"]},
        categories=[],
        flight_start=date(2026, 8, 10),
        flight_end=date(2026, 8, 20),  # 10 days -> 2 weeks
        serves_total=None,
    )
    assert quote.weeks == 2 and quote.serves_total is None


async def test_mixed_slots_rejected(db_session: AsyncSession) -> None:
    with pytest.raises(pricing.RateCardError) as exc:
        await pricing.quote_campaign(
            db_session,
            slot_keys=["milk_home_hero", "milk_sponsored_listing"],
            geo_target={},
            categories=[],
            flight_start=date(2026, 8, 10),
            flight_end=date(2026, 8, 17),
            serves_total=1000,
        )
    assert exc.value.code == "mixed_pricing_models"


async def test_validate_rate_card_rejects_bad_config() -> None:
    good = dict(pricing.DEFAULT_CONFIG_KEYS_EXAMPLE)  # a valid literal dict
    cases: list[tuple[Callable[[dict[str, Any]], Any], str]] = [
        (lambda c: c.pop("cpm_paise"), "missing_key"),
        (lambda c: c["cpm_paise"].pop("3"), "bad_tier_map"),
        (lambda c: c["cpm_paise"].update({"1": -5}), "bad_tier_map"),
        (lambda c: c["category_multipliers_bp"].update({"ghee": 0}), "bad_multiplier"),
        (lambda c: c.update({"min_total_paise": -1}), "bad_min"),
    ]
    for mutate, code in cases:
        cfg = {k: dict(v) if isinstance(v, dict) else v for k, v in good.items()}
        mutate(cfg)
        with pytest.raises(pricing.RateCardError) as exc:
            pricing.validate_rate_card(cfg)
        assert exc.value.code == code
