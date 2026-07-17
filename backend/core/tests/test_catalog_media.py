"""D17 product image upload/delete: the shared media helper (shared.media.
reencode_image) strips EXIF/GPS by construction, and served URLs point at
the media domain (media_public_base_url), never the app's own API domain
(NN#2). Storage is monkeypatched - no MinIO needed. IDOR: only the owning
business's owner may upload/delete a product's images."""

import uuid
from collections.abc import AsyncIterator
from io import BytesIO

import httpx
import pytest
from fastapi import Request
from PIL import Image
from sqlalchemy.ext.asyncio import AsyncSession

from main import create_app
from modules.directory import catalog_router, catalog_service, service
from modules.directory.models import Business
from settings import get_settings
from shared import storage
from shared.db import get_session
from shared.security import register_principal_resolver

pytestmark = pytest.mark.asyncio

USER_A = uuid.uuid4()
USER_B = uuid.uuid4()


class _Principal:
    def __init__(self, user_id: uuid.UUID, roles: tuple[str, ...] = ("user",)) -> None:
        self.user_id = user_id
        self.roles = roles


def _as(user_id: uuid.UUID, roles: str = "user") -> dict[str, str]:
    return {"x-test-user": str(user_id), "x-test-roles": roles}


def _jpeg_with_gps_exif() -> bytes:
    img = Image.new("RGB", (32, 32), "green")
    exif = Image.Exif()
    exif[0x0110] = "SpyCam 3000"  # Model
    gps_ifd = exif.get_ifd(0x8825)
    gps_ifd[1] = "N"  # GPSLatitudeRef
    gps_ifd[2] = (12.0, 58.0, 0.0)  # GPSLatitude
    gps_ifd[3] = "E"  # GPSLongitudeRef
    gps_ifd[4] = (77.0, 34.0, 0.0)  # GPSLongitude
    buf = BytesIO()
    img.save(buf, format="JPEG", exif=exif)
    return buf.getvalue()


@pytest.fixture
def object_store(monkeypatch: pytest.MonkeyPatch) -> dict[str, bytes]:
    """In-memory stand-in for MinIO wired through shared.storage."""
    store: dict[str, bytes] = {}

    async def fake_put(key: str, data: bytes, content_type: str) -> None:
        store[key] = data

    async def fake_get(key: str) -> bytes:
        if key not in store:
            raise storage.StorageError("missing")
        return store[key]

    monkeypatch.setattr(storage, "put_object", fake_put)
    monkeypatch.setattr(storage, "get_object", fake_get)
    return store


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


async def _business(
    session: AsyncSession, owner: uuid.UUID, name: str = "Coimbatore Dairy"
) -> Business:
    return await service.create_business(
        session, owner_user_id=owner, name=name, type_="vendor", primary_pincode="641001"
    )


async def _product(
    session: AsyncSession, owner: uuid.UUID, business: Business, name: str
) -> uuid.UUID:
    product = await catalog_service.create_product(
        session,
        owner_user_id=owner,
        business_id=business.id,
        vertical_slug="milk",
        name=name,
        specs={"milk_type": "cow"},
    )
    return product.id


async def test_upload_strips_exif_and_serves_off_app_domain(
    api: tuple[httpx.AsyncClient, AsyncSession], object_store: dict[str, bytes]
) -> None:
    client, session = api
    business = await _business(session, USER_A)
    product_id = await _product(session, USER_A, business, "A2 Milk")

    source = _jpeg_with_gps_exif()
    assert dict(Image.open(BytesIO(source)).getexif())  # premise: EXIF present

    response = await client.post(
        f"/catalog/products/{product_id}/images",
        files={"file": ("cow.jpg", source, "image/jpeg")},
        headers=_as(USER_A),
    )
    assert response.status_code == 201
    body = response.json()
    assert len(body["images"]) == 1

    # NN#2b: served off the media domain, not the app's own API domain
    settings = get_settings()
    assert body["images"][0].startswith(settings.media_public_base_url)
    assert not body["images"][0].startswith("https://api.test")

    # stored key shape
    assert len(object_store) == 1
    (key,) = object_store
    assert key.startswith("products/")
    assert key.endswith(".jpg")

    # NN#2a: EXIF/GPS gone by construction, re-encoded to JPEG
    stored = Image.open(BytesIO(object_store[key]))
    assert stored.format == "JPEG"
    assert len(stored.getexif()) == 0


async def test_upload_rejects_unsupported_type(
    api: tuple[httpx.AsyncClient, AsyncSession], object_store: dict[str, bytes]
) -> None:
    client, session = api
    business = await _business(session, USER_A)
    product_id = await _product(session, USER_A, business, "Bad Type Milk")

    response = await client.post(
        f"/catalog/products/{product_id}/images",
        files={"file": ("notes.txt", b"just some text", "text/plain")},
        headers=_as(USER_A),
    )
    assert response.status_code == 422
    assert response.json()["detail"] == "unsupported_type"
    assert not object_store


