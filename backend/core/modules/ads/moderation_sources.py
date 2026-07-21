"""Creative approval source for the unified moderation queue (D21).
Approval is the ONLY path from pending -> servable; even admin-created
creatives start pending (uniform pipeline, approver need not be uploader)."""

import uuid

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from modules.ads.models import Creative
from shared.audit import audit
from shared.moderation import (
    DecisionConflictError,
    ItemNotFoundError,
    ModDecision,
    ModItem,
    PendingEvent,
    register_moderation_source,
)
from shared.pagination import Page, paginate

EVENT_STREAM = "ads"


def _creative_item(creative: Creative) -> ModItem:
    copy = creative.copy or {}
    title = (copy.get("en") or {}).get("title", "") or str(creative.id)
    return ModItem(
        type_key="creative",
        id=creative.id,
        created_at=creative.created_at,
        title=title,
        summary=(copy.get("en") or {}).get("body", "")[:200],
        payload={
            "campaign_id": str(creative.campaign_id),
            "media_count": len(creative.media_keys),
            "copy": copy,
            "target_url": creative.target_url,
            "status": creative.moderation_status,
        },
    )


class CreativeSource:
    type_key = "creative"

    async def count_pending(self, session: AsyncSession) -> int:
        return (
            await session.scalar(
                select(func.count())
                .select_from(Creative)
                .where(Creative.moderation_status == "pending")
            )
        ) or 0

    async def list_pending(
        self, session: AsyncSession, *, cursor: str | None, limit: int
    ) -> Page[ModItem]:
        page = await paginate(
            session,
            select(Creative).where(Creative.moderation_status == "pending"),
            cursor=cursor,
            limit=limit,
        )
        return Page(items=[_creative_item(c) for c in page.items], next_cursor=page.next_cursor)

    async def approve(
        self,
        session: AsyncSession,
        *,
        item_id: uuid.UUID,
        actor_user_id: uuid.UUID,
        note: str | None,
        ip: str | None,
    ) -> ModDecision:
        return await self._decide(
            session, item_id, actor_user_id=actor_user_id, note=note, ip=ip, approve=True
        )

    async def reject(
        self,
        session: AsyncSession,
        *,
        item_id: uuid.UUID,
        actor_user_id: uuid.UUID,
        note: str | None,
        ip: str | None,
    ) -> ModDecision:
        return await self._decide(
            session, item_id, actor_user_id=actor_user_id, note=note, ip=ip, approve=False
        )

    async def _decide(
        self,
        session: AsyncSession,
        item_id: uuid.UUID,
        *,
        actor_user_id: uuid.UUID,
        note: str | None,
        ip: str | None,
        approve: bool,
    ) -> ModDecision:
        creative = await session.scalar(
            # FOR UPDATE: serialize concurrent decisions (claims.py precedent)
            select(Creative).where(Creative.id == item_id).with_for_update()
        )
        if creative is None:
            raise ItemNotFoundError(str(item_id))
        if creative.moderation_status != "pending":
            raise DecisionConflictError("already_decided")
        creative.moderation_status = "approved" if approve else "rejected"
        await session.flush()
        action = "ads.creative_approved" if approve else "ads.creative_rejected"
        await audit(
            session,
            action=action,
            actor_user_id=actor_user_id,
            target_type="ad_creative",
            target_id=str(creative.id),
            metadata={"campaign_id": str(creative.campaign_id), "note": note},
            ip=ip,
        )
        event_type = "creative.approved" if approve else "creative.rejected"
        events = (
            PendingEvent(
                EVENT_STREAM,
                event_type,
                {"creative_id": str(creative.id), "campaign_id": str(creative.campaign_id)},
            ),
        )
        return ModDecision(item=_creative_item(creative), events=events)


def register_ads_moderation_sources() -> None:
    register_moderation_source(CreativeSource())
