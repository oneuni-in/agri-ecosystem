# D09 — Sessions, Refresh Rotation, Web-ID App Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** id.agri.in browser sessions (OTP login → httpOnly cookie), 30-day rotating device-bound refresh tokens with family revocation, logout/logout-everywhere, and the web-id auth UI (phone → OTP → handle → language → devices manager), proven by a Playwright E2E suite.

**Architecture:** Backend work all lands in `backend/core/modules/identity` (new `session_limits.py`, `session_service.py`, `refresh_service.py`, `session_auth.py`, `session_router.py`; extensions to `oauth_server.py`/`oauth_router.py`), riding the existing `sessions_refresh` table (migration 0007) plus one new migration (0010: `sessions_web` table + refresh-family columns). The `require_auth` stub in `shared/security.py` becomes a pluggable resolver the identity module registers at app creation. web-id (Next 15, port 3003) proxies `/api/id/*` and `/authorize` to the FastAPI backend via rewrites so the session cookie is first-party in dev and prod; screens are composed from `packages/ui` (new `OtpInput` component, CategoryTile button mode, `ui.auth.*` messages in EN/TA/HI).

**Tech Stack:** FastAPI + SQLAlchemy async + authlib 1.7 + joserfc (backend, host Python 3.12, CI 3.13); Next 15 + next-intl + Tailwind 3 tokens (frontend, Node 24 / pnpm 11); `@playwright/test` (new, pin 1.61.1 to match existing `playwright` dep); pytest with real Postgres (local port **55432**, CI 5432) and real Redis (test DB 9).

## Global Constraints

- Branch: `feat/d09-sessions-webid` (already checked out). Conventional commits. PR targets `dev`. NEVER commit to dev/main.
- Refresh tokens: 30-day TTL, ROTATING; reuse of a rotated token revokes the whole family + audit log line (a test proves it). Hashed at rest (SHA-256, same as oauth codes); plaintext exists only in the creation/rotation response. Device-bound: fingerprint = `sha256(f"{user_agent}|{sec_ch_ua_platform}")` (privacy-light, spec assumption adopted).
- Cookies: `agri_sid`, httpOnly + Secure + SameSite=Lax, host-only (NO `Domain` attribute), path=/. No tokens in localStorage anywhere, ever. Session fixation: every login mints a brand-new sid.
- Logout-everywhere kills every web session and every refresh family in ONE request cycle (two bulk UPDATEs in one transaction; a test proves it).
- Suspended user = instant deny at every path: login, session resolve, refresh rotation, /authorize code mint (all go through `load_token_subject`-style `status == "active"` checks).
- Identity module rules (backend/core/modules/identity/CLAUDE.md): never log request bodies/query strings; every response model exposing identity subclasses `IdentityPublicSchema` (no `id`/`user_id`/`phone` field names, no `uuid.UUID` annotations — expose stringified session-row ids as `device_id: str`); `public=True` routes must be added to `backend/core/public_routes.txt` in the same PR; all lists cursor-paginated via `shared/pagination.paginate` (OFFSET is banned by a lint gate).
- Service functions take the caller's `AsyncSession`, `flush()` but never `commit()`; routers own transactions; get_session commits after the endpoint returns, so a 4xx raised as HTTPException skips commit — commit explicitly BEFORE raising when a failure must persist (D07's commit-before-400 lesson).
- Every SecureRouter endpoint needs a return-type annotation or response_model (enforced at registration).
- Migration file needs the `# -- THREAT/NOTES:` block (downgrade data loss / locks / rollout). Use `shared/migrations.pk_column()/timestamp_columns()`.
- UI: tokens only — `node scripts/check-hex.mjs` fails CI on any hex/rgb literal in apps/ or packages/ui. Touch targets ≥44px. All copy in EN/TA/HI via `packages/ui/src/i18n/messages/{en,ta,hi}.json` under a new `ui.auth.*` subtree. New ui components exported from `packages/ui/src/index.ts` barrel.
- Lighthouse gate applies to web-id `/` (perf≥90 / a11y≥95 / seo≥95, mobile). Auth pages get `buildMetadata` + noindex.
- Backend verification commands (Windows local): `docker compose -f docker-compose.dev.yml up -d postgres redis`, then from `backend/core`: `.venv\Scripts\pytest.exe -q`, `.venv\Scripts\ruff.exe format --check .`, `.venv\Scripts\ruff.exe check .`, `.venv\Scripts\mypy.exe .`, `.venv\Scripts\python.exe scripts\dump_public_routes.py --check`. NOTE: `scripts/migrate_check.py` WIPES dev data (D05 memory) — only CI runs it.
- Frontend verification: `pnpm exec turbo run lint typecheck test build`, `pnpm run check:hex`.
- Deferred by spec (DO NOT build): BFF/app-side cookies (D10), profile editing beyond handle+language (D11), hash-chained audit storage (D12 — use structured `logger.warning/info` with `extra_fields` for session lifecycle events).

## File Structure

**Backend (backend/core):**
- Create: `alembic/versions/0010_sessions_v1.py` — `identity.sessions_web` table; `sessions_refresh` gains `family_id`, `client_id`, `device_fingerprint`, `last_used_at`; indexes.
- Modify: `modules/identity/models.py` — `SessionWeb` model + new `SessionRefresh` columns.
- Create: `modules/identity/session_limits.py` — TTLs + cookie name (pinned by tests).
- Create: `modules/identity/session_service.py` — fingerprint, web-session create/resolve/revoke/revoke-all, device listing/labeling.
- Create: `modules/identity/refresh_service.py` — issue/rotate/family-revoke (the line-by-line-review target).
- Modify: `modules/identity/oauth_server.py` — allow `refresh_token` grant, `AgriRefreshTokenGrant`, ctx fields, token-generator closure emitting `refresh_token`.
- Modify: `modules/identity/oauth_router.py` — /token refresh branch + code-grant refresh mint + failure cleanup; /authorize session check + code mint + login-resume redirect.
- Create: `modules/identity/session_auth.py` — principal resolver plugged into `shared/security.require_auth`.
- Create: `modules/identity/session_router.py` — /auth/login, /auth/logout, /auth/logout-everywhere, /auth/me, /auth/devices*, /auth/handle*, /auth/language.
- Modify: `shared/security.py` — `require_auth` becomes resolver-driven.
- Modify: `main.py` — register resolver, mount session_router + flag-gated OTP peek router.
- Modify: `settings.py` — `otp_test_peek: bool = False`.
- Modify: `modules/identity/router.py` — `otp_test_peek_router()` (flag-gated, mock-driver outbox peek for E2E).
- Modify: `public_routes.txt` — add `/auth/login`.
- Modify: `tests/conftest.py` — reset principal resolver in `_reset_state`.
- Tests: `tests/test_session_service.py`, `tests/test_refresh_rotation.py`, `tests/test_oauth_refresh_grant.py`, `tests/test_session_router.py`, `tests/test_devices_router.py`, `tests/test_authorize_session.py`; modify `tests/test_oauth_flow.py`.

**Frontend:**
- Create: `packages/ui/src/components/otp-input.tsx` (+ pure helper `packages/ui/src/lib/otp.ts` with vitest test).
- Modify: `packages/ui/src/components/category-tile.tsx` — optional button mode + selected state.
- Modify: `packages/ui/src/i18n/messages/{en,ta,hi}.json`, `packages/ui/src/index.ts`.
- Modify: `apps/web-id/next.config.ts` (rewrites), `apps/web-id/i18n/request.ts` (NEXT_LOCALE cookie), `apps/web-id/app/page.tsx`, `apps/web-id/app/layout.tsx` (ToastProvider).
- Create: `apps/web-id/lib/api.ts`, `apps/web-id/app/login/page.tsx` + `login-flow.tsx` (client), `apps/web-id/app/devices/page.tsx` + `devices-manager.tsx` (client).

**E2E / CI:**
- Create: `e2e/playwright.config.ts`, `e2e/auth.spec.ts`, `e2e/helpers.ts`, `scripts/e2e-api.mjs`.
- Modify: root `package.json` (`@playwright/test`, `e2e` script), `.github/workflows/ci.yml` (new `e2e-auth` job), `docs/runbooks/branch-protection.md` (8 checks).

---

### Task 1: Migration 0010 + ORM models + session_limits

**Files:**
- Create: `backend/core/alembic/versions/0010_sessions_v1.py`
- Create: `backend/core/modules/identity/session_limits.py`
- Modify: `backend/core/modules/identity/models.py`
- Test: `backend/core/tests/test_session_models.py`

**Interfaces:**
- Produces: `SessionWeb` ORM model (identity.sessions_web); `SessionRefresh` gains `family_id: uuid.UUID`, `client_id: uuid.UUID` (FK oauth_clients), `device_fingerprint: str | None`, `last_used_at: datetime | None`; constants `WEB_SESSION_TTL_SECONDS = 2_592_000`, `REFRESH_TOKEN_TTL_SECONDS = 2_592_000`, `SESSION_COOKIE_NAME = "agri_sid"`, `DEVICE_LABEL_MAX_CHARS = 64`.

- [ ] **Step 1: Write the failing test**

`backend/core/tests/test_session_models.py`:

```python
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
```

- [ ] **Step 2: Run it to verify failure**

Run (from `backend/core`): `.venv\Scripts\pytest.exe tests/test_session_models.py -q`
Expected: FAIL — `ImportError` (no `SessionWeb`, no `session_limits`).

- [ ] **Step 3: Create `session_limits.py`**

```python
"""Every session/refresh limit lives here (D09) - numbers the test suite pins.

Same contract as otp_limits.py: product security decisions, not deployment
knobs; change a value and its boundary test must change in the same commit.
"""

# 30-day rolling credential lifetime (spec assumption, confirmed in the PR
# description). Both sides match on purpose: the web session and the refresh
# family are two faces of "a device stays signed in for a month of disuse".
WEB_SESSION_TTL_SECONDS = 30 * 86400
REFRESH_TOKEN_TTL_SECONDS = 30 * 86400

# httpOnly + Secure + SameSite=Lax, host-only (no Domain attribute) - the
# session must never be readable by JS or sent to sibling subdomains.
SESSION_COOKIE_NAME = "agri_sid"

DEVICE_LABEL_MAX_CHARS = 64
```

- [ ] **Step 4: Add models to `models.py`**

Append new columns to `SessionRefresh` (after `rotated_from`) and add `SessionWeb` after it:

```python
    # D09 rotation family: family_id is the root row's id, shared by every
    # rotation descendant so one UPDATE revokes the whole family. client_id
    # scopes tokens per relying app; device_fingerprint binds them to the UA.
    family_id: Mapped[uuid.UUID] = mapped_column(
        postgresql.UUID(as_uuid=True), nullable=False, index=True
    )
    client_id: Mapped[uuid.UUID] = mapped_column(
        postgresql.UUID(as_uuid=True), ForeignKey("identity.oauth_clients.id"), nullable=False
    )
    device_fingerprint: Mapped[str | None] = mapped_column(Text, nullable=True)
    last_used_at: Mapped[datetime | None] = mapped_column(TIMESTAMP(timezone=True), nullable=True)


class SessionWeb(UUIDv7PKMixin, TimestampMixin, Base):
    """id.agri.in browser session (D09). Stores the sid HASH only - a
    plaintext sid column must never exist. Revocation is revoked_at (instant
    server-side deny), not soft-delete."""

    __tablename__ = "sessions_web"
    __table_args__ = {"schema": "identity"}

    user_id: Mapped[uuid.UUID] = mapped_column(
        postgresql.UUID(as_uuid=True), ForeignKey("identity.users.id"), nullable=False, index=True
    )
    sid_hash: Mapped[str] = mapped_column(Text, unique=True, nullable=False)
    device_fingerprint: Mapped[str | None] = mapped_column(Text, nullable=True)
    device_label: Mapped[str | None] = mapped_column(Text, nullable=True)
    ip: Mapped[str | None] = mapped_column(Text, nullable=True)
    last_seen_at: Mapped[datetime | None] = mapped_column(TIMESTAMP(timezone=True), nullable=True)
    expires_at: Mapped[datetime] = mapped_column(TIMESTAMP(timezone=True), nullable=False)
    revoked_at: Mapped[datetime | None] = mapped_column(TIMESTAMP(timezone=True), nullable=True)
```

- [ ] **Step 5: Write migration `0010_sessions_v1.py`**

```python
"""sessions v1: web sessions table + refresh-family columns (D09).

Revision ID: 0010
Revises: 0009
Create Date: 2026-07-11

"""
# -- THREAT/NOTES:
# downgrade data loss: drops sessions_web (every id.agri.in login) and the
#   refresh-family columns (rotation lineage). Pre-launch this is "everyone
#   logs in again" - acceptable and reversible by design.
# locks: sessions_refresh is empty until this spec's code ships, so the
#   NOT NULL ADD COLUMNs take a brief exclusive lock on an empty table;
#   CREATE TABLE/INDEX on new objects; negligible.
# rollout: run after 0009. No seed data. Revocation is revoked_at, never
#   DELETE - the device manager and reuse forensics read revoked rows.

from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op
from shared.migrations import pk_column, timestamp_columns

revision: str = "0010"
down_revision: str | None = "0009"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "sessions_web",
        pk_column(),
        *timestamp_columns(),
        sa.Column(
            "user_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("identity.users.id"),
            nullable=False,
        ),
        sa.Column("sid_hash", sa.Text, unique=True, nullable=False),
        sa.Column("device_fingerprint", sa.Text, nullable=True),
        sa.Column("device_label", sa.Text, nullable=True),
        sa.Column("ip", sa.Text, nullable=True),
        sa.Column("last_seen_at", sa.TIMESTAMP(timezone=True), nullable=True),
        sa.Column("expires_at", sa.TIMESTAMP(timezone=True), nullable=False),
        sa.Column("revoked_at", sa.TIMESTAMP(timezone=True), nullable=True),
        schema="identity",
    )
    op.create_index(
        "ix_identity_sessions_web_user_id", "sessions_web", ["user_id"], schema="identity"
    )
    op.create_index(
        "ix_identity_sessions_web_user_active",
        "sessions_web",
        ["user_id", "revoked_at"],
        schema="identity",
    )
    op.add_column(
        "sessions_refresh",
        sa.Column("family_id", postgresql.UUID(as_uuid=True), nullable=False),
        schema="identity",
    )
    op.add_column(
        "sessions_refresh",
        sa.Column(
            "client_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("identity.oauth_clients.id"),
            nullable=False,
        ),
        schema="identity",
    )
    op.add_column(
        "sessions_refresh",
        sa.Column("device_fingerprint", sa.Text, nullable=True),
        schema="identity",
    )
    op.add_column(
        "sessions_refresh",
        sa.Column("last_used_at", sa.TIMESTAMP(timezone=True), nullable=True),
        schema="identity",
    )
    op.create_index(
        "ix_identity_sessions_refresh_family_id",
        "sessions_refresh",
        ["family_id"],
        schema="identity",
    )
    op.create_index(
        "ix_identity_sessions_refresh_user_active",
        "sessions_refresh",
        ["user_id", "revoked_at"],
        schema="identity",
    )


def downgrade() -> None:
    op.drop_index(
        "ix_identity_sessions_refresh_user_active", "sessions_refresh", schema="identity"
    )
    op.drop_index("ix_identity_sessions_refresh_family_id", "sessions_refresh", schema="identity")
    op.drop_column("sessions_refresh", "last_used_at", schema="identity")
    op.drop_column("sessions_refresh", "device_fingerprint", schema="identity")
    op.drop_column("sessions_refresh", "client_id", schema="identity")
    op.drop_column("sessions_refresh", "family_id", schema="identity")
    op.drop_index("ix_identity_sessions_web_user_active", "sessions_web", schema="identity")
    op.drop_index("ix_identity_sessions_web_user_id", "sessions_web", schema="identity")
    op.drop_table("sessions_web", schema="identity")
```

- [ ] **Step 6: Run tests to verify pass**

Run: `.venv\Scripts\pytest.exe tests/test_session_models.py -q` (the session-scoped `database_url` fixture recreates `agri_test` and runs `alembic upgrade head`, so the new migration is exercised).
Expected: PASS (3 tests). Then run `.venv\Scripts\pytest.exe -q` to confirm nothing else broke.

- [ ] **Step 7: Commit**

```bash
git add backend/core/alembic/versions/0010_sessions_v1.py backend/core/modules/identity/models.py backend/core/modules/identity/session_limits.py backend/core/tests/test_session_models.py
git commit -m "feat(d09): sessions_web table and refresh-family schema"
```

### Task 2: Web-session service (create / resolve / revoke / revoke-all)

**Files:**
- Create: `backend/core/modules/identity/session_service.py`
- Test: `backend/core/tests/test_session_service.py`

**Interfaces:**
- Consumes: `SessionWeb`, `session_limits`, `oauth_service.hash_code`, `oauth_service.load_token_subject`.
- Produces (exact signatures later tasks rely on):
  - `device_fingerprint(user_agent: str | None, platform: str | None) -> str`
  - `@dataclass(frozen=True) WebPrincipal(user_id: uuid.UUID, agri_id: str, roles: tuple[str, ...], session_id: uuid.UUID, fingerprint: str | None)`
  - `async create_web_session(session, *, user_id, fingerprint, ip, device_label=None) -> str` (plaintext sid, exactly once)
  - `async resolve_web_session(session, sid: str) -> WebPrincipal | None` (None for unknown/expired/revoked sid or non-active user; touches `last_seen_at`)
  - `async revoke_web_session(session, *, session_id: uuid.UUID, user_id: uuid.UUID) -> bool`
  - `async revoke_everything(session, user_id: uuid.UUID) -> tuple[int, int]` (bulk-revokes all web sessions AND all refresh rows; returns counts)

- [ ] **Step 1: Write the failing test**

`backend/core/tests/test_session_service.py`:

