"""Coins user-facing API (D13). All routes are private + rate-limited.
Never log request bodies or query strings - this module handles balance data.

Principal resolution reads request.state.principal directly (populated by
require_auth via shared.security) instead of importing modules.identity -
the independence contract forbids modules.coins -> modules.identity."""

import uuid
from typing import Annotated

from fastapi import Depends, Query, Request
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from modules.coins import referrals, service
from modules.coins.models import ReferralCode, Rule
from modules.coins.reason_codes import label_key
from modules.coins.schemas import (
    BalanceOut,
    HistoryItemOut,
    HistoryOut,
    ReferralCodeOut,
    ReferrerOut,
    RuleOut,
    RulesOut,
)
from shared.db import get_session
from shared.lookups import resolve_handle
from shared.pagination import DEFAULT_PAGE_SIZE
from shared.security import SecureRouter

router = SecureRouter(prefix="/coins", tags=["coins"])

SessionDep = Annotated[AsyncSession, Depends(get_session)]


def _principal_user_id(request: Request) -> uuid.UUID:
    principal = request.state.principal  # set by require_auth (shared.security)
    user_id = principal.user_id
    assert isinstance(user_id, uuid.UUID)  # narrow Starlette state's Any for mypy
    return user_id


# public=True: an earn rule's amount is a published fact about the product,
# not user data — the home's "Earn AgriCoins" cards render for logged-out
# visitors, so gating this would leave them showing a coin glyph where a
# number belongs (the A-U1 deviation this endpoint exists to close).
# It returns rule codes, amounts and caps. No balance, no identity, no
# reference to the caller at all.
@router.get("/rules", public=True)
async def get_rules(session: SessionDep) -> RulesOut:
    rows = (
        await session.execute(select(Rule).where(Rule.active.is_(True)).order_by(Rule.code))
    ).scalars()
    return RulesOut(
        items=[
            RuleOut(
                code=r.code,
                amount=r.amount,
                label_key=label_key(r.code),
                daily_cap=r.daily_cap,
                weekly_cap=r.weekly_cap,
                total_cap=r.total_cap,
            )
            for r in rows
            # Burn/adjust reasons are not earn rules and must never render as
            # something a visitor can do to gain coins.
            if r.amount > 0
        ]
    )


@router.get("/balance")
async def get_balance(request: Request, session: SessionDep) -> BalanceOut:
    user_id = _principal_user_id(request)
    return BalanceOut(balance=await service.balance(session, user_id))


@router.get("/history")
async def get_history(
    request: Request,
    session: SessionDep,
    cursor: str | None = None,
    limit: Annotated[int, Query(ge=1, le=100)] = DEFAULT_PAGE_SIZE,
) -> HistoryOut:
    user_id = _principal_user_id(request)
    page = await service.history(session, user_id, cursor=cursor, limit=limit)
    return HistoryOut(
        items=[
            HistoryItemOut(
                id=e.id,
                delta=e.delta,
                reason_code=e.reason_code,
                reason_label_key=label_key(e.reason_code),
                ref_type=e.ref_type,
                created_at=e.created_at,
            )
            for e in page.items
        ],
        next_cursor=page.next_cursor,
    )


# PRIVATE on purpose, and this is the whole reason the login banner does not
# name the inviter until after the OTP. A public code -> handle route would be
# an enumeration oracle: codes are 8 characters from a 32-character alphabet,
# and anyone could walk them to harvest handles. Behind require_auth (and the
# router's rate limit) the same walk costs a session and a budget.
#
# The handle comes through shared.lookups, never a join: coins may not read
# identity.users (the independence contract), and the seam hands back the
# handle alone.
@router.get("/referral/resolve")
async def resolve_referrer(
    request: Request,
    session: SessionDep,
    code: Annotated[str, Query(min_length=1, max_length=16)],
) -> ReferrerOut:
    user_id = _principal_user_id(request)
    owner_id = await session.scalar(select(ReferralCode.user_id).where(ReferralCode.code == code))
    # Your own code names nobody: a self-referral is not attributable anyway
    # (referrals.attribute refuses it), so the banner must not imply it is.
    if owner_id is None or owner_id == user_id:
        return ReferrerOut(handle=None)
    return ReferrerOut(handle=await resolve_handle(session, owner_id))


@router.get("/referral-code")
async def get_referral_code(request: Request, session: SessionDep) -> ReferralCodeOut:
    user_id = _principal_user_id(request)
    return ReferralCodeOut(code=await referrals.get_or_create_code(session, user_id))
