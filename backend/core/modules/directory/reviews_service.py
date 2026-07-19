"""Reviews engine service (D18.A). Target validation + aggregates live here;
the router maps errors to HTTP statuses."""

import uuid
from decimal import Decimal

from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from modules.directory.catalog_models import Product
from modules.directory.models import Business
from modules.directory.reviews_models import RatingAggregate, Review
from shared.i18n import Translated
from shared.pagination import DEFAULT_PAGE_SIZE, Page, paginate


class ReviewsError(Exception):
    pass


class TargetNotFoundError(ReviewsError):
    pass


class ReviewExistsError(ReviewsError):
    pass


class ReviewDecisionConflictError(ReviewsError):
    pass


class ReviewNotFoundError(ReviewsError):
    pass


async def _target_exists(session: AsyncSession, target_type: str, target_id: uuid.UUID) -> bool:
    if target_type in ("business", "vendor"):
        query = select(Business.id).where(Business.id == target_id, Business.status == "active")
        if target_type == "vendor":
            query = query.where(Business.type == "vendor")
        return (await session.scalar(query)) is not None
    query = select(Product.id).where(
        Product.id == target_id,
        Product.status == "active",
        Product.moderation_status == "approved",
    )
    return (await session.scalar(query)) is not None


async def create_review(
    session: AsyncSession,
    *,
    author_user_id: uuid.UUID,
    target_type: str,
    target_id: uuid.UUID,
    rating: int,
    body: dict[str, str] | None,
) -> Review:
    if not await _target_exists(session, target_type, target_id):
        raise TargetNotFoundError(str(target_id))
    review = Review(
        author_user_id=author_user_id,
        target_type=target_type,
        target_id=target_id,
        rating=rating,
        body=Translated.from_dict(body) if body else None,
    )
    sp = await session.begin_nested()
    try:
        session.add(review)
        await session.flush()
    except IntegrityError as exc:
        await sp.rollback()
        raise ReviewExistsError(str(target_id)) from exc
    await sp.commit()
    return review


async def list_public(
    session: AsyncSession,
    *,
    target_type: str,
    target_id: uuid.UUID,
    cursor: str | None = None,
    limit: int = DEFAULT_PAGE_SIZE,
) -> Page[Review]:
    query = select(Review).where(
        Review.target_type == target_type,
        Review.target_id == target_id,
        Review.moderation_status == "approved",
    )
    return await paginate(session, query, cursor=cursor, limit=limit, descending=True)


async def get_summary(
    session: AsyncSession, *, target_type: str, target_id: uuid.UUID
) -> tuple[Decimal | None, int]:
    agg = await session.scalar(
        select(RatingAggregate).where(
            RatingAggregate.target_type == target_type,
            RatingAggregate.target_id == target_id,
        )
    )
    if agg is None:
        return None, 0
    return agg.rating_avg, agg.rating_count


async def recompute_aggregate(
    session: AsyncSession, *, target_type: str, target_id: uuid.UUID
) -> None:
    avg, count = (
        await session.execute(
            select(func.avg(Review.rating), func.count()).where(
                Review.target_type == target_type,
                Review.target_id == target_id,
                Review.moderation_status == "approved",
            )
        )
    ).one()
    agg = await session.scalar(
        select(RatingAggregate).where(
            RatingAggregate.target_type == target_type,
            RatingAggregate.target_id == target_id,
        )
    )
    if not count:
        if agg is not None:
            await session.delete(agg)
        await session.flush()
        return
    rounded = Decimal(avg).quantize(Decimal("0.01"))
    if agg is None:
        session.add(
            RatingAggregate(
                target_type=target_type,
                target_id=target_id,
                rating_avg=rounded,
                rating_count=int(count),
            )
        )
    else:
        agg.rating_avg = rounded
        agg.rating_count = int(count)
    await session.flush()


async def list_for_moderation(
    session: AsyncSession, *, status: str, cursor: str | None = None, limit: int = DEFAULT_PAGE_SIZE
) -> Page[Review]:
    query = select(Review).where(Review.moderation_status == status)
    return await paginate(session, query, cursor=cursor, limit=limit)


async def moderate(session: AsyncSession, *, review_id: uuid.UUID, approve: bool) -> Review:
    review = await session.scalar(select(Review).where(Review.id == review_id))
    if review is None:
        raise ReviewNotFoundError(str(review_id))
    if review.moderation_status != "pending":
        raise ReviewDecisionConflictError(review.moderation_status)
    review.moderation_status = "approved" if approve else "rejected"
    await session.flush()
    return review