```python
"""D09.C web-session lifecycle: resolve, deny, revoke, revoke-everything."""

from datetime import UTC, datetime, timedelta

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from modules.identity.models import SessionRefresh, SessionWeb
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


async def _user(session: AsyncSession, phone: str):
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
    # bob cannot revoke alice's session
    assert not await revoke_web_session(
        db_session, session_id=principal.session_id, user_id=bob.id
    )
    assert await revoke_web_session(
        db_session, session_id=principal.session_id, user_id=alice.id
    )
    assert await resolve_web_session(db_session, sid) is None


async def test_revoke_everything_kills_sessions_and_refresh(db_session: AsyncSession) -> None:
    import uuid as uuid_mod

    from modules.identity.oauth_service import get_client

    user = await _user(db_session, "+919876510005")
    sid_a = await create_web_session(db_session, user_id=user.id, fingerprint="a", ip=None)
    sid_b = await create_web_session(db_session, user_id=user.id, fingerprint="b", ip=None)
    client = await get_client(db_session, "web-agri")
    assert client is not None
    family = uuid_mod.uuid4()
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
```

- [ ] **Step 2: Run it to verify failure**

Run: `.venv\Scripts\pytest.exe tests/test_session_service.py -q`
Expected: FAIL — `ModuleNotFoundError: modules.identity.session_service`.

- [ ] **Step 3: Implement `session_service.py`**

```python
"""id.agri.in web-session lifecycle (D09.A/C) - no HTTP here.

The sid is a 256-bit random token; sessions_web stores SHA-256(sid) only, the
plaintext exists exactly once in create_web_session's return value (it goes
straight into the Set-Cookie header). Resolution re-checks user status on
every request, so suspension is an instant deny, not an eventual one.

Functions take the caller's AsyncSession and flush but never commit.
"""

import hashlib
import secrets
import uuid
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta

from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from modules.identity.models import SessionRefresh, SessionWeb
from modules.identity.oauth_service import hash_code, load_token_subject
from modules.identity.session_limits import WEB_SESSION_TTL_SECONDS
from shared.telemetry import get_logger

logger = get_logger(__name__)


def device_fingerprint(user_agent: str | None, platform: str | None) -> str:
    """Privacy-light device binding: UA + client-hint platform, hashed.

    Deliberately coarse - it distinguishes "my laptop" from "a stolen token
    replayed elsewhere", not one user from another. 32 hex chars keep rows
    compact; collision resistance at that scope is ample.
    """
    raw = f"{user_agent or ''}|{platform or ''}"
    return hashlib.sha256(raw.encode()).hexdigest()[:32]


@dataclass(frozen=True)
class WebPrincipal:
    """The resolved session identity routers act on. Internal-only shape -
    response models re-expose agri_id and stringified session ids only."""

    user_id: uuid.UUID
    agri_id: str
    roles: tuple[str, ...]
    session_id: uuid.UUID
    fingerprint: str | None


async def create_web_session(
    session: AsyncSession,
    *,
    user_id: uuid.UUID,
    fingerprint: str,
    ip: str | None,
    device_label: str | None = None,
) -> str:
    """Mint a session and return the plaintext sid exactly once.

    Fixation hardening: callers ALWAYS get a fresh sid at login - there is no
    code path that adopts or upgrades a pre-login identifier.
    """
    sid = secrets.token_urlsafe(32)
    session.add(
        SessionWeb(
            user_id=user_id,
            sid_hash=hash_code(sid),
            device_fingerprint=fingerprint,
            device_label=device_label,
            ip=ip,
            expires_at=datetime.now(UTC) + timedelta(seconds=WEB_SESSION_TTL_SECONDS),
        )
    )
    await session.flush()
    logger.info("session.web.created", extra={"extra_fields": {"user": str(user_id)}})
    return sid


async def resolve_web_session(session: AsyncSession, sid: str) -> WebPrincipal | None:
    """None for unknown, expired, revoked, or non-active-user sessions - the
    four cases are indistinguishable to callers (and to attackers)."""
    now = datetime.now(UTC)
    row = await session.scalar(
        select(SessionWeb).where(
            SessionWeb.sid_hash == hash_code(sid),
            SessionWeb.revoked_at.is_(None),
            SessionWeb.expires_at > now,
        )
    )
    if row is None:
        return None
    subject = await load_token_subject(session, row.user_id)
    if subject is None:  # suspended or gone: instant deny
        return None
    row.last_seen_at = now
    await session.flush()
    return WebPrincipal(
        user_id=subject.user_id,
        agri_id=subject.agri_id,
        roles=subject.roles,
        session_id=row.id,
        fingerprint=row.device_fingerprint,
    )


async def revoke_web_session(
    session: AsyncSession, *, session_id: uuid.UUID, user_id: uuid.UUID
) -> bool:
    """Revoke one session, only if it belongs to user_id (ownership in the
    WHERE clause, not in caller logic)."""
    row = await session.scalar(
        update(SessionWeb)
        .where(
            SessionWeb.id == session_id,
            SessionWeb.user_id == user_id,
            SessionWeb.revoked_at.is_(None),
        )
        .values(revoked_at=datetime.now(UTC))
        .returning(SessionWeb.id)
    )
    return row is not None


async def revoke_everything(session: AsyncSession, user_id: uuid.UUID) -> tuple[int, int]:
    """Logout-everywhere: every web session and every refresh row, two bulk
    UPDATEs inside the caller's single transaction (one request cycle, the
    non-negotiable a test pins)."""
    now = datetime.now(UTC)
    web = await session.execute(
        update(SessionWeb)
        .where(SessionWeb.user_id == user_id, SessionWeb.revoked_at.is_(None))
        .values(revoked_at=now)
    )
    refresh = await session.execute(
        update(SessionRefresh)
        .where(SessionRefresh.user_id == user_id, SessionRefresh.revoked_at.is_(None))
        .values(revoked_at=now)
    )
    logger.warning(
        "session.logout_everywhere",
        extra={
            "extra_fields": {
                "user": str(user_id),
                "web_revoked": web.rowcount,
                "refresh_revoked": refresh.rowcount,
            }
        },
    )
    return web.rowcount, refresh.rowcount
```

- [ ] **Step 4: Run tests to verify pass**

Run: `.venv\Scripts\pytest.exe tests/test_session_service.py -q`
Expected: PASS (5 tests).

- [ ] **Step 5: Commit**

```bash
git add backend/core/modules/identity/session_service.py backend/core/tests/test_session_service.py
git commit -m "feat(d09): web-session service with instant suspended deny"
```

---

### Task 3: Refresh-token service — rotation, reuse detection, family revoke

This is the file the Definition of Done requires reading line-by-line before merge.

**Files:**
- Create: `backend/core/modules/identity/refresh_service.py`
- Test: `backend/core/tests/test_refresh_rotation.py`

