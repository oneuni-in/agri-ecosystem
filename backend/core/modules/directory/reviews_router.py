"""Reviews API (D18.A). POST is login-gated (spam defence); reads are public
(keyset + rate limit are the scraping defence). Never log bodies - review
text is user content."""

import uuid
from typing import Annotated

from fastapi import Depends, HTTPException, Query, Request
from sqlalchemy.ext.asyncio import AsyncSession

from modules.directory import reviews_service
from modules.directory.reviews_schemas import (
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
