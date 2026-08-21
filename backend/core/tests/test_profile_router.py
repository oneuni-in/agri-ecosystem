"""D11.A/B: progressive profile updates, geo-derived location, visibility
toggles, live score, and exactly-one profile.completed per crossing."""

from collections.abc import AsyncIterator
from decimal import Decimal
from typing import cast

import httpx
import pytest
from redis.asyncio import Redis
from sqlalchemy.ext.asyncio import AsyncSession

from main import create_app
from shared import storage
from shared.db import get_session
from shared.geo.models import District, Pincode, State
from tests.test_session_router import UA, _login

PHONE = "+919876522222"


@pytest.fixture
async def api(
    db_session: AsyncSession, otp_redis: Redis
) -> AsyncIterator[tuple[httpx.AsyncClient, AsyncSession]]:
    app = create_app()

    async def _session_override() -> AsyncIterator[AsyncSession]:
        yield db_session

    app.dependency_overrides[get_session] = _session_override
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(
        transport=transport, base_url="https://id.test", headers=UA
    ) as client:
        yield client, db_session


@pytest.fixture
async def geo_row(db_session: AsyncSession) -> str:
    """One deterministic pincode; the committed snapshot is not loaded in tests."""
    state = State(lgd_code=33, name="Tamil Nadu")
    db_session.add(state)
    await db_session.flush()
    district = District(lgd_code=558, state_id=state.id, name="Erode")
    db_session.add(district)
    await db_session.flush()
    db_session.add(
        Pincode(
            pincode="638001",
            district_id=district.id,
            centroid_lat=Decimal("11.341000"),
            centroid_lon=Decimal("77.717000"),
        )
    )
    await db_session.flush()
    return "638001"


async def test_profile_includes_member_since(
    api: tuple[httpx.AsyncClient, AsyncSession],
) -> None:
    """M1.5.D: 'Member since {month year}' renders from AgriID created_at."""
    from datetime import datetime

    from sqlalchemy import select

    from modules.identity.models import User

    http, session = api
    await _login(http, session, phone=PHONE)
    body = (await http.get("/identity/profile")).json()
    user = await session.scalar(select(User).where(User.phone == PHONE))
    assert user is not None
    got = datetime.fromisoformat(body["member_since"].replace("Z", "+00:00"))
    assert got == user.created_at


async def test_get_profile_before_any_update_scores_phone_only(
    api: tuple[httpx.AsyncClient, AsyncSession],
) -> None:
    http, session = api
    await _login(http, session, phone=PHONE)
    body = (await http.get("/identity/profile")).json()
    assert body["completion_score"] == 20  # phone verified at signup
    assert body["language"] is None and body["name"] is None
    assert body["visibility"] == {
        "avatar": False,
        "interests": False,
        "language": False,
        "location": False,
        "name": False,
    }


async def test_patch_name_language_interests(
    api: tuple[httpx.AsyncClient, AsyncSession],
) -> None:
    http, session = api
    await _login(http, session, phone=PHONE)
    response = await http.patch(
        "/identity/profile",
        json={
            "name": "  Asha  Farmer ",
            "language": "ta",
            "interests": ["Paddy", "paddy", "Drip irrigation"],
        },
    )
    assert response.status_code == 200
    body = response.json()
    assert body["name"] == "Asha Farmer"  # whitespace collapsed
    assert body["language"] == "ta"
    assert body["interests"] == ["Paddy", "Drip irrigation"]  # case-insensitive dedupe
    assert body["completion_score"] == 20 + 15 + 10 + 15


async def test_empty_interests_list_is_rejected_and_clears_nothing(
    api: tuple[httpx.AsyncClient, AsyncSession],
) -> None:
    """Progressive-only invariant: [] would wipe a set field, regress the
    score, and allow a second profile.completed for the same state."""
    http, session = api
    await _login(http, session, phone=PHONE)
    set_up = await http.patch("/identity/profile", json={"interests": ["Paddy"]})
    assert set_up.status_code == 200
    assert set_up.json()["completion_score"] == 20 + 15
    wipe = await http.patch("/identity/profile", json={"interests": []})
    assert wipe.status_code == 422  # min_length=1 at the Pydantic layer
    body = (await http.get("/identity/profile")).json()
    assert body["interests"] == ["Paddy"]  # unchanged
    assert body["completion_score"] == 20 + 15  # no regression


