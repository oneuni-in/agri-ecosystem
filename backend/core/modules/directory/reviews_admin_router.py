"""Review moderation queue (D18.A admin).

Auth is ROLE-gated, not permission-gated: modules.directory must never import
modules.identity (import-linter independence) - same trade-off as
modules/directory/admin_router.py and modules/coins/admin_router.py.

Choreography per decision (D16 precedent): decide -> audit (same tx) ->
capture event payload -> commit -> best-effort publish. An event for a
rolled-back decision must never exist; a Redis blip must never roll back
a decision.
"""

import logging
import uuid
from typing import Annotated, Literal

from fastapi import Depends, HTTPException, Query, Request
from sqlalchemy.ext.asyncio import AsyncSession

from modules.directory import reviews_service
from modules.directory.reviews_schemas import (
    AdminReplyPageOut,
    AdminReviewPageOut,
    ReplyOut,
    ReviewOut,
    reply_out,
    review_out,
)
from modules.directory.schemas import RejectIn
from shared.audit import audit
from shared.db import get_session
from shared.events import publish
from shared.pagination import InvalidCursorError
from shared.security import SecureRouter

logger = logging.getLogger(__name__)

admin_router = SecureRouter(prefix="/admin/reviews", tags=["admin-reviews"])

SessionDep = Annotated[AsyncSession, Depends(get_session)]
LimitQuery = Annotated[int, Query(ge=1, le=100)]

EVENT_STREAM = "directory"
STAFF = "staff"
SUPER_ADMIN = "super_admin"


def _require_role(request: Request, *allowed: str) -> uuid.UUID:
    """Fail-closed role gate. Returns the acting admin's user_id (for audit)."""
    principal = request.state.principal
    roles = getattr(principal, "roles", ())
    if not any(role in roles for role in allowed):
        raise HTTPException(status_code=403, detail="missing_role")
    user_id = principal.user_id
    assert isinstance(user_id, uuid.UUID)
    return user_id


async def _publish_best_effort(event_type: str, payload: dict[str, object]) -> None:
    try:
        await publish(EVENT_STREAM, event_type, payload)
    except Exception:  # a Redis blip must never roll back an admin decision
        logger.warning(
            "reviews admin: event publish failed",
            extra={"extra_fields": {"event_type": event_type}},
        )


@admin_router.get("")
async def list_reviews_for_moderation(
    request: Request,
    session: SessionDep,
    status: Literal["pending", "approved", "rejected"] = "pending",
    cursor: str | None = None,
    limit: LimitQuery = 20,
) -> AdminReviewPageOut:
    _require_role(request, STAFF, SUPER_ADMIN)
    try:
        page = await reviews_service.list_for_moderation(
            session, status=status, cursor=cursor, limit=limit
        )
    except InvalidCursorError as exc:
        raise HTTPException(status_code=400, detail="invalid cursor") from exc
    return AdminReviewPageOut(
        items=[review_out(r) for r in page.items], next_cursor=page.next_cursor
    )


@admin_router.post("/{review_id}/approve")
async def approve_review(request: Request, review_id: uuid.UUID, session: SessionDep) -> ReviewOut:
    admin_id = _require_role(request, STAFF, SUPER_ADMIN)
    try:
        review = await reviews_service.moderate(session, review_id=review_id, approve=True)
    except reviews_service.ReviewNotFoundError as exc:
        raise HTTPException(status_code=404, detail="review not found") from exc
    except reviews_service.ReviewDecisionConflictError as exc:
        raise HTTPException(status_code=409, detail="already_decided") from exc
    await reviews_service.recompute_aggregate(
        session, target_type=review.target_type, target_id=review.target_id
    )
    await audit(
        session,
        action="reviews.review_approved",
        actor_user_id=admin_id,
        target_type="review",
        target_id=str(review.id),
        metadata={
            "author_user_id": str(review.author_user_id),
            "review_target_type": review.target_type,
            "review_target_id": str(review.target_id),
        },
        ip=request.client.host if request.client else None,
    )
    # capture BEFORE commit - ORM attributes expire on commit (async lazy-load raises)
    payload: dict[str, object] = {
        "user_id": str(review.author_user_id),
        "review_id": str(review.id),
        "target_type": review.target_type,
        "target_id": str(review.target_id),
        "vars": {},
    }
    out = review_out(review)
    await session.commit()
    await _publish_best_effort("review.approved", payload)
    return out


