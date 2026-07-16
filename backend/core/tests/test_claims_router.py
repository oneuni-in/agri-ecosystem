"""D16 claim submission + evidence access. Non-negotiable 3: evidence docs
behind auth (IDOR matrix - only the claimant reads their evidence here;
admins get their own route). Storage is monkeypatched - no MinIO needed."""

import uuid
from collections.abc import AsyncIterator
from io import BytesIO

import httpx
import pytest
from fastapi import Request
from PIL import Image
from sqlalchemy.ext.asyncio import AsyncSession

from main import create_app
from modules.directory.models import Business
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


def _jpeg(color: str = "red") -> bytes:
    buf = BytesIO()
    Image.new("RGB", (24, 24), color).save(buf, format="JPEG")
    return buf.getvalue()


def _files(count: int = 1) -> list[tuple[str, tuple[str, bytes, str]]]:
    return [("files", (f"doc{i}.jpg", _jpeg(), "image/jpeg")) for i in range(count)]


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


async def _seeded_business(session: AsyncSession, name: str = "Seeded Farm") -> Business:
    """A claimable business: NULL owner, as our seed scripts will create."""
    business = Business(
        owner_user_id=None,
        name=name,
        slug=f"seeded-{uuid.uuid4().hex[:10]}",
        type="farm",
        primary_pincode="641001",
    )
    session.add(business)
    await session.flush()
    await session.refresh(business)
    return business


async def test_claim_requires_auth(
    api: tuple[httpx.AsyncClient, AsyncSession], object_store: dict[str, bytes]
) -> None:
    http, session = api
    business = await _seeded_business(session)
    response = await http.post(f"/directory/businesses/{business.id}/claim", files=_files())
    assert response.status_code == 401


async def test_claim_seeded_business(
    api: tuple[httpx.AsyncClient, AsyncSession], object_store: dict[str, bytes]
) -> None:
    http, session = api
    business = await _seeded_business(session)
    response = await http.post(
        f"/directory/businesses/{business.id}/claim", files=_files(2), headers=_as(USER_A)
    )
    assert response.status_code == 201
    body = response.json()
    assert body["status"] == "pending"
    assert body["evidence_count"] == 2
    # evidence went through re-encode -> storage under claims/ keys
    assert len(object_store) == 2
    assert all(key.startswith("claims/") and key.endswith(".jpg") for key in object_store)
    # claim does NOT touch the business yet (no auto-approval)
    await session.refresh(business)
    assert business.owner_user_id is None
    assert business.verification_status == "unverified"


async def test_claim_owned_business_is_409(
    api: tuple[httpx.AsyncClient, AsyncSession], object_store: dict[str, bytes]
) -> None:
    http, session = api
    business = await _seeded_business(session)
    business.owner_user_id = USER_B
    await session.flush()
    response = await http.post(
        f"/directory/businesses/{business.id}/claim", files=_files(), headers=_as(USER_A)
    )
    assert response.status_code == 409
    assert response.json()["detail"] == "already_owned"


async def test_duplicate_pending_claim_is_409(
    api: tuple[httpx.AsyncClient, AsyncSession], object_store: dict[str, bytes]
) -> None:
    http, session = api
    business = await _seeded_business(session)
    first = await http.post(
        f"/directory/businesses/{business.id}/claim", files=_files(), headers=_as(USER_A)
    )
    assert first.status_code == 201
    second = await http.post(
        f"/directory/businesses/{business.id}/claim", files=_files(), headers=_as(USER_A)
    )
    assert second.status_code == 409
    assert second.json()["detail"] == "claim_pending"


async def test_claim_file_count_and_type_limits(
    api: tuple[httpx.AsyncClient, AsyncSession], object_store: dict[str, bytes]
) -> None:
    http, session = api
    business = await _seeded_business(session)
    too_many = await http.post(
        f"/directory/businesses/{business.id}/claim", files=_files(6), headers=_as(USER_A)
    )
    assert too_many.status_code == 422
    bad_type = await http.post(
        f"/directory/businesses/{business.id}/claim",
        files=[("files", ("doc.pdf", b"%PDF-1.7 junk", "application/pdf"))],
        headers=_as(USER_A),
    )
    assert bad_type.status_code == 422
    assert bad_type.json()["detail"] == "unsupported_type"
    assert not object_store  # nothing stored on rejection


