"""Directory API (D15). Public reads (business detail by slug, covers search)
are declared in backend/core/public_routes.txt; everything else is private
and owner-scoped through the service layer.

Principal resolution reads request.state.principal directly (populated by
require_auth via shared.security) - the independence contract forbids
modules.directory -> modules.identity. Never log request bodies or query
strings: this module carries business contact PII (phones, addresses).
"""

import logging
import uuid
from dataclasses import asdict
from datetime import UTC, datetime
from typing import Annotated

from fastapi import Depends, HTTPException, Path, Query, Request
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from modules.directory import covers as covers_module
from modules.directory import search_sync, service
from modules.directory.leads_models import ContactReveal
from modules.directory.leads_schemas import ContactRevealOut
from modules.directory.models import Branch, Business, Category
from modules.directory.reveal import (
    RevealCapExceededError,
    RevealUnavailableError,
    claim_reveal_slot,
)
from modules.directory.schemas import (
    BranchCreateIn,
    BranchOut,
    BranchPatchIn,
    BusinessCreateIn,
    BusinessDetailOut,
    BusinessOut,
    BusinessPageOut,
    BusinessPatchIn,
    CategoryAssignIn,
    CategoryAssignOut,
    CategoryOut,
    CategoryPageOut,
    CoverageIn,
    CoverageOut,
    CoversItemOut,
    CoversOut,
    PublicBranchOut,
    RenameIn,
)
from shared.db import get_session
from shared.events import publish
from shared.pagination import DEFAULT_PAGE_SIZE, InvalidCursorError
from shared.security import SecureRouter

logger = logging.getLogger(__name__)

router = SecureRouter(prefix="/directory", tags=["directory"])

SessionDep = Annotated[AsyncSession, Depends(get_session)]
LimitQuery = Annotated[int, Query(ge=1, le=100)]

EVENT_STREAM = "directory"


async def _publish_best_effort(event_type: str, payload: dict[str, object]) -> None:
    try:
        await publish(EVENT_STREAM, event_type, payload)
    except Exception:  # a Redis blip must never roll back a directory write
        logger.warning(
            "directory: event publish failed", extra={"extra_fields": {"event_type": event_type}}
        )


def _principal_user_id(request: Request) -> uuid.UUID:
    principal = request.state.principal  # set by require_auth (shared.security)
    user_id = principal.user_id
    assert isinstance(user_id, uuid.UUID)  # narrow Starlette state's Any for mypy
    return user_id


def _business_out(business: Business) -> BusinessOut:
    return BusinessOut(
        id=business.id,
        name=business.name,
        slug=business.slug,
        type=business.type,
        status=business.status,
        verification_status=business.verification_status,
        subscription_tier=business.subscription_tier,
        claimable=business.owner_user_id is None,
        primary_pincode=business.primary_pincode,
        description=business.description.to_dict() if business.description else None,
        created_at=business.created_at,
    )


def _branch_out(branch: Branch) -> BranchOut:
    return BranchOut(
        id=branch.id,
        business_id=branch.business_id,
        address=branch.address,
        state=branch.state,
        district=branch.district,
        pincode=branch.pincode,
        lat=branch.lat,
        lng=branch.lng,
        phone=branch.phone,
        whatsapp=branch.whatsapp,
        hours=branch.hours,
    )


def _public_branch_out(branch: Branch) -> PublicBranchOut:
    """Same as _branch_out minus phone/whatsapp (D18.C): the public detail
    page must not carry contact fields, not even as null."""
    return PublicBranchOut(
        id=branch.id,
        business_id=branch.business_id,
        address=branch.address,
        state=branch.state,
        district=branch.district,
        pincode=branch.pincode,
        lat=branch.lat,
        lng=branch.lng,
        hours=branch.hours,
    )


def _category_out(category: Category) -> CategoryOut:
    return CategoryOut(
        id=category.id,
        slug=category.slug,
        name=category.name.to_dict(),
        sort_order=category.sort_order,
    )


