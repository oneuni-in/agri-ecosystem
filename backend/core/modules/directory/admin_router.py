"""Directory admin surface (D16): claim + verification queues.

Auth is ROLE-gated, not permission-gated: modules.directory must never import
modules.identity (import-linter independence), so require_permission is
unavailable here - same trade-off as modules/coins/admin_router.py.

Every decision writes an audit entry IN the decision's transaction (D12);
events publish only AFTER commit, best-effort (an approved claim without a
coins event is a delayed award; a coins event without an approved claim
would be a wrong one). Never log request bodies or query strings."""

import uuid
from datetime import UTC, datetime
from typing import Annotated, Literal

from fastapi import Depends, HTTPException, Path, Query, Request, Response
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from modules.directory import claims, search_sync
from modules.directory.models import Business, Claim, Verification
from modules.directory.schemas import (
    AdminBusinessDetailOut,
    AdminClaimOut,
    AdminClaimPageOut,
    AdminTierIn,
    AdminVerificationOut,
    AdminVerificationPageOut,
    BusinessOut,
    BusinessPageOut,
    DecisionIn,
    EnforceIn,
    EnforcementLogEntryOut,
    EnforcementLogPageOut,
    ReinstateIn,
    RejectIn,
)
from shared import storage
from shared.audit import AuditEntry, audit
from shared.authz import require_permission
from shared.db import get_session
from shared.events import publish
from shared.lookups import pause_campaigns_for_business
from shared.pagination import DEFAULT_PAGE_SIZE, InvalidCursorError, paginate
from shared.security import SecureRouter
from shared.telemetry import get_logger

logger = get_logger(__name__)

admin_router = SecureRouter(prefix="/admin/directory", tags=["directory-admin"])

SessionDep = Annotated[AsyncSession, Depends(get_session)]
LimitQuery = Annotated[int, Query(ge=1, le=100)]
StatusQuery = Literal["pending", "approved", "rejected"]

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


def _admin_claim_out(claim: Claim, business_name: str) -> AdminClaimOut:
    return AdminClaimOut(
        id=claim.id,
        business_id=claim.business_id,
        business_name=business_name,
        claimant_user_id=claim.claimant_user_id,
        status=claim.status,
        evidence_count=len(claim.evidence_docs),
        decision_note=claim.decision_note,
        created_at=claim.created_at,
        decided_at=claim.decided_at,
    )


def _admin_verification_out(verification: Verification, business_name: str) -> AdminVerificationOut:
    return AdminVerificationOut(
        id=verification.id,
        business_id=verification.business_id,
        business_name=business_name,
        method=verification.method,
        status=verification.status,
        notes=verification.notes,
        doc_count=len(verification.doc_keys),
        created_at=verification.created_at,
        decided_at=verification.decided_at,
    )


def _admin_business_out(business: Business) -> BusinessOut:
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
        delivery_windows=business.delivery_windows,
        created_at=business.created_at,
        enforcement_reason=business.enforcement_reason,
    )


async def _publish_best_effort(event_type: str, payload: dict[str, object]) -> None:
    try:
        await publish(EVENT_STREAM, event_type, payload)
    except Exception:  # a Redis blip must never roll back an admin decision
        logger.warning(
            "directory admin: event publish failed",
            extra={"extra_fields": {"event_type": event_type}},
        )


async def _product_payloads(
    session: AsyncSession, business_id: uuid.UUID
) -> list[dict[str, object]]:
    """Every one of a business's own products, as fat event payloads - call
    BEFORE commit alongside `business_event_payload` so an admin decision
    that changes snapshot-visible business fields (verified, ...) also
    republishes its products (see search_sync.business_product_ids; D19
    review finding 1)."""
    return [
        await search_sync.product_event_payload(session, product_id)
        for product_id in await search_sync.business_product_ids(session, business_id)
    ]


@admin_router.get("/claims")
async def list_claims(
    request: Request,
    session: SessionDep,
    status: StatusQuery = "pending",
    cursor: str | None = None,
    limit: LimitQuery = DEFAULT_PAGE_SIZE,
) -> AdminClaimPageOut:
    _require_role(request, STAFF, SUPER_ADMIN)
    try:
        page = await claims.list_claims(session, status=status, cursor=cursor, limit=limit)
    except InvalidCursorError as exc:
        raise HTTPException(status_code=400, detail="invalid cursor") from exc
    names = await claims.business_names(session, [c.business_id for c in page.items])
    return AdminClaimPageOut(
        items=[_admin_claim_out(c, names.get(c.business_id, "")) for c in page.items],
        next_cursor=page.next_cursor,
    )


