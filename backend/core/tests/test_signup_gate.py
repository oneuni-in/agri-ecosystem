"""D30.B: signup is gated until DLT clears.

Two layers, and the second is the one that matters. The flag is the control we
lift when approval lands. The prod-on-mock refusal is an invariant: a flag
alone cannot stop someone enabling signup in production while the mock driver
is still configured, which would silently send real users nothing. The spec's
"do NOT launch real signup on the mock driver" has to be structural.
"""

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from modules.identity.signup_gate import signup_allowed
from settings import get_settings
from shared.flags import FeatureFlag, reset_flag_cache


async def _set_flag(session: AsyncSession, enabled: bool) -> None:
    # merge(), not add(): migration 0028 seeds this row, so an INSERT collides
    # with pk_feature_flags. merge upserts, which keeps these tests correct
    # whether or not the seed has been applied to the test database.
    await session.merge(FeatureFlag(key="signup_enabled", enabled=enabled, description="d30 test"))
    await session.flush()
    reset_flag_cache()


async def test_open_when_flag_enabled_in_dev(db_session: AsyncSession) -> None:
    await _set_flag(db_session, True)

    assert await signup_allowed(session=db_session) is True


async def test_closed_when_flag_disabled(db_session: AsyncSession) -> None:
    await _set_flag(db_session, False)

    assert await signup_allowed(session=db_session) is False


async def test_prod_on_mock_driver_refuses_even_with_flag_on(
    db_session: AsyncSession, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The invariant: flag ON, prod, mock driver -> still refused. Without this
    a single flag flip puts signup live while every OTP goes nowhere."""
    await _set_flag(db_session, True)
    monkeypatch.setenv("APP_ENV", "prod")
    monkeypatch.setenv("SMS_PROVIDER", "mock")
    get_settings.cache_clear()
    try:
        assert await signup_allowed(session=db_session) is False
    finally:
        get_settings.cache_clear()


async def test_prod_on_msg91_respects_the_flag(
    db_session: AsyncSession, monkeypatch: pytest.MonkeyPatch
) -> None:
    """With a real driver configured the invariant steps aside and the flag
    governs - otherwise lifting the gate after DLT approval would do nothing."""
    await _set_flag(db_session, True)
    monkeypatch.setenv("APP_ENV", "prod")
    monkeypatch.setenv("SMS_PROVIDER", "msg91")
    get_settings.cache_clear()
    try:
        assert await signup_allowed(session=db_session) is True
    finally:
        get_settings.cache_clear()


async def test_dev_on_mock_is_unaffected(
    db_session: AsyncSession, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Guard keys on prod ONLY. Dev and CI run the mock driver by design, and
    the D29 e2e suites drive real OTP login through it - if this ever fails,
    15+ specs go with it."""
    await _set_flag(db_session, True)
    monkeypatch.setenv("APP_ENV", "dev")
    monkeypatch.setenv("SMS_PROVIDER", "mock")
    get_settings.cache_clear()
    try:
        assert await signup_allowed(session=db_session) is True
    finally:
        get_settings.cache_clear()