async def test_storage_down_is_503_and_no_claim_row(
    api: tuple[httpx.AsyncClient, AsyncSession],
    object_store: dict[str, bytes],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    http, session = api
    business = await _seeded_business(session)

    async def broken_put(key: str, data: bytes, content_type: str) -> None:
        raise storage.StorageError("down")

    monkeypatch.setattr(storage, "put_object", broken_put)
    response = await http.post(
        f"/directory/businesses/{business.id}/claim", files=_files(), headers=_as(USER_A)
    )
    assert response.status_code == 503
    mine = await http.get("/directory/claims", headers=_as(USER_A))
    assert mine.json()["items"] == []


async def test_my_claims_lists_only_mine(
    api: tuple[httpx.AsyncClient, AsyncSession], object_store: dict[str, bytes]
) -> None:
    http, session = api
    business_a = await _seeded_business(session, "Farm A")
    business_b = await _seeded_business(session, "Farm B")
    await http.post(
        f"/directory/businesses/{business_a.id}/claim", files=_files(), headers=_as(USER_A)
    )
    await http.post(
        f"/directory/businesses/{business_b.id}/claim", files=_files(), headers=_as(USER_B)
    )
    mine = await http.get("/directory/claims", headers=_as(USER_A))
    assert mine.status_code == 200
    items = mine.json()["items"]
    assert len(items) == 1
    assert items[0]["business_id"] == str(business_a.id)


async def test_evidence_idor_matrix(
    api: tuple[httpx.AsyncClient, AsyncSession], object_store: dict[str, bytes]
) -> None:
    """Non-negotiable 3: only the claimant reads their evidence."""
    http, session = api
    business = await _seeded_business(session)
    created = await http.post(
        f"/directory/businesses/{business.id}/claim", files=_files(), headers=_as(USER_A)
    )
    claim_id = created.json()["id"]
    # unauthenticated -> 401
    assert (await http.get(f"/directory/claims/{claim_id}/evidence/0")).status_code == 401
    # another user -> same 404 as a missing claim (no existence oracle)
    attack = await http.get(f"/directory/claims/{claim_id}/evidence/0", headers=_as(USER_B))
    assert attack.status_code == 404
    # claimant -> the re-encoded jpeg
    legit = await http.get(f"/directory/claims/{claim_id}/evidence/0", headers=_as(USER_A))
    assert legit.status_code == 200
    assert legit.headers["content-type"].startswith("image/jpeg")
    assert legit.content[:3] == b"\xff\xd8\xff"
    # out-of-range index -> 404
    oob = await http.get(f"/directory/claims/{claim_id}/evidence/9", headers=_as(USER_A))
    assert oob.status_code == 404


async def test_public_detail_exposes_claimable(
    api: tuple[httpx.AsyncClient, AsyncSession], object_store: dict[str, bytes]
) -> None:
    http, session = api
    business = await _seeded_business(session)
    detail = await http.get(f"/directory/businesses/{business.slug}")  # public
    assert detail.status_code == 200
    body = detail.json()["business"]
    assert body["claimable"] is True
    assert "owner_user_id" not in body  # never leak the owner column publicly


async def _owned_business(session: AsyncSession, owner: uuid.UUID) -> Business:
    business = await _seeded_business(session, "Owned Dairy")
    business.owner_user_id = owner
    await session.flush()
    return business


async def test_owner_requests_verification(
    api: tuple[httpx.AsyncClient, AsyncSession], object_store: dict[str, bytes]
) -> None:
    http, session = api
    business = await _owned_business(session, USER_A)
    response = await http.post(
        f"/directory/businesses/{business.id}/verification", files=_files(), headers=_as(USER_A)
    )
    assert response.status_code == 201
    body = response.json()
    assert body["method"] == "document"
    assert body["status"] == "pending"
    await session.refresh(business)
    assert business.verification_status == "pending"


async def test_verification_is_owner_only_and_single_pending(
    api: tuple[httpx.AsyncClient, AsyncSession], object_store: dict[str, bytes]
) -> None:
    http, session = api
    business = await _owned_business(session, USER_A)
    # non-owner -> 404 (same as missing business; IDOR)
    attack = await http.post(
        f"/directory/businesses/{business.id}/verification", files=_files(), headers=_as(USER_B)
    )
    assert attack.status_code == 404
    first = await http.post(
        f"/directory/businesses/{business.id}/verification", files=_files(), headers=_as(USER_A)
    )
    assert first.status_code == 201
    dup = await http.post(
        f"/directory/businesses/{business.id}/verification", files=_files(), headers=_as(USER_A)
    )
    assert dup.status_code == 409
    assert dup.json()["detail"] == "verification_pending"


async def test_verified_business_cannot_rerequest(
    api: tuple[httpx.AsyncClient, AsyncSession], object_store: dict[str, bytes]
) -> None:
    http, session = api
    business = await _owned_business(session, USER_A)
    business.verification_status = "verified"
    await session.flush()
    response = await http.post(
        f"/directory/businesses/{business.id}/verification", files=_files(), headers=_as(USER_A)
    )
    assert response.status_code == 409
    assert response.json()["detail"] == "already_verified"
