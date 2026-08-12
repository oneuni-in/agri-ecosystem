"""U2 — THE IDOR SWEEP (binding table, §7 of docs/design-reference/polish-u1.md).

For every console resource, signed in as vendor B, attempt vendor A's row —
read, edit, delete, and list. Expected: **404 on every one, never 403, never
2xx** — a 403 confirms the row exists, which is the IDOR tell. This is
stricter than test_d30_idor.py (which accepts 403-or-404 and stays untouched
as the D30 record); U2's contract pins the exact status.

Design mirrors D30's two-fixture shape:
  - the attacker owns a business of their own, so a refusal cannot be
    explained away as "not a vendor at all";
  - every route is re-run as the OWNER as a positive control — without it a
    mistyped path would also 404 and the sweep would prove nothing.

Runs as an ordinary pytest spec so it stays true after U3 — new
console resources get a row here or they are not done.
"""

import uuid
from collections.abc import AsyncIterator
from dataclasses import dataclass
from io import BytesIO

import httpx
import pytest
from fastapi import Request
from PIL import Image
from sqlalchemy.ext.asyncio import AsyncSession

from main import create_app
from modules.directory import catalog_router, catalog_service
from modules.directory import service as directory_service
from modules.identity.service import create_user
from shared import storage
from shared.db import get_session
from shared.security import register_principal_resolver

pytestmark = pytest.mark.asyncio


class _Principal:
    def __init__(self, user_id: uuid.UUID, roles: tuple[str, ...] = ("user",)) -> None:
        self.user_id = user_id
        self.roles = roles


def _png() -> bytes:
    buf = BytesIO()
    Image.new("RGB", (8, 8), "white").save(buf, format="PNG")
    return buf.getvalue()


@dataclass
class World:
    client: httpx.AsyncClient
    victim: dict[str, str]  # headers
    attacker: dict[str, str]
    business_id: uuid.UUID  # victim's
    branch_id: uuid.UUID
    product_id: uuid.UUID
    inquiry_id: uuid.UUID
    attacker_business_id: uuid.UUID


@pytest.fixture
def object_store(monkeypatch: pytest.MonkeyPatch) -> dict[str, bytes]:
    """In-memory MinIO stand-in (test_catalog_media precedent) so the image
    rows exercise the OWNERSHIP check, not storage availability."""
    store: dict[str, bytes] = {}

    async def fake_put(key: str, data: bytes, content_type: str) -> None:
        store[key] = data

    async def fake_get(key: str) -> bytes:
        if key not in store:
            raise storage.StorageError("missing")
        return store[key]

    async def fake_ensure(prefix: str) -> None:
        return None

    monkeypatch.setattr(storage, "put_object", fake_put)
    monkeypatch.setattr(storage, "get_object", fake_get)
    monkeypatch.setattr(storage, "ensure_prefix_public_read", fake_ensure)
    catalog_router._media_prefix_ready = False
    return store


@pytest.fixture
async def world(db_session: AsyncSession, object_store: dict[str, bytes]) -> AsyncIterator[World]:
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

    victim_user = await create_user(db_session, "+919000000811")
    attacker_user = await create_user(db_session, "+919000000812")
    victim = {"x-test-user": str(victim_user.id)}
    attacker = {"x-test-user": str(attacker_user.id)}

    business = await directory_service.create_business(
        db_session,
        owner_user_id=victim_user.id,
        name="U2 Victim Dairy",
        type_="vendor",
        primary_pincode="641001",
        description={"en": "victim"},
    )
    branch = await directory_service.add_branch(
        db_session,
        owner_user_id=victim_user.id,
        business_id=business.id,
        address="1 Victim Road",
        state="Tamil Nadu",
        district="Coimbatore",
        pincode="641001",
    )
    await directory_service.set_coverage(
        db_session,
        owner_user_id=victim_user.id,
        business_id=business.id,
        pincodes=["641001"],
    )
    product = await catalog_service.create_product(
        db_session,
        owner_user_id=victim_user.id,
        business_id=business.id,
        vertical_slug="milk",
        name="Victim Cow Milk",
        specs={"category": "milk", "milk_type": "cow"},
    )
    attacker_business = await directory_service.create_business(
        db_session,
        owner_user_id=attacker_user.id,
        name="U2 Attacker Dairy",
        type_="vendor",
        primary_pincode="641002",
        description={"en": "attacker"},
    )
    await db_session.flush()

    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="https://api.test") as client:
        # a real lead into the victim's inbox, via the public route
        created = await client.post(
            "/leads/inquiries",
            json={
                "type": "contact",
                "business_id": str(business.id),
                "pincode": "641001",
                "payload": {"message": "hello"},
            },
        )
        assert created.status_code == 201, created.text
        inquiry_id = uuid.UUID(created.json()["id"])
        # give the victim's product an image so the delete-image row targets
        # a real index
        uploaded = await client.post(
            f"/catalog/products/{product.id}/images",
            files={"file": ("a.png", _png(), "image/png")},
            headers=victim,
        )
        assert uploaded.status_code == 201, uploaded.text
        yield World(
            client=client,
            victim=victim,
            attacker=attacker,
            business_id=business.id,
            branch_id=branch.id,
            product_id=product.id,
            inquiry_id=inquiry_id,
            attacker_business_id=attacker_business.id,
        )


