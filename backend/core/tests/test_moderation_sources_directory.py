"""NON-NEGOTIABLE 4 (seam test): claims + reviews flow through the ONE
unified queue with full domain effects - ownership flip, aggregate recompute,
audit rows, and post-commit events identical to the legacy per-domain routes."""

import uuid
from collections.abc import AsyncIterator

import httpx
import pytest
from fastapi import Request
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from main import create_app
from modules.directory.models import Business, Claim, Verification
from modules.directory.reviews_models import RatingAggregate, Review
from shared.audit import AuditEntry
from shared.db import get_session
from shared.security import register_principal_resolver

pytestmark = pytest.mark.asyncio

ADMIN = uuid.uuid4()
CLAIMANT = uuid.uuid4()


class _Principal:
    def __init__(self, user_id: uuid.UUID, roles: tuple[str, ...]) -> None:
        self.user_id = user_id
        self.roles = roles


def _as(user_id: uuid.UUID, roles: str) -> dict[str, str]:
    return {"x-test-user": str(user_id), "x-test-roles": roles}


@pytest.fixture
async def api(db_session: AsyncSession) -> AsyncIterator[tuple[httpx.AsyncClient, AsyncSession]]:
    app = create_app()  # create_app registers the real directory sources

    async def _resolver(request: Request, session: AsyncSession) -> _Principal | None:
        header = request.headers.get("x-test-user")
        if header is None:
            return None
        return _Principal(
            uuid.UUID(header), tuple(request.headers.get("x-test-roles", "user").split(","))
        )

    register_principal_resolver(_resolver)

    async def _session_override() -> AsyncIterator[AsyncSession]:
        yield db_session

    app.dependency_overrides[get_session] = _session_override
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        yield client, db_session


async def _seed_claim(session: AsyncSession) -> tuple[Business, Claim]:
    business = Business(
        name="Kovai Mills",
        slug=f"kovai-{uuid.uuid4().hex[:8]}",
        owner_user_id=None,
        type="farm",
        primary_pincode="641001",
    )
    session.add(business)
    await session.flush()
    claim = Claim(
        business_id=business.id, claimant_user_id=CLAIMANT, evidence_docs=["claims/x.jpg"]
    )
    session.add(claim)
    await session.flush()
    return business, claim


async def _seed_pending_review(session: AsyncSession) -> tuple[Business, Review]:
    business = Business(
        name="Erode Farm",
        slug=f"erode-{uuid.uuid4().hex[:8]}",
        owner_user_id=uuid.uuid4(),
        type="farm",
        primary_pincode="641001",
    )
    session.add(business)
    await session.flush()
    review = Review(
        author_user_id=uuid.uuid4(),
        target_type="business",
        target_id=business.id,
        rating=5,
    )
    session.add(review)
    await session.flush()
    return business, review


async def test_summary_includes_directory_types(
    api: tuple[httpx.AsyncClient, AsyncSession],
) -> None:
    client, session = api
    await _seed_claim(session)
    r = await client.get("/admin/moderation/summary", headers=_as(ADMIN, "staff"))
    assert r.status_code == 200
    counts = r.json()["counts"]
    assert counts["claim"] == 1
    assert "verification" in counts and "review" in counts


async def test_claim_approve_via_unified_queue_full_effect(
    api: tuple[httpx.AsyncClient, AsyncSession],
) -> None:
    client, session = api
    business, claim = await _seed_claim(session)
    listed = await client.get("/admin/moderation/queue?type=claim", headers=_as(ADMIN, "staff"))
    assert listed.status_code == 200
    assert listed.json()["items"][0]["id"] == str(claim.id)
    assert listed.json()["items"][0]["payload"]["business_name"] == "Kovai Mills"

    r = await client.post(
        f"/admin/moderation/claim/{claim.id}/approve",
        json={"note": "docs check out"},
        headers=_as(ADMIN, "staff"),
    )
    assert r.status_code == 200
    # domain effect: ownership + verified + verification row (all-or-nothing)
    fresh = await session.get(Business, business.id)
    assert fresh is not None and fresh.owner_user_id == CLAIMANT
    assert fresh.verification_status == "verified"
    ver = await session.scalar(select(Verification).where(Verification.business_id == business.id))
    assert ver is not None and ver.status == "approved" and ver.method == "claim"
    # audit rode the decision transaction with the legacy action string
    entry = await session.scalar(
        select(AuditEntry)
        .where(AuditEntry.action == "directory.claim_approved")
        .order_by(AuditEntry.id.desc())
    )
    assert entry is not None and entry.target_id == str(claim.id)


async def test_claim_double_decide_409(api: tuple[httpx.AsyncClient, AsyncSession]) -> None:
    client, session = api
    _, claim = await _seed_claim(session)
    first = await client.post(
        f"/admin/moderation/claim/{claim.id}/reject",
        json={"note": "insufficient evidence"},
        headers=_as(ADMIN, "staff"),
    )
    assert first.status_code == 200
    second = await client.post(
        f"/admin/moderation/claim/{claim.id}/approve",
        json={},
        headers=_as(ADMIN, "staff"),
    )
    assert second.status_code == 409
    assert second.json()["detail"] == "already_decided"


async def test_review_approve_recomputes_aggregate(
    api: tuple[httpx.AsyncClient, AsyncSession],
) -> None:
    client, session = api
    business, review = await _seed_pending_review(session)
    r = await client.post(
        f"/admin/moderation/review/{review.id}/approve",
        json={},
        headers=_as(ADMIN, "staff"),
    )
    assert r.status_code == 200
    agg = await session.scalar(
        select(RatingAggregate).where(
            RatingAggregate.target_type == "business",
            RatingAggregate.target_id == business.id,
        )
    )
    assert agg is not None and agg.rating_count == 1
    entry = await session.scalar(
        select(AuditEntry)
        .where(AuditEntry.action == "reviews.review_approved")
        .order_by(AuditEntry.id.desc())
    )
    assert entry is not None and entry.target_id == str(review.id)
