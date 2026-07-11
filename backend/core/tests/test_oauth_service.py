"""D08.B code lifecycle on the real schema: hash-only storage, atomic
single-use consumption, 60s TTL, client binding, and token-subject loading."""

from datetime import UTC, datetime, timedelta

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from modules.identity.models import OAuthClient, OAuthCode, Profile
from modules.identity.oauth_limits import AUTH_CODE_TTL_SECONDS
from modules.identity.oauth_service import (
    consume_authorization_code,
    create_authorization_code,
    get_client,
    load_token_subject,
)
from modules.identity.service import assign_role, create_user

PHONE = "+919876543210"
REDIRECT = "http://localhost:3002/api/auth/callback"
CHALLENGE = "E9Melhoa2OwvFrEMTJguCHaoeK1t8URWbuGJSstw-cM"


async def _seeded_client(session: AsyncSession, client_id: str = "web-agri") -> OAuthClient:
    client = await get_client(session, client_id)
    assert client is not None, "migration 0009 must seed the first-party clients"
    return client


async def test_seed_contains_all_four_first_party_clients(db_session: AsyncSession) -> None:
    rows = (await db_session.scalars(select(OAuthClient))).all()
    assert {c.client_id for c in rows} == {"web-agri", "web-milk", "web-organic", "web-admin"}
    for row in rows:
        # dev seed: exactly one localhost callback each (APP_ENV != prod here)
        assert len(row.redirect_uris) == 1
        assert row.redirect_uris[0].startswith("http://localhost:3")
        assert row.redirect_uris[0].endswith("/api/auth/callback")


async def test_code_is_stored_hash_only_with_ttl(db_session: AsyncSession) -> None:
    user = await create_user(db_session, PHONE)
    client = await _seeded_client(db_session)
    code = await create_authorization_code(
        db_session,
        user_id=user.id,
        client=client,
        redirect_uri=REDIRECT,
        code_challenge=CHALLENGE,
    )
    row = (await db_session.scalars(select(OAuthCode))).one()
    assert code not in (row.code_hash, row.code_challenge)  # plaintext never lands
    assert row.code_challenge_method == "S256"
    assert row.consumed_at is None
    lifetime = row.expires_at - datetime.now(UTC)
    assert timedelta(seconds=0) < lifetime <= timedelta(seconds=AUTH_CODE_TTL_SECONDS)


async def test_consume_is_single_use(db_session: AsyncSession) -> None:
    user = await create_user(db_session, PHONE)
    client = await _seeded_client(db_session)
    code = await create_authorization_code(
        db_session,
        user_id=user.id,
        client=client,
        redirect_uri=REDIRECT,
        code_challenge=CHALLENGE,
    )
    first = await consume_authorization_code(db_session, code=code, client=client)
    assert first is not None
    assert first.consumed_at is not None
    assert await consume_authorization_code(db_session, code=code, client=client) is None


async def test_expired_code_does_not_consume(db_session: AsyncSession) -> None:
    user = await create_user(db_session, PHONE)
    client = await _seeded_client(db_session)
    code = await create_authorization_code(
        db_session,
        user_id=user.id,
        client=client,
        redirect_uri=REDIRECT,
        code_challenge=CHALLENGE,
    )
    row = (await db_session.scalars(select(OAuthCode))).one()
    row.expires_at = datetime.now(UTC) - timedelta(seconds=1)
    await db_session.flush()
    assert await consume_authorization_code(db_session, code=code, client=client) is None


async def test_foreign_client_cannot_consume(db_session: AsyncSession) -> None:
    user = await create_user(db_session, PHONE)
    agri = await _seeded_client(db_session, "web-agri")
    milk = await _seeded_client(db_session, "web-milk")
    code = await create_authorization_code(
        db_session,
        user_id=user.id,
        client=agri,
        redirect_uri=REDIRECT,
        code_challenge=CHALLENGE,
    )
    assert await consume_authorization_code(db_session, code=code, client=milk) is None
    # the failed foreign attempt must not have burned the rightful client's code
    assert await consume_authorization_code(db_session, code=code, client=agri) is not None


async def test_never_issued_code_does_not_consume(db_session: AsyncSession) -> None:
    client = await _seeded_client(db_session)
    assert await consume_authorization_code(db_session, code="forged", client=client) is None


async def test_token_subject_carries_agri_id_and_sorted_roles(db_session: AsyncSession) -> None:
    user = await create_user(db_session, PHONE)
    await assign_role(db_session, user.id, "user")
    await assign_role(db_session, user.id, "farmer")
    subject = await load_token_subject(db_session, user.id)
    assert subject is not None
    assert subject.user_id == user.id
    assert subject.agri_id == user.agri_id
    assert subject.roles == ("farmer", "user")


async def test_suspended_user_yields_no_token_subject(db_session: AsyncSession) -> None:
    user = await create_user(db_session, PHONE)
    user.status = "suspended"
    await db_session.flush()
    assert await load_token_subject(db_session, user.id) is None


async def test_load_token_subject_carries_profile_name(db_session: AsyncSession) -> None:
    user = await create_user(db_session, "+919812300001")
    await assign_role(db_session, user.id, "user")
    db_session.add(Profile(user_id=user.id, name="Asha"))
    await db_session.flush()
    subject = await load_token_subject(db_session, user.id)
    assert subject is not None
    assert subject.name == "Asha"


async def test_load_token_subject_name_none_without_profile(db_session: AsyncSession) -> None:
    user = await create_user(db_session, "+919812300002")
    await assign_role(db_session, user.id, "user")
    subject = await load_token_subject(db_session, user.id)
    assert subject is not None
    assert subject.name is None