async def test_location_is_pincode_derived(
    api: tuple[httpx.AsyncClient, AsyncSession], geo_row: str
) -> None:
    http, session = api
    await _login(http, session, phone=PHONE)
    body = (await http.patch("/identity/profile", json={"pincode": geo_row})).json()
    assert body["state"] == "Tamil Nadu" and body["district"] == "Erode"
    assert body["completion_score"] == 20 + 25
    unknown = await http.patch("/identity/profile", json={"pincode": "999999"})
    assert unknown.status_code == 422 and unknown.json()["detail"] == "unknown_pincode"


async def test_free_text_location_is_rejected(
    api: tuple[httpx.AsyncClient, AsyncSession],
) -> None:
    http, session = api
    await _login(http, session, phone=PHONE)
    response = await http.patch("/identity/profile", json={"state": "Kerala"})
    assert response.status_code == 422  # extra="forbid"


async def test_visibility_toggles_validated_and_persisted(
    api: tuple[httpx.AsyncClient, AsyncSession],
) -> None:
    http, session = api
    await _login(http, session, phone=PHONE)
    ok = await http.patch(
        "/identity/profile", json={"visibility": {"name": True, "location": True}}
    )
    assert ok.json()["visibility"]["name"] is True
    bad = await http.patch("/identity/profile", json={"visibility": {"phone": True}})
    assert bad.status_code == 422 and bad.json()["detail"] == "unknown_visibility_key"


