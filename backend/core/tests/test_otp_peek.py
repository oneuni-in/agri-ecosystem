"""The E2E peek route exists ONLY behind the flag and never in prod."""

from collections.abc import AsyncIterator, Callable, Coroutine

import httpx
import pytest
from redis.asyncio import Redis
from sqlalchemy.ext.asyncio import AsyncSession

from main import create_app
from modules.identity.otp_service import issue_otp
from modules.identity.otp_throttle import OtpRateLimited
from settings import get_settings
from shared.db import get_session

PHONE = "+919876550001"

MakeApi = Callable[[], Coroutine[None, None, httpx.AsyncClient]]


@pytest.fixture
def make_api(db_session: AsyncSession) -> MakeApi:
    async def _make() -> httpx.AsyncClient:
        app = create_app()

        async def _session_override() -> AsyncIterator[AsyncSession]:
            yield db_session

        app.dependency_overrides[get_session] = _session_override
        return httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="https://id.test")

    return _make


async def test_peek_absent_by_default(make_api: MakeApi, otp_redis: Redis) -> None:
    async with await make_api() as http:
        assert (await http.get("/auth/otp/_peek", params={"phone": PHONE})).status_code == 404


async def test_peek_returns_last_code_when_flagged(
    make_api: MakeApi,
    db_session: AsyncSession,
    otp_redis: Redis,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("OTP_TEST_PEEK", "true")
    get_settings.cache_clear()
    async with await make_api() as http:
        await issue_otp(db_session, phone=PHONE, purpose="login", ip=None, device_fingerprint=None)
        response = await http.get("/auth/otp/_peek", params={"phone": PHONE})
        assert response.status_code == 200
        code = response.json()["code"]
        assert code is not None and len(code) == 6


async def test_reset_clears_resend_cooldown_when_flagged(
    make_api: MakeApi,
    db_session: AsyncSession,
    otp_redis: Redis,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("OTP_TEST_PEEK", "true")
    get_settings.cache_clear()
    async with await make_api() as http:
        await issue_otp(db_session, phone=PHONE, purpose="login", ip=None, device_fingerprint=None)
        # immediate reissue is inside the 30s resend cooldown
        with pytest.raises(OtpRateLimited):
            await issue_otp(
                db_session, phone=PHONE, purpose="login", ip=None, device_fingerprint=None
            )
        response = await http.post("/auth/otp/_reset", json={"phone": PHONE})
        assert response.status_code == 200
        # ladder cleared: the same phone can be issued a code again at once
        await issue_otp(db_session, phone=PHONE, purpose="login", ip=None, device_fingerprint=None)


async def test_peek_never_mounts_in_prod(
    make_api: MakeApi, monkeypatch: pytest.MonkeyPatch, otp_redis: Redis
) -> None:
    monkeypatch.setenv("OTP_TEST_PEEK", "true")
    monkeypatch.setenv("APP_ENV", "prod")
    get_settings.cache_clear()
    async with await make_api() as http:
        assert (await http.get("/auth/otp/_peek", params={"phone": PHONE})).status_code == 404
