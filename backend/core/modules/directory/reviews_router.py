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
    ReviewCreateIn,
    ReviewOut,
    ReviewPageOut,
    ReviewTargetType,
)
from modules.directory.reviews_schemas import review_out as _review_out
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
    return ReviewPageOut(items=[_review_out(r) for r in page.items], next_cursor=page.next_cursor)


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
