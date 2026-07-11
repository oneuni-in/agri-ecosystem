"""RS256 signing key management + JWKS (D08.C) - no HTTP here.

The private key is env-provided PEM (OAUTH_JWT_PRIVATE_KEY_PEM, "\\n" escapes
accepted for single-line env files) with its kid in OAUTH_JWT_KID. Rules:

- prod with no key is a hard configuration error - the server must fail at
  boot, never mint unverifiable tokens.
- dev/test with no key generates an ephemeral RSA-2048 keypair per process via
  joserfc (authlib's JOSE successor - no hand-rolled crypto). Tokens die with
  the process; fine for dev and CI.
- OAUTH_JWT_EXTRA_PUBLIC_KEYS_PEM holds retired/incoming PUBLIC keys so JWKS
  keeps every verifiable kid resolvable during rotation overlap
  (docs/runbooks/jwks-rotation.md). kids for extra keys are RFC 7638
  thumbprints unless the PEM owner pins one.

Everything is cached per process; reset_oauth_keys() is for tests (the
settings cache is cleared between tests, so key caches must follow).
"""

from joserfc.jwk import KeyParameters, KeySet, KeySetSerialization, RSAKey

from settings import get_settings
from shared.telemetry import get_logger

logger = get_logger(__name__)

_signing_key: RSAKey | None = None
_key_set: KeySet | None = None


class OAuthKeyConfigError(RuntimeError):
    """Raised when the environment demands a real key and none is configured."""


def reset_oauth_keys() -> None:
    global _signing_key, _key_set
    _signing_key = None
    _key_set = None


def _normalize_pem(raw: str) -> str:
    # single-line env files carry literal "\n"; real newlines pass through
    return raw.replace("\\n", "\n").strip()


def _sig_params(kid: str | None = None) -> KeyParameters:
    params: KeyParameters = {"use": "sig", "alg": "RS256"}
    if kid is not None:
        params["kid"] = kid
    return params


def get_signing_key() -> RSAKey:
    """The active private key. Generates an ephemeral one in dev/test only."""
    global _signing_key
    if _signing_key is not None:
        return _signing_key
    settings = get_settings()
    pem = _normalize_pem(settings.oauth_jwt_private_key_pem)
    if pem:
        key = RSAKey.import_key(pem, parameters=_sig_params(settings.oauth_jwt_kid))
    elif settings.app_env == "prod":
        raise OAuthKeyConfigError(
            "OAUTH_JWT_PRIVATE_KEY_PEM is required in prod - refusing to start "
            "without a stable RS256 signing key"
        )
    else:
        logger.warning(
            "no OAUTH_JWT_PRIVATE_KEY_PEM set; generating ephemeral RS256 keypair "
            "(dev/test only - tokens will not survive a restart)"
        )
        key = RSAKey.generate_key(2048, parameters=_sig_params(settings.oauth_jwt_kid))
    _signing_key = key
    return key


def _extra_public_keys() -> list[RSAKey]:
    raw = _normalize_pem(get_settings().oauth_jwt_extra_public_keys_pem)
    if not raw:
        return []
    marker = "-----END PUBLIC KEY-----"
    keys = []
    for chunk in raw.split(marker):
        if chunk.strip():
            key = RSAKey.import_key(chunk + marker, parameters=_sig_params())
            if key.dict_value.get("kid") is None:
                key.ensure_kid()  # RFC 7638 thumbprint
            keys.append(key)
    return keys


def get_key_set() -> KeySet:
    """Every key a downstream verifier may need: active + rotation extras."""
    global _key_set
    if _key_set is None:
        _key_set = KeySet([get_signing_key(), *_extra_public_keys()])
    return _key_set


def get_jwks() -> KeySetSerialization:
    """Public JWKS document for /.well-known/jwks.json - private members never
    leave this module."""
    return get_key_set().as_dict(private=False)
