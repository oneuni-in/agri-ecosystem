"""M5 rate card + quoting. Server-side pricing ONLY (threat: price tampering).

All money is integer paise; multipliers are basis points. The client never sends
an amount - checkout re-quotes and stores the server number.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from datetime import date
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from modules.ads.models import RateCardVersion
from settings import get_settings
from shared.geo.service import get_tier

TIER_KEYS = ("1", "2", "3", "4", "5")
BP_ONE = 10000
MIN_CPM_SERVES = 1000
FLAT_SUFFIX = "_sponsored_listing"
# Every money column on ads.campaigns / billing.ad_orders / billing.invoices is
# INT4 (max 2,147,483,647 paise). An unbounded serve count or a decades-long
# flat flight would otherwise quote a number Postgres cannot store, surfacing
# as an asyncpg NumericValueOutOfRange 500 at create time (and a bogus,
# uncheckoutable number from /quote). Ceiling is on the GST-INCLUSIVE total,
# with headroom under INT4 - a validation error (422), never a 500.
MAX_TOTAL_PAISE = 2_000_000_000

# A valid config literal, used by tests and as documentation of the shape.
DEFAULT_CONFIG_KEYS_EXAMPLE: dict[str, Any] = {
    "cpm_paise": {"1": 30000, "2": 20000, "3": 12000, "4": 8000, "5": 5000},
    "flat_weekly_paise": {"1": 150000, "2": 100000, "3": 60000, "4": 40000, "5": 25000},
    "category_multipliers_bp": {"ghee": 12000},
    "min_total_paise": 10000,
}


class RateCardError(ValueError):
    def __init__(self, code: str) -> None:
        super().__init__(code)
        self.code = code


def _ceil_div(a: int, b: int) -> int:
    return -(-a // b)


def validate_rate_card(config: dict[str, Any]) -> None:
    for key in ("cpm_paise", "flat_weekly_paise", "category_multipliers_bp", "min_total_paise"):
        if key not in config:
            raise RateCardError("missing_key")
    for key in ("cpm_paise", "flat_weekly_paise"):
        tier_map = config[key]
        if (
            not isinstance(tier_map, dict)
            or set(tier_map) != set(TIER_KEYS)
            or not all(isinstance(v, int) and v > 0 for v in tier_map.values())
        ):
            raise RateCardError("bad_tier_map")
    mults = config["category_multipliers_bp"]
    if not isinstance(mults, dict) or not all(
        isinstance(k, str) and isinstance(v, int) and v > 0 for k, v in mults.items()
    ):
        raise RateCardError("bad_multiplier")
    if not isinstance(config["min_total_paise"], int) or config["min_total_paise"] < 0:
        raise RateCardError("bad_min")


async def active_rate_card(session: AsyncSession) -> RateCardVersion:
    row = (
        await session.execute(
            select(RateCardVersion).order_by(RateCardVersion.version.desc()).limit(1)
        )
    ).scalar_one_or_none()
    if row is None:
        raise RateCardError("no_rate_card")
    return row


def pricing_model_for_slots(slot_keys: Sequence[str]) -> str:
    flats = [k for k in slot_keys if k.endswith(FLAT_SUFFIX)]
    if flats and len(flats) != len(slot_keys):
        raise RateCardError("mixed_pricing_models")
    return "flat_weekly" if flats else "cpm"


async def tier_for_targeting(session: AsyncSession, geo_target: dict[str, Any]) -> int:
    tiers = geo_target.get("tiers")
    if tiers:
        return min(int(t) for t in tiers)
    pincodes = geo_target.get("pincodes")
    if pincodes:
        return min([await get_tier(session, p) for p in pincodes])
    return 1  # ALL / district / state reach prices at the top tier


@dataclass(frozen=True, slots=True)
class QuoteLine:
    """One printable invoice line. INVARIANT (money-path review): the lines of
    a Quote sum to EXACTLY its `subtotal_paise` - they flow verbatim through
    Campaign.quote -> AdOrder.quote -> invoice_pdf.render_invoice_pdf, so a
    line that doesn't foot to the invoice's own taxable value is a defective
    tax invoice. Anything that is not itself an amount (the category
    multiplier) belongs in a label, never in a zero-amount row; anything that
    tops the subtotal up (the minimum-order floor) is emitted as the DELTA,
    never as the full floor."""

    label: str
    amount_paise: int


@dataclass(frozen=True, slots=True)
class Quote:
    pricing_model: str
    tier: int
    multiplier_bp: int
    serves_total: int | None
    weeks: int | None
    lines: tuple[QuoteLine, ...]
    subtotal_paise: int
    gst_paise: int
    total_paise: int
    rate_card_version: int


async def quote_campaign(
    session: AsyncSession,
    *,
    slot_keys: Sequence[str],
    geo_target: dict[str, Any],
    categories: Sequence[str],
    flight_start: date,
    flight_end: date,
    serves_total: int | None,
) -> Quote:
    card = await active_rate_card(session)
    config = card.config
    model = pricing_model_for_slots(slot_keys)
    tier = await tier_for_targeting(session, geo_target)
    mults = config["category_multipliers_bp"]
    # Priciest declared category wins (a category absent from the card prices
    # at 1x). Its name is carried alongside so the multiplier can be stated
    # INSIDE the base line's label instead of as a zero-amount line of its own.
    multiplier_bp = BP_ONE
    multiplier_category: str | None = None
    for category in categories:
        category_bp = int(mults.get(category, BP_ONE))
        if multiplier_category is None or category_bp > multiplier_bp:
            multiplier_bp, multiplier_category = category_bp, category
    suffix = (
        f" (x{multiplier_bp / BP_ONE:g} {multiplier_category})" if multiplier_bp != BP_ONE else ""
    )

    lines: list[QuoteLine] = []
    weeks: int | None = None
    if model == "cpm":
        if serves_total is None:
            raise RateCardError("serves_required")
        if serves_total < MIN_CPM_SERVES:
            raise RateCardError("serves_too_small")
        rate = int(config["cpm_paise"][str(tier)])
        subtotal = _ceil_div(serves_total * rate * multiplier_bp, 1000 * BP_ONE)
        lines.append(QuoteLine(f"{serves_total:,} ad views @ CPM T{tier}{suffix}", subtotal))
    else:
        serves_total = None
        days = (flight_end - flight_start).days
        weeks = max(1, _ceil_div(days, 7))
        rate = int(config["flat_weekly_paise"][str(tier)])
        subtotal = _ceil_div(weeks * rate * multiplier_bp, BP_ONE)
        lines.append(QuoteLine(f"Sponsored listing x {weeks} wk @ T{tier}{suffix}", subtotal))
    min_total = int(config["min_total_paise"])
    if subtotal < min_total:
        # the DELTA, not the floor itself - the lines must still foot to the
        # (now floored) subtotal.
        lines.append(QuoteLine("Minimum order top-up", min_total - subtotal))
        subtotal = min_total
    gst = _ceil_div(subtotal * get_settings().gst_rate_bp, BP_ONE)
    if subtotal + gst > MAX_TOTAL_PAISE:
        raise RateCardError("total_too_large")
    return Quote(
        pricing_model=model,
        tier=tier,
        multiplier_bp=multiplier_bp,
        serves_total=serves_total,
        weeks=weeks,
        lines=tuple(lines),
        subtotal_paise=subtotal,
        gst_paise=gst,
        total_paise=subtotal + gst,
        rate_card_version=card.version,
    )
