# backend/core/modules/billing/admin_router.py
"""Admin billing actions (D20): super_admin only, flag-gated like every
billing surface, every state change audited (shared.audit). Choreography per
decision (D16 precedent): decide -> audit (same tx) -> capture event payload
-> commit -> best-effort publish."""

import uuid
from datetime import UTC, datetime
from typing import Annotated

from fastapi import Depends, HTTPException, Request
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from modules.billing import razorpay_client
from modules.billing.models import Subscription
from modules.billing.router import _principal_user_id, _require_flag
from modules.billing.schemas import SubscriptionOut, subscription_out
from modules.billing.service import apply_subscription_cancelled, publish_pending
from shared.audit import audit
from shared.db import get_session
from shared.pagination import InvalidCursorError, paginate
from shared.security import SecureRouter

admin_router = SecureRouter(prefix="/billing/admin", tags=["billing-admin"])
SessionDep = Annotated[AsyncSession, Depends(get_session)]

SUPER_ADMIN = "super_admin"


def _require_role(request: Request, *allowed: str) -> uuid.UUID:
    principal = request.state.principal  # set by require_auth (shared.security)
    roles = tuple(getattr(principal, "roles", ()) or ())
    if not any(role in roles for role in allowed):
        raise HTTPException(status_code=403, detail="forbidden")
    return _principal_user_id(request)


class AdminSubscriptionPage(BaseModel):
    items: list[SubscriptionOut]
    next_cursor: str | None


@admin_router.get("/subscriptions")
async def list_subscriptions(
    request: Request,
    session: SessionDep,
    cursor: str | None = None,
    limit: int = 50,
) -> AdminSubscriptionPage:
    await _require_flag(session)
    _require_role(request, SUPER_ADMIN)
    try:
        page = await paginate(
            session, select(Subscription), cursor=cursor, limit=limit, descending=True
        )
    except InvalidCursorError as exc:
        raise HTTPException(status_code=400, detail="invalid cursor") from exc
    return AdminSubscriptionPage(
        items=[subscription_out(sub) for sub in page.items], next_cursor=page.next_cursor
    )


@admin_router.post("/subscriptions/{subscription_id}/cancel")
async def cancel_subscription(
    request: Request, subscription_id: uuid.UUID, session: SessionDep
) -> SubscriptionOut:
    await _require_flag(session)
    admin_id = _require_role(request, SUPER_ADMIN)
    sub = await session.scalar(
        select(Subscription).where(Subscription.id == subscription_id).with_for_update()
    )
    if sub is None:
        raise HTTPException(status_code=404, detail="subscription not found")
    if sub.status == "canceled":
        raise HTTPException(status_code=409, detail="already_canceled")
    if sub.razorpay_sub_id:
        await razorpay_client.get_client().cancel_subscription(sub.razorpay_sub_id)
    pending = await apply_subscription_cancelled(session, sub, now=datetime.now(UTC))
    await audit(
        session,
        action="billing.admin_cancel",
        actor_user_id=admin_id,
        target_type="subscription",
        target_id=str(sub.id),
        metadata={"business_id": str(sub.business_id), "tier": sub.tier},
        ip=request.client.host if request.client else None,
    )
    out = subscription_out(sub)  # capture BEFORE commit (attributes expire)
    await session.commit()
    await publish_pending(pending)
    return out
