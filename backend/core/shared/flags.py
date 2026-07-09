"""Feature flags: a DB table read through a short in-process cache.

Unknown flags are disabled (fail closed). Reads tolerate up to
FLAG_CACHE_TTL_SECONDS of staleness per process; flips take effect on the
next cache expiry without a deploy.
"""

import time

from sqlalchemy import Text, false, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import Mapped, mapped_column

from shared.db import Base, TimestampMixin, get_sessionmaker

FLAG_CACHE_TTL_SECONDS = 30.0

_cache: dict[str, tuple[float, bool]] = {}


class FeatureFlag(TimestampMixin, Base):
    """public.feature_flags - key is the natural primary key."""

    __tablename__ = "feature_flags"

    key: Mapped[str] = mapped_column(Text, primary_key=True)
    enabled: Mapped[bool] = mapped_column(server_default=false(), nullable=False)
    description: Mapped[str] = mapped_column(Text, server_default="", nullable=False)


async def flag_enabled(key: str, *, session: AsyncSession | None = None) -> bool:
    """Cached flag read; opens its own session unless given one (tests)."""
    now = time.monotonic()
    cached = _cache.get(key)
    if cached is not None and now - cached[0] < FLAG_CACHE_TTL_SECONDS:
        return cached[1]

    query = select(FeatureFlag.enabled).where(FeatureFlag.key == key)
    if session is not None:
        value = await session.scalar(query)
    else:
        async with get_sessionmaker()() as own_session:
            value = await own_session.scalar(query)

    enabled = bool(value)
    _cache[key] = (now, enabled)
    return enabled


def reset_flag_cache() -> None:
    _cache.clear()
