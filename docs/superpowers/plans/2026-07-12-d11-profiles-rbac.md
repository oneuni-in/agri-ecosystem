# D11 Profiles + RBAC Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Progressive user profiles (PATCH-style, geo-validated location, avatar upload, completion score with a `profile.completed` event) plus RBAC (`require_permission` dependency, cached permission matrix) and an admin console (user search by agri_id/phone-last-4, role assignment, suspend/reactivate) — backend + web-id account UI + web-admin UI + a `ProfileNudge` component in packages/ui.

**Architecture:** Backend work extends the existing identity module (the `Profile`/`Role`/`Permission` tables already exist from D06 migration 0007). RBAC layers a cached roles→permissions matrix on top of D09's per-request principal resolution — user→roles is never cached (loaded fresh every request), so role changes and suspension bite within one request cycle with no invalidation machinery. web-admin reaches the backend with the D08 access token via a new Bearer path in `resolve_principal` plus a `getAccessToken()` accessor on `@agri/auth-client` and a thin BFF proxy route (tokens never touch the browser).

**Tech Stack:** FastAPI + SQLAlchemy async + Alembic (backend/core, venv `.venv`, host Python 3.12), joserfc (JWT verify), minio (avatar storage, new dep), Redis Streams (events), Next 15 + next-intl + Tailwind tokens (apps/web-id, apps/web-admin, packages/ui), vitest.

## Global Constraints

- Branch `feat/d11-profiles-rbac` from `dev`. NEVER commit to dev/main. PR targets dev; PR TITLE must match `^(feat|fix|...)(\(scope\))?: ...` (GitHub defaults it to the branch name, which FAILS — set title `feat(d11): profiles + rbac` explicitly).
- Backend tooling runs from `backend/core` with `.venv`: `ruff format .`, `ruff check .`, `mypy .`, `lint-imports`, `pytest`. CI also runs `ruff format --check` — always `ruff format .` before committing.
- Windows host: compose postgres is on port **55432**; docker `agri-dev-api-1` squats port 8000 (`docker compose -f docker-compose.dev.yml stop api` before any local E2E). Use the Bash tool with `set -o pipefail` for pipelines. No `gh` CLI — PRs via GitHub REST API with the `git credential fill` token (Bash tool, not PowerShell).
- Every route lives on a `SecureRouter`; no new `public=True` routes in D11 (public_routes.txt must stay unchanged — CI diffs it).
- Every public identity response model subclasses `IdentityPublicSchema` (bans `id`/`user_id`/`phone`/`phone_number` and any UUID annotation at class-definition time).
- Never log request bodies or query strings in the identity module. Full phone numbers never in responses or logs — `phone_last4` only.
- Lists are cursor-paginated via `shared/pagination.paginate` (OFFSET is banned by a lint test).
- Migrations: chain from revision `0010`, filled `# -- THREAT/NOTES:` block (a TODO fails tests), helpers from `shared/migrations.py`.
- Frontend: tokens only — `pnpm check:hex` fails on any hex/rgb literal in apps/ or packages/ui/. New UI strings go into ALL THREE catalogs (`packages/ui/src/i18n/messages/{en,ta,hi}.json`) under the single top-level `"ui"` key.
- Internal packages ship TS source (`exports` → `src/index.ts`); no build steps in packages.
- The D09 handle rule stands: signup consumes the one free handle change — do NOT "fix" `agri_id_changed_once` semantics in profile work.
- Spec assumptions adopted (flag both in the PR body for the owner): score weights phone 20 / name 15 / location 25 / language 10 / interests 15 / avatar 15; interests are free-form strings v1 (max 10, each ≤ 40 chars).
- Scope guards: no KYC, no public profile pages, no role-matrix editing UI, suspend ≠ delete (no row deletion anywhere).

---

### Task 1: Migration 0011 — `users.read` permission + nullable profile language

**Files:**
- Create: `backend/core/alembic/versions/0011_profiles_rbac_v1.py`
- Modify: `backend/core/modules/identity/models.py:231-233` (language nullable)
- Modify: `backend/core/modules/identity/session_router.py:87-89` (`_language_for` None-safe)
- Modify: `backend/core/tests/test_identity_seeds.py` (users.read expectations)

**Interfaces:**
- Consumes: revision `0010`, seed tables from `0008_identity_seed_roles.py`.
- Produces: permission `users.read` granted to `staff` + `super_admin`; `identity.profiles.language` nullable with no default (NULL = "not chosen yet"; API layers report `"en"` as the effective language). Later tasks rely on `Profile.language: Mapped[str | None]`.

**Why language goes nullable:** the completion score awards 10 points for an explicitly chosen language. Today the column is `NOT NULL DEFAULT 'en'`, so any profile row created as a side effect (e.g. a name-only PATCH) would silently score the language component. Every existing profile row was created by `POST /auth/language` (the only write path before D11), so existing rows all represent explicit choices and keep their values.

- [ ] **Step 1: Branch setup**

```bash
git checkout dev && git pull && git checkout -b feat/d11-profiles-rbac
```

- [ ] **Step 2: Write the failing test** — extend `backend/core/tests/test_identity_seeds.py`. Update the existing sets and add a staff assertion:

```python
EXPECTED_PERMISSIONS = {
    "profile.read",
    "profile.write",
    "handle.change",
    "users.suspend",
    "roles.assign",
    "users.read",
}
```

(`test_super_admin_has_every_baseline_permission` asserts `granted == EXPECTED_PERMISSIONS`, so it now demands users.read automatically.) Add:

```python
async def test_staff_can_read_and_suspend_but_not_assign(db_session: AsyncSession) -> None:
    stmt = (
        select(Permission.name)
        .join(RolePermission, RolePermission.permission_id == Permission.id)
        .join(Role, Role.id == RolePermission.role_id)
        .where(Role.name == "staff")
    )
    granted = set((await db_session.scalars(stmt)).all())
    assert granted == {
        "profile.read",
        "profile.write",
        "handle.change",
        "users.suspend",
        "users.read",
    }
```

- [ ] **Step 3: Run to verify it fails**

Run (from `backend/core`): `pytest tests/test_identity_seeds.py -v`
Expected: FAIL — `users.read` not present (test DB is rebuilt per session, so the new migration is required).

- [ ] **Step 4: Write the migration** — `backend/core/alembic/versions/0011_profiles_rbac_v1.py`:

```python
"""D11 profiles+rbac: users.read permission, explicit-only profile language.

Revision ID: 0011
Revises: 0010
Create Date: 2026-07-12

"""
# -- THREAT/NOTES:
# downgrade data loss: the users.read permission row and its staff/super_admin
#   grants are deleted; profiles.language NULLs are rewritten to 'en' before
#   NOT NULL is restored, losing the "not chosen yet" state (completion scores
#   are recomputed on the next profile update, so drift self-heals). Acceptable
#   pre-launch.
# locks: single-row DML on tiny RBAC tables; ALTER COLUMN on identity.profiles
#   takes a brief ACCESS EXCLUSIVE lock - the table is small pre-launch.
# rollout: run after 0010. D11 code assumes users.read exists and that
#   profiles.language may be NULL; deploy the migration with (or before) the
#   D11 API code.

from collections.abc import Sequence

import sqlalchemy as sa
import uuid6
from sqlalchemy.dialects import postgresql

from alembic import op

revision: str = "0011"
down_revision: str | None = "0010"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

PERMISSION = ("users.read", "search users and view their profiles (admin)")
GRANTEE_ROLES = ("staff", "super_admin")

_uuid = postgresql.UUID(as_uuid=True)
permissions_table = sa.table(
    "permissions",
    sa.column("id", _uuid),
    sa.column("name", sa.Text),
    sa.column("description", sa.Text),
    schema="identity",
)
role_permissions_table = sa.table(
    "role_permissions",
    sa.column("id", _uuid),
    sa.column("role_id", _uuid),
    sa.column("permission_id", _uuid),
    schema="identity",
)

language_enum = postgresql.ENUM(
    "en", "ta", "hi", name="user_language", schema="identity", create_type=False
)


def upgrade() -> None:
    bind = op.get_bind()
    permission_id = uuid6.uuid7()
    op.bulk_insert(
        permissions_table,
        [{"id": permission_id, "name": PERMISSION[0], "description": PERMISSION[1]}],
    )
    role_rows = bind.execute(
        sa.text("SELECT id, name FROM identity.roles WHERE name IN :names").bindparams(
            sa.bindparam("names", expanding=True, value=list(GRANTEE_ROLES))
        )
    ).fetchall()
    op.bulk_insert(
        role_permissions_table,
        [
            {"id": uuid6.uuid7(), "role_id": row.id, "permission_id": permission_id}
            for row in role_rows
        ],
    )
    op.alter_column(
        "profiles",
        "language",
        schema="identity",
        existing_type=language_enum,
        nullable=True,
        server_default=None,
    )


def downgrade() -> None:
    op.execute(sa.text("UPDATE identity.profiles SET language = 'en' WHERE language IS NULL"))
    op.alter_column(
        "profiles",
        "language",
        schema="identity",
        existing_type=language_enum,
        nullable=False,
        server_default=sa.text("'en'"),
    )
    seeded = sa.select(permissions_table.c.id).where(permissions_table.c.name == PERMISSION[0])
    op.execute(
        role_permissions_table.delete().where(role_permissions_table.c.permission_id.in_(seeded))
    )
    op.execute(permissions_table.delete().where(permissions_table.c.name == PERMISSION[0]))
```

- [ ] **Step 5: Update the ORM model** — in `backend/core/modules/identity/models.py`, replace the `language` column on `Profile`:

```python
    language: Mapped[str | None] = mapped_column(user_language_enum, nullable=True)
```

- [ ] **Step 6: Make `_language_for` None-safe** — in `backend/core/modules/identity/session_router.py`:

```python
async def _language_for(session: AsyncSession, user_id: uuid.UUID) -> str:
    profile = await session.scalar(select(Profile).where(Profile.user_id == user_id))
    language = profile.language if profile is not None else None
    return language or "en"
```

- [ ] **Step 7: Run tests**

Run: `pytest tests/test_identity_seeds.py tests/test_session_router.py -v`
Expected: PASS (session tests prove login/`me` still report `"en"` for users without an explicit language).

