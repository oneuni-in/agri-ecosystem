"""D19 Task 1: search snapshot builders + the event publishes that carry them.

Snapshots are the ONLY index-worthy payload builders (ADR-0007) - the search
module never reads directory tables directly, so these payloads must be
PII-free ("fat" events) and every business/product write that can change
public visibility must re-publish one. See modules/directory/search_sync.py.
"""

import uuid
from collections.abc import AsyncIterator
from decimal import Decimal
from typing import Any

import httpx
import pytest
from fastapi import Request
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from main import create_app
from modules.directory import catalog_service, search_sync, service
from modules.directory.models import Category
from shared.db import get_session
from shared.security import register_principal_resolver

pytestmark = pytest.mark.asyncio

FORBIDDEN_KEYS = {"phone", "whatsapp", "email", "owner_user_id", "phone_last4"}


def _assert_no_pii(obj: object) -> None:
    if isinstance(obj, dict):
        assert not (set(obj) & FORBIDDEN_KEYS), f"PII key leaked: {set(obj) & FORBIDDEN_KEYS}"
        for v in obj.values():
            _assert_no_pii(v)
    elif isinstance(obj, list):
        for v in obj:
            _assert_no_pii(v)


# --- snapshot builders -------------------------------------------------


async def test_business_snapshot_visible(db_session: AsyncSession, tn_geo_sample: None) -> None:
    owner = uuid.uuid4()
    biz = await service.create_business(
        db_session,
        owner_user_id=owner,
        name="Kovai Dairy",
        type_="vendor",
        primary_pincode="641001",
    )
    await service.set_coverage(
        db_session,
        owner_user_id=owner,
        business_id=biz.id,
        pincodes=["641001", "641002"],
    )
    snap = await search_sync.business_snapshot(db_session, biz.id)
    assert snap is not None
    assert snap["id"] == f"business_{biz.id.hex}"
    assert snap["kind"] == "business"
    assert "agri" in snap["sites"]
    assert snap["name"] == "Kovai Dairy"
    assert snap["district"] == "Coimbatore"
    assert set(snap["covered_pincodes"]) == {"641001", "641002"}
    assert snap["verified"] is False
    _assert_no_pii(snap)


async def test_business_snapshot_none_when_soft_deleted(
    db_session: AsyncSession, tn_geo_sample: None
) -> None:
    biz = await service.create_business(
        db_session,
        owner_user_id=uuid.uuid4(),
        name="Gone",
        type_="vendor",
        primary_pincode="641001",
    )
    from datetime import UTC, datetime

    biz.deleted_at = datetime.now(UTC)
    await db_session.flush()
    assert await search_sync.business_snapshot(db_session, biz.id) is None


async def test_business_snapshot_none_when_suspended(
    db_session: AsyncSession, tn_geo_sample: None
) -> None:
    biz = await service.create_business(
        db_session,
        owner_user_id=uuid.uuid4(),
        name="Suspended Farm",
        type_="vendor",
        primary_pincode="641001",
    )
    biz.status = "suspended"
    await db_session.flush()
    assert await search_sync.business_snapshot(db_session, biz.id) is None


async def test_business_snapshot_geo_from_branch(
    db_session: AsyncSession, tn_geo_sample: None
) -> None:
    owner = uuid.uuid4()
    biz = await service.create_business(
        db_session,
        owner_user_id=owner,
        name="Branch Farm",
        type_="vendor",
        primary_pincode="641001",  # Coimbatore centroid - deliberately different from the branch
    )
    await service.add_branch(
        db_session,
        owner_user_id=owner,
        business_id=biz.id,
        address="1 Main Rd",
        state="Tamil Nadu",
        district="Chennai",
        pincode="600001",
        lat=Decimal("13.079000"),
        lng=Decimal("80.287000"),
    )
    snap = await search_sync.business_snapshot(db_session, biz.id)
    assert snap is not None
    assert snap["_geo"] == {"lat": 13.079, "lng": 80.287}


async def test_business_snapshot_no_geo_match(
    db_session: AsyncSession, tn_geo_sample: None
) -> None:
    owner = uuid.uuid4()
    biz = await service.create_business(
        db_session,
        owner_user_id=owner,
        name="Unmapped Farm",
        type_="vendor",
        primary_pincode="999999",  # 6-digit, valid shape, absent from geo.pincodes
    )
    snap = await search_sync.business_snapshot(db_session, biz.id)
    assert snap is not None
    assert snap["district"] is None
    assert snap["state"] is None
    assert snap["_geo"] is None


