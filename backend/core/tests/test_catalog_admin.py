"""D17 Task 7: /admin/catalog - flag-gated schema version CRUD + product
moderation. Role-gated (staff/super_admin), not permission-gated: same
directory/identity independence trade-off as modules/directory/admin_router.py
and modules/coins/admin_router.py. Schema WRITES additionally require the
catalog_schema_admin flag (seeded false by migration 0018)."""

import uuid
from collections.abc import AsyncIterator

import httpx
import pytest
from fastapi import Request
from sqlalchemy import select
from sqlalchemy import update as sa_update
from sqlalchemy.ext.asyncio import AsyncSession

from main import create_app
from modules.directory import catalog_service, service
from modules.directory.catalog_models import Product
from modules.directory.models import Business
from shared.audit import AuditEntry
from shared.db import get_session
from shared.flags import FeatureFlag, reset_flag_cache
from shared.security import register_principal_resolver

pytestmark = pytest.mark.asyncio

USER_A = uuid.uuid4()
STAFF = uuid.uuid4()
SUPER_ADMIN = uuid.uuid4()


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


async def _enable_flag(session: AsyncSession) -> None:
    await session.execute(
        sa_update(FeatureFlag).where(FeatureFlag.key == "catalog_schema_admin").values(enabled=True)
    )
    await session.flush()
    reset_flag_cache()


async def _business(session: AsyncSession, owner: uuid.UUID) -> Business:
    return await service.create_business(
        session,
        owner_user_id=owner,
        name="Coimbatore Dairy",
        type_="vendor",
        primary_pincode="641001",
    )


async def _pending_product(
    session: AsyncSession, owner: uuid.UUID, business: Business
) -> uuid.UUID:
    product = await catalog_service.create_product(
        session,
        owner_user_id=owner,
        business_id=business.id,
        vertical_slug="milk",
        name="A2 Milk",
        specs={"milk_type": "a2"},
    )
    return product.id


VALID_FIELDS = [
    {
        "key": "fat_percent",
        "label": {"en": "Fat %"},
        "type": "number",
        "min": 0,
        "max": 100,
        "required": False,
    }
]


# --- auth matrix -----------------------------------------------------------


async def test_list_schemas_anon_401(api: tuple[httpx.AsyncClient, AsyncSession]) -> None:
    client, _ = api
    response = await client.get("/admin/catalog/schemas/milk")
    assert response.status_code == 401


async def test_list_schemas_plain_user_403(api: tuple[httpx.AsyncClient, AsyncSession]) -> None:
    client, _ = api
    response = await client.get("/admin/catalog/schemas/milk", headers=_as(USER_A))
    assert response.status_code == 403


async def test_get_schema_version_anon_401(api: tuple[httpx.AsyncClient, AsyncSession]) -> None:
    client, _ = api
    response = await client.get("/admin/catalog/schemas/milk/1")
    assert response.status_code == 401


async def test_get_schema_version_plain_user_403(
    api: tuple[httpx.AsyncClient, AsyncSession],
) -> None:
    client, _ = api
    response = await client.get("/admin/catalog/schemas/milk/1", headers=_as(USER_A))
    assert response.status_code == 403


async def test_create_schema_anon_401(api: tuple[httpx.AsyncClient, AsyncSession]) -> None:
    client, _ = api
    response = await client.post("/admin/catalog/schemas/milk", json={"fields": VALID_FIELDS})
    assert response.status_code == 401


async def test_create_schema_plain_user_403(api: tuple[httpx.AsyncClient, AsyncSession]) -> None:
    client, _ = api
    response = await client.post(
        "/admin/catalog/schemas/milk", json={"fields": VALID_FIELDS}, headers=_as(USER_A)
    )
    assert response.status_code == 403


async def test_list_products_anon_401(api: tuple[httpx.AsyncClient, AsyncSession]) -> None:
    client, _ = api
    response = await client.get("/admin/catalog/products")
    assert response.status_code == 401


async def test_list_products_plain_user_403(api: tuple[httpx.AsyncClient, AsyncSession]) -> None:
    client, _ = api
    response = await client.get("/admin/catalog/products", headers=_as(USER_A))
    assert response.status_code == 403


async def test_approve_anon_401(api: tuple[httpx.AsyncClient, AsyncSession]) -> None:
    client, session = api
    business = await _business(session, USER_A)
    product_id = await _pending_product(session, USER_A, business)
    response = await client.post(f"/admin/catalog/products/{product_id}/approve")
    assert response.status_code == 401


