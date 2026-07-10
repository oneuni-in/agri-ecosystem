"""Sentry initialisation: no DSN, no-op — activation is environment-only.

send_default_pii stays False and request bodies are never attached; the log
side of PII hygiene is telemetry.PiiScrubFilter.
"""

import sentry_sdk

from settings import Settings


def init_sentry(settings: Settings) -> bool:
    """Initialise Sentry when a DSN is configured; returns True if it was."""
    if not settings.sentry_dsn:
        return False
    sentry_sdk.init(
        dsn=settings.sentry_dsn,
        environment=settings.app_env,
        release=settings.release or None,
        traces_sample_rate=settings.sentry_traces_sample_rate,
        send_default_pii=False,
        max_request_body_size="never",
    )
    return True