- [ ] **Step 8: Migration round-trip check** — point at a throwaway DB, never the dev DB (migrate_check's downgrade pass drops tables):

```bash
cd backend/core && set -o pipefail && \
DATABASE_URL="postgresql+asyncpg://app:app@localhost:55432/agri_migrate_check" python scripts/migrate_check.py
```

Expected: upgrade head → downgrade base → upgrade head, exit 0. (If the DB doesn't exist, create it first: `psql "postgresql://app:app@localhost:55432/postgres" -c "CREATE DATABASE agri_migrate_check"` — or rely on the script if it self-creates.)

- [ ] **Step 9: Commit**

```bash
git add backend/core/alembic/versions/0011_profiles_rbac_v1.py backend/core/modules/identity/models.py backend/core/modules/identity/session_router.py backend/core/tests/test_identity_seeds.py
git commit -m "feat(d11): users.read permission + explicit-only profile language"
```

---

### Task 2: Completion score — pure function, table-driven tests

**Files:**
- Create: `backend/core/modules/identity/completion.py`
- Test: `backend/core/tests/test_completion_score.py`

**Interfaces:**
- Produces: `compute_completion(*, phone_verified: bool, has_name: bool, has_location: bool, has_language: bool, has_interests: bool, has_avatar: bool) -> int`; `crossed_completion(old_score: int, new_score: int) -> bool`; `WEIGHTS: dict[str, int]`; `COMPLETE_SCORE = 100`. Task 5 (profile service) consumes all of these.

- [ ] **Step 1: Write the failing tests** — `backend/core/tests/test_completion_score.py`:

```python
"""D11.B: the score function is pure and table-tested (non-negotiable)."""

import pytest

from modules.identity.completion import COMPLETE_SCORE, WEIGHTS, compute_completion, crossed_completion

_NONE = dict(
    phone_verified=False,
    has_name=False,
    has_location=False,
    has_language=False,
    has_interests=False,
    has_avatar=False,
)


def test_weights_sum_to_complete_score() -> None:
    assert sum(WEIGHTS.values()) == COMPLETE_SCORE == 100


@pytest.mark.parametrize(
    ("flags", "expected"),
    [
        ({}, 0),
        ({"phone_verified": True}, 20),
        ({"has_name": True}, 15),
        ({"has_location": True}, 25),
        ({"has_language": True}, 10),
        ({"has_interests": True}, 15),
        ({"has_avatar": True}, 15),
        ({"phone_verified": True, "has_name": True}, 35),
        ({"phone_verified": True, "has_location": True, "has_language": True}, 55),
        (
            {
                "phone_verified": True,
                "has_name": True,
                "has_location": True,
                "has_language": True,
                "has_interests": True,
            },
            85,
        ),
        (
            {
                "phone_verified": True,
                "has_name": True,
                "has_location": True,
                "has_language": True,
                "has_interests": True,
                "has_avatar": True,
            },
            100,
        ),
    ],
)
def test_score_table(flags: dict[str, bool], expected: int) -> None:
    assert compute_completion(**{**_NONE, **flags}) == expected


@pytest.mark.parametrize(
    ("old", "new", "expected"),
    [
        (0, 100, True),
        (85, 100, True),
        (100, 100, False),  # staying complete re-emits nothing
        (85, 85, False),
        (0, 85, False),
        (100, 85, False),  # dropping out of 100 emits nothing
    ],
)
def test_crossing_table(old: int, new: int, expected: bool) -> None:
    assert crossed_completion(old, new) is expected
```

- [ ] **Step 2: Run to verify failure**

Run: `pytest tests/test_completion_score.py -v`
Expected: FAIL — `ModuleNotFoundError: modules.identity.completion`.

- [ ] **Step 3: Implement** — `backend/core/modules/identity/completion.py`:

```python
"""Profile completion score (D11.B) - pure, no I/O, no clock.

Weights are the spec's confirmed assumption (flagged in the D11 PR): phone 20 /
name 15 / location 25 / language 10 / interests 15 / avatar 15, summing to
exactly 100. Location only counts as the full pincode-derived triple - partial
location never scores. crossed_completion is the single source of truth for
"emit profile.completed exactly once per crossing".
"""

from typing import Final

WEIGHTS: Final[dict[str, int]] = {
    "phone_verified": 20,
    "name": 15,
    "location": 25,
    "language": 10,
    "interests": 15,
    "avatar": 15,
}

COMPLETE_SCORE: Final = 100


def compute_completion(
    *,
    phone_verified: bool,
    has_name: bool,
    has_location: bool,
    has_language: bool,
    has_interests: bool,
    has_avatar: bool,
) -> int:
    present = {
        "phone_verified": phone_verified,
        "name": has_name,
        "location": has_location,
        "language": has_language,
        "interests": has_interests,
        "avatar": has_avatar,
    }
    return sum(weight for part, weight in WEIGHTS.items() if present[part])


def crossed_completion(old_score: int, new_score: int) -> bool:
    """True exactly when an update crosses INTO completeness."""
    return old_score < COMPLETE_SCORE and new_score >= COMPLETE_SCORE
```

- [ ] **Step 4: Run tests**

Run: `pytest tests/test_completion_score.py -v`
Expected: PASS (18 tests).

- [ ] **Step 5: Commit**

```bash
git add backend/core/modules/identity/completion.py backend/core/tests/test_completion_score.py
git commit -m "feat(d11): pure table-tested profile completion score"
```

---

### Task 3: Pure helpers — `phone_last4` + avatar validation

**Files:**
- Modify: `backend/core/modules/identity/phone.py` (append)
- Create: `backend/core/modules/identity/avatar.py`
- Test: `backend/core/tests/test_avatar_validation.py`, extend `backend/core/tests/test_phone.py` (create if missing — check with `ls backend/core/tests | grep phone`; D06 shipped phone tests, append to the existing file)

**Interfaces:**
- Produces: `phone_last4(phone: str) -> str`; `validate_avatar(data: bytes) -> tuple[str, str]` (content_type, ext — raises `AvatarError(code)`); `avatar_object_key(ext: str) -> str`; `MAX_AVATAR_BYTES = 2_097_152`. Tasks 6 and 7 consume these.

- [ ] **Step 1: Write the failing tests** — `backend/core/tests/test_avatar_validation.py`:

```python
"""D11.A: avatar bytes are judged by magic numbers, never by client headers."""

import pytest

from modules.identity.avatar import (
    MAX_AVATAR_BYTES,
    AvatarError,
    avatar_object_key,
    validate_avatar,
)

JPEG = b"\xff\xd8\xff\xe0" + b"\x00" * 32
PNG = b"\x89PNG\r\n\x1a\n" + b"\x00" * 32
WEBP = b"RIFF" + b"\x00\x00\x00\x00" + b"WEBP" + b"\x00" * 32


@pytest.mark.parametrize(
    ("data", "content_type", "ext"),
    [(JPEG, "image/jpeg", "jpg"), (PNG, "image/png", "png"), (WEBP, "image/webp", "webp")],
)
def test_accepts_real_image_signatures(data: bytes, content_type: str, ext: str) -> None:
    assert validate_avatar(data) == (content_type, ext)


@pytest.mark.parametrize(
    ("data", "code"),
    [
        (b"", "empty_file"),
        (b"GIF89a" + b"\x00" * 16, "unsupported_type"),  # GIF deliberately unsupported
        (b"<svg xmlns='...'/>", "unsupported_type"),  # SVG = script vector, never
        (b"\x89PNG" + b"\x00" * (MAX_AVATAR_BYTES + 1), "too_large"),
    ],
)
def test_rejects_bad_uploads(data: bytes, code: str) -> None:
    with pytest.raises(AvatarError) as excinfo:
        validate_avatar(data)
    assert excinfo.value.code == code


def test_object_keys_are_random_and_extension_typed() -> None:
    first, second = avatar_object_key("png"), avatar_object_key("png")
    assert first != second
    assert first.startswith("avatars/") and first.endswith(".png")


def test_phone_last4() -> None:
    from modules.identity.phone import phone_last4

    assert phone_last4("+919876543210") == "3210"
```

- [ ] **Step 2: Run to verify failure**

Run: `pytest tests/test_avatar_validation.py -v`
Expected: FAIL — `ModuleNotFoundError: modules.identity.avatar`.

- [ ] **Step 3: Implement** — `backend/core/modules/identity/avatar.py`:

```python
"""Avatar upload validation (D11.A) - pure byte-sniffing, no I/O.

The client's Content-Type header is never consulted: type comes from magic
numbers only. JPEG/PNG/WebP allowlist; SVG is deliberately absent (it is a
script vector), GIF adds nothing for a profile photo. 2 MiB cap keeps the
media bucket boring until a real media pipeline lands.
"""

import uuid6

MAX_AVATAR_BYTES = 2 * 1024 * 1024

_SIGNATURES: tuple[tuple[bytes, str, str], ...] = (
    (b"\xff\xd8\xff", "image/jpeg", "jpg"),
    (b"\x89PNG\r\n\x1a\n", "image/png", "png"),
)


class AvatarError(ValueError):
    """Rejected upload; .code is the API error detail."""

    def __init__(self, code: str) -> None:
        super().__init__(code)
        self.code = code


def sniff_image(data: bytes) -> tuple[str, str] | None:
    for magic, content_type, ext in _SIGNATURES:
        if data.startswith(magic):
            return content_type, ext
    if data[:4] == b"RIFF" and data[8:12] == b"WEBP":
        return "image/webp", "webp"
    return None


def validate_avatar(data: bytes) -> tuple[str, str]:
    if not data:
        raise AvatarError("empty_file")
    if len(data) > MAX_AVATAR_BYTES:
        raise AvatarError("too_large")
    sniffed = sniff_image(data)
    if sniffed is None:
        raise AvatarError("unsupported_type")
    return sniffed


def avatar_object_key(ext: str) -> str:
    """Random UUIDv7 key: never derived from user identity (bucket paths must
    not leak who owns which object)."""
    return f"avatars/{uuid6.uuid7().hex}.{ext}"
```

- [ ] **Step 4: Add `phone_last4`** — append to `backend/core/modules/identity/phone.py`:

```python
def phone_last4(phone: str) -> str:
    """The only phone fragment admin surfaces may show (D11 non-negotiable 2)."""
    return phone[-4:]
```

- [ ] **Step 5: Run tests**

Run: `pytest tests/test_avatar_validation.py -v`
Expected: PASS.

- [ ] **Step 6: Commit**

```bash
git add backend/core/modules/identity/avatar.py backend/core/modules/identity/phone.py backend/core/tests/test_avatar_validation.py
git commit -m "feat(d11): avatar byte-sniff validation + phone_last4 helper"
```

---

### Task 4: RBAC — `require_permission` dependency with cached matrix

**Files:**
- Create: `backend/core/modules/identity/rbac.py`
- Modify: `backend/core/tests/conftest.py:33-44` (add cache reset to `_reset_state`)
- Test: `backend/core/tests/test_rbac.py`

**Interfaces:**
- Consumes: `current_principal` from `modules/identity/session_auth.py`, `Role`/`Permission`/`RolePermission` models, `get_session`.
- Produces: `require_permission(permission: str) -> params.Depends` (used as `dependencies=[require_permission("x")]` on SecureRouter routes); `permissions_for_roles(session, roles) -> frozenset[str]`; `reset_permission_cache() -> None`. Tasks 6–8 consume `require_permission`; conftest consumes the reset.

- [ ] **Step 1: Write the failing tests** — `backend/core/tests/test_rbac.py`. Uses a throwaway SecureRouter with three guarded sample routes (the non-negotiable: the pattern proven on ≥3 permissions), the real login flow, and direct role grants:

```python
"""D11.C: require_permission on three sample permissions, per-role denial,
cache freshness semantics."""

from collections.abc import AsyncIterator

import httpx
import pytest
from redis.asyncio import Redis
from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from main import create_app
from modules.identity.models import Permission, Role, RolePermission, User
from modules.identity.rbac import (
    permissions_for_roles,
    require_permission,
    reset_permission_cache,
)
from modules.identity.service import assign_role
from shared.db import get_session
from shared.security import SecureRouter
from tests.test_session_router import UA, _login

pytestmark = pytest.mark.anyio

sample_router = SecureRouter(prefix="/rbac-sample", tags=["rbac-sample"])


@sample_router.get("/write", dependencies=[require_permission("profile.write")])
async def sample_write() -> dict[str, bool]:
    return {"ok": True}


@sample_router.get("/suspend", dependencies=[require_permission("users.suspend")])
async def sample_suspend() -> dict[str, bool]:
    return {"ok": True}


@sample_router.get("/assign", dependencies=[require_permission("roles.assign")])
async def sample_assign() -> dict[str, bool]:
    return {"ok": True}


@pytest.fixture
async def api(
    db_session: AsyncSession, otp_redis: Redis
) -> AsyncIterator[tuple[httpx.AsyncClient, AsyncSession]]:
    app = create_app()
    app.include_router(sample_router)

    async def _session_override() -> AsyncIterator[AsyncSession]:
        yield db_session

    app.dependency_overrides[get_session] = _session_override
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(
        transport=transport, base_url="https://id.test", headers=UA
    ) as client:
        yield client, db_session


async def _me_user(session: AsyncSession, phone: str) -> User:
    user = await session.scalar(select(User).where(User.phone == phone))
    assert user is not None
    return user


async def test_plain_user_permission_matrix(api: tuple[httpx.AsyncClient, AsyncSession]) -> None:
    http, session = api
    await _login(http, session, phone="+919876500001")
    assert (await http.get("/rbac-sample/write")).status_code == 200
    assert (await http.get("/rbac-sample/suspend")).status_code == 403
    assert (await http.get("/rbac-sample/assign")).status_code == 403


async def test_staff_gains_suspend_next_request_without_invalidation(
    api: tuple[httpx.AsyncClient, AsyncSession],
) -> None:
    """user->roles is read fresh per request: no cache to invalidate."""
    http, session = api
    await _login(http, session, phone="+919876500002")
    assert (await http.get("/rbac-sample/suspend")).status_code == 403
    user = await _me_user(session, "+919876500002")
    await assign_role(session, user.id, "staff")
    assert (await http.get("/rbac-sample/suspend")).status_code == 200
    assert (await http.get("/rbac-sample/assign")).status_code == 403  # staff still can't assign


async def test_super_admin_passes_all_three(
    api: tuple[httpx.AsyncClient, AsyncSession],
) -> None:
    http, session = api
    await _login(http, session, phone="+919876500003")
    user = await _me_user(session, "+919876500003")
    await assign_role(session, user.id, "super_admin")
    for path in ("/rbac-sample/write", "/rbac-sample/suspend", "/rbac-sample/assign"):
        assert (await http.get(path)).status_code == 200


async def test_matrix_is_cached_until_reset(db_session: AsyncSession) -> None:
    """role->permissions rides the TTL cache; mutating grants requires
    reset_permission_cache() (the invalidation hook role-matrix tooling must call)."""
    granted = await permissions_for_roles(db_session, ("user",))
    assert "profile.write" in granted
    role_id = await db_session.scalar(select(Role.id).where(Role.name == "user"))
    perm_id = await db_session.scalar(select(Permission.id).where(Permission.name == "profile.write"))
    await db_session.execute(
        delete(RolePermission).where(
            RolePermission.role_id == role_id, RolePermission.permission_id == perm_id
        )
    )
    assert "profile.write" in await permissions_for_roles(db_session, ("user",))  # stale by design
    reset_permission_cache()
    assert "profile.write" not in await permissions_for_roles(db_session, ("user",))


async def test_unknown_role_grants_nothing(db_session: AsyncSession) -> None:
    assert await permissions_for_roles(db_session, ("ghost_role",)) == frozenset()
```

Note: if the repo's tests run without `pytestmark = pytest.mark.anyio` (check `tests/test_devices_router.py` — it has none, asyncio mode is configured globally), drop that line to match.

- [ ] **Step 2: Run to verify failure**

Run: `pytest tests/test_rbac.py -v`
Expected: FAIL — `ModuleNotFoundError: modules.identity.rbac`.

- [ ] **Step 3: Implement** — `backend/core/modules/identity/rbac.py`:

```python
"""require_permission (D11.C): roles -> permissions through a cached matrix.

Freshness contract (the design decision, spelled out):
- user -> roles is NEVER cached. The principal resolver (D09/session_auth)
  loads roles from the DB on every request, so assigning or removing a role
  takes effect on the target's next request with zero invalidation machinery -
  and suspension already denies at resolve time (one request cycle,
  non-negotiable 3).
- role -> permissions changes only via migration today (there is no
  role-matrix editing endpoint in D11), so it rides a short in-process TTL
  cache (the flags.py idiom). Any future endpoint that mutates
  role_permissions MUST call reset_permission_cache() in the same request.

Usage on a SecureRouter route (require_auth has already populated
request.state.principal by the time route-level dependencies after it run):

    @router.post("/thing", dependencies=[require_permission("thing.write")])
"""

import time
from typing import Annotated

from fastapi import Depends, HTTPException, Request, params
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from modules.identity.models import Permission, Role, RolePermission
from modules.identity.session_auth import current_principal
from shared.db import get_session

PERMISSION_CACHE_TTL_SECONDS = 30.0

_cache: tuple[float, dict[str, frozenset[str]]] | None = None


def reset_permission_cache() -> None:
    global _cache
    _cache = None


async def role_permission_matrix(session: AsyncSession) -> dict[str, frozenset[str]]:
    global _cache
    now = time.monotonic()
    if _cache is not None and now - _cache[0] < PERMISSION_CACHE_TTL_SECONDS:
        return _cache[1]
    rows = await session.execute(
        select(Role.name, Permission.name)
        .join(RolePermission, RolePermission.role_id == Role.id)
        .join(Permission, Permission.id == RolePermission.permission_id)
    )
    matrix: dict[str, set[str]] = {}
    for role_name, permission_name in rows:
        matrix.setdefault(role_name, set()).add(permission_name)
    frozen = {name: frozenset(perms) for name, perms in matrix.items()}
    _cache = (now, frozen)
    return frozen


async def permissions_for_roles(
    session: AsyncSession, roles: tuple[str, ...]
) -> frozenset[str]:
    matrix = await role_permission_matrix(session)
    granted: set[str] = set()
    for role in roles:
        granted |= matrix.get(role, frozenset())
    return frozenset(granted)


def require_permission(permission: str) -> params.Depends:
    """403 unless the resolved principal's roles grant `permission`.

    Multi-role users get the UNION of their roles' grants. The detail stays
    generic - the matrix layout is not an API surface.
    """

    async def dependency(
        request: Request, session: Annotated[AsyncSession, Depends(get_session)]
    ) -> None:
        principal = current_principal(request)
        granted = await permissions_for_roles(session, principal.roles)
        if permission not in granted:
            raise HTTPException(status_code=403, detail="missing_permission")

    return Depends(dependency)
```

- [ ] **Step 4: Wire the reset hook** — in `backend/core/tests/conftest.py`, add the import and one line to `_reset_state` (after `reset_principal_resolver()`):

```python
from modules.identity.rbac import reset_permission_cache
```

```python
    reset_principal_resolver()
    reset_permission_cache()
```

- [ ] **Step 5: Run tests**

Run: `pytest tests/test_rbac.py tests/test_identity_seeds.py -v`
Expected: PASS.

- [ ] **Step 6: Commit**

```bash
git add backend/core/modules/identity/rbac.py backend/core/tests/test_rbac.py backend/core/tests/conftest.py
git commit -m "feat(d11): require_permission dependency with cached role matrix"
```

---

### Task 5: Bearer-token principal resolution (web-admin's path to the API)

**Files:**
- Modify: `backend/core/modules/identity/session_auth.py`
- Modify: `backend/core/modules/identity/session_service.py:39-48` (`session_id` nullable on `WebPrincipal`)
- Modify: `backend/core/modules/identity/session_router.py:145-156` (logout guards `session_id is None`)
- Test: `backend/core/tests/test_bearer_auth.py`

**Interfaces:**
- Consumes: `get_key_set()` from `oauth_keys.py`, `load_token_subject` from `oauth_service.py`, D08 token claims (`iss`, `sub`=user UUID, `exp`, RS256+kid).
- Produces: `resolve_principal` now also accepts `Authorization: Bearer <D08 access token>`; `WebPrincipal.session_id: uuid.UUID | None` (None ⇔ bearer principal). Task 8's suspension tests and web-admin (Tasks 10–12) rely on this.

**Design note:** roles and status are loaded FRESH from the DB (`load_token_subject`), never trusted from token claims — a suspension or role change beats the token's remaining ~15-minute lifetime, which is what keeps non-negotiable 3 true for bearer callers. `aud` is deliberately not pinned: this API is the resource server for every first-party client. Cookie wins when both are present.

- [ ] **Step 1: Write the failing tests** — `backend/core/tests/test_bearer_auth.py`:

```python
"""D11: D08 access tokens as a first-class principal for BFF backend calls."""

import time
import uuid
from collections.abc import AsyncIterator

import httpx
import pytest
from joserfc import jwt
from redis.asyncio import Redis
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from main import create_app
from modules.identity.models import User
from modules.identity.oauth_keys import get_signing_key
from settings import get_settings
from shared.db import get_session
from tests.test_session_router import UA, _login

PHONE = "+919876511111"


@pytest.fixture
async def api(
    db_session: AsyncSession, otp_redis: Redis
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


def _mint(user_id: uuid.UUID, *, expires_in: int = 900, issuer: str | None = None) -> str:
    key = get_signing_key()
    now = int(time.time())
    claims = {
        "iss": issuer or get_settings().oauth_issuer,
        "sub": str(user_id),
        "aud": "web-admin",
        "iat": now,
        "exp": now + expires_in,
    }
    return jwt.encode({"alg": "RS256", "kid": key.kid, "typ": "JWT"}, claims, key)


async def _fresh_user(http: httpx.AsyncClient, session: AsyncSession) -> User:
    await _login(http, session, phone=PHONE)
    http.cookies.clear()  # bearer-only from here: prove the cookie isn't doing the work
    user = await session.scalar(select(User).where(User.phone == PHONE))
    assert user is not None
    return user


async def test_valid_bearer_reaches_private_route(
    api: tuple[httpx.AsyncClient, AsyncSession],
) -> None:
    http, session = api
    user = await _fresh_user(http, session)
    response = await http.get(
        "/auth/me", headers={"authorization": f"Bearer {_mint(user.id)}"}
    )
    assert response.status_code == 200
    assert response.json()["agri_id"] == user.agri_id


@pytest.mark.parametrize(
    "token_builder",
    [
        lambda user_id: _mint(user_id, expires_in=-60),  # expired
        lambda user_id: _mint(user_id, issuer="https://evil.example"),  # wrong iss
        lambda user_id: "not-a-jwt",  # garbage
        lambda user_id: _mint(uuid.uuid4()),  # unknown subject
    ],
)
async def test_bad_bearer_is_401(
    api: tuple[httpx.AsyncClient, AsyncSession], token_builder
) -> None:
    http, session = api
    user = await _fresh_user(http, session)
    response = await http.get(
        "/auth/me", headers={"authorization": f"Bearer {token_builder(user.id)}"}
    )
    assert response.status_code == 401


async def test_suspended_user_bearer_denied_within_one_request(
    api: tuple[httpx.AsyncClient, AsyncSession],
) -> None:
    """The token stays cryptographically valid; the DB status check kills it."""
    http, session = api
    user = await _fresh_user(http, session)
    token = _mint(user.id)
    ok = await http.get("/auth/me", headers={"authorization": f"Bearer {token}"})
    assert ok.status_code == 200
    user.status = "suspended"
    await session.flush()
    denied = await http.get("/auth/me", headers={"authorization": f"Bearer {token}"})
    assert denied.status_code == 401


async def test_bearer_logout_is_a_clean_noop(
    api: tuple[httpx.AsyncClient, AsyncSession],
) -> None:
    """No web session to revoke; must not 500 (session_id is None)."""
    http, session = api
    user = await _fresh_user(http, session)
    response = await http.post(
        "/auth/logout", headers={"authorization": f"Bearer {_mint(user.id)}"}
    )
    assert response.status_code == 200
```

- [ ] **Step 2: Run to verify failure**

Run: `pytest tests/test_bearer_auth.py -v`
Expected: FAIL — bearer requests all 401 (only the cookie path exists).

- [ ] **Step 3: Implement the bearer path** — replace `backend/core/modules/identity/session_auth.py` with:

```python
"""The registered principal resolver + handler-side dependency (D09.C, D11).

require_auth rides the request-scoped get_session dependency, so the resolver
shares the endpoint's session/transaction - the last_seen_at touch commits
(or rolls back) with the endpoint's own writes.

Two credential shapes resolve here, cookie first:
- agri_sid session cookie (browsers on id.agri.in) -> resolve_web_session
- Authorization: Bearer <D08 access token> (BFF server-side calls, D11) ->
  resolve_bearer_token. Roles and status come FRESH from the DB, never from
  token claims: a suspension or role change beats the token's remaining
  lifetime (non-negotiable: one request cycle). aud is deliberately not
  pinned - this API is the resource server for every first-party client.
"""

import uuid
from typing import Annotated

from fastapi import Depends, Request
from joserfc import jwt
from joserfc.errors import JoseError
from sqlalchemy.ext.asyncio import AsyncSession

from modules.identity.oauth_keys import get_key_set
from modules.identity.oauth_service import load_token_subject
from modules.identity.session_limits import SESSION_COOKIE_NAME
from modules.identity.session_service import WebPrincipal, resolve_web_session
from settings import get_settings


async def resolve_principal(request: Request, session: AsyncSession) -> WebPrincipal | None:
    sid = request.cookies.get(SESSION_COOKIE_NAME)
    if sid:
        return await resolve_web_session(session, sid)
    header = request.headers.get("authorization", "")
    scheme, _, token = header.partition(" ")
    if scheme.lower() == "bearer" and token.strip():
        return await resolve_bearer_token(session, token.strip())
    return None


async def resolve_bearer_token(session: AsyncSession, token: str) -> WebPrincipal | None:
    """None for malformed, mis-signed, expired, wrong-issuer, unknown-subject,
    and suspended - indistinguishable to callers, all 401."""
    try:
        decoded = jwt.decode(token, get_key_set(), algorithms=["RS256"])
        jwt.JWTClaimsRegistry(
            iss={"essential": True, "value": get_settings().oauth_issuer},
            exp={"essential": True},
            sub={"essential": True},
        ).validate(decoded.claims)
        user_id = uuid.UUID(str(decoded.claims["sub"]))
    except (JoseError, ValueError):
        return None
    subject = await load_token_subject(session, user_id)
    if subject is None:  # suspended or gone: instant deny
        return None
    return WebPrincipal(
        user_id=subject.user_id,
        agri_id=subject.agri_id,
        roles=subject.roles,
        session_id=None,
        fingerprint=None,
    )


def current_principal(request: Request) -> WebPrincipal:
    principal = getattr(request.state, "principal", None)
    assert isinstance(principal, WebPrincipal), "route must be private (require_auth ran)"
    return principal


PrincipalDep = Annotated[WebPrincipal, Depends(current_principal)]
```

- [ ] **Step 4: Make `session_id` optional** — in `backend/core/modules/identity/session_service.py`, update the `WebPrincipal` dataclass field and docstring:

```python
@dataclass(frozen=True)
class WebPrincipal:
    """The resolved identity routers act on. Internal-only shape - response
    models re-expose agri_id and stringified session ids only. session_id is
    None for bearer-token principals (D11): no web session exists to revoke."""

    user_id: uuid.UUID
    agri_id: str
    roles: tuple[str, ...]
    session_id: uuid.UUID | None
    fingerprint: str | None
```

- [ ] **Step 5: Guard logout** — in `backend/core/modules/identity/session_router.py`, the `logout` handler's first line becomes:

```python
    if principal.session_id is not None:
        await revoke_web_session(
            session, session_id=principal.session_id, user_id=principal.user_id
        )
```

(`logout-everywhere` and `devices` need no change: `revoke_everything` takes user_id, and `row.id == principal.session_id` is False for None.)

- [ ] **Step 6: Run tests**

Run: `pytest tests/test_bearer_auth.py tests/test_session_router.py tests/test_devices_router.py -v`
Expected: PASS. Then `mypy .` from `backend/core` — expect clean (the `session_id` type change is why logout got guarded).

- [ ] **Step 7: Commit**

```bash
git add backend/core/modules/identity/session_auth.py backend/core/modules/identity/session_service.py backend/core/modules/identity/session_router.py backend/core/tests/test_bearer_auth.py
git commit -m "feat(d11): bearer access-token principal resolution for BFF calls"
```

---

### Task 6: Profile API — GET/PATCH with geo derivation, score recompute, completion event

**Files:**
- Create: `backend/core/modules/identity/profile_service.py`
- Create: `backend/core/modules/identity/profile_router.py`
- Modify: `backend/core/main.py` (imports at :17-23, `MODULE_ROUTERS` at :41-52)
- Test: `backend/core/tests/test_profile_router.py`

**Interfaces:**
- Consumes: Task 2 (`compute_completion`, `crossed_completion`), Task 4 (`require_permission`), `district_for_pincode` from `shared/geo/service.py`, `publish` from `shared/events.py`, `Profile`/`Preference`/`User` models.
- Produces: `GET /identity/profile` → `ProfileOut`; `PATCH /identity/profile` (body `ProfilePatchIn`); event `("identity", "profile.completed", {"user_id", "agri_id", "score"})`. Task 7 reuses `_profile_out`, `_commit_and_announce`, `recompute_score`. Task 13 (web-id UI) consumes the endpoints.
- Location contract: the client sends only a 6-digit `pincode`; the server derives district+state from the D03 geo snapshot (free-text state/district is rejected by `extra="forbid"`). Unknown pincode → 422 `unknown_pincode`.
- Score contract: GET computes the score LIVE (pure function over current state — pre-D11 rows self-heal); PATCH persists it to `profiles.completion_score`. Progressive-only v1: fields are set, never cleared, so scores only rise and each crossing fires once.

- [ ] **Step 1: Write the failing tests** — `backend/core/tests/test_profile_router.py`:

```python
"""D11.A/B: progressive profile updates, geo-derived location, visibility
toggles, live score, and exactly-one profile.completed per crossing."""

from collections.abc import AsyncIterator
from decimal import Decimal

import httpx
import pytest
from redis.asyncio import Redis
from sqlalchemy.ext.asyncio import AsyncSession

from main import create_app
from shared import storage
from shared.db import get_session
from shared.geo.models import District, Pincode, State
from tests.test_session_router import UA, _login

PHONE = "+919876522222"


@pytest.fixture
async def api(
    db_session: AsyncSession, otp_redis: Redis
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


@pytest.fixture
async def geo_row(db_session: AsyncSession) -> str:
    """One deterministic pincode; the committed snapshot is not loaded in tests."""
    state = State(lgd_code=33, name="Tamil Nadu")
    db_session.add(state)
    await db_session.flush()
    district = District(lgd_code=558, state_id=state.id, name="Erode")
    db_session.add(district)
    await db_session.flush()
    db_session.add(
        Pincode(
            pincode="638001",
            district_id=district.id,
            centroid_lat=Decimal("11.341000"),
            centroid_lon=Decimal("77.717000"),
        )
    )
    await db_session.flush()
    return "638001"


async def test_get_profile_before_any_update_scores_phone_only(
    api: tuple[httpx.AsyncClient, AsyncSession],
) -> None:
    http, session = api
    await _login(http, session, phone=PHONE)
    body = (await http.get("/identity/profile")).json()
    assert body["completion_score"] == 20  # phone verified at signup
    assert body["language"] is None and body["name"] is None
    assert body["visibility"] == {
        "avatar": False, "interests": False, "language": False, "location": False, "name": False,
    }


async def test_patch_name_language_interests(
    api: tuple[httpx.AsyncClient, AsyncSession],
) -> None:
    http, session = api
    await _login(http, session, phone=PHONE)
    response = await http.patch(
        "/identity/profile",
        json={"name": "  Asha  Farmer ", "language": "ta", "interests": ["Paddy", "paddy", "Drip irrigation"]},
    )
    assert response.status_code == 200
    body = response.json()
    assert body["name"] == "Asha Farmer"  # whitespace collapsed
    assert body["language"] == "ta"
    assert body["interests"] == ["Paddy", "Drip irrigation"]  # case-insensitive dedupe
    assert body["completion_score"] == 20 + 15 + 10 + 15


async def test_location_is_pincode_derived(
    api: tuple[httpx.AsyncClient, AsyncSession], geo_row: str
) -> None:
    http, session = api
    await _login(http, session, phone=PHONE)
    body = (await http.patch("/identity/profile", json={"pincode": geo_row})).json()
    assert body["state"] == "Tamil Nadu" and body["district"] == "Erode"
    assert body["completion_score"] == 20 + 25
    unknown = await http.patch("/identity/profile", json={"pincode": "999999"})
    assert unknown.status_code == 422 and unknown.json()["detail"] == "unknown_pincode"


async def test_free_text_location_is_rejected(
    api: tuple[httpx.AsyncClient, AsyncSession],
) -> None:
    http, session = api
    await _login(http, session, phone=PHONE)
    response = await http.patch("/identity/profile", json={"state": "Kerala"})
    assert response.status_code == 422  # extra="forbid"


async def test_visibility_toggles_validated_and_persisted(
    api: tuple[httpx.AsyncClient, AsyncSession],
) -> None:
    http, session = api
    await _login(http, session, phone=PHONE)
    ok = await http.patch("/identity/profile", json={"visibility": {"name": True, "location": True}})
    assert ok.json()["visibility"]["name"] is True
    bad = await http.patch("/identity/profile", json={"visibility": {"phone": True}})
    assert bad.status_code == 422 and bad.json()["detail"] == "unknown_visibility_key"


async def test_completed_event_exactly_once_per_crossing(
    api: tuple[httpx.AsyncClient, AsyncSession],
    geo_row: str,
    redis_client: Redis,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    async def fake_put_object(key: str, data: bytes, content_type: str) -> None:
        return None

    monkeypatch.setattr(storage, "put_object", fake_put_object)
    http, session = api
    await _login(http, session, phone=PHONE)
    await http.patch(
        "/identity/profile",
        json={"name": "Asha", "language": "ta", "interests": ["paddy"], "pincode": geo_row},
    )
    assert await redis_client.xlen("identity") == 0  # 85: not complete yet
    jpeg = b"\xff\xd8\xff\xe0" + b"\x00" * 64
    upload = await http.post(
        "/identity/profile/avatar", files={"file": ("me.jpg", jpeg, "image/jpeg")}
    )
    assert upload.status_code == 200
    assert upload.json()["completion_score"] == 100
    entries = await redis_client.xrange("identity")
    assert len(entries) == 1 and entries[0][1]["type"] == "profile.completed"
    # Same state again: no second crossing, no second event.
    await http.patch("/identity/profile", json={"name": "Asha Again"})
    assert await redis_client.xlen("identity") == 1
```

Note: the avatar POST in the last test lands in Task 7 — this one test stays red until Task 7 finishes; every other test here must pass at the end of THIS task. (Run it with `-k "not completed_event"` for this task's green gate.)

- [ ] **Step 2: Run to verify failure**

Run: `pytest tests/test_profile_router.py -v`
Expected: FAIL — 404s (`/identity/profile` doesn't exist).

- [ ] **Step 3: Implement the service** — `backend/core/modules/identity/profile_service.py`:

```python
"""Progressive profile updates + completion recompute (D11.A/B) - no HTTP.

Location is pincode-driven: clients send a pincode, the server derives
district/state from the D03 geo snapshot - free-text location is never
trusted (profiles.state/district are plain Text with no FK; this service is
the only writer). Progressive v1: fields are set, never cleared.

Functions take the caller's AsyncSession and flush but never commit.
"""

import uuid

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from modules.identity.completion import compute_completion, crossed_completion
from modules.identity.models import Preference, Profile, User
from shared.geo.models import State
from shared.geo.service import district_for_pincode

INTERESTS_MAX = 10
INTEREST_CHAR_MAX = 40
VISIBILITY_KEYS = frozenset({"name", "location", "language", "interests", "avatar"})


class ProfileUpdateError(ValueError):
    """Rejected update; .code is the API error detail."""

    def __init__(self, code: str) -> None:
        super().__init__(code)
        self.code = code


async def get_or_create_profile(session: AsyncSession, user_id: uuid.UUID) -> Profile:
    profile = await session.scalar(select(Profile).where(Profile.user_id == user_id))
    if profile is None:
        profile = Profile(user_id=user_id, language=None)
        session.add(profile)
        await session.flush()
    return profile


def normalize_name(raw: str) -> str:
    name = " ".join(raw.split())
    if not name:
        raise ProfileUpdateError("empty_name")
    return name


def normalize_interests(raw: list[str]) -> list[str]:
    """Free-form v1 (confirmed assumption): trim, collapse whitespace,
    case-insensitive dedupe preserving first spelling, caps enforced."""
    cleaned: list[str] = []
    seen: set[str] = set()
    for item in raw:
        text = " ".join(item.split())
        if not text:
            raise ProfileUpdateError("empty_interest")
        if len(text) > INTEREST_CHAR_MAX:
            raise ProfileUpdateError("interest_too_long")
        if text.lower() in seen:
            continue
        seen.add(text.lower())
        cleaned.append(text)
    if len(cleaned) > INTERESTS_MAX:
        raise ProfileUpdateError("too_many_interests")
    return cleaned


async def apply_location(session: AsyncSession, profile: Profile, pincode: str) -> None:
    district = await district_for_pincode(session, pincode)
    if district is None:
        raise ProfileUpdateError("unknown_pincode")
    state = await session.scalar(select(State).where(State.id == district.state_id))
    assert state is not None  # FK guarantees the parent row
    profile.pincode = pincode
    profile.district = district.name
    profile.state = state.name


async def get_visibility(session: AsyncSession, user_id: uuid.UUID) -> dict[str, bool]:
    """Private-by-default: absent keys read as False. Phone and email are not
    keys at all - they are never public (non-negotiable), not a toggle."""
    preference = await session.scalar(select(Preference).where(Preference.user_id == user_id))
    stored = preference.privacy if preference is not None else {}
    return {key: bool(stored.get(key, False)) for key in sorted(VISIBILITY_KEYS)}


async def set_visibility(
    session: AsyncSession, user_id: uuid.UUID, toggles: dict[str, bool]
) -> None:
    unknown = set(toggles) - VISIBILITY_KEYS
    if unknown:
        raise ProfileUpdateError("unknown_visibility_key")
    preference = await session.scalar(select(Preference).where(Preference.user_id == user_id))
    if preference is None:
        preference = Preference(user_id=user_id, notifications={}, privacy={})
        session.add(preference)
    preference.privacy = {**preference.privacy, **{k: bool(v) for k, v in toggles.items()}}
    await session.flush()


def live_score(user: User, profile: Profile | None) -> int:
    return compute_completion(
        phone_verified=user.phone_verified_at is not None,
        has_name=bool(profile is not None and profile.name),
        has_location=bool(
            profile is not None and profile.state and profile.district and profile.pincode
        ),
        has_language=profile is not None and profile.language is not None,
        has_interests=bool(profile is not None and profile.interests),
        has_avatar=profile is not None and profile.avatar_key is not None,
    )


async def recompute_score(
    session: AsyncSession, *, user: User, profile: Profile
) -> tuple[int, bool]:
    """Persist the recomputed score; True iff this update crossed into 100."""
    old = profile.completion_score
    new = live_score(user, profile)
    profile.completion_score = new
    await session.flush()
    return new, crossed_completion(old, new)
```

- [ ] **Step 4: Implement the router** — `backend/core/modules/identity/profile_router.py`:

```python
"""Own-profile endpoints (D11.A/B): GET/PATCH /identity/profile + avatar.

Per module rules nothing here logs bodies or query strings. All routes are
private (SecureRouter default) and additionally permission-gated - profile.*
are two of the three sample permissions the D11 tests pin the pattern on.
"""

from typing import Annotated, Literal

from fastapi import Depends, HTTPException, UploadFile
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from modules.identity.avatar import MAX_AVATAR_BYTES, AvatarError, avatar_object_key, validate_avatar
from modules.identity.models import Profile, User
from modules.identity.profile_service import (
    INTERESTS_MAX,
    ProfileUpdateError,
    apply_location,
    get_or_create_profile,
    get_visibility,
    live_score,
    normalize_interests,
    normalize_name,
    recompute_score,
    set_visibility,
)
from modules.identity.rbac import require_permission
from modules.identity.schemas import IdentityPublicSchema
from modules.identity.session_auth import PrincipalDep
from shared import storage
from shared.db import get_session
from shared.events import publish
from shared.security import SecureRouter
from shared.telemetry import get_logger

logger = get_logger(__name__)

profile_router = SecureRouter(prefix="/identity/profile", tags=["profile"])

SessionDep = Annotated[AsyncSession, Depends(get_session)]

EVENT_STREAM = "identity"


class ProfileOut(IdentityPublicSchema):
    agri_id: str
    name: str | None
    state: str | None
    district: str | None
    pincode: str | None
    language: str | None
    interests: list[str]
    has_avatar: bool
    completion_score: int
    visibility: dict[str, bool]


async def _load_user(session: AsyncSession, principal: PrincipalDep) -> User:
    user = await session.scalar(select(User).where(User.id == principal.user_id))
    assert user is not None  # the resolver proved existence this request
    return user


async def _profile_out(session: AsyncSession, user: User, profile: Profile | None) -> ProfileOut:
    return ProfileOut(
        agri_id=user.agri_id,
        name=profile.name if profile else None,
        state=profile.state if profile else None,
        district=profile.district if profile else None,
        pincode=profile.pincode if profile else None,
        language=profile.language if profile else None,
        interests=list(profile.interests) if profile else [],
        has_avatar=bool(profile is not None and profile.avatar_key),
        completion_score=live_score(user, profile),
        visibility=await get_visibility(session, user.id),
    )


@profile_router.get("", dependencies=[require_permission("profile.read")])
async def get_profile(principal: PrincipalDep, session: SessionDep) -> ProfileOut:
    """Live-computed score: pre-D11 rows (stored score 0) read correctly and
    self-heal on their next write."""
    user = await _load_user(session, principal)
    profile = await session.scalar(select(Profile).where(Profile.user_id == user.id))
    return await _profile_out(session, user, profile)


class ProfilePatchIn(BaseModel):
    """Progressive: only supplied fields change; nothing is cleared in v1.
    extra="forbid" is the free-text-location rejection (state/district are
    derived from pincode, never accepted)."""

    model_config = ConfigDict(extra="forbid")

    name: str | None = Field(default=None, min_length=1, max_length=80)
    pincode: str | None = Field(default=None, pattern=r"^\d{6}$")
    language: Literal["en", "ta", "hi"] | None = None
    interests: list[str] | None = Field(default=None, max_length=INTERESTS_MAX)
    visibility: dict[str, bool] | None = None


async def _commit_and_announce(session: AsyncSession, *, user: User, crossed: bool) -> None:
    """Commit BEFORE announcing: a profile.completed for a rolled-back update
    would hand out D13 coins for a state that never existed (mirrors D07's
    commit-before-respond precedent; expire_on_commit=False keeps the ORM
    objects readable for the response). After the commit the publish is
    best-effort - a Redis blip must not 500 a successful save."""
    await session.commit()
    if not crossed:
        return
    try:
        await publish(
            EVENT_STREAM,
            "profile.completed",
            {"user_id": str(user.id), "agri_id": user.agri_id, "score": 100},
        )
    except Exception as exc:
        logger.warning(
            "profile.completed.publish_failed",
            extra={"extra_fields": {"exc_type": type(exc).__name__}},
        )


@profile_router.patch("", dependencies=[require_permission("profile.write")])
async def patch_profile(
    body: ProfilePatchIn, principal: PrincipalDep, session: SessionDep
) -> ProfileOut:
    user = await _load_user(session, principal)
    profile = await get_or_create_profile(session, user.id)
    try:
        if body.name is not None:
            profile.name = normalize_name(body.name)
        if body.pincode is not None:
            await apply_location(session, profile, body.pincode)
        if body.language is not None:
            profile.language = body.language
        if body.interests is not None:
            profile.interests = normalize_interests(body.interests)
        if body.visibility is not None:
            await set_visibility(session, user.id, body.visibility)
    except ProfileUpdateError as exc:
        raise HTTPException(status_code=422, detail=exc.code) from exc
    _, crossed = await recompute_score(session, user=user, profile=profile)
    await _commit_and_announce(session, user=user, crossed=crossed)
    return await _profile_out(session, user, profile)


@profile_router.post("/avatar", dependencies=[require_permission("profile.write")])
async def upload_avatar(
    file: UploadFile, principal: PrincipalDep, session: SessionDep
) -> ProfileOut:
    """Multipart image upload. Type comes from magic bytes only - the part's
    Content-Type header is never consulted."""
    data = await file.read(MAX_AVATAR_BYTES + 1)
    try:
        content_type, ext = validate_avatar(data)
    except AvatarError as exc:
        raise HTTPException(status_code=422, detail=exc.code) from exc
    key = avatar_object_key(ext)
    try:
        await storage.put_object(key, data, content_type)
    except storage.StorageError as exc:
        raise HTTPException(status_code=503, detail="storage_unavailable") from exc
    user = await _load_user(session, principal)
    profile = await get_or_create_profile(session, user.id)
    profile.avatar_key = key
    _, crossed = await recompute_score(session, user=user, profile=profile)
    await _commit_and_announce(session, user=user, crossed=crossed)
    return await _profile_out(session, user, profile)
```

Note: `shared.storage.put_object` / `StorageError` don't exist until Task 7. To keep THIS task green, Task 6 and Task 7 are committed together only if needed — preferred order: implement Task 7's `storage.py` additions FIRST if the import fails, or temporarily leave `upload_avatar` out of this task and add it in Task 7. **Decision: leave `upload_avatar` and the two avatar imports OUT of this task's edit; Task 7 adds them.** The `test_completed_event_exactly_once_per_crossing` test stays deselected until Task 7.

- [ ] **Step 5: Mount the router** — in `backend/core/main.py` add the import (alphabetical with the other identity imports):

```python
from modules.identity.profile_router import profile_router as identity_profile_router
```

and in `MODULE_ROUTERS`, after `identity_otp_router`:

```python
    identity_profile_router,
```

- [ ] **Step 6: Run tests**

Run: `pytest tests/test_profile_router.py -v -k "not completed_event"`
Expected: PASS. Also `pytest tests/test_public_routes.py -v` (or the equivalent gate test) — public_routes.txt unchanged, no new public paths.

- [ ] **Step 7: Commit**

```bash
git add backend/core/modules/identity/profile_service.py backend/core/modules/identity/profile_router.py backend/core/main.py backend/core/tests/test_profile_router.py
git commit -m "feat(d11): progressive profile API with geo-derived location and completion score"
```

---

### Task 7: Avatar upload — MinIO storage client + POST /identity/profile/avatar

**Files:**
- Modify: `backend/core/shared/storage.py` (add client + put_object)
- Modify: `backend/core/settings.py:32-33` (dev-default MinIO creds)
- Modify: `backend/core/pyproject.toml:10-26` (add `minio` dependency)
- Modify: `backend/core/modules/identity/profile_router.py` (add `upload_avatar` + avatar/storage imports from Task 6's listing)
- Modify: `backend/core/tests/conftest.py` (`reset_storage` in `_reset_state`)
- Test: `backend/core/tests/test_profile_router.py` (the deselected event test goes green) + new avatar-route cases

**Interfaces:**
- Consumes: Task 3 (`validate_avatar`, `avatar_object_key`, `MAX_AVATAR_BYTES`), Task 6 (`_commit_and_announce`, `recompute_score`).
- Produces: `shared.storage.put_object(key: str, data: bytes, content_type: str) -> None` (async, raises `StorageError`); `shared.storage.reset_storage()`. `POST /identity/profile/avatar` (multipart field `file`) → `ProfileOut`.

- [ ] **Step 1: Add the failing route tests** — append to `backend/core/tests/test_profile_router.py`:

```python
async def test_avatar_upload_stores_and_scores(
    api: tuple[httpx.AsyncClient, AsyncSession], monkeypatch: pytest.MonkeyPatch
) -> None:
    calls: list[tuple[str, int, str]] = []

    async def fake_put_object(key: str, data: bytes, content_type: str) -> None:
        calls.append((key, len(data), content_type))

    monkeypatch.setattr(storage, "put_object", fake_put_object)
    http, session = api
    await _login(http, session, phone=PHONE)
    jpeg = b"\xff\xd8\xff\xe0" + b"\x00" * 64
    response = await http.post(
        "/identity/profile/avatar", files={"file": ("me.jpg", jpeg, "image/jpeg")}
    )
    assert response.status_code == 200
    body = response.json()
    assert body["has_avatar"] is True and body["completion_score"] == 20 + 15
    assert len(calls) == 1
    key, size, content_type = calls[0]
    assert key.startswith("avatars/") and key.endswith(".jpg")
    assert content_type == "image/jpeg" and size == len(jpeg)


async def test_avatar_rejects_lying_content_type(
    api: tuple[httpx.AsyncClient, AsyncSession], monkeypatch: pytest.MonkeyPatch
) -> None:
    async def fake_put_object(key: str, data: bytes, content_type: str) -> None:
        raise AssertionError("must not reach storage")

    monkeypatch.setattr(storage, "put_object", fake_put_object)
    http, session = api
    await _login(http, session, phone=PHONE)
    response = await http.post(
        "/identity/profile/avatar",
        files={"file": ("evil.jpg", b"<svg onload=alert(1)>", "image/jpeg")},
    )
    assert response.status_code == 422 and response.json()["detail"] == "unsupported_type"


async def test_avatar_storage_down_is_503_and_profile_untouched(
    api: tuple[httpx.AsyncClient, AsyncSession], monkeypatch: pytest.MonkeyPatch
) -> None:
    async def broken_put_object(key: str, data: bytes, content_type: str) -> None:
        raise storage.StorageError("down")

    monkeypatch.setattr(storage, "put_object", broken_put_object)
    http, session = api
    await _login(http, session, phone=PHONE)
    jpeg = b"\xff\xd8\xff\xe0" + b"\x00" * 64
    response = await http.post(
        "/identity/profile/avatar", files={"file": ("me.jpg", jpeg, "image/jpeg")}
    )
    assert response.status_code == 503
    assert (await http.get("/identity/profile")).json()["has_avatar"] is False
```

- [ ] **Step 2: Run to verify failure**

Run: `pytest tests/test_profile_router.py -v`
Expected: FAIL — 404 on `/identity/profile/avatar` and `AttributeError: shared.storage has no put_object`.

- [ ] **Step 3: Add the dependency and install** — in `backend/core/pyproject.toml` `dependencies`, after `"python-multipart>=0.0.9",`:

```toml
    "minio>=7.2",
```

Then from `backend/core`: `pip install -e .[dev]` (host venv). Add a mypy override if minio ships untyped (check: `python -c "import minio; print(minio.__file__)"` then run mypy; if it complains, extend the existing overrides block):

```toml
[[tool.mypy.overrides]]
module = ["minio.*"]
ignore_missing_imports = true
```

- [ ] **Step 4: Implement storage** — replace `backend/core/shared/storage.py`:

```python
"""Object storage access (MinIO locally, standing in for R2).

put_object is the entire D11 media surface: avatars only, bytes fully in
memory (2 MiB cap upstream). The minio client is sync - calls run in a
worker thread. Bucket auto-creation is a dev convenience; prod buckets are
provisioned, and the call is a cheap existence check afterwards.
"""

import asyncio
import io
from urllib.parse import urlparse

import httpx
from minio import Minio

from settings import get_settings

_client: Minio | None = None


class StorageError(RuntimeError):
    """Object storage is unreachable or rejected the write."""


def reset_storage() -> None:
    global _client
    _client = None


def get_storage_client() -> Minio:
    global _client
    if _client is None:
        settings = get_settings()
        parsed = urlparse(settings.minio_endpoint)
        _client = Minio(
            parsed.netloc,
            access_key=settings.minio_access_key,
            secret_key=settings.minio_secret_key,
            secure=parsed.scheme == "https",
        )
    return _client


async def put_object(key: str, data: bytes, content_type: str) -> None:
    def _put() -> None:
        client = get_storage_client()
        bucket = get_settings().minio_bucket
        if not client.bucket_exists(bucket):
            client.make_bucket(bucket)
        client.put_object(bucket, key, io.BytesIO(data), length=len(data), content_type=content_type)

    try:
        await asyncio.to_thread(_put)
    except Exception as exc:
        raise StorageError("object storage write failed") from exc


async def check_storage() -> bool:
    url = f"{get_settings().minio_endpoint}/minio/health/live"
    try:
        async with httpx.AsyncClient(timeout=2.0) as client:
            response = await client.get(url)
        return response.status_code == 200
    except httpx.HTTPError:
        return False
```

- [ ] **Step 5: Dev-default creds** — in `backend/core/settings.py` (matches docker-compose.dev.yml's dev-only credentials):

```python
    minio_access_key: str = "minioadmin"  # dev-only default, matches compose
    minio_secret_key: str = "minioadmin"  # dev-only default, matches compose
```

- [ ] **Step 6: Add the avatar route** — in `backend/core/modules/identity/profile_router.py`, add the imports Task 6 listed (`from modules.identity.avatar import ...`, `from shared import storage`) and the `upload_avatar` endpoint exactly as shown in Task 6 Step 4.

- [ ] **Step 7: Reset hook** — in `backend/core/tests/conftest.py` `_reset_state`, add `from shared.storage import reset_storage` and call `reset_storage()` after `reset_redis()`.

- [ ] **Step 8: Run the full profile suite (event test included)**

Run: `pytest tests/test_profile_router.py -v`
Expected: PASS — including `test_completed_event_exactly_once_per_crossing` (the exactly-once non-negotiable) and all three avatar cases.

- [ ] **Step 9: Commit**

```bash
git add backend/core/shared/storage.py backend/core/settings.py backend/core/pyproject.toml backend/core/modules/identity/profile_router.py backend/core/tests/conftest.py backend/core/tests/test_profile_router.py
git commit -m "feat(d11): avatar upload via minio-backed storage put_object"
```

---

### Task 8: Admin API — search, detail, roles, suspend/reactivate

**Files:**
- Create: `backend/core/modules/identity/admin_router.py`
- Modify: `backend/core/main.py` (import + `MODULE_ROUTERS`)
- Test: `backend/core/tests/test_admin_router.py`

**Interfaces:**
- Consumes: Task 4 (`require_permission`), Task 3 (`phone_last4`), `revoke_everything`, `notify_logout_everywhere`, `assign_role`/`UnknownRoleError`, `paginate`.
- Produces (all under prefix `/admin`, all private, keyed by agri_id — internal UUIDs never appear):
  - `GET /admin/users?q=&cursor=&limit=` → `AdminUserPage` — 4-digit `q` = phone-suffix match, else agri_id prefix. Permission `users.read`.
  - `GET /admin/users/{agri_id}` → `AdminUserDetailOut`. Permission `users.read`.
  - `POST /admin/users/{agri_id}/roles` body `{"role": str}` → `AdminRolesOut`. Permission `roles.assign`; assigning `super_admin` additionally requires the CALLER to hold `super_admin`.
  - `DELETE /admin/users/{agri_id}/roles/{role}` → `AdminRolesOut`. Same guards.
  - `POST /admin/users/{agri_id}/suspend` / `.../reactivate` → `StatusOut`. Permission `users.suspend`; suspend = status flip + `revoke_everything` + best-effort backchannel, all in one transaction; cannot self-suspend; suspending a super_admin requires super_admin.
- Audit placeholder (D12 owns the real hash-chained audit schema — do NOT build a table): structured `logger.warning` lines `admin.role_assigned` / `admin.role_removed` / `admin.user_suspended` / `admin.user_reactivated` with `extra_fields` = `{actor, target, role?}` using agri_ids only (never phone), shaped so D12 can swap in `audit()` at the same call sites.

- [ ] **Step 1: Write the failing tests** — `backend/core/tests/test_admin_router.py`:

```python
"""D11.D: admin surface. Non-negotiables pinned here: full phone never in any
admin response, suspension kills access within one request cycle, super_admin
assignment requires super_admin."""

import time
import uuid
from collections.abc import AsyncIterator

import httpx
import pytest
from joserfc import jwt
from redis.asyncio import Redis
from sqlalchemy import insert, select
from sqlalchemy.ext.asyncio import AsyncSession

from main import create_app
from modules.identity.models import Permission, Role, RolePermission, User
from modules.identity.oauth_keys import get_signing_key
from modules.identity.rbac import reset_permission_cache
from modules.identity.service import assign_role
from settings import get_settings
from shared.db import get_session
from tests.test_session_router import UA, _login

ADMIN_PHONE = "+919876533333"
TARGET_PHONE = "+919876544444"


@pytest.fixture
async def api(
    db_session: AsyncSession, otp_redis: Redis
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


async def _user(session: AsyncSession, phone: str) -> User:
    user = await session.scalar(select(User).where(User.phone == phone))
    assert user is not None
    return user


async def _login_admin(
    http: httpx.AsyncClient, session: AsyncSession, *, role: str = "staff"
) -> User:
    await _login(http, session, phone=ADMIN_PHONE)
    admin = await _user(session, ADMIN_PHONE)
    await assign_role(session, admin.id, role)
    return admin


async def _make_target(http: httpx.AsyncClient, session: AsyncSession) -> User:
    """Login as target (creates the account + a live session cookie snapshot),
    then restore no-cookie state for the admin login that follows."""
    await _login(http, session, phone=TARGET_PHONE)
    http.cookies.clear()
    return await _user(session, TARGET_PHONE)


async def test_search_last4_and_full_phone_never_rendered(
    api: tuple[httpx.AsyncClient, AsyncSession],
) -> None:
    http, session = api
    target = await _make_target(http, session)
    await _login_admin(http, session)
    response = await http.get("/admin/users", params={"q": TARGET_PHONE[-4:]})
    assert response.status_code == 200
    body = response.json()
    found = [item for item in body["items"] if item["agri_id"] == target.agri_id]
    assert len(found) == 1 and found[0]["phone_last4"] == TARGET_PHONE[-4:]
    # THE non-negotiable: the full number appears nowhere in the payload.
    assert TARGET_PHONE not in response.text and TARGET_PHONE.lstrip("+") not in response.text

    detail = await http.get(f"/admin/users/{target.agri_id}")
    assert detail.status_code == 200
    assert TARGET_PHONE not in detail.text and TARGET_PHONE.lstrip("+") not in detail.text


async def test_search_by_agri_id_prefix(api: tuple[httpx.AsyncClient, AsyncSession]) -> None:
    http, session = api
    target = await _make_target(http, session)
    await _login_admin(http, session)
    response = await http.get("/admin/users", params={"q": target.agri_id[:5]})
    assert any(item["agri_id"] == target.agri_id for item in response.json()["items"])


async def test_permission_denied_paths_per_role(
    api: tuple[httpx.AsyncClient, AsyncSession],
) -> None:
    http, session = api
    target = await _make_target(http, session)
    # plain user: nothing on /admin works
    await _login(http, session, phone=ADMIN_PHONE)
    assert (await http.get("/admin/users", params={"q": "1234"})).status_code == 403
    assert (
        await http.post(f"/admin/users/{target.agri_id}/suspend")
    ).status_code == 403
    assert (
        await http.post(f"/admin/users/{target.agri_id}/roles", json={"role": "farmer"})
    ).status_code == 403
    # staff: read + suspend yes, roles.assign no
    admin = await _user(session, ADMIN_PHONE)
    await assign_role(session, admin.id, "staff")
    assert (await http.get("/admin/users", params={"q": "1234"})).status_code == 200
    assert (
        await http.post(f"/admin/users/{target.agri_id}/roles", json={"role": "farmer"})
    ).status_code == 403
    # super_admin: everything
    await assign_role(session, admin.id, "super_admin")
    assert (
        await http.post(f"/admin/users/{target.agri_id}/roles", json={"role": "farmer"})
    ).status_code == 200


async def test_role_assign_remove_and_unknowns(
    api: tuple[httpx.AsyncClient, AsyncSession],
) -> None:
    http, session = api
    target = await _make_target(http, session)
    await _login_admin(http, session, role="super_admin")
    assigned = await http.post(f"/admin/users/{target.agri_id}/roles", json={"role": "farmer"})
    assert assigned.status_code == 200 and "farmer" in assigned.json()["roles"]
    duplicate = await http.post(f"/admin/users/{target.agri_id}/roles", json={"role": "farmer"})
    assert duplicate.status_code == 409
    unknown = await http.post(f"/admin/users/{target.agri_id}/roles", json={"role": "wizard"})
    assert unknown.status_code == 404
    removed = await http.request(
        "DELETE", f"/admin/users/{target.agri_id}/roles/farmer"
    )
    assert removed.status_code == 200 and "farmer" not in removed.json()["roles"]
    not_assigned = await http.request(
        "DELETE", f"/admin/users/{target.agri_id}/roles/farmer"
    )
    assert not_assigned.status_code == 404
    ghost = await http.post("/admin/users/does_not_exist/roles", json={"role": "farmer"})
    assert ghost.status_code == 404


async def test_super_admin_assignment_requires_super_admin(
    api: tuple[httpx.AsyncClient, AsyncSession],
) -> None:
    """Privilege-escalation guard. Staff normally lacks roles.assign entirely,
    so grant it temporarily - the guard must STILL refuse super_admin."""
    http, session = api
    target = await _make_target(http, session)
    admin = await _login_admin(http, session, role="staff")
    role_id = await session.scalar(select(Role.id).where(Role.name == "staff"))
    perm_id = await session.scalar(select(Permission.id).where(Permission.name == "roles.assign"))
    await session.execute(
        insert(RolePermission).values(id=uuid.uuid4(), role_id=role_id, permission_id=perm_id)
    )
    reset_permission_cache()
    escalate = await http.post(
        f"/admin/users/{target.agri_id}/roles", json={"role": "super_admin"}
    )
    assert escalate.status_code == 403
    assert escalate.json()["detail"] == "super_admin_required"
    # and removing super_admin from someone is equally guarded
    await assign_role(session, target.id, "super_admin")
    demote = await http.request(
        "DELETE", f"/admin/users/{target.agri_id}/roles/super_admin"
    )
    assert demote.status_code == 403


def _bearer(user_id: uuid.UUID) -> dict[str, str]:
    key = get_signing_key()
    now = int(time.time())
    claims = {
        "iss": get_settings().oauth_issuer,
        "sub": str(user_id),
        "aud": "web-admin",
        "iat": now,
        "exp": now + 900,
    }
    token = jwt.encode({"alg": "RS256", "kid": key.kid, "typ": "JWT"}, claims, key)
    return {"authorization": f"Bearer {token}"}


async def test_suspension_kills_all_access_and_reactivate_restores_login(
    api: tuple[httpx.AsyncClient, AsyncSession],
) -> None:
    http, session = api
    # the target gets their OWN client so their live cookie jar survives the
    # admin's login on the shared client (httpx forbids mixing per-request
    # cookies with a client jar)
    transport = http._transport  # same ASGI app
    async with httpx.AsyncClient(
        transport=transport, base_url="https://id.test", headers=UA
    ) as target_http:
        await _login(target_http, session, phone=TARGET_PHONE)
        target = await _user(session, TARGET_PHONE)
        target_bearer = _bearer(target.id)
        assert (await target_http.get("/auth/me")).status_code == 200  # alive pre-suspend
        await _login_admin(http, session)  # staff: has users.suspend

        suspended = await http.post(f"/admin/users/{target.agri_id}/suspend")
        assert suspended.status_code == 200
        again = await http.post(f"/admin/users/{target.agri_id}/suspend")
        assert again.status_code == 409

        # cookie dead within one request cycle
        assert (await target_http.get("/auth/me")).status_code == 401
        # bearer dead too (fresh DB status check beats token lifetime)
        assert (await http.get("/auth/me", headers=target_bearer)).status_code == 401

        reactivated = await http.post(f"/admin/users/{target.agri_id}/reactivate")
        assert reactivated.status_code == 200
        # old sessions stay revoked (revoke_everything is not undone) ...
        assert (await target_http.get("/auth/me")).status_code == 401
        # ... but the account itself works again
        assert (await http.get("/auth/me", headers=target_bearer)).status_code == 200


async def test_cannot_suspend_self_or_super_admin_as_staff(
    api: tuple[httpx.AsyncClient, AsyncSession],
) -> None:
    http, session = api
    target = await _make_target(http, session)
    admin = await _login_admin(http, session)  # staff
    await assign_role(session, target.id, "super_admin")
    assert (
        await http.post(f"/admin/users/{target.agri_id}/suspend")
    ).status_code == 403
    assert (await http.post(f"/admin/users/{admin.agri_id}/suspend")).status_code == 400


async def test_audit_lines_use_agri_ids_never_phone(
    api: tuple[httpx.AsyncClient, AsyncSession], caplog: pytest.LogCaptureFixture
) -> None:
    http, session = api
    target = await _make_target(http, session)
    await _login_admin(http, session, role="super_admin")
    with caplog.at_level("WARNING"):
        await http.post(f"/admin/users/{target.agri_id}/roles", json={"role": "farmer"})
        await http.post(f"/admin/users/{target.agri_id}/suspend")
    events = {record.message for record in caplog.records}
    assert "admin.role_assigned" in events and "admin.user_suspended" in events
    for record in caplog.records:
        fields = getattr(record, "extra_fields", {})
        assert TARGET_PHONE not in str(fields) and TARGET_PHONE not in record.message
```

- [ ] **Step 2: Run to verify failure**

Run: `pytest tests/test_admin_router.py -v`
Expected: FAIL — 404 everywhere (`/admin` doesn't exist).

- [ ] **Step 3: Implement** — `backend/core/modules/identity/admin_router.py`:

```python
"""Admin user management (D11.D). Threat model: admin is a PII-leak surface
and a privilege-escalation surface.

- Users are addressed by agri_id everywhere - internal UUIDs never appear.
- The full phone never renders: search accepts a 4-digit suffix, responses
  carry phone_last4 only (non-negotiable 2, pinned by tests).
- roles.assign gates role changes; touching the super_admin role additionally
  requires the CALLER to hold super_admin (escalation guard).
- Suspend = status flip + revoke_everything in ONE transaction (takes effect
  within one request cycle: the resolver re-checks status on every request)
  + best-effort back-channel to BFFs. Suspend is not delete - no row is
  removed anywhere.
- Audit: structured logger.warning placeholders; D12's audit schema replaces
  these call-site-for-call-site. Per module rules nothing logs bodies or
  query strings.
"""

import re
import uuid
from datetime import datetime
from typing import Annotated, Literal

from fastapi import Depends, HTTPException, Request
from pydantic import BaseModel
from sqlalchemy import delete, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from modules.identity.backchannel import notify_logout_everywhere
from modules.identity.models import Profile, Role, User, UserRole
from modules.identity.phone import phone_last4
from modules.identity.rbac import require_permission
from modules.identity.schemas import IdentityPublicSchema
from modules.identity.service import UnknownRoleError, assign_role
from modules.identity.session_auth import PrincipalDep
from modules.identity.session_service import revoke_everything
from shared.db import get_session
from shared.pagination import paginate
from shared.security import SecureRouter
from shared.telemetry import get_logger

logger = get_logger(__name__)

admin_router = SecureRouter(prefix="/admin", tags=["admin"])

SessionDep = Annotated[AsyncSession, Depends(get_session)]

SUPER_ADMIN = "super_admin"
_LAST4_RE = re.compile(r"^\d{4}$")


class AdminUserOut(IdentityPublicSchema):
    agri_id: str
    phone_last4: str
    status: str
    name: str | None
    roles: list[str]
    created_at: datetime


class AdminUserPage(BaseModel):
    items: list[AdminUserOut]
    next_cursor: str | None


class AdminUserDetailOut(AdminUserOut):
    state: str | None
    district: str | None
    pincode: str | None
    language: str | None
    interests: list[str]
    has_avatar: bool
    completion_score: int


class StatusOut(BaseModel):
    status: Literal["ok"] = "ok"


async def _roles_by_user(
    session: AsyncSession, user_ids: list[uuid.UUID]
) -> dict[uuid.UUID, list[str]]:
    if not user_ids:
        return {}
    rows = await session.execute(
        select(UserRole.user_id, Role.name)
        .join(Role, Role.id == UserRole.role_id)
        .where(UserRole.user_id.in_(user_ids))
        .order_by(Role.name)
    )
    grouped: dict[uuid.UUID, list[str]] = {}
    for user_id, role_name in rows:
        grouped.setdefault(user_id, []).append(role_name)
    return grouped


async def _target_user(session: AsyncSession, agri_id: str) -> User:
    user = await session.scalar(select(User).where(User.agri_id == agri_id))
    if user is None:
        raise HTTPException(status_code=404, detail="unknown_user")
    return user


def _audit(action: str, *, actor: str, target: str, role: str | None = None) -> None:
    fields: dict[str, str] = {"actor": actor, "target": target}
    if role is not None:
        fields["role"] = role
    logger.warning(action, extra={"extra_fields": fields})


@admin_router.get("/users", dependencies=[require_permission("users.read")])
async def search_users(
    q: str,
    principal: PrincipalDep,
    session: SessionDep,
    cursor: str | None = None,
    limit: int = 20,
) -> AdminUserPage:
    """4 digits = phone-suffix match (the ONLY way phone is searchable);
    anything else matches agri_id as an escaped prefix."""
    q = q.strip()
    if not 1 <= len(q) <= 64:
        raise HTTPException(status_code=422, detail="bad_query")
    if _LAST4_RE.fullmatch(q):
        condition = User.phone.endswith(q)
    else:
        condition = User.agri_id.istartswith(q, autoescape=True)
    page = await paginate(session, select(User).where(condition), cursor=cursor, limit=limit)
    roles = await _roles_by_user(session, [user.id for user in page.items])
    names = dict(
        (
            await session.execute(
                select(Profile.user_id, Profile.name).where(
                    Profile.user_id.in_([user.id for user in page.items])
                )
            )
        ).all()
    ) if page.items else {}
    return AdminUserPage(
        items=[
            AdminUserOut(
                agri_id=user.agri_id,
                phone_last4=phone_last4(user.phone),
                status=user.status,
                name=names.get(user.id),
                roles=roles.get(user.id, []),
                created_at=user.created_at,
            )
            for user in page.items
        ],
        next_cursor=page.next_cursor,
    )


async def _detail(session: AsyncSession, user: User) -> AdminUserDetailOut:
    profile = await session.scalar(select(Profile).where(Profile.user_id == user.id))
    roles = await _roles_by_user(session, [user.id])
    return AdminUserDetailOut(
        agri_id=user.agri_id,
        phone_last4=phone_last4(user.phone),
        status=user.status,
        name=profile.name if profile else None,
        roles=roles.get(user.id, []),
        created_at=user.created_at,
        state=profile.state if profile else None,
        district=profile.district if profile else None,
        pincode=profile.pincode if profile else None,
        language=profile.language if profile else None,
        interests=list(profile.interests) if profile else [],
        has_avatar=bool(profile is not None and profile.avatar_key),
        completion_score=profile.completion_score if profile else 0,
    )


@admin_router.get("/users/{agri_id}", dependencies=[require_permission("users.read")])
async def get_user(agri_id: str, principal: PrincipalDep, session: SessionDep) -> AdminUserDetailOut:
    return await _detail(session, await _target_user(session, agri_id))


class AdminRolesOut(IdentityPublicSchema):
    agri_id: str
    roles: list[str]


class RoleIn(BaseModel):
    role: str


def _guard_super_admin(role: str, principal: PrincipalDep) -> None:
    """Escalation guard: only super_admins may grant or revoke super_admin,
    regardless of how the caller came by roles.assign."""
    if role == SUPER_ADMIN and SUPER_ADMIN not in principal.roles:
        raise HTTPException(status_code=403, detail="super_admin_required")


async def _roles_out(session: AsyncSession, user: User) -> AdminRolesOut:
    roles = await _roles_by_user(session, [user.id])
    return AdminRolesOut(agri_id=user.agri_id, roles=roles.get(user.id, []))


@admin_router.post("/users/{agri_id}/roles", dependencies=[require_permission("roles.assign")])
async def add_role(
    agri_id: str, body: RoleIn, principal: PrincipalDep, session: SessionDep
) -> AdminRolesOut:
    user = await _target_user(session, agri_id)
    _guard_super_admin(body.role, principal)
    try:
        await assign_role(session, user.id, body.role)
    except UnknownRoleError as exc:
        raise HTTPException(status_code=404, detail="unknown_role") from exc
    except IntegrityError as exc:
        await session.rollback()
        raise HTTPException(status_code=409, detail="already_assigned") from exc
    _audit("admin.role_assigned", actor=principal.agri_id, target=user.agri_id, role=body.role)
    return await _roles_out(session, user)


@admin_router.delete(
    "/users/{agri_id}/roles/{role}", dependencies=[require_permission("roles.assign")]
)
async def remove_role(
    agri_id: str, role: str, principal: PrincipalDep, session: SessionDep
) -> AdminRolesOut:
    user = await _target_user(session, agri_id)
    _guard_super_admin(role, principal)
    role_id = await session.scalar(select(Role.id).where(Role.name == role))
    if role_id is None:
        raise HTTPException(status_code=404, detail="unknown_role")
    result = await session.execute(
        delete(UserRole)
        .where(UserRole.user_id == user.id, UserRole.role_id == role_id)
        .returning(UserRole.id)
    )
    if result.first() is None:
        raise HTTPException(status_code=404, detail="not_assigned")
    _audit("admin.role_removed", actor=principal.agri_id, target=user.agri_id, role=role)
    return await _roles_out(session, user)


async def _guard_suspend_target(
    session: AsyncSession, user: User, principal: PrincipalDep
) -> None:
    if user.id == principal.user_id:
        raise HTTPException(status_code=400, detail="cannot_suspend_self")
    target_roles = (await _roles_by_user(session, [user.id])).get(user.id, [])
    if SUPER_ADMIN in target_roles and SUPER_ADMIN not in principal.roles:
        raise HTTPException(status_code=403, detail="super_admin_required")


@admin_router.post(
    "/users/{agri_id}/suspend", dependencies=[require_permission("users.suspend")]
)
async def suspend_user(
    agri_id: str, principal: PrincipalDep, request: Request, session: SessionDep
) -> StatusOut:
    user = await _target_user(session, agri_id)
    await _guard_suspend_target(session, user, principal)
    if user.status == "suspended":
        raise HTTPException(status_code=409, detail="already_suspended")
    user.status = "suspended"
    await revoke_everything(session, user.id)
    try:
        await notify_logout_everywhere(session, user.id)
    except Exception as exc:
        # a dead BFF must never roll back the suspension (mirrors D09's
        # logout-everywhere handler; exc message never logged - PII risk)
        logger.warning(
            "backchannel.logout.notify_failed",
            extra={"extra_fields": {"exc_type": type(exc).__name__}},
        )
    _audit("admin.user_suspended", actor=principal.agri_id, target=user.agri_id)
    return StatusOut()


@admin_router.post(
    "/users/{agri_id}/reactivate", dependencies=[require_permission("users.suspend")]
)
async def reactivate_user(
    agri_id: str, principal: PrincipalDep, session: SessionDep
) -> StatusOut:
    user = await _target_user(session, agri_id)
    if user.status != "suspended":
        raise HTTPException(status_code=409, detail="not_suspended")
    user.status = "active"
    await session.flush()
    _audit("admin.user_reactivated", actor=principal.agri_id, target=user.agri_id)
    return StatusOut()
```

- [ ] **Step 4: Mount** — in `backend/core/main.py`:

```python
from modules.identity.admin_router import admin_router as identity_admin_router
```

and in `MODULE_ROUTERS`, before `identity_router` (alphabetical within the identity block):

```python
    identity_admin_router,
```

- [ ] **Step 5: Run tests**

Run: `pytest tests/test_admin_router.py -v`
Expected: PASS — all nine, including the three non-negotiable pins.

- [ ] **Step 6: Commit**

```bash
git add backend/core/modules/identity/admin_router.py backend/core/main.py backend/core/tests/test_admin_router.py
git commit -m "feat(d11): admin user search, role management, suspend/reactivate"
```

---

### Task 9: Backend gate

**Files:** none new — verification only (fix whatever it surfaces).

- [ ] **Step 1: Full backend gate** (from `backend/core`, Bash tool):

```bash
cd backend/core && set -o pipefail && \
ruff format . && ruff check . && mypy . && lint-imports && pytest -q
```

Expected: all green. Common traps: `ruff format` reflows long select() chains — rerun tests after; mypy on `params.Depends` return type; the OFFSET lint gate (we used `paginate` everywhere).

- [ ] **Step 2: Public routes gate**

```bash
cd backend/core && python scripts/dump_public_routes.py --check
```

Expected: exit 0, `public_routes.txt` unchanged (D11 adds zero public routes).

- [ ] **Step 3: Commit any gate fixes**

```bash
git add -A && git commit -m "chore(d11): backend gate fixes" # only if fixes were needed
```

---

### Task 10: `@agri/auth-client` — `getAccessToken()`

**Files:**
- Modify: `packages/auth-client/src/server.ts`
- Modify: `packages/auth-client/src/index.ts`
- Modify: `packages/auth-client/README.md` (document the new accessor)
- Test: `packages/auth-client/src/server.test.ts`

**Interfaces:**
- Consumes: `readSession`, `ResolvedConfig`, `SessionPayload.accessToken/accessExpiresAt`.
- Produces: `AgriAuth.getAccessToken(): Promise<string | null>` — server-side only, read-only (expired/role-disallowed/missing → null; callers heal via `GET /api/auth/me`, which owns rotation). Task 11's proxy consumes it.

- [ ] **Step 1: Write the failing tests** — append to `packages/auth-client/src/server.test.ts` (reuses the existing `cookieStore` mock and `sessionCookieValue` helper in that file):

```ts
import { getAccessToken } from "./server";

describe("getAccessToken", () => {
  it("valid session -> raw access token (server-side only)", async () => {
    cookieStore.get.mockReturnValue({ value: await sessionCookieValue() });
    expect(await getAccessToken(cfg)).toBe("at");
  });

  it("no cookie -> null", async () => {
    cookieStore.get.mockReturnValue(undefined);
    expect(await getAccessToken(cfg)).toBeNull();
  });

  it("expired access token -> null (caller heals via /api/auth/me)", async () => {
    cookieStore.get.mockReturnValue({
      value: await sessionCookieValue({ accessExpiresAt: Math.floor(Date.now() / 1000) - 10 }),
    });
    expect(await getAccessToken(cfg)).toBeNull();
  });

  it("requiredRoles unmet -> null (admin gate holds for tokens too)", async () => {
    cookieStore.get.mockReturnValue({ value: await sessionCookieValue({}, adminCfg) });
    expect(await getAccessToken(adminCfg)).toBeNull();
  });

  it("denylisted sub -> null", async () => {
    recordLogout("sub-1", Math.floor(Date.now() / 1000) + 5);
    cookieStore.get.mockReturnValue({ value: await sessionCookieValue() });
    expect(await getAccessToken(cfg)).toBeNull();
  });
});
```

(Adjust the `import { getServerUser } from "./server";` line to also import `getAccessToken`.)

- [ ] **Step 2: Run to verify failure**

Run: `pnpm --filter @agri/auth-client test`
Expected: FAIL — `getAccessToken` is not exported.

- [ ] **Step 3: Implement** — in `packages/auth-client/src/server.ts`, refactor the shared read into a helper and add the accessor:

```ts
import type { ResolvedConfig } from "./config";
import { readSession } from "./handlers";
import { projectUser, type AgriUser, type SessionPayload } from "./session";

async function readValidSession(cfg: ResolvedConfig): Promise<SessionPayload | null> {
  const { cookies } = await import("next/headers");
  const store = await cookies();
  const raw = store.get(cfg.sessionCookie)?.value;
  const session = await readSession(cfg, raw ? `${cfg.sessionCookie}=${raw}` : null);
  if (!session) return null;
  if (session.accessExpiresAt <= Math.floor(Date.now() / 1000)) return null;
  if (cfg.requiredRoles.length && !cfg.requiredRoles.some((r) => session.roles.includes(r)))
    return null;
  return session;
}

export async function getServerUser(cfg: ResolvedConfig): Promise<AgriUser | null> {
  const session = await readValidSession(cfg);
  return session ? projectUser(session) : null;
}

/**
 * SERVER-SIDE ONLY: the raw D08 access token for backend calls
 * (Authorization: Bearer). Read-only like getServerUser - an expired token
 * reads as null and the caller retries after GET /api/auth/me rotates the
 * session. Never hand this value to client components.
 */
export async function getAccessToken(cfg: ResolvedConfig): Promise<string | null> {
  const session = await readValidSession(cfg);
  return session?.accessToken ?? null;
}
```

- [ ] **Step 4: Expose on `AgriAuth`** — in `packages/auth-client/src/index.ts`, update the import, interface, and factory return:

```ts
import { getAccessToken, getServerUser } from "./server";
```

```ts
export interface AgriAuth {
  handlers: ReturnType<typeof createHandlers>;
  /** Read-only session view for RSC - never refreshes (route handlers own
   * cookie writes); a stale session reads as null and useAgriUser() heals it. */
  getServerUser(): Promise<AgriUser | null>;
  /** Server-side only: bearer token for backend API calls. Stale -> null;
   * call GET /api/auth/me to rotate, then retry once. */
  getAccessToken(): Promise<string | null>;
}
```

```ts
    getServerUser: async () => getServerUser(cfg()),
    getAccessToken: async () => getAccessToken(cfg()),
```

Also re-export at the bottom of the existing export block: `export { getServerUser, getAccessToken } from "./server";` (replacing the current `getServerUser`-only line).

- [ ] **Step 5: Run tests + typecheck**

Run: `pnpm --filter @agri/auth-client test && pnpm --filter @agri/auth-client typecheck`
Expected: PASS.

- [ ] **Step 6: README** — add a short section to `packages/auth-client/README.md` under the existing API docs:

```markdown
### `auth.getAccessToken()`

Server-side only. Returns the session's D08 access token for calling the
backend API with `Authorization: Bearer <token>`, or `null` when the session
is missing/stale/role-disallowed. It never refreshes: on `null` (or a 401
from the API), call `GET /api/auth/me` (which owns rotation) and retry once.
Never pass the token to client components.
```

- [ ] **Step 7: Commit**

```bash
git add packages/auth-client
git commit -m "feat(d11): getAccessToken accessor on auth-client"
```

---

### Task 11: web-admin backend proxy + API helper

**Files:**
- Create: `apps/web-admin/app/api/admin/[...path]/route.ts`
- Create: `apps/web-admin/lib/api.ts`

**Interfaces:**
- Consumes: Task 10 (`auth.getAccessToken()`), backend `/admin/*` (Task 8).
- Produces: same-origin `/api/admin/<path>` (GET/POST/DELETE) forwarding to `${API_BASE_URL}/admin/<path>` with the bearer attached server-side; `getJson/postJson/deleteJson` client helpers with one 401-heal-retry. Task 12 consumes both.

- [ ] **Step 1: Proxy route** — `apps/web-admin/app/api/admin/[...path]/route.ts`:

```ts
/**
 * BFF proxy: browser -> same-origin /api/admin/* -> FastAPI /admin/* with the
 * session's bearer token attached HERE, server-side (tokens never touch JS -
 * D10 non-negotiable). Only the backend's /admin prefix is reachable through
 * this route by construction.
 */
import { NextRequest, NextResponse } from "next/server";

import { auth } from "@/lib/auth";

const API = process.env.API_BASE_URL ?? "http://127.0.0.1:8000";

async function forward(
  req: NextRequest,
  params: Promise<{ path: string[] }>,
  method: "GET" | "POST" | "DELETE",
): Promise<NextResponse> {
  const token = await auth.getAccessToken();
  if (!token) return NextResponse.json({ detail: "unauthenticated" }, { status: 401 });
  const { path } = await params;
  const url = new URL(`${API}/admin/${path.map(encodeURIComponent).join("/")}`);
  url.search = req.nextUrl.search;
  const upstream = await fetch(url, {
    method,
    headers: {
      authorization: `Bearer ${token}`,
      ...(method === "POST" ? { "content-type": "application/json" } : {}),
    },
    body: method === "POST" ? await req.text() : undefined,
    cache: "no-store",
  });
  const body = (await upstream.json().catch(() => ({}))) as Record<string, unknown>;
  return NextResponse.json(body, { status: upstream.status });
}

type Ctx = { params: Promise<{ path: string[] }> };

export async function GET(req: NextRequest, ctx: Ctx): Promise<NextResponse> {
  return forward(req, ctx.params, "GET");
}
export async function POST(req: NextRequest, ctx: Ctx): Promise<NextResponse> {
  return forward(req, ctx.params, "POST");
}
export async function DELETE(req: NextRequest, ctx: Ctx): Promise<NextResponse> {
  return forward(req, ctx.params, "DELETE");
}
```

- [ ] **Step 2: Client helper** — `apps/web-admin/lib/api.ts` (mirrors web-id's `lib/api.ts` shape, plus the documented heal-retry from Task 10):

```ts
/**
 * Same-origin calls to /api/admin/* (the BFF proxy). Access tokens live ~15
 * minutes; on a 401 we ask /api/auth/me to rotate the session cookie, then
 * retry exactly once.
 */
export class ApiError extends Error {
  constructor(
    public readonly status: number,
    public readonly detail: string,
  ) {
    super(`${status}: ${detail}`);
  }
}

interface JsonBody {
  [key: string]: unknown;
}

async function parse(response: Response): Promise<JsonBody> {
  const body = (await response.json().catch(() => ({}))) as JsonBody;
  if (!response.ok) {
    throw new ApiError(response.status, String(body.detail ?? body.error ?? "request_failed"));
  }
  return body;
}

async function request(path: string, init?: RequestInit): Promise<JsonBody> {
  const url = `/api/admin${path}`;
  const first = await fetch(url, init);
  if (first.status !== 401) return parse(first);
  await fetch("/api/auth/me"); // rotates a stale session cookie
  return parse(await fetch(url, init));
}

export function getJson(path: string): Promise<JsonBody> {
  return request(path);
}

export function postJson(path: string, payload?: unknown): Promise<JsonBody> {
  return request(path, {
    method: "POST",
    headers: { "content-type": "application/json" },
    body: JSON.stringify(payload ?? {}),
  });
}

export function deleteJson(path: string): Promise<JsonBody> {
  return request(path, { method: "DELETE" });
}
```

- [ ] **Step 3: Typecheck + lint**

Run: `pnpm --filter web-admin typecheck && pnpm --filter web-admin lint`
Expected: PASS.

- [ ] **Step 4: Commit**

```bash
git add apps/web-admin/app/api/admin apps/web-admin/lib/api.ts
git commit -m "feat(d11): web-admin bearer proxy and api helper"
```

---

### Task 12: web-admin users UI

**Files:**
- Create: `apps/web-admin/app/users/page.tsx`, `apps/web-admin/app/users/users-manager.tsx`
- Modify: `apps/web-admin/app/page.tsx` (link to /users)
- Modify: `packages/ui/src/i18n/messages/en.json`, `ta.json`, `hi.json` (add `ui.admin` block)

**Interfaces:**
- Consumes: Task 11 helpers, `auth.getServerUser()`, `@agri/ui` (`Card`, `Button`, `Badge`, `Modal`, `SearchBar` or a plain input, `useToast`, `Skeleton`, `EmptyState`), `useTranslations("ui.admin")`.
- Produces: `/users` — search by handle or phone last-4, result list with load-more (cursor), detail panel with roles (assign/remove from the five known roles) and suspend/reactivate with confirm modal.

- [ ] **Step 1: i18n strings** — add to `packages/ui/src/i18n/messages/en.json` under `"ui"` (sibling of `"auth"`):

```json
"admin": {
  "users": {
    "title": "Users",
    "searchLabel": "Search users",
    "searchPlaceholder": "@handle or last 4 digits of phone",
    "search": "Search",
    "empty": "No users match",
    "loadMore": "Load more",
    "phoneEnding": "Phone ending {last4}",
    "status": { "active": "Active", "suspended": "Suspended", "deleted": "Deleted" },
    "roles": "Roles",
    "addRole": "Add role",
    "removeRole": "Remove {role}",
    "suspend": "Suspend",
    "reactivate": "Reactivate",
    "confirmSuspend": "Suspend {agriId}? All their sessions on every app are signed out immediately.",
    "confirmReactivate": "Reactivate {agriId}? Suspension is lifted; they must sign in again.",
    "cancel": "Cancel",
    "suspended": "User suspended",
    "reactivated": "User reactivated",
    "roleAdded": "Role added",
    "roleRemoved": "Role removed",
    "completion": "Profile completion",
    "location": "Location",
    "language": "Language",
    "interests": "Interests",
    "error": "That didn't work — try again"
  }
}
```

Add the same keys with Tamil / Hindi translations to `ta.json` / `hi.json` (translate values, keep keys identical — follow the tone of the existing `auth` block translations in each file).

- [ ] **Step 2: RSC page** — `apps/web-admin/app/users/page.tsx`:

```tsx
import { redirect } from "next/navigation";

import { auth } from "@/lib/auth";

import { UsersManager } from "./users-manager";

export default async function UsersPage() {
  const user = await auth.getServerUser();
  if (!user) redirect("/api/auth/login?next=/users");
  return <UsersManager />;
}
```

- [ ] **Step 3: Client manager** — `apps/web-admin/app/users/users-manager.tsx`. Full implementation:

```tsx
"use client";

/** Admin user console (D11.D). Phone renders as last-4 ONLY - the API never
 * sends more, and this component must never try to reconstruct it. */

import { useState } from "react";
import { useTranslations } from "next-intl";

import { Badge, Button, Card, EmptyState, Modal, Skeleton, cn, useToast } from "@agri/ui";

import { ApiError, deleteJson, getJson, postJson } from "@/lib/api";

interface AdminUser {
  agri_id: string;
  phone_last4: string;
  status: "active" | "suspended" | "deleted";
  name: string | null;
  roles: string[];
  created_at: string;
}

interface AdminUserDetail extends AdminUser {
  state: string | null;
  district: string | null;
  pincode: string | null;
  language: string | null;
  interests: string[];
  has_avatar: boolean;
  completion_score: number;
}

const ASSIGNABLE_ROLES = ["user", "farmer", "business_owner", "staff", "super_admin"] as const;

export function UsersManager() {
  const t = useTranslations("ui.admin.users");
  const { toast } = useToast();
  const [query, setQuery] = useState("");
  const [items, setItems] = useState<AdminUser[]>([]);
  const [nextCursor, setNextCursor] = useState<string | null>(null);
  const [searched, setSearched] = useState(false);
  const [loading, setLoading] = useState(false);
  const [detail, setDetail] = useState<AdminUserDetail | null>(null);
  const [confirm, setConfirm] = useState<"suspend" | "reactivate" | null>(null);

  const search = async (cursor?: string) => {
    if (!query.trim()) return;
    setLoading(true);
    try {
      const params = new URLSearchParams({ q: query.trim() });
      if (cursor) params.set("cursor", cursor);
      const body = (await getJson(`/users?${params}`)) as unknown as {
        items: AdminUser[];
        next_cursor: string | null;
      };
      setItems(cursor ? [...items, ...body.items] : body.items);
      setNextCursor(body.next_cursor);
      setSearched(true);
    } catch {
      toast({ title: t("error") });
    } finally {
      setLoading(false);
    }
  };

  const open = async (agriId: string) => {
    try {
      setDetail((await getJson(`/users/${encodeURIComponent(agriId)}`)) as unknown as AdminUserDetail);
    } catch {
      toast({ title: t("error") });
    }
  };

  const refresh = async (agriId: string) => {
    await open(agriId);
    await search();
  };

  const addRole = async (role: string) => {
    if (!detail) return;
    try {
      await postJson(`/users/${encodeURIComponent(detail.agri_id)}/roles`, { role });
      toast({ title: t("roleAdded") });
      await refresh(detail.agri_id);
    } catch (error) {
      toast({ title: error instanceof ApiError ? error.detail : t("error") });
    }
  };

  const removeRole = async (role: string) => {
    if (!detail) return;
    try {
      await deleteJson(`/users/${encodeURIComponent(detail.agri_id)}/roles/${encodeURIComponent(role)}`);
      toast({ title: t("roleRemoved") });
      await refresh(detail.agri_id);
    } catch (error) {
      toast({ title: error instanceof ApiError ? error.detail : t("error") });
    }
  };

  const setSuspension = async () => {
    if (!detail || !confirm) return;
    const action = confirm;
    setConfirm(null);
    try {
      await postJson(`/users/${encodeURIComponent(detail.agri_id)}/${action}`);
      toast({ title: t(action === "suspend" ? "suspended" : "reactivated") });
      await refresh(detail.agri_id);
    } catch (error) {
      toast({ title: error instanceof ApiError ? error.detail : t("error") });
    }
  };

  return (
    <main className="mx-auto max-w-3xl space-y-4 p-4">
      <h1 className="text-xl font-bold text-ink">{t("title")}</h1>
      <form
        className="flex gap-2"
        onSubmit={(event) => {
          event.preventDefault();
          void search();
        }}
      >
        <input
          className="min-w-0 flex-1 rounded-btn border border-line bg-card px-3 py-2 text-ink"
          aria-label={t("searchLabel")}
          placeholder={t("searchPlaceholder")}
          value={query}
          onChange={(event) => setQuery(event.target.value)}
        />
        <Button type="submit" variant="brand">
          {t("search")}
        </Button>
      </form>

      {loading && items.length === 0 ? <Skeleton className="h-24" /> : null}
      {searched && !loading && items.length === 0 ? <EmptyState title={t("empty")} /> : null}

      <ul className="space-y-2">
        {items.map((user) => (
          <li key={user.agri_id}>
            <Card
              hover
              className={cn("cursor-pointer p-3", detail?.agri_id === user.agri_id && "border-brand")}
              onClick={() => void open(user.agri_id)}
            >
              <div className="flex items-center justify-between gap-2">
                <div>
                  <p className="font-semibold text-ink">{user.agri_id}</p>
                  <p className="text-sm text-sub">
                    {user.name ?? "—"} · {t("phoneEnding", { last4: user.phone_last4 })}
                  </p>
                </div>
                <Badge>{t(`status.${user.status}`)}</Badge>
              </div>
            </Card>
          </li>
        ))}
      </ul>
      {nextCursor ? (
        <Button onClick={() => void search(nextCursor)}>{t("loadMore")}</Button>
      ) : null}

      {detail ? (
        <Card className="space-y-3 p-4">
          <div className="flex items-center justify-between">
            <p className="font-semibold text-ink">{detail.agri_id}</p>
            <Badge>{t(`status.${detail.status}`)}</Badge>
          </div>
          <p className="text-sm text-sub">
            {t("completion")}: {detail.completion_score}% · {t("location")}:{" "}
            {detail.district ? `${detail.district}, ${detail.state} ${detail.pincode}` : "—"} ·{" "}
            {t("language")}: {detail.language ?? "—"}
          </p>
          {detail.interests.length > 0 ? (
            <p className="text-sm text-sub">
              {t("interests")}: {detail.interests.join(", ")}
            </p>
          ) : null}
          <div>
            <p className="text-sm font-semibold text-ink">{t("roles")}</p>
            <div className="mt-1 flex flex-wrap gap-2">
              {detail.roles.map((role) => (
                <button
                  key={role}
                  type="button"
                  className="tap-target rounded-pill border border-line px-3 py-1 text-sm text-ink"
                  aria-label={t("removeRole", { role })}
                  onClick={() => void removeRole(role)}
                >
                  {role} ✕
                </button>
              ))}
              <select
                className="rounded-btn border border-line bg-card px-2 py-1 text-sm text-ink"
                aria-label={t("addRole")}
                value=""
                onChange={(event) => {
                  if (event.target.value) void addRole(event.target.value);
                }}
              >
                <option value="">{t("addRole")}</option>
                {ASSIGNABLE_ROLES.filter((role) => !detail.roles.includes(role)).map((role) => (
                  <option key={role} value={role}>
                    {role}
                  </option>
                ))}
              </select>
            </div>
          </div>
          {detail.status === "active" ? (
            <Button onClick={() => setConfirm("suspend")}>{t("suspend")}</Button>
          ) : detail.status === "suspended" ? (
            <Button onClick={() => setConfirm("reactivate")}>{t("reactivate")}</Button>
          ) : null}
        </Card>
      ) : null}

      <Modal open={confirm !== null} onClose={() => setConfirm(null)}>
        <p className="text-ink">
          {confirm === "suspend"
            ? t("confirmSuspend", { agriId: detail?.agri_id ?? "" })
            : t("confirmReactivate", { agriId: detail?.agri_id ?? "" })}
        </p>
        <div className="mt-4 flex justify-end gap-2">
          <Button onClick={() => setConfirm(null)}>{t("cancel")}</Button>
          <Button variant="brand" onClick={() => void setSuspension()}>
            {confirm === "suspend" ? t("suspend") : t("reactivate")}
          </Button>
        </div>
      </Modal>
    </main>
  );
}
```

**Check the real prop signatures before using**: `Modal` (open/onClose props — read `packages/ui/src/components/modal.tsx`), `EmptyState` (title prop), `Badge`, `Card` (accepts onClick via HTMLAttributes). Adjust the JSX to the actual APIs; do not modify packages/ui to fit this page.

- [ ] **Step 4: Link from home** — in `apps/web-admin/app/page.tsx`, add a link (keep the existing scaffold text or replace with a minimal console landing):

```tsx
import Link from "next/link";
```

and inside the rendered output:

```tsx
<Link href="/users" className="text-brand underline">Users</Link>
```

- [ ] **Step 5: Verify**

Run: `pnpm --filter web-admin typecheck && pnpm --filter web-admin lint && pnpm check:hex`
Expected: PASS. Then a manual smoke (optional but recommended): `docker compose -f docker-compose.dev.yml stop api`, run backend `uvicorn main:app` + `pnpm --filter web-admin dev`, log in via id (3003) as a user granted staff, search/suspend a test user.

- [ ] **Step 6: Commit**

```bash
git add apps/web-admin packages/ui/src/i18n/messages
git commit -m "feat(d11): web-admin users console (search, roles, suspend)"
```

---

### Task 13: web-id account/profile screen

**Files:**
- Create: `apps/web-id/app/account/page.tsx`, `apps/web-id/app/account/account-manager.tsx`
- Modify: `apps/web-id/lib/api.ts` (add `patchJson`, `postForm`)
- Modify: `packages/ui/src/i18n/messages/{en,ta,hi}.json` (add `ui.auth.profile` block)

**Interfaces:**
- Consumes: `GET/PATCH /identity/profile`, `POST /identity/profile/avatar` (via the `/api/id` rewrite), `PincodeInput`/`Button`/`Card`/`useToast`/`Skeleton` from `@agri/ui`, `useTranslations("ui.auth.profile")`.
- Produces: `/account` on web-id (theme-agri, EN/TA/HI) — the D11 "account section": completion bar, name, pincode→derived location, language, interests chips, avatar upload, visibility toggles.

- [ ] **Step 1: API helpers** — append to `apps/web-id/lib/api.ts`:

```ts
export function patchJson(path: string, payload: unknown): Promise<JsonBody> {
  return fetch(`/api/id${path}`, {
    method: "PATCH",
    headers: { "content-type": "application/json" },
    body: JSON.stringify(payload),
  }).then(parse);
}

export function postForm(path: string, form: FormData): Promise<JsonBody> {
  // no content-type header: the browser sets the multipart boundary
  return fetch(`/api/id${path}`, { method: "POST", body: form }).then(parse);
}
```

- [ ] **Step 2: i18n strings** — add under `ui.auth` in all three catalogs (English shown; translate for ta/hi):

```json
"profile": {
  "title": "Your profile",
  "completion": "Profile {score}% complete",
  "name": "Name",
  "namePlaceholder": "Your name",
  "save": "Save",
  "saved": "Saved",
  "location": "Location",
  "pincodeHint": "Enter your 6-digit pincode — district and state fill in automatically",
  "unknownPincode": "We don't know that pincode yet",
  "language": "Language",
  "interests": "Interests",
  "interestsHint": "Up to 10 — crops, livestock, anything agri",
  "addInterest": "Add",
  "interestPlaceholder": "e.g. paddy",
  "removeInterest": "Remove {interest}",
  "avatar": "Profile photo",
  "avatarUpload": "Upload photo",
  "avatarTooLarge": "Photo must be under 2 MB (JPG, PNG or WebP)",
  "visibility": "What others can see",
  "visibilityHint": "Your phone number is never public",
  "visibilityKeys": {
    "name": "Name",
    "location": "Location",
    "language": "Language",
    "interests": "Interests",
    "avatar": "Photo"
  },
  "devices": "Manage devices",
  "error": "That didn't work — try again"
}
```

- [ ] **Step 3: RSC page** — `apps/web-id/app/account/page.tsx` (devices-page pattern):

```tsx
import { cookies } from "next/headers";
import { redirect } from "next/navigation";

import { AccountManager, type ProfileData } from "./account-manager";

const API = process.env.API_BASE_URL ?? "http://localhost:8000";

export default async function AccountPage() {
  const jar = await cookies();
  const sid = jar.get("agri_sid")?.value;
  if (!sid) redirect("/login?next=/account");
  const response = await fetch(`${API}/identity/profile`, {
    headers: { cookie: `agri_sid=${sid}` },
    cache: "no-store",
  });
  if (!response.ok) redirect("/login?next=/account");
  const profile = (await response.json()) as ProfileData;
  return <AccountManager initial={profile} />;
}
```

- [ ] **Step 4: Client manager** — `apps/web-id/app/account/account-manager.tsx`:

```tsx
"use client";

/** Progressive profile editor (D11.E). Location is pincode-only: district and
 * state come back from the server, they are never typed here. */

import { useState } from "react";
import { useTranslations } from "next-intl";

import { Button, Card, PincodeInput, Skeleton, useToast } from "@agri/ui";

import { ApiError, patchJson, postForm } from "../../lib/api";

export interface ProfileData {
  agri_id: string;
  name: string | null;
  state: string | null;
  district: string | null;
  pincode: string | null;
  language: string | null;
  interests: string[];
  has_avatar: boolean;
  completion_score: number;
  visibility: Record<string, boolean>;
}

const LANGUAGES = ["en", "ta", "hi"] as const;
const VISIBILITY_KEYS = ["name", "location", "language", "interests", "avatar"] as const;

export function AccountManager({ initial }: { initial: ProfileData }) {
  const t = useTranslations("ui.auth.profile");
  const { toast } = useToast();
  const [profile, setProfile] = useState(initial);
  const [name, setName] = useState(initial.name ?? "");
  const [pincode, setPincode] = useState(initial.pincode ?? "");
  const [interestDraft, setInterestDraft] = useState("");
  const [busy, setBusy] = useState(false);

  const apply = async (payload: Record<string, unknown>, okToast = t("saved")) => {
    setBusy(true);
    try {
      const updated = (await patchJson("/identity/profile", payload)) as unknown as ProfileData;
      setProfile(updated);
      toast({ title: okToast });
    } catch (error) {
      toast({
        title:
          error instanceof ApiError && error.detail === "unknown_pincode"
            ? t("unknownPincode")
            : t("error"),
      });
    } finally {
      setBusy(false);
    }
  };

  const uploadAvatar = async (file: File) => {
    const form = new FormData();
    form.append("file", file);
    setBusy(true);
    try {
      const updated = (await postForm("/identity/profile/avatar", form)) as unknown as ProfileData;
      setProfile(updated);
      toast({ title: t("saved") });
    } catch (error) {
      toast({
        title:
          error instanceof ApiError && (error.detail === "too_large" || error.detail === "unsupported_type")
            ? t("avatarTooLarge")
            : t("error"),
      });
    } finally {
      setBusy(false);
    }
  };

  const addInterest = () => {
    const value = interestDraft.trim();
    if (!value || profile.interests.length >= 10) return;
    setInterestDraft("");
    void apply({ interests: [...profile.interests, value] });
  };

  return (
    <main className="mx-auto max-w-xl space-y-4 p-4">
      <h1 className="text-xl font-bold text-ink">{t("title")}</h1>

      <Card className="p-4">
        <p className="text-sm font-semibold text-ink">
          {t("completion", { score: profile.completion_score })}
        </p>
        <div
          className="mt-2 h-2 rounded-pill bg-line"
          role="progressbar"
          aria-valuenow={profile.completion_score}
          aria-valuemin={0}
          aria-valuemax={100}
        >
          <div
            className="h-2 rounded-pill bg-brand"
            style={{ width: `${profile.completion_score}%` }}
          />
        </div>
      </Card>

      <Card className="space-y-2 p-4">
        <label className="text-sm font-semibold text-ink" htmlFor="profile-name">
          {t("name")}
        </label>
        <div className="flex gap-2">
          <input
            id="profile-name"
            className="min-w-0 flex-1 rounded-btn border border-line bg-card px-3 py-2 text-ink"
            placeholder={t("namePlaceholder")}
            value={name}
            maxLength={80}
            onChange={(event) => setName(event.target.value)}
          />
          <Button variant="brand" disabled={busy || !name.trim()} onClick={() => void apply({ name })}>
            {t("save")}
          </Button>
        </div>
      </Card>

      <Card className="space-y-2 p-4">
        <p className="text-sm font-semibold text-ink">{t("location")}</p>
        <p className="text-sm text-sub">{t("pincodeHint")}</p>
        <div className="flex items-end gap-2">
          <PincodeInput value={pincode} onChange={setPincode} />
          <Button
            variant="brand"
            disabled={busy || pincode.length !== 6}
            onClick={() => void apply({ pincode })}
          >
            {t("save")}
          </Button>
        </div>
        {profile.district ? (
          <p className="text-sm text-sub">
            {profile.district}, {profile.state} {profile.pincode}
          </p>
        ) : null}
      </Card>

      <Card className="space-y-2 p-4">
        <p className="text-sm font-semibold text-ink">{t("language")}</p>
        <div className="flex gap-2">
          {LANGUAGES.map((lang) => (
            <Button
              key={lang}
              variant={profile.language === lang ? "brand" : "ghost"}
              disabled={busy}
              onClick={() => void apply({ language: lang })}
            >
              {lang.toUpperCase()}
            </Button>
          ))}
        </div>
      </Card>

      <Card className="space-y-2 p-4">
        <p className="text-sm font-semibold text-ink">{t("interests")}</p>
        <p className="text-sm text-sub">{t("interestsHint")}</p>
        <div className="flex flex-wrap gap-2">
          {profile.interests.map((interest) => (
            <button
              key={interest}
              type="button"
              className="tap-target rounded-pill border border-line px-3 py-1 text-sm text-ink"
              aria-label={t("removeInterest", { interest })}
              onClick={() =>
                void apply({ interests: profile.interests.filter((item) => item !== interest) })
              }
            >
              {interest} ✕
            </button>
          ))}
        </div>
        <form
          className="flex gap-2"
          onSubmit={(event) => {
            event.preventDefault();
            addInterest();
          }}
        >
          <input
            className="min-w-0 flex-1 rounded-btn border border-line bg-card px-3 py-2 text-ink"
            placeholder={t("interestPlaceholder")}
            aria-label={t("interests")}
            value={interestDraft}
            maxLength={40}
            onChange={(event) => setInterestDraft(event.target.value)}
          />
          <Button type="submit" disabled={busy || profile.interests.length >= 10}>
            {t("addInterest")}
          </Button>
        </form>
      </Card>

      <Card className="space-y-2 p-4">
        <p className="text-sm font-semibold text-ink">{t("avatar")}</p>
        <label className="inline-block">
          <span className="sr-only">{t("avatarUpload")}</span>
          <input
            type="file"
            accept="image/jpeg,image/png,image/webp"
            className="text-sm text-sub"
            disabled={busy}
            onChange={(event) => {
              const file = event.target.files?.[0];
              if (file) void uploadAvatar(file);
              event.target.value = "";
            }}
          />
        </label>
        {profile.has_avatar ? <p className="text-sm text-sub">✓</p> : null}
      </Card>

      <Card className="space-y-2 p-4">
        <p className="text-sm font-semibold text-ink">{t("visibility")}</p>
        <p className="text-sm text-sub">{t("visibilityHint")}</p>
        {VISIBILITY_KEYS.map((key) => (
          <label key={key} className="flex items-center gap-2 text-sm text-ink">
            <input
              type="checkbox"
              checked={profile.visibility[key] ?? false}
              disabled={busy}
              onChange={(event) => void apply({ visibility: { [key]: event.target.checked } })}
            />
            {t(`visibilityKeys.${key}`)}
          </label>
        ))}
      </Card>

      <a href="/devices" className="inline-block text-sm text-brand underline">
        {t("devices")}
      </a>
    </main>
  );
}
```

**Check `PincodeInput`'s real props** (`packages/ui/src/components/pincode-input.tsx`) before wiring — adjust `value/onChange` to its actual API (it may take a label prop; give it `t("location")` if required). If any Tailwind class here isn't in the preset (e.g. `sr-only` is standard, `rounded-btn`/`rounded-pill`/`bg-line` come from D02's preset), swap to the closest existing token class — never add raw values.

- [ ] **Step 5: Verify**

Run: `pnpm --filter web-id typecheck && pnpm --filter web-id lint && pnpm check:hex`
Expected: PASS. Manual smoke (recommended): backend up (compose api stopped, local uvicorn with migrated DB + `python scripts/load_geo.py` so real pincodes resolve), `pnpm --filter web-id dev`, log in, fill the profile, watch the score climb.

- [ ] **Step 6: Commit**

```bash
git add apps/web-id packages/ui/src/i18n/messages
git commit -m "feat(d11): web-id account screen with progressive profile editing"
```

---

### Task 14: ProfileNudge component + demo

**Files:**
- Create: `packages/ui/src/components/profile-nudge.tsx`
- Test: `packages/ui/src/components/profile-nudge.test.ts`
- Modify: `packages/ui/src/index.ts` (export)
- Modify: `packages/ui/src/i18n/messages/{en,ta,hi}.json` (`ui.profileNudge`)
- Modify: `apps/web-agri/app/demo/page.tsx` (demo section)

**Interfaces:**
- Produces: `ProfileNudge({ score, href, title, cta, className? }): JSX.Element | null` — presentational, server-component-safe (no "use client"), renders null at ≥100; apps pass already-translated `title`/`cta` (i18n stays app-side, matching `AuthCluster`'s `loginLabel` pattern). `clampScore(score: number): number` exported for tests/consumers.

- [ ] **Step 1: Write the failing test** — `packages/ui/src/components/profile-nudge.test.ts`:

```ts
import { describe, expect, it } from "vitest";

import { clampScore } from "./profile-nudge";

describe("clampScore", () => {
  it("clamps into 0..100 and rounds", () => {
    expect(clampScore(-5)).toBe(0);
    expect(clampScore(0)).toBe(0);
    expect(clampScore(59.6)).toBe(60);
    expect(clampScore(100)).toBe(100);
    expect(clampScore(140)).toBe(100);
  });
});
```

- [ ] **Step 2: Run to verify failure**

Run: `pnpm --filter @agri/ui test`
Expected: FAIL — module not found.

- [ ] **Step 3: Implement** — `packages/ui/src/components/profile-nudge.tsx`:

```tsx
/**
 * ProfileNudge (D11.E): "Complete your profile — 60%" strip any app can embed.
 * Presentational + server-safe: the app supplies translated title/cta (with
 * the score already interpolated) and the link into id.agri.in's /account.
 * Renders nothing once the profile is complete.
 */
import type { JSX } from "react";

import { cn } from "../lib/cn";
import { buttonVariants } from "./button";
import { Card } from "./card";

export function clampScore(score: number): number {
  return Math.min(100, Math.max(0, Math.round(score)));
}

export interface ProfileNudgeProps {
  score: number;
  href: string;
  title: string;
  cta: string;
  className?: string;
}

export function ProfileNudge({
  score,
  href,
  title,
  cta,
  className,
}: ProfileNudgeProps): JSX.Element | null {
  const clamped = clampScore(score);
  if (clamped >= 100) return null;
  return (
    <Card className={cn("flex items-center gap-4 p-4", className)}>
      <div className="min-w-0 flex-1">
        <p className="truncate text-sm font-semibold text-ink">{title}</p>
        <div
          className="mt-2 h-2 rounded-pill bg-line"
          role="progressbar"
          aria-valuenow={clamped}
          aria-valuemin={0}
          aria-valuemax={100}
          aria-label={title}
        >
          <div className="h-2 rounded-pill bg-brand" style={{ width: `${clamped}%` }} />
        </div>
      </div>
      <a href={href} className={cn(buttonVariants({ variant: "brand" }), "shrink-0")}>
        {cta}
      </a>
    </Card>
  );
}
```

(Match `buttonVariants`' actual call signature from `packages/ui/src/components/button.tsx`; if `Card` uses different padding idioms in siblings, mirror them.)

- [ ] **Step 4: Export + strings.** In `packages/ui/src/index.ts` add (alphabetical with its neighbors):

```ts
export { ProfileNudge, clampScore } from "./components/profile-nudge";
export type { ProfileNudgeProps } from "./components/profile-nudge";
```

In all three message catalogs add under `"ui"`:

```json
"profileNudge": {
  "title": "Complete your profile — {score}%",
  "cta": "Complete now"
}
```

(translated in ta/hi).

- [ ] **Step 5: Demo section** — in `apps/web-agri/app/demo/page.tsx`, add `ProfileNudge` to the big `@agri/ui` import block, and add a section following the page's existing `<Section>`/`<Label>` idiom (place near the other composite sections; `t` here is whatever translator handle the page already uses — reuse it):

```tsx
<Section title="Profile nudge (D11)">
  <ProfileNudge
    score={60}
    href="#"
    title={t("profileNudge.title", { score: 60 })}
    cta={t("profileNudge.cta")}
  />
</Section>
```

If the demo page resolves messages differently (e.g. `getTranslations({ locale })` with the full `ui` namespace), interpolate accordingly — copy the exact call style of the nearest existing section.

- [ ] **Step 6: Verify**

Run: `pnpm --filter @agri/ui test && pnpm --filter @agri/ui typecheck && pnpm --filter web-agri typecheck && pnpm check:hex`
Expected: PASS. The demo page renders the nudge at 60% (DoD: "nudge component in demo route").

- [ ] **Step 7: Commit**

```bash
git add packages/ui apps/web-agri/app/demo
git commit -m "feat(d11): ProfileNudge component with demo showcase"
```

---

### Task 15: Full gate + PR

**Files:** none new — verification, push, PR.

- [ ] **Step 1: Frontend full gate**

```bash
pnpm lint && pnpm typecheck && pnpm test && pnpm check:hex && pnpm build
```

Expected: green. (`pnpm build` on Windows: NEXT_OUTPUT unset → no standalone symlinks, safe. Lighthouse runs in CI only; lhci is known-broken on this box — do not run it locally.)

- [ ] **Step 2: Backend full gate once more** (formatting drifts during frontend work are impossible, but the CI matrix runs everything — mirror it):

```bash
cd backend/core && set -o pipefail && \
ruff format --check . && ruff check . && mypy . && lint-imports && pytest -q && \
python scripts/dump_public_routes.py --check
```

Expected: green.

- [ ] **Step 3: Push and open the PR** (Bash tool; no gh CLI on this host):

```bash
git push -u origin feat/d11-profiles-rbac
```

```bash
TOKEN=$(printf 'protocol=https\nhost=github.com\n\n' | git credential fill | grep '^password=' | cut -d= -f2)
curl -sS -X POST "https://api.github.com/repos/oneuni-in/agri-ecosystem/pulls" \
  -H "Authorization: Bearer $TOKEN" -H "Accept: application/vnd.github+json" \
  -d @- <<'JSON'
{
  "title": "feat(d11): profiles + rbac",
  "head": "feat/d11-profiles-rbac",
  "base": "dev",
  "body": "SPEC D11: progressive profiles, completion score + profile.completed event, require_permission RBAC, admin console (search by agri_id/phone-last-4, roles, suspend/reactivate), web-id /account, ProfileNudge in packages/ui + demo.\n\n## Assumptions confirmed as adopted (owner: veto here)\n- Score weights: phone 20 / name 15 / location 25 / language 10 / interests 15 / avatar 15.\n- Interests are free-form strings v1 (max 10 x 40 chars, case-insensitive dedupe).\n\n## Decisions worth eyes\n- profiles.language is now nullable: NULL = not chosen (score integrity); APIs still report \"en\" as effective language.\n- Location is pincode-derived only; free-text state/district rejected (422).\n- Bearer access tokens now resolve as principals (roles/status ALWAYS re-read from DB, so suspension beats token lifetime); web-admin reaches /admin/* through a BFF proxy + new auth-client getAccessToken().\n- Avatar storage: minimal minio put_object (magic-byte validation, 2MiB, JPEG/PNG/WebP); the D03 'media-safe upload path' did not previously exist.\n- Admin audit trail is structured log lines (admin.role_assigned / admin.user_suspended ...) shaped for D12's audit schema to replace call-site-for-call-site.\n\n## Non-negotiables pinned by tests\n- require_permission proven on 3 permissions (profile.write / users.suspend / roles.assign)\n- full phone never rendered by admin endpoints (response-text assertion)\n- suspension kills cookie+bearer+refresh within one request cycle\n- score pure + table-tested; profile.completed exactly once per crossing\n\n🤖 Generated with [Claude Code](https://claude.com/claude-code)"
}
JSON
```

(Verify the repo slug with `git remote get-url origin` first and substitute if it differs.)

- [ ] **Step 4: Watch CI** — poll the checks via the REST API (`/repos/<slug>/commits/<sha>/check-runs`); all 8 required checks green (`web`, `design-tokens`, `backend`, `public-routes`, `security`, `lighthouse`, `conventional-commits`, `e2e-auth`). Remember: a re-run of a failed workflow re-executes the OLD commit — push fixes and wait for the new run. Lighthouse variance: median-of-3 is already configured; do not chase single-run flakes.

- [ ] **Step 5: Merge** — merging to dev is convention-gated: with all checks green, merge the PR via the REST API merge endpoint (squash off — repo uses merge commits per history) or hand it to the owner if any check is red for environmental reasons. DoD: `PR → dev merged`.

---

## Self-Review Notes (already applied)

- **Spec coverage:** A→Tasks 1,3,6,7 (PATCH updates, geo validation, language, interests, avatar, privacy defaults + JSONB visibility) · B→Tasks 2,6 (weights, recompute on update, event at 100, D13 payload carries user_id/agri_id) · C→Task 4 (+matrix seed extension Task 1; multi-role = union) · D→Tasks 8,10,11,12 (search last-4, view, roles audit-logged for D12, suspend kills sessions via D09 `revoke_everything`) · E→Tasks 13,14 (web-id account, EN/TA/HI, ProfileNudge exported + demo) · F→Tasks 2,4,8 (per-role denial, table-driven score, suspension-kills-access).
- **DO NOTs held:** no KYC, no public profile pages, role UI only in admin, suspend flips status + revokes (soft-delete untouched, no deletions).
- **Threat model:** escalation → super_admin guard + audit lines (Task 8); PII → phone_last4 + response-text tests + no body/query logging; zombie sessions → per-request status check (already in resolver) + bearer path re-reads DB + `revoke_everything` in the suspend transaction.
- **Type consistency spot-checks:** `WebPrincipal.session_id: uuid.UUID | None` consumed in Tasks 5/6/8; `ProfileOut` produced in Task 6, reused by Task 7 and typed as `ProfileData` in Task 13; `put_object(key, data, content_type)` identical in Tasks 6 (import site), 7 (definition), and both monkeypatched fakes; `AdminUserPage.items[].phone_last4` matches Task 12's `AdminUser` interface; `getAccessToken` name identical across Tasks 10/11.