async def test_approve_plain_user_403(api: tuple[httpx.AsyncClient, AsyncSession]) -> None:
    client, session = api
    business = await _business(session, USER_A)
    product_id = await _pending_product(session, USER_A, business)
    response = await client.post(
        f"/admin/catalog/products/{product_id}/approve", headers=_as(USER_A)
    )
    assert response.status_code == 403


async def test_reject_anon_401(api: tuple[httpx.AsyncClient, AsyncSession]) -> None:
    client, session = api
    business = await _business(session, USER_A)
    product_id = await _pending_product(session, USER_A, business)
    response = await client.post(
        f"/admin/catalog/products/{product_id}/reject", json={"note": "bad photo"}
    )
    assert response.status_code == 401


async def test_reject_plain_user_403(api: tuple[httpx.AsyncClient, AsyncSession]) -> None:
    client, session = api
    business = await _business(session, USER_A)
    product_id = await _pending_product(session, USER_A, business)
    response = await client.post(
        f"/admin/catalog/products/{product_id}/reject",
        json={"note": "bad photo"},
        headers=_as(USER_A),
    )
    assert response.status_code == 403


# --- staff: read schemas, but cannot write ---------------------------------


async def test_staff_can_list_and_read_schemas(
    api: tuple[httpx.AsyncClient, AsyncSession],
) -> None:
    client, _ = api
    listing = await client.get("/admin/catalog/schemas/milk", headers=_as(STAFF, "staff"))
    assert listing.status_code == 200
    body = listing.json()
    assert body["items"][0]["vertical_slug"] == "milk"
    assert body["items"][0]["version"] == 1

    detail = await client.get("/admin/catalog/schemas/milk/1", headers=_as(STAFF, "staff"))
    assert detail.status_code == 200
    assert detail.json()["version"] == 1
    assert len(detail.json()["fields"]) == 3


async def test_get_schema_version_unknown_is_404(
    api: tuple[httpx.AsyncClient, AsyncSession],
) -> None:
    client, _ = api
    response = await client.get("/admin/catalog/schemas/milk/99", headers=_as(STAFF, "staff"))
    assert response.status_code == 404


async def test_staff_post_schema_is_403_role(
    api: tuple[httpx.AsyncClient, AsyncSession],
) -> None:
    client, session = api
    await _enable_flag(session)  # even with the flag ON, staff is still refused
    response = await client.post(
        "/admin/catalog/schemas/milk", json={"fields": VALID_FIELDS}, headers=_as(STAFF, "staff")
    )
    assert response.status_code == 403
    assert response.json()["detail"] == "missing_role"


# --- super_admin: schema writes, flag-gated ---------------------------------


async def test_create_schema_flag_off_is_403(
    api: tuple[httpx.AsyncClient, AsyncSession],
) -> None:
    client, _ = api
    response = await client.post(
        "/admin/catalog/schemas/milk",
        json={"fields": VALID_FIELDS},
        headers=_as(SUPER_ADMIN, "super_admin"),
    )
    assert response.status_code == 403
    assert response.json()["detail"] == "schema_admin_disabled"


async def test_create_schema_flag_on_creates_version_and_audits(
    api: tuple[httpx.AsyncClient, AsyncSession],
) -> None:
    client, session = api
    await _enable_flag(session)

    response = await client.post(
        "/admin/catalog/schemas/milk",
        json={"fields": VALID_FIELDS},
        headers=_as(SUPER_ADMIN, "super_admin"),
    )
    assert response.status_code == 201
    body = response.json()
    assert body["vertical_slug"] == "milk"
    assert body["version"] == 2
    assert body["fields"][0]["key"] == "fat_percent"

    entry = await session.scalar(
        select(AuditEntry).where(AuditEntry.action == "catalog.schema_created")
    )
    assert entry is not None
    assert entry.actor_user_id == SUPER_ADMIN
    assert entry.target_type == "spec_schema"
    assert entry.target_id == "milk:2"
    assert entry.meta == {"vertical_slug": "milk", "version": 2, "field_count": 1}


async def test_create_schema_malformed_fields_is_422(
    api: tuple[httpx.AsyncClient, AsyncSession],
) -> None:
    client, session = api
    await _enable_flag(session)
    response = await client.post(
        "/admin/catalog/schemas/milk",
        json={"fields": [{"key": "Bad Key!", "label": {"en": "x"}, "type": "string"}]},
        headers=_as(SUPER_ADMIN, "super_admin"),
    )
    assert response.status_code == 422
    detail = response.json()["detail"]
    assert detail["code"] == "invalid_field_definition"


