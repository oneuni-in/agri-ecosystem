"""Ops Console admin surface (D21): the ONE moderation queue + flag switches.

Moderation fan-in: this router owns the generic choreography - delegate the
decision to the registered source (which runs its module's FOR UPDATE service
+ audit() in THIS session's transaction and captures event payloads), then
commit, then best-effort publish. An event for a rolled-back decision must
never exist; a Redis blip must never roll back a decision (D16 contract).

Role gates: moderation = staff|super_admin; flags = super_admin only (a flag
flip is a business-level act - see Task 11). Never log request bodies."""

import uuid
from datetime import UTC, datetime
from typing import Annotated

from fastapi import Depends, HTTPException, Path, Query, Request
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from modules.ops.schemas import (
    DecisionIn,
    FlagOut,
    FlagsOut,
    FlagToggleIn,
    ModerationSummaryOut,
    ModItemOut,
    ModQueuePageOut,
    ModRejectIn,
    PincodeTierOut,
    TierBucketOut,
    TierDistributionOut,
    TierOverrideIn,
    item_out,
)
from shared.audit import audit
from shared.db import get_session
from shared.events import publish
from shared.flags import FeatureFlag, reset_flag_cache
from shared.geo.models import PincodeTier
from shared.geo.tiers import (
    TierDistribution,
    UnknownPincodeTierError,
    get_pincode_tier_row,
    override_tier,
    tier_distribution,
)
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


def _flag_out(flag: FeatureFlag) -> FlagOut:
    return FlagOut(
        key=flag.key,
        enabled=flag.enabled,
        description=flag.description,
        updated_at=flag.updated_at,
    )


@admin_router.get("/ops/flags")
async def list_flags(request: Request, session: SessionDep) -> FlagsOut:
    require_role(request, SUPER_ADMIN)
    flags = (await session.scalars(select(FeatureFlag).order_by(FeatureFlag.key))).all()
    return FlagsOut(items=[_flag_out(f) for f in flags])


@admin_router.put("/ops/flags/{key}")
async def toggle_flag(
    request: Request, key: str, body: FlagToggleIn, session: SessionDep
) -> FlagOut:
    """Kill switch: toggles EXISTING flags only. A flag flip is a
    business-level act (PRE-FLAG-FLIP checklist) - super_admin, audited."""
    admin_id = require_role(request, SUPER_ADMIN)
    flag = await session.get(FeatureFlag, key, with_for_update=True)
    if flag is None:
        raise HTTPException(status_code=404, detail="unknown_flag")
    flag.enabled = body.enabled
    await session.flush()
    await session.refresh(flag)  # refresh server-side-computed columns (updated_at)
    await audit(
        session,
        action="ops.flag_changed",
        actor_user_id=admin_id,
        target_type="feature_flag",
        target_id=key,
        metadata={"enabled": body.enabled},
        ip=request.client.host if request.client else None,
    )
    out = _flag_out(flag)
    await session.commit()
    reset_flag_cache()  # this process serves the new state immediately
    return out


def _pincode_tier_out(row: PincodeTier) -> PincodeTierOut:
    return PincodeTierOut(
        pincode=row.pincode,
        tier=row.tier,
        population=row.population,
        user_count=row.user_count,
        method=row.method,
        computed_at=row.computed_at,
        tier_changed_at=row.tier_changed_at,
    )


def _distribution_out(dist: TierDistribution) -> TierDistributionOut:
    return TierDistributionOut(
        buckets=[TierBucketOut(tier=t, count=dist.buckets[t]) for t in range(1, 6)],
        by_method=dist.by_method,
        unclassified=dist.unclassified,
        total=dist.total,
    )


@admin_router.get("/ops/pincode-tiers/distribution")
async def pincode_tier_distribution(request: Request, session: SessionDep) -> TierDistributionOut:
    require_role(request, STAFF, SUPER_ADMIN)
    dist = await tier_distribution(session)
    return _distribution_out(dist)


@admin_router.get("/ops/pincode-tiers/{pincode}")
async def get_pincode_tier(
    request: Request,
    session: SessionDep,
    pincode: Annotated[str, Path(pattern=r"^\d{6}$")],
) -> PincodeTierOut:
    require_role(request, STAFF, SUPER_ADMIN)
    row = await get_pincode_tier_row(session, pincode)
    if row is None:
        raise HTTPException(status_code=404, detail="unknown pincode")
    return _pincode_tier_out(row)


@admin_router.post("/ops/pincode-tiers/{pincode}")
async def override_pincode_tier(
    request: Request,
    session: SessionDep,
    pincode: Annotated[str, Path(pattern=r"^\d{6}$")],
    body: TierOverrideIn,
) -> PincodeTierOut:
    """Admin escape hatch (spec: optional). Bypasses promote-only; a
    demoting override is re-promoted by the next nightly run."""
    admin_id = require_role(request, STAFF, SUPER_ADMIN)
    try:
        row = await override_tier(session, pincode, body.tier, now=datetime.now(UTC))
    except UnknownPincodeTierError as exc:
        raise HTTPException(status_code=404, detail="unknown pincode") from exc
    await audit(
        session,
        action="geo.tier_override",
        actor_user_id=admin_id,
        metadata={"pincode": pincode, "tier": body.tier},
        ip=request.client.host if request.client else None,
    )
    out = _pincode_tier_out(row)
    await session.commit()
    return out