async def test_business_in_milk_site_when_dairy_category(
    db_session: AsyncSession, tn_geo_sample: None
) -> None:
    owner = uuid.uuid4()
    biz = await service.create_business(
        db_session,
        owner_user_id=owner,
        name="Dairy Farm",
        type_="vendor",
        primary_pincode="641001",
    )
    category = await db_session.scalar(select(Category).where(Category.slug == "dairy"))
    assert category is not None
    await service.assign_categories(
        db_session, owner_user_id=owner, business_id=biz.id, category_ids=[category.id]
    )
    snap = await search_sync.business_snapshot(db_session, biz.id)
    assert snap is not None
    assert "milk" in snap["sites"]


async def test_product_snapshot_requires_approved(
    db_session: AsyncSession, tn_geo_sample: None
) -> None:
    # "milk" vertical + its v1 spec schema are seeded by migration 0018 - no
    # extra fixture needed (see test_catalog_service.py precedent).
    owner = uuid.uuid4()
    biz = await service.create_business(
        db_session,
        owner_user_id=owner,
        name="Kovai Dairy",
        type_="vendor",
        primary_pincode="641001",
    )
    prod = await catalog_service.create_product(
        db_session,
        owner_user_id=owner,
        business_id=biz.id,
        vertical_slug="milk",
        name="A2 Milk 500ml",
        specs={"milk_type": "a2"},
    )
    assert await search_sync.product_snapshot(db_session, prod.id) is None  # pending
    await catalog_service.moderate_product(db_session, product_id=prod.id, approve=True)
    snap = await search_sync.product_snapshot(db_session, prod.id)
    assert snap is not None
    assert snap["sites"] == ["agri", "milk"]
    assert snap["business_slug"] == biz.slug
    _assert_no_pii(snap)


async def test_product_snapshot_none_when_business_suspended(
    db_session: AsyncSession, tn_geo_sample: None
) -> None:
    owner = uuid.uuid4()
    biz = await service.create_business(
        db_session,
        owner_user_id=owner,
        name="Suspended Dairy",
        type_="vendor",
        primary_pincode="641001",
    )
    prod = await catalog_service.create_product(
        db_session,
        owner_user_id=owner,
        business_id=biz.id,
        vertical_slug="milk",
        name="A2 Milk",
        specs={"milk_type": "cow"},
    )
    await catalog_service.moderate_product(db_session, product_id=prod.id, approve=True)
    biz.status = "suspended"
    await db_session.flush()
    assert await search_sync.product_snapshot(db_session, prod.id) is None


async def test_business_event_payload_carries_doc_id(
    db_session: AsyncSession, tn_geo_sample: None
) -> None:
    biz = await service.create_business(
        db_session,
        owner_user_id=uuid.uuid4(),
        name="Payload Farm",
        type_="vendor",
        primary_pincode="641001",
    )
    payload = await search_sync.business_event_payload(db_session, biz.id)
    assert payload["doc_id"] == f"business_{biz.id.hex}"
    assert payload["business_id"] == str(biz.id)
    assert payload["snapshot"] is not None
    _assert_no_pii(payload)


async def test_business_event_payload_doc_id_present_when_snapshot_null(
    db_session: AsyncSession, tn_geo_sample: None
) -> None:
    biz = await service.create_business(
        db_session,
        owner_user_id=uuid.uuid4(),
        name="Deleted Farm",
        type_="vendor",
        primary_pincode="641001",
    )
    from datetime import UTC, datetime

    biz.deleted_at = datetime.now(UTC)
    await db_session.flush()
    payload = await search_sync.business_event_payload(db_session, biz.id)
    assert payload["doc_id"] == f"business_{biz.id.hex}"
    assert payload["snapshot"] is None


async def test_product_event_payload_carries_doc_id(
    db_session: AsyncSession, tn_geo_sample: None
) -> None:
    owner = uuid.uuid4()
    biz = await service.create_business(
        db_session,
        owner_user_id=owner,
        name="Payload Dairy",
        type_="vendor",
        primary_pincode="641001",
    )
    prod = await catalog_service.create_product(
        db_session,
        owner_user_id=owner,
        business_id=biz.id,
        vertical_slug="milk",
        name="Payload Milk",
        specs={"milk_type": "cow"},
    )
    payload = await search_sync.product_event_payload(db_session, prod.id)
    assert payload["doc_id"] == f"product_{prod.id.hex}"
    assert payload["product_id"] == str(prod.id)
    assert payload["business_id"] == str(biz.id)
    assert payload["snapshot"] is None  # still pending
    _assert_no_pii(payload)