@admin_router.post("/{review_id}/reject")
async def reject_review(
    request: Request, review_id: uuid.UUID, body: RejectIn, session: SessionDep
) -> ReviewOut:
    admin_id = _require_role(request, STAFF, SUPER_ADMIN)
    try:
        review = await reviews_service.moderate(session, review_id=review_id, approve=False)
    except reviews_service.ReviewNotFoundError as exc:
        raise HTTPException(status_code=404, detail="review not found") from exc
    except reviews_service.ReviewDecisionConflictError as exc:
        raise HTTPException(status_code=409, detail="already_decided") from exc
    await reviews_service.recompute_aggregate(
        session, target_type=review.target_type, target_id=review.target_id
    )
    await audit(
        session,
        action="reviews.review_rejected",
        actor_user_id=admin_id,
        target_type="review",
        target_id=str(review.id),
        metadata={"note": body.note},
        ip=request.client.host if request.client else None,
    )
    out = review_out(review)
    await session.commit()
    return out


# ── review-reply moderation (U2 Group C) ─────────────────────────────────
# Same choreography as review moderation above. A reply is a separate UGC
# lifecycle from its review, so it has its own queue; approving a review does
# NOT approve a reply and vice-versa.

reply_admin_router = SecureRouter(prefix="/admin/review-replies", tags=["admin-review-replies"])


@reply_admin_router.get("")
async def list_replies_for_moderation(
    request: Request,
    session: SessionDep,
    status: Literal["pending", "approved", "rejected"] = "pending",
    cursor: str | None = None,
    limit: LimitQuery = 20,
) -> AdminReplyPageOut:
    _require_role(request, STAFF, SUPER_ADMIN)
    try:
        page = await reviews_service.list_replies_for_moderation(
            session, status=status, cursor=cursor, limit=limit
        )
    except InvalidCursorError as exc:
        raise HTTPException(status_code=400, detail="invalid cursor") from exc
    return AdminReplyPageOut(items=[reply_out(r) for r in page.items], next_cursor=page.next_cursor)


@reply_admin_router.post("/{reply_id}/approve")
async def approve_reply(request: Request, reply_id: uuid.UUID, session: SessionDep) -> ReplyOut:
    admin_id = _require_role(request, STAFF, SUPER_ADMIN)
    try:
        reply = await reviews_service.moderate_reply(session, reply_id=reply_id, approve=True)
    except reviews_service.ReplyNotFoundError as exc:
        raise HTTPException(status_code=404, detail="reply not found") from exc
    except reviews_service.ReviewDecisionConflictError as exc:
        raise HTTPException(status_code=409, detail="already_decided") from exc
    await audit(
        session,
        action="reviews.reply_approved",
        actor_user_id=admin_id,
        target_type="review_reply",
        target_id=str(reply.id),
        metadata={"review_id": str(reply.review_id), "business_id": str(reply.business_id)},
        ip=request.client.host if request.client else None,
    )
    out = reply_out(reply)
    await session.commit()
    return out


@reply_admin_router.post("/{reply_id}/reject")
async def reject_reply(
    request: Request, reply_id: uuid.UUID, body: RejectIn, session: SessionDep
) -> ReplyOut:
    admin_id = _require_role(request, STAFF, SUPER_ADMIN)
    try:
        reply = await reviews_service.moderate_reply(session, reply_id=reply_id, approve=False)
    except reviews_service.ReplyNotFoundError as exc:
        raise HTTPException(status_code=404, detail="reply not found") from exc
    except reviews_service.ReviewDecisionConflictError as exc:
        raise HTTPException(status_code=409, detail="already_decided") from exc
    await audit(
        session,
        action="reviews.reply_rejected",
        actor_user_id=admin_id,
        target_type="review_reply",
        target_id=str(reply.id),
        metadata={"note": body.note},
        ip=request.client.host if request.client else None,
    )
    out = reply_out(reply)
    await session.commit()
    return out