async def test_create_schema_unknown_vertical_is_404(
    api: tuple[httpx.AsyncClient, AsyncSession],
) -> None:
    client, session = api
    await _enable_flag(session)
    response = await client.post(
        "/admin/catalog/schemas/no-such-vertical",
        json={"fields": VALID_FIELDS},
        headers=_as(SUPER_ADMIN, "super_admin"),
    )
    assert response.status_code == 404


async def test_create_schema_race_is_409(
    api: tuple[httpx.AsyncClient, AsyncSession], monkeypatch: pytest.MonkeyPatch
) -> None:
    """Concurrent-version race hardening: a lost race against the
    (vertical_slug, version) unique constraint must 409, not 500."""
    client, session = api
    await _enable_flag(session)

    from sqlalchemy.exc import IntegrityError

    async def _raise_integrity_error(*args: object, **kwargs: object) -> None:
        raise IntegrityError("insert", {}, Exception("unique violation"))

    # catalog_admin_router does `from modules.directory import catalog_service`,
    # so it shares this module object - patching it here reaches the router's
    # call site too (test_catalog_media.py precedent).
    monkeypatch.setattr(catalog_service, "create_schema_version", _raise_integrity_error)

    response = await client.post(
        "/admin/catalog/schemas/milk",
        json={"fields": VALID_FIELDS},
        headers=_as(SUPER_ADMIN, "super_admin"),
    )
    assert response.status_code == 409
    assert response.json()["detail"] == "version_conflict"


# --- moderation queue --------------------------------------------------------


async def test_pending_product_listed_for_staff(
    api: tuple[httpx.AsyncClient, AsyncSession],
) -> None:
    client, session = api
    business = await _business(session, USER_A)
    product_id = await _pending_product(session, USER_A, business)

    response = await client.get(
        "/admin/catalog/products?status=pending", headers=_as(STAFF, "staff")
    )
    assert response.status_code == 200
    ids = [item["id"] for item in response.json()["items"]]
    assert str(product_id) in ids


async def test_approve_makes_product_public_and_audits(
    api: tuple[httpx.AsyncClient, AsyncSession],
) -> None:
    client, session = api
    business = await _business(session, USER_A)
    product_id = await _pending_product(session, USER_A, business)
    product = await session.get(Product, product_id)
    assert product is not None
    slug = product.slug

    pre_check = await client.get(f"/catalog/products/{slug}")
    assert pre_check.status_code == 404

    response = await client.post(
        f"/admin/catalog/products/{product_id}/approve", headers=_as(STAFF, "staff")
    )
    assert response.status_code == 200
    assert response.json()["moderation_status"] == "approved"

    entry = await session.scalar(
        select(AuditEntry).where(AuditEntry.action == "catalog.product_approved")
    )
    assert entry is not None
    assert entry.target_type == "product"
    assert entry.target_id == str(product_id)
    assert entry.meta == {"business_id": str(business.id)}

    # goes through the real public route on the same client (Task 7 addition #7)
    public = await client.get(f"/catalog/products/{slug}")
    assert public.status_code == 200


async def test_reject_requires_note(api: tuple[httpx.AsyncClient, AsyncSession]) -> None:
    client, session = api
    business = await _business(session, USER_A)
    product_id = await _pending_product(session, USER_A, business)

    missing_note = await client.post(
        f"/admin/catalog/products/{product_id}/reject", json={}, headers=_as(STAFF, "staff")
    )
    assert missing_note.status_code == 422

    with_note = await client.post(
        f"/admin/catalog/products/{product_id}/reject",
        json={"note": "blurry photo"},
        headers=_as(STAFF, "staff"),
    )
    assert with_note.status_code == 200
    assert with_note.json()["moderation_status"] == "rejected"

    entry = await session.scalar(
        select(AuditEntry).where(AuditEntry.action == "catalog.product_rejected")
    )
    assert entry is not None
    assert entry.meta == {"business_id": str(business.id), "note": "blurry photo"}

    product = await session.get(Product, product_id)
    assert product is not None
    assert product.moderation_status == "rejected"


async def test_approve_unknown_product_is_404(
    api: tuple[httpx.AsyncClient, AsyncSession],
) -> None:
    client, _ = api
    response = await client.post(
        f"/admin/catalog/products/{uuid.uuid4()}/approve", headers=_as(STAFF, "staff")
    )
    assert response.status_code == 404


async def test_list_products_invalid_cursor_is_400(
    api: tuple[httpx.AsyncClient, AsyncSession],
) -> None:
    client, _ = api
    response = await client.get(
        "/admin/catalog/products?status=pending&cursor=not-valid-base64!!",
        headers=_as(STAFF, "staff"),
    )
    assert response.status_code == 400
