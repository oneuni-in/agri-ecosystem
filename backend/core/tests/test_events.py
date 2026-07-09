"""In-process event bus delivers payloads to subscribers."""

from typing import Any

from shared.events import EventBus


async def test_publish_reaches_all_subscribers() -> None:
    bus = EventBus()
    received: list[dict[str, Any]] = []

    async def handler(payload: dict[str, Any]) -> None:
        received.append(payload)

    bus.subscribe("lead.created", handler)
    bus.subscribe("lead.created", handler)
    await bus.publish("lead.created", {"id": "abc"})
    assert received == [{"id": "abc"}, {"id": "abc"}]


async def test_publish_without_subscribers_is_a_noop() -> None:
    await EventBus().publish("nobody.listening", {})


async def test_events_are_isolated_by_name() -> None:
    bus = EventBus()
    received: list[dict[str, Any]] = []

    async def handler(payload: dict[str, Any]) -> None:
        received.append(payload)

    bus.subscribe("a", handler)
    await bus.publish("b", {"x": 1})
    assert received == []
