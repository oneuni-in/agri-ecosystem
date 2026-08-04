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
    if (
        len(parts) != 4
        or parts != sorted(parts, reverse=True)
        or not all(0 < p < 100 for p in parts)
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
            "population+users" if boosted or row.method == "population+users" else "population"
        )
        pop_tier = _tier_for(row.population, thresholds)
        target = (
            max(1, pop_tier - settings.pincode_tier_user_promotion_step) if boosted else pop_tier
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