@admin_router.get("/claims/{claim_id}/evidence/{index}")
async def get_claim_evidence(
    request: Request,
    claim_id: uuid.UUID,
    index: Annotated[int, Path(ge=0)],
    session: SessionDep,
) -> Response:
    _require_role(request, STAFF, SUPER_ADMIN)
    claim = await claims.get_claim(session, claim_id)
    if claim is None or index >= len(claim.evidence_docs):
        raise HTTPException(status_code=404, detail="Claim not found")
    try:
        data = await storage.get_object(claim.evidence_docs[index])
    except storage.StorageError as exc:
        raise HTTPException(status_code=503, detail="storage unavailable") from exc
    return Response(
        content=data, media_type="image/jpeg", headers={"cache-control": "private, no-store"}
    )


@admin_router.post("/claims/{claim_id}/approve")
async def approve_claim(
    request: Request, claim_id: uuid.UUID, body: DecisionIn, session: SessionDep
) -> AdminClaimOut:
    admin_id = _require_role(request, STAFF, SUPER_ADMIN)
    try:
        claim, business = await claims.approve_claim(
            session, claim_id=claim_id, decided_by=admin_id, note=body.note, now=datetime.now(UTC)
        )
    except claims.ClaimNotFoundError as exc:
        raise HTTPException(status_code=404, detail="Claim not found") from exc
    except claims.ClaimError as exc:
        raise HTTPException(status_code=409, detail=exc.code) from exc
    # audit rides the SAME transaction as the decision (D12 contract)
    await audit(
        session,
        action="directory.claim_approved",
        actor_user_id=admin_id,
        target_type="business_claim",
        target_id=str(claim.id),
        metadata={
            "business_id": str(business.id),
            "claimant_user_id": str(claim.claimant_user_id),
            "note": body.note,
        },
        ip=request.client.host if request.client else None,
    )
    # capture EVERYTHING needed after commit BEFORE committing - ORM
    # attributes expire at commit and async lazy-refresh raises
    payload: dict[str, object] = {
        "user_id": str(claim.claimant_user_id),
        "business_id": str(business.id),
        "vars": {"business_name": business.name},
    }
    search_payload = await search_sync.business_event_payload(session, business.id)
    product_payloads = await _product_payloads(session, business.id)
    out = _admin_claim_out(claim, business.name)
    await session.commit()  # commit BEFORE announcing (identity precedent)
    await _publish_best_effort("business.claimed", payload)
    await _publish_best_effort("business.updated", search_payload)
    for product_payload in product_payloads:
        await _publish_best_effort("product.updated", product_payload)
    return out


@admin_router.post("/claims/{claim_id}/reject")
async def reject_claim(
    request: Request, claim_id: uuid.UUID, body: RejectIn, session: SessionDep
) -> AdminClaimOut:
    admin_id = _require_role(request, STAFF, SUPER_ADMIN)
    try:
        claim, business = await claims.reject_claim(
            session, claim_id=claim_id, decided_by=admin_id, note=body.note, now=datetime.now(UTC)
        )
    except claims.ClaimNotFoundError as exc:
        raise HTTPException(status_code=404, detail="Claim not found") from exc
    except claims.ClaimError as exc:
        raise HTTPException(status_code=409, detail=exc.code) from exc
    await audit(
        session,
        action="directory.claim_rejected",
        actor_user_id=admin_id,
        target_type="business_claim",
        target_id=str(claim.id),
        metadata={
            "business_id": str(business.id),
            "claimant_user_id": str(claim.claimant_user_id),
            "note": body.note,
        },
        ip=request.client.host if request.client else None,
    )
    payload: dict[str, object] = {
        "user_id": str(claim.claimant_user_id),
        "business_id": str(business.id),
        "vars": {"business_name": business.name, "reason": body.note},
    }
    out = _admin_claim_out(claim, business.name)
    await session.commit()
    await _publish_best_effort("directory.claim_rejected", payload)
    return out


@admin_router.get("/verifications")
async def list_verifications(
    request: Request,
    session: SessionDep,
    status: StatusQuery = "pending",
    cursor: str | None = None,
    limit: LimitQuery = DEFAULT_PAGE_SIZE,
) -> AdminVerificationPageOut:
    _require_role(request, STAFF, SUPER_ADMIN)
    try:
        page = await claims.list_verifications(session, status=status, cursor=cursor, limit=limit)
    except InvalidCursorError as exc:
        raise HTTPException(status_code=400, detail="invalid cursor") from exc
    names = await claims.business_names(session, [v.business_id for v in page.items])
    return AdminVerificationPageOut(
        items=[_admin_verification_out(v, names.get(v.business_id, "")) for v in page.items],
        next_cursor=page.next_cursor,
    )


