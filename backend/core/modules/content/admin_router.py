"""Content admin surface (E6, A-U3) — the moderation queue and THE human gate.

`content.publish` is the gate. It is a router-level dependency on the
moderation route, so the check cannot be forgotten on a future endpoint,
and it is a SEPARATE permission from `content.write`: drafting an item
and approving one are different acts, and an editor may hold the first
without the second.

Every state change writes an audit row. "Who approved this and when" is
the whole point of a human gate — a gate with no record of who passed
what through it proves nothing after the fact.
"""

from __future__ import annotations

import uuid
from typing import Annotated

from fastapi import Depends, HTTPException, Query, Request
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from shared.audit import audit
from shared.authz import require_permission, resolve_actor
from shared.db import get_session
from shared.pagination import DEFAULT_PAGE_SIZE, MAX_PAGE_SIZE, InvalidCursorError
from shared.security import SecureRouter

from .schemas import ItemIn, ModerationIn, QueueCard, QueuePage, to_queue_card
from .service import create_item, list_queue, set_moderation

SessionDep = Annotated[AsyncSession, Depends(get_session)]

admin_router = SecureRouter(prefix="/admin/content", tags=["content-admin"])


@admin_router.get("/queue", dependencies=[require_permission("content.read")])
async def get_queue(
    session: SessionDep,
    status: Annotated[str, Query(pattern="^(pending|approved|rejected)$")] = "pending",
    cursor: Annotated[str | None, Query(max_length=64)] = None,
    limit: Annotated[int, Query(ge=1, le=MAX_PAGE_SIZE)] = DEFAULT_PAGE_SIZE,
) -> QueuePage:
    """What is waiting for a human. Defaults to `pending` — the queue's
    reason to exist."""
    try:
        page = await list_queue(session, status=status, cursor=cursor, limit=limit)
    except InvalidCursorError:
        raise HTTPException(status_code=422, detail="invalid_cursor") from None
    return QueuePage(
        items=[to_queue_card(item) for item in page.items], next_cursor=page.next_cursor
    )


@admin_router.post("/items", status_code=201, dependencies=[require_permission("content.write")])
async def create_content_item(session: SessionDep, request: Request, body: ItemIn) -> QueueCard:
    """Write a first-party item — a guide, an advisory, a curated video.

    Gated on `content.write`, NOT `content.publish`: drafting is not
    approving. Whatever this creates lands `pending` and still has to go
    through the gate, so an editor who can write cannot self-publish.
    """
    actor = resolve_actor(request)
    try:
        item = await create_item(session, **body.model_dump())
    except IntegrityError:
        # Slugs are immutable and unique (ADR-0006) — reusing one would
        # silently repoint an indexed URL at different content.
        raise HTTPException(status_code=409, detail="slug_taken") from None

    await audit(
        session,
        action="content.created",
        actor_user_id=actor,
        target_type="content.item",
        target_id=str(item.id),
        metadata={"kind": item.kind, "slug": item.slug},
    )
    return to_queue_card(item)


@admin_router.post(
    "/items/{item_id}/moderation", dependencies=[require_permission("content.publish")]
)
async def moderate_item(
    session: SessionDep, request: Request, item_id: uuid.UUID, body: ModerationIn
) -> QueueCard:
    """THE human gate (AG row: publish requires an approver).

    A caller without `content.publish` never reaches this body — the
    router-level dependency 403s first, which is exactly what the
    acceptance row tests by attempting a publish as a non-approver.

    Reversible on purpose: `approved` -> `pending` un-publishes. An
    approval made in error must be undoable by the same door it came
    through, not by a database edit.
    """
    actor = resolve_actor(request)
    item = await set_moderation(session, item_id, status=body.status)
    if item is None:
        raise HTTPException(status_code=404, detail="content_not_found")

    await audit(
        session,
        action="content.moderated",
        actor_user_id=actor,
        target_type="content.item",
        target_id=str(item.id),
        metadata={"status": body.status, "kind": item.kind, "slug": item.slug},
    )
    return to_queue_card(item)
