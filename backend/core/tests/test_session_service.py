"""D09.C web-session lifecycle: resolve, deny, revoke, revoke-everything."""

import hashlib
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
    legacy_fingerprints,
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


def test_fingerprint_survives_a_missing_platform_hint() -> None:
    """One browser is one device even when sec-ch-ua-platform does not arrive.

    Chrome omits the hint on some request paths (and the BFF only forwards
    what it received), so a platform-sensitive fingerprint split a single
    browser into two "devices" that drifted apart on every visit - and made
    this-device logout miss whichever half the current request did not match.
    """
    ua = "Mozilla/5.0 (Windows NT 10.0) Chrome/151.0.0.0"
    assert device_fingerprint(ua, '"Windows"') == device_fingerprint(ua, None)
    assert device_fingerprint(ua, '"Windows"') == device_fingerprint(ua, "")


def test_legacy_fingerprints_recognise_pre_fix_rows() -> None:
    """Rows minted before the fix hash UA|platform. Rotation must recognise
    them as the same device instead of reading them as token theft."""
    ua = "Mozilla/5.0 (Windows NT 10.0) Chrome/151.0.0.0"
    legacy_with_hint = hashlib.sha256(f'{ua}|"Windows"'.encode()).hexdigest()[:32]
    legacy_without = hashlib.sha256(f"{ua}|".encode()).hexdigest()[:32]

    assert legacy_with_hint in legacy_fingerprints(ua, '"Windows"')
    assert legacy_without in legacy_fingerprints(ua, '"Windows"')
    assert legacy_without in legacy_fingerprints(ua, None)
    # a different browser's legacy hash is never accepted
    assert legacy_with_hint not in legacy_fingerprints("Mozilla/5.0 (X11; Linux)", '"Windows"')


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


async def test_login_supersedes_this_devices_previous_session(db_session: AsyncSession) -> None:
    """One browser holds one agri_sid, so the previous session on the same
    device is unreachable the moment a new one is minted - keeping it live only
    grew /devices by a row per login. Fixation hardening is unaffected: the new
    sid is still freshly generated, never adopted from the old one."""
    user = await _user(db_session, "+919876510010")
    old = await create_web_session(db_session, user_id=user.id, fingerprint="fp-1", ip=None)
    elsewhere = await create_web_session(db_session, user_id=user.id, fingerprint="fp-2", ip=None)
    new = await create_web_session(db_session, user_id=user.id, fingerprint="fp-1", ip=None)

    assert new != old
    assert await resolve_web_session(db_session, old) is None  # superseded
    assert await resolve_web_session(db_session, new) is not None
    assert await resolve_web_session(db_session, elsewhere) is not None  # other device untouched


async def test_supersede_is_scoped_to_one_user(db_session: AsyncSession) -> None:
    """Two people on a shared computer share a fingerprint. One signing in
    must never sign the other out."""
    alice = await _user(db_session, "+919876510011")
    bob = await _user(db_session, "+919876510012")
    alice_sid = await create_web_session(db_session, user_id=alice.id, fingerprint="fp", ip=None)
    await create_web_session(db_session, user_id=bob.id, fingerprint="fp", ip=None)
    assert await resolve_web_session(db_session, alice_sid) is not None


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
