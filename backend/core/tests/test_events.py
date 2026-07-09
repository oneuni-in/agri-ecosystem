"""Redis Streams event bus: publish/consume round trip through consumer
groups, ack semantics, and dead-lettering of poison messages."""

from collections.abc import AsyncIterator

import pytest
from redis.asyncio import Redis

from settings import get_settings
from shared.cache import reset_redis
from shared.events import EventConsumer, dlq_stream, publish
from tests.conftest import TEST_REDIS_DB


@pytest.fixture
async def bus_redis(redis_client: Redis, monkeypatch: pytest.MonkeyPatch) -> AsyncIterator[Redis]:
    """Point the bus's own client at the flushed test redis DB."""
    url = get_settings().redis_url.rsplit("/", 1)[0] + f"/{TEST_REDIS_DB}"
    monkeypatch.setenv("REDIS_URL", url)
    get_settings.cache_clear()
    reset_redis()
    yield redis_client


async def test_publish_consume_ack_round_trip(bus_redis: Redis) -> None:
    consumer = EventConsumer("leads", group="notify", name="worker-1")
    await consumer.ensure_group()

    await publish("leads", "lead.created", {"id": "abc"})
    events = await consumer.read()

    assert len(events) == 1
    assert events[0].type == "lead.created"
    assert events[0].payload == {"id": "abc"}

    await consumer.ack(events[0])
    pending = await bus_redis.xpending("leads", "notify")
    assert pending["pending"] == 0


async def test_each_group_gets_its_own_copy(bus_redis: Redis) -> None:
    notify = EventConsumer("leads", group="notify", name="w1")
    coins = EventConsumer("leads", group="coins", name="w1")
    await notify.ensure_group()
    await coins.ensure_group()

    await publish("leads", "lead.created", {"id": "abc"})

    assert len(await notify.read()) == 1
    assert len(await coins.read()) == 1


async def test_unacked_messages_stay_pending(bus_redis: Redis) -> None:
    consumer = EventConsumer("leads", group="notify", name="w1")
    await consumer.ensure_group()
    await publish("leads", "lead.created", {"id": "abc"})

    await consumer.read()  # no ack
    pending = await bus_redis.xpending("leads", "notify")
    assert pending["pending"] == 1

    # a fresh read only sees new messages, not the pending one
    assert await consumer.read() == []


async def test_poison_messages_move_to_dead_letter(bus_redis: Redis) -> None:
    consumer = EventConsumer("leads", group="notify", name="w1", max_deliveries=1)
    await consumer.ensure_group()
    await publish("leads", "lead.exploding", {"id": "boom"})

    await consumer.read()  # delivered once, never acked -> at the poison threshold
    dead = await consumer.reap_poison()

    assert len(dead) == 1
    assert dead[0].type == "lead.exploding"

    assert await bus_redis.xlen(dlq_stream("leads")) == 1
    pending = await bus_redis.xpending("leads", "notify")
    assert pending["pending"] == 0


async def test_ensure_group_is_idempotent(bus_redis: Redis) -> None:
    consumer = EventConsumer("leads", group="notify", name="w1")
    await consumer.ensure_group()
    await consumer.ensure_group()
