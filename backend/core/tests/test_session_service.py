"""D09.C web-session lifecycle: resolve, deny, revoke, revoke-everything."""

import uuid
from datetime import UTC, datetime, timedelta

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from modules.identity.models import SessionRefresh, SessionWeb, User
from modules.identity.oauth_service import get_client
from modules.identity.service import assign_role, create_user
from modules.identity.session_service import (
    create_web_session,
    device_fingerprint,
    resolve_web_session,
    revoke_everything,
    revoke_web_session,
)


def test_fingerprint_is_stable_and_opaque() -> None:
    fp = device_fingerprint("Mozilla/5.0 (Windows NT 10.0)", '"Windows"')
    assert fp == device_fingerprint("Mozilla/5.0 (Windows NT 10.0)", '"Windows"')
    assert fp != device_fingerprint("Mozilla/5.0 (X11; Linux)", '"Linux"')
    assert len(fp) == 32 and "Mozilla" not in fp
    assert device_fingerprint(None, None)  # never crashes on missing headers


async def _user(session: AsyncSession, phone: str) -> User:
    user = await create_user(session, phone)
    await assign_role(session, user.id, "user")
    return user


async def test_create_and_resolve(db_session: AsyncSession) -> None:
    user = await _user(db_session, "+919876510001")
    sid = await create_web_session(
        db_session, user_id=user.id, fingerprint="fp", ip="1.2.3.4", device_label=None
    )
    principal = await resolve_web_session(db_session, sid)
    assert principal is not None
    assert principal.agri_id == user.agri_id and principal.roles == ("user",)
    row = (await db_session.scalars(select(SessionWeb))).one()
    assert row.sid_hash != sid  # hashed at rest
    assert row.last_seen_at is not None


async def test_resolve_denies_garbage_expired_revoked_suspended(
    db_session: AsyncSession,
) -> None:
    user = await _user(db_session, "+919876510002")
    sid = await create_web_session(db_session, user_id=user.id, fingerprint="fp", ip=None)
    assert await resolve_web_session(db_session, "not-a-sid") is None

    row = (await db_session.scalars(select(SessionWeb))).one()
    row.expires_at = datetime.now(UTC) - timedelta(seconds=1)
    await db_session.flush()
    assert await resolve_web_session(db_session, sid) is None

    row.expires_at = datetime.now(UTC) + timedelta(days=1)
    row.revoked_at = datetime.now(UTC)
    await db_session.flush()
    assert await resolve_web_session(db_session, sid) is None

    row.revoked_at = None
    user.status = "suspended"  # instant deny mid-session
    await db_session.flush()
    assert await resolve_web_session(db_session, sid) is None


async def test_revoke_web_session_is_scoped_to_owner(db_session: AsyncSession) -> None:
    alice = await _user(db_session, "+919876510003")
    bob = await _user(db_session, "+919876510004")
    sid = await create_web_session(db_session, user_id=alice.id, fingerprint="fp", ip=None)
    principal = await resolve_web_session(db_session, sid)
    assert principal is not None
    assert principal.session_id is not None
    # bob cannot revoke alice's session
    assert not await revoke_web_session(db_session, session_id=principal.session_id, user_id=bob.id)
    assert await revoke_web_session(db_session, session_id=principal.session_id, user_id=alice.id)
    assert await resolve_web_session(db_session, sid) is None


async def test_revoke_everything_kills_sessions_and_refresh(db_session: AsyncSession) -> None:
    user = await _user(db_session, "+919876510005")
    sid_a = await create_web_session(db_session, user_id=user.id, fingerprint="a", ip=None)
    sid_b = await create_web_session(db_session, user_id=user.id, fingerprint="b", ip=None)
    client = await get_client(db_session, "web-agri")
    assert client is not None
    family = uuid.uuid4()
    db_session.add(
        SessionRefresh(
            user_id=user.id,
            token_hash="c" * 64,
            family_id=family,
            client_id=client.id,
            expires_at=datetime.now(UTC) + timedelta(days=30),
        )
    )
    await db_session.flush()

    web_count, refresh_count = await revoke_everything(db_session, user.id)
    assert (web_count, refresh_count) == (2, 1)
    assert await resolve_web_session(db_session, sid_a) is None
    assert await resolve_web_session(db_session, sid_b) is None
    refresh_row = (await db_session.scalars(select(SessionRefresh))).one()
    assert refresh_row.revoked_at is not None
