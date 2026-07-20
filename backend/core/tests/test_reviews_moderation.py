"""Review moderation admin router (D18.A Task 3): approve -> aggregate +
audit + best-effort review.approved event; reject -> audit only, no event.
Scaffold mirrors test_directory_admin.py (role-header trick) and
test_reviews_router.py (real service layer, no mocks except the publisher)."""

import uuid
from collections.abc import AsyncIterator
from typing import Any

import httpx
import pytest
from fastapi import Request
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from main import create_app
from modules.directory import service
from modules.directory.models import Business
from modules.directory.reviews_models import RatingAggregate, Review
from shared.audit import AuditEntry
from shared.db import get_session
from shared.security import register_principal_resolver

pytestmark = pytest.mark.asyncio

OWNER = uuid.uuid4()
AUTHOR = uuid.uuid4()
ADMIN = uuid.uuid4()
PLAIN = uuid.uuid4()


class _Principal:
    def __init__(self, user_id: uuid.UUID, roles: tuple[str, ...]) -> None:
        self.user_id = user_id
        self.roles = roles


def _as(user_id: uuid.UUID, roles: str = "user") -> dict[str, str]:
    return {"x-test-user": str(user_id), "x-test-roles": roles}


@pytest.fixture
def published(monkeypatch: pytest.MonkeyPatch) -> list[tuple[str, str, dict[str, Any]]]:
    events: list[tuple[str, str, dict[str, Any]]] = []

    async def _fake_publish(stream: str, event_type: str, payload: dict[str, Any]) -> str:
        events.append((stream, event_type, payload))
        return "1-1"

    monkeypatch.setattr("modules.directory.reviews_admin_router.publish", _fake_publish)
    return events


@pytest.fixture
async def api(db_session: AsyncSession) -> AsyncIterator[tuple[httpx.AsyncClient, AsyncSession]]:
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
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="https://api.test") as client:
        yield client, db_session


async def _business(session: AsyncSession) -> Business:
    return await service.create_business(
        session, owner_user_id=OWNER, name="Agri Shop", type_="shop", primary_pincode="641001"
    )


async def _pending_review(session: AsyncSession, business: Business, rating: int = 4) -> Review:
    review = Review(
        author_user_id=AUTHOR, target_type="business", target_id=business.id, rating=rating
    )
    session.add(review)
    await session.flush()
    return review


async def test_moderation_requires_role(
    api: tuple[httpx.AsyncClient, AsyncSession],
) -> None:
    http, session = api
    business = await _business(session)
    review = await _pending_review(session, business)

    assert (await http.get("/admin/reviews")).status_code == 401
    assert (await http.get("/admin/reviews", headers=_as(PLAIN))).status_code == 403
    assert (
        await http.post(f"/admin/reviews/{review.id}/approve", headers=_as(PLAIN))
    ).status_code == 403
    assert (await http.get("/admin/reviews", headers=_as(ADMIN, "staff"))).status_code == 200


async def test_approve_flow(
    api: tuple[httpx.AsyncClient, AsyncSession],
    published: list[tuple[str, str, dict[str, Any]]],
) -> None:
    http, session = api
    business = await _business(session)
    review = await _pending_review(session, business)

    resp = await http.post(f"/admin/reviews/{review.id}/approve", headers=_as(ADMIN, "staff"))
    assert resp.status_code == 200
    assert resp.json()["moderation_status"] == "approved"

    await session.refresh(review)
    assert review.moderation_status == "approved"

    agg = await session.scalar(
        select(RatingAggregate).where(
            RatingAggregate.target_type == "business", RatingAggregate.target_id == business.id
        )
    )
    assert agg is not None
    assert agg.rating_count == 1

    entry = await session.scalar(
        select(AuditEntry).where(AuditEntry.action == "reviews.review_approved")
    )
    assert entry is not None
    assert entry.target_id == str(review.id)

    assert published == [
        (
            "directory",
            "review.approved",
            {
                "user_id": str(AUTHOR),
                "review_id": str(review.id),
                "target_type": "business",
                "target_id": str(business.id),
                "vars": {},
            },
        )
    ]


async def test_reject_requires_note(
    api: tuple[httpx.AsyncClient, AsyncSession],
    published: list[tuple[str, str, dict[str, Any]]],
) -> None:
    http, session = api
    business = await _business(session)
    review = await _pending_review(session, business)

    no_note = await http.post(
        f"/admin/reviews/{review.id}/reject", json={}, headers=_as(ADMIN, "staff")
    )
    assert no_note.status_code == 422

    with_note = await http.post(
        f"/admin/reviews/{review.id}/reject",
        json={"note": "spam content"},
        headers=_as(ADMIN, "staff"),
    )
    assert with_note.status_code == 200
    assert with_note.json()["moderation_status"] == "rejected"
    assert published == []


async def test_decide_only_from_pending(
    api: tuple[httpx.AsyncClient, AsyncSession],
) -> None:
    http, session = api
    business = await _business(session)
    review = await _pending_review(session, business)

    first = await http.post(f"/admin/reviews/{review.id}/approve", headers=_as(ADMIN, "staff"))
    assert first.status_code == 200

    second = await http.post(f"/admin/reviews/{review.id}/approve", headers=_as(ADMIN, "staff"))
    assert second.status_code == 409


async def test_reject_after_approve_recomputes_nothing(
    api: tuple[httpx.AsyncClient, AsyncSession],
) -> None:
    http, session = api
    business = await _business(session)
    review = await _pending_review(session, business)

    approve = await http.post(f"/admin/reviews/{review.id}/approve", headers=_as(ADMIN, "staff"))
    assert approve.status_code == 200

    reject = await http.post(
        f"/admin/reviews/{review.id}/reject",
        json={"note": "changed my mind"},
        headers=_as(ADMIN, "staff"),
    )
    assert reject.status_code == 409

    agg = await session.scalar(
        select(RatingAggregate).where(
            RatingAggregate.target_type == "business", RatingAggregate.target_id == business.id
        )
    )
    assert agg is not None
    assert agg.rating_count == 1
