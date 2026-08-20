# backend/core/tests/test_startup_checks.py
"""Prod must refuse to boot on a credential that ships in this repository.

Several settings carry a working dev default so a clone runs with no setup:
the OTP pepper, the two beacon secrets, the MinIO keys and the app_rt/app
database passwords. Each is published here, so any of them reaching a real
deployment is a live compromise - the pepper worst of all, since it is the
only thing standing between a stolen otp table and a 10^6 brute force.

Nothing enforced that before: settings.py has no validators, secrets/
staging.env.example does not carry the lines, and the one existing boot guard
(get_signing_key) covers only the OAuth key. These tests pin the guard.
"""

import pytest
from fastapi.testclient import TestClient

from main import create_app
from settings import get_settings
from shared.startup_checks import InsecureDefaultError, check_production_secrets

# every dev default the guard knows about, and a safe replacement
REAL_SECRETS = {
    "OTP_PEPPER": "a-real-32-byte-pepper-from-sops",
    "VIEW_BEACON_SECRET": "a-real-view-beacon-secret",
    "ADS_BEACON_SECRET": "a-real-ads-beacon-secret",
    "MINIO_ACCESS_KEY": "prod-access-key",
    "MINIO_SECRET_KEY": "prod-secret-key",
    "DATABASE_URL": "postgresql+asyncpg://app_rt:s3cret@db:5432/agri",
    "DATABASE_ADMIN_URL": "postgresql+asyncpg://app:s3cret@db:5432/agri",
}


def _prod_with(monkeypatch: pytest.MonkeyPatch, **overrides: str) -> None:
    monkeypatch.setenv("APP_ENV", "prod")
    for key, value in {**REAL_SECRETS, **overrides}.items():
        monkeypatch.setenv(key, value)
    get_settings.cache_clear()


def test_prod_boots_when_every_secret_is_real(monkeypatch: pytest.MonkeyPatch) -> None:
    _prod_with(monkeypatch)
    check_production_secrets(get_settings())  # must not raise


@pytest.mark.parametrize(
    ("env_var", "dev_default"),
    [
        ("OTP_PEPPER", "dev-only-pepper"),
        ("VIEW_BEACON_SECRET", "dev-view-beacon-secret"),
        ("ADS_BEACON_SECRET", "dev-ads-beacon-secret"),
        ("MINIO_ACCESS_KEY", "minioadmin"),
        ("MINIO_SECRET_KEY", "minioadmin"),
        ("DATABASE_URL", "postgresql+asyncpg://app_rt:app_rt@localhost:55432/agri"),
        ("DATABASE_ADMIN_URL", "postgresql+asyncpg://app:app@localhost:55432/agri"),
    ],
)
def test_prod_refuses_each_dev_default(
    monkeypatch: pytest.MonkeyPatch, env_var: str, dev_default: str
) -> None:
    _prod_with(monkeypatch, **{env_var: dev_default})
    with pytest.raises(InsecureDefaultError) as excinfo:
        check_production_secrets(get_settings())
    assert env_var in str(excinfo.value)


def test_error_names_every_offender_not_just_the_first(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """An operator fixing these one restart at a time is the failure mode this
    avoids - the message must list all of them at once."""
    _prod_with(
        monkeypatch,
        OTP_PEPPER="dev-only-pepper",
        ADS_BEACON_SECRET="dev-ads-beacon-secret",
        MINIO_SECRET_KEY="minioadmin",
    )
    with pytest.raises(InsecureDefaultError) as excinfo:
        check_production_secrets(get_settings())
    message = str(excinfo.value)
    assert "OTP_PEPPER" in message
    assert "ADS_BEACON_SECRET" in message
    assert "MINIO_SECRET_KEY" in message
    assert "VIEW_BEACON_SECRET" not in message  # that one was set properly


def test_error_does_not_leak_the_configured_value(monkeypatch: pytest.MonkeyPatch) -> None:
    """The message goes to logs and Sentry; it names settings, never values."""
    _prod_with(monkeypatch, OTP_PEPPER="dev-only-pepper")
    with pytest.raises(InsecureDefaultError) as excinfo:
        check_production_secrets(get_settings())
    assert "dev-only-pepper" not in str(excinfo.value)


@pytest.mark.parametrize("env", ["dev", "test"])
def test_dev_and_test_tolerate_the_defaults(monkeypatch: pytest.MonkeyPatch, env: str) -> None:
    """The defaults exist so a clone runs with no setup; the guard is only
    about prod. A local run must not be broken by it."""
    monkeypatch.setenv("APP_ENV", env)
    get_settings.cache_clear()
    check_production_secrets(get_settings())  # must not raise


def test_app_refuses_to_start_in_prod_with_a_dev_secret(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The guard has to run at boot to be worth anything.

    It also has to run BEFORE get_signing_key(), which is why this expects
    InsecureDefaultError rather than OAuthKeyConfigError: prod here has no
    OAUTH_JWT_PRIVATE_KEY_PEM either, so whichever guard runs first decides
    the exception type.
    """
    _prod_with(monkeypatch, OTP_PEPPER="dev-only-pepper")
    with pytest.raises(InsecureDefaultError), TestClient(create_app()):
        pass  # pragma: no cover - lifespan raises on enter
