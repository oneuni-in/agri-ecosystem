"""Directory's moderation sources for the unified queue (D21): claim,
verification, review. Each approve/reject wraps the EXISTING D16/D18 decision
services (FOR UPDATE choreography preserved), audits in the caller's
transaction with the LEGACY action strings, and captures post-commit event
payloads before returning (ORM attributes expire on commit) - identical
behaviour to the legacy admin routes, which stay mounted for back-compat."""

import uuid
from datetime import UTC, datetime

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from modules.directory import claims, reviews_service, search_sync
from modules.directory.admin_router import _product_payloads
from modules.directory.models import Business, Claim, Verification
from modules.directory.reviews_models import Review
from shared.audit import audit
from shared.moderation import (
    DecisionConflictError,
    ItemNotFoundError,
    ModDecision,
    ModItem,
    PendingEvent,
    register_moderation_source,
)
from shared.pagination import Page

EVENT_STREAM = "directory"


def _claim_item(claim: Claim, business_name: str) -> ModItem:
    return ModItem(
        type_key="claim",
        id=claim.id,
        created_at=claim.created_at,
        title=business_name or str(claim.business_id),
        summary=f"claim by {claim.claimant_user_id}",
        payload={
            "business_id": str(claim.business_id),
            "business_name": business_name,
            "claimant_user_id": str(claim.claimant_user_id),
            "evidence_count": len(claim.evidence_docs),
            "status": claim.status,
        },
    )


class ClaimSource:
    type_key = "claim"

    async def count_pending(self, session: AsyncSession) -> int:
        return (
            await session.scalar(
                select(func.count()).select_from(Claim).where(Claim.status == "pending")
            )
        ) or 0

    async def list_pending(
        self, session: AsyncSession, *, cursor: str | None, limit: int
    ) -> Page[ModItem]:
        page = await claims.list_claims(session, status="pending", cursor=cursor, limit=limit)
        names = await claims.business_names(session, [c.business_id for c in page.items])
        return Page(
            items=[_claim_item(c, names.get(c.business_id, "")) for c in page.items],
            next_cursor=page.next_cursor,
        )

    async def approve(
        self,
        session: AsyncSession,
        *,
        item_id: uuid.UUID,
        actor_user_id: uuid.UUID,
        note: str | None,
        ip: str | None,
    ) -> ModDecision:
        try:
            claim, business = await claims.approve_claim(
                session,
                claim_id=item_id,
                decided_by=actor_user_id,
                note=note,
                now=datetime.now(UTC),
            )
        except claims.ClaimNotFoundError as exc:
            raise ItemNotFoundError(str(item_id)) from exc
        except claims.ClaimError as exc:
            raise DecisionConflictError(exc.code) from exc
        await audit(
            session,
            action="directory.claim_approved",
            actor_user_id=actor_user_id,
            target_type="business_claim",
            target_id=str(claim.id),
            metadata={
                "business_id": str(business.id),
                "claimant_user_id": str(claim.claimant_user_id),
                "note": note,
            },
            ip=ip,
        )
        events = [
            PendingEvent(
                EVENT_STREAM,
                "business.claimed",
                {
                    "user_id": str(claim.claimant_user_id),
                    "business_id": str(business.id),
                    "vars": {"business_name": business.name},
                },
            ),
            PendingEvent(
                EVENT_STREAM,
                "business.updated",
                await search_sync.business_event_payload(session, business.id),
            ),
        ]
        events += [
            PendingEvent(EVENT_STREAM, "product.updated", p)
            for p in await _product_payloads(session, business.id)
        ]
        return ModDecision(item=_claim_item(claim, business.name), events=tuple(events))

    async def reject(
        self,
        session: AsyncSession,
        *,
        item_id: uuid.UUID,
        actor_user_id: uuid.UUID,
        note: str | None,
        ip: str | None,
    ) -> ModDecision:
        try:
            claim, business = await claims.reject_claim(
                session,
                claim_id=item_id,
                decided_by=actor_user_id,
                note=note or "",
                now=datetime.now(UTC),
            )
        except claims.ClaimNotFoundError as exc:
            raise ItemNotFoundError(str(item_id)) from exc
        except claims.ClaimError as exc:
            raise DecisionConflictError(exc.code) from exc
        await audit(
            session,
            action="directory.claim_rejected",
            actor_user_id=actor_user_id,
            target_type="business_claim",
            target_id=str(claim.id),
            metadata={
                "business_id": str(business.id),
                "claimant_user_id": str(claim.claimant_user_id),
                "note": note,
            },
            ip=ip,
        )
        events = (
            PendingEvent(
                EVENT_STREAM,
                "directory.claim_rejected",
                {
                    "user_id": str(claim.claimant_user_id),
                    "business_id": str(business.id),
                    "vars": {"business_name": business.name, "reason": note},
                },
            ),
        )
        return ModDecision(item=_claim_item(claim, business.name), events=events)