@admin_router.get("/verifications/{verification_id}/docs/{index}")
async def get_verification_doc(
    request: Request,
    verification_id: uuid.UUID,
    index: Annotated[int, Path(ge=0)],
    session: SessionDep,
) -> Response:
    _require_role(request, STAFF, SUPER_ADMIN)
    verification = await claims.get_verification(session, verification_id)
    if verification is None or index >= len(verification.doc_keys):
        raise HTTPException(status_code=404, detail="Verification not found")
    try:
        data = await storage.get_object(verification.doc_keys[index])
    except storage.StorageError as exc:
        raise HTTPException(status_code=503, detail="storage unavailable") from exc
    return Response(
        content=data, media_type="image/jpeg", headers={"cache-control": "private, no-store"}
    )


@admin_router.post("/verifications/{verification_id}/approve")
async def approve_verification(
    request: Request, verification_id: uuid.UUID, body: DecisionIn, session: SessionDep
) -> AdminVerificationOut:
    admin_id = _require_role(request, STAFF, SUPER_ADMIN)
    try:
        verification, business = await claims.decide_verification(
            session,
            verification_id=verification_id,
            approve=True,
            decided_by=admin_id,
            note=body.note,
            now=datetime.now(UTC),
        )
    except claims.ClaimNotFoundError as exc:
        raise HTTPException(status_code=404, detail="Verification not found") from exc
    except claims.ClaimError as exc:
        raise HTTPException(status_code=409, detail=exc.code) from exc
    # audit rides the SAME transaction as the decision (D12 contract)
    await audit(
        session,
        action="directory.verification_approved",
        actor_user_id=admin_id,
        target_type="business_verification",
        target_id=str(verification.id),
        metadata={"business_id": str(business.id), "note": body.note},
        ip=request.client.host if request.client else None,
    )
    # capture EVERYTHING needed after commit BEFORE committing - ORM
    # attributes expire at commit and async lazy-refresh raises
    payload: dict[str, object] = {
        "user_id": str(business.owner_user_id),
        "business_id": str(business.id),
        "vars": {"business_name": business.name},
    }
    search_payload = await search_sync.business_event_payload(session, business.id)
    product_payloads = await _product_payloads(session, business.id)
    out = _admin_verification_out(verification, business.name)
    await session.commit()  # commit BEFORE announcing (identity precedent)
    await _publish_best_effort("directory.verification_approved", payload)
    await _publish_best_effort("business.updated", search_payload)
    for product_payload in product_payloads:
        await _publish_best_effort("product.updated", product_payload)
    return out


@admin_router.post("/verifications/{verification_id}/reject")
async def reject_verification(
    request: Request, verification_id: uuid.UUID, body: RejectIn, session: SessionDep
) -> AdminVerificationOut:
    admin_id = _require_role(request, STAFF, SUPER_ADMIN)
    try:
        verification, business = await claims.decide_verification(
            session,
            verification_id=verification_id,
            approve=False,
            decided_by=admin_id,
            note=body.note,
            now=datetime.now(UTC),
        )
    except claims.ClaimNotFoundError as exc:
        raise HTTPException(status_code=404, detail="Verification not found") from exc
    except claims.ClaimError as exc:
        raise HTTPException(status_code=409, detail=exc.code) from exc
    await audit(
        session,
        action="directory.verification_rejected",
        actor_user_id=admin_id,
        target_type="business_verification",
        target_id=str(verification.id),
        metadata={"business_id": str(business.id), "note": body.note},
        ip=request.client.host if request.client else None,
    )
    payload: dict[str, object] = {
        "user_id": str(business.owner_user_id),
        "business_id": str(business.id),
        "vars": {"business_name": business.name, "reason": body.note},
    }
    # unconditional per the D19 event contract - "verification approve/reject"
    # both re-publish, even though a reject rarely flips the visible
    # `verified` boolean (pending/unverified both read as False)
    search_payload = await search_sync.business_event_payload(session, business.id)
    product_payloads = await _product_payloads(session, business.id)
    out = _admin_verification_out(verification, business.name)
    await session.commit()
    await _publish_best_effort("directory.verification_rejected", payload)
    await _publish_best_effort("business.updated", search_payload)
    for product_payload in product_payloads:
        await _publish_best_effort("product.updated", product_payload)
    return out


# --- enforcement (M1.5.B): suspend / disable / reinstate -------------------
#
# Soft-state one-liners on Business (Constitution soft-delete: no data is
# ever deleted). Status is snapshot-visible, so every action republishes the
# fat events; a non-active status makes business_snapshot() return None and
# the search worker tombstones the docs. Enforcement is ALWAYS a human
# decision - nothing here is reachable from report counts.


