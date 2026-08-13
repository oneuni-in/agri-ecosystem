"""U2 Group C — review replies: the D18 moderation rule holds unchanged.

A reply lands `pending` and is invisible in the public reviews list until a
moderator approves it; the owner always sees their own reply with its status.
Replies are soft-deleted, one per review, and only postable to an approved
review the caller's business owns.
"""

import uuid
from collections.abc import AsyncIterator
from typing import Any

import httpx
import pytest
from fastapi import Request
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from main import create_app
from modules.directory import reviews_service
from modules.directory import service as directory_service
from modules.directory.models import Business
from modules.directory.reviews_models import ReviewReply
from modules.identity.service import create_user
from shared.db import get_session
from shared.security import register_principal_resolver

pytestmark = pytest.mark.asyncio


class _Principal:
    def __init__(self, user_id: uuid.UUID, roles: tuple[str, ...] = ("user",)) -> None:
        self.user_id = user_id
        self.roles = roles


@pytest.fixture
async def world(
    db_session: AsyncSession,
) -> AsyncIterator[tuple[httpx.AsyncClient, dict[str, Any]]]:
    app = create_app()

    async def _session_override() -> AsyncIterator[AsyncSession]:
        yield db_session

    async def _resolver(request: Request, session: AsyncSession) -> object | None:
        header = request.headers.get("x-test-user")
        if not header:
            return None
        roles = tuple((request.headers.get("x-test-roles") or "user").split(","))
        return _Principal(uuid.UUID(header), roles)

    app.dependency_overrides[get_session] = _session_override
    register_principal_resolver(_resolver)

    owner = await create_user(db_session, "+919000000821")
    reviewer = await create_user(db_session, "+919000000822")
    business = await directory_service.create_business(
        db_session,
        owner_user_id=owner.id,
        name="U2 Reply Dairy",
        type_="vendor",
        primary_pincode="641001",
        description={"en": "owner"},
    )
    # an APPROVED review to reply to
    review = await reviews_service.create_review(
        db_session,
        author_user_id=reviewer.id,
        target_type="business",
        target_id=business.id,
        rating=5,
        body={"en": "great milk"},
    )
    await reviews_service.moderate(db_session, review_id=review.id, approve=True)
    await reviews_service.recompute_aggregate(
        db_session, target_type="business", target_id=business.id
    )
    await db_session.flush()

    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="https://api.test") as client:
        yield (
            client,
            {
                "owner": {"x-test-user": str(owner.id)},
                "staff": {
                    "x-test-user": str((await create_user(db_session, "+919000000823")).id),
                    "x-test-roles": "staff",
                },
                "business_id": str(business.id),
                "review_id": str(review.id),
            },
        )


async def test_reply_is_pending_and_invisible_until_approved(
    world: tuple[httpx.AsyncClient, dict[str, Any]],
) -> None:
    client, ctx = world
    review_id = ctx["review_id"]

    # owner posts a reply → 201, pending
    created = await client.post(
        f"/reviews/{review_id}/reply",
        json={"body": {"en": "thank you!"}},
        headers=ctx["owner"],
    )
    assert created.status_code == 201, created.text
    reply = created.json()
    assert reply["moderation_status"] == "pending"

    # PUBLIC list: the review is there, but its reply is NULL (pending hidden)
    public = await client.get(
        "/reviews", params={"target_type": "business", "target_id": ctx["business_id"]}
    )
    assert public.status_code == 200
    row = next(r for r in public.json()["items"] if r["id"] == review_id)
    assert row["reply"] is None, "a PENDING reply must not appear publicly"

    # OWNER surface: the owner sees their own pending reply
    owned = await client.get(
        "/reviews/owner", params={"business_id": ctx["business_id"]}, headers=ctx["owner"]
    )
    owned_row = next(r for r in owned.json()["items"] if r["id"] == review_id)
    assert owned_row["reply"]["moderation_status"] == "pending"

    # moderator approves → now visible publicly
    approve = await client.post(
        f"/admin/review-replies/{reply['id']}/approve", headers=ctx["staff"]
    )
    assert approve.status_code == 200, approve.text
    public2 = await client.get(
        "/reviews", params={"target_type": "business", "target_id": ctx["business_id"]}
    )
    row2 = next(r for r in public2.json()["items"] if r["id"] == review_id)
    assert row2["reply"] is not None
    assert row2["reply"]["body"]["en"] == "thank you!"


