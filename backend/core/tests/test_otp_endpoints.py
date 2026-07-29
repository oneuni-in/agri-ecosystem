"""D07.E endpoints: /auth/otp/request + /auth/otp/verify on the real app.

The enumeration tests are the point: for a well-formed phone, every response
(status, body) is byte-identical whether or not the phone belongs to a
registered user."""

from collections.abc import AsyncIterator

import httpx
import pytest
from redis.asyncio import Redis
from sqlalchemy import update
from sqlalchemy.ext.asyncio import AsyncSession

from main import create_app
from modules.identity.otp_drivers import MockDriver
from modules.identity.otp_limits import (
    OTP_MAX_ATTEMPTS,
    OTP_PROOF_TTL_SECONDS,
    RESEND_COOLDOWNS_SECONDS,
)
from modules.identity.otp_service import consume_otp_proof
from modules.identity.service import create_user
from settings import get_settings
from shared.db import get_engine, get_session, reset_engine
from shared.flags import FeatureFlag, reset_flag_cache

REGISTERED = "+919876543210"
UNKNOWN = "+919876500001"


@pytest.fixture
async def api(
    db_session: AsyncSession, otp_redis: Redis
) -> AsyncIterator[tuple[httpx.AsyncClient, AsyncSession, Redis]]:
    """Real app, test DB session, test redis; requests share the rollback tx."""
    app = create_app()

    async def _session_override() -> AsyncIterator[AsyncSession]:
        yield db_session

    app.dependency_overrides[get_session] = _session_override
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        yield client, db_session, otp_redis


async def request_otp(client: httpx.AsyncClient, phone: str, **extra: str) -> httpx.Response:
    return await client.post(
        "/auth/otp/request", json={"phone": phone, "purpose": "login", **extra}
    )


async def verify_otp_call(client: httpx.AsyncClient, phone: str, code: str) -> httpx.Response:
    return await client.post(
        "/auth/otp/verify", json={"phone": phone, "purpose": "login", "code": code}
    )


async def test_request_and_verify_round_trip(
    api: tuple[httpx.AsyncClient, AsyncSession, Redis],
) -> None:
    client, _session, _redis = api
    response = await request_otp(client, REGISTERED)
    assert response.status_code == 200
    assert response.json() == {"status": "sent"}

    code = MockDriver.last_code(REGISTERED)
    assert code is not None
    verified = await verify_otp_call(client, REGISTERED, code)
    assert verified.status_code == 200
    body = verified.json()
    assert body["expires_in"] == OTP_PROOF_TTL_SECONDS
    # the proof is real, single-use, and NOT a session/JWT
    assert await consume_otp_proof(body["otp_proof"]) == (REGISTERED, "login")
    assert await consume_otp_proof(body["otp_proof"]) is None


async def test_request_responses_identical_for_known_and_unknown_phone(
    api: tuple[httpx.AsyncClient, AsyncSession, Redis],
) -> None:
    client, session, _redis = api
    await create_user(session, REGISTERED)

    known = await request_otp(client, REGISTERED)
    unknown = await request_otp(client, UNKNOWN)
    assert known.status_code == unknown.status_code == 200
    assert known.json() == unknown.json()


async def test_verify_failure_identical_for_known_and_unknown_phone(
    api: tuple[httpx.AsyncClient, AsyncSession, Redis],
) -> None:
    client, session, _redis = api
    await create_user(session, REGISTERED)
    await request_otp(client, REGISTERED)  # active code exists for REGISTERED

    wrong_code = await verify_otp_call(client, REGISTERED, "000000")
    never_issued = await verify_otp_call(client, UNKNOWN, "000000")
    if wrong_code.status_code == 200:  # pragma: no cover - 1-in-10^6 guess
        pytest.skip("guessed the real code")
    assert wrong_code.status_code == never_issued.status_code == 400
    assert wrong_code.json() == never_issued.json() == {"detail": "invalid_or_expired_code"}


async def test_request_during_cooldown_is_429_with_retry_after(
    api: tuple[httpx.AsyncClient, AsyncSession, Redis],
) -> None:
    client, _session, _redis = api
    assert (await request_otp(client, REGISTERED)).status_code == 200
    throttled = await request_otp(client, REGISTERED)
    assert throttled.status_code == 429
    assert 0 < int(throttled.headers["Retry-After"]) <= RESEND_COOLDOWNS_SECONDS[0]


async def test_malformed_phone_is_422_on_both_endpoints(
    api: tuple[httpx.AsyncClient, AsyncSession, Redis],
) -> None:
    client, _session, _redis = api
    assert (await request_otp(client, "12345")).status_code == 422
    assert (await verify_otp_call(client, "12345", "123456")).status_code == 422


async def test_unknown_purpose_is_422(api: tuple[httpx.AsyncClient, AsyncSession, Redis]) -> None:
    client, _session, _redis = api
    response = await client.post(
        "/auth/otp/request", json={"phone": REGISTERED, "purpose": "steal_account"}
    )
    assert response.status_code == 422


@pytest.fixture
async def persistent_api(
    database_url: str, otp_redis: Redis, monkeypatch: pytest.MonkeyPatch
) -> AsyncIterator[httpx.AsyncClient]:
    """App on the migrated test DB with REAL per-request sessions (no override):
    commits and rollbacks behave exactly as in production."""
    monkeypatch.setenv("DATABASE_URL", database_url)
    get_settings.cache_clear()
    reset_engine()
    app = create_app()
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        yield client
    await get_engine().dispose()


async def test_attempt_burn_survives_request_rollback(persistent_api: httpx.AsyncClient) -> None:
    # a failed verify returns 400 via an exception, which skips the session
    # dependency's commit - the attempt counter must be committed anyway, or
    # burn-after-3 would silently reset between requests (unlimited brute force)
    phone = "+919876511111"  # unique to this test: rows commit for real
    assert (await request_otp(persistent_api, phone)).status_code == 200
    code = MockDriver.last_code(phone)
    assert code is not None
    wrong = "000000" if code != "000000" else "000001"
    for _ in range(OTP_MAX_ATTEMPTS):
        assert (await verify_otp_call(persistent_api, phone, wrong)).status_code == 400
    burned = await verify_otp_call(persistent_api, phone, code)
    assert burned.status_code == 400  # the correct code is dead after 3 misses


async def test_device_fingerprint_is_accepted_and_stored(
    api: tuple[httpx.AsyncClient, AsyncSession, Redis],
) -> None:
    client, _session, redis = api
    response = await request_otp(client, REGISTERED, device_fingerprint="fp-abc")
    assert response.status_code == 200
    assert int(await redis.get("otp:day:dev:fp-abc") or 0) == 1


async def test_request_is_refused_when_signup_is_gated(
    api: tuple[httpx.AsyncClient, AsyncSession, Redis],
) -> None:
    """D30.B: with the gate closed the route answers 503 signup_unavailable.

    The detail string is a contract - web-id keys the "login coming shortly"
    notice off it, so changing it silently degrades that screen to a generic
    error.
    """
    client, session, _redis = api
    await session.execute(
        update(FeatureFlag).where(FeatureFlag.key == "signup_enabled").values(enabled=False)
    )
    await session.flush()
    reset_flag_cache()
    try:
        response = await request_otp(client, REGISTERED)

        assert response.status_code == 503
        assert response.json() == {"detail": "signup_unavailable"}
        # and no code was issued
        assert MockDriver.last_code(REGISTERED) is None
    finally:
        reset_flag_cache()
