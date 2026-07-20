"""D19 Task 5: unified public search API (GET /search). Real Meilisearch
(the `meili` fixture, ADR-0007) - docs are seeded through the same
`indexing.apply_event` path production events go through (Task 3), then
exercised over HTTP through the app, mirroring the httpx.ASGITransport
harness in tests/test_directory_router.py."""

import base64
import json
from collections.abc import AsyncIterator
from typing import Any

import httpx
import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from main import create_app
from modules.search import indexing
from modules.search import service as search_service
from shared.db import get_session
from shared.events import Event

pytestmark = pytest.mark.asyncio


@pytest.fixture
async def api(db_session: AsyncSession) -> AsyncIterator[httpx.AsyncClient]:
    app = create_app()

    async def _session_override() -> AsyncIterator[AsyncSession]:
        yield db_session

    app.dependency_overrides[get_session] = _session_override
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="https://api.test") as client:
        yield client


def _snap(doc_id: str, **overrides: Any) -> dict[str, Any]:
    base: dict[str, Any] = {
        "id": doc_id,
        "kind": "business",
        "sites": ["milk"],
        "name": "Doc",
        "slug": "doc",
        "business_name": None,
        "business_slug": None,
        "description": None,
        "categories": [],
        "vertical": None,
        "district": None,
        "state": None,
        "covered_pincodes": [],
        "verified": False,
        "price_display": None,
        "_geo": None,
    }
    base.update(overrides)
    return base


async def _seed(doc_id: str, **overrides: Any) -> None:
    snapshot = _snap(doc_id, **overrides)
    await indexing.apply_event(
        Event(
            id=f"evt-{doc_id}",
            type="business.created",
            payload={"business_id": doc_id, "doc_id": doc_id, "snapshot": snapshot},
        )
    )


async def test_search_basic(api: httpx.AsyncClient, meili: None) -> None:
    await indexing.ensure_indexes()
    await _seed("business_kovai001", name="Kovai Dairy", slug="kovai-dairy")
    # "dairi" is a one-letter substitution of "dairy" - both >=5 chars, inside
    # Meili's default minWordSizeForTypos.oneTypo threshold.
    resp = await api.get("/search", params={"site": "milk", "q": "kovai dairi"})
    assert resp.status_code == 200
    body = resp.json()
    assert any(h["id"] == "business_kovai001" for h in body["items"])


async def test_pincode_boost(api: httpx.AsyncClient, meili: None, tn_geo_sample: None) -> None:
    await indexing.ensure_indexes()
    # Identical name on both docs -> tied relevance; only _geo differs, so a
    # pincode boost is the only thing that can break the tie.
    await _seed(
        "business_near0001",
        name="Kovai AgriMart",
        slug="kovai-agrimart-near",
        _geo={"lat": 10.9232, "lng": 76.9686},  # ~0km from 641001 centroid
    )
    await _seed(
        "business_far0001",
        name="Kovai AgriMart",
        slug="kovai-agrimart-far",
        _geo={"lat": 13.079, "lng": 80.287},  # Chennai - ~430km away
    )
    resp = await api.get(
        "/search", params={"site": "milk", "q": "Kovai AgriMart", "pincode": "641001"}
    )
    assert resp.status_code == 200
    ids = [h["id"] for h in resp.json()["items"]]
    assert ids.index("business_near0001") < ids.index("business_far0001")


async def test_covered_filter(api: httpx.AsyncClient, meili: None, tn_geo_sample: None) -> None:
    await indexing.ensure_indexes()
    await _seed(
        "business_covered001",
        name="Anbu Milk Depot",
        slug="anbu-milk-depot",
        covered_pincodes=["641001"],
    )
    await _seed(
        "business_uncovered001",
        name="Anbu Milk Depot Two",
        slug="anbu-milk-depot-two",
        covered_pincodes=["600001"],
    )
    resp = await api.get(
        "/search",
        params={
            "site": "milk",
            "q": "Anbu Milk Depot",
            "pincode": "641001",
            "covered": "true",
        },
    )
    assert resp.status_code == 200
    ids = {h["id"] for h in resp.json()["items"]}
    assert ids == {"business_covered001"}