async def test_upload_rejects_too_large(
    api: tuple[httpx.AsyncClient, AsyncSession], object_store: dict[str, bytes]
) -> None:
    client, session = api
    business = await _business(session, USER_A)
    product_id = await _product(session, USER_A, business, "Huge Milk")

    oversized = b"\xff\xd8\xff" + b"0" * (6 * 1024 * 1024)  # 6 MiB, over the 5 MiB cap
    response = await client.post(
        f"/catalog/products/{product_id}/images",
        files={"file": ("cow.jpg", oversized, "image/jpeg")},
        headers=_as(USER_A),
    )
    assert response.status_code == 422
    assert response.json()["detail"] == "too_large"
    assert not object_store


async def test_ninth_image_is_409(
    api: tuple[httpx.AsyncClient, AsyncSession], object_store: dict[str, bytes]
) -> None:
    client, session = api
    business = await _business(session, USER_A)
    product_id = await _product(session, USER_A, business, "Capped Milk")
    for i in range(8):
        await catalog_service.add_product_image(
            session, owner_user_id=USER_A, product_id=product_id, key=f"products/seed-{i}.jpg"
        )

    response = await client.post(
        f"/catalog/products/{product_id}/images",
        files={"file": ("cow.jpg", _jpeg_with_gps_exif(), "image/jpeg")},
        headers=_as(USER_A),
    )
    assert response.status_code == 409


async def test_upload_non_owner_is_404(
    api: tuple[httpx.AsyncClient, AsyncSession], object_store: dict[str, bytes]
) -> None:
    client, session = api
    business = await _business(session, USER_A)
    product_id = await _product(session, USER_A, business, "Stolen Milk")

    response = await client.post(
        f"/catalog/products/{product_id}/images",
        files={"file": ("cow.jpg", _jpeg_with_gps_exif(), "image/jpeg")},
        headers=_as(USER_B),
    )
    assert response.status_code == 404
    # storage-before-DB (avatar/claims precedent): the object may already be
    # written when the ownership check 404s - that's an accepted orphan, not
    # a leak (the key is never surfaced to the attacker).
    product = await catalog_service.get_owned_product(session, USER_A, product_id)
    assert product.media_keys == []


async def test_delete_removes_image_and_shrinks_list(
    api: tuple[httpx.AsyncClient, AsyncSession], object_store: dict[str, bytes]
) -> None:
    client, session = api
    business = await _business(session, USER_A)
    product_id = await _product(session, USER_A, business, "Deletable Milk")
    await catalog_service.add_product_image(
        session, owner_user_id=USER_A, product_id=product_id, key="products/one.jpg"
    )
    await catalog_service.add_product_image(
        session, owner_user_id=USER_A, product_id=product_id, key="products/two.jpg"
    )

    response = await client.delete(f"/catalog/products/{product_id}/images/0", headers=_as(USER_A))
    assert response.status_code == 200
    body = response.json()
    assert len(body["images"]) == 1


async def test_delete_out_of_range_index_is_404(
    api: tuple[httpx.AsyncClient, AsyncSession], object_store: dict[str, bytes]
) -> None:
    client, session = api
    business = await _business(session, USER_A)
    product_id = await _product(session, USER_A, business, "One Image Milk")
    await catalog_service.add_product_image(
        session, owner_user_id=USER_A, product_id=product_id, key="products/one.jpg"
    )

    response = await client.delete(f"/catalog/products/{product_id}/images/9", headers=_as(USER_A))
    assert response.status_code == 404
    assert response.json()["detail"] == "Image not found"


async def test_delete_non_owner_is_404(
    api: tuple[httpx.AsyncClient, AsyncSession], object_store: dict[str, bytes]
) -> None:
    client, session = api
    business = await _business(session, USER_A)
    product_id = await _product(session, USER_A, business, "Guarded Milk")
    await catalog_service.add_product_image(
        session, owner_user_id=USER_A, product_id=product_id, key="products/one.jpg"
    )

    response = await client.delete(f"/catalog/products/{product_id}/images/0", headers=_as(USER_B))
    assert response.status_code == 404


async def test_upload_attempts_public_prefix_policy_once(
    api: tuple[httpx.AsyncClient, AsyncSession],
    object_store: dict[str, bytes],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    client, session = api
    business = await _business(session, USER_A)
    product_id = await _product(session, USER_A, business, "Policy Milk")

    calls: list[str] = []

    async def fake_ensure(prefix: str) -> None:
        calls.append(prefix)

    # catalog_router does `from shared import storage`, so it shares this
    # module object - patching it here reaches the router's call site too.
    monkeypatch.setattr(storage, "ensure_prefix_public_read", fake_ensure)
    catalog_router._media_prefix_ready = False

    response = await client.post(
        f"/catalog/products/{product_id}/images",
        files={"file": ("cow.jpg", _jpeg_with_gps_exif(), "image/jpeg")},
        headers=_as(USER_A),
    )
    assert response.status_code == 201
    assert calls == [catalog_router.PRODUCT_MEDIA_PREFIX]
