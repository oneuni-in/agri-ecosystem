"""Reviews API request/response schemas (D18.A)."""

import uuid
from datetime import datetime
from decimal import Decimal
from typing import Literal

from pydantic import BaseModel, Field

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