async def test_completed_event_exactly_once_per_crossing(
    api: tuple[httpx.AsyncClient, AsyncSession],
    geo_row: str,
    redis_client: Redis,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    async def fake_put_object(key: str, data: bytes, content_type: str) -> None:
        return None

    monkeypatch.setattr(storage, "put_object", fake_put_object)
    http, session = api
    await _login(http, session, phone=PHONE)
    # Login now emits both user.registered (D13) and identity.signup_completed
    # (D12) on the identity stream; drop them so this test isolates
    # profile.completed crossings from login events.
    await redis_client.delete("identity")
    await http.patch(
        "/identity/profile",
        json={"name": "Asha", "language": "ta", "interests": ["paddy"], "pincode": geo_row},
    )
    assert await redis_client.xlen("identity") == 0  # 85: not complete yet
    jpeg = b"\xff\xd8\xff\xe0" + b"\x00" * 64
    upload = await http.post(
        "/identity/profile/avatar", files={"file": ("me.jpg", jpeg, "image/jpeg")}
    )
    assert upload.status_code == 200
    assert upload.json()["completion_score"] == 100
    entries = cast(list[tuple[str, dict[str, str]]], await redis_client.xrange("identity"))
    assert entries is not None
    types = [fields["type"] for _id, fields in entries]
    assert types == ["profile.completed"]
    # Same state again: no second crossing, no second event.
    await http.patch("/identity/profile", json={"name": "Asha Again"})
    assert await redis_client.xlen("identity") == 1


async def test_avatar_upload_stores_and_scores(
    api: tuple[httpx.AsyncClient, AsyncSession], monkeypatch: pytest.MonkeyPatch
) -> None:
    calls: list[tuple[str, int, str]] = []

    async def fake_put_object(key: str, data: bytes, content_type: str) -> None:
        calls.append((key, len(data), content_type))

    monkeypatch.setattr(storage, "put_object", fake_put_object)
    http, session = api
    await _login(http, session, phone=PHONE)
    jpeg = b"\xff\xd8\xff\xe0" + b"\x00" * 64
    response = await http.post(
        "/identity/profile/avatar", files={"file": ("me.jpg", jpeg, "image/jpeg")}
    )
    assert response.status_code == 200
    body = response.json()
    assert body["has_avatar"] is True and body["completion_score"] == 20 + 15
    assert len(calls) == 1
    key, size, content_type = calls[0]
    assert key.startswith("avatars/") and key.endswith(".jpg")
    assert content_type == "image/jpeg" and size == len(jpeg)


async def test_avatar_rejects_lying_content_type(
    api: tuple[httpx.AsyncClient, AsyncSession], monkeypatch: pytest.MonkeyPatch
) -> None:
    async def fake_put_object(key: str, data: bytes, content_type: str) -> None:
        raise AssertionError("must not reach storage")

    monkeypatch.setattr(storage, "put_object", fake_put_object)
    http, session = api
    await _login(http, session, phone=PHONE)
    response = await http.post(
        "/identity/profile/avatar",
        files={"file": ("evil.jpg", b"<svg onload=alert(1)>", "image/jpeg")},
    )
    assert response.status_code == 422 and response.json()["detail"] == "unsupported_type"


async def test_avatar_storage_down_is_503_and_profile_untouched(
    api: tuple[httpx.AsyncClient, AsyncSession], monkeypatch: pytest.MonkeyPatch
) -> None:
    async def broken_put_object(key: str, data: bytes, content_type: str) -> None:
        raise storage.StorageError("down")

    monkeypatch.setattr(storage, "put_object", broken_put_object)
    http, session = api
    await _login(http, session, phone=PHONE)
    jpeg = b"\xff\xd8\xff\xe0" + b"\x00" * 64
    response = await http.post(
        "/identity/profile/avatar", files={"file": ("me.jpg", jpeg, "image/jpeg")}
    )
    assert response.status_code == 503
    assert (await http.get("/identity/profile")).json()["has_avatar"] is False


# --- ID-U1 P7: what's missing, and serving the photo back -------------------


async def test_missing_lists_empty_parts_heaviest_first(
    api: tuple[httpx.AsyncClient, AsyncSession],
) -> None:
    http, session = api
    await _login(http, session, phone=PHONE)
    body = (await http.get("/identity/profile")).json()
    # phone is verified by logging in; everything else is still empty, and the
    # order is by WEIGHT so the heaviest missing piece is offered first.
    assert body["missing"] == ["location", "name", "interests", "avatar", "language"]
    assert "phone_verified" not in body["missing"]


async def test_missing_and_score_stay_in_agreement(
    api: tuple[httpx.AsyncClient, AsyncSession], geo_row: str
) -> None:
    http, session = api
    await _login(http, session, phone=PHONE)
    await http.patch("/identity/profile", json={"name": "Murugesan"})
    body = (await http.patch("/identity/profile", json={"pincode": geo_row})).json()
    assert "name" not in body["missing"] and "location" not in body["missing"]
    # the two renderings of one reading: everything absent from `missing` is
    # exactly what the score counted.
    from modules.identity.completion import WEIGHTS

    assert body["completion_score"] == sum(
        weight for part, weight in WEIGHTS.items() if part not in body["missing"]
    )


async def test_avatar_is_served_back_to_its_owner(
    api: tuple[httpx.AsyncClient, AsyncSession], monkeypatch: pytest.MonkeyPatch
) -> None:
    stored: dict[str, bytes] = {}

    async def fake_put(key: str, data: bytes, content_type: str) -> None:
        stored[key] = data

    async def fake_get(key: str) -> bytes:
        return stored[key]

    monkeypatch.setattr(storage, "put_object", fake_put)
    monkeypatch.setattr(storage, "get_object", fake_get)
    http, session = api
    await _login(http, session, phone=PHONE)
    png = b"\x89PNG\r\n\x1a\n" + b"\x00" * 64
    await http.post("/identity/profile/avatar", files={"file": ("me.png", png, "image/png")})

    response = await http.get("/identity/profile/avatar")
    assert response.status_code == 200
    assert response.content == png
    # content type comes from the stored EXTENSION, not from whatever the
    # upload part claimed - the same rule the upload path already follows.
    assert response.headers["content-type"].startswith("image/png")
    # one person's face: no shared cache may keep it.
    assert "private" in response.headers["cache-control"]


async def test_avatar_404s_when_there_is_none(
    api: tuple[httpx.AsyncClient, AsyncSession],
) -> None:
    http, session = api
    await _login(http, session, phone=PHONE)
    response = await http.get("/identity/profile/avatar")
    assert response.status_code == 404 and response.json()["detail"] == "no_avatar"


async def test_avatar_requires_a_session(
    api: tuple[httpx.AsyncClient, AsyncSession],
) -> None:
    http, _session = api
    # No login: the photo route is owner-scoped like every other profile route.
    assert (await http.get("/identity/profile/avatar")).status_code == 401
