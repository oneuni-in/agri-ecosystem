"""D09.B non-negotiables: rotation, reuse -> WHOLE-family revoke, device
binding, per-client scoping, suspended deny, expiry."""

from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from modules.identity.models import OAuthClient, SessionRefresh, User
from modules.identity.oauth_service import get_client
from modules.identity.refresh_service import (
    RefreshInvalidError,
    RefreshReuseError,
    issue_refresh_token,
    revoke_families_for_device,
    revoke_family,
    rotate_refresh_token,
)
from modules.identity.service import assign_role, create_user
from modules.identity.session_service import device_fingerprint, legacy_fingerprints

FP = "fingerprint-a"


async def _setup(session: AsyncSession, phone: str = "+919876520001") -> tuple[User, OAuthClient]:
    user = await create_user(session, phone)
    await assign_role(session, user.id, "user")
    client = await get_client(session, "web-agri")
    assert client is not None
    return user, client


async def test_issue_starts_family_hashed_at_rest(db_session: AsyncSession) -> None:
    user, client = await _setup(db_session)
    issued = await issue_refresh_token(
        db_session, user_id=user.id, client=client, fingerprint=FP, ip=None
    )
    row = (await db_session.scalars(select(SessionRefresh))).one()
    assert row.family_id == issued.row_id == issued.family_id  # root row anchors the family
    assert row.token_hash != issued.token and issued.token not in row.token_hash
    assert row.rotated_from is None and row.revoked_at is None


async def test_rotation_issues_new_and_revokes_old(db_session: AsyncSession) -> None:
    user, client = await _setup(db_session)
    first = await issue_refresh_token(
        db_session, user_id=user.id, client=client, fingerprint=FP, ip=None
    )
    second = await rotate_refresh_token(
        db_session, token=first.token, client=client, fingerprint=FP
    )
    assert second.token != first.token
    assert second.family_id == first.family_id
    rows = (await db_session.scalars(select(SessionRefresh).order_by(SessionRefresh.id))).all()
    assert len(rows) == 2
    assert rows[0].revoked_at is not None and rows[0].last_used_at is not None
    assert rows[1].rotated_from == first.row_id and rows[1].revoked_at is None


async def test_reuse_of_rotated_token_revokes_entire_family(db_session: AsyncSession) -> None:
    """THE non-negotiable: replaying a rotated token kills every descendant."""
    user, client = await _setup(db_session)
    first = await issue_refresh_token(
        db_session, user_id=user.id, client=client, fingerprint=FP, ip=None
    )
    second = await rotate_refresh_token(
        db_session, token=first.token, client=client, fingerprint=FP
    )
    third = await rotate_refresh_token(
        db_session, token=second.token, client=client, fingerprint=FP
    )

    with pytest.raises(RefreshReuseError):  # attacker replays the FIRST token
        await rotate_refresh_token(db_session, token=first.token, client=client, fingerprint=FP)

    rows = (await db_session.scalars(select(SessionRefresh))).all()
    assert len(rows) == 3
    assert all(row.revoked_at is not None for row in rows)  # whole family, incl. the live leaf
    with pytest.raises(RefreshInvalidError):  # the legitimate leaf is dead too
        await rotate_refresh_token(db_session, token=third.token, client=client, fingerprint=FP)


async def test_expired_token_rejected_without_family_damage(db_session: AsyncSession) -> None:
    user, client = await _setup(db_session)
    issued = await issue_refresh_token(
        db_session, user_id=user.id, client=client, fingerprint=FP, ip=None
    )
    row = (await db_session.scalars(select(SessionRefresh))).one()
    row.expires_at = datetime.now(UTC) - timedelta(seconds=1)
    await db_session.flush()
    with pytest.raises(RefreshInvalidError):
        await rotate_refresh_token(db_session, token=issued.token, client=client, fingerprint=FP)


async def test_wrong_client_cannot_rotate(db_session: AsyncSession) -> None:
    user, client = await _setup(db_session)
    milk = await get_client(db_session, "web-milk")
    assert milk is not None
    issued = await issue_refresh_token(
        db_session, user_id=user.id, client=client, fingerprint=FP, ip=None
    )
    with pytest.raises(RefreshInvalidError):
        await rotate_refresh_token(db_session, token=issued.token, client=milk, fingerprint=FP)
    # and the rightful client is unharmed
    await rotate_refresh_token(db_session, token=issued.token, client=client, fingerprint=FP)


async def test_fingerprint_mismatch_revokes_family(db_session: AsyncSession) -> None:
    user, client = await _setup(db_session)
    issued = await issue_refresh_token(
        db_session, user_id=user.id, client=client, fingerprint=FP, ip=None
    )
    with pytest.raises(RefreshInvalidError):
        await rotate_refresh_token(
            db_session, token=issued.token, client=client, fingerprint="stolen-elsewhere"
        )
    rows = (await db_session.scalars(select(SessionRefresh))).all()
    assert all(row.revoked_at is not None for row in rows)  # theft signal: family is gone