async def test_rejected_reply_never_appears_publicly(
    world: tuple[httpx.AsyncClient, dict[str, Any]],
) -> None:
    client, ctx = world
    created = await client.post(
        f"/reviews/{ctx['review_id']}/reply",
        json={"body": {"en": "off-topic"}},
        headers=ctx["owner"],
    )
    reply_id = created.json()["id"]
    rejected = await client.post(
        f"/admin/review-replies/{reply_id}/reject",
        json={"note": "spam"},
        headers=ctx["staff"],
    )
    assert rejected.status_code == 200
    public = await client.get(
        "/reviews", params={"target_type": "business", "target_id": ctx["business_id"]}
    )
    row = next(r for r in public.json()["items"] if r["id"] == ctx["review_id"])
    assert row["reply"] is None


async def test_one_reply_per_review(
    world: tuple[httpx.AsyncClient, dict[str, Any]],
) -> None:
    client, ctx = world
    first = await client.post(
        f"/reviews/{ctx['review_id']}/reply", json={"body": {"en": "a"}}, headers=ctx["owner"]
    )
    assert first.status_code == 201
    second = await client.post(
        f"/reviews/{ctx['review_id']}/reply", json={"body": {"en": "b"}}, headers=ctx["owner"]
    )
    assert second.status_code == 409
    assert second.json()["detail"] == "reply_exists"


async def test_reply_soft_delete(
    world: tuple[httpx.AsyncClient, dict[str, Any]],
    db_session: AsyncSession,
) -> None:
    client, ctx = world
    created = await client.post(
        f"/reviews/{ctx['review_id']}/reply", json={"body": {"en": "temp"}}, headers=ctx["owner"]
    )
    reply_id = created.json()["id"]
    deleted = await client.delete(f"/reviews/replies/{reply_id}", headers=ctx["owner"])
    assert deleted.status_code == 204
    # gone from the owner surface...
    owned = await client.get(
        "/reviews/owner", params={"business_id": ctx["business_id"]}, headers=ctx["owner"]
    )
    row = next(r for r in owned.json()["items"] if r["id"] == ctx["review_id"])
    assert row["reply"] is None
    # ...but the row survives (soft delete). include_deleted justification:
    # this IS the recoverability proof — the DELETE verb must not hard-delete.
    survivor = await db_session.scalar(
        select(ReviewReply)
        .where(ReviewReply.id == uuid.UUID(reply_id))
        .execution_options(include_deleted=True)
    )
    assert survivor is not None
    assert survivor.deleted_at is not None


async def test_cannot_reply_to_unapproved_review(
    world: tuple[httpx.AsyncClient, dict[str, Any]],
    db_session: AsyncSession,
) -> None:
    client, ctx = world
    business = await db_session.scalar(
        select(Business).where(Business.id == uuid.UUID(str(ctx["business_id"])))
    )
    assert business is not None
    # a second, still-pending review on the same business
    pending = await reviews_service.create_review(
        db_session,
        author_user_id=(await create_user(db_session, "+919000000824")).id,
        target_type="business",
        target_id=business.id,
        rating=2,
        body={"en": "pending one"},
    )
    await db_session.flush()
    resp = await client.post(
        f"/reviews/{pending.id}/reply", json={"body": {"en": "hi"}}, headers=ctx["owner"]
    )
    assert resp.status_code == 409
    assert resp.json()["detail"] == "review_not_approved"
