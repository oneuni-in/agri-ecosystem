"""Voice-note shell routes (D25): validated multipart upload, auth-gated
playback for the need owner and each routed vendor (via the inquiry IDOR
contract). Storage stubbed in-memory (test_claims_router.py pattern)."""

import uuid
from collections.abc import AsyncIterator
from datetime import datetime
from typing import Any

import httpx
import pytest
from fastapi import Request
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from main import create_app
from modules.directory import needs_service, service
from modules.directory.leads_models import Inquiry, Need
from modules.directory.models import Business, BusinessCoverage
from shared import storage
from shared.db import get_session
from shared.security import register_principal_resolver

pytestmark = pytest.mark.asyncio

PINCODE = "641001"
WEBM = b"\x1a\x45\xdf\xa3" + b"\x00" * 64
JPEG = b"\xff\xd8\xff\xe0" + b"\x00" * 64

GOOD_PAYLOAD: dict[str, Any] = {"qty_liters": "1", "milk_type": "cow", "schedule": "daily"}


class _Principal:
    def __init__(self, user_id: uuid.UUID) -> None:
        self.user_id = user_id
        self.roles = ("user",)


def _as(user_id: uuid.UUID) -> dict[str, str]:
    return {"x-test-user": str(user_id)}


@pytest.fixture
def mem_storage(monkeypatch: pytest.MonkeyPatch) -> dict[str, bytes]:
    blobs: dict[str, bytes] = {}

    async def fake_put(key: str, data: bytes, content_type: str) -> None:
        blobs[key] = data

    async def fake_get(key: str) -> bytes:
        if key not in blobs:
            raise storage.StorageError("missing")
        return blobs[key]

    monkeypatch.setattr(storage, "put_object", fake_put)
    monkeypatch.setattr(storage, "get_object", fake_get)
    return blobs


@pytest.fixture
def no_cap(monkeypatch: pytest.MonkeyPatch) -> None:
    async def _allow(user_id: uuid.UUID, *, now: datetime) -> None:
        return None

    monkeypatch.setattr(needs_service, "claim_need_slot", _allow)


@pytest.fixture
async def client(db_session: AsyncSession) -> AsyncIterator[httpx.AsyncClient]:
    app = create_app()

    async def _session_override() -> AsyncIterator[AsyncSession]:
        yield db_session

    async def _resolver(request: Request, session: AsyncSession) -> object | None:
        header = request.headers.get("x-test-user")
        return _Principal(uuid.UUID(header)) if header else None

    app.dependency_overrides[get_session] = _session_override
    register_principal_resolver(_resolver)
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="https://api.test") as http:
        yield http


async def _mk_need(session: AsyncSession, *, user: uuid.UUID, status: str = "open") -> Need:
    need = Need(from_user_id=user, pincode=PINCODE, payload=GOOD_PAYLOAD, status=status)
    session.add(need)
    await session.flush()
    return need


async def _mk_routed_vendor(
    session: AsyncSession, need: Need, *, owner: uuid.UUID
) -> tuple[Business, Inquiry]:
    business = await service.create_business(
        session, owner_user_id=owner, name="Dairy Farm", type_="vendor", primary_pincode=PINCODE
    )
    session.add(BusinessCoverage(business_id=business.id, pincode=PINCODE))
    inquiry = Inquiry(
        type="milk_subscription",
        from_user_id=need.from_user_id,
        business_id=business.id,
        payload=GOOD_PAYLOAD,
        pincode=PINCODE,
        need_id=need.id,
    )
    session.add(inquiry)
    await session.flush()
    return business, inquiry


def _upload(blob: bytes) -> dict[str, tuple[str, bytes, str]]:
    # client-declared name/MIME are ignored server-side - magic bytes decide
    return {"file": ("note.webm", blob, "audio/webm")}