# --- publish wiring ----------------------------------------------------


class _Principal:
    def __init__(self, user_id: uuid.UUID, roles: tuple[str, ...] = ("user",)) -> None:
        self.user_id = user_id
        self.roles = roles


def _as(user_id: uuid.UUID, roles: str = "user") -> dict[str, str]:
    return {"x-test-user": str(user_id), "x-test-roles": roles}


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


@pytest.fixture
def captured_events(monkeypatch: pytest.MonkeyPatch) -> list[tuple[str, str, dict[str, Any]]]:
    """Capture best-effort event publishes across every directory router that
    imports `publish` by name (router.py, admin_router.py, catalog_router.py,
    catalog_admin_router.py all import it independently)."""
    events: list[tuple[str, str, dict[str, Any]]] = []

    async def fake_publish(stream: str, event_type: str, payload: dict[str, Any]) -> str:
        events.append((stream, event_type, payload))
        return "1-0"

    monkeypatch.setattr("modules.directory.router.publish", fake_publish)
    monkeypatch.setattr("modules.directory.admin_router.publish", fake_publish)
    monkeypatch.setattr("modules.directory.catalog_router.publish", fake_publish)
    monkeypatch.setattr("modules.directory.catalog_admin_router.publish", fake_publish)
    return events


CREATE_BODY = {"name": "Anbu Milk Farm", "type": "vendor", "primary_pincode": "641001"}


async def _business(
    session: AsyncSession, owner: uuid.UUID, name: str = "Coimbatore Dairy"
) -> service.Business:  # type: ignore[name-defined]
    return await service.create_business(
        session, owner_user_id=owner, name=name, type_="vendor", primary_pincode="641001"
    )


async def test_create_business_publishes_created(
    api: tuple[httpx.AsyncClient, AsyncSession],
    captured_events: list[tuple[str, str, dict[str, Any]]],
) -> None:
    http, _ = api
    owner = uuid.uuid4()
    resp = await http.post("/directory/businesses", json=CREATE_BODY, headers=_as(owner))
    assert resp.status_code == 201
    business_id = resp.json()["id"]
    matches = [e for e in captured_events if e[1] == "business.created"]
    assert len(matches) == 1
    stream, event_type, payload = matches[0]
    assert stream == "directory"
    assert payload["doc_id"] == f"business_{uuid.UUID(business_id).hex}"
    assert isinstance(payload["snapshot"], dict)


async def test_update_business_publishes_updated(
    api: tuple[httpx.AsyncClient, AsyncSession],
    captured_events: list[tuple[str, str, dict[str, Any]]],
) -> None:
    http, session = api
    owner = uuid.uuid4()
    biz = await _business(session, owner)
    resp = await http.patch(
        f"/directory/businesses/{biz.id}", json={"name": "Renamed Dairy"}, headers=_as(owner)
    )
    assert resp.status_code == 200
    types = [e[1] for e in captured_events]
    assert "business.updated" in types


async def test_rename_business_publishes_updated(
    api: tuple[httpx.AsyncClient, AsyncSession],
    captured_events: list[tuple[str, str, dict[str, Any]]],
) -> None:
    http, session = api
    owner = uuid.uuid4()
    biz = await _business(session, owner)
    resp = await http.post(
        f"/directory/businesses/{biz.id}/rename",
        json={"new_slug": "renamed-slug"},
        headers=_as(owner),
    )
    assert resp.status_code == 200
    types = [e[1] for e in captured_events]
    assert "business.updated" in types


async def test_add_branch_publishes_updated(
    api: tuple[httpx.AsyncClient, AsyncSession],
    captured_events: list[tuple[str, str, dict[str, Any]]],
) -> None:
    http, session = api
    owner = uuid.uuid4()
    biz = await _business(session, owner)
    resp = await http.post(
        f"/directory/businesses/{biz.id}/branches",
        json={
            "address": "1 Main Rd",
            "state": "Tamil Nadu",
            "district": "Coimbatore",
            "pincode": "641001",
        },
        headers=_as(owner),
    )
    assert resp.status_code == 201
    types = [e[1] for e in captured_events]
    assert "business.updated" in types


