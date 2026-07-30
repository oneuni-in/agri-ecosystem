"""Reviews API (D18.A): login-gated POST with target validation + one-per-user
uniqueness, public list/summary reads. Principal injection mirrors
test_directory_router.py (x-test-user header resolver)."""

import uuid
from collections.abc import AsyncIterator

import httpx
import pytest
from fastapi import Request
from sqlalchemy.ext.asyncio import AsyncSession

from main import create_app
from modules.directory import catalog_service, service
from modules.directory.catalog_models import Product
from modules.directory.models import Business
from modules.directory.reviews_models import Review
from modules.directory.reviews_service import recompute_aggregate
from shared.db import get_session
from shared.security import register_principal_resolver

pytestmark = pytest.mark.asyncio

USER_A = uuid.uuid4()
USER_B = uuid.uuid4()


class _Principal:
    def __init__(self, user_id: uuid.UUID) -> None:
        self.user_id = user_id
        self.roles = ("user",)


def _as(user_id: uuid.UUID) -> dict[str, str]:
    return {"x-test-user": str(user_id)}


@pytest.fixture
async def api(db_session: AsyncSession) -> AsyncIterator[tuple[httpx.AsyncClient, AsyncSession]]:
    app = create_app()

    async def _session_override() -> AsyncIterator[AsyncSession]:
        yield db_session

    async def _resolver(request: Request, session: AsyncSession) -> object | None:
        header = request.headers.get("x-test-user")
        return _Principal(uuid.UUID(header)) if header else None

    app.dependency_overrides[get_session] = _session_override
    register_principal_resolver(_resolver)
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="https://api.test") as client:
        yield client, db_session


async def _business(
    session: AsyncSession, owner: uuid.UUID, *, btype: str = "shop", name: str = "Agri Shop"
) -> Business:
    return await service.create_business(
        session, owner_user_id=owner, name=name, type_=btype, primary_pincode="641001"
    )


async def _pending_product(session: AsyncSession, owner: uuid.UUID, business: Business) -> Product:
    return await catalog_service.create_product(
        session,
        owner_user_id=owner,
        business_id=business.id,
        vertical_slug="milk",
        name="A2 Milk",
        specs={"category": "milk", "milk_type": "cow"},
    )


async def _approved_product(session: AsyncSession, owner: uuid.UUID, business: Business) -> Product:
    product = await _pending_product(session, owner, business)
    return await catalog_service.moderate_product(session, product_id=product.id, approve=True)


def _review_body(target_type: str, target_id: uuid.UUID, rating: int = 4) -> dict[str, object]:
    return {
        "target_type": target_type,
        "target_id": str(target_id),
        "rating": rating,
        "body": {"en": "Good service"},
    }


async def test_post_review_requires_auth(api: tuple[httpx.AsyncClient, AsyncSession]) -> None:
    http, _ = api
    resp = await http.post("/reviews", json=_review_body("business", uuid.uuid4()))
    assert resp.status_code == 401


async def test_post_review_defaults_pending(api: tuple[httpx.AsyncClient, AsyncSession]) -> None:
    http, session = api
    b = await _business(session, USER_A)
    resp = await http.post("/reviews", json=_review_body("business", b.id), headers=_as(USER_B))
    assert resp.status_code == 201
    body = resp.json()
    assert body["moderation_status"] == "pending"  # non-negotiable 1b
    assert body["target_type"] == "business"
    assert body["target_id"] == str(b.id)
    assert body["rating"] == 4
    assert body["body"] == {"en": "Good service"}


async def test_one_review_per_user_per_target(
    api: tuple[httpx.AsyncClient, AsyncSession],
) -> None:
    http, session = api
    b = await _business(session, USER_A)
    first = await http.post("/reviews", json=_review_body("business", b.id), headers=_as(USER_B))
    assert first.status_code == 201
    second = await http.post("/reviews", json=_review_body("business", b.id), headers=_as(USER_B))
    assert second.status_code == 409
    third = await http.post("/reviews", json=_review_body("business", b.id), headers=_as(USER_A))
    assert third.status_code == 201


