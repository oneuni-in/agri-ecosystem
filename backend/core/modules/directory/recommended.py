"""M3.C: the "Recommended" rail ranking - ORGANIC ONLY.

This function is the single source of the Recommended label (the storefront
renders the label exclusively from milk-home's `recommended` field, which
only this fn populates). Inputs are trust + service-quality signals:
verification, approved-review ratings, lead first-response time, coverage
freshness. Paid signals - subscription_tier, ad campaigns, budgets - MUST
NEVER enter this scoring: paid can never buy the label (spec M3.C;
test_milk_home_recommended.py::test_paid_signals_never_enter_ranking)."""

import uuid
from collections.abc import Sequence
from datetime import UTC, datetime, timedelta
from typing import TYPE_CHECKING

from sqlalchemy import func, select, text
from sqlalchemy.ext.asyncio import AsyncSession

from modules.directory.models import BusinessCoverage
from modules.directory.reviews_models import RatingAggregate

if TYPE_CHECKING:
    from modules.directory.milk_home import MilkCard

RECOMMENDED_LIMIT = 3
MIN_SCORE = 3.0  # verified floor - a no-signal unverified card never rails
_VERIFIED_POINTS = 3.0
_FAST_RESPONSE_S = 4 * 3600  # first response under 4h -> +2.0
_OK_RESPONSE_S = 24 * 3600  # under 24h -> +1.0
_FRESH_COVERAGE = timedelta(days=30)  # coverage touched recently -> +1.0

# Batched flavour of leads_service._STATS_SQL (same lateral join, grouped
# per business; avg() ignores never-responded rows via the fr.first_at NULL).
_RESPONSE_SQL = text(
    """
    SELECT i.business_id,
           CAST(avg(EXTRACT(EPOCH FROM fr.first_at - i.created_at)) AS BIGINT)
               AS avg_response_seconds
    FROM leads.inquiries i
    LEFT JOIN LATERAL (
        SELECT min(r.created_at) AS first_at
        FROM leads.responses r WHERE r.inquiry_id = i.id
    ) fr ON true
    WHERE i.business_id = ANY(:ids)
    GROUP BY i.business_id
    """
)


async def rank_recommended(
    session: AsyncSession, cards: Sequence["MilkCard"], *, now: datetime
) -> list[uuid.UUID]:
    """Top-RECOMMENDED_LIMIT business ids among `cards`, best first. Ties keep
    the caller's (organic covers) order - sorted() is stable. Only cards
    clearing MIN_SCORE rail at all."""
    if not cards:
        return []
    ids = [c.id for c in cards]

    ratings = {
        row.target_id: (float(row.rating_avg), row.rating_count)
        for row in await session.scalars(
            select(RatingAggregate).where(
                RatingAggregate.target_type == "business",
                RatingAggregate.target_id.in_(ids),
            )
        )
    }
    response: dict[uuid.UUID, int] = {
        m["business_id"]: m["avg_response_seconds"]
        for m in (r._mapping for r in await session.execute(_RESPONSE_SQL, {"ids": ids}))
        if m["avg_response_seconds"] is not None
    }
    freshness: dict[uuid.UUID, datetime] = {
        business_id: latest
        for business_id, latest in (
            await session.execute(
                select(BusinessCoverage.business_id, func.max(BusinessCoverage.updated_at))
                .where(BusinessCoverage.business_id.in_(ids))
                .group_by(BusinessCoverage.business_id)
            )
        ).all()
    }

    def score(card: "MilkCard") -> float:
        s = _VERIFIED_POINTS if card.verification_status == "verified" else 0.0
        rated = ratings.get(card.id)
        if rated is not None:
            avg, count = rated
            s += avg * min(count, 5) / 5
        avg_seconds = response.get(card.id)
        if avg_seconds is not None:
            if avg_seconds < _FAST_RESPONSE_S:
                s += 2.0
            elif avg_seconds < _OK_RESPONSE_S:
                s += 1.0
        latest = freshness.get(card.id)
        if latest is not None:
            if latest.tzinfo is None:
                latest = latest.replace(tzinfo=UTC)
            if (now - latest) <= _FRESH_COVERAGE:
                s += 1.0
        return s

    scored = [(card, score(card)) for card in cards]
    ranked = sorted(
        (entry for entry in scored if entry[1] >= MIN_SCORE),
        key=lambda entry: -entry[1],
    )
    return [card.id for card, _ in ranked[:RECOMMENDED_LIMIT]]