async def _load_business_for_enforcement(session: AsyncSession, business_id: uuid.UUID) -> Business:
    business = await session.scalar(select(Business).where(Business.id == business_id))
    if business is None:
        raise HTTPException(status_code=404, detail="Business not found")
    return business


async def _finish_enforcement(
    session: AsyncSession,
    business: Business,
    *,
    action: str,
    admin_id: uuid.UUID,
    metadata: dict[str, object],
    ip: str | None,
) -> BusinessOut:
    await session.flush()
    await audit(
        session,
        action=action,
        actor_user_id=admin_id,
        target_type="business",
        target_id=str(business.id),
        metadata=metadata,
        ip=ip,
    )
    # capture BEFORE commit - ORM attributes expire at commit
    search_payload = await search_sync.business_event_payload(session, business.id)
    product_payloads = await _product_payloads(session, business.id)
    out = _admin_business_out(business)
    await session.commit()
    await _publish_best_effort("business.updated", search_payload)
    for product_payload in product_payloads:
        await _publish_best_effort("product.updated", product_payload)
    return out


@admin_router.post("/businesses/{business_id}/suspend")
async def suspend_business(
    request: Request, business_id: uuid.UUID, body: EnforceIn, session: SessionDep
) -> BusinessOut:
    """Delist (M1.5.B): hidden from covers/search/ads, profile 410s, owner
    keeps console access and sees the reason."""
    admin_id = _require_role(request, STAFF, SUPER_ADMIN)
    business = await _load_business_for_enforcement(session, business_id)
    if business.status == "suspended":
        raise HTTPException(status_code=409, detail="already_suspended")
    if business.status == "disabled":
        # de-escalation goes through reinstate, never sideways
        raise HTTPException(status_code=409, detail="business_disabled")
    prior = business.status
    business.enforcement_prior_status = prior
    business.status = "suspended"
    business.enforcement_reason = body.reason
    return await _finish_enforcement(
        session,
        business,
        action="directory.business_suspended",
        admin_id=admin_id,
        metadata={"reason": body.reason, "prior_status": prior},
        ip=request.client.host if request.client else None,
    )


@admin_router.post("/businesses/{business_id}/disable")
async def disable_business(
    request: Request, business_id: uuid.UUID, body: EnforceIn, session: SessionDep
) -> BusinessOut:
    """Hard-off (M1.5.B): owner console locked (service.get_owned_business
    raises app-wide 403), all serving stops; active ad campaigns auto-pause
    (no refund logic v1 - the audit row's campaigns_paused list is the
    manual-handling flag)."""
    admin_id = _require_role(request, STAFF, SUPER_ADMIN)
    business = await _load_business_for_enforcement(session, business_id)
    if business.status == "disabled":
        raise HTTPException(status_code=409, detail="already_disabled")
    prior = business.status
    business.enforcement_prior_status = prior
    business.status = "disabled"
    business.enforcement_reason = body.reason
    paused = await pause_campaigns_for_business(session, business.id)
    return await _finish_enforcement(
        session,
        business,
        action="directory.business_disabled",
        admin_id=admin_id,
        metadata={"reason": body.reason, "prior_status": prior, "campaigns_paused": paused},
        ip=request.client.host if request.client else None,
    )


@admin_router.post("/businesses/{business_id}/reinstate")
async def reinstate_business(
    request: Request, business_id: uuid.UUID, body: ReinstateIn, session: SessionDep
) -> BusinessOut:
    """Restore the prior state (spec: disable-over-suspend reinstates back to
    suspended first; a second reinstate clears to active). Paused campaigns
    stay paused - un-pausing is the advertiser's explicit call."""
    admin_id = _require_role(request, STAFF, SUPER_ADMIN)
    business = await _load_business_for_enforcement(session, business_id)
    if business.status == "active":
        raise HTTPException(status_code=409, detail="not_enforced")
    prior = business.status
    restored = business.enforcement_prior_status or "active"
    business.status = restored
    business.enforcement_prior_status = None
    if restored == "active":
        business.enforcement_reason = None
    return await _finish_enforcement(
        session,
        business,
        action="directory.business_reinstated",
        admin_id=admin_id,
        metadata={"note": body.note, "prior_status": prior, "restored_status": restored},
        ip=request.client.host if request.client else None,
    )


_BUSINESS_STATUS = Literal["active", "suspended", "disabled"]
_BUSINESS_TYPE = Literal["vendor", "shop", "lab", "farm"]


