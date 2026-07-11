"""D08.C key management: env PEM, ephemeral dev fallback, prod fail-fast, and
a JWKS that never leaks private members."""

import logging

import pytest
from joserfc.jwk import RSAKey

from modules.identity.oauth_keys import (
    OAuthKeyConfigError,
    get_jwks,
    get_signing_key,
    reset_oauth_keys,
)
from settings import get_settings

RSA_PRIVATE_MEMBERS = {"d", "p", "q", "dp", "dq", "qi"}


def _reload_env(monkeypatch: pytest.MonkeyPatch, **env: str) -> None:
    for name, value in env.items():
        monkeypatch.setenv(name, value)
    get_settings.cache_clear()
    reset_oauth_keys()


def test_dev_without_pem_generates_ephemeral_key(
    monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture
) -> None:
    _reload_env(monkeypatch, APP_ENV="dev", OAUTH_JWT_PRIVATE_KEY_PEM="")
    with caplog.at_level(logging.WARNING):
        key = get_signing_key()
    assert key.is_private
    assert key.kid == get_settings().oauth_jwt_kid
    assert "ephemeral" in caplog.text


def test_ephemeral_key_is_cached_per_process(monkeypatch: pytest.MonkeyPatch) -> None:
    _reload_env(monkeypatch, APP_ENV="dev", OAUTH_JWT_PRIVATE_KEY_PEM="")
    assert get_signing_key() is get_signing_key()


def test_prod_without_pem_refuses_to_start(monkeypatch: pytest.MonkeyPatch) -> None:
    _reload_env(monkeypatch, APP_ENV="prod", OAUTH_JWT_PRIVATE_KEY_PEM="")
    with pytest.raises(OAuthKeyConfigError):
        get_signing_key()


def test_env_pem_wins_and_accepts_escaped_newlines(monkeypatch: pytest.MonkeyPatch) -> None:
    source = RSAKey.generate_key(2048)
    pem_one_line = source.as_pem(private=True).decode().replace("\n", "\\n")
    _reload_env(
        monkeypatch,
        APP_ENV="prod",
        OAUTH_JWT_PRIVATE_KEY_PEM=pem_one_line,
        OAUTH_JWT_KID="prod-2026-07",
    )
    key = get_signing_key()
    assert key.is_private
    assert key.kid == "prod-2026-07"
    assert key.thumbprint() == source.thumbprint()


def test_jwks_serves_active_key_without_private_members(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _reload_env(monkeypatch, APP_ENV="dev", OAUTH_JWT_PRIVATE_KEY_PEM="")
    jwks = get_jwks()
    assert len(jwks["keys"]) == 1
    entry = jwks["keys"][0]
    assert entry["kty"] == "RSA"
    assert entry["alg"] == "RS256"
    assert entry["use"] == "sig"
    assert entry["kid"] == get_settings().oauth_jwt_kid
    assert not RSA_PRIVATE_MEMBERS & entry.keys()


def test_jwks_includes_extra_public_keys_for_rotation(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    retired = RSAKey.generate_key(2048)
    incoming = RSAKey.generate_key(2048)
    both = (
        retired.as_pem(private=False).decode() + incoming.as_pem(private=False).decode()
    ).replace("\n", "\\n")
    _reload_env(
        monkeypatch,
        APP_ENV="dev",
        OAUTH_JWT_PRIVATE_KEY_PEM="",
        OAUTH_JWT_EXTRA_PUBLIC_KEYS_PEM=both,
    )
    jwks = get_jwks()
    assert len(jwks["keys"]) == 3
    kids = [entry["kid"] for entry in jwks["keys"]]
    assert len(set(kids)) == 3  # extras get RFC 7638 thumbprint kids
    for entry in jwks["keys"]:
        assert not RSA_PRIVATE_MEMBERS & entry.keys()
