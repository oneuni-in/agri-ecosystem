"""Application settings loaded from the environment via pydantic-settings."""

from functools import lru_cache
from typing import Literal

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    app_env: Literal["dev", "test", "prod"] = "dev"
    debug: bool = False
    log_level: str = "INFO"

    # Sentry is READY BUT INACTIVE: no SENTRY_DSN in the environment means
    # init_sentry() is a no-op. Activation: docs/runbooks/monitoring.md.
    sentry_dsn: str = ""
    sentry_traces_sample_rate: float = 0.1
    release: str = ""  # git sha, baked into images as the RELEASE env var

    api_host: str = "0.0.0.0"
    api_port: int = 8000

    # dev-only defaults; real values come from the environment
    # compose maps postgres to host port 55432 (5432 collides with native installs)
    database_url: str = "postgresql+asyncpg://app:app@localhost:55432/agri"
    redis_url: str = "redis://localhost:6379/0"
    meilisearch_url: str = "http://localhost:7700"
    meilisearch_master_key: str = ""
    minio_endpoint: str = "http://localhost:9000"
    minio_access_key: str = ""
    minio_secret_key: str = ""
    minio_bucket: str = "agri-media"

    rate_limit_requests: int = 60
    rate_limit_window_seconds: int = 60


@lru_cache
def get_settings() -> Settings:
    return Settings()
