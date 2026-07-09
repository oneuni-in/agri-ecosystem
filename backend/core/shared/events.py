"""Minimal in-process async event bus.

Modules communicate through this bus (or public service interfaces),
never by importing each other.
"""

from collections import defaultdict
from collections.abc import Awaitable, Callable
from typing import Any

Handler = Callable[[dict[str, Any]], Awaitable[None]]


class EventBus:
    def __init__(self) -> None:
        self._handlers: dict[str, list[Handler]] = defaultdict(list)

    def subscribe(self, event: str, handler: Handler) -> None:
        self._handlers[event].append(handler)

    async def publish(self, event: str, payload: dict[str, Any]) -> None:
        for handler in self._handlers.get(event, []):
            await handler(payload)


bus = EventBus()
