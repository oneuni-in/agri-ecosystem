"""Reviews engine ORM (D18.A): polymorphic reviews + cached rating aggregates.

target_id is a plain UUID (never an FK): 'business'/'vendor' point at
directory.businesses, 'product' at directory.products - validated in
reviews_service, matching the repo-wide no-cross-FK convention.
"""

import uuid
from decimal import Decimal

from sqlalchemy import CheckConstraint, Index, Integer, Numeric, SmallInteger, UniqueConstraint
from sqlalchemy.dialects import postgresql
from sqlalchemy.orm import Mapped, mapped_column

from shared.db import Base, TimestampMixin, UGCMixin, UUIDv7PKMixin
from shared.i18n import Translated, TranslatedString

review_target_enum = postgresql.ENUM(
    "business",
    "product",
    "vendor",
    name="review_target_type",
    schema="directory",
    create_type=False,
)


class Review(UUIDv7PKMixin, TimestampMixin, UGCMixin, Base):
    __tablename__ = "reviews"
    __table_args__ = (
        # one review per user per target (D18 non-negotiable 1)
        UniqueConstraint(
            "author_user_id",
            "target_type",
            "target_id",
            name="uq_directory_reviews_one_per_target",
        ),
        CheckConstraint("rating BETWEEN 1 AND 5", name="rating_1_5"),
        Index(
            "ix_directory_reviews_target_status_id",
            "target_type",
            "target_id",
            "moderation_status",
            "id",
        ),
        Index("ix_directory_reviews_moderation_status_id", "moderation_status", "id"),
        {"schema": "directory"},
    )

    author_user_id: Mapped[uuid.UUID] = mapped_column(
        postgresql.UUID(as_uuid=True), nullable=False, index=True
    )
    target_type: Mapped[str] = mapped_column(review_target_enum, nullable=False)
    target_id: Mapped[uuid.UUID] = mapped_column(postgresql.UUID(as_uuid=True), nullable=False)
    rating: Mapped[int] = mapped_column(SmallInteger, nullable=False)
    body: Mapped[Translated | None] = mapped_column(TranslatedString, nullable=True)


class RatingAggregate(UUIDv7PKMixin, TimestampMixin, Base):
    """Cached avg+count per target, recomputed on every moderation decision."""

    __tablename__ = "rating_aggregates"
    __table_args__ = (
        UniqueConstraint("target_type", "target_id", name="uq_directory_rating_aggregates_target"),
        {"schema": "directory"},
    )

    target_type: Mapped[str] = mapped_column(review_target_enum, nullable=False)
    target_id: Mapped[uuid.UUID] = mapped_column(postgresql.UUID(as_uuid=True), nullable=False)
    rating_avg: Mapped[Decimal] = mapped_column(Numeric(3, 2), nullable=False)
    rating_count: Mapped[int] = mapped_column(Integer, nullable=False)
