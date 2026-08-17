"""Content module routes (E6, A-U3 W1).

Public reads serve APPROVED items only — the gate lives in
`service._published()`, so no handler here can widen it by forgetting a
filter. Bookmarks are private by SecureRouter default and never appear in
`public_routes.txt`.

There is deliberately NO public write. Feed items arrive from the ingest
worker; first-party items arrive through the admin router behind
`content.write`. A reader cannot create content, so there is no
user-generated path to moderate beyond what an editor already sees.
"""

from __future__ import annotations

import uuid
from typing import Annotated

from fastapi import Depends, HTTPException, Path, Query, Request, status
from sqlalchemy.ext.asyncio import AsyncSession

from shared.db import get_session
from shared.geo.service import district_for_pincode
from shared.pagination import DEFAULT_PAGE_SIZE, MAX_PAGE_SIZE, InvalidCursorError
from shared.security import SecureRouter

from .models import KINDS
from .schemas import BookmarkIn, ContentCard, ContentDetail, ContentPage, to_card, to_detail
from .service import (
    BookmarkCapReached,
    UnknownKind,
    add_bookmark,
    bookmarked_ids,
    get_item,
    list_advisories,
    list_bookmarks,
    list_feed,
    remove_bookmark,
)

SessionDep = Annotated[AsyncSession, Depends(get_session)]

router = SecureRouter(prefix="/content", tags=["content"])

# Tag values are free text in the DB but bounded on the wire: a filter is
# a query parameter, and an unbounded one invites probing.
_TAG = Annotated[str | None, Query(max_length=64, pattern=r"^[a-z0-9-]+$")]
# District names are proper nouns from the geo dataset ("Tiruvannamalai"),
# not slugs, so they need their own looser-but-still-bounded shape.
_TAG_FREE = Annotated[str | None, Query(max_length=64, pattern=r"^[A-Za-z .\-]+$")]


def _caller(request: Request) -> uuid.UUID:
    user_id = request.state.principal.user_id
    assert isinstance(user_id, uuid.UUID)  # narrow Starlette state's Any
    return user_id


def _optional_caller(request: Request) -> uuid.UUID | None:
    """The reader, if this public request happens to carry a session.

    Public routes do not require auth, but a signed-in reader should see
    their own save state on the cards. Absent principal = anonymous, not
    an error.
    """
    principal = getattr(request.state, "principal", None)
    user_id = getattr(principal, "user_id", None)
    return user_id if isinstance(user_id, uuid.UUID) else None


# public=True: approved editorial/news content, the same read-only class
# as /catalog/verticals and /market/commodities. Registered in
# backend/core/public_routes.txt in this same PR.
@router.get("/feed", public=True)
async def get_feed(
    session: SessionDep,
    request: Request,
    kind: Annotated[str | None, Query(max_length=16)] = None,
    vertical: _TAG = None,
    state: _TAG = None,
    cursor: Annotated[str | None, Query(max_length=64)] = None,
    limit: Annotated[int, Query(ge=1, le=MAX_PAGE_SIZE)] = DEFAULT_PAGE_SIZE,
) -> ContentPage:
    try:
        page = await list_feed(
            session, kind=kind, vertical=vertical, state=state, cursor=cursor, limit=limit
        )
    except UnknownKind:
        raise HTTPException(
            status_code=422, detail=f"kind must be one of {', '.join(KINDS)}"
        ) from None
    except InvalidCursorError:
        raise HTTPException(status_code=422, detail="invalid_cursor") from None

    reader = _optional_caller(request)
    saved = (
        await bookmarked_ids(session, reader, [item.id for item in page.items]) if reader else set()
    )
    return ContentPage(
        items=[to_card(item, bookmarked=item.id in saved) for item in page.items],
        next_cursor=page.next_cursor,
    )


@router.get("/items/{slug}", public=True)
async def get_content_item(
    session: SessionDep,
    request: Request,
    slug: Annotated[str, Path(min_length=1, max_length=128, pattern=r"^[a-z0-9-]+$")],
) -> ContentDetail:
    """404 for pending, rejected and nonexistent alike — an unapproved
    item must not be discoverable by guessing its slug."""
    item = await get_item(session, slug)
    if item is None:
        raise HTTPException(status_code=404, detail="content_not_found")
    reader = _optional_caller(request)
    saved = bool(reader) and bool(await bookmarked_ids(session, reader, [item.id]))  # type: ignore[arg-type]
    return to_detail(item, bookmarked=saved)


# ── bookmarks ────────────────────────────────────────────────────────
# NO public=True: these read and write one user's own shelf.


@router.get("/bookmarks")
async def get_bookmarks(
    session: SessionDep,
    request: Request,
    cursor: Annotated[str | None, Query(max_length=64)] = None,
    limit: Annotated[int, Query(ge=1, le=MAX_PAGE_SIZE)] = DEFAULT_PAGE_SIZE,
) -> ContentPage:
    """The CALLER's shelf only — there is no parameter that could ask for
    someone else's."""
    try:
        page = await list_bookmarks(session, _caller(request), cursor=cursor, limit=limit)
    except InvalidCursorError:
        raise HTTPException(status_code=422, detail="invalid_cursor") from None
    return ContentPage(
        items=[to_card(item, bookmarked=True) for item in page.items],
        next_cursor=page.next_cursor,
    )


@router.post("/bookmarks", status_code=status.HTTP_201_CREATED)
async def create_bookmark(session: SessionDep, request: Request, body: BookmarkIn) -> None:
    """Idempotent — the UI control is a toggle with no 'already saved'
    state to explain. An unapproved or nonexistent item id gets the same
    404, so this cannot enumerate the moderation queue."""
    try:
        saved = await add_bookmark(session, _caller(request), body.item_id)
    except BookmarkCapReached:
        raise HTTPException(status_code=429, detail="bookmark_cap_reached") from None
    if not saved:
        raise HTTPException(status_code=404, detail="content_not_found")


@router.delete("/bookmarks/{item_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_bookmark(session: SessionDep, request: Request, item_id: uuid.UUID) -> None:
    """Another user's bookmark and a nonexistent one both 404, EXACTLY
    alike (the U2 IDOR rule)."""
    if not await remove_bookmark(session, _caller(request), item_id):
        raise HTTPException(status_code=404, detail="bookmark_not_found")


@router.get("/advisories", public=True)
async def get_advisories(
    session: SessionDep,
    district: _TAG_FREE = None,
    pincode: Annotated[str | None, Query(min_length=6, max_length=6, pattern=r"^\d{6}$")] = None,
) -> list[ContentCard]:
    """Live pest advisories for a district (AG row: target district + window).

    Takes either a district name or a pincode we resolve one from — the
    home has a pincode, the hub has a district. When NEITHER resolves,
    the caller gets nationwide advisories only: a wrong-district "spray
    now" costs a farmer money, so an unknown location narrows the answer
    rather than widening it.

    Uncursored: bounded to `limit` live advisories by construction, and
    an advisory set large enough to need paging would itself be the bug.
    """
    resolved = district
    if resolved is None and pincode is not None:
        # An unmapped pincode leaves this None, which narrows the answer
        # to nationwide advisories rather than widening it to everything.
        row = await district_for_pincode(session, pincode)
        resolved = row.name if row is not None else None
    return [to_card(item) for item in await list_advisories(session, district=resolved)]
