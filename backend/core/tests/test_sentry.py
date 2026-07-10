"""Sentry is a no-op without a DSN and initialises with one."""

from settings import Settings
from shared.sentry import init_sentry


def test_no_dsn_no_init() -> None:
    assert init_sentry(Settings(sentry_dsn="")) is False


def test_dsn_initialises_with_release_and_env() -> None:
    import sentry_sdk

    settings = Settings(
        sentry_dsn="https://examplePublicKey@o0.ingest.sentry.io/0",
        release="abc123",
        app_env="test",
    )
    try:
        assert init_sentry(settings) is True
        client = sentry_sdk.get_client()
        assert client.options["release"] == "abc123"
        assert client.options["send_default_pii"] is False
    finally:
        # the sdk client is process-global: leaving it active would capture
        # deliberate test exceptions and try to flush them over the network
        # at interpreter exit. Re-init without a DSN disables it.
        sentry_sdk.init(dsn=None)