@router.post("/businesses", status_code=201)
async def create_business(
    request: Request, body: BusinessCreateIn, session: SessionDep
) -> BusinessOut:
    try:
        business = await service.create_business(
            session,
            owner_user_id=_principal_user_id(request),
            name=body.name,
            type_=body.type,
            primary_pincode=body.primary_pincode,
            description=body.description,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    # capture EVERYTHING needed after commit BEFORE committing - ORM
    # attributes expire at commit and async lazy-refresh raises
    payload = await search_sync.business_event_payload(session, business.id)
    out = _business_out(business)
    await session.commit()  # commit BEFORE announcing (admin_router precedent)
    await _publish_best_effort("business.created", payload)
    return out


@router.get("/businesses")
async def list_my_businesses(
    request: Request,
    session: SessionDep,
    cursor: str | None = None,
    limit: LimitQuery = DEFAULT_PAGE_SIZE,
) -> BusinessPageOut:
    try:
        page = await service.list_my_businesses(
            session, _principal_user_id(request), cursor=cursor, limit=limit
        )
    except InvalidCursorError as exc:
        raise HTTPException(status_code=400, detail="invalid cursor") from exc
    return BusinessPageOut(
        items=[_business_out(b) for b in page.items], next_cursor=page.next_cursor
    )


@router.patch("/businesses/{business_id}")
async def update_business(
    request: Request, business_id: uuid.UUID, body: BusinessPatchIn, session: SessionDep
) -> BusinessOut:
    try:
        business = await service.update_business(
            session,
            owner_user_id=_principal_user_id(request),
            business_id=business_id,
            patch=body.model_dump(exclude_unset=True),
        )
    except service.BusinessNotFoundError as exc:
        raise HTTPException(status_code=404, detail="Business not found") from exc
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    payload = await search_sync.business_event_payload(session, business.id)
    out = _business_out(business)
    await session.commit()
    await _publish_best_effort("business.updated", payload)
    return out


@router.post("/businesses/{business_id}/rename")
async def rename_business(
    request: Request, business_id: uuid.UUID, body: RenameIn, session: SessionDep
) -> BusinessOut:
    try:
        business = await service.rename_business(
            session,
            owner_user_id=_principal_user_id(request),
            business_id=business_id,
            new_slug=body.new_slug,
        )
    except service.BusinessNotFoundError as exc:
        raise HTTPException(status_code=404, detail="Business not found") from exc
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    payload = await search_sync.business_event_payload(session, business.id)
    out = _business_out(business)
    await session.commit()
    await _publish_best_effort("business.updated", payload)
    return out


@router.post("/businesses/{business_id}/branches", status_code=201)
async def add_branch(
    request: Request, business_id: uuid.UUID, body: BranchCreateIn, session: SessionDep
) -> BranchOut:
    try:
        branch = await service.add_branch(
            session,
            owner_user_id=_principal_user_id(request),
            business_id=business_id,
            **body.model_dump(),
        )
    except service.BusinessNotFoundError as exc:
        raise HTTPException(status_code=404, detail="Business not found") from exc
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    # a branch's geo/contact rows feed the parent business's snapshot
    payload = await search_sync.business_event_payload(session, business_id)
    out = _branch_out(branch)
    await session.commit()
    await _publish_best_effort("business.updated", payload)
    return out


@router.patch("/branches/{branch_id}")
async def update_branch(
    request: Request, branch_id: uuid.UUID, body: BranchPatchIn, session: SessionDep
) -> BranchOut:
    try:
        branch = await service.update_branch(
            session,
            owner_user_id=_principal_user_id(request),
            branch_id=branch_id,
            patch=body.model_dump(exclude_unset=True),
        )
    except service.BusinessNotFoundError as exc:
        raise HTTPException(status_code=404, detail="Branch not found") from exc
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    payload = await search_sync.business_event_payload(session, branch.business_id)
    out = _branch_out(branch)
    await session.commit()
    await _publish_best_effort("business.updated", payload)
    return out


@router.put("/businesses/{business_id}/coverage")
async def set_coverage(
    request: Request, business_id: uuid.UUID, body: CoverageIn, session: SessionDep
) -> CoverageOut:
    try:
        pincodes = await service.set_coverage(
            session,
            owner_user_id=_principal_user_id(request),
            business_id=business_id,
            pincodes=body.pincodes,
        )
    except service.BusinessNotFoundError as exc:
        raise HTTPException(status_code=404, detail="Business not found") from exc
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    payload = await search_sync.business_event_payload(session, business_id)
    out = CoverageOut(pincodes=pincodes)
    await session.commit()
    await _publish_best_effort("business.updated", payload)
    return out


@router.put("/businesses/{business_id}/categories")
async def assign_categories(
    request: Request, business_id: uuid.UUID, body: CategoryAssignIn, session: SessionDep
) -> CategoryAssignOut:
    try:
        category_ids = await service.assign_categories(
            session,
            owner_user_id=_principal_user_id(request),
            business_id=business_id,
            category_ids=body.category_ids,
        )
    except service.BusinessNotFoundError as exc:
        raise HTTPException(status_code=404, detail="Business not found") from exc
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    payload = await search_sync.business_event_payload(session, business_id)
    out = CategoryAssignOut(category_ids=category_ids)
    await session.commit()
    await _publish_best_effort("business.updated", payload)
    return out


@router.get("/categories")
async def list_categories(
    session: SessionDep, cursor: str | None = None, limit: LimitQuery = DEFAULT_PAGE_SIZE
) -> CategoryPageOut:
    try:
        page = await service.list_categories(session, cursor=cursor, limit=limit)
    except InvalidCursorError as exc:
        raise HTTPException(status_code=400, detail="invalid cursor") from exc
    return CategoryPageOut(
        items=[_category_out(c) for c in page.items], next_cursor=page.next_cursor
    )


# --- public reads (declared in backend/core/public_routes.txt) -------------


@router.get("/businesses/{slug}", public=True)
async def get_business_detail(slug: str, session: SessionDep) -> BusinessDetailOut:
    """Public business profile (SSR source). Suspended/deleted -> 404; renamed
    slugs 301 via SlugRedirectMiddleware reading slug_redirects."""
    result = await service.get_by_slug(session, slug)
    if result is None:
        raise HTTPException(status_code=404, detail="Business not found")
    business, branches, categories = result
    return BusinessDetailOut(
        business=_business_out(business),
        branches=[_public_branch_out(b) for b in branches],
        categories=[_category_out(c) for c in categories],
    )


@router.post("/branches/{branch_id}/reveal")
async def reveal_branch_contact(
    request: Request, branch_id: uuid.UUID, session: SessionDep
) -> ContactRevealOut:
    """Login-gated, daily-capped, DPDP-logged contact reveal (D18.C).
    Order matters: cap FIRST (never bypassed), log row SECOND, numbers LAST."""
    user_id = _principal_user_id(request)
    branch = await session.scalar(select(Branch).where(Branch.id == branch_id))
    if branch is None:
        raise HTTPException(status_code=404, detail="Branch not found")
    business = await session.scalar(
        select(Business).where(Business.id == branch.business_id, Business.status == "active")
    )
    if business is None:
        raise HTTPException(status_code=404, detail="Branch not found")
    try:
        await claim_reveal_slot(user_id, now=datetime.now(UTC))
    except RevealCapExceededError as exc:
        raise HTTPException(status_code=429, detail="reveal_cap_exceeded") from exc
    except RevealUnavailableError as exc:
        raise HTTPException(status_code=503, detail="reveal_unavailable") from exc
    session.add(ContactReveal(user_id=user_id, business_id=branch.business_id, branch_id=branch.id))
    await session.commit()
    # IDs only - never the numbers (DPDP; scrubber is last-line defence, not licence)
    logger.info(
        "contact.revealed",
        extra={"extra_fields": {"user_id": str(user_id), "branch_id": str(branch.id)}},
    )
    return ContactRevealOut(branch_id=branch.id, phone=branch.phone, whatsapp=branch.whatsapp)


@router.get("/covers/{pincode}", public=True)
async def covers_search(
    pincode: Annotated[str, Path(pattern=r"^\d{6}$")],
    session: SessionDep,
    cursor: str | None = None,
    limit: LimitQuery = DEFAULT_PAGE_SIZE,
) -> CoversOut:
    """Vendor discovery: businesses covering the pincode, nearest first.
    Keyset + rate limit are the scraping defence (no offsets to walk)."""
    try:
        page = await covers_module.covers(session, pincode=pincode, cursor=cursor, limit=limit)
    except InvalidCursorError as exc:
        raise HTTPException(status_code=400, detail="invalid cursor") from exc
    return CoversOut(
        items=[CoversItemOut(**asdict(item)) for item in page.items],
        next_cursor=page.next_cursor,
    )
