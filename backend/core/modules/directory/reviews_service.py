"""Reviews engine service (D18.A). Target validation + aggregates live here;
the router maps errors to HTTP statuses."""

import uuid
from decimal import Decimal

from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from modules.directory.catalog_models import Product
from modules.directory.models import Business
from modules.directory.reviews_models import RatingAggregate, Review, ReviewReply
from modules.directory.service import BusinessNotFoundError, get_owned_business
from shared.db import soft_delete
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


class ReplyNotFoundError(ReviewsError):
    pass


class ReplyExistsError(ReviewsError):
    pass


class ReviewNotApprovedError(ReviewsError):
    """A reply may only be posted to a publicly-visible (approved) review."""


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
        # FOR UPDATE: serializes concurrent recomputes for the same target
        # (D16 claims.py precedent). The rare concurrent-first-INSERT race
        # (two callers both see agg is None and both try to insert) stays as
        # documented debt - it's caught by the aggregate's unique index, not
        # by this lock, and isn't exercised by any test in this repo.
        select(RatingAggregate)
        .where(
            RatingAggregate.target_type == target_type,
            RatingAggregate.target_id == target_id,
        )
        .with_for_update()
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


# ── review replies (U2 Group C) ──────────────────────────────────────────


async def _owned_business_review(
    session: AsyncSession, *, owner_user_id: uuid.UUID, review_id: uuid.UUID
) -> tuple[Review, uuid.UUID]:
    """Resolve the review AND assert the caller owns the business it targets.

    Missing review, a review that targets a product/another business, and a
    business the caller does not own ALL collapse to ReviewNotFoundError, so
    the router 404s every one (the IDOR contract — a 403 would confirm the
    row exists). Returns (review, business_id)."""
    review = await session.scalar(select(Review).where(Review.id == review_id))
    if review is None or review.target_type not in ("business", "vendor"):
        raise ReviewNotFoundError(str(review_id))
    try:
        # the target_id of a business/vendor review IS a business id
        business = await get_owned_business(session, owner_user_id, review.target_id)
    except BusinessNotFoundError as exc:
        raise ReviewNotFoundError(str(review_id)) from exc
    return review, business.id


async def create_reply(
    session: AsyncSession,
    *,
    owner_user_id: uuid.UUID,
    review_id: uuid.UUID,
    body: dict[str, str],
) -> ReviewReply:
    """Owner posts their official response. Lands `pending` (UGCMixin) —
    invisible publicly until a moderator approves it (D18 rule). Requires the
    review to be approved (you respond to what customers can see) and unreplied."""
    review, business_id = await _owned_business_review(
        session, owner_user_id=owner_user_id, review_id=review_id
    )
    if review.moderation_status != "approved":
        raise ReviewNotApprovedError(str(review_id))
    reply = ReviewReply(
        review_id=review_id,
        business_id=business_id,
        author_user_id=owner_user_id,
        body=Translated.from_dict(body),
    )
    sp = await session.begin_nested()
    try:
        session.add(reply)
        await session.flush()
    except IntegrityError as exc:
        await sp.rollback()
        raise ReplyExistsError(str(review_id)) from exc
    await sp.commit()
    return reply


async def delete_reply(
    session: AsyncSession, *, owner_user_id: uuid.UUID, reply_id: uuid.UUID
) -> ReviewReply:
    """Owner removes their reply — soft-delete (never hard). Not-yours 404s."""
    reply = await session.scalar(select(ReviewReply).where(ReviewReply.id == reply_id))
    if reply is None:
        raise ReplyNotFoundError(str(reply_id))
    try:
        await get_owned_business(session, owner_user_id, reply.business_id)
    except BusinessNotFoundError as exc:
        raise ReplyNotFoundError(str(reply_id)) from exc
    soft_delete(reply)
    await session.flush()
    return reply


async def replies_for_reviews(
    session: AsyncSession, *, review_ids: list[uuid.UUID], approved_only: bool
) -> dict[uuid.UUID, ReviewReply]:
    """Map review_id → its reply. `approved_only` for public reads (D18);
    the owner surface passes False to see its own pending/rejected replies."""
    if not review_ids:
        return {}
    query = select(ReviewReply).where(ReviewReply.review_id.in_(review_ids))
    if approved_only:
        query = query.where(ReviewReply.moderation_status == "approved")
    rows = await session.scalars(query)
    return {r.review_id: r for r in rows}


async def list_owner_reviews(
    session: AsyncSession,
    *,
    owner_user_id: uuid.UUID,
    business_id: uuid.UUID,
    cursor: str | None = None,
    limit: int = DEFAULT_PAGE_SIZE,
) -> Page[Review]:
    """Approved reviews targeting the owner's business (business/vendor
    targets). Owner-gated: get_owned_business raises if not theirs."""
    await get_owned_business(session, owner_user_id, business_id)
    query = select(Review).where(
        Review.target_type.in_(("business", "vendor")),
        Review.target_id == business_id,
        Review.moderation_status == "approved",
    )
    return await paginate(session, query, cursor=cursor, limit=limit, descending=True)


async def list_mine(
    session: AsyncSession,
    *,
    author_user_id: uuid.UUID,
    cursor: str | None = None,
    limit: int = DEFAULT_PAGE_SIZE,
) -> Page[Review]:
    """Every review this person WROTE, newest first, whatever its status.

    Deliberately unfiltered by moderation status, which is the point of the
    endpoint: a review is `pending` on write and therefore absent from the
    public list, so without this an author has no way to see that what they
    wrote exists at all. `author_user_id` is indexed.

    Scoped to the caller by the router - there is no parameter here that
    could ask for somebody else's.
    """
    query = select(Review).where(Review.author_user_id == author_user_id)
    return await paginate(session, query, cursor=cursor, limit=limit, descending=True)


async def list_replies_for_moderation(
    session: AsyncSession, *, status: str, cursor: str | None = None, limit: int = DEFAULT_PAGE_SIZE
) -> Page[ReviewReply]:
    query = select(ReviewReply).where(ReviewReply.moderation_status == status)
    return await paginate(session, query, cursor=cursor, limit=limit)


async def moderate_reply(
    session: AsyncSession, *, reply_id: uuid.UUID, approve: bool
) -> ReviewReply:
    reply = await session.scalar(
        # FOR UPDATE serializes concurrent approve/reject (moderate() precedent)
        select(ReviewReply).where(ReviewReply.id == reply_id).with_for_update()
    )
    if reply is None:
        raise ReplyNotFoundError(str(reply_id))
    if reply.moderation_status != "pending":
        raise ReviewDecisionConflictError(reply.moderation_status)
    reply.moderation_status = "approved" if approve else "rejected"
    await session.flush()
    return reply


async def moderate(session: AsyncSession, *, review_id: uuid.UUID, approve: bool) -> Review:
    review = await session.scalar(
        # FOR UPDATE: serializes concurrent approve/reject decisions on the
        # same review (D16 claims.py _pending_claim_with_business precedent).
        # Without this, two racing decisions can both read "pending" and both
        # succeed - worst case: approve + reject both land, awarding coins
        # and a review_approved notification for a review that ends up
        # rejected.
        select(Review).where(Review.id == review_id).with_for_update()
    )
    if review is None:
        raise ReviewNotFoundError(str(review_id))
    if review.moderation_status != "pending":
        raise ReviewDecisionConflictError(review.moderation_status)
    review.moderation_status = "approved" if approve else "rejected"
    await session.flush()
    return review
