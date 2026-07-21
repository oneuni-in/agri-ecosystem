"""shared/lookups: dependency-inverted cross-module reads (the
register_principal_resolver precedent). Unregistered resolvers fail closed."""

import uuid

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from modules.directory.lookups import business_ref, owned_business_refs
from modules.directory.models import Business
from modules.identity.lookups import notify_contact
from modules.identity.models import Email, Profile, User
from shared.lookups import (
    register_business_resolver,
    register_contact_resolver,
    register_owned_businesses_resolver,
    resolve_business,
    resolve_contact,
    resolve_owned_businesses,
)

pytestmark = pytest.mark.asyncio


async def test_unregistered_resolvers_fail_closed(db_session: AsyncSession) -> None:
    assert await resolve_business(db_session, uuid.uuid4()) is None
    assert await resolve_owned_businesses(db_session, uuid.uuid4()) == []
    assert await resolve_contact(db_session, uuid.uuid4()) is None


async def test_directory_adapter_resolves_owned_business(db_session: AsyncSession) -> None:
    owner = uuid.uuid4()
    business = Business(
        name="Kovai Mills",
        slug="kovai-mills",
        owner_user_id=owner,
        type="farm",
        primary_pincode="641001",
    )
    db_session.add(business)
    await db_session.flush()
    register_business_resolver(business_ref)
    register_owned_businesses_resolver(owned_business_refs)

    ref = await resolve_business(db_session, business.id)
    assert ref is not None and ref.owner_user_id == owner and ref.name == "Kovai Mills"
    owned = await resolve_owned_businesses(db_session, owner)
    assert [entry.id for entry in owned] == [business.id]
    assert await resolve_business(db_session, uuid.uuid4()) is None


async def test_identity_adapter_returns_verified_email_and_locale(
    db_session: AsyncSession,
) -> None:
    from datetime import UTC, datetime

    user = User(phone="+916374344001", agri_id="AG-9000001")
    db_session.add(user)
    await db_session.flush()
    db_session.add(Profile(user_id=user.id, language="ta"))
    db_session.add(Email(user_id=user.id, email="owner@example.com", verified_at=datetime.now(UTC)))
    db_session.add(Email(user_id=user.id, email="unverified@example.com"))
    await db_session.flush()
    register_contact_resolver(notify_contact)

    contact = await resolve_contact(db_session, user.id)
    assert contact is not None
    assert contact.email == "owner@example.com"
    assert contact.locale == "ta"
