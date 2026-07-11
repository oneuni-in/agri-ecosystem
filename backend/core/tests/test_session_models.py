"""D09 model + limits pins: sessions_web exists, refresh rows carry family data."""

import uuid
from datetime import UTC, datetime, timedelta

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from modules.identity.models import SessionRefresh, SessionWeb
from modules.identity.oauth_service import get_client
from modules.identity.service import create_user
from modules.identity.session_limits import (
    REFRESH_TOKEN_TTL_SECONDS,
    SESSION_COOKIE_NAME,
    WEB_SESSION_TTL_SECONDS,
)


def test_limits_pinned() -> None:
    assert WEB_SESSION_TTL_SECONDS == 30 * 86400
    assert REFRESH_TOKEN_TTL_SECONDS == 30 * 86400
    assert SESSION_COOKIE_NAME == "agri_sid"


async def test_sessions_web_roundtrip(db_session: AsyncSession) -> None:
    user = await create_user(db_session, "+919876500001")
    row = SessionWeb(
        user_id=user.id,
        sid_hash="a" * 64,
        device_fingerprint="f" * 32,
        device_label="Chrome on Windows",
        ip="127.0.0.1",
        expires_at=datetime.now(UTC) + timedelta(days=30),
    )
    db_session.add(row)
    await db_session.flush()
    fetched = await db_session.scalar(select(SessionWeb).where(SessionWeb.user_id == user.id))
    assert fetched is not None
    assert fetched.revoked_at is None and fetched.last_seen_at is None


async def test_sessions_refresh_family_columns(db_session: AsyncSession) -> None:
    user = await create_user(db_session, "+919876500002")
    client = await get_client(db_session, "web-agri")
    assert client is not None
    family = uuid.uuid4()
    row = SessionRefresh(
        user_id=user.id,
        token_hash="b" * 64,
        family_id=family,
        client_id=client.id,
        device_fingerprint="f" * 32,
        expires_at=datetime.now(UTC) + timedelta(days=30),
    )
    db_session.add(row)
    await db_session.flush()
    fetched = await db_session.scalar(
        select(SessionRefresh).where(SessionRefresh.family_id == family)
    )
    assert fetched is not None and fetched.last_used_at is None