async def test_update_branch_publishes_updated(
    api: tuple[httpx.AsyncClient, AsyncSession],
    captured_events: list[tuple[str, str, dict[str, Any]]],
) -> None:
    http, session = api
    owner = uuid.uuid4()
    biz = await _business(session, owner)
    branch = await service.add_branch(
        session,
        owner_user_id=owner,
        business_id=biz.id,
        address="1 Main Rd",
        state="Tamil Nadu",
        district="Coimbatore",
        pincode="641001",
    )
    resp = await http.patch(
        f"/directory/branches/{branch.id}", json={"phone": "9999999999"}, headers=_as(owner)
    )
    assert resp.status_code == 200
    types = [e[1] for e in captured_events]
    assert "business.updated" in types


async def test_set_coverage_publishes_updated(
    api: tuple[httpx.AsyncClient, AsyncSession],
    captured_events: list[tuple[str, str, dict[str, Any]]],
) -> None:
    http, session = api
    owner = uuid.uuid4()
    biz = await _business(session, owner)
    resp = await http.put(
        f"/directory/businesses/{biz.id}/coverage",
        json={"pincodes": ["641001"]},
        headers=_as(owner),
    )
    assert resp.status_code == 200
    types = [e[1] for e in captured_events]
    assert "business.updated" in types


async def test_assign_categories_publishes_updated(
    api: tuple[httpx.AsyncClient, AsyncSession],
    captured_events: list[tuple[str, str, dict[str, Any]]],
) -> None:
    http, session = api
    owner = uuid.uuid4()
    biz = await _business(session, owner)
    category = await session.scalar(select(Category).where(Category.slug == "dairy"))
    assert category is not None
    resp = await http.put(
        f"/directory/businesses/{biz.id}/categories",
        json={"category_ids": [str(category.id)]},
        headers=_as(owner),
    )
    assert resp.status_code == 200
    types = [e[1] for e in captured_events]
    assert "business.updated" in types


async def test_claim_approve_publishes_claimed_and_updated(
    api: tuple[httpx.AsyncClient, AsyncSession],
    captured_events: list[tuple[str, str, dict[str, Any]]],
) -> None:
    http, session = api
    from modules.directory.models import Business

    business = Business(
        owner_user_id=None,
        name="Seeded Farm",
        slug=f"seeded-{uuid.uuid4().hex[:10]}",
        type="farm",
        primary_pincode="641001",
    )
    session.add(business)
    await session.flush()
    claimant = uuid.uuid4()
    claim_resp = await http.post(
        f"/directory/businesses/{business.id}/claim",
        files=[("files", ("doc.jpg", _jpeg(), "image/jpeg"))],
        headers=_as(claimant),
    )
    assert claim_resp.status_code == 201
    claim_id = claim_resp.json()["id"]
    admin = uuid.uuid4()
    approve = await http.post(
        f"/admin/directory/claims/{claim_id}/approve",
        json={"note": "checks out"},
        headers=_as(admin, "staff"),
    )
    assert approve.status_code == 200
    types = [e[1] for e in captured_events]
    assert "business.claimed" in types
    assert "business.updated" in types


async def test_verification_approve_publishes_updated(
    api: tuple[httpx.AsyncClient, AsyncSession],
    captured_events: list[tuple[str, str, dict[str, Any]]],
) -> None:
    http, session = api
    from modules.directory.models import Business

    owner = uuid.uuid4()
    business = Business(
        owner_user_id=owner,
        name="Owned Dairy",
        slug=f"owned-{uuid.uuid4().hex[:10]}",
        type="vendor",
        primary_pincode="641001",
    )
    session.add(business)
    await session.flush()
    created = await http.post(
        f"/directory/businesses/{business.id}/verification",
        files=[("files", ("doc.jpg", _jpeg(), "image/jpeg"))],
        headers=_as(owner),
    )
    assert created.status_code == 201
    verification_id = created.json()["id"]
    admin = uuid.uuid4()
    approve = await http.post(
        f"/admin/directory/verifications/{verification_id}/approve",
        json={"note": "docs valid"},
        headers=_as(admin, "staff"),
    )
    assert approve.status_code == 200
    types = [e[1] for e in captured_events]
    assert "directory.verification_approved" in types
    assert "business.updated" in types