async def test_cursor_walk(api: httpx.AsyncClient, meili: None) -> None:
    await indexing.ensure_indexes()
    for suffix in ("alpha", "beta", "gamma"):
        await _seed(
            f"business_vendor_{suffix}",
            name=f"Vendor {suffix.capitalize()}",
            slug=f"vendor-{suffix}",
        )
    params: dict[str, str | int] = {"site": "milk", "q": "vendor", "limit": 2}
    page1 = await api.get("/search", params=params)
    assert page1.status_code == 200
    body1 = page1.json()
    assert len(body1["items"]) == 2
    assert body1["next_cursor"] is not None

    page2 = await api.get("/search", params={**params, "cursor": body1["next_cursor"]})
    assert page2.status_code == 200
    body2 = page2.json()
    assert len(body2["items"]) == 1
    assert body2["next_cursor"] is None

    seen_ids = [h["id"] for h in body1["items"]] + [h["id"] for h in body2["items"]]
    assert len(seen_ids) == len(set(seen_ids)) == 3

    tampered = await api.get("/search", params={**params, "cursor": "not-a-real-cursor"})
    assert tampered.status_code == 400
    assert tampered.json()["detail"] == "invalid_cursor"

    mismatched = await api.get(
        "/search",
        params={"site": "milk", "q": "somethingelse", "cursor": body1["next_cursor"]},
    )
    assert mismatched.status_code == 400
    assert mismatched.json()["detail"] == "invalid_cursor"


async def test_no_pii_in_response(api: httpx.AsyncClient, meili: None) -> None:
    await indexing.ensure_indexes()
    await _seed("business_pii0001", name="PII Guard Dairy", slug="pii-guard-dairy")
    resp = await api.get("/search", params={"site": "milk", "q": "PII Guard Dairy"})
    assert resp.status_code == 200
    assert "phone" not in resp.text
    assert "email" not in resp.text


async def test_unknown_site_404(api: httpx.AsyncClient, meili: None) -> None:
    resp = await api.get("/search", params={"site": "bogus", "q": "anything"})
    assert resp.status_code == 404
    assert resp.json()["detail"] == "unknown_site"


async def test_kind_filter_injection_rejected(api: httpx.AsyncClient) -> None:
    """kind is a closed Literal set (search_sync only ever emits "business"/
    "product"); an attempt to smuggle an ` OR ...` clause into the Meili
    filter expression must 422, not 200 with hits leaked via a boolean
    filter-injection oracle over covered_pincodes/_geo (filterable but never
    displayed). No meili fixture needed - this never reaches run_search."""
    resp = await api.get(
        "/search",
        params={"site": "milk", "q": "x", "kind": 'business" OR covered_pincodes = "641001'},
    )
    assert resp.status_code == 422


async def test_vertical_filter_injection_rejected(api: httpx.AsyncClient) -> None:
    """vertical is constrained to the slug charset; anything outside
    [a-z0-9-] (quotes, spaces, `=`) must 422 rather than reach the Meili
    filter string verbatim."""
    resp = await api.get(
        "/search",
        params={"site": "milk", "q": "x", "vertical": 'milk" OR _geoRadius(0,0,999999999)'},
    )
    assert resp.status_code == 422


async def test_cursor_bare_json_scalar_rejected(api: httpx.AsyncClient) -> None:
    """A cursor that is valid base64 + valid JSON but not the {"s", "h"}
    object we mint (e.g. base64 of a bare `123`) must 400, not crash the
    endpoint with an unhandled TypeError on data["s"]."""
    bogus = base64.urlsafe_b64encode(json.dumps(123).encode()).decode()
    resp = await api.get("/search", params={"site": "milk", "q": "x", "cursor": bogus})
    assert resp.status_code == 400
    assert resp.json()["detail"] == "invalid_cursor"

    bogus_null = base64.urlsafe_b64encode(json.dumps(None).encode()).decode()
    resp2 = await api.get("/search", params={"site": "milk", "q": "x", "cursor": bogus_null})
    assert resp2.status_code == 400
    assert resp2.json()["detail"] == "invalid_cursor"


async def test_cursor_max_depth_boundary_rejected(api: httpx.AsyncClient) -> None:
    """encode_search_cursor only ever mints next_start < MAX_DEPTH, so a
    legitimate cursor's start is always in [0, MAX_DEPTH). start == MAX_DEPTH
    is already outside anything we'd issue and must 400 at the boundary, not
    only once past it."""
    qhash = search_service._query_hash("milk", "x", None, None, None, False, 20)
    at_depth = search_service.encode_search_cursor(search_service.MAX_DEPTH, qhash)
    resp = await api.get("/search", params={"site": "milk", "q": "x", "cursor": at_depth})
    assert resp.status_code == 400
    assert resp.json()["detail"] == "invalid_cursor"

    past_depth = search_service.encode_search_cursor(search_service.MAX_DEPTH + 1, qhash)
    resp2 = await api.get("/search", params={"site": "milk", "q": "x", "cursor": past_depth})
    assert resp2.status_code == 400
    assert resp2.json()["detail"] == "invalid_cursor"


async def test_search_public_route_registered() -> None:
    app = create_app()
    assert "/search" in app.state.public_routes
