"""DPDP rights, by dependency inversion (ID-U1 W4).

The Digital Personal Data Protection Act, 2023 gives a person three things
this platform has to be able to do: hand over a copy of their data, delete
it, and show them who their contact details were revealed to. All three span
every module - and import-linter forbids modules importing each other, so
identity cannot read directory's or coins' tables to build any of them.

Same seam as shared.lookups and shared.security.register_principal_resolver:
the OWNING module registers a callable here, main.create_app() wires it, and
identity's DPDP router only ever calls what modules chose to expose. The code
that touches a module's tables is always that module's own.

Fail-closed differs by right, on purpose:

- EXPORT fails LOUD. A missing provider means an incomplete archive handed to
  someone who asked for all their data, and silently returning less than
  everything is the one outcome a data-access right cannot have. Providers
  that raise take the whole export down with them.
- HOLDS fail CLOSED-as-held. If a module cannot answer "does this person have
  an open dispute?", the erasure waits for a human rather than proceeding.
  Deleting during an unanswered question is irreversible; waiting is not.
- ERASERS fail LOUD for the same reason as export: a partial erasure that
  reports success is a lie about a right.
"""

import uuid
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from datetime import datetime
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

# Everything one module knows about a person, as JSON-serialisable data.
ExportProvider = Callable[[AsyncSession, uuid.UUID], Awaitable[dict[str, Any]]]
# A reason this person's data must NOT be erased yet, or None to allow it.
# The string is shown to staff in the admin queue, never to the user.
ErasureHoldProvider = Callable[[AsyncSession, uuid.UUID], Awaitable[str | None]]
# Actually erase this module's rows for the user; returns rows affected, for
# the audit trail. Runs inside the caller's transaction.
Eraser = Callable[[AsyncSession, uuid.UUID], Awaitable[int]]


@dataclass(frozen=True, slots=True)
class RevealRecord:
    """One "your contact details were shown to someone" event.

    Deliberately carries no contact VALUE - the owning table is append-only by
    grant and must never gain a phone column (D18). This records THAT a reveal
    happened, to whom, and when.
    """

    revealed_at: datetime
    business_name: str | None
    source: str


RevealLogProvider = Callable[[AsyncSession, uuid.UUID], Awaitable[list[RevealRecord]]]

_export_providers: dict[str, ExportProvider] = {}
_hold_providers: dict[str, ErasureHoldProvider] = {}
_erasers: dict[str, Eraser] = {}
_reveal_log_provider: RevealLogProvider | None = None


def register_export_provider(name: str, provider: ExportProvider) -> None:
    _export_providers[name] = provider


def register_erasure_hold_provider(name: str, provider: ErasureHoldProvider) -> None:
    _hold_providers[name] = provider


def register_eraser(name: str, eraser: Eraser) -> None:
    _erasers[name] = eraser


def register_reveal_log_provider(provider: RevealLogProvider) -> None:
    global _reveal_log_provider
    _reveal_log_provider = provider


def reset_dpdp_registry() -> None:
    global _reveal_log_provider
    _export_providers.clear()
    _hold_providers.clear()
    _erasers.clear()
    _reveal_log_provider = None


def registered_export_sections() -> tuple[str, ...]:
    """The sections an export WILL contain. The completeness test pins this,
    so a module that gains user data and forgets to register shows up as a
    failing assertion rather than as a quietly short archive."""
    return tuple(sorted(_export_providers))


async def collect_export(session: AsyncSession, user_id: uuid.UUID) -> dict[str, Any]:
    """Every module's answer, keyed by module name.

    No exception handling on purpose - see the module docstring. An export
    that silently omits a section is worse than an export that fails.
    """
    sections: dict[str, Any] = {}
    for name in sorted(_export_providers):
        sections[name] = await _export_providers[name](session, user_id)
    return sections


async def erasure_holds(session: AsyncSession, user_id: uuid.UUID) -> list[str]:
    """Reasons this erasure must wait, one per module that has one.

    A provider that RAISES is itself a hold: an unanswerable question about
    an irreversible action resolves to "ask a human", never to "go ahead".

    An EMPTY REGISTRY is also a hold, and this is not paranoia - it is a bug
    this code has already had. The erasure job is a standalone script; it
    imported execute_due directly and never ran the wiring, so no provider was
    registered, "nobody objected" and "nobody was asked" looked identical,
    and a real account that owned five live businesses was erased on the first
    run. Fail closed here so the same class of mistake stops the deletion
    instead of completing it: a queue full of unexpected holds is a loud,
    recoverable failure; a wrongly erased account is neither.
    """
    if not _hold_providers:
        return ["registry:unwired"]
    holds: list[str] = []
    for name in sorted(_hold_providers):
        try:
            reason = await _hold_providers[name](session, user_id)
        except Exception:
            holds.append(f"{name}:unavailable")
            continue
        if reason:
            holds.append(f"{name}:{reason}")
    return holds


async def run_erasers(session: AsyncSession, user_id: uuid.UUID) -> dict[str, int]:
    return {name: await _erasers[name](session, user_id) for name in sorted(_erasers)}


async def reveal_log(session: AsyncSession, user_id: uuid.UUID) -> list[RevealRecord]:
    """Empty when unregistered: an empty reveal log and "no reveals happened"
    are the same statement to the reader, and this is a READ - nothing
    irreversible follows from it."""
    if _reveal_log_provider is None:
        return []
    return await _reveal_log_provider(session, user_id)
