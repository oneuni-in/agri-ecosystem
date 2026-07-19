"""Contact reveal throttle (D18.C, anti-scraping).

Fail-closed by design (OTP-throttle precedent): Redis down means 503, never
an uncapped reveal - the cap IS the scraping defence and is never bypassed.
Fixed daily window via INCR+EXPIRE; the increment happens BEFORE the numbers
leave the process, so a crash mid-request costs the user one slot, never
grants a free reveal."""

import uuid
from datetime import datetime

from redis.exceptions import RedisError

from settings import get_settings
from shared.cache import get_redis

_DAY_SECONDS = 86400


class RevealCapExceededError(Exception):
    pass


class RevealUnavailableError(Exception):
    pass


async def claim_reveal_slot(user_id: uuid.UUID, *, now: datetime) -> None:
    cap = get_settings().contact_reveal_daily_cap
    key = f"reveal:{user_id}:{now.strftime('%Y%m%d')}"
    try:
        redis = get_redis()
        count = int(await redis.incr(key))
        if count == 1:
            await redis.expire(key, _DAY_SECONDS)
    except RedisError as exc:
        raise RevealUnavailableError() from exc
    if count > cap:
        raise RevealCapExceededError()
