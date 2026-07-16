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
from sqlalchemy.ext.asyncio import AsyncSession

from modules.directory import claims
from modules.directory.models import Claim
from modules.directory.schemas import (
    AdminClaimOut,
    AdminClaimPageOut,
    DecisionIn,
    RejectIn,
)
from shared import storage
from shared.audit import audit
from shared.db import get_session
from shared.events import publish
from shared.pagination import DEFAULT_PAGE_SIZE, InvalidCursorError
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


async def _publish_best_effort(event_type: str, payload: dict[str, object]) -> None:
    try:
        await publish(EVENT_STREAM, event_type, payload)
    except Exception:  # a Redis blip must never roll back an admin decision
        logger.warning(
            "directory admin: event publish failed",
            extra={"extra_fields": {"event_type": event_type}},
        )


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
    return Response(content=data, media_type="image/jpeg")


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
    out = _admin_claim_out(claim, business.name)
    await session.commit()  # commit BEFORE announcing (identity precedent)
    await _publish_best_effort("business.claimed", payload)
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