**Interfaces:**
- Consumes: `SessionRefresh` (Task 1), `hash_code`, `load_token_subject`, `REFRESH_TOKEN_TTL_SECONDS`.
- Produces:
  - `class RefreshInvalidError(Exception)` / `class RefreshReuseError(RefreshInvalidError)`
  - `@dataclass(frozen=True) RefreshRotation(token: str, row_id: uuid.UUID, family_id: uuid.UUID, subject: TokenSubject)`
  - `async issue_refresh_token(session, *, user_id, client: OAuthClient, fingerprint: str | None, ip: str | None, device_label: str | None = None) -> RefreshRotation` (new family; `family_id == row id`)
  - `async rotate_refresh_token(session, *, token: str, client: OAuthClient, fingerprint: str | None) -> RefreshRotation` (raises on any failure)
  - `async revoke_family(session, family_id: uuid.UUID) -> int`
  - `async revoke_families_for_device(session, *, user_id, fingerprint: str) -> int` (device logout kills that device's app tokens too)

- [ ] **Step 1: Write the failing test**

`backend/core/tests/test_refresh_rotation.py`:

```python
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
    assert all(row.revoked_at is not None for row in rows)  # whole family, including the live leaf
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
    row = (await db_session.scalars(select(SessionRefresh))).one()
    assert row.revoked_at is not None  # theft signal: family is gone


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
```

- [ ] **Step 2: Run it to verify failure**

Run: `.venv\Scripts\pytest.exe tests/test_refresh_rotation.py -q`
Expected: FAIL — `ModuleNotFoundError: modules.identity.refresh_service`.

- [ ] **Step 3: Implement `refresh_service.py`**

```python
"""Rotating refresh tokens (D09.B) - no HTTP, no authlib here.

Lifecycle invariants (the ones the reuse test pins):
- sessions_refresh stores SHA-256(token) only; plaintext exists exactly once,
  in RefreshRotation.token, and goes straight into the /token response body.
- family_id is the ROOT row's id, copied to every rotation descendant. One
  bulk UPDATE on family_id revokes an entire lineage.
- Rotation is an atomic UPDATE .. WHERE revoked_at IS NULL .. RETURNING: two
  racing rotations can never both win. The loser's presented token now hashes
  to a REVOKED row, which is exactly the reuse signature.
- Reuse of ANY revoked row's token (rotated-away or logged-out) revokes the
  whole family and logs an audit line - the token was seen by two parties, so
  every credential derived from it is presumed stolen.
- Device binding is strict: a fingerprint mismatch is treated as theft, not
  drift - family revoked. A browser upgrade changes the fingerprint and logs
  that device out; acceptable v1 cost, decided in the D09 plan.
- Rotation happens on the ATTEMPT, before authlib judges the request
  (burn-on-attempt, mirrors D08 codes and D07 OTP burn semantics).

Functions take the caller's AsyncSession and flush but never commit.
"""

import secrets
import uuid
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta

from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from modules.identity.models import OAuthClient, SessionRefresh
from modules.identity.oauth_service import TokenSubject, hash_code, load_token_subject
from modules.identity.session_limits import REFRESH_TOKEN_TTL_SECONDS
from shared.telemetry import get_logger

logger = get_logger(__name__)


class RefreshInvalidError(Exception):
    """Unknown, expired, foreign-client, device-mismatched, or dead-user
    token. Callers surface every case identically (invalid_grant)."""


class RefreshReuseError(RefreshInvalidError):
    """A revoked token was presented: theft signature. The family is already
    revoked by the time this raises."""


@dataclass(frozen=True)
class RefreshRotation:
    token: str
    row_id: uuid.UUID
    family_id: uuid.UUID
    subject: TokenSubject


def _new_row(
    *,
    user_id: uuid.UUID,
    client_row_id: uuid.UUID,
    family_id: uuid.UUID | None,
    fingerprint: str | None,
    device_label: str | None,
    ip: str | None,
    rotated_from: uuid.UUID | None,
) -> tuple[str, SessionRefresh]:
    token = secrets.token_urlsafe(32)
    row = SessionRefresh(
        user_id=user_id,
        token_hash=hash_code(token),
        client_id=client_row_id,
        device_fingerprint=fingerprint,
        device_label=device_label,
        ip=ip,
        expires_at=datetime.now(UTC) + timedelta(seconds=REFRESH_TOKEN_TTL_SECONDS),
        rotated_from=rotated_from,
        # family_id must be NOT NULL on insert; the root points at itself,
        # which is why the row id is assigned client-side (UUIDv7PKMixin)
        family_id=family_id if family_id is not None else uuid.uuid4(),
    )
    if family_id is None:
        row.family_id = row.id  # root anchors its own family
    return token, row


async def revoke_family(session: AsyncSession, family_id: uuid.UUID) -> int:
    result = await session.execute(
        update(SessionRefresh)
        .where(SessionRefresh.family_id == family_id, SessionRefresh.revoked_at.is_(None))
        .values(revoked_at=datetime.now(UTC))
    )
    return result.rowcount


async def revoke_families_for_device(
    session: AsyncSession, *, user_id: uuid.UUID, fingerprint: str
) -> int:
    """This-device logout: kill every refresh row minted from this device."""
    result = await session.execute(
        update(SessionRefresh)
        .where(
            SessionRefresh.user_id == user_id,
            SessionRefresh.device_fingerprint == fingerprint,
            SessionRefresh.revoked_at.is_(None),
        )
        .values(revoked_at=datetime.now(UTC))
    )
    return result.rowcount


async def issue_refresh_token(
    session: AsyncSession,
    *,
    user_id: uuid.UUID,
    client: OAuthClient,
    fingerprint: str | None,
    ip: str | None,
    device_label: str | None = None,
) -> RefreshRotation:
    """Start a new family (the code-exchange mint point)."""
    subject = await load_token_subject(session, user_id)
    if subject is None:
        raise RefreshInvalidError("subject not eligible")
    token, row = _new_row(
        user_id=user_id,
        client_row_id=client.id,
        family_id=None,
        fingerprint=fingerprint,
        device_label=device_label,
        ip=ip,
        rotated_from=None,
    )
    session.add(row)
    await session.flush()
    logger.info(
        "refresh.family.issued",
        extra={"extra_fields": {"family": str(row.family_id), "client": client.client_id}},
    )
    return RefreshRotation(token=token, row_id=row.id, family_id=row.family_id, subject=subject)


async def rotate_refresh_token(
    session: AsyncSession, *, token: str, client: OAuthClient, fingerprint: str | None
) -> RefreshRotation:
    """Atomically retire the presented token and mint its successor.

    Order matters and every branch is deliberate:
    1. Atomic claim (UPDATE .. revoked_at IS NULL .. RETURNING) scoped to this
       client. Success means WE retired a live token just now.
    2. Claim failed but the hash exists for this client -> the token was
       already retired: REUSE. Revoke the family, audit, raise.
    3. Claim succeeded but the row was already past expiry -> plain invalid
       (a hoarded-not-stolen token; no family damage).
    4. Fingerprint mismatch -> theft signal: revoke family, audit, raise.
    5. Suspended/missing user -> revoke family, raise (instant deny).
    6. Mint successor: same family_id, rotated_from=old row.
    """
    now = datetime.now(UTC)
    presented_hash = hash_code(token)
    row = await session.scalar(
        update(SessionRefresh)
        .where(
            SessionRefresh.token_hash == presented_hash,
            SessionRefresh.client_id == client.id,
            SessionRefresh.revoked_at.is_(None),
        )
        .values(revoked_at=now, last_used_at=now)
        .returning(SessionRefresh)
    )
    if row is None:
        stale = await session.scalar(
            select(SessionRefresh).where(
                SessionRefresh.token_hash == presented_hash,
                SessionRefresh.client_id == client.id,
            )
        )
        if stale is not None:
            revoked = await revoke_family(session, stale.family_id)
            logger.warning(
                "refresh.reuse.family_revoked",
                extra={
                    "extra_fields": {
                        "family": str(stale.family_id),
                        "client": client.client_id,
                        "revoked_rows": revoked,
                    }
                },
            )
            raise RefreshReuseError("rotated token replayed")
        raise RefreshInvalidError("unknown token")
    if row.expires_at <= now:
        raise RefreshInvalidError("expired token")
    if fingerprint != row.device_fingerprint:
        revoked = await revoke_family(session, row.family_id)
        logger.warning(
            "refresh.device_mismatch.family_revoked",
            extra={
                "extra_fields": {
                    "family": str(row.family_id),
                    "client": client.client_id,
                    "revoked_rows": revoked,
                }
            },
        )
        raise RefreshInvalidError("device mismatch")
    subject = await load_token_subject(session, row.user_id)
    if subject is None:
        await revoke_family(session, row.family_id)
        raise RefreshInvalidError("subject not eligible")
    new_token, new_row = _new_row(
        user_id=row.user_id,
        client_row_id=row.client_id,
        family_id=row.family_id,
        fingerprint=row.device_fingerprint,
        device_label=row.device_label,
        ip=row.ip,
        rotated_from=row.id,
    )
    session.add(new_row)
    await session.flush()
    return RefreshRotation(
        token=new_token, row_id=new_row.id, family_id=new_row.family_id, subject=subject
    )
```

- [ ] **Step 4: Run tests to verify pass**

Run: `.venv\Scripts\pytest.exe tests/test_refresh_rotation.py -q`
Expected: PASS (8 tests). Note: if `_new_row`'s self-family assignment trips mypy or the UUIDv7 mixin assigns `id` lazily, assign explicitly: `row.id = uuid6.uuid7()` before `row.family_id = row.id` (check how `UUIDv7PKMixin` defaults `id` in `shared/db.py` — it generates client-side, so `row.id` is available immediately after construction).

- [ ] **Step 5: Commit**

```bash
git add backend/core/modules/identity/refresh_service.py backend/core/tests/test_refresh_rotation.py
git commit -m "feat(d09): rotating refresh tokens with reuse family-revoke"
```

### Task 4: /token — refresh grant + refresh minting on code exchange

**Files:**
- Modify: `backend/core/modules/identity/oauth_server.py`
- Modify: `backend/core/modules/identity/oauth_router.py` (token endpoint only — /authorize is Task 8)
- Modify: `backend/core/tests/test_oauth_flow.py` (one assertion)
- Test: `backend/core/tests/test_oauth_refresh_grant.py`

**Interfaces:**
- Consumes: `issue_refresh_token`, `rotate_refresh_token`, `RefreshInvalidError`, `device_fingerprint` (Tasks 2–3).
- Produces: `/token` responses now carry `refresh_token` on BOTH grants; `RequestContext` gains `rotation: RefreshRotation | None = None`, `new_refresh_token: str | None = None`, `issued_family_id: uuid.UUID | None = None`.

- [ ] **Step 1: Write the failing tests**

In `tests/test_oauth_flow.py`, `test_full_code_flow_with_pkce`, replace
`assert "refresh_token" not in body  # D09, not sooner` with:

```python
    assert body["refresh_token"]  # D09: the code exchange starts a refresh family
```

Create `tests/test_oauth_refresh_grant.py` (reuses the `api` fixture idiom and `_pkce`/`_mint_code`/`_exchange` helpers — import them from `tests.test_oauth_flow`):

```python
"""D09.B at the HTTP layer: grant_type=refresh_token on the real /token."""

import httpx
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from modules.identity.models import SessionRefresh
from tests.test_oauth_flow import _exchange, _mint_code, _pkce, api  # noqa: F401

UA = {"user-agent": "pytest-device", "sec-ch-ua-platform": '"Windows"'}


async def _login_and_get_refresh(
    http: httpx.AsyncClient, session: AsyncSession
) -> tuple[str, dict[str, str]]:
    verifier, challenge = _pkce()
    code, _ = await _mint_code(session, challenge)
    response = await _exchange(http, code, verifier)  # httpx sends its own UA consistently
    assert response.status_code == 200
    return response.json()["refresh_token"], {}


async def _refresh(http: httpx.AsyncClient, token: str, client_id: str = "web-agri") -> httpx.Response:
    return await http.post(
        "/token",
        data={"grant_type": "refresh_token", "refresh_token": token, "client_id": client_id},
    )


async def test_refresh_grant_rotates(api: tuple[httpx.AsyncClient, AsyncSession]) -> None:
    http, session = api
    first, _ = await _login_and_get_refresh(http, session)
    response = await _refresh(http, first)
    assert response.status_code == 200
    body = response.json()
    assert body["token_type"] == "Bearer"
    assert body["access_token"]
    assert body["refresh_token"] and body["refresh_token"] != first


async def test_refresh_reuse_revokes_family_via_http(
    api: tuple[httpx.AsyncClient, AsyncSession],
) -> None:
    http, session = api
    first, _ = await _login_and_get_refresh(http, session)
    second = (await _refresh(http, first)).json()["refresh_token"]

    reuse = await _refresh(http, first)  # replay the rotated token
    assert reuse.status_code == 400
    assert reuse.json()["error"] == "invalid_grant"

    dead_leaf = await _refresh(http, second)  # the whole family died with it
    assert dead_leaf.status_code == 400
    rows = (await session.scalars(select(SessionRefresh))).all()
    assert rows and all(row.revoked_at is not None for row in rows)


async def test_refresh_wrong_client_rejected(
    api: tuple[httpx.AsyncClient, AsyncSession],
) -> None:
    http, session = api
    token, _ = await _login_and_get_refresh(http, session)
    response = await _refresh(http, token, client_id="web-milk")
    assert response.status_code == 400
    assert response.json()["error"] == "invalid_grant"


async def test_refresh_missing_token_param_rejected(
    api: tuple[httpx.AsyncClient, AsyncSession],
) -> None:
    http, _ = api
    response = await http.post(
        "/token", data={"grant_type": "refresh_token", "client_id": "web-agri"}
    )
    assert response.status_code == 400


async def test_failed_code_exchange_leaves_no_live_refresh_family(
    api: tuple[httpx.AsyncClient, AsyncSession],
) -> None:
    """A refresh row minted during a PKCE-failed exchange must not survive as
    a phantom device."""
    import secrets

    http, session = api
    verifier, challenge = _pkce()
    code, _ = await _mint_code(session, challenge)
    wrong = await _exchange(http, code, secrets.token_urlsafe(48))
    assert wrong.status_code == 400
    rows = (await session.scalars(select(SessionRefresh))).all()
    assert all(row.revoked_at is not None for row in rows)
    _ = verifier
```

- [ ] **Step 2: Run to verify failure**

Run: `.venv\Scripts\pytest.exe tests/test_oauth_refresh_grant.py tests/test_oauth_flow.py -q`
Expected: FAIL — refresh grant 400s (`unsupported_grant_type`), `refresh_token` absent from code-exchange body.

- [ ] **Step 3: Extend `oauth_server.py`**

3a. `ClientWrapper.check_grant_type` becomes:

```python
    def check_grant_type(self, grant_type: str) -> bool:
        return grant_type in ("authorization_code", "refresh_token")
```

(Also update the module docstring bullet that says authlib "can never emit a refresh token" — D09 adds the grant deliberately, as that comment itself promises.)

3b. `RequestContext` gains the D09 fields:

```python
@dataclass
class RequestContext:
    """Rows prefetched by the router; the only state authlib's hooks see."""

    client: ClientWrapper | None = None
    code: OAuthCode | None = None
    subject: TokenSubject | None = None
    # D09: refresh rotation result (refresh grant) or freshly-minted family
    # (code grant). new_refresh_token rides into the token response;
    # issued_family_id lets the router clean up when authlib rejects late.
    rotation: RefreshRotation | None = None
    new_refresh_token: str | None = None
    issued_family_id: uuid.UUID | None = None
```

with imports `import uuid` and `from modules.identity.refresh_service import RefreshRotation`.

3c. New grant class after `AgriAuthorizationCodeGrant`:

```python
class RefreshCredentialWrapper:
    """authlib's view of an already-rotated sessions_refresh lineage. The
    atomic rotation in the router settled reuse/expiry/binding; this only
    proves the presented token is THIS request's."""

    def __init__(self, rotation: RefreshRotation) -> None:
        self.rotation = rotation

    def get_scope(self) -> str:
        return ""


class AgriRefreshTokenGrant(grants.RefreshTokenGrant):  # type: ignore[misc]
    TOKEN_ENDPOINT_AUTH_METHODS = ["none"]
    INCLUDE_NEW_REFRESH_TOKEN = True

    def authenticate_refresh_token(self, refresh_token: str) -> RefreshCredentialWrapper | None:
        rotation = self.server.ctx.rotation
        if rotation is None:
            return None  # rotation failed in prefetch -> invalid_grant
        return RefreshCredentialWrapper(rotation)

    def authenticate_user(self, credential: RefreshCredentialWrapper) -> TokenSubject | None:
        subject: TokenSubject | None = self.server.ctx.subject
        return subject

    def revoke_old_credential(self, credential: RefreshCredentialWrapper) -> None:
        pass  # rotated atomically in the router before authlib ran
```

3d. In `AgriAuthorizationServer.__init__`, register the grant and swap the token generator for a ctx-aware closure:

```python
    def __init__(self, ctx: RequestContext) -> None:
        super().__init__()
        self.ctx = ctx
        self.register_grant(AgriAuthorizationCodeGrant, [S256CodeChallenge(required=True)])
        self.register_grant(AgriRefreshTokenGrant)

        def _token_with_refresh(
            grant_type: str,
            client: ClientWrapper,
            user: TokenSubject | None = None,
            scope: str | None = None,
            expires_in: int | None = None,
            include_refresh_token: bool = True,
        ) -> dict[str, Any]:
            token = _generate_access_token(grant_type, client, user, scope, expires_in)
            # D09: the router minted/rotated the opaque refresh credential;
            # authlib only ever sees (and returns) the plaintext once
            if self.ctx.new_refresh_token is not None:
                token["refresh_token"] = self.ctx.new_refresh_token
            return token

        self.register_token_generator("default", _token_with_refresh)
```

(`_generate_access_token` itself: drop the `include_refresh_token` param and its docstring line about no refresh key — the closure owns that decision now.)

- [ ] **Step 4: Extend the `/token` endpoint in `oauth_router.py`**

Replace the prefetch block in `token()` with:

```python
    ctx = await _client_context(session, params.get("client_id"))
    grant_type = params.get("grant_type")
    fingerprint = device_fingerprint(
        request.headers.get("user-agent"), request.headers.get("sec-ch-ua-platform")
    )
    code = params.get("code")
    if ctx.client is not None and grant_type == "authorization_code" and code:
        ctx.code = await consume_authorization_code(session, code=code, client=ctx.client.row)
        if ctx.code is not None:
            ctx.subject = await load_token_subject(session, ctx.code.user_id)
        if ctx.subject is not None and ctx.code is not None:
            # D09: every successful code exchange starts a refresh family,
            # bound to the exchanging device (D10's BFF forwards the browser
            # UA so the binding is the user's browser, not the BFF host)
            issued = await issue_refresh_token(
                session,
                user_id=ctx.code.user_id,
                client=ctx.client.row,
                fingerprint=fingerprint,
                ip=request.client.host if request.client else None,
            )
            ctx.new_refresh_token = issued.token
            ctx.issued_family_id = issued.family_id
    elif ctx.client is not None and grant_type == "refresh_token" and params.get("refresh_token"):
        try:
            # burn-on-attempt: the old token is retired even if authlib
            # rejects the request afterwards (mirrors D08 code burning)
            rotation = await rotate_refresh_token(
                session,
                token=params["refresh_token"],
                client=ctx.client.row,
                fingerprint=fingerprint,
            )
            ctx.rotation = rotation
            ctx.subject = rotation.subject
            ctx.new_refresh_token = rotation.token
            ctx.issued_family_id = rotation.family_id
        except RefreshInvalidError:
            pass  # ctx.rotation stays None -> authlib answers invalid_grant
    await session.commit()
    server = AgriAuthorizationServer(ctx)
    try:
        oauth2_request = build_oauth2_request("POST", str(request.url), params, datalist)
    except OAuth2Error as error:
        return server.handle_response(*error(None))
    response: Response = server.create_token_response(oauth2_request)
    if response.status_code != 200 and ctx.issued_family_id is not None:
        # a refresh credential whose plaintext never reached a client must
        # not linger as a phantom device in the manager
        await revoke_family(session, ctx.issued_family_id)
        await session.commit()
    return response
```

New imports in `oauth_router.py`:

```python
from modules.identity.refresh_service import (
    RefreshInvalidError,
    issue_refresh_token,
    revoke_family,
    rotate_refresh_token,
)
from modules.identity.session_service import device_fingerprint
```

- [ ] **Step 5: Run tests to verify pass**

Run: `.venv\Scripts\pytest.exe tests/test_oauth_refresh_grant.py tests/test_oauth_flow.py -q`
Expected: PASS. If `AgriRefreshTokenGrant` fails inside authlib validation, debug against authlib 1.7's `RefreshTokenGrant.validate_token_request` (it requires the `refresh_token` param, calls `authenticate_refresh_token`, then `authenticate_user`, then scope validation via `credential.get_scope()`) — the wrapper above satisfies exactly that surface.

- [ ] **Step 6: Full-suite + lints, then commit**

Run: `.venv\Scripts\pytest.exe -q && .venv\Scripts\ruff.exe format --check . && .venv\Scripts\ruff.exe check . && .venv\Scripts\mypy.exe .`

```bash
git add backend/core/modules/identity/oauth_server.py backend/core/modules/identity/oauth_router.py backend/core/tests/test_oauth_refresh_grant.py backend/core/tests/test_oauth_flow.py
git commit -m "feat(d09): refresh_token grant wired into the oauth server"
```

---

### Task 5: Real require_auth — pluggable principal resolver

**Files:**
- Modify: `backend/core/shared/security.py`
- Create: `backend/core/modules/identity/session_auth.py`
- Modify: `backend/core/main.py` (register resolver in `create_app`)
- Modify: `backend/core/tests/conftest.py` (reset hook)
- Test: `backend/core/tests/test_require_auth.py`

**Interfaces:**
- Consumes: `resolve_web_session`, `SESSION_COOKIE_NAME`, `shared.db.get_sessionmaker` (verify the exact factory name in `shared/db.py` — docs/backend-conventions.md names `get_sessionmaker()`; if it differs, adapt the one call site in `session_auth.py`).
- Produces:
  - `shared.security.register_principal_resolver(resolver: Callable[[Request], Awaitable[object | None]]) -> None` and `reset_principal_resolver() -> None`
  - `require_auth` now: 401 if no resolver registered or resolver returns None; else sets `request.state.principal`
  - `modules.identity.session_auth.resolve_principal(request: Request) -> WebPrincipal | None`
  - `modules.identity.session_auth.current_principal(request: Request) -> WebPrincipal` (FastAPI dependency for handlers) and `PrincipalDep = Annotated[WebPrincipal, Depends(current_principal)]`

- [ ] **Step 1: Write the failing test**

`backend/core/tests/test_require_auth.py`:

```python
"""D09: the SecureRouter 401 stub becomes real cookie auth via the registered
resolver. Import-linter forbids shared -> modules, hence the registration
indirection; these tests pin both halves."""

from collections.abc import AsyncIterator

import httpx
import pytest
from fastapi import Request
from sqlalchemy.ext.asyncio import AsyncSession

from main import create_app
from modules.identity.service import assign_role, create_user
from modules.identity.session_limits import SESSION_COOKIE_NAME
from modules.identity.session_service import create_web_session
from shared.db import get_session
from shared.security import register_principal_resolver, require_auth, reset_principal_resolver


async def test_require_auth_401s_without_resolver() -> None:
    reset_principal_resolver()
    scope = {"type": "http", "headers": [], "method": "GET", "path": "/x", "query_string": b""}
    with pytest.raises(Exception) as excinfo:
        await require_auth(Request(scope))
    assert getattr(excinfo.value, "status_code", None) == 401


async def test_require_auth_sets_principal_when_resolver_matches() -> None:
    async def fake_resolver(request: Request) -> object | None:
        return "principal-sentinel"

    register_principal_resolver(fake_resolver)
    scope = {"type": "http", "headers": [], "method": "GET", "path": "/x", "query_string": b""}
    request = Request(scope)
    await require_auth(request)
    assert request.state.principal == "principal-sentinel"


@pytest.fixture
async def api(db_session: AsyncSession) -> AsyncIterator[tuple[httpx.AsyncClient, AsyncSession]]:
    app = create_app()  # create_app registers the real resolver

    async def _session_override() -> AsyncIterator[AsyncSession]:
        yield db_session

    app.dependency_overrides[get_session] = _session_override
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="https://id.test") as client:
        yield client, db_session


async def test_private_route_rejects_no_cookie_and_garbage_cookie(
    api: tuple[httpx.AsyncClient, AsyncSession],
) -> None:
    http, _ = api
    # /auth/me lands in Task 6; until then use any private route the app
    # exposes - the ads router registers private routes since D03. If none
    # respond before Task 6, mark this test as the red half of Task 6 instead.
    response = await http.get("/auth/me")
    assert response.status_code in (401, 404)
    response = await http.get("/auth/me", cookies={SESSION_COOKIE_NAME: "garbage"})
    assert response.status_code in (401, 404)
```

NOTE: the real end-to-end proof (valid cookie → 200) lands with `/auth/me` in Task 6; this task pins the resolver mechanics.

- [ ] **Step 2: Run to verify failure**

Run: `.venv\Scripts\pytest.exe tests/test_require_auth.py -q`
Expected: FAIL — `ImportError: register_principal_resolver`.

- [ ] **Step 3: Rework `shared/security.py`**

Replace the `require_auth` stub (and module docstring's "401 unconditionally" sentence) with:

```python
from collections.abc import Awaitable, Callable

PrincipalResolver = Callable[[Request], Awaitable[object | None]]

_principal_resolver: PrincipalResolver | None = None


def register_principal_resolver(resolver: PrincipalResolver) -> None:
    """The identity module plugs real session auth in at app creation (D09).

    Indirection, not import: import-linter forbids shared -> modules, and the
    threat model (a route registered without public=True must never be open)
    holds either way - no resolver means every private route 401s.
    """
    global _principal_resolver
    _principal_resolver = resolver


def reset_principal_resolver() -> None:
    global _principal_resolver
    _principal_resolver = None


async def require_auth(request: Request) -> None:
    """Session-cookie auth for every non-public route (D09). Unresolved and
    unregistered are the same 401 - fail closed, never open."""
    if _principal_resolver is None:
        raise HTTPException(status_code=401, detail="Authentication required")
    principal = await _principal_resolver(request)
    if principal is None:
        raise HTTPException(status_code=401, detail="Authentication required")
    request.state.principal = principal
```

- [ ] **Step 4: Create `modules/identity/session_auth.py`**

```python
"""The registered principal resolver + handler-side dependency (D09.C).

require_auth is a router-level dependency, so the resolver manages its own
short DB session (get_session's request-scoped session belongs to the
endpoint's transaction). The commit persists the last_seen_at touch.
"""

from typing import Annotated

from fastapi import Depends, Request

from modules.identity.session_limits import SESSION_COOKIE_NAME
from modules.identity.session_service import WebPrincipal, resolve_web_session
from shared.db import get_sessionmaker


async def resolve_principal(request: Request) -> WebPrincipal | None:
    sid = request.cookies.get(SESSION_COOKIE_NAME)
    if not sid:
        return None
    maker = get_sessionmaker()
    async with maker() as session:
        principal = await resolve_web_session(session, sid)
        await session.commit()
    return principal


def current_principal(request: Request) -> WebPrincipal:
    principal = getattr(request.state, "principal", None)
    assert isinstance(principal, WebPrincipal), "route must be private (require_auth ran)"
    return principal


PrincipalDep = Annotated[WebPrincipal, Depends(current_principal)]
```

(If `shared/db.py` exposes the session factory under another name — e.g. `get_session_factory` or a module-level `async_sessionmaker` — use that; do NOT add a new engine.)

- [ ] **Step 5: Register in `main.py` and reset in `conftest.py`**

`main.py` — add imports and one line at the top of `create_app()`:

```python
from modules.identity.session_auth import resolve_principal
from shared.security import register_principal_resolver
```

```python
def create_app() -> FastAPI:
    init_sentry(get_settings())
    register_principal_resolver(resolve_principal)  # D09: real session auth
    ...
```

`tests/conftest.py` — inside the autouse `_reset_state` fixture, alongside `rate_limiter.reset()`:

```python
from shared.security import reset_principal_resolver
reset_principal_resolver()
```

(match the file's existing import style — imports at top, call in the fixture body).

- [ ] **Step 6: Run tests to verify pass**

Run: `.venv\Scripts\pytest.exe tests/test_require_auth.py -q` then the full `.venv\Scripts\pytest.exe -q` — pre-existing tests that relied on the unconditional 401 (if any assert on private routes) must still pass because no cookie ⇒ still 401.

- [ ] **Step 7: Commit**

```bash
git add backend/core/shared/security.py backend/core/modules/identity/session_auth.py backend/core/main.py backend/core/tests/conftest.py backend/core/tests/test_require_auth.py
git commit -m "feat(d09): require_auth resolves real web sessions"
```

### Task 6: Session router — login, logout, logout-everywhere, me, handle, language, devices

**Files:**
- Create: `backend/core/modules/identity/session_router.py`
- Modify: `backend/core/main.py` (add to `MODULE_ROUTERS`), `backend/core/public_routes.txt` (add `/auth/login`)
- Test: `backend/core/tests/test_session_router.py`, `backend/core/tests/test_devices_router.py`

**Interfaces:**
- Consumes: `consume_otp_proof(token) -> tuple[str, str] | None` (otp_service, GETDEL-atomic), `create_user`/`get_by_phone`/`assign_role`, `validate_handle`/`can_change_handle`/`HandleError`, `Profile` model, Tasks 2–5 services, `shared.pagination.paginate`.
- Produces HTTP surface the web-id UI (Task 10) calls:
  - `POST /auth/login` (public) `{otp_proof, device_label?}` → sets `agri_sid` cookie → `{status, is_new_user, agri_id, handle_is_fallback, language}`
  - `POST /auth/logout` (private) → revokes current session + this device's refresh families, clears cookie
  - `POST /auth/logout-everywhere` (private) → `revoke_everything`, clears cookie
  - `GET /auth/me` (private) → `{agri_id, handle_is_fallback, can_change_handle, language}`
  - `POST /auth/handle` (private) `{handle}` → 200 `{agri_id}` | 409 `{detail: reserved|invalid_format|taken|already_changed}`
  - `GET /auth/handle/check?h=` (private) → `{ok, code}`
  - `GET /auth/handle/suggest` (private) → `{suggestions: [str]}`
  - `POST /auth/language` (private) `{language: en|ta|hi}` → `{status}`
  - `GET /auth/devices?cursor=&limit=` (private) → cursor-paginated `{items: [{device_id, kind, client, label, current, last_seen_at, created_at}], next_cursor}`
  - `POST /auth/devices/revoke` (private) `{device_id, kind}` — web kind revokes session (+its device's refresh families); app kind revokes the family
  - `POST /auth/devices/label` (private) `{device_id, kind, label}`

- [ ] **Step 1: Write the failing tests**

`backend/core/tests/test_session_router.py`:

```python
"""D09.A/C at the HTTP layer: login (new + returning), cookie discipline,
fixation, suspended deny, logout, logout-everywhere in one request."""

from collections.abc import AsyncIterator

import httpx
import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from main import create_app
from modules.identity.models import SessionRefresh, SessionWeb, User
from modules.identity.otp_service import issue_otp, verify_otp
from modules.identity.session_limits import SESSION_COOKIE_NAME
from shared.db import get_session

PHONE = "+919876530001"
UA = {"user-agent": "pytest-browser", "sec-ch-ua-platform": '"Windows"'}


@pytest.fixture
async def api(
    db_session: AsyncSession, otp_redis: object
) -> AsyncIterator[tuple[httpx.AsyncClient, AsyncSession]]:
    app = create_app()

    async def _session_override() -> AsyncIterator[AsyncSession]:
        yield db_session

    app.dependency_overrides[get_session] = _session_override
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(
        transport=transport, base_url="https://id.test", headers=UA
    ) as client:
        yield client, db_session


async def _otp_proof(session: AsyncSession, phone: str = PHONE) -> str:
    from modules.identity.otp_drivers import MockDriver

    await issue_otp(session, phone=phone, purpose="login", ip=None, device_fingerprint=None)
    code = MockDriver.last_code(phone)
    assert code is not None
    return await verify_otp(session, phone=phone, purpose="login", code=code, ip=None)


async def _login(
    http: httpx.AsyncClient, session: AsyncSession, phone: str = PHONE
) -> httpx.Response:
    proof = await _otp_proof(session, phone)
    return await http.post("/auth/login", json={"otp_proof": proof})


async def test_new_user_login_sets_cookie_and_creates_account(
    api: tuple[httpx.AsyncClient, AsyncSession],
) -> None:
    http, session = api
    response = await _login(http, session)
    assert response.status_code == 200
    body = response.json()
    assert body["is_new_user"] is True
    assert body["agri_id"].startswith("AG-")
    assert body["handle_is_fallback"] is True
    cookie = response.headers["set-cookie"]
    assert SESSION_COOKIE_NAME in cookie
    assert "HttpOnly" in cookie and "Secure" in cookie and "SameSite=lax" in cookie.lower().replace("samesite=lax", "SameSite=lax")
    user = (await session.scalars(select(User))).one()
    assert user.phone_verified_at is not None


async def test_returning_login_and_session_fixation(
    api: tuple[httpx.AsyncClient, AsyncSession],
) -> None:
    http, session = api
    first = await _login(http, session)
    second = await _login(http, session)
    assert second.json()["is_new_user"] is False
    # fixation: every login mints a brand-new sid
    sid1 = first.cookies[SESSION_COOKIE_NAME]
    sid2 = second.cookies[SESSION_COOKIE_NAME]
    assert sid1 != sid2
    assert len((await session.scalars(select(User))).all()) == 1


async def test_login_rejects_bad_or_reused_proof(
    api: tuple[httpx.AsyncClient, AsyncSession],
) -> None:
    http, session = api
    assert (await http.post("/auth/login", json={"otp_proof": "junk"})).status_code == 400
    proof = await _otp_proof(session)
    assert (await http.post("/auth/login", json={"otp_proof": proof})).status_code == 200
    reuse = await http.post("/auth/login", json={"otp_proof": proof})  # GETDEL burned it
    assert reuse.status_code == 400


async def test_suspended_user_cannot_login_or_use_session(
    api: tuple[httpx.AsyncClient, AsyncSession],
) -> None:
    http, session = api
    await _login(http, session)
    user = (await session.scalars(select(User))).one()
    user.status = "suspended"
    await session.flush()
    assert (await http.get("/auth/me")).status_code == 401  # instant deny mid-session
    relogin = await _login(http, session)
    assert relogin.status_code == 403


async def test_me_requires_session_and_returns_public_shape(
    api: tuple[httpx.AsyncClient, AsyncSession],
) -> None:
    http, session = api
    assert (await http.get("/auth/me")).status_code == 401
    login = await _login(http, session)
    me = await http.get("/auth/me")
    assert me.status_code == 200
    body = me.json()
    assert body["agri_id"] == login.json()["agri_id"]
    assert "id" not in body and "user_id" not in body and "phone" not in body


async def test_logout_kills_session_and_device_refresh(
    api: tuple[httpx.AsyncClient, AsyncSession],
) -> None:
    http, session = api
    await _login(http, session)
    response = await http.post("/auth/logout")
    assert response.status_code == 200
    assert (await http.get("/auth/me")).status_code == 401
    row = (await session.scalars(select(SessionWeb))).one()
    assert row.revoked_at is not None


async def test_logout_everywhere_one_request_cycle(
    api: tuple[httpx.AsyncClient, AsyncSession],
) -> None:
    """Non-negotiable: ALL sessions + refresh families die in one request."""
    http, session = api
    await _login(http, session)  # device A (kept in http client jar)
    other = await _login(http, session)  # device B's session exists server-side
    _ = other

    response = await http.post("/auth/logout-everywhere")
    assert response.status_code == 200

    web_rows = (await session.scalars(select(SessionWeb))).all()
    refresh_rows = (await session.scalars(select(SessionRefresh))).all()
    assert len(web_rows) == 2 and all(r.revoked_at is not None for r in web_rows)
    assert all(r.revoked_at is not None for r in refresh_rows)
    assert (await http.get("/auth/me")).status_code == 401
```

`backend/core/tests/test_devices_router.py`:

```python
"""D09.D backend: device list/label/revoke + handle picker + language."""

from collections.abc import AsyncIterator

import httpx
import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from main import create_app
from modules.identity.models import Profile, SessionRefresh, User
from shared.db import get_session
from tests.test_session_router import UA, _login


@pytest.fixture
async def api(
    db_session: AsyncSession, otp_redis: object
) -> AsyncIterator[tuple[httpx.AsyncClient, AsyncSession]]:
    app = create_app()

    async def _session_override() -> AsyncIterator[AsyncSession]:
        yield db_session

    app.dependency_overrides[get_session] = _session_override
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(
        transport=transport, base_url="https://id.test", headers=UA
    ) as client:
        yield client, db_session


async def test_devices_list_marks_current(api: tuple[httpx.AsyncClient, AsyncSession]) -> None:
    http, session = api
    await _login(http, session)
    response = await http.get("/auth/devices")
    assert response.status_code == 200
    body = response.json()
    assert len(body["items"]) == 1
    device = body["items"][0]
    assert device["current"] is True and device["kind"] == "web"
    assert set(device) >= {"device_id", "kind", "label", "current", "created_at"}


async def test_device_label_and_revoke_other(
    api: tuple[httpx.AsyncClient, AsyncSession],
) -> None:
    http, session = api
    await _login(http, session)
    first_id = (await http.get("/auth/devices")).json()["items"][0]["device_id"]
    await _login(http, session)  # second session; cookie jar now holds session 2

    labelled = await http.post(
        "/auth/devices/label", json={"device_id": first_id, "kind": "web", "label": "Old laptop"}
    )
    assert labelled.status_code == 200
    items = (await http.get("/auth/devices")).json()["items"]
    assert {"Old laptop"} <= {item["label"] for item in items}

    revoked = await http.post("/auth/devices/revoke", json={"device_id": first_id, "kind": "web"})
    assert revoked.status_code == 200
    items = (await http.get("/auth/devices")).json()["items"]
    assert len(items) == 1 and items[0]["current"] is True  # only session 2 left


async def test_revoke_rejects_foreign_and_garbage_ids(
    api: tuple[httpx.AsyncClient, AsyncSession],
) -> None:
    http, session = api
    await _login(http, session)
    response = await http.post(
        "/auth/devices/revoke", json={"device_id": "not-a-uuid", "kind": "web"}
    )
    assert response.status_code == 404
    response = await http.post(
        "/auth/devices/revoke",
        json={"device_id": "01890000-0000-7000-8000-000000000000", "kind": "web"},
    )
    assert response.status_code == 404


async def test_handle_check_suggest_and_set(api: tuple[httpx.AsyncClient, AsyncSession]) -> None:
    http, session = api
    await _login(http, session)

    check = await http.get("/auth/handle/check", params={"h": "good_farmer"})
    assert check.json() == {"ok": True, "code": None}
    assert (await http.get("/auth/handle/check", params={"h": "ab"})).json()["code"] == "invalid_format"
    assert (await http.get("/auth/handle/check", params={"h": "admin"})).json()["code"] == "reserved"

    suggest = await http.get("/auth/handle/suggest")
    suggestions = suggest.json()["suggestions"]
    assert len(suggestions) == 3 and all("_" in s for s in suggestions)

    taken = await http.post("/auth/handle", json={"handle": "good_farmer"})
    assert taken.status_code == 200
    assert taken.json()["agri_id"] == "good_farmer"
    user = (await session.scalars(select(User))).one()
    assert user.agri_id == "good_farmer" and user.agri_id_changed_once is True

    again = await http.post("/auth/handle", json={"handle": "second_pick"})
    assert again.status_code == 409  # one free change ever
    assert again.json()["detail"] == "already_changed"


async def test_handle_conflict_is_409_taken(api: tuple[httpx.AsyncClient, AsyncSession]) -> None:
    http, session = api
    await _login(http, session, phone="+919876540001")
    assert (await http.post("/auth/handle", json={"handle": "unique_name"})).status_code == 200
    await _login(http, session, phone="+919876540002")
    response = await http.post("/auth/handle", json={"handle": "unique_name"})
    assert response.status_code == 409
    assert response.json()["detail"] == "taken"


async def test_language_upserts_profile(api: tuple[httpx.AsyncClient, AsyncSession]) -> None:
    http, session = api
    await _login(http, session)
    assert (await http.post("/auth/language", json={"language": "ta"})).status_code == 200
    profile = (await session.scalars(select(Profile))).one()
    assert profile.language == "ta"
    assert (await http.get("/auth/me")).json()["language"] == "ta"
    assert (await http.post("/auth/language", json={"language": "xx"})).status_code == 422
```

- [ ] **Step 2: Run to verify failure**

Run: `.venv\Scripts\pytest.exe tests/test_session_router.py tests/test_devices_router.py -q`
Expected: FAIL — 404s (`/auth/login` etc. do not exist).

- [ ] **Step 3: Implement `session_router.py`**

```python
"""id.agri.in session endpoints (D09.A/C/D backend).

/auth/login is the module's only new public route (declared in
public_routes.txt); everything else rides require_auth's session cookie.
Per module rules nothing here logs bodies or query strings - login bodies
carry proofs, handle checks ride the query string.

Cookie discipline (non-negotiable 2): agri_sid is httpOnly + Secure +
SameSite=Lax and HOST-ONLY (no Domain attribute) - the session exists on
id.agri.in and nowhere else. Fixation: login always mints a fresh sid.
"""

import uuid
from datetime import datetime
from typing import Annotated, Literal

from fastapi import Depends, HTTPException, Request, Response
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from modules.identity.handles import HandleError, can_change_handle, validate_handle
from modules.identity.models import HandleHistory, Profile, SessionRefresh, SessionWeb, User
from modules.identity.otp_service import consume_otp_proof
from modules.identity.refresh_service import revoke_families_for_device, revoke_family
from modules.identity.schemas import IdentityPublicSchema
from modules.identity.service import assign_role, create_user, get_by_phone
from modules.identity.session_auth import PrincipalDep
from modules.identity.session_limits import (
    DEVICE_LABEL_MAX_CHARS,
    SESSION_COOKIE_NAME,
    WEB_SESSION_TTL_SECONDS,
)
from modules.identity.session_service import (
    create_web_session,
    device_fingerprint,
    revoke_everything,
    revoke_web_session,
)
from shared.db import get_session
from shared.pagination import Page, paginate
from shared.security import SecureRouter
from shared.telemetry import get_logger

logger = get_logger(__name__)

session_router = SecureRouter(prefix="/auth", tags=["auth-session"])

SessionDep = Annotated[AsyncSession, Depends(get_session)]

AG_FALLBACK_PREFIX = "AG-"


def _fingerprint(request: Request) -> str:
    return device_fingerprint(
        request.headers.get("user-agent"), request.headers.get("sec-ch-ua-platform")
    )


def _set_session_cookie(response: Response, sid: str) -> None:
    response.set_cookie(
        SESSION_COOKIE_NAME,
        sid,
        max_age=WEB_SESSION_TTL_SECONDS,
        httponly=True,
        secure=True,
        samesite="lax",
        path="/",
        # no domain= on purpose: host-only, id.agri.in and nowhere else
    )


def _clear_session_cookie(response: Response) -> None:
    response.delete_cookie(SESSION_COOKIE_NAME, path="/", httponly=True, secure=True)


async def _language_for(session: AsyncSession, user_id: uuid.UUID) -> str:
    profile = await session.scalar(select(Profile).where(Profile.user_id == user_id))
    return profile.language if profile is not None else "en"


class LoginIn(BaseModel):
    otp_proof: str
    device_label: str | None = Field(default=None, max_length=DEVICE_LABEL_MAX_CHARS)


class LoginOut(IdentityPublicSchema):
    status: Literal["ok"] = "ok"
    is_new_user: bool
    agri_id: str
    handle_is_fallback: bool
    language: str


@session_router.post("/login", public=True)
async def login(
    body: LoginIn, request: Request, response: Response, session: SessionDep
) -> LoginOut:
    """OTP-proof -> id.agri.in session. New phones become accounts here.

    FastAPI pattern note: cookies are set on the INJECTED response parameter
    while the handler still returns the Pydantic model - never construct a
    Response manually here.
    """
    redeemed = await consume_otp_proof(body.otp_proof)
    if redeemed is None or redeemed[1] != "login":
        raise HTTPException(status_code=400, detail="invalid_or_expired_proof")
    phone = redeemed[0]
    user = await get_by_phone(session, phone)
    is_new_user = user is None
    if user is None:
        user = await create_user(session, phone)
        await assign_role(session, user.id, "user")
        user.phone_verified_at = datetime.now(UTC)
        await session.flush()
    if user.status != "active":
        # the proof is already burned (GETDEL) - nothing to roll back
        raise HTTPException(status_code=403, detail="account_unavailable")
    sid = await create_web_session(
        session,
        user_id=user.id,
        fingerprint=_fingerprint(request),
        ip=request.client.host if request.client else None,
        device_label=body.device_label,
    )
    _set_session_cookie(response, sid)
    return LoginOut(
        is_new_user=is_new_user,
        agri_id=user.agri_id,
        handle_is_fallback=user.agri_id.startswith(AG_FALLBACK_PREFIX)
        and not user.agri_id_changed_once,
        language=await _language_for(session, user.id),
    )
```

(imports for this handler include `from datetime import UTC, datetime`)

Continue with the remaining endpoints:

```python
class StatusOut(BaseModel):
    status: Literal["ok"] = "ok"


@session_router.post("/logout")
async def logout(
    principal: PrincipalDep, request: Request, response: Response, session: SessionDep
) -> StatusOut:
    """This device only: web session + refresh families minted from it."""
    await revoke_web_session(session, session_id=principal.session_id, user_id=principal.user_id)
    if principal.fingerprint:
        await revoke_families_for_device(
            session, user_id=principal.user_id, fingerprint=principal.fingerprint
        )
    _clear_session_cookie(response)
    return StatusOut()


@session_router.post("/logout-everywhere")
async def logout_everywhere(
    principal: PrincipalDep, response: Response, session: SessionDep
) -> StatusOut:
    """Every session + every refresh family, one request cycle (non-negotiable 3)."""
    await revoke_everything(session, principal.user_id)
    _clear_session_cookie(response)
    return StatusOut()


class MeOut(IdentityPublicSchema):
    agri_id: str
    handle_is_fallback: bool
    can_change_handle: bool
    language: str


@session_router.get("/me")
async def me(principal: PrincipalDep, session: SessionDep) -> MeOut:
    user = await session.scalar(select(User).where(User.id == principal.user_id))
    assert user is not None  # resolve_web_session proved existence this request
    return MeOut(
        agri_id=user.agri_id,
        handle_is_fallback=user.agri_id.startswith(AG_FALLBACK_PREFIX)
        and not user.agri_id_changed_once,
        can_change_handle=can_change_handle(user.agri_id_changed_once),
        language=await _language_for(session, user.id),
    )
```

Handle endpoints:

```python
class HandleIn(BaseModel):
    handle: str


class HandleOut(IdentityPublicSchema):
    agri_id: str


@session_router.post("/handle")
async def set_handle(body: HandleIn, principal: PrincipalDep, session: SessionDep) -> HandleOut:
    """The one free change (D06.B). Signup's pick from the AG- fallback IS the
    change - the flag model has no second dimension, deliberately."""
    try:
        handle = validate_handle(body.handle)
    except HandleError as exc:
        raise HTTPException(status_code=409, detail=exc.code) from exc
    user = await session.scalar(select(User).where(User.id == principal.user_id))
    assert user is not None
    if not can_change_handle(user.agri_id_changed_once):
        raise HTTPException(status_code=409, detail="already_changed")
    old = user.agri_id
    user.agri_id = handle
    user.agri_id_changed_once = True
    session.add(HandleHistory(user_id=user.id, old_agri_id=old, new_agri_id=handle))
    try:
        await session.flush()
    except IntegrityError as exc:
        await session.rollback()
        raise HTTPException(status_code=409, detail="taken") from exc
    return HandleOut(agri_id=handle)


class HandleCheckOut(BaseModel):
    ok: bool
    code: str | None = None


@session_router.get("/handle/check")
async def check_handle(h: str, principal: PrincipalDep, session: SessionDep) -> HandleCheckOut:
    try:
        handle = validate_handle(h)
    except HandleError as exc:
        return HandleCheckOut(ok=False, code=exc.code)
    existing = await session.scalar(select(User.agri_id).where(User.agri_id == handle))
    if existing is not None:
        return HandleCheckOut(ok=False, code="taken")
    return HandleCheckOut(ok=True)


class HandleSuggestOut(BaseModel):
    suggestions: list[str]


_ADJECTIVES = ("green", "sunny", "golden", "fresh", "happy", "bright", "calm", "brave")
_NOUNS = ("farmer", "harvest", "fields", "valley", "sprout", "garden", "grove", "meadow")


@session_router.get("/handle/suggest")
async def suggest_handles(principal: PrincipalDep, session: SessionDep) -> HandleSuggestOut:
    """Wordlist combos, availability-checked in one query. Nothing personal
    goes into a suggestion (no phone digits, no name)."""
    import secrets as _secrets

    candidates: list[str] = []
    while len(candidates) < 12:
        name = (
            f"{_secrets.choice(_ADJECTIVES)}_{_secrets.choice(_NOUNS)}"
            f"{_secrets.randbelow(90) + 10}"
        )
        if name not in candidates:
            candidates.append(name)
    taken = set(
        await session.scalars(select(User.agri_id).where(User.agri_id.in_(candidates)))
    )
    available = [name for name in candidates if name not in taken]
    return HandleSuggestOut(suggestions=available[:3])


class LanguageIn(BaseModel):
    language: Literal["en", "ta", "hi"]


@session_router.post("/language")
async def set_language(
    body: LanguageIn, principal: PrincipalDep, session: SessionDep
) -> StatusOut:
    profile = await session.scalar(select(Profile).where(Profile.user_id == principal.user_id))
    if profile is None:
        session.add(Profile(user_id=principal.user_id, language=body.language))
    else:
        profile.language = body.language
    await session.flush()
    return StatusOut()
```

Devices endpoints (cursor-paginated per the all-lists rule; two kinds merged client-side is banned by keyset pagination, so web sessions and refresh families are ONE list via two paginated sub-queries — keep it simple: paginate the web sessions, and append active refresh families as devices of `kind == client_id` on the FIRST page only, documented in the response model):

Simpler and still honest to the rule: paginate over `SessionWeb` (the only unbounded set — one row per login) and attach app refresh families (bounded: ≤ clients × devices) grouped by fingerprint into each web device row? NO — keep flat and boring:

```python
class DeviceOut(IdentityPublicSchema):
    device_id: str  # stringified row id of sessions_web / sessions_refresh ROOT
    kind: str  # "web" or the oauth client_id ("web-agri", ...)
    label: str | None
    current: bool
    created_at: datetime
    last_seen_at: datetime | None


class DevicesOut(BaseModel):
    items: list[DeviceOut]
    next_cursor: str | None


@session_router.get("/devices")
async def list_devices(
    principal: PrincipalDep,
    session: SessionDep,
    cursor: str | None = None,
    limit: int = 20,
) -> DevicesOut:
    """Active web sessions, keyset-paginated; each device's app refresh
    families are folded into its row via matching fingerprint (kind column
    shows which). Standalone refresh families (minted by a device whose web
    session is gone) surface on the first page after the web rows."""
    now = datetime.now(UTC)
    page: Page[SessionWeb] = await paginate(
        session,
        select(SessionWeb).where(
            SessionWeb.user_id == principal.user_id,
            SessionWeb.revoked_at.is_(None),
            SessionWeb.expires_at > now,
        ),
        cursor=cursor,
        limit=limit,
    )
    items = [
        DeviceOut(
            device_id=str(row.id),
            kind="web",
            label=row.device_label,
            current=row.id == principal.session_id,
            created_at=row.created_at,
            last_seen_at=row.last_seen_at,
        )
        for row in page.items
    ]
    if cursor is None:
        client_name = OAuthClient.client_id
        family_rows = (
            await session.execute(
                select(SessionRefresh, client_name)
                .join(OAuthClient, OAuthClient.id == SessionRefresh.client_id)
                .where(
                    SessionRefresh.user_id == principal.user_id,
                    SessionRefresh.revoked_at.is_(None),
                    SessionRefresh.expires_at > now,
                )
                .order_by(SessionRefresh.id)
            )
        ).all()
        items.extend(
            DeviceOut(
                device_id=str(refresh.id),
                kind=client_id,
                label=refresh.device_label,
                current=False,
                created_at=refresh.created_at,
                last_seen_at=refresh.last_used_at,
            )
            for refresh, client_id in family_rows
        )
    return DevicesOut(items=items, next_cursor=page.next_cursor)
```

(add `OAuthClient` to the models import; `from datetime import UTC, datetime`)

```python
class DeviceActionIn(BaseModel):
    device_id: str
    kind: str


def _parse_device_id(raw: str) -> uuid.UUID:
    try:
        return uuid.UUID(raw)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail="unknown_device") from exc


@session_router.post("/devices/revoke")
async def revoke_device(
    body: DeviceActionIn, principal: PrincipalDep, response: Response, session: SessionDep
) -> StatusOut:
    row_id = _parse_device_id(body.device_id)
    if body.kind == "web":
        target = await session.scalar(
            select(SessionWeb).where(
                SessionWeb.id == row_id, SessionWeb.user_id == principal.user_id
            )
        )
        if target is None:
            raise HTTPException(status_code=404, detail="unknown_device")
        await revoke_web_session(session, session_id=row_id, user_id=principal.user_id)
        if target.device_fingerprint:
            await revoke_families_for_device(
                session, user_id=principal.user_id, fingerprint=target.device_fingerprint
            )
        if row_id == principal.session_id:
            _clear_session_cookie(response)  # self-revoke == logout
        return StatusOut()
    refresh = await session.scalar(
        select(SessionRefresh).where(
            SessionRefresh.id == row_id, SessionRefresh.user_id == principal.user_id
        )
    )
    if refresh is None:
        raise HTTPException(status_code=404, detail="unknown_device")
    await revoke_family(session, refresh.family_id)
    return StatusOut()


class DeviceLabelIn(DeviceActionIn):
    label: str = Field(min_length=1, max_length=DEVICE_LABEL_MAX_CHARS)


@session_router.post("/devices/label")
async def label_device(
    body: DeviceLabelIn, principal: PrincipalDep, session: SessionDep
) -> StatusOut:
    row_id = _parse_device_id(body.device_id)
    model = SessionWeb if body.kind == "web" else SessionRefresh
    row = await session.scalar(
        select(model).where(model.id == row_id, model.user_id == principal.user_id)
    )
    if row is None:
        raise HTTPException(status_code=404, detail="unknown_device")
    row.device_label = body.label
    await session.flush()
    return StatusOut()
```

- [ ] **Step 4: Mount + declare public route**

`main.py`: `from modules.identity.session_router import session_router as identity_session_router` and add `identity_session_router` to `MODULE_ROUTERS` (after `identity_otp_router`).

`public_routes.txt`: add `/auth/login` (keep the file's ordering — after `/auth/otp/verify`).

- [ ] **Step 5: Run tests to verify pass**

Run: `.venv\Scripts\pytest.exe tests/test_session_router.py tests/test_devices_router.py -q`
Expected: PASS. Then `.venv\Scripts\python.exe scripts\dump_public_routes.py --check` — must be clean.

- [ ] **Step 6: Full backend suite + lints, commit**

Run: `.venv\Scripts\pytest.exe -q && .venv\Scripts\ruff.exe format --check . && .venv\Scripts\ruff.exe check . && .venv\Scripts\mypy.exe . && .venv\Scripts\lint-imports.exe`

```bash
git add backend/core/modules/identity/session_router.py backend/core/main.py backend/core/public_routes.txt backend/core/tests/test_session_router.py backend/core/tests/test_devices_router.py
git commit -m "feat(d09): login, logout, devices, handle and language endpoints"
```

### Task 7: /authorize — session check, code mint, login resume

**Files:**
- Modify: `backend/core/modules/identity/oauth_router.py` (`authorize()` + module docstring)
- Modify: `backend/core/tests/test_oauth_flow.py` (`test_full_code_flow_with_pkce` step 1, `test_authorize_missing_state_rejected` untouched — verify)
- Test: `backend/core/tests/test_authorize_session.py`

**Interfaces:**
- Consumes: `resolve_web_session`, `SESSION_COOKIE_NAME`, `create_authorization_code` (exact call: `create_authorization_code(session, user_id=..., client=..., redirect_uri=..., code_challenge=...)`).
- Produces: `/authorize` with a valid session → 302 `{redirect_uri}?code=...&state=...`; without → 302 relative `/login?next=<urlencoded /authorize path+query>` (relative Location keeps the login UI same-origin behind the web-id rewrite in dev AND prod, and is not an open-redirect surface).

- [ ] **Step 1: Write the failing tests**

Create `tests/test_authorize_session.py`:

```python
"""D09.A: /authorize consults the id.agri.in session - mints a code when
present, parks the request at /login?next= when absent."""

from urllib.parse import parse_qs, quote, unquote, urlsplit

import httpx
from sqlalchemy.ext.asyncio import AsyncSession

from tests.test_oauth_flow import REDIRECT, _authorize_params, _exchange, _pkce, api  # noqa: F401
from tests.test_session_router import UA, _login


async def test_authorize_without_session_redirects_to_login_resume(
    api: tuple[httpx.AsyncClient, AsyncSession],
) -> None:
    http, _ = api
    _, challenge = _pkce()
    response = await http.get("/authorize", params=_authorize_params(challenge))
    assert response.status_code == 302
    location = response.headers["location"]
    assert location.startswith("/login?next=")  # RELATIVE - never an absolute foreign URL
    resumed = unquote(location.removeprefix("/login?next="))
    assert resumed.startswith("/authorize?")
    assert "state=state-xyz" in resumed


async def test_authorize_with_session_mints_code(
    api: tuple[httpx.AsyncClient, AsyncSession],
) -> None:
    http, session = api
    verifier, challenge = _pkce()
    login = await _login(http, session)  # sets agri_sid in the client jar
    assert login.status_code == 200

    response = await http.get("/authorize", params=_authorize_params(challenge))
    assert response.status_code == 302
    location = response.headers["location"]
    assert location.startswith(REDIRECT + "?")
    query = parse_qs(urlsplit(location).query)
    assert query["state"] == ["state-xyz"]
    code = query["code"][0]

    exchange = await _exchange(http, code, verifier)
    assert exchange.status_code == 200
    assert exchange.json()["refresh_token"]


async def test_authorize_with_session_still_validates_pkce_and_client(
    api: tuple[httpx.AsyncClient, AsyncSession],
) -> None:
    http, session = api
    _, challenge = _pkce()
    await _login(http, session)
    # missing challenge: error redirect, NO code minted despite the session
    bad = await http.get("/authorize", params=_authorize_params(challenge, code_challenge=""))
    query = parse_qs(urlsplit(bad.headers["location"]).query)
    assert query["error"] == ["invalid_request"] and "code" not in query
    # unknown client: 400 JSON, no redirect, session irrelevant
    evil = await http.get(
        "/authorize", params=_authorize_params(challenge, client_id="evil-app")
    )
    assert evil.status_code == 400 and "location" not in evil.headers


async def test_authorize_suspended_session_parks_at_login(
    api: tuple[httpx.AsyncClient, AsyncSession],
) -> None:
    from sqlalchemy import select

    from modules.identity.models import User

    http, session = api
    _, challenge = _pkce()
    await _login(http, session)
    user = (await session.scalars(select(User))).one()
    user.status = "suspended"
    await session.flush()
    response = await http.get("/authorize", params=_authorize_params(challenge))
    assert response.headers["location"].startswith("/login?next=")  # instant deny
```

The `api` fixture in `test_oauth_flow.py` doesn't send UA headers or use `otp_redis`; the imports above reuse it, so `_login` needs those — **adapt**: give `test_authorize_session.py` its own `api` fixture copying the `test_session_router.py` one (app + db override + `base_url="https://id.test"` + `headers=UA` + `otp_redis` param). Delete the `# noqa` import of the flow fixture if unused after that.

And in `tests/test_oauth_flow.py::test_full_code_flow_with_pkce`, replace step 1:

```python
    # step 1: a valid /authorize with no session parks at the login resume (D09)
    authorize = await http.get("/authorize", params=_authorize_params(challenge))
    assert authorize.status_code == 302
    assert authorize.headers["location"].startswith("/login?next=")
```

(the old `error=login_required` assertions go away; `_location_query` stays for the error-path tests).

- [ ] **Step 2: Run to verify failure**

Run: `.venv\Scripts\pytest.exe tests/test_authorize_session.py tests/test_oauth_flow.py -q`
Expected: new file FAILS (still `error=login_required` behavior), flow test FAILS on step 1.

- [ ] **Step 3: Rewrite `authorize()` in `oauth_router.py`**

```python
@oauth_router.get("/authorize", public=True)
async def authorize(request: Request, session: SessionDep) -> Response:
    """Validate, then consult the id.agri.in session (D09).

    Order matters: authlib validates client_id + exact redirect_uri before any
    redirecting error can exist, then PKCE (S256 required), then our
    state-required rule. Only a fully valid request gets to see the session:
    - session present and active -> mint a one-time code, 302 to the client.
    - no session (or suspended)  -> 302 to the RELATIVE login resume; the
      next value is this request's own path+query, so it can never point
      anywhere but back here.
    """
    params = {key: request.query_params[key] for key in request.query_params}
    datalist = {key: request.query_params.getlist(key) for key in request.query_params}
    ctx = await _client_context(session, params.get("client_id"))
    server = AgriAuthorizationServer(ctx)
    try:
        oauth2_request = build_oauth2_request("GET", str(request.url), params, datalist)
        grant = server.get_consent_grant(request=oauth2_request, end_user=None)
        if not params.get("state"):
            raise InvalidRequestError(
                "Missing 'state' in request.", redirect_uri=grant.redirect_uri
            )
    except OAuth2Error as error:
        return server.handle_response(*error(None))

    sid = request.cookies.get(SESSION_COOKIE_NAME)
    principal = await resolve_web_session(session, sid) if sid else None
    if principal is None:
        resume = f"{request.url.path}?{request.url.query}"
        return RedirectResponse(f"/login?next={quote(resume, safe='')}", status_code=302)
    assert ctx.client is not None  # get_consent_grant validated it
    code = await create_authorization_code(
        session,
        user_id=principal.user_id,
        client=ctx.client.row,
        redirect_uri=grant.redirect_uri,
        code_challenge=params["code_challenge"],
    )
    return RedirectResponse(
        f"{grant.redirect_uri}?code={quote(code, safe='')}&state={quote(params['state'], safe='')}",
        status_code=302,
    )
```

New imports: `from urllib.parse import quote`, `from starlette.responses import RedirectResponse` (extend the existing starlette import), `from modules.identity.oauth_service import create_authorization_code` (extend existing), `from modules.identity.session_limits import SESSION_COOKIE_NAME`, `from modules.identity.session_service import resolve_web_session`. Update the module docstring paragraph ("Until D09 lands…") to describe the real behavior.

- [ ] **Step 4: Run tests to verify pass**

Run: `.venv\Scripts\pytest.exe tests/test_authorize_session.py tests/test_oauth_flow.py -q`
Expected: PASS (all authorize error-path tests still green — errors raise inside the try block exactly as before).

- [ ] **Step 5: Commit**

```bash
git add backend/core/modules/identity/oauth_router.py backend/core/tests/test_authorize_session.py backend/core/tests/test_oauth_flow.py
git commit -m "feat(d09): authorize consults the web session and resumes login"
```

---

### Task 8: Flag-gated OTP peek route (E2E enabler)

**Files:**
- Modify: `backend/core/settings.py`, `backend/core/modules/identity/router.py`, `backend/core/main.py`
- Test: `backend/core/tests/test_otp_peek.py`

**Interfaces:**
- Produces: `GET /auth/otp/_peek?phone=` → `{code: str | None}` — mounted ONLY when `settings.otp_test_peek and settings.app_env != "prod"` (mirrors the msg91 webhook pattern: default builds expose exactly the routes in public_routes.txt; the peek route is never declared there because default settings never mount it). Playwright reads OTP codes through this instead of scraping uvicorn stdout.

- [ ] **Step 1: Write the failing test**

`backend/core/tests/test_otp_peek.py`:

```python
"""The E2E peek route exists ONLY behind the flag and never in prod."""

from collections.abc import AsyncIterator

import httpx
import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from main import create_app
from modules.identity.otp_service import issue_otp
from settings import get_settings
from shared.db import get_session

PHONE = "+919876550001"


@pytest.fixture
async def make_api(db_session: AsyncSession):  # type: ignore[no-untyped-def]
    async def _make() -> httpx.AsyncClient:
        app = create_app()

        async def _session_override() -> AsyncIterator[AsyncSession]:
            yield db_session

        app.dependency_overrides[get_session] = _session_override
        return httpx.AsyncClient(
            transport=httpx.ASGITransport(app=app), base_url="https://id.test"
        )

    return _make


async def test_peek_absent_by_default(make_api, otp_redis: object) -> None:  # type: ignore[no-untyped-def]
    async with await make_api() as http:
        assert (await http.get("/auth/otp/_peek", params={"phone": PHONE})).status_code == 404


async def test_peek_returns_last_code_when_flagged(
    make_api, db_session: AsyncSession, otp_redis: object, monkeypatch: pytest.MonkeyPatch
) -> None:  # type: ignore[no-untyped-def]
    monkeypatch.setenv("OTP_TEST_PEEK", "true")
    get_settings.cache_clear()
    async with await make_api() as http:
        await issue_otp(db_session, phone=PHONE, purpose="login", ip=None, device_fingerprint=None)
        response = await http.get("/auth/otp/_peek", params={"phone": PHONE})
        assert response.status_code == 200
        code = response.json()["code"]
        assert code is not None and len(code) == 6


async def test_peek_never_mounts_in_prod(
    make_api, monkeypatch: pytest.MonkeyPatch, otp_redis: object
) -> None:  # type: ignore[no-untyped-def]
    monkeypatch.setenv("OTP_TEST_PEEK", "true")
    monkeypatch.setenv("APP_ENV", "prod")
    monkeypatch.setenv("OAUTH_JWT_PRIVATE_KEY_PEM", "")  # keep prod boot semantics out of scope
    get_settings.cache_clear()
    async with await make_api() as http:
        assert (await http.get("/auth/otp/_peek", params={"phone": PHONE})).status_code == 404
```

(If `create_app()` in prod mode trips the fail-at-boot signing-key check inside `lifespan` — lifespan doesn't run under bare ASGITransport unless the client enters it, so the 404 assertion works; if it does trip, generate an ephemeral key via the same helper `oauth_keys` tests use.)

- [ ] **Step 2: Run to verify failure**

Run: `.venv\Scripts\pytest.exe tests/test_otp_peek.py -q`
Expected: `test_peek_returns_last_code_when_flagged` FAILS with 404.

- [ ] **Step 3: Implement**

`settings.py` — after `sms_provider` block:

```python
    # E2E-only escape hatch (D09): mounts GET /auth/otp/_peek returning the
    # mock driver's last code so Playwright can log in across processes.
    # Never on in prod: main.create_app() refuses to mount it there.
    otp_test_peek: bool = False
```

`modules/identity/router.py` — after `msg91_webhook_router()`:

```python
class OtpPeekOut(BaseModel):
    code: str | None


def otp_test_peek_router() -> SecureRouter:
    """E2E peek at the mock outbox, mounted by main.create_app() ONLY when
    settings.otp_test_peek is set outside prod. Same doctrine as the msg91
    webhook: default builds expose exactly the public_routes.txt surface."""
    from modules.identity.otp_drivers import MockDriver

    peek = SecureRouter(prefix="/auth/otp", tags=["auth-otp"])

    @peek.get("/_peek", public=True)
    async def otp_peek(phone: str) -> OtpPeekOut:
        return OtpPeekOut(code=MockDriver.last_code(normalize_phone(phone)))

    return peek
```

`main.py` — next to the msg91 mount inside `create_app()`:

```python
    if get_settings().otp_test_peek and get_settings().app_env != "prod":
        routers.append(otp_test_peek_router())
```

with `from modules.identity.router import otp_test_peek_router` added to the existing import block.

- [ ] **Step 4: Run tests to verify pass**

Run: `.venv\Scripts\pytest.exe tests/test_otp_peek.py -q` then full `.venv\Scripts\pytest.exe -q` and `.venv\Scripts\python.exe scripts\dump_public_routes.py --check` (must stay clean — flag defaults off).

- [ ] **Step 5: Commit**

```bash
git add backend/core/settings.py backend/core/modules/identity/router.py backend/core/main.py backend/core/tests/test_otp_peek.py
git commit -m "feat(d09): flag-gated otp peek route for e2e login"
```

### Task 9: packages/ui — OtpInput, CategoryTile button mode, auth i18n

**Files:**
- Create: `packages/ui/src/lib/otp.ts`, `packages/ui/src/lib/otp.test.ts`, `packages/ui/src/components/otp-input.tsx`
- Modify: `packages/ui/src/components/category-tile.tsx`, `packages/ui/src/index.ts`, `packages/ui/src/i18n/messages/en.json`, `ta.json`, `hi.json`

**Interfaces:**
- Produces:
  - `applyOtpInput(current: string, index: number, raw: string, length: number): { value: string; focusIndex: number }` (pure, unit-tested)
  - `<OtpInput length={6} value onChange onComplete label disabled? error? className?>` — client component, segmented boxes ≥44px, auto-advance, backspace-back, paste-distribute
  - `CategoryTile` accepts `href?: string; onClick?: () => void; selected?: boolean` (renders `<button>` when no href) — existing `<a>` call sites unaffected
  - messages: `ui.auth.*` in all three catalogs (keys below — web-id consumes via `useTranslations("ui.auth")`)

- [ ] **Step 1: Write the failing unit test**

`packages/ui/src/lib/otp.test.ts`:

```ts
import { describe, expect, it } from "vitest";

import { applyOtpInput } from "./otp";

describe("applyOtpInput", () => {
  it("types one digit and advances", () => {
    expect(applyOtpInput("", 0, "4", 6)).toEqual({ value: "4", focusIndex: 1 });
    expect(applyOtpInput("41", 2, "7", 6)).toEqual({ value: "417", focusIndex: 3 });
  });
  it("overwrites an existing digit", () => {
    expect(applyOtpInput("123456", 2, "9", 6)).toEqual({ value: "129456", focusIndex: 3 });
  });
  it("ignores non-digits", () => {
    expect(applyOtpInput("12", 2, "x", 6)).toEqual({ value: "12", focusIndex: 2 });
  });
  it("distributes a pasted code from any index", () => {
    expect(applyOtpInput("", 3, "123456", 6)).toEqual({ value: "123456", focusIndex: 5 });
    expect(applyOtpInput("99", 2, "1234", 6)).toEqual({ value: "991234", focusIndex: 5 });
  });
  it("strips separators from pasted text and clamps to length", () => {
    expect(applyOtpInput("", 0, "123-456-789", 6)).toEqual({ value: "123456", focusIndex: 5 });
  });
  it("stays on the last box when full", () => {
    expect(applyOtpInput("12345", 5, "6", 6)).toEqual({ value: "123456", focusIndex: 5 });
  });
});
```

- [ ] **Step 2: Run to verify failure**

Run: `pnpm --filter @agri/ui test` (vitest — same task the `web` CI job runs)
Expected: FAIL — `Cannot find module './otp'`.

- [ ] **Step 3: Implement `packages/ui/src/lib/otp.ts`**

```ts
/**
 * Pure OTP-box state transition: given the current value, the box index the
 * user typed into, and the raw input (a keystroke or a paste), return the
 * next value and which box should hold focus. Kept out of the component so
 * the auto-advance/paste rules are unit-testable without a DOM.
 */
export function applyOtpInput(
  current: string,
  index: number,
  raw: string,
  length: number,
): { value: string; focusIndex: number } {
  const digits = raw.replace(/\D/g, "");
  if (!digits) return { value: current, focusIndex: index };
  const chars = current.padEnd(index, " ").split("");
  let cursor = index;
  for (const digit of digits) {
    if (cursor >= length) break;
    chars[cursor] = digit;
    cursor += 1;
  }
  const value = chars.join("").replace(/\s+$/, "").slice(0, length);
  return { value, focusIndex: Math.min(cursor, length - 1) };
}
```

- [ ] **Step 4: Run unit test to verify pass**

Run: `pnpm --filter @agri/ui test` — Expected: PASS.

- [ ] **Step 5: Implement `packages/ui/src/components/otp-input.tsx`**

```tsx
"use client";

import { useEffect, useRef } from "react";

import { applyOtpInput } from "../lib/otp";
import { cn } from "../lib/cn";

export interface OtpInputProps {
  value: string;
  onChange: (value: string) => void;
  onComplete?: (value: string) => void;
  label: string;
  length?: number;
  disabled?: boolean;
  error?: boolean;
  className?: string;
}

/**
 * PincodeInput-style OTP boxes (D09): the same white 16px container +
 * 18px/700 numeric type, split into single-digit auto-advance boxes.
 * Every box is a 48px square (≥44px touch target). Focus ring comes from
 * the global token rule; error state borders with --alert-line.
 */
export function OtpInput({
  value,
  onChange,
  onComplete,
  label,
  length = 6,
  disabled = false,
  error = false,
  className,
}: OtpInputProps) {
  const refs = useRef<Array<HTMLInputElement | null>>([]);
  const completed = useRef<string | null>(null);

  useEffect(() => {
    if (value.length === length && completed.current !== value) {
      completed.current = value;
      onComplete?.(value);
    }
  }, [value, length, onComplete]);

  const handleInput = (index: number, raw: string) => {
    const next = applyOtpInput(value, index, raw, length);
    onChange(next.value);
    refs.current[next.focusIndex]?.focus();
  };

  const handleKeyDown = (index: number, event: React.KeyboardEvent<HTMLInputElement>) => {
    if (event.key === "Backspace" && !value[index] && index > 0) {
      event.preventDefault();
      onChange(value.slice(0, index - 1));
      refs.current[index - 1]?.focus();
    }
  };

  return (
    <div
      role="group"
      aria-label={label}
      className={cn(
        "mx-auto flex w-fit gap-1.5 rounded-card bg-card p-1.5 shadow-pin",
        className,
      )}
    >
      {Array.from({ length }, (_, index) => (
        <input
          key={index}
          ref={(node) => {
            refs.current[index] = node;
          }}
          type="text"
          inputMode="numeric"
          autoComplete={index === 0 ? "one-time-code" : "off"}
          aria-label={`${label} ${index + 1}/${length}`}
          value={value[index] ?? ""}
          disabled={disabled}
          onChange={(event) => handleInput(index, event.target.value)}
          onKeyDown={(event) => handleKeyDown(index, event)}
          onFocus={(event) => event.target.select()}
          className={cn(
            "h-12 w-11 rounded-btn border bg-transparent text-center text-lg font-bold text-ink",
            error ? "border-alert-line" : "border-line",
            "disabled:opacity-50",
          )}
        />
      ))}
    </div>
  );
}
```

Check the tailwind preset (`packages/config`) for the exact alert-border token class — design-system.md names `--alert-bg/line`; if the preset exposes it as `border-alert-line` use that, otherwise use the preset's actual name (grep `alert` in `packages/config/tailwind-preset.ts`). NO hex literals.

- [ ] **Step 6: CategoryTile button mode**

In `category-tile.tsx`, change the component signature and root element (keep `tintClass`, anatomy, classes identical):

```tsx
export function CategoryTile({
  icon,
  label,
  vernacular,
  tint,
  href,
  onClick,
  selected = false,
  className,
}: {
  icon: ReactNode;
  label: ReactNode;
  vernacular: ReactNode;
  tint: Tint;
  href?: string;
  onClick?: () => void;
  selected?: boolean;
  className?: string;
}) {
  const classes = cn(
    /* the component's existing root class string, unchanged */,
    selected && "ring-[3px] ring-accent",
    className,
  );
  const body = (
    <>{/* existing children markup, unchanged */}</>
  );
  if (href) {
    return (
      <a href={href} className={classes}>
        {body}
      </a>
    );
  }
  return (
    <button type="button" onClick={onClick} aria-pressed={selected} className={classes}>
      {body}
    </button>
  );
}
```

(Read the current file first and preserve its exact class strings/markup; only the wrapper element and the three new props change. `ring-accent` must be a real preset token — design-system.md: focus ring `3px solid --accent`; grep the preset for the accent ring/utility actually used elsewhere and reuse it.)

- [ ] **Step 7: Auth messages in all three catalogs**

Add inside the existing top-level `"ui"` object of `en.json` (sibling of `"lang"`):

```json
"auth": {
  "phone": {
    "title": "Sign in to AgriID",
    "subtitle": "One login for agri, milk and organic",
    "label": "Mobile number",
    "cta": "Send OTP",
    "invalid": "Enter a valid 10-digit mobile number"
  },
  "otp": {
    "title": "Enter the 6-digit code",
    "sentTo": "Code sent to {phone}",
    "verify": "Verify",
    "resend": "Resend code",
    "resendIn": "Resend in {seconds}s",
    "wrong": "That code didn't work — try again",
    "locked": "Too many attempts. Request a new code.",
    "inputLabel": "OTP digit"
  },
  "handle": {
    "title": "Pick your @handle",
    "subtitle": "Your public name across the family of apps",
    "placeholder": "your_handle",
    "available": "Available",
    "taken": "Already taken",
    "reserved": "This name is reserved",
    "invalidFormat": "4–20 characters: a–z, 0–9 and _",
    "suggestions": "Suggestions",
    "save": "Save handle",
    "skip": "Skip for now"
  },
  "language": {
    "title": "Choose your language",
    "continue": "Continue"
  },
  "devices": {
    "title": "Your devices",
    "current": "This device",
    "revoke": "Sign out",
    "revokeAll": "Sign out everywhere",
    "rename": "Rename",
    "renamePlaceholder": "e.g. Home laptop",
    "empty": "No other devices",
    "confirmRevoke": "Sign out this device?",
    "confirmRevokeAll": "Sign out of every device? All apps on all devices will be signed out.",
    "cancel": "Cancel",
    "revoked": "Device signed out",
    "logout": "Sign out"
  }
}
```

`ta.json` (same keys):

```json
"auth": {
  "phone": {
    "title": "AgriID-இல் உள்நுழையவும்",
    "subtitle": "அக்ரி, பால், ஆர்கானிக் — ஒரே உள்நுழைவு",
    "label": "மொபைல் எண்",
    "cta": "OTP அனுப்பவும்",
    "invalid": "சரியான 10-இலக்க மொபைல் எண்ணை உள்ளிடவும்"
  },
  "otp": {
    "title": "6-இலக்க குறியீட்டை உள்ளிடவும்",
    "sentTo": "{phone}-க்கு குறியீடு அனுப்பப்பட்டது",
    "verify": "சரிபார்க்கவும்",
    "resend": "மீண்டும் அனுப்பு",
    "resendIn": "{seconds} விநாடிகளில் மீண்டும் அனுப்பலாம்",
    "wrong": "குறியீடு தவறு — மீண்டும் முயற்சிக்கவும்",
    "locked": "அதிக முயற்சிகள். புதிய குறியீட்டைக் கேளுங்கள்.",
    "inputLabel": "OTP இலக்கம்"
  },
  "handle": {
    "title": "உங்கள் @handle-ஐத் தேர்வு செய்யவும்",
    "subtitle": "எல்லா ஆப்களிலும் உங்கள் பொதுப் பெயர்",
    "placeholder": "your_handle",
    "available": "கிடைக்கிறது",
    "taken": "ஏற்கனவே எடுக்கப்பட்டது",
    "reserved": "இந்தப் பெயர் ஒதுக்கப்பட்டது",
    "invalidFormat": "4–20 எழுத்துகள்: a–z, 0–9, _",
    "suggestions": "பரிந்துரைகள்",
    "save": "சேமிக்கவும்",
    "skip": "இப்போது வேண்டாம்"
  },
  "language": {
    "title": "உங்கள் மொழியைத் தேர்ந்தெடுக்கவும்",
    "continue": "தொடரவும்"
  },
  "devices": {
    "title": "உங்கள் சாதனங்கள்",
    "current": "இந்த சாதனம்",
    "revoke": "வெளியேறு",
    "revokeAll": "எல்லா இடங்களிலும் வெளியேறு",
    "rename": "பெயர் மாற்று",
    "renamePlaceholder": "உதா. வீட்டு லேப்டாப்",
    "empty": "வேறு சாதனங்கள் இல்லை",
    "confirmRevoke": "இந்த சாதனத்திலிருந்து வெளியேறவா?",
    "confirmRevokeAll": "எல்லா சாதனங்களிலிருந்தும் வெளியேறவா? எல்லா ஆப்களும் வெளியேற்றப்படும்.",
    "cancel": "ரத்து",
    "revoked": "சாதனம் வெளியேற்றப்பட்டது",
    "logout": "வெளியேறு"
  }
}
```

`hi.json` (same keys):

```json
"auth": {
  "phone": {
    "title": "AgriID में साइन इन करें",
    "subtitle": "एग्री, दूध और ऑर्गैनिक — एक ही लॉगिन",
    "label": "मोबाइल नंबर",
    "cta": "OTP भेजें",
    "invalid": "सही 10 अंकों का मोबाइल नंबर डालें"
  },
  "otp": {
    "title": "6 अंकों का कोड डालें",
    "sentTo": "{phone} पर कोड भेजा गया",
    "verify": "सत्यापित करें",
    "resend": "फिर से भेजें",
    "resendIn": "{seconds} सेकंड में फिर से भेजें",
    "wrong": "कोड गलत है — फिर कोशिश करें",
    "locked": "बहुत अधिक प्रयास। नया कोड मांगें।",
    "inputLabel": "OTP अंक"
  },
  "handle": {
    "title": "अपना @handle चुनें",
    "subtitle": "सभी ऐप्स में आपका सार्वजनिक नाम",
    "placeholder": "your_handle",
    "available": "उपलब्ध है",
    "taken": "पहले से लिया गया है",
    "reserved": "यह नाम आरक्षित है",
    "invalidFormat": "4–20 अक्षर: a–z, 0–9 और _",
    "suggestions": "सुझाव",
    "save": "सहेजें",
    "skip": "अभी नहीं"
  },
  "language": {
    "title": "अपनी भाषा चुनें",
    "continue": "जारी रखें"
  },
  "devices": {
    "title": "आपके डिवाइस",
    "current": "यह डिवाइस",
    "revoke": "साइन आउट",
    "revokeAll": "हर जगह से साइन आउट करें",
    "rename": "नाम बदलें",
    "renamePlaceholder": "जैसे: घर का लैपटॉप",
    "empty": "कोई अन्य डिवाइस नहीं",
    "confirmRevoke": "इस डिवाइस से साइन आउट करें?",
    "confirmRevokeAll": "हर डिवाइस से साइन आउट करें? सभी ऐप्स साइन आउट हो जाएँगे।",
    "cancel": "रद्द करें",
    "revoked": "डिवाइस साइन आउट हो गया",
    "logout": "साइन आउट"
  }
}
```

- [ ] **Step 8: Export from the barrel**

`packages/ui/src/index.ts`: add `export { OtpInput } from "./components/otp-input";` and `export type { OtpInputProps } from "./components/otp-input";` alongside the existing component exports (CategoryTile is already exported).

- [ ] **Step 9: Verify and commit**

Run: `pnpm --filter @agri/ui test && pnpm --filter @agri/ui lint && pnpm --filter @agri/ui typecheck && pnpm run check:hex`
Expected: all PASS, zero hex violations.

```bash
git add packages/ui/src
git commit -m "feat(d09): otp input, selectable category tile, auth i18n"
```

### Task 10: web-id app — login flow, devices manager, locale plumbing

No unit-test cycle here (the app has no test runner); the red→green cycle for this task is the Playwright suite in Task 11 plus `turbo lint typecheck build`. Keep this task's commit separate so review can gate on it.

**Files:**
- Modify: `apps/web-id/next.config.ts`, `apps/web-id/i18n/request.ts`, `apps/web-id/app/layout.tsx`, `apps/web-id/app/page.tsx`
- Create: `apps/web-id/lib/api.ts`, `apps/web-id/app/login/page.tsx`, `apps/web-id/app/login/login-flow.tsx`, `apps/web-id/app/devices/page.tsx`, `apps/web-id/app/devices/devices-manager.tsx`

**Interfaces:**
- Consumes: Task 6 endpoints via same-origin paths `/api/id/*` (rewritten), `/authorize` (rewritten); `OtpInput`, `CategoryTile`, `Button`, `Card`, `Modal`, `EmptyState`, `ToastProvider/useToast` from `@agri/ui`; `ui.auth.*` messages.
- Produces: routes `/` (redirects by session), `/login` (phone → OTP → handle → language, resumes `next`), `/devices`.

- [ ] **Step 1: Rewrites + API base**

`next.config.ts` — add inside `nextConfig`:

```ts
  // D09: the session cookie must be first-party on id.agri.in. In dev the
  // Next server proxies the FastAPI backend so browser, UI and API share one
  // origin; in prod the reverse proxy does the same job at id.agri.in.
  async rewrites() {
    const api = process.env.API_BASE_URL ?? "http://localhost:8000";
    return [
      { source: "/api/id/:path*", destination: `${api}/:path*` },
      { source: "/authorize", destination: `${api}/authorize` },
    ];
  },
```

- [ ] **Step 2: Locale from cookie**

`apps/web-id/i18n/request.ts` becomes:

```ts
import { getUiMessages, isLocale } from "@agri/ui/i18n";
import { cookies } from "next/headers";
import { getRequestConfig } from "next-intl/server";

/**
 * Locale = NEXT_LOCALE cookie (set by the language screen), else "en".
 * The cookie holds a locale code, never a token - localStorage stays empty
 * and agri_sid stays httpOnly (D09 non-negotiable 2).
 */
export default getRequestConfig(async ({ requestLocale }) => {
  const requested = await requestLocale;
  if (requested !== undefined && isLocale(requested)) {
    return { locale: requested, messages: getUiMessages(requested) };
  }
  const jar = await cookies();
  const fromCookie = jar.get("NEXT_LOCALE")?.value;
  const locale = isLocale(fromCookie) ? fromCookie : "en";
  return { locale, messages: getUiMessages(locale) };
});
```

(Reading `cookies()` opts pages into dynamic rendering — correct for auth screens.)

- [ ] **Step 3: `lib/api.ts` — thin same-origin client**

```ts
/**
 * Same-origin calls to the id.agri.in API (Next rewrite -> FastAPI).
 * credentials stay default ("same-origin"): the agri_sid cookie rides along
 * because the rewrite keeps everything one origin. No tokens ever touch JS.
 */
export class ApiError extends Error {
  constructor(
    public readonly status: number,
    public readonly detail: string,
  ) {
    super(`${status}: ${detail}`);
  }
}

async function parse(response: Response) {
  const body = await response.json().catch(() => ({}));
  if (!response.ok) {
    throw new ApiError(response.status, String(body.detail ?? body.error ?? "request_failed"));
  }
  return body;
}

export function postJson(path: string, payload: unknown) {
  return fetch(`/api/id${path}`, {
    method: "POST",
    headers: { "content-type": "application/json" },
    body: JSON.stringify(payload),
  }).then(parse);
}

export function getJson(path: string) {
  return fetch(`/api/id${path}`).then(parse);
}
```

- [ ] **Step 4: Layout + landing**

`app/layout.tsx`: wrap children with `ToastProvider` from `@agri/ui` (inside `NextIntlClientProvider`). Keep `THEME = "theme-agri"` and fonts unchanged.

`app/page.tsx` (server component — session check by forwarding the cookie to the API):

```tsx
import { cookies } from "next/headers";
import { redirect } from "next/navigation";

const API = process.env.API_BASE_URL ?? "http://localhost:8000";

export default async function Home() {
  const jar = await cookies();
  const sid = jar.get("agri_sid")?.value;
  if (sid) {
    const me = await fetch(`${API}/auth/me`, {
      headers: { cookie: `agri_sid=${sid}` },
      cache: "no-store",
    });
    if (me.ok) redirect("/devices");
  }
  redirect("/login");
}
```

- [ ] **Step 5: Login flow**

`app/login/page.tsx` (server shell — metadata + centered column):

```tsx
import { buildMetadata } from "@agri/ui/seo";
import type { Metadata } from "next";

import { LoginFlow } from "./login-flow";

export const metadata: Metadata = {
  ...buildMetadata({
    title: "Sign in — AgriID",
    description: "One login for agri.in, milk.in and organicstore.in",
    path: "/login",
  }),
  robots: { index: false, follow: false }, // auth screens never index
};

export default function LoginPage({
  searchParams,
}: {
  searchParams: Promise<{ next?: string }>;
}) {
  return <LoginFlow searchParamsPromise={searchParams} />;
}
```

(Adapt the `buildMetadata` call to its real signature in `packages/ui/src/seo/meta.ts` — read it first; if it requires a `siteUrl`/`canonical` param, pass the id.agri.in origin. If `@agri/ui/seo` exports a `NoIndex` helper (`no-index.tsx`), prefer it over the raw robots object.)

`app/login/login-flow.tsx` — the client flow. Complete component:

```tsx
"use client";

import {
  Button,
  Card,
  CategoryTile,
  OtpInput,
  useToast,
} from "@agri/ui";
import { useRouter } from "next/navigation";
import { use, useEffect, useRef, useState } from "react";
import { useTranslations } from "next-intl";

import { ApiError, getJson, postJson } from "../../lib/api";

type Step = "phone" | "otp" | "handle" | "language";
const RESEND_SECONDS = 30; // mirrors otp_limits first-rung cooldown

function safeNext(raw: string | undefined): string | null {
  // resume only ever returns to our own /authorize - anything else is dropped
  return raw && raw.startsWith("/authorize?") ? raw : null;
}

export function LoginFlow({
  searchParamsPromise,
}: {
  searchParamsPromise: Promise<{ next?: string }>;
}) {
  const { next } = use(searchParamsPromise);
  const t = useTranslations("ui.auth");
  const router = useRouter();
  const { toast } = useToast();

  const [step, setStep] = useState<Step>("phone");
  const [phone, setPhone] = useState("");
  const [code, setCode] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const [cooldown, setCooldown] = useState(0);
  const [isNewUser, setIsNewUser] = useState(false);
  const [handle, setHandle] = useState("");
  const [handleState, setHandleState] = useState<string | null>(null);
  const [suggestions, setSuggestions] = useState<string[]>([]);
  const proofUsed = useRef(false);

  useEffect(() => {
    if (cooldown <= 0) return;
    const timer = setInterval(() => setCooldown((s) => s - 1), 1000);
    return () => clearInterval(timer);
  }, [cooldown > 0]);

  const finish = (nextStep: Step | "done") => {
    if (nextStep !== "done") return setStep(nextStep);
    const resume = safeNext(next);
    if (resume) window.location.assign(resume);
    else router.push("/devices");
  };

  const requestOtp = async () => {
    setBusy(true);
    setError(null);
    try {
      await postJson("/auth/otp/request", { phone, purpose: "login" });
      setCode("");
      setCooldown(RESEND_SECONDS);
      setStep("otp");
    } catch (err) {
      setError(err instanceof ApiError && err.status === 429 ? t("otp.locked") : t("phone.invalid"));
    } finally {
      setBusy(false);
    }
  };

  const verifyAndLogin = async (fullCode: string) => {
    if (busy || proofUsed.current) return;
    setBusy(true);
    setError(null);
    try {
      const { otp_proof } = await postJson("/auth/otp/verify", {
        phone,
        purpose: "login",
        code: fullCode,
      });
      proofUsed.current = true;
      const login = await postJson("/auth/login", { otp_proof });
      setIsNewUser(login.is_new_user);
      if (login.is_new_user) {
        setSuggestions((await getJson("/auth/handle/suggest")).suggestions);
        finish("handle");
      } else {
        finish("done");
      }
    } catch (err) {
      setCode("");
      proofUsed.current = false;
      const locked = err instanceof ApiError && err.status === 429;
      setError(locked ? t("otp.locked") : t("otp.wrong"));
    } finally {
      setBusy(false);
    }
  };

  const checkHandle = async (candidate: string) => {
    setHandle(candidate);
    if (candidate.length < 4) return setHandleState(null);
    const result = await getJson(`/auth/handle/check?h=${encodeURIComponent(candidate)}`);
    setHandleState(result.ok ? "available" : result.code);
  };

  const saveHandle = async () => {
    setBusy(true);
    try {
      await postJson("/auth/handle", { handle });
      finish("language");
    } catch (err) {
      setHandleState(err instanceof ApiError ? err.detail : "invalid_format");
    } finally {
      setBusy(false);
    }
  };

  const chooseLanguage = async (locale: "en" | "ta" | "hi") => {
    await postJson("/auth/language", { language: locale });
    document.cookie = `NEXT_LOCALE=${locale}; path=/; max-age=31536000; samesite=lax`;
    toast({ title: t("language.continue") });
    finish("done");
    router.refresh();
  };

  return (
    <main className="mx-auto flex min-h-dvh w-full max-w-[420px] flex-col justify-center gap-4 px-4 py-8">
      <Card className="p-6">
        {step === "phone" && (
          <form
            className="flex flex-col gap-3"
            onSubmit={(event) => {
              event.preventDefault();
              void requestOtp();
            }}
          >
            <h1 className="font-display text-xl font-bold text-ink">{t("phone.title")}</h1>
            <p className="text-sm text-sub">{t("phone.subtitle")}</p>
            <label className="text-sm font-bold text-ink" htmlFor="phone">
              {t("phone.label")}
            </label>
            <input
              id="phone"
              type="tel"
              inputMode="numeric"
              autoComplete="tel"
              maxLength={10}
              value={phone}
              onChange={(event) => setPhone(event.target.value.replace(/\D/g, ""))}
              className="min-h-[44px] rounded-btn border border-line bg-card px-3.5 text-lg font-bold tracking-[.05em] text-ink"
            />
            {error && <p role="alert" className="text-sm text-sub">{error}</p>}
            <Button variant="brand" type="submit" disabled={busy || phone.length !== 10}>
              {t("phone.cta")}
            </Button>
          </form>
        )}

        {step === "otp" && (
          <div className="flex flex-col gap-3">
            <h1 className="font-display text-xl font-bold text-ink">{t("otp.title")}</h1>
            <p className="text-sm text-sub">{t("otp.sentTo", { phone: `+91 ${phone}` })}</p>
            <OtpInput
              value={code}
              onChange={setCode}
              onComplete={(full) => void verifyAndLogin(full)}
              label={t("otp.inputLabel")}
              disabled={busy}
              error={Boolean(error)}
            />
            {error && <p role="alert" className="text-sm text-sub">{error}</p>}
            <Button
              variant="ghost"
              onClick={() => void requestOtp()}
              disabled={busy || cooldown > 0}
            >
              {cooldown > 0 ? t("otp.resendIn", { seconds: cooldown }) : t("otp.resend")}
            </Button>
          </div>
        )}

        {step === "handle" && (
          <div className="flex flex-col gap-3">
            <h1 className="font-display text-xl font-bold text-ink">{t("handle.title")}</h1>
            <p className="text-sm text-sub">{t("handle.subtitle")}</p>
            <input
              aria-label={t("handle.title")}
              value={handle}
              placeholder={t("handle.placeholder")}
              onChange={(event) => void checkHandle(event.target.value.toLowerCase())}
              className="min-h-[44px] rounded-btn border border-line bg-card px-3.5 text-lg font-bold text-ink"
            />
            {handleState && (
              <p role="status" className="text-sm text-sub">
                {handleState === "available" && t("handle.available")}
                {handleState === "taken" && t("handle.taken")}
                {handleState === "reserved" && t("handle.reserved")}
                {(handleState === "invalid_format" || handleState === "already_changed") &&
                  t("handle.invalidFormat")}
              </p>
            )}
            <div className="flex flex-wrap gap-1.5" aria-label={t("handle.suggestions")}>
              {suggestions.map((name) => (
                <button
                  key={name}
                  type="button"
                  onClick={() => void checkHandle(name)}
                  className="tap-target rounded-pill border border-line bg-card px-3 text-sm font-bold text-ink"
                >
                  @{name}
                </button>
              ))}
            </div>
            <Button
              variant="brand"
              onClick={() => void saveHandle()}
              disabled={busy || handleState !== "available"}
            >
              {t("handle.save")}
            </Button>
            <Button variant="ghost" onClick={() => finish("language")}>
              {t("handle.skip")}
            </Button>
          </div>
        )}

        {step === "language" && (
          <div className="flex flex-col gap-3">
            <h1 className="font-display text-xl font-bold text-ink">{t("language.title")}</h1>
            <div className="grid grid-cols-3 gap-2">
              <CategoryTile icon="🌐" label="English" vernacular="English" tint="sky" onClick={() => void chooseLanguage("en")} />
              <CategoryTile icon="🌾" label="Tamil" vernacular="தமிழ்" tint="leaf" onClick={() => void chooseLanguage("ta")} />
              <CategoryTile icon="🌻" label="Hindi" vernacular="हिन्दी" tint="gold" onClick={() => void chooseLanguage("hi")} />
            </div>
          </div>
        )}
      </Card>
    </main>
  );
}
```

Adapt utility classes to the preset's actual token names (`rounded-pill`, `tap-target`, `font-display` — grep `packages/config/tailwind-preset.ts` and existing `packages/ui` components; `pills.tsx` uses `tap-target`, `PincodeHero` shows the display-font pattern). New-user flow order note: `isNewUser` is set for potential future copy differences; the flow itself is handle → language → done, returning users skip straight to done.

- [ ] **Step 6: Devices manager**

`app/devices/page.tsx` (server shell, session-gated):

```tsx
import { buildMetadata } from "@agri/ui/seo";
import type { Metadata } from "next";
import { cookies } from "next/headers";
import { redirect } from "next/navigation";

import { DevicesManager } from "./devices-manager";

const API = process.env.API_BASE_URL ?? "http://localhost:8000";

export const metadata: Metadata = {
  ...buildMetadata({
    title: "Your devices — AgriID",
    description: "Manage where you are signed in",
    path: "/devices",
  }),
  robots: { index: false, follow: false },
};

export default async function DevicesPage() {
  const jar = await cookies();
  const sid = jar.get("agri_sid")?.value;
  if (!sid) redirect("/login");
  const me = await fetch(`${API}/auth/me`, {
    headers: { cookie: `agri_sid=${sid}` },
    cache: "no-store",
  });
  if (!me.ok) redirect("/login");
  const profile = await me.json();
  return <DevicesManager agriId={profile.agri_id} />;
}
```

`app/devices/devices-manager.tsx`:

```tsx
"use client";

import { Button, Card, EmptyState, Modal, useToast } from "@agri/ui";
import { useRouter } from "next/navigation";
import { useCallback, useEffect, useState } from "react";
import { useTranslations } from "next-intl";

import { getJson, postJson } from "../../lib/api";

interface Device {
  device_id: string;
  kind: string;
  label: string | null;
  current: boolean;
  created_at: string;
  last_seen_at: string | null;
}

export function DevicesManager({ agriId }: { agriId: string }) {
  const t = useTranslations("ui.auth.devices");
  const router = useRouter();
  const { toast } = useToast();
  const [devices, setDevices] = useState<Device[] | null>(null);

  const reload = useCallback(async () => {
    setDevices((await getJson("/auth/devices")).items);
  }, []);

  useEffect(() => {
    void reload();
  }, [reload]);

  const revoke = async (device: Device) => {
    await postJson("/auth/devices/revoke", { device_id: device.device_id, kind: device.kind });
    toast({ title: t("revoked") });
    if (device.current) return router.push("/login");
    await reload();
  };

  const rename = async (device: Device, label: string) => {
    if (!label.trim()) return;
    await postJson("/auth/devices/label", {
      device_id: device.device_id,
      kind: device.kind,
      label: label.trim(),
    });
    await reload();
  };

  const logoutEverywhere = async () => {
    await postJson("/auth/logout-everywhere", {});
    router.push("/login");
  };

  return (
    <main className="mx-auto flex w-full max-w-[560px] flex-col gap-4 px-4 py-8">
      <header className="flex items-center justify-between">
        <div>
          <h1 className="font-display text-xl font-bold text-ink">{t("title")}</h1>
          <p className="text-sm text-sub">@{agriId}</p>
        </div>
        <Button variant="ghost" onClick={() => void postJson("/auth/logout", {}).then(() => router.push("/login"))}>
          {t("logout")}
        </Button>
      </header>

      {devices !== null && devices.length === 0 && (
        <EmptyState icon="💻" title={t("empty")} />
      )}

      <ul className="flex flex-col gap-2" data-testid="device-list">
        {(devices ?? []).map((device) => (
          <li key={device.device_id}>
            <Card className="flex items-center justify-between gap-2 p-4">
              <div className="min-w-0">
                <p className="truncate font-bold text-ink">
                  {device.label ?? device.kind}
                  {device.current && (
                    <span className="ml-2 rounded-pill border border-line px-2 text-xs text-sub">
                      {t("current")}
                    </span>
                  )}
                </p>
                <p className="text-xs text-sub">{device.kind}</p>
              </div>
              <div className="flex shrink-0 gap-1.5">
                <form
                  onSubmit={(event) => {
                    event.preventDefault();
                    const input = event.currentTarget.elements.namedItem("label");
                    void rename(device, (input as HTMLInputElement).value);
                  }}
                  className="hidden sm:flex sm:gap-1.5"
                >
                  <input
                    name="label"
                    aria-label={t("rename")}
                    placeholder={t("renamePlaceholder")}
                    defaultValue={device.label ?? ""}
                    className="min-h-[44px] w-32 rounded-btn border border-line bg-card px-2 text-sm text-ink"
                  />
                  <Button variant="ghost" type="submit" className="flex-none">
                    {t("rename")}
                  </Button>
                </form>
                <Modal
                  trigger={<Button variant="ghost" className="flex-none">{t("revoke")}</Button>}
                  title={t("confirmRevoke")}
                  closeLabel={t("cancel")}
                >
                  <Button variant="brand" onClick={() => void revoke(device)}>
                    {t("revoke")}
                  </Button>
                </Modal>
              </div>
            </Card>
          </li>
        ))}
      </ul>

      {devices !== null && devices.length > 0 && (
        <Modal
          trigger={<Button variant="ghost">{t("revokeAll")}</Button>}
          title={t("confirmRevokeAll")}
          closeLabel={t("cancel")}
        >
          <Button variant="brand" onClick={() => void logoutEverywhere()}>
            {t("revokeAll")}
          </Button>
        </Modal>
      )}
    </main>
  );
}
```

(Check `Modal`'s exact prop surface in `packages/ui/src/components/modal.tsx` — if the dialog needs a controlled-close on confirm, either close via Radix context or accept the dialog staying open during navigation; navigation unmounts it.)

- [ ] **Step 7: Verify build + tokens + visual pass**

Run: `pnpm exec turbo run lint typecheck build --filter=@agri/web-id... && pnpm run check:hex`
Expected: clean. Then a manual side-by-side check against `docs/design-reference/preview_frontend.html` (the DoD's visual-consistency gate): white cards on `--page-bg`, brand CTA, glass pills, `.vern` secondary lines on the language tiles, focus rings visible. Start the stack (`docker compose -f docker-compose.dev.yml up -d postgres redis`, `backend: .venv\Scripts\python.exe -m uvicorn main:app --port 8000`, `pnpm --filter @agri/web-id dev`) and click through phone→OTP (code prints on the API stdout via mock driver) → handle → language → devices.

- [ ] **Step 8: Commit**

```bash
git add apps/web-id
git commit -m "feat(d09): web-id login flow, language picker and devices manager"
```

### Task 11: Playwright auth E2E suite

**Files:**
- Create: `e2e/playwright.config.ts`, `e2e/helpers.ts`, `e2e/auth.spec.ts`, `scripts/e2e-api.mjs`
- Modify: root `package.json` (devDeps + scripts), `turbo.json` (no change needed if e2e runs from root scripts — keep it out of turbo, it's server-coupled)

**Interfaces:**
- Consumes: running FastAPI (port 8000, `OTP_TEST_PEEK=true`), running web-id (port 3003, rewrites at `/api/id/*` + `/authorize`), Postgres (local 55432 default / CI 5432 via `DATABASE_URL`), Redis.
- Produces: `pnpm run e2e` — the five spec scenarios (new-user signup, returning login, wrong-OTP lockout UX, device revoke, logout-everywhere).

- [ ] **Step 1: Install and scripts**

Run: `pnpm add -D -w @playwright/test@1.61.1` then `pnpm exec playwright install chromium`.

Root `package.json` scripts — add:

```json
    "e2e": "playwright test --config e2e/playwright.config.ts",
    "e2e:api": "node scripts/e2e-api.mjs"
```

- [ ] **Step 2: `scripts/e2e-api.mjs` — migrate + serve the API (cross-platform)**

```js
/**
 * Playwright webServer command for the FastAPI side: run migrations, then
 * uvicorn with the E2E peek flag. Uses the venv python locally (Windows dev
 * box) and plain `python` on CI (the job pip-installs into the runner env).
 */
import { spawnSync, spawn } from "node:child_process";
import { existsSync } from "node:fs";
import path from "node:path";
import { fileURLToPath } from "node:url";

const repoRoot = path.join(path.dirname(fileURLToPath(import.meta.url)), "..");
const core = path.join(repoRoot, "backend", "core");
const venvPython = path.join(core, ".venv", "Scripts", "python.exe");
const python = process.env.CI ? "python" : existsSync(venvPython) ? venvPython : "python";

const env = { ...process.env, OTP_TEST_PEEK: "true" };

const migrate = spawnSync(python, ["-m", "alembic", "upgrade", "head"], {
  cwd: core,
  env,
  stdio: "inherit",
});
if (migrate.status !== 0) process.exit(migrate.status ?? 1);

const server = spawn(
  python,
  ["-m", "uvicorn", "main:app", "--host", "127.0.0.1", "--port", "8000"],
  { cwd: core, env, stdio: "inherit" },
);
server.on("exit", (code) => process.exit(code ?? 0));
```

- [ ] **Step 3: `e2e/playwright.config.ts`**

```ts
import { defineConfig } from "@playwright/test";

export default defineConfig({
  testDir: ".",
  timeout: 60_000,
  retries: process.env.CI ? 1 : 0,
  workers: 1, // scenarios share one backend DB; serialize for determinism
  use: {
    baseURL: "http://localhost:3003",
    trace: "retain-on-failure",
  },
  webServer: [
    {
      command: "pnpm run e2e:api",
      url: "http://127.0.0.1:8000/health",
      timeout: 120_000,
      reuseExistingServer: !process.env.CI,
    },
    {
      command: "pnpm --filter @agri/web-id dev",
      url: "http://localhost:3003",
      timeout: 180_000,
      reuseExistingServer: !process.env.CI,
    },
  ],
});
```

(`dev` not `build+start`: rewrites read `API_BASE_URL` at request time either way, and dev avoids a build step per run; if first-compile latency flakes CI, switch the second entry's command to `pnpm --filter @agri/web-id build && pnpm --filter @agri/web-id start` — decide by what CI shows.)

- [ ] **Step 4: `e2e/helpers.ts`**

```ts
import { expect, type Page } from "@playwright/test";

export const API = "http://127.0.0.1:8000";

export function randomPhone(): string {
  // 10-digit Indian mobile, 9-prefix; uniqueness per run keeps scenarios independent
  return `9${Math.floor(100_000_000 + Math.random() * 899_999_999)}`;
}

export async function peekOtp(phone: string): Promise<string> {
  const response = await fetch(`${API}/auth/otp/_peek?phone=${encodeURIComponent(phone)}`);
  const body = (await response.json()) as { code: string | null };
  if (!body.code) throw new Error(`no OTP recorded for ${phone}`);
  return body.code;
}

export async function fillOtp(page: Page, code: string): Promise<void> {
  // typing into box 1 with auto-advance covers the component contract
  const first = page.getByRole("textbox").filter({ hasNot: page.locator("#phone") }).first();
  await first.click();
  await page.keyboard.type(code, { delay: 40 });
}

export async function loginAs(page: Page, phone: string): Promise<void> {
  await page.goto("/login");
  await page.getByLabel(/mobile number/i).fill(phone);
  await page.getByRole("button", { name: /send otp/i }).click();
  await expect(page.getByText(/6-digit code/i)).toBeVisible();
  await fillOtp(page, await peekOtp(`+91${phone}`));
}
```

- [ ] **Step 5: `e2e/auth.spec.ts` — the five scenarios**

```ts
import { expect, test, type BrowserContext } from "@playwright/test";

import { fillOtp, loginAs, peekOtp, randomPhone } from "./helpers";

test.describe("D09 auth flows", () => {
  test("new-user signup: phone -> otp -> handle -> language -> devices", async ({ page }) => {
    const phone = randomPhone();
    await loginAs(page, phone);

    // new user lands on the handle picker
    await expect(page.getByText(/pick your @handle/i)).toBeVisible();
    const handle = `e2e_${phone.slice(4)}`;
    await page.getByPlaceholder("your_handle").fill(handle);
    await expect(page.getByText(/available/i)).toBeVisible();
    await page.getByRole("button", { name: /save handle/i }).click();

    // language picker, then devices
    await page.getByRole("button", { name: /tamil/i }).click();
    await expect(page).toHaveURL(/\/devices/);
    await expect(page.getByText(`@${handle}`)).toBeVisible();
    await expect(page.getByText(/this device|இந்த சாதனம்/i)).toBeVisible();
  });

  test("returning login skips handle and language", async ({ page }) => {
    const phone = randomPhone();
    await loginAs(page, phone); // first signup
    await page.getByRole("button", { name: /skip/i }).click();
    await page.getByRole("button", { name: /english/i }).click();
    await expect(page).toHaveURL(/\/devices/);
    await page.getByRole("button", { name: /sign out$/i }).first().click();
    await expect(page).toHaveURL(/\/login/);

    await loginAs(page, phone); // returning
    await expect(page).toHaveURL(/\/devices/); // straight through
  });

  test("wrong OTP shows error, then lockout UX after burn", async ({ page }) => {
    const phone = randomPhone();
    await page.goto("/login");
    await page.getByLabel(/mobile number/i).fill(phone);
    await page.getByRole("button", { name: /send otp/i }).click();
    const real = await peekOtp(`+91${phone}`);
    const wrong = real === "000000" ? "111111" : "000000";

    for (let attempt = 0; attempt < 3; attempt += 1) {
      await fillOtp(page, wrong);
      await expect(page.getByRole("alert")).toBeVisible(); // wrong-code message
    }
    // OTP_MAX_ATTEMPTS = 3: the code is burned - even the real one fails now
    await fillOtp(page, real);
    await expect(page.getByRole("alert")).toBeVisible();
    // resend is the recovery path and shows its cooldown countdown
    await expect(page.getByRole("button", { name: /resend/i })).toBeVisible();
  });

  test("device revoke signs the other browser out", async ({ browser }) => {
    const phone = randomPhone();
    const deviceA: BrowserContext = await browser.newContext();
    const deviceB: BrowserContext = await browser.newContext({
      userAgent: "e2e-second-device",
    });
    const pageA = await deviceA.newPage();
    const pageB = await deviceB.newPage();

    await loginAs(pageA, phone);
    await pageA.getByRole("button", { name: /skip/i }).click();
    await pageA.getByRole("button", { name: /english/i }).click();
    await loginAs(pageB, phone);
    await expect(pageB).toHaveURL(/\/devices/);

    // A revokes B (the non-current row)
    await pageA.goto("/devices");
    const otherRow = pageA
      .getByTestId("device-list")
      .locator("li")
      .filter({ hasNot: pageA.getByText(/this device/i) })
      .first();
    await otherRow.getByRole("button", { name: /sign out/i }).click();
    await pageA.getByRole("dialog").getByRole("button", { name: /sign out/i }).click();

    await pageB.reload();
    await expect(pageB).toHaveURL(/\/login/); // server-side session store said no
    await deviceA.close();
    await deviceB.close();
  });

  test("logout-everywhere kills both devices at once", async ({ browser }) => {
    const phone = randomPhone();
    const deviceA = await browser.newContext();
    const deviceB = await browser.newContext({ userAgent: "e2e-second-device" });
    const pageA = await deviceA.newPage();
    const pageB = await deviceB.newPage();

    await loginAs(pageA, phone);
    await pageA.getByRole("button", { name: /skip/i }).click();
    await pageA.getByRole("button", { name: /english/i }).click();
    await loginAs(pageB, phone);

    await pageA.goto("/devices");
    await pageA.getByRole("button", { name: /sign out everywhere/i }).click();
    await pageA
      .getByRole("dialog")
      .getByRole("button", { name: /sign out everywhere/i })
      .click();
    await expect(pageA).toHaveURL(/\/login/);

    await pageB.reload();
    await expect(pageB).toHaveURL(/\/login/);
    await deviceA.close();
    await deviceB.close();
  });
});
```

Selector strings must match the Task 9 message catalog exactly — when a locator fails, fix the LOCATOR to the real copy, never weaken the assertion. The wrong-OTP test depends on `verify_otp` burning after `OTP_MAX_ATTEMPTS = 3` (otp_limits.py).

- [ ] **Step 6: Run red → green**

Prereqs once: `docker compose -f docker-compose.dev.yml up -d postgres redis`.
Run: `pnpm run e2e`
Expected first run: failures wherever UI copy/selectors drift — fix locators (or genuine UI bugs Task 10 left) until green. All five scenarios PASS.

- [ ] **Step 7: Commit**

```bash
git add e2e scripts/e2e-api.mjs package.json pnpm-lock.yaml
git commit -m "test(d09): playwright auth e2e suite"
```

---

### Task 12: CI job, runbook, final verification, PR

**Files:**
- Modify: `.github/workflows/ci.yml`, `docs/runbooks/branch-protection.md`

- [ ] **Step 1: Add the `e2e-auth` job to `ci.yml`**

New job, same doctrine as the header comment (no path filters — it runs on every PR):

```yaml
  e2e-auth:
    runs-on: ubuntu-latest
    timeout-minutes: 15
    services:
      postgres:
        image: postgres:16
        env:
          POSTGRES_USER: app
          POSTGRES_PASSWORD: app
          POSTGRES_DB: agri
        ports: ["5432:5432"]
        options: >-
          --health-cmd "pg_isready -U app -d agri" --health-interval 5s
          --health-timeout 5s --health-retries 10
      redis:
        image: redis:7
        ports: ["6379:6379"]
        options: >-
          --health-cmd "redis-cli ping" --health-interval 5s
          --health-timeout 5s --health-retries 10
    env:
      DATABASE_URL: postgresql+asyncpg://app:app@localhost:5432/agri
      REDIS_URL: redis://localhost:6379/0
      API_BASE_URL: http://127.0.0.1:8000
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-python@v5
        with:
          python-version: "3.13"
          cache: pip
          cache-dependency-path: backend/core/pyproject.toml
      - run: pip install -e backend/core[dev]
      - uses: actions/setup-node@v4
        with:
          node-version-file: .nvmrc
      - uses: pnpm/action-setup@v4
      - run: pnpm install --frozen-lockfile
      - run: pnpm exec playwright install chromium --with-deps
      - run: pnpm run e2e
        env:
          CI: "true"
      - uses: actions/upload-artifact@v4
        if: failure()
        with:
          name: playwright-traces
          path: test-results/
```

Copy the exact `postgres`/`redis` service stanzas, pnpm/node setup steps, and concurrency/permissions conventions from the existing `backend`/`web` jobs in `ci.yml` rather than trusting the YAML above wholesale — the file is protected and its idioms (env var names, service env like `POSTGRES_*`) must match what the `backend` job already uses. Check whether `pip install -e backend/core[dev]` works from the repo root or needs `working-directory`.

- [ ] **Step 2: Update `docs/runbooks/branch-protection.md`**

Add `e2e-auth` to the required-checks list (7 → 8) following the file's existing format, including the `gh api` verification snippet if the doc templates it per-check.

- [ ] **Step 3: Full local verification sweep (the DoD list)**

From `backend/core` (postgres+redis up):
- `.venv\Scripts\pytest.exe -q` — all green, including the family-revoke and logout-everywhere tests.
- `.venv\Scripts\ruff.exe format --check . && .venv\Scripts\ruff.exe check . && .venv\Scripts\mypy.exe . && .venv\Scripts\lint-imports.exe`
- `.venv\Scripts\python.exe scripts\dump_public_routes.py --check`

From repo root:
- `pnpm exec turbo run lint typecheck test build`
- `pnpm run check:hex`
- `pnpm run e2e`

- [ ] **Step 4: 🔍 Line-by-line security read (DoD, human-grade care)**

Read `refresh_service.py`, `session_service.py`, `session_router.py`, and the `oauth_router.py` diff top to bottom in one sitting, checking each THREAT-MODEL claim: rotation atomicity (racing rotations), reuse → family revoke, device binding, fixation (fresh sid), httpOnly/Secure/Lax and host-only cookie, no plaintext token at rest or in logs (grep the diff for `token`, `sid`, `logger` — no plaintext in any `extra_fields`), suspended-deny on every path, GETDEL proof burn. Record findings; fix anything found before the PR.

- [ ] **Step 5: Push and open the PR**

```bash
git push -u origin feat/d09-sessions-webid
gh pr create --base dev --title "feat(d09): sessions + web-id" --body "<summary covering: A-E spec items, non-negotiables each mapped to its proving test, adopted assumptions (30-day refresh TTL; fingerprint = UA+platform hash), threat-model mitigations, CI: new e2e-auth required check>"
```

(Memory D01-B says no `gh` on this box — if `gh` is absent, push and open the PR via the GitHub web UI, or provide the compare URL: `https://github.com/oneuni-in/agri-ecosystem/compare/dev...feat/d09-sessions-webid`.)

PR body must end with:

```
🤖 Generated with [Claude Code](https://claude.com/claude-code)
```

---

## Self-Review (spec coverage)

- **A. Login flow**: phone→OTP entry = existing D07 routes + Task 10 UI; otp_proof consumption + account creation + AG-fallback = Task 6 `/auth/login`; handle picker (suggestions/availability/skip) = Tasks 6+10; cookie discipline = Task 6 `_set_session_cookie`; resume /authorize = Task 7 + `safeNext` in Task 10. ✔
- **B. Refresh tokens**: 30-day rotating device-bound per-client hashed = Tasks 1+3; reuse→family revoke + audit = Task 3 (+HTTP proof Task 4); `grant_type=refresh_token` in D08 server = Task 4. ✔
- **C. Revocation**: logout / logout-everywhere / server-side store checks / suspended instant deny = Tasks 2, 5, 6 (+Playwright proof Task 11). ✔
- **D. web-id screens**: phone, OTP auto-advance + visible resend cooldown, handle picker, language selection (CategoryTile), device manager (list/label/revoke/revoke-all), EN/TA/HI, ≥44px, vernacular = Tasks 9+10. ✔
- **E. Playwright E2E**: all five named scenarios = Task 11. ✔
- **Non-negotiables**: family-revoke test (T3/T4), httpOnly+Secure+no web storage (T6/T10), logout-everywhere one request + test (T2/T6/T11), visual consistency check (T10 step 7). ✔
- **DO NOTs respected**: no BFF/app cookies (auth-client stub untouched), no profile editing beyond handle+language, refresh plaintext only in creation responses, session logic only on id.agri.in. ✔
- **Known judgment calls** (flag in PR): signup handle pick consumes the one free change (the flag model has no second dimension); strict fingerprint binding logs a device out on browser major-update (revokes family — clean, safe, re-login is cheap); `/authorize` no-session now 302s to relative `/login?next=` instead of `error=login_required` (D10's BFF must expect a login redirect, not an error callback).

## Execution Handoff

Plan complete. Execute with superpowers:executing-plans (inline) or superpowers:subagent-driven-development (fresh subagent per task), reviewing at each task's commit boundary.







