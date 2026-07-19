"""Contact reveal - cap + DPDP log + strip public phones (D18.C).

Non-negotiable 3: the daily reveal cap is enforced (increment-then-check,
BEFORE numbers leave the process) and every reveal is logged without the
plaintext phone/whatsapp ever reaching a log line. Public detail structurally
lacks phone/whatsapp keys - reveal is a separate, capped, logged endpoint."""

import uuid
from collections.abc import AsyncIterator
from decimal import Decimal

import httpx
import pytest
from fastapi import Request
from redis.asyncio import Redis
from redis.exceptions import RedisError
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from main import create_app
from modules.directory import service
from modules.directory.leads_models import ContactReveal
from settings import get_settings
from shared.cache import reset_redis
from shared.db import get_session
from shared.security import register_principal_resolver

pytestmark = pytest.mark.asyncio

TEST_REDIS_DB = 9
PHONE = "+916374000001"
WHATSAPP = "+916374000002"


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


@pytest.fixture
async def reveal_redis(
    redis_client: Redis, monkeypatch: pytest.MonkeyPatch
) -> AsyncIterator[Redis]:
    """Point shared.cache.get_redis at the flushed test redis DB (mirrors the
    otp_redis fixture pattern in test_otp_throttle.py)."""
    url = get_settings().redis_url.rsplit("/", 1)[0] + f"/{TEST_REDIS_DB}"
    monkeypatch.setenv("REDIS_URL", url)
    get_settings.cache_clear()
    reset_redis()
    yield redis_client


async def _seeded_branch(
    session: AsyncSession, owner: uuid.UUID, *, phone: str = PHONE, whatsapp: str = WHATSAPP
) -> tuple[str, uuid.UUID]:
    """Create an active business with one branch; return (slug, branch_id)."""
    business = await service.create_business(
        session,
        owner_user_id=owner,
        name="Anbu Milk Farm",
        type_="vendor",
        primary_pincode="641001",
    )
    branch = await service.add_branch(
        session,
        owner_user_id=owner,
        business_id=business.id,
        address="1 Mettupalayam Rd",
        state="Tamil Nadu",
        district="Coimbatore",
        pincode="641001",
        lat=Decimal("10.923220"),
        lng=Decimal("76.968600"),
        phone=phone,
        whatsapp=whatsapp,
    )
    await session.commit()
    return business.slug, branch.id


async def test_public_detail_has_no_contact_fields(
    api: tuple[httpx.AsyncClient, AsyncSession],
) -> None:
    http, session = api
    slug, _branch_id = await _seeded_branch(session, uuid.uuid4())
    detail = await http.get(f"/directory/businesses/{slug}")
    assert detail.status_code == 200
    branches = detail.json()["branches"]
    assert len(branches) == 1
    # key absence, not null - a scraper must learn nothing from the shape
    assert "phone" not in branches[0]
    assert "whatsapp" not in branches[0]


async def test_reveal_requires_login(api: tuple[httpx.AsyncClient, AsyncSession]) -> None:
    http, session = api
    _slug, branch_id = await _seeded_branch(session, uuid.uuid4())
    response = await http.post(f"/directory/branches/{branch_id}/reveal")
    assert response.status_code == 401


async def test_reveal_returns_numbers_and_logs(
    api: tuple[httpx.AsyncClient, AsyncSession], reveal_redis: Redis
) -> None:
    http, session = api
    owner = uuid.uuid4()
    caller = uuid.uuid4()
    _slug, branch_id = await _seeded_branch(session, owner)
    response = await http.post(f"/directory/branches/{branch_id}/reveal", headers=_as(caller))
    assert response.status_code == 200
    body = response.json()
    assert body == {"branch_id": str(branch_id), "phone": PHONE, "whatsapp": WHATSAPP}
    row = await session.scalar(
        select(ContactReveal).where(
            ContactReveal.user_id == caller,
            ContactReveal.branch_id == branch_id,
        )
    )
    assert row is not None
    assert row.business_id is not None
    # the log is evidence THAT a reveal happened, never WHAT was revealed
    assert not hasattr(ContactReveal, "phone")
    assert not hasattr(ContactReveal, "whatsapp")


async def test_reveal_daily_cap_enforced(
    api: tuple[httpx.AsyncClient, AsyncSession],
    reveal_redis: Redis,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("CONTACT_REVEAL_DAILY_CAP", "3")
    get_settings.cache_clear()
    http, session = api
    owner = uuid.uuid4()
    caller = uuid.uuid4()
    _slug, branch_id = await _seeded_branch(session, owner)
    for _ in range(3):
        ok = await http.post(f"/directory/branches/{branch_id}/reveal", headers=_as(caller))
        assert ok.status_code == 200
    blocked = await http.post(f"/directory/branches/{branch_id}/reveal", headers=_as(caller))
    assert blocked.status_code == 429
    assert blocked.json()["detail"] == "reveal_cap_exceeded"


async def test_reveal_fails_closed_without_redis(
    api: tuple[httpx.AsyncClient, AsyncSession], monkeypatch: pytest.MonkeyPatch
) -> None:
    def _broken_get_redis() -> Redis:
        raise RedisError("redis unreachable")

    monkeypatch.setattr("modules.directory.reveal.get_redis", _broken_get_redis)
    http, session = api
    owner = uuid.uuid4()
    caller = uuid.uuid4()
    _slug, branch_id = await _seeded_branch(session, owner)
    response = await http.post(f"/directory/branches/{branch_id}/reveal", headers=_as(caller))
    assert response.status_code == 503
    assert response.json()["detail"] == "reveal_unavailable"


async def test_reveal_log_line_has_no_phone(
    api: tuple[httpx.AsyncClient, AsyncSession],
    reveal_redis: Redis,
    caplog: pytest.LogCaptureFixture,
) -> None:
    http, session = api
    owner = uuid.uuid4()
    caller = uuid.uuid4()
    _slug, branch_id = await _seeded_branch(session, owner)
    with caplog.at_level("INFO"):
        response = await http.post(f"/directory/branches/{branch_id}/reveal", headers=_as(caller))
    assert response.status_code == 200
    assert PHONE not in caplog.text
    assert "637400" not in caplog.text
