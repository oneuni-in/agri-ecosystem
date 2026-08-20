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


class ReferrerOut(BaseModel):
    """Who a referral code belongs to, for the login done screen.

    The handle and nothing else - no user id, no join date, no counts. `None`
    means "we will not name them": an unknown code, a code belonging to a
    suspended account, or your own code. The caller renders the banner
    without a name rather than with a placeholder."""

    handle: str | None


class RuleOut(BaseModel):
    """One active earn rule, as the earn cards render it.

    `amount` is the REAL configured award, read from coins.rules — never the
    A1 mockup's illustrative figure. A-U1 shipped those cards with a coin
    glyph instead of a number precisely because this read did not exist yet
    ("never invent amounts"); this is the read.
    """

    code: str
    amount: int
    label_key: str
    daily_cap: int | None = None
    weekly_cap: int | None = None
    total_cap: int | None = None


class RulesOut(BaseModel):
    items: list[RuleOut]