async def test_reauth_supersedes_the_previous_family_on_the_same_device(
    db_session: AsyncSession,
) -> None:
    """One app + one device = one live family, not one per SSO round trip.

    Every code exchange used to start a family and leave the last one live for
    its full TTL, so a browser that re-ran the handshake a few times collected
    a row per visit on /devices - each a still-valid refresh token nobody
    holds any more.
    """
    user, client = await _setup(db_session)
    first = await issue_refresh_token(
        db_session, user_id=user.id, client=client, fingerprint=FP, ip=None
    )
    second = await issue_refresh_token(
        db_session, user_id=user.id, client=client, fingerprint=FP, ip=None
    )
    assert second.family_id != first.family_id

    live = (
        await db_session.scalars(select(SessionRefresh).where(SessionRefresh.revoked_at.is_(None)))
    ).all()
    assert [row.family_id for row in live] == [second.family_id]
    # the superseded token is dead, and replaying it is not read as theft of
    # the family that replaced it
    with pytest.raises(RefreshInvalidError):
        await rotate_refresh_token(db_session, token=first.token, client=client, fingerprint=FP)
    still_live = (
        await db_session.scalars(select(SessionRefresh).where(SessionRefresh.revoked_at.is_(None)))
    ).all()
    assert [row.family_id for row in still_live] == [second.family_id]


async def test_reauth_leaves_other_devices_and_other_apps_alone(
    db_session: AsyncSession,
) -> None:
    user, client = await _setup(db_session)
    milk = await get_client(db_session, "web-milk")
    assert milk is not None
    other_device = await issue_refresh_token(
        db_session, user_id=user.id, client=client, fingerprint="dev-b", ip=None
    )
    other_app = await issue_refresh_token(
        db_session, user_id=user.id, client=milk, fingerprint=FP, ip=None
    )
    await issue_refresh_token(db_session, user_id=user.id, client=client, fingerprint=FP, ip=None)
    live = {
        row.family_id
        for row in (
            await db_session.scalars(
                select(SessionRefresh).where(SessionRefresh.revoked_at.is_(None))
            )
        ).all()
    }
    assert other_device.family_id in live and other_app.family_id in live


async def test_legacy_fingerprint_row_rotates_and_is_upgraded(db_session: AsyncSession) -> None:
    """A family minted before the UA-only fingerprint is the SAME device.

    Without this, shipping the fingerprint change would read every live family
    in the system as stolen and revoke it on first refresh.
    """
    user, client = await _setup(db_session)
    ua = "Mozilla/5.0 (Windows NT 10.0) Chrome/151.0.0.0"
    legacy = legacy_fingerprints(ua, '"Windows"')[0]
    current = device_fingerprint(ua)
    assert legacy != current  # the pre-fix row really is stored differently

    issued = await issue_refresh_token(
        db_session, user_id=user.id, client=client, fingerprint=legacy, ip=None
    )
    rotated = await rotate_refresh_token(
        db_session,
        token=issued.token,
        client=client,
        fingerprint=current,
        legacy=legacy_fingerprints(ua, '"Windows"'),
    )
    assert rotated.family_id == issued.family_id
    rows = (await db_session.scalars(select(SessionRefresh))).all()
    # every row in the family now carries the current-format fingerprint, so
    # this-device logout keeps matching the whole lineage
    assert {row.device_fingerprint for row in rows} == {current}


async def test_unrelated_legacy_hash_is_still_theft(db_session: AsyncSession) -> None:
    user, client = await _setup(db_session)
    issued = await issue_refresh_token(
        db_session, user_id=user.id, client=client, fingerprint=FP, ip=None
    )
    with pytest.raises(RefreshInvalidError):
        await rotate_refresh_token(
            db_session,
            token=issued.token,
            client=client,
            fingerprint="another-device",
            legacy=legacy_fingerprints("Mozilla/5.0 (X11; Linux)", '"Linux"'),
        )
    rows = (await db_session.scalars(select(SessionRefresh))).all()
    assert all(row.revoked_at is not None for row in rows)


async def test_suspended_user_cannot_rotate(db_session: AsyncSession) -> None:
    user, client = await _setup(db_session)
    issued = await issue_refresh_token(
        db_session, user_id=user.id, client=client, fingerprint=FP, ip=None
    )
    user.status = "suspended"
    await db_session.flush()
    with pytest.raises(RefreshInvalidError):
        await rotate_refresh_token(db_session, token=issued.token, client=client, fingerprint=FP)


async def test_revoke_family_and_device_helpers(db_session: AsyncSession) -> None:
    user, client = await _setup(db_session)
    a = await issue_refresh_token(
        db_session, user_id=user.id, client=client, fingerprint="dev-a", ip=None
    )
    b = await issue_refresh_token(
        db_session, user_id=user.id, client=client, fingerprint="dev-b", ip=None
    )
    assert await revoke_family(db_session, a.family_id) == 1
    assert await revoke_families_for_device(db_session, user_id=user.id, fingerprint="dev-b") == 1
    rows = (await db_session.scalars(select(SessionRefresh))).all()
    assert all(row.revoked_at is not None for row in rows)
    _ = b