def _verification_item(verification: Verification, business_name: str) -> ModItem:
    return ModItem(
        type_key="verification",
        id=verification.id,
        created_at=verification.created_at,
        title=business_name or str(verification.business_id),
        summary=f"{verification.method} verification",
        payload={
            "business_id": str(verification.business_id),
            "business_name": business_name,
            "method": verification.method,
            "doc_count": len(verification.doc_keys),
            "status": verification.status,
        },
    )


class VerificationSource:
    type_key = "verification"

    async def count_pending(self, session: AsyncSession) -> int:
        return (
            await session.scalar(
                select(func.count())
                .select_from(Verification)
                .where(Verification.status == "pending")
            )
        ) or 0

    async def list_pending(
        self, session: AsyncSession, *, cursor: str | None, limit: int
    ) -> Page[ModItem]:
        page = await claims.list_verifications(
            session, status="pending", cursor=cursor, limit=limit
        )
        names = await claims.business_names(session, [v.business_id for v in page.items])
        return Page(
            items=[_verification_item(v, names.get(v.business_id, "")) for v in page.items],
            next_cursor=page.next_cursor,
        )

    async def approve(
        self,
        session: AsyncSession,
        *,
        item_id: uuid.UUID,
        actor_user_id: uuid.UUID,
        note: str | None,
        ip: str | None,
    ) -> ModDecision:
        verification, business = await self._decide(
            session, item_id, approve=True, decided_by=actor_user_id, note=note
        )
        await audit(
            session,
            action="directory.verification_approved",
            actor_user_id=actor_user_id,
            target_type="business_verification",
            target_id=str(verification.id),
            metadata={"business_id": str(business.id), "note": note},
            ip=ip,
        )
        # capture EVERYTHING needed after commit BEFORE returning - ORM
        # attributes expire at commit and async lazy-refresh raises
        events = [
            PendingEvent(
                EVENT_STREAM,
                "directory.verification_approved",
                {
                    "user_id": str(business.owner_user_id),
                    "business_id": str(business.id),
                    "vars": {"business_name": business.name},
                },
            ),
            PendingEvent(
                EVENT_STREAM,
                "business.updated",
                await search_sync.business_event_payload(session, business.id),
            ),
        ]
        events += [
            PendingEvent(EVENT_STREAM, "product.updated", p)
            for p in await _product_payloads(session, business.id)
        ]
        return ModDecision(
            item=_verification_item(verification, business.name), events=tuple(events)
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
        verification, business = await self._decide(
            session, item_id, approve=False, decided_by=actor_user_id, note=note
        )
        await audit(
            session,
            action="directory.verification_rejected",
            actor_user_id=actor_user_id,
            target_type="business_verification",
            target_id=str(verification.id),
            metadata={"business_id": str(business.id), "note": note},
            ip=ip,
        )
        # unconditional per the D19 event contract - "verification approve/reject"
        # both re-publish, even though a reject rarely flips the visible
        # `verified` boolean (pending/unverified both read as False)
        events = [
            PendingEvent(
                EVENT_STREAM,
                "directory.verification_rejected",
                {
                    "user_id": str(business.owner_user_id),
                    "business_id": str(business.id),
                    "vars": {"business_name": business.name, "reason": note},
                },
            ),
            PendingEvent(
                EVENT_STREAM,
                "business.updated",
                await search_sync.business_event_payload(session, business.id),
            ),
        ]
        events += [
            PendingEvent(EVENT_STREAM, "product.updated", p)
            for p in await _product_payloads(session, business.id)
        ]
        return ModDecision(
            item=_verification_item(verification, business.name), events=tuple(events)
        )

    @staticmethod
    async def _decide(
        session: AsyncSession,
        item_id: uuid.UUID,
        *,
        approve: bool,
        decided_by: uuid.UUID,
        note: str | None,
    ) -> tuple[Verification, Business]:
        try:
            return await claims.decide_verification(
                session,
                verification_id=item_id,
                approve=approve,
                decided_by=decided_by,
                note=note,
                now=datetime.now(UTC),
            )
        except claims.ClaimNotFoundError as exc:
            raise ItemNotFoundError(str(item_id)) from exc
        except claims.ClaimError as exc:
            raise DecisionConflictError(exc.code) from exc


def _review_item(review: Review) -> ModItem:
    body = review.body.to_dict() if review.body else {}
    return ModItem(
        type_key="review",
        id=review.id,
        created_at=review.created_at,
        title=f"{review.rating}★ on {review.target_type}",
        summary=(body.get("en") or next(iter(body.values()), ""))[:200],
        payload={
            "author_user_id": str(review.author_user_id),
            "target_type": review.target_type,
            "target_id": str(review.target_id),
            "rating": review.rating,
            "body": body,
            "status": review.moderation_status,
        },
    )


class ReviewSource:
    type_key = "review"

    async def count_pending(self, session: AsyncSession) -> int:
        return (
            await session.scalar(
                select(func.count())
                .select_from(Review)
                .where(Review.moderation_status == "pending")
            )
        ) or 0

    async def list_pending(
        self, session: AsyncSession, *, cursor: str | None, limit: int
    ) -> Page[ModItem]:
        page = await reviews_service.list_for_moderation(
            session, status="pending", cursor=cursor, limit=limit
        )
        return Page(items=[_review_item(r) for r in page.items], next_cursor=page.next_cursor)

    async def approve(
        self,
        session: AsyncSession,
        *,
        item_id: uuid.UUID,
        actor_user_id: uuid.UUID,
        note: str | None,
        ip: str | None,
    ) -> ModDecision:
        review = await self._moderate(session, item_id, approve=True)
        await reviews_service.recompute_aggregate(
            session, target_type=review.target_type, target_id=review.target_id
        )
        await audit(
            session,
            action="reviews.review_approved",
            actor_user_id=actor_user_id,
            target_type="review",
            target_id=str(review.id),
            metadata={
                "author_user_id": str(review.author_user_id),
                "review_target_type": review.target_type,
                "review_target_id": str(review.target_id),
            },
            ip=ip,
        )
        events = (
            PendingEvent(
                EVENT_STREAM,
                "review.approved",
                {
                    "user_id": str(review.author_user_id),
                    "review_id": str(review.id),
                    "target_type": review.target_type,
                    "target_id": str(review.target_id),
                    "vars": {},
                },
            ),
        )
        return ModDecision(item=_review_item(review), events=events)

    async def reject(
        self,
        session: AsyncSession,
        *,
        item_id: uuid.UUID,
        actor_user_id: uuid.UUID,
        note: str | None,
        ip: str | None,
    ) -> ModDecision:
        review = await self._moderate(session, item_id, approve=False)
        await reviews_service.recompute_aggregate(
            session, target_type=review.target_type, target_id=review.target_id
        )
        await audit(
            session,
            action="reviews.review_rejected",
            actor_user_id=actor_user_id,
            target_type="review",
            target_id=str(review.id),
            metadata={"note": note},
            ip=ip,
        )
        return ModDecision(item=_review_item(review), events=())

    @staticmethod
    async def _moderate(session: AsyncSession, item_id: uuid.UUID, *, approve: bool) -> Review:
        try:
            return await reviews_service.moderate(session, review_id=item_id, approve=approve)
        except reviews_service.ReviewNotFoundError as exc:
            raise ItemNotFoundError(str(item_id)) from exc
        except reviews_service.ReviewDecisionConflictError as exc:
            raise DecisionConflictError("already_decided") from exc


def register_directory_moderation_sources() -> None:
    register_moderation_source(ClaimSource())
    register_moderation_source(VerificationSource())
    register_moderation_source(ReviewSource())