async def test_rating_bounds(api: tuple[httpx.AsyncClient, AsyncSession]) -> None:
    http, _ = api
    target_id = uuid.uuid4()
    too_low = await http.post(
        "/reviews", json=_review_body("business", target_id, rating=0), headers=_as(USER_A)
    )
    assert too_low.status_code == 422
    too_high = await http.post(
        "/reviews", json=_review_body("business", target_id, rating=6), headers=_as(USER_A)
    )
    assert too_high.status_code == 422


async def test_bad_locale_body_400(api: tuple[httpx.AsyncClient, AsyncSession]) -> None:
    http, session = api
    b = await _business(session, USER_A)
    body = _review_body("business", b.id)
    body["body"] = {"xx": "hi"}
    resp = await http.post("/reviews", json=body, headers=_as(USER_B))
    assert resp.status_code == 400


async def test_unknown_target_404(api: tuple[httpx.AsyncClient, AsyncSession]) -> None:
    http, _ = api
    resp = await http.post(
        "/reviews", json=_review_body("business", uuid.uuid4()), headers=_as(USER_A)
    )
    assert resp.status_code == 404


async def test_vendor_target_requires_vendor_type(
    api: tuple[httpx.AsyncClient, AsyncSession],
) -> None:
    http, session = api
    shop = await _business(session, USER_A, btype="shop")
    shop_resp = await http.post(
        "/reviews", json=_review_body("vendor", shop.id), headers=_as(USER_B)
    )
    assert shop_resp.status_code == 404

    vendor = await _business(session, USER_A, btype="vendor", name="Agri Vendor")
    vendor_resp = await http.post(
        "/reviews", json=_review_body("vendor", vendor.id), headers=_as(USER_B)
    )
    assert vendor_resp.status_code == 201


async def test_product_target_must_be_approved(
    api: tuple[httpx.AsyncClient, AsyncSession],
) -> None:
    http, session = api
    business = await _business(session, USER_A)
    pending = await _pending_product(session, USER_A, business)
    pending_resp = await http.post(
        "/reviews", json=_review_body("product", pending.id), headers=_as(USER_B)
    )
    assert pending_resp.status_code == 404

    approved = await _approved_product(session, USER_A, business)
    approved_resp = await http.post(
        "/reviews", json=_review_body("product", approved.id), headers=_as(USER_B)
    )
    assert approved_resp.status_code == 201


async def test_public_list_shows_only_approved(
    api: tuple[httpx.AsyncClient, AsyncSession],
) -> None:
    http, session = api
    business = await _business(session, USER_A)
    pending = Review(
        author_user_id=uuid.uuid4(), target_type="business", target_id=business.id, rating=3
    )
    approved = Review(
        author_user_id=uuid.uuid4(),
        target_type="business",
        target_id=business.id,
        rating=5,
        moderation_status="approved",
    )
    session.add_all([pending, approved])
    await session.flush()

    resp = await http.get(
        "/reviews", params={"target_type": "business", "target_id": str(business.id)}
    )
    assert resp.status_code == 200
    payload = resp.json()
    assert "next_cursor" in payload
    assert [item["id"] for item in payload["items"]] == [str(approved.id)]
    assert payload["items"][0]["moderation_status"] == "approved"


async def test_summary_math(api: tuple[httpx.AsyncClient, AsyncSession]) -> None:
    http, session = api
    business = await _business(session, USER_A)
    session.add_all(
        [
            Review(
                author_user_id=uuid.uuid4(),
                target_type="business",
                target_id=business.id,
                rating=4,
                moderation_status="approved",
            ),
            Review(
                author_user_id=uuid.uuid4(),
                target_type="business",
                target_id=business.id,
                rating=5,
                moderation_status="approved",
            ),
        ]
    )
    await session.flush()
    await recompute_aggregate(session, target_type="business", target_id=business.id)

    resp = await http.get(
        "/reviews/summary", params={"target_type": "business", "target_id": str(business.id)}
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["rating_avg"] == "4.50"
    assert body["rating_count"] == 2

    unknown = await http.get(
        "/reviews/summary", params={"target_type": "business", "target_id": str(uuid.uuid4())}
    )
    assert unknown.status_code == 200
    unknown_body = unknown.json()
    assert unknown_body["rating_avg"] is None
    assert unknown_body["rating_count"] == 0


async def test_reviews_public_routes_are_registered() -> None:
    app = create_app()
    assert "/reviews" in app.state.public_routes
    assert "/reviews/summary" in app.state.public_routes
