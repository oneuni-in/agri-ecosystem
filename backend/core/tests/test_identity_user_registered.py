"""D13 producer contract: /auth/login emits user.registered exactly once for
a brand-new account, carrying the caller-supplied referral_code and a coarse
4-char phone_prefix - never the full phone number. Existing-account logins
publish nothing. Mirrors the harness in tests/test_session_router.py."""

from collections.abc import AsyncIterator
from unittest.mock import AsyncMock, patch

import httpx
import pytest
from redis.asyncio import Redis
from sqlalchemy.ext.asyncio import AsyncSession

from main import create_app
from modules.identity.otp_service import issue_otp, verify_otp
from shared.db import get_session

pytestmark = pytest.mark.asyncio

NEW_PHONE = "+919876540001"
UA = {"user-agent": "pytest-browser", "sec-ch-ua-platform": '"Windows"'}


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


async def _otp_proof(session: AsyncSession, phone: str) -> str:
    # fresh throttle ladder per call - these tests exercise the user.registered
    # contract, not the D07 resend cooldown
    from shared.cache import get_redis

    await get_redis().flushdb()
    await issue_otp(session, phone=phone, purpose="login", ip=None, device_fingerprint=None)
    from modules.identity.otp_drivers import MockDriver

    code = MockDriver.last_code(phone)
    assert code is not None
    return await verify_otp(session, phone=phone, purpose="login", code=code, ip=None)


async def _login(
    http: httpx.AsyncClient, session: AsyncSession, phone: str, referral_code: str | None = None
) -> httpx.Response:
    proof = await _otp_proof(session, phone)
    body: dict[str, str] = {"otp_proof": proof}
    if referral_code is not None:
        body["referral_code"] = referral_code
    return await http.post("/auth/login", json=body)


async def test_new_user_publishes_user_registered_once_with_referral_and_prefix(
    api: tuple[httpx.AsyncClient, AsyncSession],
) -> None:
    http, session = api
    with patch("modules.identity.session_router.publish", new=AsyncMock()) as pub:
        response = await _login(http, session, NEW_PHONE, referral_code="ABCD1234")
        assert response.status_code == 200
        assert response.json()["is_new_user"] is True

        # (1) exactly one user.registered published for the new phone
        types = [c.args[1] for c in pub.await_args_list]
        assert types.count("user.registered") == 1

        call = next(c for c in pub.await_args_list if c.args[1] == "user.registered")
        stream, event_type, payload = call.args
        assert stream == "identity"
        assert event_type == "user.registered"

        # (3) referral_code passed through verbatim
        assert payload["referral_code"] == "ABCD1234"

        # (4) phone_prefix is a coarse 4-char prefix; the FULL phone never
        # appears anywhere in the payload values
        assert payload["phone_prefix"] == NEW_PHONE[:4]
        assert len(payload["phone_prefix"]) == 4
        assert NEW_PHONE not in payload.values()

        body = response.json()
        assert payload["agri_id"] == body["agri_id"]
        assert isinstance(payload["user_id"], str)

        # (2) logging in again with the SAME (now-existing) phone publishes
        # NO further user.registered
        pub.reset_mock()
        second = await _login(http, session, NEW_PHONE)
        assert second.status_code == 200
        assert second.json()["is_new_user"] is False
        assert [c.args[1] for c in pub.await_args_list] == []
