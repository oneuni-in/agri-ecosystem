"""Market admin surface (A-U4b C1) — the module's first admin router.

One read-only route: the ingest-run ledger. ADR-0012 records every pull
ATTEMPT precisely so a missed day is distinguishable from a quiet mandi —
but a ledger nothing reads proves nothing to anyone. This surface is how
a human sees "the job never fired yesterday" without opening psql.
"""

from __future__ import annotations

from typing import Annotated

from fastapi import Depends, HTTPException, Query
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from shared.authz import require_permission
from shared.db import get_session
from shared.pagination import DEFAULT_PAGE_SIZE, MAX_PAGE_SIZE, InvalidCursorError, paginate
from shared.security import SecureRouter

from .models import IngestRun
from .schemas import IngestRunOut, IngestRunPage

SessionDep = Annotated[AsyncSession, Depends(get_session)]

admin_router = SecureRouter(prefix="/admin/market", tags=["market-admin"])


@admin_router.get("/ingest-runs", dependencies=[require_permission("market.read")])
async def list_ingest_runs(
    session: SessionDep,
    cursor: Annotated[str | None, Query(max_length=64)] = None,
    limit: Annotated[int, Query(ge=1, le=MAX_PAGE_SIZE)] = DEFAULT_PAGE_SIZE,
) -> IngestRunPage:
    """The recent pull attempts, newest first. `outcome='empty'` is a
    healthy run that found nothing; a DAY with no row at all is the
    silent outage this route exists to make visible."""
    try:
        page = await paginate(
            session, select(IngestRun), cursor=cursor, limit=limit, descending=True
        )
    except InvalidCursorError:
        raise HTTPException(status_code=400, detail="invalid cursor") from None
    return IngestRunPage(
        items=[IngestRunOut.model_validate(run) for run in page.items],
        next_cursor=page.next_cursor,
    )
