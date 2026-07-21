"""Tier vocabulary (D20): free / growth / pro, where free is the absence of
a subscription row. Prices are PLACEHOLDERS until Pricing v1 - that spec
edits THIS file and the razorpay_plan_id_* settings, nothing else."""

from dataclasses import dataclass

from settings import Settings


@dataclass(frozen=True, slots=True)
class Tier:
    key: str
    display_name: str
    monthly_price_paise: int  # placeholder until Pricing v1
    plan_id_setting: str


TIERS: dict[str, Tier] = {
    "growth": Tier("growth", "Growth", 49900, "razorpay_plan_id_growth"),
    "pro": Tier("pro", "Pro", 149900, "razorpay_plan_id_pro"),
}


def plan_id_for(tier_key: str, settings: Settings) -> str:
    """Empty string while unconfigured (pre-KYC) - callers answer 503."""
    return str(getattr(settings, TIERS[tier_key].plan_id_setting))
