"""Reviews API (D18.A). POST is login-gated (spam defence); reads are public
(keyset + rate limit are the scraping defence). Never log bodies - review
text is user content."""

import uuid
from typing import Annotated

from fastapi import Depends, HTTPException, Query, Request
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from modules.directory import reviews_service
from modules.directory.catalog_models import Product
from modules.directory.models import Business
from modules.directory.reviews_models import Review
from modules.directory.reviews_schemas import (
    MyReviewOut,
    MyReviewPageOut,
    RatingSummaryOut,
    ReplyCreateIn,
    ReplyOut,
    ReviewCreateIn,
    ReviewOut,
    ReviewPageOut,
    ReviewTargetType,
)
from modules.directory.reviews_schemas import reply_out as _reply_out
from modules.directory.reviews_schemas import review_out as _review_out
from modules.directory.service import BusinessNotFoundError
from shared.db import get_session
from shared.pagination import DEFAULT_PAGE_SIZE, InvalidCursorError
from shared.security import SecureRouter

router = SecureRouter(prefix="/reviews", tags=["reviews"])

SessionDep = Annotated[AsyncSession, Depends(get_session)]
LimitQuery = Annotated[int, Query(ge=1, le=100)]


async def _target_names(
    session: AsyncSession, reviews: list[Review]
) -> dict[tuple[str, uuid.UUID], tuple[str, str]]:
    """Name + slug for each review target, in two queries rather than N.

    `business` and `vendor` both point at directory.businesses (the same
    assumption list_owner_reviews makes); `product` points at
    directory.products. A target that no longer resolves - deleted, archived,
    hidden - is simply absent from the map, and the row renders nameless
    rather than with a stale name.
    """
    resolved: dict[tuple[str, uuid.UUID], tuple[str, str]] = {}
    business_ids = {r.target_id for r in reviews if r.target_type in ("business", "vendor")}
    product_ids = {r.target_id for r in reviews if r.target_type == "product"}

    if business_ids:
        rows = await session.execute(
            select(Business.id, Business.name, Business.slug).where(Business.id.in_(business_ids))
        )
        found = {row.id: (row.name, row.slug) for row in rows}
        for review in reviews:
            if review.target_type in ("business", "vendor") and review.target_id in found:
                resolved[(review.target_type, review.target_id)] = found[review.target_id]

    if product_ids:
        rows = await session.execute(
            select(Product.id, Product.name, Product.slug).where(Product.id.in_(product_ids))
        )
        for row in rows:
            resolved[("product", row.id)] = (row.name, row.slug)

    return resolved


def _principal_user_id(request: Request) -> uuid.UUID:
    principal = request.state.principal  # set by require_auth (shared.security)
    user_id = principal.user_id
    assert isinstance(user_id, uuid.UUID)
    return user_id


@router.post("", status_code=201)
async def create_review(request: Request, body: ReviewCreateIn, session: SessionDep) -> ReviewOut:
    try:
        review = await reviews_service.create_review(
            session,
            author_user_id=_principal_user_id(request),
            target_type=body.target_type,
            target_id=body.target_id,
            rating=body.rating,
            body=body.body,
        )
    except reviews_service.TargetNotFoundError as exc:
        raise HTTPException(status_code=404, detail="target not found") from exc
    except reviews_service.ReviewExistsError as exc:
        raise HTTPException(status_code=409, detail="review_exists") from exc
    except ValueError as exc:  # Translated.from_dict rejects unknown locales
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    await session.commit()
    return _review_out(review)


@router.get("", public=True)
async def list_reviews(
    session: SessionDep,
    target_type: ReviewTargetType,
    target_id: uuid.UUID,
    cursor: str | None = None,
    limit: LimitQuery = DEFAULT_PAGE_SIZE,
) -> ReviewPageOut:
    try:
        page = await reviews_service.list_public(
            session, target_type=target_type, target_id=target_id, cursor=cursor, limit=limit
        )
    except InvalidCursorError as exc:
        raise HTTPException(status_code=400, detail="invalid cursor") from exc
    # attach the business's APPROVED reply per review (D18 approved-only)
    replies = await reviews_service.replies_for_reviews(
        session, review_ids=[r.id for r in page.items], approved_only=True
    )
    return ReviewPageOut(
        items=[_review_out(r, replies.get(r.id)) for r in page.items],
        next_cursor=page.next_cursor,
    )


