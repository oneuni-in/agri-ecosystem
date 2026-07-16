"""Claim + verification-lite service (D16). Claims target seeded businesses
(owner_user_id IS NULL); decisions are admin-only (admin_router) and
permanent - there is deliberately NO unclaim path (coins-farming defence:
the award idempotency key is claim:{business_id}, once per business ever).

Never log request bodies here - evidence metadata is claimant PII-adjacent.
"""

import uuid
from datetime import datetime

import uuid6
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from modules.directory import service
from modules.directory.models import Business, Claim, Verification
from shared.ownership import owned_by
from shared.pagination import DEFAULT_PAGE_SIZE, Page, paginate

MAX_EVIDENCE_DOCS = 5


class ClaimNotFoundError(Exception):
    """No such claim/business - or not yours. Routers 404 both identically."""


class ClaimError(Exception):
    """Conflict; .code is the API error detail (409)."""

    def __init__(self, code: str) -> None:
        self.code = code
        super().__init__(code)


def evidence_object_key() -> str:
    # random UUIDv7 key, never derived from user identity (avatar precedent)
    return f"claims/{uuid6.uuid7().hex}.jpg"


async def submit_claim(
    session: AsyncSession,
    *,
    claimant_user_id: uuid.UUID,
    business_id: uuid.UUID,
    evidence_docs: list[str],
) -> Claim:
    business = await session.scalar(
        select(Business).where(Business.id == business_id, Business.status == "active")
    )
    if business is None:
        raise ClaimNotFoundError(str(business_id))
    if business.owner_user_id is not None:
        raise ClaimError("already_owned")
    pending = await session.scalar(
        select(Claim.id).where(
            Claim.business_id == business_id,
            Claim.claimant_user_id == claimant_user_id,
            Claim.status == "pending",
        )
    )
    if pending is not None:  # friendly 409 for the common case; the savepoint
        raise ClaimError("claim_pending")  # below maps the unique-index race to the same 409
    claim = Claim(
        business_id=business_id,
        claimant_user_id=claimant_user_id,
        evidence_docs=evidence_docs,
    )
    # Savepoint wraps only the insert so a lost race against the partial
    # unique index (uq_directory_claims_one_pending) rolls back just this
    # insert, not the caller's transaction (record_entry precedent).
    sp = await session.begin_nested()
    try:
        session.add(claim)
        await session.flush()
    except IntegrityError as exc:  # lost the race to the partial unique index
        await sp.rollback()
        raise ClaimError("claim_pending") from exc
    await sp.commit()
    await session.refresh(claim)
    return claim


async def get_claim(session: AsyncSession, claim_id: uuid.UUID) -> Claim | None:
    claim = await session.scalar(select(Claim).where(Claim.id == claim_id))
    return claim


async def list_my_claims(
    session: AsyncSession,
    user_id: uuid.UUID,
    *,
    cursor: str | None = None,
    limit: int = DEFAULT_PAGE_SIZE,
) -> Page[Claim]:
    return await paginate(
        session,
        owned_by(select(Claim), user_id, column="claimant_user_id"),
        cursor=cursor,
        limit=limit,
    )


async def request_verification(
    session: AsyncSession,
    *,
    owner_user_id: uuid.UUID,
    business_id: uuid.UUID,
    doc_keys: list[str],
) -> Verification:
    business = await service.get_owned_business(session, owner_user_id, business_id)
    if business.verification_status == "verified":
        raise ClaimError("already_verified")
    pending = await session.scalar(
        select(Verification.id).where(
            Verification.business_id == business_id, Verification.status == "pending"
        )
    )
    if pending is not None:  # friendly 409 for the common case; the savepoint
        raise ClaimError("verification_pending")  # below maps the unique-index race to the same 409
    verification = Verification(business_id=business_id, method="document", doc_keys=doc_keys)
    # Savepoint wraps only the insert so a lost race against the partial
    # unique index (uq_directory_verifications_one_pending) rolls back just
    # this insert, not the caller's transaction (submit_claim precedent).
    sp = await session.begin_nested()
    try:
        session.add(verification)
        await session.flush()
    except IntegrityError as exc:  # lost the race to the partial unique index
        await sp.rollback()
        raise ClaimError("verification_pending") from exc
    await sp.commit()
    # Set after the savepoint commit so a lost race leaves the business untouched.
    business.verification_status = "pending"
    await session.refresh(verification)
    return verification


async def _pending_claim_with_business(
    session: AsyncSession, claim_id: uuid.UUID
) -> tuple[Claim, Business]:
    claim = await get_claim(session, claim_id)
    if claim is None:
        raise ClaimNotFoundError(str(claim_id))
    if claim.status != "pending":
        raise ClaimError("already_decided")
    business = await session.scalar(select(Business).where(Business.id == claim.business_id))
    if business is None:
        raise ClaimNotFoundError(str(claim.business_id))
    return claim, business


async def approve_claim(
    session: AsyncSession,
    *,
    claim_id: uuid.UUID,
    decided_by: uuid.UUID,
    note: str | None,
    now: datetime,
) -> tuple[Claim, Business]:
    """Non-negotiable 4: owner + verified + verification record land in the
    caller's single transaction - all or nothing."""
    claim, business = await _pending_claim_with_business(session, claim_id)
    if business.owner_user_id is not None:
        raise ClaimError("already_owned")
    claim.status = "approved"
    claim.decided_by = decided_by
    claim.decided_at = now
    claim.decision_note = note
    business.owner_user_id = claim.claimant_user_id
    business.verification_status = "verified"
    session.add(
        Verification(
            business_id=business.id,
            method="claim",
            doc_keys=claim.evidence_docs,
            status="approved",
            notes=note,
            decided_by=decided_by,
            decided_at=now,
        )
    )
    await session.flush()
    return claim, business


async def reject_claim(
    session: AsyncSession,
    *,
    claim_id: uuid.UUID,
    decided_by: uuid.UUID,
    note: str,
    now: datetime,
) -> tuple[Claim, Business]:
    claim, business = await _pending_claim_with_business(session, claim_id)
    claim.status = "rejected"
    claim.decided_by = decided_by
    claim.decided_at = now
    claim.decision_note = note
    await session.flush()
    return claim, business


async def list_claims(
    session: AsyncSession,
    *,
    status: str,
    cursor: str | None = None,
    limit: int = DEFAULT_PAGE_SIZE,
) -> Page[Claim]:
    return await paginate(
        session, select(Claim).where(Claim.status == status), cursor=cursor, limit=limit
    )


async def business_names(
    session: AsyncSession, business_ids: list[uuid.UUID]
) -> dict[uuid.UUID, str]:
    if not business_ids:
        return {}
    rows = await session.execute(
        select(Business.id, Business.name).where(Business.id.in_(business_ids))
    )
    return {row[0]: row[1] for row in rows}
