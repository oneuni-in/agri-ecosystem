"""Unified moderation queue registry (D21) - THE shared surface for admin
moderation. Cross-module by dependency inversion (register_principal_resolver
/ shared.lookups precedent): each owning module registers a typed source at
app wiring time; modules/ops fans the sources into one admin queue. A future
module (forum D96+, classifieds Stage E) EXTENDS the queue by registering a
source here - never by forking the queue.

Source contract (mirrors the D16/D18 decision choreography):
- approve/reject run the owning module's FOR UPDATE decision service, call
  audit() IN the caller's transaction, and capture every post-commit payload
  into ModDecision.events BEFORE returning (ORM attributes expire on commit).
- Sources NEVER commit; modules/ops owns the single commit -> best-effort
  publish sequence.
- Domain conflicts map to DecisionConflictError(code) -> 409; missing items
  to ItemNotFoundError -> 404.
"""

import uuid
from dataclasses import dataclass, field
from datetime import datetime
from typing import Protocol

from sqlalchemy.ext.asyncio import AsyncSession

from shared.pagination import Page


@dataclass(frozen=True, slots=True)
class PendingEvent:
    stream: str
    event_type: str
    payload: dict[str, object]


@dataclass(frozen=True, slots=True)
class ModItem:
    type_key: str
    id: uuid.UUID
    created_at: datetime
    title: str
    summary: str
    payload: dict[str, object] = field(default_factory=dict)


@dataclass(frozen=True, slots=True)
class ModDecision:
    item: ModItem
    events: tuple[PendingEvent, ...] = ()


class ItemNotFoundError(Exception):
    """No such pending item (or type mismatch). Routers 404."""


class DecisionConflictError(Exception):
    """Already decided / state conflict; .code is the API 409 detail."""

    def __init__(self, code: str) -> None:
        self.code = code
        super().__init__(code)


class ModerationSource(Protocol):
    type_key: str

    async def count_pending(self, session: AsyncSession) -> int: ...

    async def list_pending(
        self, session: AsyncSession, *, cursor: str | None, limit: int
    ) -> Page[ModItem]: ...

    async def approve(
        self,
        session: AsyncSession,
        *,
        item_id: uuid.UUID,
        actor_user_id: uuid.UUID,
        note: str | None,
        ip: str | None,
    ) -> ModDecision: ...

    async def reject(
        self,
        session: AsyncSession,
        *,
        item_id: uuid.UUID,
        actor_user_id: uuid.UUID,
        note: str | None,
        ip: str | None,
    ) -> ModDecision: ...


_sources: dict[str, ModerationSource] = {}


def register_moderation_source(source: ModerationSource) -> None:
    """Idempotent by type_key (create_app() may run repeatedly in tests)."""
    _sources[source.type_key] = source


def get_source(type_key: str) -> ModerationSource | None:
    return _sources.get(type_key)


def iter_sources() -> tuple[ModerationSource, ...]:
    return tuple(_sources[key] for key in sorted(_sources))


def reset_moderation_sources() -> None:
    _sources.clear()
