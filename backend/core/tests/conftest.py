"""Shared test fixtures: reset cached global state between tests."""

from collections.abc import Iterator

import pytest

from settings import get_settings
from shared.cache import reset_redis


@pytest.fixture(autouse=True)
def _reset_state() -> Iterator[None]:
    yield
    get_settings.cache_clear()
    reset_redis()
