"""modules/ads admin CRUD (D21): campaigns, creatives, placements.

Creatives always land `pending` - approval is the unified moderation queue's
job (Task 7), never this router. No events publish here (ads CRUD is
silent)."""

import uuid
from collections.abc import AsyncIterator

import httpx
import pytest
from fastapi import Request
from sqlalchemy.ext.asyncio import AsyncSession

from main import create_app
from shared.db import get_session
from shared.lookups import BusinessRef, register_business_resolver
from shared.security import register_principal_resolver

pytestmark = pytest.mark.asyncio

ADMIN = uuid.uuid4()
KNOWN_BUSINESS = uuid.uuid4()
UNKNOWN_BUSINESS = uuid.uuid4()


class _Principal:
    def __init__(self, user_id: uuid.UUID, roles: tuple[str, ...]) -> None:
        self.user_id = user_id
        self.roles = roles


def _as(user_id: uuid.UUID, roles: str) -> dict[str, str]:
    return {"x-test-user": str(user_id), "x-test-roles": roles}


async def _biz_resolver(session: AsyncSession, business_id: uuid.UUID) -> BusinessRef | None:
    if business_id == KNOWN_BUSINESS:
        return BusinessRef(id=business_id, owner_user_id=uuid.uuid4(), name="Kovai Mills")
    return None


@pytest.fixture
async def api(db_session: AsyncSession) -> AsyncIterator[httpx.AsyncClient]:
    app = create_app()
    register_business_resolver(_biz_resolver)  # after create_app(): D20 pattern

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
        yield client


def _campaign_body(**overrides: object) -> dict[str, object]:
    body: dict[str, object] = {
        "advertiser_business_id": str(KNOWN_BUSINESS),
        "name": "Kovai Mills - kharif push",
        "budget_display": "Rs 50,000/mo",
        "flight_start": "2026-08-01",
        "flight_end": "2026-09-01",
    }
    body.update(overrides)
    return body


async def _create_campaign(client: httpx.AsyncClient) -> str:
    r = await client.post(
        "/admin/ads/campaigns", json=_campaign_body(), headers=_as(ADMIN, "staff")
    )
    assert r.status_code == 201, r.text
    campaign_id: str = r.json()["id"]
    return campaign_id


def _creative_body(campaign_id: str, **overrides: object) -> dict[str, object]:
    body: dict[str, object] = {
        "campaign_id": campaign_id,
        "media_keys": ["ads/creative-1.jpg"],
        "copy": {"en": {"title": "Kharif seeds now live", "body": "Book your order today."}},
        "target_url": "https://kovaimills.example.com/offers",
    }
    body.update(overrides)
    return body


# ---------------------------------------------------------------------------
# 403 non-staff


async def test_non_staff_403(api: httpx.AsyncClient) -> None:
    r = await api.post("/admin/ads/campaigns", json=_campaign_body(), headers=_as(ADMIN, "user"))
    assert r.status_code == 403


# ---------------------------------------------------------------------------
# campaigns


async def test_campaign_create_happy(api: httpx.AsyncClient) -> None:
    r = await api.post("/admin/ads/campaigns", json=_campaign_body(), headers=_as(ADMIN, "staff"))
    assert r.status_code == 201, r.text
    body = r.json()
    assert body["status"] == "draft"
    assert body["advertiser_business_id"] == str(KNOWN_BUSINESS)
    assert uuid.UUID(body["id"])


async def test_campaign_create_unknown_business_422(api: httpx.AsyncClient) -> None:
    r = await api.post(
        "/admin/ads/campaigns",
        json=_campaign_body(advertiser_business_id=str(UNKNOWN_BUSINESS)),
        headers=_as(ADMIN, "staff"),
    )
    assert r.status_code == 422
    assert r.json()["detail"] == "unknown_business"


async def test_campaign_status_flip(api: httpx.AsyncClient) -> None:
    campaign_id = await _create_campaign(api)
    r = await api.post(
        f"/admin/ads/campaigns/{campaign_id}/status",
        json={"status": "active"},
        headers=_as(ADMIN, "staff"),
    )
    assert r.status_code == 200, r.text
    assert r.json()["status"] == "active"


async def test_campaign_list_cursor_pagination(api: httpx.AsyncClient) -> None:
    for _ in range(3):
        await _create_campaign(api)
    r1 = await api.get("/admin/ads/campaigns?limit=2", headers=_as(ADMIN, "staff"))
    assert r1.status_code == 200
    page1 = r1.json()
    assert len(page1["items"]) == 2
    assert page1["next_cursor"] is not None

    r2 = await api.get(
        f"/admin/ads/campaigns?limit=2&cursor={page1['next_cursor']}",
        headers=_as(ADMIN, "staff"),
    )
    assert r2.status_code == 200
    page2 = r2.json()
    assert len(page2["items"]) == 1
    seen_ids = {item["id"] for item in page1["items"]} | {item["id"] for item in page2["items"]}
    assert len(seen_ids) == 3


# ---------------------------------------------------------------------------
# creatives


async def test_creative_created_pending(api: httpx.AsyncClient) -> None:
    campaign_id = await _create_campaign(api)
    r = await api.post(
        "/admin/ads/creatives", json=_creative_body(campaign_id), headers=_as(ADMIN, "staff")
    )
    assert r.status_code == 201, r.text
    body = r.json()
    assert body["moderation_status"] == "pending"
    assert body["copy"]["en"]["title"] == "Kharif seeds now live"


