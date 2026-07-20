"""Unified public search API (D19 Task 5): `GET /search` fans a single call
out to the per-site Meilisearch index built by modules/search/indexing.py,
applying kind/vertical/covered filters and an optional pincode geo-boost
(default ranking rules keep relevance first; geo sort only breaks ties).

Public (backend/core/public_routes.txt); rate-limited automatically by
SecureRouter like every other route here. The bespoke cursor lives in
service.py - see its docstring for why shared.pagination doesn't apply.
"""

from typing import Annotated, Any, Literal

from fastapi import Depends, HTTPException, Query
from pydantic import BaseModel, ConfigDict
from sqlalchemy.ext.asyncio import AsyncSession

from shared.db import get_session
from shared.security import SecureRouter

from .indexing import SITES
from .service import InvalidSearchCursor, run_search

router = SecureRouter(prefix="/search", tags=["search"])

SessionDep = Annotated[AsyncSession, Depends(get_session)]


class SearchHit(BaseModel):
    """Mirrors indexing.DISPLAYED_ATTRIBUTES exactly - never covered_pincodes,
    never _geo, never PII (indexing._to_doc's allowlist is the first line of
    defence; extra="ignore" here is the second, not a licence to add fields
    without updating DISPLAYED_ATTRIBUTES too)."""

    model_config = ConfigDict(extra="ignore")

    id: str
    kind: str
    name: str
    slug: str | None = None
    business_name: str | None = None
    business_slug: str | None = None
    description: dict[str, Any] | None = None
    categories: list[str] | None = None
    vertical: str | None = None
    district: str | None = None
    state: str | None = None
    verified: bool | None = None
    price_display: str | None = None
    sites: list[str] | None = None


class SearchPage(BaseModel):
    items: list[SearchHit]
    next_cursor: str | None = None


@router.get("", public=True)
async def search(
    session: SessionDep,
    site: str,
    q: Annotated[str, Query(max_length=200)] = "",
    pincode: Annotated[str | None, Query(pattern=r"^\d{6}$")] = None,
    kind: Literal["business", "product"] | None = None,
    vertical: Annotated[str | None, Query(pattern=r"^[a-z0-9-]+$")] = None,
    covered: bool = False,
    cursor: str | None = None,
    limit: Annotated[int, Query(ge=1, le=50)] = 20,
) -> SearchPage:
    """`kind`/`vertical` are allowlisted here (Literal / slug-charset pattern),
    not escaped-and-interpolated: both values are spliced verbatim into a
    Meili filter expression in service.py, and Meili's filter grammar accepts
    boolean composition - an unconstrained value could smuggle in an ` OR
    covered_pincodes = "..."` (or `_geoRadius(...)`) clause and turn the
    filterable-but-not-displayed fields into a hit-presence oracle on this
    public, unauthenticated endpoint. FastAPI's own 422 on a bad value is the
    intended failure mode, not a 200 with leaked hits."""
    if site not in SITES:
        raise HTTPException(status_code=404, detail="unknown_site")
    try:
        result = await run_search(
            session,
            site=site,
            q=q,
            pincode=pincode,
            kind=kind,
            vertical=vertical,
            covered=covered,
            cursor=cursor,
            limit=limit,
        )
    except InvalidSearchCursor as exc:
        raise HTTPException(status_code=400, detail="invalid_cursor") from exc
    return SearchPage(
        items=[SearchHit(**hit) for hit in result["items"]],
        next_cursor=result["next_cursor"],
    )
