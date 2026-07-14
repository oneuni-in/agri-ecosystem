"""Coins user-facing API (D13). All routes are private + rate-limited.
Never log request bodies or query strings - this module handles balance data.

Principal resolution reads request.state.principal directly (populated by
require_auth via shared.security) instead of importing modules.identity -
the independence contract forbids modules.coins -> modules.identity."""

import uuid
from typing import Annotated

from fastapi import Depends, Query, Request
from sqlalchemy.ext.asyncio import AsyncSession

from modules.coins import referrals, service
from modules.coins.reason_codes import label_key
from modules.coins.schemas import BalanceOut, HistoryItemOut, HistoryOut, ReferralCodeOut
from shared.db import get_session
from shared.pagination import DEFAULT_PAGE_SIZE
from shared.security import SecureRouter

router = SecureRouter(prefix="/coins", tags=["coins"])

SessionDep = Annotated[AsyncSession, Depends(get_session)]


def _principal_user_id(request: Request) -> uuid.UUID:
    principal = request.state.principal  # set by require_auth (shared.security)
    user_id = principal.user_id
    assert isinstance(user_id, uuid.UUID)  # narrow Starlette state's Any for mypy
    return user_id


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


@router.get("/referral-code")
async def get_referral_code(request: Request, session: SessionDep) -> ReferralCodeOut:
    user_id = _principal_user_id(request)
    return ReferralCodeOut(code=await referrals.get_or_create_code(session, user_id))
