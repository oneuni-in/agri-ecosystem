"""Ops Console admin surface (D21): the ONE moderation queue + flag switches.

Moderation fan-in: this router owns the generic choreography - delegate the
decision to the registered source (which runs its module's FOR UPDATE service
+ audit() in THIS session's transaction and captures event payloads), then
commit, then best-effort publish. An event for a rolled-back decision must
never exist; a Redis blip must never roll back a decision (D16 contract).

Role gates: moderation = staff|super_admin; flags = super_admin only (a flag
flip is a business-level act - see Task 11). Never log request bodies."""

import uuid
from typing import Annotated

from fastapi import Depends, HTTPException, Query, Request
from sqlalchemy.ext.asyncio import AsyncSession

from modules.ops.schemas import (
    DecisionIn,
    ModerationSummaryOut,
    ModItemOut,
    ModQueuePageOut,
    ModRejectIn,
    item_out,
)
from shared.db import get_session
from shared.events import publish
from shared.moderation import (
    DecisionConflictError,
    ItemNotFoundError,
    ModerationSource,
    PendingEvent,
    get_source,
    iter_sources,
)
from shared.pagination import DEFAULT_PAGE_SIZE, InvalidCursorError
from shared.security import SecureRouter, require_role
from shared.telemetry import get_logger

logger = get_logger(__name__)

admin_router = SecureRouter(prefix="/admin", tags=["ops-admin"])

SessionDep = Annotated[AsyncSession, Depends(get_session)]
LimitQuery = Annotated[int, Query(ge=1, le=100)]

STAFF = "staff"
SUPER_ADMIN = "super_admin"


def _source_or_404(type_key: str) -> ModerationSource:
    source = get_source(type_key)
    if source is None:
        raise HTTPException(status_code=404, detail="unknown_type")
    return source


async def _publish_best_effort(event: PendingEvent) -> None:
    try:
        await publish(event.stream, event.event_type, dict(event.payload))
    except Exception:  # a Redis blip must never roll back an admin decision
        logger.warning(
            "ops admin: event publish failed",
            extra={"extra_fields": {"event_type": event.event_type}},
        )


@admin_router.get("/moderation/summary")
async def moderation_summary(request: Request, session: SessionDep) -> ModerationSummaryOut:
    require_role(request, STAFF, SUPER_ADMIN)
    counts = {src.type_key: await src.count_pending(session) for src in iter_sources()}
    return ModerationSummaryOut(counts=counts)


@admin_router.get("/moderation/queue")
async def moderation_queue(
    request: Request,
    session: SessionDep,
    type: str,
    cursor: str | None = None,
    limit: LimitQuery = DEFAULT_PAGE_SIZE,
) -> ModQueuePageOut:
    require_role(request, STAFF, SUPER_ADMIN)
    source = _source_or_404(type)
    try:
        page = await source.list_pending(session, cursor=cursor, limit=limit)
    except InvalidCursorError as exc:
        raise HTTPException(status_code=400, detail="invalid cursor") from exc
    return ModQueuePageOut(items=[item_out(i) for i in page.items], next_cursor=page.next_cursor)


async def _decide(
    request: Request,
    session: AsyncSession,
    *,
    type_key: str,
    item_id: uuid.UUID,
    note: str | None,
    approve: bool,
) -> ModItemOut:
    admin_id = require_role(request, STAFF, SUPER_ADMIN)
    source = _source_or_404(type_key)
    ip = request.client.host if request.client else None
    try:
        if approve:
            decision = await source.approve(
                session, item_id=item_id, actor_user_id=admin_id, note=note, ip=ip
            )
        else:
            decision = await source.reject(
                session, item_id=item_id, actor_user_id=admin_id, note=note, ip=ip
            )
    except ItemNotFoundError as exc:
        raise HTTPException(status_code=404, detail="item not found") from exc
    except DecisionConflictError as exc:
        raise HTTPException(status_code=409, detail=exc.code) from exc
    out = item_out(decision.item)  # capture-before-commit is the SOURCE's job;
    await session.commit()  # the DTO is built from the returned snapshot
    for event in decision.events:
        await _publish_best_effort(event)
    return out


@admin_router.post("/moderation/{type_key}/{item_id}/approve")
async def approve_item(
    request: Request,
    type_key: str,
    item_id: uuid.UUID,
    body: DecisionIn,
    session: SessionDep,
) -> ModItemOut:
    return await _decide(
        request, session, type_key=type_key, item_id=item_id, note=body.note, approve=True
    )


@admin_router.post("/moderation/{type_key}/{item_id}/reject")
async def reject_item(
    request: Request,
    type_key: str,
    item_id: uuid.UUID,
    body: ModRejectIn,
    session: SessionDep,
) -> ModItemOut:
    return await _decide(
        request, session, type_key=type_key, item_id=item_id, note=body.note, approve=False
    )
