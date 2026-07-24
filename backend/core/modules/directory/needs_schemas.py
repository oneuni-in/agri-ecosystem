"""Post-my-need API schemas (D25)."""

import uuid
from datetime import datetime
from decimal import Decimal
from typing import Any, Literal

from pydantic import BaseModel, Field

from modules.directory.leads_schemas import ResponseOut
from modules.directory.schemas import PINCODE_PATTERN

NeedStatus = Literal["open", "fulfilled", "closed"]


class NeedPayloadIn(BaseModel):
    qty_liters: Decimal = Field(gt=0, le=100)
    milk_type: Literal["cow", "buffalo", "goat", "mixed"]
    schedule: Literal["daily", "alternate_days", "weekly"]
    delivery_time: Literal["morning", "evening", "any"] = "any"
    note: str | None = Field(default=None, max_length=500)


class NeedCreateIn(BaseModel):
    pincode: str = Field(pattern=PINCODE_PATTERN)
    payload: dict[str, Any]


class NeedOut(BaseModel):
    id: uuid.UUID
    pincode: str
    payload: dict[str, Any]
    status: str
    accepted_business_id: uuid.UUID | None
    has_voice: bool
    routed_count: int
    created_at: datetime


class NeedRouteOut(BaseModel):
    inquiry_id: uuid.UUID
    business_id: uuid.UUID
    business_name: str
    status: str
    responses: list[ResponseOut]


class MyNeedOut(NeedOut):
    routes: list[NeedRouteOut]


class MyNeedPageOut(BaseModel):
    items: list[MyNeedOut]
    next_cursor: str | None


class FulfillIn(BaseModel):
    business_id: uuid.UUID | None = None