@router.get("/mine")
async def list_my_reviews(
    request: Request,
    session: SessionDep,
    cursor: str | None = None,
    limit: LimitQuery = DEFAULT_PAGE_SIZE,
) -> MyReviewPageOut:
    """Reviews the CALLER wrote, any status, newest first (AG-U5 P4).

    Not to be confused with /reviews/owner, which is the mirror image:
    approved reviews written ABOUT a business you own. This one is what you
    said; that one is what was said about you.

    Pending rows are included on purpose - "where did my review go?" is the
    question a moderation queue creates, and this is the only surface that
    can answer it. Nothing here is another user's: the query is scoped to the
    principal and takes no author parameter.
    """
    try:
        page = await reviews_service.list_mine(
            session, author_user_id=_principal_user_id(request), cursor=cursor, limit=limit
        )
    except InvalidCursorError as exc:
        raise HTTPException(status_code=400, detail="invalid cursor") from exc
    names = await _target_names(session, page.items)
    return MyReviewPageOut(
        items=[
            MyReviewOut(
                **_review_out(review).model_dump(),
                target_name=names.get((review.target_type, review.target_id), (None, None))[0],
                target_slug=names.get((review.target_type, review.target_id), (None, None))[1],
            )
            for review in page.items
        ],
        next_cursor=page.next_cursor,
    )


@router.get("/owner")
async def list_owner_reviews(
    request: Request,
    session: SessionDep,
    business_id: uuid.UUID,
    cursor: str | None = None,
    limit: LimitQuery = DEFAULT_PAGE_SIZE,
) -> ReviewPageOut:
    """Approved reviews about the owner's business, each with the owner's own
    reply attached (ANY status — the owner sees their pending reply). Not
    theirs → 404."""
    try:
        page = await reviews_service.list_owner_reviews(
            session,
            owner_user_id=_principal_user_id(request),
            business_id=business_id,
            cursor=cursor,
            limit=limit,
        )
    except BusinessNotFoundError as exc:
        raise HTTPException(status_code=404, detail="Business not found") from exc
    except InvalidCursorError as exc:
        raise HTTPException(status_code=400, detail="invalid cursor") from exc
    replies = await reviews_service.replies_for_reviews(
        session, review_ids=[r.id for r in page.items], approved_only=False
    )
    return ReviewPageOut(
        items=[_review_out(r, replies.get(r.id)) for r in page.items],
        next_cursor=page.next_cursor,
    )


@router.post("/{review_id}/reply", status_code=201)
async def create_reply(
    request: Request, review_id: uuid.UUID, body: ReplyCreateIn, session: SessionDep
) -> ReplyOut:
    """Owner posts their response — lands `pending`, invisible publicly until
    a moderator approves it. Not-yours / product-target review → 404."""
    try:
        reply = await reviews_service.create_reply(
            session,
            owner_user_id=_principal_user_id(request),
            review_id=review_id,
            body=body.body,
        )
    except reviews_service.ReviewNotFoundError as exc:
        raise HTTPException(status_code=404, detail="review not found") from exc
    except reviews_service.ReviewNotApprovedError as exc:
        raise HTTPException(status_code=409, detail="review_not_approved") from exc
    except reviews_service.ReplyExistsError as exc:
        raise HTTPException(status_code=409, detail="reply_exists") from exc
    except ValueError as exc:  # Translated.from_dict rejects unknown locales
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    out = _reply_out(reply)
    await session.commit()
    return out


@router.delete("/replies/{reply_id}", status_code=204)
async def delete_reply(request: Request, reply_id: uuid.UUID, session: SessionDep) -> None:
    """Owner removes their reply — soft delete. Not-yours → 404."""
    try:
        await reviews_service.delete_reply(
            session, owner_user_id=_principal_user_id(request), reply_id=reply_id
        )
    except reviews_service.ReplyNotFoundError as exc:
        raise HTTPException(status_code=404, detail="reply not found") from exc
    await session.commit()


@router.get("/summary", public=True)
async def rating_summary(
    session: SessionDep, target_type: ReviewTargetType, target_id: uuid.UUID
) -> RatingSummaryOut:
    avg, count = await reviews_service.get_summary(
        session, target_type=target_type, target_id=target_id
    )
    return RatingSummaryOut(
        target_type=target_type, target_id=target_id, rating_avg=avg, rating_count=count
    )
