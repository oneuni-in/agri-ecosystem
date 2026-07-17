"""Catalog API request/response schemas (D17). media_url() is the ONE place
that turns a stored media_keys entry into an absolute URL - media_keys
themselves are never exposed on the wire, only these built URLs."""

import uuid
from datetime import datetime
from typing import Any

from pydantic import BaseModel, Field

from settings import get_settings


def media_url(key: str) -> str:
    return f"{get_settings().media_public_base_url}/{key}"


class ProductCreateIn(BaseModel):
    vertical_slug: str
    name: str = Field(min_length=1, max_length=200)
    specs: dict[str, object]
    price_display: str | None = Field(default=None, max_length=100)


class ProductPatchIn(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=200)
    specs: dict[str, object] | None = None
    price_display: str | None = Field(default=None, max_length=100)
    status: str | None = None


class ProductOut(BaseModel):
    id: uuid.UUID
    business_id: uuid.UUID
    vertical_slug: str
    schema_version: int
    name: str
    slug: str
    specs: dict[str, Any]
    price_display: str | None
    status: str
    moderation_status: str
    images: list[str]
    created_at: datetime


class ProductPageOut(BaseModel):
    items: list[ProductOut]
    next_cursor: str | None


class PublicProductOut(BaseModel):
    id: uuid.UUID
    business_id: uuid.UUID
    business_name: str
    business_slug: str
    vertical_slug: str
    schema_version: int
    name: str
    slug: str
    specs: dict[str, Any]
    price_display: str | None
    status: str
    images: list[str]
    created_at: datetime


class PublicProductPageOut(BaseModel):
    items: list[PublicProductOut]
    next_cursor: str | None


class ProductDetailOut(BaseModel):
    product: PublicProductOut
    schema_fields: list[dict[str, Any]]


class VerticalOut(BaseModel):
    slug: str
    name: dict[str, str]
    engines_enabled: dict[str, Any]
    nav_placement: dict[str, Any]


class VerticalPageOut(BaseModel):
    items: list[VerticalOut]
    next_cursor: str | None


# --- admin: schema versions (D17 Task 7) ----------------------------------


class SchemaVersionOut(BaseModel):
    vertical_slug: str
    version: int
    fields: list[dict[str, Any]]
    created_at: datetime


class SchemaVersionListOut(BaseModel):
    items: list[SchemaVersionOut]


class SchemaCreateIn(BaseModel):
    fields: list[dict[str, Any]]


class ProductRejectIn(BaseModel):
    # admin rejection note is always required (distinct from claims' RejectIn
    # which allows a shorter/optional note) - min_length=1 per Task 7 brief.
    note: str = Field(min_length=1, max_length=1000)