async def test_voice_upload_and_owner_playback(
    client: httpx.AsyncClient,
    db_session: AsyncSession,
    mem_storage: dict[str, bytes],
) -> None:
    user = uuid.uuid4()
    need = await _mk_need(db_session, user=user)
    up = await client.post(f"/leads/needs/{need.id}/voice", files=_upload(WEBM), headers=_as(user))
    assert up.status_code == 201
    assert up.json() == {"status": "stored"}
    [key] = mem_storage.keys()
    assert key.startswith("needs/") and key.endswith(".webm")

    play = await client.get(f"/leads/needs/{need.id}/voice", headers=_as(user))
    assert play.status_code == 200
    assert play.content == WEBM
    assert play.headers["content-type"].startswith("audio/webm")
    assert play.headers["cache-control"] == "private, no-store"


async def test_voice_rejects_non_audio(
    client: httpx.AsyncClient, db_session: AsyncSession, mem_storage: dict[str, bytes]
) -> None:
    user = uuid.uuid4()
    need = await _mk_need(db_session, user=user)
    up = await client.post(f"/leads/needs/{need.id}/voice", files=_upload(JPEG), headers=_as(user))
    assert up.status_code == 422
    assert up.json()["detail"] == "unsupported_type"
    assert mem_storage == {}  # nothing stored


async def test_voice_on_closed_need_409(
    client: httpx.AsyncClient, db_session: AsyncSession, mem_storage: dict[str, bytes]
) -> None:
    user = uuid.uuid4()
    need = await _mk_need(db_session, user=user, status="fulfilled")
    up = await client.post(f"/leads/needs/{need.id}/voice", files=_upload(WEBM), headers=_as(user))
    assert up.status_code == 409
    assert up.json()["detail"] == "need_closed"


async def test_voice_upload_idor_404(
    client: httpx.AsyncClient, db_session: AsyncSession, mem_storage: dict[str, bytes]
) -> None:
    need = await _mk_need(db_session, user=uuid.uuid4())
    up = await client.post(
        f"/leads/needs/{need.id}/voice", files=_upload(WEBM), headers=_as(uuid.uuid4())
    )
    assert up.status_code == 404


async def test_storage_down_503_and_no_key_saved(
    client: httpx.AsyncClient,
    db_session: AsyncSession,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    async def broken_put(key: str, data: bytes, content_type: str) -> None:
        raise storage.StorageError("down")

    monkeypatch.setattr(storage, "put_object", broken_put)
    user = uuid.uuid4()
    need = await _mk_need(db_session, user=user)
    up = await client.post(f"/leads/needs/{need.id}/voice", files=_upload(WEBM), headers=_as(user))
    assert up.status_code == 503
    assert up.json()["detail"] == "storage_unavailable"
    fresh = await db_session.scalar(select(Need.voice_key).where(Need.id == need.id))
    assert fresh is None  # DB never points at a blob that was not stored


async def test_vendor_can_play_via_inquiry(
    client: httpx.AsyncClient,
    db_session: AsyncSession,
    mem_storage: dict[str, bytes],
) -> None:
    user = uuid.uuid4()
    vendor_owner = uuid.uuid4()
    need = await _mk_need(db_session, user=user)
    _, inquiry = await _mk_routed_vendor(db_session, need, owner=vendor_owner)
    up = await client.post(f"/leads/needs/{need.id}/voice", files=_upload(WEBM), headers=_as(user))
    assert up.status_code == 201

    play = await client.get(f"/leads/inquiries/{inquiry.id}/voice", headers=_as(vendor_owner))
    assert play.status_code == 200
    assert play.content == WEBM

    # unrelated user: not-yours == missing on both playback paths
    other = uuid.uuid4()
    assert (
        await client.get(f"/leads/inquiries/{inquiry.id}/voice", headers=_as(other))
    ).status_code == 404
    assert (
        await client.get(f"/leads/needs/{need.id}/voice", headers=_as(other))
    ).status_code == 404


async def test_voiceless_need_404(
    client: httpx.AsyncClient, db_session: AsyncSession, mem_storage: dict[str, bytes]
) -> None:
    user = uuid.uuid4()
    need = await _mk_need(db_session, user=user)
    play = await client.get(f"/leads/needs/{need.id}/voice", headers=_as(user))
    assert play.status_code == 404
    assert play.json()["detail"] == "no_voice_note"
