"""Sentry is a no-op without a DSN and initialises with one."""

from settings import Settings
from shared.sentry import init_sentry


def test_no_dsn_no_init() -> None:
    assert init_sentry(Settings(sentry_dsn="")) is False


def test_dsn_initialises_with_release_and_env() -> None:
    settings = Settings(
        sentry_dsn="https://examplePublicKey@o0.ingest.sentry.io/0",
        release="abc123",
        app_env="test",
    )
    assert init_sentry(settings) is True
    import sentry_sdk

    client = sentry_sdk.get_client()
    assert client.options["release"] == "abc123"
    assert client.options["send_default_pii"] is False
