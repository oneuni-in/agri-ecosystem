"""Public response shapes for the coins API. Integer coins only; no money
fields ever appear here."""

import uuid
from datetime import datetime

from pydantic import BaseModel


class BalanceOut(BaseModel):
    balance: int


class HistoryItemOut(BaseModel):
    id: uuid.UUID
    delta: int
    reason_code: str
    reason_label_key: str
    ref_type: str
    created_at: datetime


class HistoryOut(BaseModel):
    items: list[HistoryItemOut]
    next_cursor: str | None = None


class ReferralCodeOut(BaseModel):
    code: str
