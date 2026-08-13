"""Reviews API request/response schemas (D18.A)."""

import uuid
from datetime import datetime
from decimal import Decimal
from typing import Literal

from pydantic import BaseModel, Field

from modules.directory.reviews_models import Review, ReviewReply

ReviewTargetType = Literal["business", "product", "vendor"]


class ReplyOut(BaseModel):
    id: uuid.UUID
    review_id: uuid.UUID
    business_id: uuid.UUID
    body: dict[str, str]
    moderation_status: str
    created_at: datetime


class ReplyCreateIn(BaseModel):
    body: dict[str, str] = Field(min_length=1)


def reply_out(reply: ReviewReply) -> ReplyOut:
    return ReplyOut(
        id=reply.id,
        review_id=reply.review_id,
        business_id=reply.business_id,
        body=reply.body.to_dict(),
        moderation_status=reply.moderation_status,
        created_at=reply.created_at,
    )


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
    # U2 Group C: the business's approved response, when one exists. Public
    # reads attach approved-only; the owner surface attaches its own reply
    # (any status). Absent → null, never a stub.
    reply: ReplyOut | None = None


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


class AdminReplyPageOut(BaseModel):
    items: list[ReplyOut]
    next_cursor: str | None


def review_out(review: Review, reply: ReviewReply | None = None) -> ReviewOut:
    """Shared serializer: reviews_router (public) and reviews_admin_router
    (moderation) both need the identical shape. `reply` is attached by the
    public list + owner surface; the admin queue passes none."""
    return ReviewOut(
        id=review.id,
        author_user_id=review.author_user_id,
        target_type=review.target_type,
        target_id=review.target_id,
        rating=review.rating,
        body=review.body.to_dict() if review.body else None,
        moderation_status=review.moderation_status,
        created_at=review.created_at,
        reply=reply_out(reply) if reply is not None else None,
    )
