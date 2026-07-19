"""Leads API request/response schemas (D18.B)."""

import uuid
from datetime import datetime
from decimal import Decimal
from typing import Any, Literal

from pydantic import BaseModel, Field

from modules.directory.schemas import PINCODE_PATTERN, SLUG_PATTERN

InquiryType = Literal["contact", "milk_subscription"]
InquiryStatus = Literal["new", "responded", "closed"]


class ContactPayloadIn(BaseModel):
    message: str = Field(min_length=1, max_length=2000)


class MilkSubscriptionPayloadIn(BaseModel):
    qty_liters: Decimal = Field(gt=0, le=100)
    milk_type: Literal["cow", "buffalo", "goat", "mixed"]
    schedule: Literal["daily", "alternate_days", "weekly"]


class InquiryCreateIn(BaseModel):
    type: InquiryType
    business_id: uuid.UUID | None = None
    pincode: str = Field(pattern=PINCODE_PATTERN)
    category: str | None = Field(default=None, pattern=SLUG_PATTERN)
    payload: dict[str, Any]


class InquiryOut(BaseModel):
    id: uuid.UUID
    type: str
    business_id: uuid.UUID
    business_name: str
    status: str
    pincode: str
    category: str | None
    payload: dict[str, Any]
    created_at: datetime


class ResponseCreateIn(BaseModel):
    body: str = Field(min_length=1, max_length=2000)


class ResponseOut(BaseModel):
    id: uuid.UUID
    inquiry_id: uuid.UUID
    business_user_id: uuid.UUID
    body: str
    created_at: datetime


class InboxInquiryOut(BaseModel):
    id: uuid.UUID
    type: str
    status: str
    pincode: str
    category: str | None
    payload: dict[str, Any]
    from_user_id: uuid.UUID | None
    created_at: datetime


class InboxPageOut(BaseModel):
    items: list[InboxInquiryOut]
    next_cursor: str | None


class MyInquiryOut(BaseModel):
    id: uuid.UUID
    type: str
    business_id: uuid.UUID
    status: str
    payload: dict[str, Any]
    responses: list[ResponseOut]
    created_at: datetime


class MyInquiryPageOut(BaseModel):
    items: list[MyInquiryOut]
    next_cursor: str | None


class InboxStatsOut(BaseModel):
    total: int
    responded: int
    avg_response_seconds: int | None


class ContactRevealOut(BaseModel):
    branch_id: uuid.UUID
    phone: str | None
    whatsapp: str | None
