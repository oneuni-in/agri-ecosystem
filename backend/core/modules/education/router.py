"""Education vertical public reads (spec section 5).

Every route here is `public=True` and declared in
`backend/core/public_routes.txt` in the same PR. They serve reference data
about public institutions — the same read-only class as `/catalog/verticals`
and `/market/schemes`: no user data, no mutation, already public at the
source, and carrying the source URL and verified-on date the UI renders.

There is deliberately NO write route, public or private. Rows arrive from a
reviewed seed commit through `scripts/import_education_seed.py`, and `app_rt`
holds SELECT only on `education.*` (0049), so there is no handler to widen and
no credentials behind one if there were.
"""

from __future__ import annotations

from typing import Annotated

from fastapi import Depends, HTTPException, Path, Query
from sqlalchemy.ext.asyncio import AsyncSession

from shared.db import get_session
from shared.pagination import DEFAULT_PAGE_SIZE, MAX_PAGE_SIZE, InvalidCursorError
from shared.security import SecureRouter

from .schemas import (
    GuideCard,
    GuideDetail,
    InstitutionDetail,
    InstitutionPage,
    ProgrammeOut,
    ResourceDetail,
    ResourcePage,
    StateFacet,
    to_detail,
    to_guide_card,
    to_guide_detail,
    to_programme,
    to_resource_card,
    to_resource_detail,
)
from .service import (
    GUIDE_KINDS,
    KINDS,
    RESOURCE_CATEGORIES,
    RESOURCE_KINDS,
    RESOURCE_SCOPES,
    TRUSTS,
    UnknownFilter,
    get_guide,
    get_institution,
    get_resource,
    list_guides,
    list_institutions,
    list_programmes,
    list_resources,
    state_facets,
)

SessionDep = Annotated[AsyncSession, Depends(get_session)]

router = SecureRouter(prefix="/education", tags=["education"])

# Slugs are our own vocabulary and bounded on the wire; a filter is a query
# parameter, and an unbounded one invites probing.
_SLUG = Annotated[str | None, Query(max_length=96, pattern=r"^[a-z0-9-]+$")]
_SLUG_PATH = Annotated[str, Path(min_length=1, max_length=96, pattern=r"^[a-z0-9-]+$")]
_COUNTRY = Annotated[str | None, Query(min_length=2, max_length=2, pattern=r"^[A-Za-z]{2}$")]
_CURSOR = Annotated[str | None, Query(max_length=64)]
_LIMIT = Annotated[int, Query(ge=1, le=MAX_PAGE_SIZE)]


def _unknown(exc: UnknownFilter, allowed: tuple[str, ...]) -> HTTPException:
    """422, not an empty 200.

    An empty page tells a caller their filter matched nothing. A value outside
    the enum is a different fact and deserves a different answer.
    """
    return HTTPException(
        status_code=422,
        detail=f"unknown filter value {exc.args[0]!r}; expected one of {', '.join(allowed)}",
    )


# ── institutions ─────────────────────────────────────────────────────


@router.get("/institutions", public=True)
async def get_institutions(
    session: SessionDep,
    state: _SLUG = None,
    district: _SLUG = None,
    kind: Annotated[str | None, Query(max_length=32)] = None,
    is_government: bool | None = None,
    programme: _SLUG = None,
    country: _COUNTRY = None,
    trust: Annotated[str | None, Query(max_length=16)] = None,
    q: Annotated[str | None, Query(max_length=64)] = None,
    cursor: _CURSOR = None,
    limit: _LIMIT = DEFAULT_PAGE_SIZE,
) -> InstitutionPage:
    """Active institutions, verified first.

    Closed and merged rows are absent by construction -- a browse list is a
    list of places a student can apply to. Both stay reachable by slug, which
    is what keeps the 301 and the closed banner of spec section 7 working.

    `district` resolves inside Tamil Nadu only until D65 loads the rest of
    geo.districts; a district filter elsewhere correctly returns nothing.
    """
    try:
        return await list_institutions(
            session,
            state=state,
            district=district,
            kind=kind,
            is_government=is_government,
            programme=programme,
            country=country,
            trust=trust,
            q=q,
            cursor=cursor,
            limit=limit,
        )
    except UnknownFilter as exc:
        raise _unknown(exc, KINDS + TRUSTS) from None
    except InvalidCursorError:
        raise HTTPException(status_code=422, detail="invalid_cursor") from None


