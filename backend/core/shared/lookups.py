"""Cross-module lookups by dependency inversion (D20).

import-linter's independence contract forbids modules importing each other,
so billing cannot call directory/identity code directly. Instead - exactly
like shared.security.register_principal_resolver (D09) - the OWNING module
registers a resolver here and main.create_app() wires it. The code that runs
is always the owning module's own; nothing here reads another module's
tables. Fail closed: unregistered resolvers answer None/empty, never raise.
"""

import uuid
from collections.abc import Awaitable, Callable
from dataclasses import dataclass

from sqlalchemy.ext.asyncio import AsyncSession


@dataclass(frozen=True, slots=True)
class BusinessRef:
    id: uuid.UUID
    owner_user_id: uuid.UUID | None
    name: str


@dataclass(frozen=True, slots=True)
class NotifyContact:
    email: str | None
    locale: str | None


BusinessResolver = Callable[[AsyncSession, uuid.UUID], Awaitable[BusinessRef | None]]
OwnedBusinessesResolver = Callable[[AsyncSession, uuid.UUID], Awaitable[list[BusinessRef]]]
ContactResolver = Callable[[AsyncSession, uuid.UUID], Awaitable[NotifyContact | None]]
# M1.5.E: directory answers "may this business be served/shown at all?"
# (status == 'active'); ads consumes it at serve time - the M3 seam.
ServableResolver = Callable[[AsyncSession, uuid.UUID], Awaitable[bool]]
# M1.5.B: ads pauses an advertiser's active campaigns on disable, in the
# caller's transaction; returns the paused campaign ids for the audit row.
CampaignPauser = Callable[[AsyncSession, uuid.UUID], Awaitable[list[str]]]

_business_resolver: BusinessResolver | None = None
_owned_businesses_resolver: OwnedBusinessesResolver | None = None
_contact_resolver: ContactResolver | None = None
_servable_resolver: ServableResolver | None = None
_campaign_pauser: CampaignPauser | None = None


def register_business_resolver(resolver: BusinessResolver) -> None:
    global _business_resolver
    _business_resolver = resolver


def register_owned_businesses_resolver(resolver: OwnedBusinessesResolver) -> None:
    global _owned_businesses_resolver
    _owned_businesses_resolver = resolver


def register_contact_resolver(resolver: ContactResolver) -> None:
    global _contact_resolver
    _contact_resolver = resolver


def register_servable_resolver(resolver: ServableResolver) -> None:
    global _servable_resolver
    _servable_resolver = resolver


def register_campaign_pauser(pauser: CampaignPauser) -> None:
    global _campaign_pauser
    _campaign_pauser = pauser


def reset_lookup_resolvers() -> None:
    global _business_resolver, _owned_businesses_resolver, _contact_resolver
    global _servable_resolver, _campaign_pauser
    _business_resolver = None
    _owned_businesses_resolver = None
    _contact_resolver = None
    _servable_resolver = None
    _campaign_pauser = None


async def resolve_business(session: AsyncSession, business_id: uuid.UUID) -> BusinessRef | None:
    if _business_resolver is None:
        return None
    return await _business_resolver(session, business_id)


async def resolve_owned_businesses(
    session: AsyncSession, owner_user_id: uuid.UUID
) -> list[BusinessRef]:
    if _owned_businesses_resolver is None:
        return []
    return await _owned_businesses_resolver(session, owner_user_id)


async def resolve_contact(session: AsyncSession, user_id: uuid.UUID) -> NotifyContact | None:
    if _contact_resolver is None:
        return None
    return await _contact_resolver(session, user_id)


async def is_servable(session: AsyncSession, business_id: uuid.UUID) -> bool:
    """Serve-time enforcement check (M1.5.E). FAIL CLOSED: no resolver or an
    unknown business means False - a suspended vendor's ads must never serve
    because wiring was missing."""
    if _servable_resolver is None:
        return False
    return await _servable_resolver(session, business_id)


async def pause_campaigns_for_business(session: AsyncSession, business_id: uuid.UUID) -> list[str]:
    if _campaign_pauser is None:
        return []
    return await _campaign_pauser(session, business_id)
