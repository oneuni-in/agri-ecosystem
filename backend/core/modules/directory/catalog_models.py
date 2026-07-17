"""Catalog ORM models (D17) - mirrors migration 0018 exactly. Hosted in the
directory module: product writes must IDOR-check business ownership, and the
module-independence contract (import-linter) forbids a separate catalog
module from reading directory tables. URL namespace is /catalog/* so the
Stage-B extraction never breaks public URLs."""

import uuid
from typing import Any

from sqlalchemy import ForeignKey, Index, Integer, Text, UniqueConstraint
from sqlalchemy.dialects import postgresql
from sqlalchemy.orm import Mapped, mapped_column

from shared.db import Base, SoftDeleteMixin, TimestampMixin, UGCMixin, UUIDv7PKMixin
from shared.i18n import Translated, TranslatedString
from shared.slugs import ImmutableSlugMixin

vertical_status_enum = postgresql.ENUM(
    "active", "hidden", name="vertical_status", schema="directory", create_type=False
)
product_status_enum = postgresql.ENUM(
    "active", "archived", name="product_status", schema="directory", create_type=False
)


class Vertical(UUIDv7PKMixin, TimestampMixin, Base):
    __tablename__ = "vertical_registry"
    __table_args__ = {"schema": "directory"}

    slug: Mapped[str] = mapped_column(Text, nullable=False, unique=True)
    name: Mapped[Translated] = mapped_column(TranslatedString, nullable=False)
    engines_enabled: Mapped[dict[str, Any]] = mapped_column(
        postgresql.JSONB, nullable=False, server_default="{}"
    )
    nav_placement: Mapped[dict[str, Any]] = mapped_column(
        postgresql.JSONB, nullable=False, server_default="{}"
    )
    status: Mapped[str] = mapped_column(
        vertical_status_enum, nullable=False, server_default="active"
    )


class SpecSchema(UUIDv7PKMixin, TimestampMixin, Base):
    """Append-only schema versions (UPDATE/DELETE revoked from app_rt in
    0018): a published version is pinned by products - publish N+1 to change."""

    __tablename__ = "spec_schemas"
    __table_args__ = (
        UniqueConstraint("vertical_slug", "version", name="uq_spec_schemas_vertical_slug_version"),
        {"schema": "directory"},
    )

    # no separate index: the composite unique constraint above already puts
    # vertical_slug as its leading column, covering vertical_slug lookups.
    vertical_slug: Mapped[str] = mapped_column(
        Text, ForeignKey("directory.vertical_registry.slug"), nullable=False
    )
    version: Mapped[int] = mapped_column(Integer, nullable=False)
    fields: Mapped[list[dict[str, Any]]] = mapped_column(postgresql.JSONB, nullable=False)


class Product(UUIDv7PKMixin, TimestampMixin, SoftDeleteMixin, ImmutableSlugMixin, UGCMixin, Base):
    __tablename__ = "products"
    __table_args__ = (
        Index("ix_directory_products_moderation_status_id", "moderation_status", "id"),
        {"schema": "directory"},
    )

    business_id: Mapped[uuid.UUID] = mapped_column(
        postgresql.UUID(as_uuid=True),
        ForeignKey("directory.businesses.id"),
        nullable=False,
        index=True,
    )
    vertical_slug: Mapped[str] = mapped_column(
        Text, ForeignKey("directory.vertical_registry.slug"), nullable=False, index=True
    )
    schema_version: Mapped[int] = mapped_column(Integer, nullable=False)
    name: Mapped[str] = mapped_column(Text, nullable=False)
    specs: Mapped[dict[str, Any]] = mapped_column(
        postgresql.JSONB, nullable=False, server_default="{}"
    )
    price_display: Mapped[str | None] = mapped_column(Text, nullable=True)
    media_keys: Mapped[list[str]] = mapped_column(
        postgresql.JSONB, nullable=False, server_default="[]"
    )
    status: Mapped[str] = mapped_column(
        product_status_enum, nullable=False, server_default="active"
    )