async def test_verification_reject_publishes_updated(
    api: tuple[httpx.AsyncClient, AsyncSession],
    captured_events: list[tuple[str, str, dict[str, Any]]],
) -> None:
    """Unconditional per the D19 contract ("verification approve/reject"),
    even though a reject rarely flips the visible `verified` boolean."""
    http, session = api
    from modules.directory.models import Business

    owner = uuid.uuid4()
    business = Business(
        owner_user_id=owner,
        name="Rejected Verification Dairy",
        slug=f"owned-{uuid.uuid4().hex[:10]}",
        type="vendor",
        primary_pincode="641001",
    )
    session.add(business)
    await session.flush()
    created = await http.post(
        f"/directory/businesses/{business.id}/verification",
        files=[("files", ("doc.jpg", _jpeg(), "image/jpeg"))],
        headers=_as(owner),
    )
    assert created.status_code == 201
    verification_id = created.json()["id"]
    admin = uuid.uuid4()
    reject = await http.post(
        f"/admin/directory/verifications/{verification_id}/reject",
        json={"note": "document unreadable"},
        headers=_as(admin, "staff"),
    )
    assert reject.status_code == 200
    types = [e[1] for e in captured_events]
    assert "directory.verification_rejected" in types
    assert "business.updated" in types


def _jpeg() -> bytes:
    from io import BytesIO

    from PIL import Image

    buf = BytesIO()
    Image.new("RGB", (24, 24), "red").save(buf, format="JPEG")
    return buf.getvalue()


async def test_create_product_publishes_created(
    api: tuple[httpx.AsyncClient, AsyncSession],
    captured_events: list[tuple[str, str, dict[str, Any]]],
) -> None:
    http, session = api
    owner = uuid.uuid4()
    biz = await _business(session, owner)
    resp = await http.post(
        f"/catalog/businesses/{biz.id}/products",
        json={"vertical_slug": "milk", "name": "A2 Milk", "specs": {"milk_type": "a2"}},
        headers=_as(owner),
    )
    assert resp.status_code == 201
    product_id = resp.json()["id"]
    matches = [e for e in captured_events if e[1] == "product.created"]
    assert len(matches) == 1
    stream, event_type, payload = matches[0]
    assert stream == "directory"
    assert payload["doc_id"] == f"product_{uuid.UUID(product_id).hex}"
    assert payload["snapshot"] is None  # pending, not yet approved


async def test_update_product_and_moderation_approve_publish_updated(
    api: tuple[httpx.AsyncClient, AsyncSession],
    captured_events: list[tuple[str, str, dict[str, Any]]],
) -> None:
    http, session = api
    owner = uuid.uuid4()
    biz = await _business(session, owner)
    product = await catalog_service.create_product(
        session,
        owner_user_id=owner,
        business_id=biz.id,
        vertical_slug="milk",
        name="A2 Milk",
        specs={"milk_type": "a2"},
    )
    patched = await http.patch(
        f"/catalog/products/{product.id}",
        json={"price_display": "₹80/500ml"},
        headers=_as(owner),
    )
    assert patched.status_code == 200
    types = [e[1] for e in captured_events]
    assert "product.updated" in types
    captured_events.clear()
    admin = uuid.uuid4()
    approved = await http.post(
        f"/admin/catalog/products/{product.id}/approve", headers=_as(admin, "staff")
    )
    assert approved.status_code == 200
    matches = [e for e in captured_events if e[1] == "product.updated"]
    assert len(matches) == 1
    assert matches[0][2]["snapshot"] is not None  # now approved -> visible


async def test_product_moderation_reject_tombstones_search_doc(
    api: tuple[httpx.AsyncClient, AsyncSession],
    captured_events: list[tuple[str, str, dict[str, Any]]],
) -> None:
    """Unconditional per the D19 contract ("product moderation approve/
    reject"). This is the real bug the reviewer caught: a previously-APPROVED
    (and therefore search-visible) product that gets rejected must re-publish
    with snapshot=None so the indexer tombstones the stale document - without
    this event, the doc would linger in the index forever."""
    http, session = api
    owner = uuid.uuid4()
    biz = await _business(session, owner)
    product = await catalog_service.create_product(
        session,
        owner_user_id=owner,
        business_id=biz.id,
        vertical_slug="milk",
        name="Recalled Milk",
        specs={"milk_type": "cow"},
    )
    admin = uuid.uuid4()
    approved = await http.post(
        f"/admin/catalog/products/{product.id}/approve", headers=_as(admin, "staff")
    )
    assert approved.status_code == 200
    captured_events.clear()  # isolate the reject's own event
    rejected = await http.post(
        f"/admin/catalog/products/{product.id}/reject",
        json={"note": "recalled by FSSAI"},
        headers=_as(admin, "staff"),
    )
    assert rejected.status_code == 200
    matches = [e for e in captured_events if e[1] == "product.updated"]
    assert len(matches) == 1
    stream, event_type, payload = matches[0]
    assert stream == "directory"
    assert payload["doc_id"] == f"product_{product.id.hex}"
    assert payload["snapshot"] is None  # tombstone: no longer visible
