# backend/core/shared/startup_checks.py
"""Refuse to boot prod on a credential that ships in this repository.

Several settings carry a working dev default so a fresh clone runs with no
setup - the OTP pepper, the two beacon secrets, the MinIO keys, and the
app_rt/app database passwords. That convenience is only safe while the value
stays in dev: every one of them is published in settings.py and in the compose
files, so the same string reaching a real deployment is a live compromise.

`otp_pepper` is the sharp one. modules/identity/otp_service.py keys its
HMAC with it, and the module's own docstring names the pepper as the single
reason a stolen otp table is not brute-forceable across the 10^6 code space.
A published pepper deletes that property outright.

Nothing enforced this before. settings.py has no validators; the staging
template does not even carry the lines, so an operator filling it in as
written ships the dev pepper; and the one existing boot guard
(identity/oauth_keys.get_signing_key) covers the OAuth signing key alone.

The guard is deliberately narrow. It compares against the exact published
value rather than trying to judge whether a secret is "strong enough" - a
length or entropy rule would be guesswork that fails valid secrets and
invites the operator to work around it. Matching the known-bad string is
unambiguous, and the fix is always the same: set the variable.
"""

from settings import Settings


class InsecureDefaultError(RuntimeError):
    """A published dev credential is configured while app_env is prod."""


# (env var, settings attribute, the value published in this repo)
_EXACT_DEFAULTS: tuple[tuple[str, str, str], ...] = (
    ("OTP_PEPPER", "otp_pepper", "dev-only-pepper"),
    ("VIEW_BEACON_SECRET", "view_beacon_secret", "dev-view-beacon-secret"),
    ("ADS_BEACON_SECRET", "ads_beacon_secret", "dev-ads-beacon-secret"),
    ("MINIO_ACCESS_KEY", "minio_access_key", "minioadmin"),
    ("MINIO_SECRET_KEY", "minio_secret_key", "minioadmin"),
)

# DSNs are matched on the credential pair only: host, port and database name
# legitimately differ per environment, the password is the part that must not
# still be the one 0013 created the role with.
_EMBEDDED_CREDENTIALS: tuple[tuple[str, str, str], ...] = (
    ("DATABASE_URL", "database_url", "app_rt:app_rt@"),
    ("DATABASE_ADMIN_URL", "database_admin_url", "app:app@"),
)


def insecure_defaults(settings: Settings) -> list[str]:
    """Env var names still holding their published dev value, in declared order."""
    offenders = [
        env for env, attr, published in _EXACT_DEFAULTS if getattr(settings, attr) == published
    ]
    offenders.extend(
        env
        for env, attr, credential in _EMBEDDED_CREDENTIALS
        if credential in getattr(settings, attr)
    )
    return offenders


def check_production_secrets(settings: Settings) -> None:
    """Raise unless every published dev credential has been replaced.

    No-op outside prod: the defaults exist so a local clone runs unconfigured,
    and breaking that would only teach people to bypass the check.
    """
    if settings.app_env != "prod":
        return
    offenders = insecure_defaults(settings)
    if offenders:
        # names only - this message reaches logs and Sentry
        raise InsecureDefaultError(
            "refusing to start: these settings still hold the dev default published "
            "in this repository, set them to real secrets before serving traffic - "
            + ", ".join(offenders)
        )
