"""Reviews API request/response schemas (D18.A)."""

import uuid
from datetime import datetime
from decimal import Decimal
from typing import Literal

from pydantic import BaseModel, Field

from modules.directory.reviews_models import Review

ReviewTargetType = Literal["business", "product", "vendor"]


class ReviewCreateIn(BaseModel):
    target_type: ReviewTargetType
    target_id: uuid.UUID
    rating: int = Field(ge=1, le=5)
    body: dict[str, str] | None = None


class ReviewOut(BaseModel):
    id: uuid.UUID
    author_user_id: uuid.UUID
    target_type: str
    target_id: uuid.UUID
    rating: int
    body: dict[str, str] | None
    moderation_status: str
    created_at: datetime


class ReviewPageOut(BaseModel):
    items: list[ReviewOut]
    next_cursor: str | None


class RatingSummaryOut(BaseModel):
    target_type: str
    target_id: uuid.UUID
    rating_avg: Decimal | None
    rating_count: int


class AdminReviewPageOut(BaseModel):
    items: list[ReviewOut]
    next_cursor: str | None


def review_out(review: Review) -> ReviewOut:
    """Shared serializer: reviews_router (public) and reviews_admin_router
    (moderation) both need the identical shape."""
    return ReviewOut(
        id=review.id,
        author_user_id=review.author_user_id,
        target_type=review.target_type,
        target_id=review.target_id,
        rating=review.rating,
        body=review.body.to_dict() if review.body else None,
        moderation_status=review.moderation_status,
        created_at=review.created_at,
    )