# (label, method, path template, body kind) — bodies resolved in _request.
# {bid}/{brid}/{pid}/{iid} = victim's business/branch/product/inquiry ids.
SWEEP: list[tuple[str, str, str, str | None]] = [
    # business — read / edit / delete / sub-writes
    ("business edit", "PATCH", "/directory/businesses/{bid}", "patch_business"),
    ("business delete", "DELETE", "/directory/businesses/{bid}", None),
    ("business rename", "POST", "/directory/businesses/{bid}/rename", "rename"),
    ("coverage write", "PUT", "/directory/businesses/{bid}/coverage", "coverage"),
    ("categories write", "PUT", "/directory/businesses/{bid}/categories", "categories"),
    ("tier write", "PUT", "/directory/businesses/{bid}/tier-selection", "tier"),
    ("tier read", "GET", "/directory/businesses/{bid}/tier-selection", None),
    ("analytics read", "GET", "/directory/businesses/{bid}/analytics", None),
    ("branch add", "POST", "/directory/businesses/{bid}/branches", "branch"),
    ("branch edit", "PATCH", "/directory/branches/{brid}", "patch_branch"),
    # products — create / list / edit / delete / media
    ("product create", "POST", "/catalog/businesses/{bid}/products", "product"),
    ("product list", "GET", "/catalog/my/products?business_id={bid}", None),
    ("product edit", "PATCH", "/catalog/products/{pid}", "patch_product"),
    ("product delete", "DELETE", "/catalog/products/{pid}", None),
    ("image upload", "POST", "/catalog/products/{pid}/images", "image"),
    ("image delete", "DELETE", "/catalog/products/{pid}/images/0", None),
    # leads — list / stats / respond / close
    ("inbox list", "GET", "/leads/inbox?business_id={bid}", None),
    ("inbox stats", "GET", "/leads/inbox/stats?business_id={bid}", None),
    ("lead respond", "POST", "/leads/inquiries/{iid}/responses", "response"),
    ("lead close", "POST", "/leads/inquiries/{iid}/close", None),
]

BODIES: dict[str, dict[str, object]] = {
    "patch_business": {"description": {"en": "pwned"}},
    "rename": {"new_slug": "pwned-dairy"},
    "coverage": {"pincodes": ["641009"]},
    "categories": {"category_ids": []},
    "tier": {"tier": "premium"},
    "branch": {
        "address": "2 Attacker Road",
        "state": "Tamil Nadu",
        "district": "Coimbatore",
        "pincode": "641001",
    },
    "patch_branch": {"address": "3 Pwned Street"},
    "product": {
        "vertical_slug": "milk",
        "name": "Pwned Milk",
        "specs": {"category": "milk", "milk_type": "cow"},
    },
    "patch_product": {"price_display": "₹1/L"},
    "response": {"body": "we deliver"},
}


async def _request(
    world: World, headers: dict[str, str], method: str, path: str, body_kind: str | None
) -> httpx.Response:
    url = path.format(
        bid=world.business_id,
        brid=world.branch_id,
        pid=world.product_id,
        iid=world.inquiry_id,
    )
    if body_kind == "image":
        return await world.client.post(
            url, files={"file": ("b.png", _png(), "image/png")}, headers=headers
        )
    return await world.client.request(
        method, url, json=BODIES.get(body_kind) if body_kind else None, headers=headers
    )


@pytest.mark.parametrize(
    "label,method,path,body_kind", SWEEP, ids=[f"{row[1]} {row[2]}" for row in SWEEP]
)
async def test_idor_sweep_attacker_gets_exactly_404(
    world: World, label: str, method: str, path: str, body_kind: str | None
) -> None:
    response = await _request(world, world.attacker, method, path, body_kind)
    assert response.status_code == 404, (
        f"[{label}] {method} {path} answered {response.status_code}, not 404 — "
        f"a 403 confirms the row exists (IDOR tell), a 2xx is a leak: "
        f"{response.text[:300]}"
    )


@pytest.mark.parametrize(
    "label,method,path,body_kind", SWEEP, ids=[f"owner {row[1]} {row[2]}" for row in SWEEP]
)
async def test_idor_sweep_owner_positive_control(
    world: World, label: str, method: str, path: str, body_kind: str | None
) -> None:
    """The owner must NOT get 403/404 on the same URL — any other status
    (200/201/204/409/422) proves the route is real, so the attacker's 404
    above is an authz decision, not a routing accident.

    Order note: the destructive rows (business delete, product delete,
    image delete) run against a per-test fresh `world`, so earlier rows
    cannot have removed what later rows target.
    """
    response = await _request(world, world.victim, method, path, body_kind)
    assert response.status_code not in (403, 404), (
        f"[{label}] {method} {path} refused the OWNER "
        f"({response.status_code}) — the sweep row proves nothing: {response.text[:300]}"
    )


async def test_owner_list_excludes_other_vendors_rows(world: World) -> None:
    """The LIST leg of the sweep: B's owner list never contains A's business,
    and B cannot page A's products through the my-products list."""
    listing = await world.client.get("/directory/businesses", headers=world.attacker)
    assert listing.status_code == 200
    ids = {row["id"] for row in listing.json()["items"]}
    assert str(world.business_id) not in ids
    assert str(world.attacker_business_id) in ids

    victim_products = await world.client.get(
        f"/catalog/my/products?business_id={world.business_id}", headers=world.attacker
    )
    assert victim_products.status_code == 404