@router.get("/institutions/{slug}", public=True)
async def get_institution_detail(session: SessionDep, slug: _SLUG_PATH) -> InstitutionDetail:
    """Any status resolves.

    A `merged` row answers 200 with `merged_into_slug` and the PAGE issues the
    301. This API never redirects: `fetch` follows 3xx by default, so a client
    asking for `old-slug` would silently receive `new-slug`'s JSON under the
    URL it requested and have no way to know.
    """
    row = await get_institution(session, slug)
    if row is None:
        raise HTTPException(status_code=404, detail="institution_not_found")
    return to_detail(row)


@router.get("/states", public=True)
async def get_states(session: SessionDep) -> list[StateFacet]:
    """The state-slug vocabulary for `/colleges/state/[state]`.

    `geo.states` has no slug column, so something has to turn "Tamil Nadu"
    into a URL segment. Doing it in both the route generator and the filter
    would let the two drift on the first name with a period or an ampersand,
    and the page would 404 against its own link. The API publishes the
    vocabulary; the frontend consumes it.

    Uncursored: bounded at ~36 rows by the geo dataset. Only states with at
    least one active institution appear -- 5 have none, all small UTs with no
    agricultural university, and ISR pages for them would be thin indexable
    pages with nothing on them.
    """
    return await state_facets(session)


# ── programmes ───────────────────────────────────────────────────────


@router.get("/programmes", public=True)
async def get_programmes(session: SessionDep) -> list[ProgrammeOut]:
    """The whole catalog, uncursored: ~47 rows of registry-as-data."""
    return [to_programme(row) for row in await list_programmes(session)]


# ── scholarships and exams ───────────────────────────────────────────


@router.get("/student-resources", public=True)
async def get_student_resources(
    session: SessionDep,
    kind: Annotated[str | None, Query(max_length=16)] = None,
    category: Annotated[str | None, Query(max_length=16)] = None,
    scope: Annotated[str | None, Query(max_length=16)] = None,
    cursor: _CURSOR = None,
    limit: _LIMIT = DEFAULT_PAGE_SIZE,
) -> ResourcePage:
    """Active resources only. An expired scholarship listed as live wastes a
    student's application, which costs more than an absent one."""
    try:
        page = await list_resources(
            session, kind=kind, category=category, scope=scope, cursor=cursor, limit=limit
        )
    except UnknownFilter as exc:
        raise _unknown(exc, RESOURCE_KINDS + RESOURCE_CATEGORIES + RESOURCE_SCOPES) from None
    except InvalidCursorError:
        raise HTTPException(status_code=422, detail="invalid_cursor") from None
    return ResourcePage(
        items=[to_resource_card(row) for row in page.items], next_cursor=page.next_cursor
    )


@router.get("/student-resources/{slug}", public=True)
async def get_student_resource(session: SessionDep, slug: _SLUG_PATH) -> ResourceDetail:
    row = await get_resource(session, slug)
    if row is None:
        raise HTTPException(status_code=404, detail="resource_not_found")
    return to_resource_detail(row)


# ── guides ───────────────────────────────────────────────────────────


@router.get("/guides", public=True)
async def get_guides(
    session: SessionDep,
    kind: Annotated[str | None, Query(max_length=16)] = None,
    country: _COUNTRY = None,
    state: _SLUG = None,
) -> list[GuideCard]:
    """Published guides. Uncursored: 13 rows of bounded registry."""
    try:
        rows = await list_guides(session, kind=kind, country=country, state=state)
    except UnknownFilter as exc:
        raise _unknown(exc, GUIDE_KINDS) from None
    return [to_guide_card(guide, state_name) for guide, state_name in rows]


@router.get("/guides/{slug}", public=True)
async def get_guide_detail(session: SessionDep, slug: _SLUG_PATH) -> GuideDetail:
    """A draft and a nonexistent slug 404 identically -- an unreviewed guide
    must not be discoverable by guessing."""
    row = await get_guide(session, slug)
    if row is None:
        raise HTTPException(status_code=404, detail="guide_not_found")
    return to_guide_detail(row[0], row[1])