@admin_router.get(
    "/businesses",
    dependencies=[require_permission("directory.read")],
)
async def admin_browse_businesses(
    request: Request,
    session: SessionDep,
    status: _BUSINESS_STATUS | None = None,
    type: _BUSINESS_TYPE | None = None,
    pincode: str | None = None,
    cursor: str | None = None,
    limit: LimitQuery = DEFAULT_PAGE_SIZE,
) -> BusinessPageOut:
    """Admin directory browse (U3, read-only). The PUBLIC path is covers()
    (active-only, pincode-keyed, distance-ranked); an enforcement console must
    also see suspended/disabled rows, so this reads directory.businesses
    directly via paginate() (soft-deleted rows stay excluded by the global
    filter). Enforcement (suspend/disable/reinstate) reuses the existing
    routes above — nothing new is invented here. `type` is the D24 brand
    dimension (vendor/shop/lab/farm)."""
    query = select(Business)
    if status is not None:
        query = query.where(Business.status == status)
    if type is not None:
        query = query.where(Business.type == type)
    if pincode is not None:
        query = query.where(Business.primary_pincode == pincode)
    try:
        page = await paginate(session, query, cursor=cursor, limit=limit)
    except InvalidCursorError as exc:
        raise HTTPException(status_code=400, detail="invalid cursor") from exc
    return BusinessPageOut(
        items=[_admin_business_out(b) for b in page.items],
        next_cursor=page.next_cursor,
    )


@admin_router.get("/businesses/{slug}")
async def admin_business_lookup(
    request: Request, slug: str, session: SessionDep
) -> AdminBusinessDetailOut:
    """Enforcement console lookup by slug (admin sees any status)."""
    _require_role(request, STAFF, SUPER_ADMIN)
    business = await session.scalar(select(Business).where(Business.slug == slug))
    if business is None:
        raise HTTPException(status_code=404, detail="Business not found")
    base = _admin_business_out(business)
    return AdminBusinessDetailOut(
        **base.model_dump(), enforcement_prior_status=business.enforcement_prior_status
    )


_ENFORCEMENT_ACTIONS = (
    "directory.business_suspended",
    "directory.business_disabled",
    "directory.business_reinstated",
)


@admin_router.get("/businesses/{business_id}/enforcement-log")
async def enforcement_log(
    request: Request,
    business_id: uuid.UUID,
    session: SessionDep,
    cursor: str | None = None,
    limit: LimitQuery = DEFAULT_PAGE_SIZE,
) -> EnforcementLogPageOut:
    """Append-only trail (who, when, why, prior state) straight from the
    hash-chained audit log - newest first."""
    _require_role(request, STAFF, SUPER_ADMIN)
    query = select(AuditEntry).where(
        AuditEntry.action.in_(_ENFORCEMENT_ACTIONS),
        AuditEntry.target_type == "business",
        AuditEntry.target_id == str(business_id),
    )
    try:
        page = await paginate(session, query, cursor=cursor, limit=limit, descending=True)
    except InvalidCursorError as exc:
        raise HTTPException(status_code=400, detail="invalid cursor") from exc
    return EnforcementLogPageOut(
        items=[
            EnforcementLogEntryOut(
                id=entry.id,
                action=entry.action,
                actor_user_id=entry.actor_user_id,
                created_at=entry.created_at,
                metadata=entry.meta,
            )
            for entry in page.items
        ],
        next_cursor=page.next_cursor,
    )


@admin_router.post("/businesses/{business_id}/tier")
async def set_business_tier(
    request: Request, business_id: uuid.UUID, body: AdminTierIn, session: SessionDep
) -> BusinessOut:
    """THE subscription_tier write path (D26). Owner surfaces only record
    intent; ops flips the real tier here (and billing will, at launch,
    through the flag-flip runbook's sync)."""
    admin_id = _require_role(request, STAFF, SUPER_ADMIN)
    business = await session.scalar(select(Business).where(Business.id == business_id))
    if business is None:
        raise HTTPException(status_code=404, detail="Business not found")
    business.subscription_tier = body.tier
    await session.flush()
    await audit(
        session,
        action="directory.tier_set",
        actor_user_id=admin_id,
        target_type="business",
        target_id=str(business.id),
        metadata={"tier": body.tier},
        ip=request.client.host if request.client else None,
    )
    # tier is snapshot-visible (covers/search carry it): republish
    search_payload = await search_sync.business_event_payload(session, business.id)
    product_payloads = await _product_payloads(session, business.id)
    out = _admin_business_out(business)
    await session.commit()
    await _publish_best_effort("business.updated", search_payload)
    for product_payload in product_payloads:
        await _publish_best_effort("product.updated", product_payload)
    return out
