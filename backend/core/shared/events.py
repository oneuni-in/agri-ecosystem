"""Redis Streams event bus.

Modules communicate through streams (or public service interfaces), never by
importing each other. Each interested module consumes through its own consumer
group, so every group sees every event exactly once. Messages that exceed
max_deliveries without an ack are moved to "<stream>:dlq" for inspection.
"""

import json
from dataclasses import dataclass
from typing import Any, cast

from redis.exceptions import ResponseError

from shared.cache import get_redis

MAX_DELIVERIES = 3


@dataclass(frozen=True, slots=True)
class Event:
    id: str
    type: str
    payload: dict[str, Any]


def dlq_stream(stream: str) -> str:
    return f"{stream}:dlq"


async def publish(stream: str, event_type: str, payload: dict[str, Any]) -> str:
    """Append an event; returns the stream entry id."""
    entry_id = await get_redis().xadd(stream, {"type": event_type, "payload": json.dumps(payload)})
    return str(entry_id)


def _parse(entry_id: str, fields: dict[str, str]) -> Event:
    return Event(
        id=entry_id,
        type=fields.get("type", ""),
        payload=json.loads(fields.get("payload", "{}")),
    )


class EventConsumer:
    def __init__(
        self,
        stream: str,
        *,
        group: str,
        name: str,
        max_deliveries: int = MAX_DELIVERIES,
    ) -> None:
        self.stream = stream
        self.group = group
        self.name = name
        self.max_deliveries = max_deliveries

    async def ensure_group(self) -> None:
        try:
            await get_redis().xgroup_create(self.stream, self.group, id="0", mkstream=True)
        except ResponseError as exc:
            if "BUSYGROUP" not in str(exc):
                raise

    async def read(self, count: int = 10) -> list[Event]:
        """Deliver new messages for this group (pending redeliveries excluded)."""
        # redis-py stubs type stream replies as loose unions; with
        # decode_responses=True every id/field is str.
        batches = cast(
            list[tuple[str, list[tuple[str, dict[str, str]]]]],
            await get_redis().xreadgroup(self.group, self.name, {self.stream: ">"}, count=count)
            or [],
        )
        return [
            _parse(entry_id, fields) for _stream, entries in batches for entry_id, fields in entries
        ]

    async def ack(self, event: Event) -> None:
        await get_redis().xack(self.stream, self.group, event.id)

    async def reap_poison(self, count: int = 100) -> list[Event]:
        """Move messages delivered >= max_deliveries times to the DLQ and ack them."""
        redis = get_redis()
        pending = await redis.xpending_range(self.stream, self.group, min="-", max="+", count=count)
        dead: list[Event] = []
        for entry in pending:
            if cast(int, entry["times_delivered"]) < self.max_deliveries:
                continue
            claimed = cast(
                list[tuple[str, dict[str, str]]],
                await redis.xclaim(
                    self.stream,
                    self.group,
                    self.name,
                    min_idle_time=0,
                    message_ids=[cast(str, entry["message_id"])],
                ),
            )
            for entry_id, fields in claimed:
                await redis.xadd(dlq_stream(self.stream), cast(dict[Any, Any], fields))
                await redis.xack(self.stream, self.group, entry_id)
                dead.append(_parse(entry_id, fields))
        return dead
