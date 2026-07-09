"""Settings load from environment with sane dev defaults."""

import pytest

from settings import get_settings


def test_defaults() -> None:
    settings = get_settings()
    assert settings.app_env == "dev"
    assert settings.rate_limit_requests == 60
    assert settings.rate_limit_window_seconds == 60
    assert settings.database_url.startswith("postgresql+asyncpg://")


def test_env_override(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("RATE_LIMIT_REQUESTS", "5")
    get_settings.cache_clear()
    assert get_settings().rate_limit_requests == 5


def test_settings_are_cached() -> None:
    assert get_settings() is get_settings()