async def test_creative_target_url_javascript_scheme_422(api: httpx.AsyncClient) -> None:
    campaign_id = await _create_campaign(api)
    r = await api.post(
        "/admin/ads/creatives",
        json=_creative_body(campaign_id, target_url="javascript:alert(1)"),
        headers=_as(ADMIN, "staff"),
    )
    assert r.status_code == 422


async def test_creative_target_url_data_scheme_422(api: httpx.AsyncClient) -> None:
    campaign_id = await _create_campaign(api)
    r = await api.post(
        "/admin/ads/creatives",
        json=_creative_body(campaign_id, target_url="data:text/html,<script>1</script>"),
        headers=_as(ADMIN, "staff"),
    )
    assert r.status_code == 422


async def test_creative_copy_missing_en_422(api: httpx.AsyncClient) -> None:
    campaign_id = await _create_campaign(api)
    r = await api.post(
        "/admin/ads/creatives",
        json=_creative_body(
            campaign_id, copy={"ta": {"title": "Only Tamil", "body": "No English"}}
        ),
        headers=_as(ADMIN, "staff"),
    )
    assert r.status_code == 422


async def test_creative_list_filters_by_campaign(api: httpx.AsyncClient) -> None:
    campaign_id = await _create_campaign(api)
    other_campaign_id = await _create_campaign(api)
    await api.post(
        "/admin/ads/creatives", json=_creative_body(campaign_id), headers=_as(ADMIN, "staff")
    )
    await api.post(
        "/admin/ads/creatives",
        json=_creative_body(other_campaign_id),
        headers=_as(ADMIN, "staff"),
    )
    r = await api.get(
        f"/admin/ads/creatives?campaign_id={campaign_id}", headers=_as(ADMIN, "staff")
    )
    assert r.status_code == 200
    body = r.json()
    assert len(body["items"]) == 1
    assert body["items"][0]["campaign_id"] == campaign_id


async def test_creative_media_unknown_creative_404(api: httpx.AsyncClient) -> None:
    r = await api.get(f"/admin/ads/creatives/{uuid.uuid4()}/media/0", headers=_as(ADMIN, "staff"))
    assert r.status_code == 404


async def test_creative_media_index_out_of_range_404(api: httpx.AsyncClient) -> None:
    campaign_id = await _create_campaign(api)
    r = await api.post(
        "/admin/ads/creatives",
        json=_creative_body(campaign_id, media_keys=[]),
        headers=_as(ADMIN, "staff"),
    )
    creative_id = r.json()["id"]
    r2 = await api.get(f"/admin/ads/creatives/{creative_id}/media/0", headers=_as(ADMIN, "staff"))
    assert r2.status_code == 404


# ---------------------------------------------------------------------------
# placements


async def test_placement_unknown_slot_422(api: httpx.AsyncClient) -> None:
    campaign_id = await _create_campaign(api)
    r = await api.post(
        "/admin/ads/placements",
        json={"campaign_id": campaign_id, "slot_key": "homepage_hero", "weight": 1},
        headers=_as(ADMIN, "staff"),
    )
    assert r.status_code == 422
    assert r.json()["detail"] == "unknown_slot_key"


async def test_placement_geo_target_unknown_key_422(api: httpx.AsyncClient) -> None:
    campaign_id = await _create_campaign(api)
    r = await api.post(
        "/admin/ads/placements",
        json={
            "campaign_id": campaign_id,
            "slot_key": "directory_browse",
            "geo_target": {"village": "x"},
            "weight": 1,
        },
        headers=_as(ADMIN, "staff"),
    )
    assert r.status_code == 422


async def test_placement_create_and_status_flip(api: httpx.AsyncClient) -> None:
    campaign_id = await _create_campaign(api)
    r = await api.post(
        "/admin/ads/placements",
        json={
            "campaign_id": campaign_id,
            "slot_key": "directory_browse",
            "geo_target": {"state": 33},
            "weight": 2,
        },
        headers=_as(ADMIN, "staff"),
    )
    assert r.status_code == 201, r.text
    body = r.json()
    assert body["status"] == "active"
    assert body["geo_target"] == {"state": 33}
    placement_id = body["id"]

    r2 = await api.post(
        f"/admin/ads/placements/{placement_id}/status",
        json={"status": "paused"},
        headers=_as(ADMIN, "staff"),
    )
    assert r2.status_code == 200, r2.text
    assert r2.json()["status"] == "paused"


async def test_placement_list_filters_by_slot_key(api: httpx.AsyncClient) -> None:
    campaign_id = await _create_campaign(api)
    await api.post(
        "/admin/ads/placements",
        json={"campaign_id": campaign_id, "slot_key": "directory_browse", "weight": 1},
        headers=_as(ADMIN, "staff"),
    )
    r = await api.get(
        "/admin/ads/placements?slot_key=directory_browse", headers=_as(ADMIN, "staff")
    )
    assert r.status_code == 200
    body = r.json()
    assert len(body["items"]) == 1
    assert body["items"][0]["slot_key"] == "directory_browse"
