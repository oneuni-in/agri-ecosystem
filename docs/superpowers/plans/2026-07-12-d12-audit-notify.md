# D12 Audit Log + Notify Module Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Tamper-evident append-only audit log (hash chain per UTC day, DB-grant-enforced immutability) + a notification engine (in-app/SMS/email with per-user preferences, event-bus consumers, retry/dead-letter) + notification-center UI in the 3 public apps and web-id.

**Architecture:** Audit lives in `shared/audit.py` (cross-cutting, importable by every module; import-linter clean). Notify is implemented inside the existing `modules/notify` stub. A new NOSUPERUSER role `app_rt` becomes the app's runtime DB identity and has INSERT+SELECT only on schema `audit`. Modules publish domain events on the Redis Streams bus; a lifespan worker consumes them and dispatches through preferences/rate-cap/flag checks to drivers. Design doc: `docs/superpowers/specs/2026-07-12-d12-audit-notify-design.md` (owner-approved).

**Tech Stack:** FastAPI + SQLAlchemy async + Alembic (backend/core), Redis Streams (`shared/events.py`), httpx (ZeptoMail), Next.js App Router + `@agri/ui` + next-intl (frontend), vitest / pytest.

## Global Constraints

- Branch `feat/d12-audit-notify` (exists, checked out). NEVER commit to dev/main. Conventional commits. PR targets dev.
- Backend commands run from `backend/core` with its venv: `cd backend/core` then `python -m pytest ...` (host Python 3.12, no uv — D01-B memory). Frontend: pnpm 11 from repo root.
- Every migration needs a filled `# -- THREAT/NOTES:` block (lint gate `tests/test_lint_contracts.py`), and must survive `python scripts/migrate_check.py` (upgrade→downgrade→upgrade).
- All IDs UUIDv7; lists cursor-paginated via `shared/pagination.py` (OFFSET banned by lint).
- No raw hex in app code (`pnpm check:hex`); tokens only. 44px tap targets (`tap-target` class).
- Never log message bodies, destination addresses, phones, or query strings. Audit metadata carries agri_ids/hashes, never phones.
- All routes on SecureRouter, private by default; `backend/core/public_routes.txt` must not change in this spec.
- i18n strings land in ALL of `packages/ui/src/i18n/messages/{en,ta,hi}.json` in the same commit.
- CI must stay green on all 8 required checks; run `ruff format --check . && ruff check . && mypy . && lint-imports` plus pytest before each backend commit (from `backend/core`).
- No push notifications, no marketing/bulk sends, no audit read API, no VPS/staging work.

---

### Task 1: Migration 0012 — audit schema, entries table, app_rt role + grants

**Files:**
- Create: `backend/core/alembic/versions/0012_audit_v1.py`
- Test: `backend/core/tests/test_audit_schema.py`

**Interfaces:**
- Produces: schema `audit`, table `audit.entries` (columns below), cluster role `app_rt` (LOGIN NOSUPERUSER, password `app_rt` in dev/CI) with full DML everywhere except schema `audit` (INSERT+SELECT only).
- Later tasks rely on: exact column names `id, created_at, actor_user_id, action, target_type, target_id, metadata, ip, chain_day, seq, prev_hash, entry_hash`; unique `(chain_day, seq)`.

- [ ] **Step 1: Write the failing test**

```python
# backend/core/tests/test_audit_schema.py
"""D12 audit schema: table shape and app_rt grant matrix (non-negotiable:
the runtime role physically cannot UPDATE/DELETE audit rows)."""

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession


async def test_audit_entries_table_exists_with_chain_columns(db_session: AsyncSession) -> None:
    rows = await db_session.execute(
        text(
            "SELECT column_name FROM information_schema.columns "
            "WHERE table_schema = 'audit' AND table_name = 'entries'"
        )
    )
    columns = {row[0] for row in rows}
    assert {
        "id", "created_at", "actor_user_id", "action", "target_type", "target_id",
        "metadata", "ip", "chain_day", "seq", "prev_hash", "entry_hash",
    } <= columns
    assert "updated_at" not in columns  # append-only rows must not pretend to update


async def test_app_rt_role_has_no_update_or_delete_on_audit(db_session: AsyncSession) -> None:
    rows = await db_session.execute(
        text(
            "SELECT privilege_type FROM information_schema.role_table_grants "
            "WHERE grantee = 'app_rt' AND table_schema = 'audit' AND table_name = 'entries'"
        )
    )
    privileges = {row[0] for row in rows}
    assert privileges == {"INSERT", "SELECT"}
```

- [ ] **Step 2: Run it to make sure it fails**

Run (from `backend/core`): `python -m pytest tests/test_audit_schema.py -v`
Expected: FAIL (empty column set — schema `audit` does not exist).

- [ ] **Step 3: Write the migration**

```python
# backend/core/alembic/versions/0012_audit_v1.py
"""D12 audit: append-only tamper-evident audit log + restricted runtime role.

Revision ID: 0012
Revises: 0011
Create Date: 2026-07-12

"""
# -- THREAT/NOTES:
# downgrade data loss: drops audit.entries - the entire audit record for this
#   database. Acceptable pre-launch; in prod, archive the table first.
# locks: CREATE SCHEMA/TABLE/ROLE and GRANT take catalog locks only.
# rollout: app_rt is CLUSTER-wide; creation is idempotent because test/dev
#   databases are recreated against the same cluster. The dev/CI password is
#   'app_rt' (dev-only credentials, same standing as app/app); prod must
#   ALTER ROLE app_rt PASSWORD '<secret>' before flipping the runtime
#   DATABASE_URL to app_rt. Grants are per-database and re-run on every fresh
#   DB via this migration. Downgrade revokes grants and drops the role only
#   if no other database on the cluster still depends on it.

from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op
from shared.migrations import pk_column

revision: str = "0012"
down_revision: str | None = "0011"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

# every schema from 0001 plus public (feature_flags lives there)
APP_SCHEMAS = (
    "identity", "coins", "directory", "leads", "content",
    "market", "ads", "notify", "billing", "geo", "public",
)


def upgrade() -> None:
    op.execute('CREATE SCHEMA IF NOT EXISTS "audit"')
    op.create_table(
        "entries",
        pk_column(),
        # no timestamp_columns(): append-only rows get created_at only, an
        # updated_at column on an immutable table would be a lie
        sa.Column(
            "created_at",
            sa.TIMESTAMP(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.Column("actor_user_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("action", sa.Text, nullable=False),
        sa.Column("target_type", sa.Text, nullable=True),
        sa.Column("target_id", sa.Text, nullable=True),
        sa.Column(
            "metadata", postgresql.JSONB, nullable=False, server_default=sa.text("'{}'::jsonb")
        ),
        sa.Column("ip", sa.Text, nullable=True),
        sa.Column("chain_day", sa.Date, nullable=False),
        sa.Column("seq", sa.Integer, nullable=False),
        sa.Column("prev_hash", sa.Text, nullable=False),
        sa.Column("entry_hash", sa.Text, nullable=False),
        sa.UniqueConstraint("chain_day", "seq"),
        schema="audit",
    )
    op.create_index(None, "entries", ["actor_user_id"], schema="audit")
    op.create_index(None, "entries", ["action"], schema="audit")

    # cluster-wide role: IF NOT EXISTS guard because test DBs are recreated
    # against the same cluster and this migration re-runs there
    op.execute(
        """
        DO $$
        BEGIN
            IF NOT EXISTS (SELECT FROM pg_roles WHERE rolname = 'app_rt') THEN
                CREATE ROLE app_rt LOGIN NOSUPERUSER PASSWORD 'app_rt';
            END IF;
        END
        $$
        """
    )
    for schema in APP_SCHEMAS:
        op.execute(f'GRANT USAGE ON SCHEMA "{schema}" TO app_rt')
        op.execute(f'GRANT SELECT, INSERT, UPDATE, DELETE ON ALL TABLES IN SCHEMA "{schema}" TO app_rt')
        op.execute(f'GRANT USAGE, SELECT ON ALL SEQUENCES IN SCHEMA "{schema}" TO app_rt')
        op.execute(
            f'ALTER DEFAULT PRIVILEGES IN SCHEMA "{schema}" '
            "GRANT SELECT, INSERT, UPDATE, DELETE ON TABLES TO app_rt"
        )
    # the non-negotiable: audit is INSERT+SELECT only for the runtime role
    op.execute('GRANT USAGE ON SCHEMA "audit" TO app_rt')
    op.execute("GRANT SELECT, INSERT ON audit.entries TO app_rt")
    op.execute('ALTER DEFAULT PRIVILEGES IN SCHEMA "audit" GRANT SELECT, INSERT ON TABLES TO app_rt')


def downgrade() -> None:
    for schema in (*APP_SCHEMAS, "audit"):
        op.execute(
            f'ALTER DEFAULT PRIVILEGES IN SCHEMA "{schema}" '
            "REVOKE ALL ON TABLES FROM app_rt"
        )
        op.execute(f'REVOKE ALL ON ALL TABLES IN SCHEMA "{schema}" FROM app_rt')
        op.execute(f'REVOKE ALL ON ALL SEQUENCES IN SCHEMA "{schema}" FROM app_rt')
        op.execute(f'REVOKE ALL ON SCHEMA "{schema}" FROM app_rt')
    op.drop_table("entries", schema="audit")
    op.execute('DROP SCHEMA IF EXISTS "audit"')
    # the role may still hold grants in OTHER databases on this cluster
    op.execute(
        """
        DO $$
        BEGIN
            BEGIN
                DROP ROLE IF EXISTS app_rt;
            EXCEPTION WHEN dependent_objects_still_exist THEN
                NULL;
            END;
        END
        $$
        """
    )
```

- [ ] **Step 4: Run migrate_check, then the test**

Run (from `backend/core`): `python scripts/migrate_check.py`
Expected: upgrade→downgrade→upgrade all succeed.
Run: `python -m pytest tests/test_audit_schema.py -v`
Expected: PASS (the session-scoped `database_url` fixture recreates the test DB at head).

- [ ] **Step 5: Commit**

```bash
git add backend/core/alembic/versions/0012_audit_v1.py backend/core/tests/test_audit_schema.py
git commit -m "feat(d12): audit schema, append-only entries table, app_rt runtime role"
```

---

### Task 2: Runtime/admin DB URL split (app connects as app_rt)

**Files:**
- Modify: `backend/core/settings.py` (add `database_admin_url`)
- Modify: `backend/core/alembic/env.py:23-27` (`_database_url` fallback)
- Modify: `backend/core/tests/conftest.py:51-96` (admin ops via admin URL; runtime fixtures via app_rt; new `admin_database_url` fixture)
- Modify: `docker-compose.dev.yml:10` (API `DATABASE_URL` → app_rt; add `DATABASE_ADMIN_URL`)
- Modify: `.github/workflows/ci.yml:92,226` (same split in both backend jobs)
- Test: `backend/core/tests/test_audit_schema.py` (extend)

**Interfaces:**
- Consumes: role `app_rt` from Task 1.
- Produces: `Settings.database_admin_url` (str; alembic + test-harness admin ops), `Settings.database_url` now pointing at `app_rt`; conftest fixture `admin_database_url: str` (session-scoped, admin creds on the test DB) that Task 4's tamper test uses.

- [ ] **Step 1: Write the failing test (append to test_audit_schema.py)**

```python
from sqlalchemy.engine import make_url

from settings import get_settings


def test_runtime_url_is_app_rt_and_admin_url_is_app() -> None:
    assert make_url(get_settings().database_url).username == "app_rt"
    assert make_url(get_settings().database_admin_url).username == "app"
```

- [ ] **Step 2: Run it to make sure it fails**

Run: `python -m pytest tests/test_audit_schema.py -v`
Expected: FAIL — `Settings` has no `database_admin_url`.

- [ ] **Step 3: Implement**

In `backend/core/settings.py`, replace the `database_url` line with:

```python
    # Runtime role (D12): app_rt has no UPDATE/DELETE on schema audit - the
    # audit log's append-only guarantee is a grant, not a convention. The
    # admin URL (table owner) is for alembic and the test harness only.
    database_url: str = "postgresql+asyncpg://app_rt:app_rt@localhost:55432/agri"
    database_admin_url: str = "postgresql+asyncpg://app:app@localhost:55432/agri"
```

In `backend/core/alembic/env.py` `_database_url()`, change the last line to:

```python
    return os.environ.get("ALEMBIC_DATABASE_URL") or get_settings().database_admin_url
```

In `backend/core/tests/conftest.py`:
- In `database_url()`: `admin_url = make_url(get_settings().database_admin_url)`; keep `test_url` (the alembic/admin URL) as-is but rename it `admin_test_url`; add `runtime_test_url = make_url(get_settings().database_url).set(database=TEST_DB_NAME).render_as_string(hide_password=False)`; keep passing `ALEMBIC_DATABASE_URL: admin_test_url` to the subprocess; **return `runtime_test_url`** (so `db_session` and every existing consumer runs as app_rt).
- Add below it:

```python
@pytest.fixture(scope="session")
def admin_database_url(database_url: str) -> str:
    """Owner-credentials URL on the same migrated test DB (tamper tests only)."""
    return (
        make_url(get_settings().database_admin_url)
        .set(database=TEST_DB_NAME)
        .render_as_string(hide_password=False)
    )
```

In `docker-compose.dev.yml` (api service environment):

```yaml
      DATABASE_URL: postgresql+asyncpg://app_rt:app_rt@postgres:5432/agri
      DATABASE_ADMIN_URL: postgresql+asyncpg://app:app@postgres:5432/agri
```

In `.github/workflows/ci.yml`, at both line 92 and line 226:

```yaml
      DATABASE_URL: postgresql+asyncpg://app_rt:app_rt@localhost:5432/agri
      DATABASE_ADMIN_URL: postgresql+asyncpg://app:app@localhost:5432/agri
```

Note: in CI, `scripts/migrate_check.py` runs before pytest and creates `app_rt` on database `agri`; pytest's conftest then recreates `agri_test` and migrates it as admin. If migrate_check ordering ever changes, conftest's alembic run still creates the role (idempotent).

- [ ] **Step 4: Run the full backend suite (this touches every DB fixture)**

Run: `python -m pytest -q`
Expected: PASS across the board (all suites now hit the DB as app_rt).

- [ ] **Step 5: Commit**

```bash
git add backend/core/settings.py backend/core/alembic/env.py backend/core/tests/conftest.py docker-compose.dev.yml .github/workflows/ci.yml backend/core/tests/test_audit_schema.py
git commit -m "feat(d12): split runtime (app_rt) and admin DB roles across dev/CI/tests"
```

---

### Task 3: shared/audit.py — model, hash chain, audit() writer

**Files:**
- Create: `backend/core/shared/audit.py`
- Test: `backend/core/tests/test_audit_chain.py`

**Interfaces:**
- Consumes: `audit.entries` (Task 1), `shared.db.Base`.
- Produces (used by Tasks 4, 5, 11):
  - `class AuditEntry(Base)` with attributes `id, created_at, actor_user_id, action, target_type, target_id, meta (column "metadata"), ip, chain_day, seq, prev_hash, entry_hash`
  - `async def audit(session: AsyncSession, *, action: str, actor_user_id: uuid.UUID | None = None, target_type: str | None = None, target_id: str | None = None, metadata: dict[str, Any] | None = None, ip: str | None = None, now: datetime | None = None) -> AuditEntry`
  - `def genesis_hash(day: date) -> str`, `def compute_entry_hash(entry: AuditEntry) -> str`

- [ ] **Step 1: Write the failing tests**

```python
# backend/core/tests/test_audit_chain.py
"""D12 hash chain: per-UTC-day genesis, prev/entry hash linkage, seq order."""

import hashlib
from datetime import UTC, datetime

from sqlalchemy.ext.asyncio import AsyncSession

from shared.audit import audit, compute_entry_hash, genesis_hash

DAY1_NOON = datetime(2020, 1, 1, 12, 0, tzinfo=UTC)
DAY2_NOON = datetime(2020, 1, 2, 12, 0, tzinfo=UTC)


async def test_first_entry_of_day_chains_from_genesis(db_session: AsyncSession) -> None:
    entry = await audit(db_session, action="test.first", now=DAY1_NOON)
    assert entry.chain_day == DAY1_NOON.date()
    assert entry.seq == 1
    assert entry.prev_hash == genesis_hash(DAY1_NOON.date())
    assert entry.prev_hash == hashlib.sha256(b"genesis:2020-01-01").hexdigest()
    assert entry.entry_hash == compute_entry_hash(entry)


async def test_entries_link_and_seq_increments(db_session: AsyncSession) -> None:
    first = await audit(db_session, action="test.a", metadata={"n": 1}, now=DAY1_NOON)
    second = await audit(db_session, action="test.b", metadata={"n": 2}, now=DAY1_NOON)
    assert second.seq == 2
    assert second.prev_hash == first.entry_hash
    assert second.entry_hash != first.entry_hash


async def test_new_day_restarts_the_chain(db_session: AsyncSession) -> None:
    await audit(db_session, action="test.a", now=DAY1_NOON)
    next_day = await audit(db_session, action="test.b", now=DAY2_NOON)
    assert next_day.seq == 1
    assert next_day.prev_hash == genesis_hash(DAY2_NOON.date())


async def test_hash_covers_metadata(db_session: AsyncSession) -> None:
    entry = await audit(db_session, action="test.a", metadata={"k": "v"}, now=DAY1_NOON)
    entry.meta = {"k": "tampered"}
    assert compute_entry_hash(entry) != entry.entry_hash
```

- [ ] **Step 2: Run to verify failure**

Run: `python -m pytest tests/test_audit_chain.py -v`
Expected: FAIL — `shared.audit` does not exist.

- [ ] **Step 3: Implement shared/audit.py**

```python
# backend/core/shared/audit.py
"""Append-only, tamper-evident audit log (D12).

Entries hash-chain per UTC day; the first entry of a day chains from
sha256("genesis:<day>"). audit() writes in the CALLER's transaction, so the
record commits or rolls back atomically with the action it describes. Same-day
appends serialize on a pg advisory xact lock: the chain cannot fork under
concurrency and the schema needs no UPDATE grant anywhere (the app role
physically cannot rewrite history; verify_chain() proves nobody else did).

PII rule: metadata carries agri_ids and hashes - never phone numbers, message
bodies, or addresses. Deleting the newest entry of a day is the one mutation
the chain alone cannot see; the grant matrix (app_rt: INSERT+SELECT only) is
what closes that hole for the application role.
"""

import hashlib
import json
import uuid
from datetime import UTC, date, datetime
from typing import Any

import uuid6
from sqlalchemy import TIMESTAMP, Date, Integer, Text, select, text
from sqlalchemy.dialects import postgresql
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import Mapped, mapped_column

from shared.db import Base


class AuditEntry(Base):
    """audit.entries. Deliberately no TimestampMixin: immutable rows have no
    updated_at, and created_at is set client-side because it is hashed."""

    __tablename__ = "entries"
    __table_args__ = {"schema": "audit"}

    id: Mapped[uuid.UUID] = mapped_column(
        postgresql.UUID(as_uuid=True), primary_key=True, default=uuid6.uuid7
    )
    created_at: Mapped[datetime] = mapped_column(TIMESTAMP(timezone=True), nullable=False)
    actor_user_id: Mapped[uuid.UUID | None] = mapped_column(
        postgresql.UUID(as_uuid=True), nullable=True, index=True
    )
    action: Mapped[str] = mapped_column(Text, nullable=False, index=True)
    target_type: Mapped[str | None] = mapped_column(Text, nullable=True)
    target_id: Mapped[str | None] = mapped_column(Text, nullable=True)
    # attribute is `meta`: `metadata` collides with DeclarativeBase.metadata
    meta: Mapped[dict[str, Any]] = mapped_column(
        "metadata", postgresql.JSONB, nullable=False, default=dict
    )
    ip: Mapped[str | None] = mapped_column(Text, nullable=True)
    chain_day: Mapped[date] = mapped_column(Date, nullable=False)
    seq: Mapped[int] = mapped_column(Integer, nullable=False)
    prev_hash: Mapped[str] = mapped_column(Text, nullable=False)
    entry_hash: Mapped[str] = mapped_column(Text, nullable=False)


def genesis_hash(day: date) -> str:
    return hashlib.sha256(f"genesis:{day.isoformat()}".encode()).hexdigest()


def _canonical(entry: AuditEntry) -> str:
    """Deterministic serialization of every hashed field; any drift here is a
    chain-format change and needs a re-anchor plan."""
    return json.dumps(
        {
            "id": str(entry.id),
            "created_at": entry.created_at.isoformat(),
            "actor_user_id": str(entry.actor_user_id) if entry.actor_user_id else None,
            "action": entry.action,
            "target_type": entry.target_type,
            "target_id": entry.target_id,
            "metadata": entry.meta,
            "ip": entry.ip,
            "chain_day": entry.chain_day.isoformat(),
            "seq": entry.seq,
        },
        sort_keys=True,
        separators=(",", ":"),
    )


def compute_entry_hash(entry: AuditEntry) -> str:
    return hashlib.sha256((entry.prev_hash + _canonical(entry)).encode()).hexdigest()


async def audit(
    session: AsyncSession,
    *,
    action: str,
    actor_user_id: uuid.UUID | None = None,
    target_type: str | None = None,
    target_id: str | None = None,
    metadata: dict[str, Any] | None = None,
    ip: str | None = None,
    now: datetime | None = None,
) -> AuditEntry:
    """Append one entry in the caller's transaction. `now` is injectable for
    tests only; production callers never pass it."""
    now = now or datetime.now(UTC)
    day = now.date()
    # serialize same-day appends; xact lock releases with the transaction
    await session.execute(
        text("SELECT pg_advisory_xact_lock(hashtext(:key))").bindparams(key=f"audit:{day}")
    )
    last = await session.scalar(
        select(AuditEntry)
        .where(AuditEntry.chain_day == day)
        .order_by(AuditEntry.seq.desc())
        .limit(1)
    )
    entry = AuditEntry(
        created_at=now,
        actor_user_id=actor_user_id,
        action=action,
        target_type=target_type,
        target_id=target_id,
        meta=metadata or {},
        ip=ip,
        chain_day=day,
        seq=(last.seq + 1) if last is not None else 1,
        prev_hash=last.entry_hash if last is not None else genesis_hash(day),
    )
    entry.entry_hash = compute_entry_hash(entry)
    session.add(entry)
    await session.flush()
    return entry
```

- [ ] **Step 4: Run tests + linters**

Run: `python -m pytest tests/test_audit_chain.py tests/test_audit_schema.py -v && ruff format --check . && ruff check . && mypy . && lint-imports`
Expected: all PASS.

- [ ] **Step 5: Commit**

```bash
git add backend/core/shared/audit.py backend/core/tests/test_audit_chain.py
git commit -m "feat(d12): shared audit() writer with per-day hash chain"
```

---

### Task 4: verify_chain(), tamper + grant enforcement tests, verify job, metrics

**Files:**
- Modify: `backend/core/shared/audit.py` (append verify_chain + ChainBreak)
- Modify: `backend/core/shared/metrics.py` (audit counters, reset)
- Create: `backend/core/scripts/verify_audit_chain.py`
- Test: `backend/core/tests/test_audit_integrity.py`

**Interfaces:**
- Consumes: Task 3's `audit()`, Task 2's `admin_database_url` fixture.
- Produces: `@dataclass ChainBreak(day: date, seq: int, reason: str)` with reasons `"hash_mismatch" | "link_mismatch" | "seq_gap"`; `async def verify_chain(session: AsyncSession, *, days: list[date] | None = None) -> list[ChainBreak]`; metrics `AUDIT_CHAIN_DAYS_VERIFIED`, `AUDIT_CHAIN_BREAKS` in shared/metrics.py.

- [ ] **Step 1: Write the failing tests**

```python
# backend/core/tests/test_audit_integrity.py
"""D12 non-negotiables 1+2: tampering is DETECTED (not just hashed), and the
runtime role physically cannot UPDATE or DELETE audit rows.

These tests commit real rows (tamper needs a second connection to see them),
so they use their own engines + admin-credential cleanup, not db_session."""

from collections.abc import AsyncIterator
from datetime import UTC, date, datetime

import pytest
from sqlalchemy import text
from sqlalchemy.exc import DBAPIError, ProgrammingError
from sqlalchemy.ext.asyncio import AsyncEngine, async_sessionmaker, create_async_engine
from sqlalchemy.pool import NullPool

from shared.audit import audit, verify_chain

DAY = date(2020, 6, 15)


def _at(minute: int) -> datetime:
    return datetime(2020, 6, 15, 12, minute, tzinfo=UTC)


@pytest.fixture
async def engines(
    database_url: str, admin_database_url: str
) -> AsyncIterator[tuple[AsyncEngine, AsyncEngine]]:
    runtime = create_async_engine(database_url, poolclass=NullPool)
    admin = create_async_engine(admin_database_url, poolclass=NullPool)
    yield runtime, admin
    async with admin.connect() as conn:  # app_rt cannot clean audit rows
        await conn.execute(text("DELETE FROM audit.entries WHERE chain_day = '2020-06-15'"))
        await conn.commit()
    await runtime.dispose()
    await admin.dispose()


async def test_intact_chain_verifies_clean(engines: tuple[AsyncEngine, AsyncEngine]) -> None:
    runtime, _ = engines
    async with async_sessionmaker(runtime, expire_on_commit=False)() as session:
        for i in range(3):
            await audit(session, action="test.ok", metadata={"i": i}, now=_at(i))
        await session.commit()
        assert await verify_chain(session, days=[DAY]) == []


async def test_tampered_row_breaks_the_chain(engines: tuple[AsyncEngine, AsyncEngine]) -> None:
    runtime, admin = engines
    async with async_sessionmaker(runtime, expire_on_commit=False)() as session:
        for i in range(3):
            await audit(session, action="test.tamper", metadata={"i": i}, now=_at(i))
        await session.commit()
    # a privileged connection (compromised owner creds) rewrites history
    async with admin.connect() as conn:
        await conn.execute(
            text(
                "UPDATE audit.entries SET metadata = '{\"i\": 99}'::jsonb "
                "WHERE chain_day = '2020-06-15' AND seq = 2"
            )
        )
        await conn.commit()
    async with async_sessionmaker(runtime)() as session:
        breaks = await verify_chain(session, days=[DAY])
    assert [(b.day, b.seq, b.reason) for b in breaks] == [(DAY, 2, "hash_mismatch")]


async def test_deleted_row_breaks_the_chain(engines: tuple[AsyncEngine, AsyncEngine]) -> None:
    runtime, admin = engines
    async with async_sessionmaker(runtime, expire_on_commit=False)() as session:
        for i in range(3):
            await audit(session, action="test.gap", metadata={"i": i}, now=_at(i))
        await session.commit()
    async with admin.connect() as conn:
        await conn.execute(
            text("DELETE FROM audit.entries WHERE chain_day = '2020-06-15' AND seq = 2")
        )
        await conn.commit()
    async with async_sessionmaker(runtime)() as session:
        breaks = await verify_chain(session, days=[DAY])
    assert breaks and breaks[0].reason == "seq_gap"


async def test_app_rt_cannot_update_or_delete(engines: tuple[AsyncEngine, AsyncEngine]) -> None:
    runtime, _ = engines
    for statement in (
        "UPDATE audit.entries SET action = 'x' WHERE chain_day = '2020-06-15'",
        "DELETE FROM audit.entries WHERE chain_day = '2020-06-15'",
    ):
        async with runtime.connect() as conn:
            with pytest.raises((ProgrammingError, DBAPIError)) as excinfo:
                await conn.execute(text(statement))
            assert "permission denied" in str(excinfo.value).lower()
```

- [ ] **Step 2: Run to verify failure**

Run: `python -m pytest tests/test_audit_integrity.py -v`
Expected: FAIL — `verify_chain` not importable. (`test_app_rt_cannot_update_or_delete` alone may already pass; that's fine.)

- [ ] **Step 3: Implement verify_chain (append to shared/audit.py)**

```python
from dataclasses import dataclass  # add to imports


@dataclass(frozen=True, slots=True)
class ChainBreak:
    day: date
    seq: int
    reason: str  # "hash_mismatch" | "link_mismatch" | "seq_gap"


async def verify_chain(
    session: AsyncSession, *, days: list[date] | None = None
) -> list[ChainBreak]:
    """Recompute each day's chain; return every divergence. After a broken
    entry, verification continues from the STORED hash so one tampered row
    reports once instead of cascading down the day."""
    if days is None:
        day_rows = await session.execute(
            select(AuditEntry.chain_day).distinct().order_by(AuditEntry.chain_day)
        )
        days = [row[0] for row in day_rows]
    breaks: list[ChainBreak] = []
    for day in days:
        rows = (
            await session.scalars(
                select(AuditEntry).where(AuditEntry.chain_day == day).order_by(AuditEntry.seq)
            )
        ).all()
        expected_prev = genesis_hash(day)
        expected_seq = 1
        for row in rows:
            if row.seq != expected_seq:
                breaks.append(ChainBreak(day, row.seq, "seq_gap"))
                expected_seq = row.seq
            if row.prev_hash != expected_prev:
                breaks.append(ChainBreak(day, row.seq, "link_mismatch"))
            if compute_entry_hash(row) != row.entry_hash:
                breaks.append(ChainBreak(day, row.seq, "hash_mismatch"))
            expected_prev = row.entry_hash
            expected_seq += 1
    return breaks
```

Note on the delete test: removing seq 2 makes seq 3 arrive when 2 was expected → `seq_gap`, and its prev_hash points at the missing row → `link_mismatch` too; the test asserts on `breaks[0].reason` only.

In `backend/core/shared/metrics.py`, after the OTP block add:

```python
# Audit chain telemetry (D12): counts only - entry contents never label metrics.
AUDIT_CHAIN_DAYS_VERIFIED = Counter(
    "audit_chain_days_verified_total",
    "Audit chain day-verifications by outcome",
    ["result"],  # ok | broken
    registry=registry,
)
AUDIT_CHAIN_BREAKS = Counter(
    "audit_chain_breaks_total",
    "Individual audit chain breaks detected",
    registry=registry,
)
```

and extend `reset_metrics()`'s tuple with `AUDIT_CHAIN_DAYS_VERIFIED, AUDIT_CHAIN_BREAKS`.

Create `backend/core/scripts/verify_audit_chain.py`:

```python
"""Verify the audit hash chain; exit 1 on any break (cron/CI job, D12).

Runs as the runtime role (SELECT is enough). Cron wiring is deferred with the
VPS work; until then this is invoked manually or from CI.
"""

import asyncio
import sys

from shared.audit import verify_chain
from shared.db import get_sessionmaker
from shared.metrics import AUDIT_CHAIN_BREAKS, AUDIT_CHAIN_DAYS_VERIFIED
from shared.telemetry import configure_logging, get_logger

logger = get_logger(__name__)


async def main() -> int:
    async with get_sessionmaker()() as session:
        breaks = await verify_chain(session)
    if not breaks:
        AUDIT_CHAIN_DAYS_VERIFIED.labels("ok").inc()
        logger.info("audit chain verified", extra={"extra_fields": {"breaks": 0}})
        return 0
    AUDIT_CHAIN_DAYS_VERIFIED.labels("broken").inc()
    for item in breaks:
        AUDIT_CHAIN_BREAKS.inc()
        logger.error(
            "audit chain break",
            extra={
                "extra_fields": {
                    "day": item.day.isoformat(),
                    "seq": item.seq,
                    "reason": item.reason,
                }
            },
        )
    return 1


if __name__ == "__main__":
    configure_logging("INFO")
    sys.exit(asyncio.run(main()))
```

- [ ] **Step 4: Run tests + linters**

Run: `python -m pytest tests/test_audit_integrity.py tests/test_audit_chain.py -v && ruff format --check . && ruff check . && mypy . && lint-imports`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add backend/core/shared/audit.py backend/core/shared/metrics.py backend/core/scripts/verify_audit_chain.py backend/core/tests/test_audit_integrity.py
git commit -m "feat(d12): verify_chain with tamper + grant enforcement tests and verify job"
```

---

### Task 5: Wire audit into identity (role/suspend/OTP-abuse/handle)

**Files:**
- Modify: `backend/core/modules/identity/admin_router.py:13-15,115-119,207-291` (real `_audit`; docstring)
- Modify: `backend/core/modules/identity/otp_throttle.py:59-102` (system audit rows)
- Modify: `backend/core/modules/identity/session_router.py:222-243` (`set_handle` audit)
- Test: modify `backend/core/tests/test_admin_router.py:235-248`; extend `backend/core/tests/test_audit_chain.py` or the router/throttle suites as below

**Interfaces:**
- Consumes: `shared.audit.audit(...)` (Task 3 signature).
- Produces: audit actions `admin.role_assigned`, `admin.role_removed`, `admin.user_suspended`, `admin.user_reactivated`, `otp.abuse_burst_issues`, `otp.abuse_many_phones_per_ip`, `identity.handle_changed`.

- [ ] **Step 1: Rewrite the redaction test to assert on rows (failing first)**

In `backend/core/tests/test_admin_router.py`, replace `test_audit_lines_use_agri_ids_never_phone` (keep the same fixtures/client setup that the neighbouring tests use — the suite overrides `get_session` with `db_session`, so audit rows are visible in `db_session`):

```python
async def test_audit_rows_use_agri_ids_never_phone(...existing fixture params...) -> None:
    # ...existing arrange + role-assign call from the old test stays...
    from sqlalchemy import select

    from shared.audit import AuditEntry

    rows = (
        await db_session.scalars(
            select(AuditEntry).where(AuditEntry.action == "admin.role_assigned")
        )
    ).all()
    assert len(rows) == 1
    entry = rows[0]
    assert entry.target_id == target_agri_id            # agri_id, not UUID/phone
    assert entry.actor_user_id is not None
    serialized = str(entry.meta) + str(entry.target_id)
    assert phone_number not in serialized               # the raw phone never lands in audit
    assert entry.meta["actor"].startswith(("AG", "@")) or entry.meta["actor"]
```

Adapt names (`target_agri_id`, `phone_number`, client call) to the existing test body — the intent is: same request as before, but the assertion moves from captured log lines to `audit.entries` rows.

- [ ] **Step 2: Run to verify failure**

Run: `python -m pytest tests/test_admin_router.py -v`
Expected: the rewritten test FAILS (no rows — `_audit` still logs only).

- [ ] **Step 3: Implement the wiring**

`admin_router.py` — replace `_audit` (line 115-119) with:

```python
async def _audit(
    session: AsyncSession,
    request: Request,
    action: str,
    *,
    actor: "WebPrincipal",
    target: User,
    role: str | None = None,
) -> None:
    """D12: real audit rows (schema audit), call-site-for-call-site where
    logger.warning placeholders stood. agri_ids only - never phone/UUID."""
    meta: dict[str, object] = {"actor": actor.agri_id, "target": target.agri_id}
    if role is not None:
        meta["role"] = role
    await audit(
        session,
        action=action,
        actor_user_id=actor.user_id,
        target_type="user",
        target_id=target.agri_id,
        metadata=meta,
        ip=request.client.host if request.client else None,
    )
```

Add imports: `from shared.audit import audit` and `from modules.identity.session_service import WebPrincipal` (type only; identity-internal so no boundary issue). Update the module docstring lines 13-15 to say audit rows are real as of D12. Update the four call sites (all become `await _audit(session, request, ...)`, passing `actor=principal, target=user`):
- `add_role` (line 224) and `remove_role` (line 246): add `request: Request` to their signatures.
- `suspend_user` (line 277): already has `request`.
- `reactivate_user` (line 290): add `request: Request`.

`otp_throttle.py` — add at module level:

```python
from shared.audit import audit
from shared.db import get_sessionmaker


async def _audit_system(action: str, metadata: dict[str, object]) -> None:
    """System-actor audit row in its own committed session: abuse records must
    survive the request's 429 rollback. Best-effort - an audit outage must not
    take OTP issuance down with it."""
    try:
        async with get_sessionmaker()() as session:
            await audit(session, action=action, metadata=metadata)
            await session.commit()
    except Exception as exc:
        logger.warning(
            "audit.write_failed",
            extra={"extra_fields": {"action": action, "exc_type": type(exc).__name__}},
        )
```

In `assert_issue_allowed` after the existing burst `logger.warning` add:
`await _audit_system("otp.abuse_burst_issues", {"ip": ip, "cap": OTP_ISSUES_PER_PHONE_PER_DAY})`
In `register_issue` after the many-phones `logger.warning` add:
`await _audit_system("otp.abuse_many_phones_per_ip", {"ip": ip, "distinct_phones": distinct})`
(keep both logger.warning lines — logs are observability, rows are the record).

`session_router.py` `set_handle` — add `request: Request` to the signature and, after the successful `flush()` (line 239-242 try block), before `return`:

```python
    await audit(
        session,
        action="identity.handle_changed",
        actor_user_id=user.id,
        target_type="handle",
        target_id=handle,
        metadata={"old": old, "new": handle},
        ip=request.client.host if request.client else None,
    )
```

with `from shared.audit import audit` added to imports.

- [ ] **Step 4: Add throttle + handle tests**

Append to the existing OTP-throttle test file (find it: `grep -l "otp_abuse" backend/core/tests`) a case asserting a committed `audit.entries` row appears with action `otp.abuse_burst_issues` and NO phone in `meta` after the burst cap trips (drive `assert_issue_allowed` past `OTP_ISSUES_PER_PHONE_PER_DAY` with the `otp_redis` fixture; query rows via a fresh sessionmaker since `_audit_system` commits its own session; clean up via `admin_database_url` engine `DELETE FROM audit.entries WHERE action LIKE 'otp.abuse%'`). In the session-router suite, extend the existing `set_handle` happy-path test to assert one `identity.handle_changed` row exists in `db_session` with `meta == {"old": old_handle, "new": new_handle}`.

- [ ] **Step 5: Run the identity suites + full lint**

Run: `python -m pytest tests/test_admin_router.py tests/test_session_router.py tests/test_otp*.py -v && ruff format --check . && ruff check . && mypy . && lint-imports`
Expected: PASS (adjust file names to what exists — `ls backend/core/tests`).

- [ ] **Step 6: Commit**

```bash
git add backend/core/modules/identity backend/core/tests
git commit -m "feat(d12): real audit rows for role/suspend/OTP-abuse/handle actions"
```

---

### Task 6: Migration 0013 — notify tables, template seeds, email flag; ORM models

**Files:**
- Create: `backend/core/alembic/versions/0013_notify_v1.py`
- Modify: `backend/core/modules/notify/models.py`
- Test: `backend/core/tests/test_notify_templates.py` (completeness gate lives here from day one)

**Interfaces:**
- Produces (used by Tasks 7-11):
  - Tables `notify.templates(key, channel, locale, subject, body)` unique `(key, channel, locale)`; `notify.notifications(user_id, template_key, payload, locale, read_at)`; `notify.deliveries(notification_id, channel, status, attempts, next_attempt_at, destination, provider_ref, cost, last_error)`; `notify.preferences(user_id, channel, enabled)` unique `(user_id, channel)`.
  - Enums `notify.notify_channel = in_app|sms|email`, `notify.delivery_status = pending|sent|failed|dead`, `notify.notify_locale = en|ta|hi`.
  - ORM classes `Template, Notification, Delivery, Preference` in `modules/notify/models.py` (UUIDv7PKMixin + TimestampMixin, `__table_args__` schema `notify`).
  - Seeded template keys/channels: `welcome`(in_app,email), `login_new_device`(in_app,sms,email), `role_changed`(in_app), `generic_announce`(in_app,email) — × en/ta/hi each.
  - Flag row `notify.email_enabled` (disabled) in `public.feature_flags`.

- [ ] **Step 1: Write the failing tests**

```python
# backend/core/tests/test_notify_templates.py
"""D12 non-negotiable 4: every (key, channel) exists in ALL 3 locales, or CI
fails. Also pins the seeded catalogue so a dropped seed is loud."""

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from modules.notify.models import Template
from shared.i18n import SUPPORTED_LOCALES

EXPECTED_CHANNELS = {
    "welcome": {"in_app", "email"},
    "login_new_device": {"in_app", "sms", "email"},
    "role_changed": {"in_app"},
    "generic_announce": {"in_app", "email"},
}


async def test_every_key_channel_pair_has_all_three_locales(db_session: AsyncSession) -> None:
    rows = (await db_session.scalars(select(Template))).all()
    seen: dict[tuple[str, str], set[str]] = {}
    for row in rows:
        seen.setdefault((row.key, row.channel), set()).add(row.locale)
    assert seen, "template seed missing entirely"
    incomplete = {pair: locales for pair, locales in seen.items() if locales != set(SUPPORTED_LOCALES)}
    assert not incomplete, f"templates missing locales: {incomplete}"


async def test_seeded_catalogue_matches_spec(db_session: AsyncSession) -> None:
    rows = (await db_session.scalars(select(Template))).all()
    by_key: dict[str, set[str]] = {}
    for row in rows:
        by_key.setdefault(row.key, set()).add(row.channel)
    assert by_key == EXPECTED_CHANNELS


async def test_email_templates_have_subjects(db_session: AsyncSession) -> None:
    rows = (await db_session.scalars(select(Template).where(Template.channel == "email"))).all()
    assert rows and all(row.subject for row in rows)
```

- [ ] **Step 2: Run to verify failure**

Run: `python -m pytest tests/test_notify_templates.py -v`
Expected: FAIL — `modules.notify.models` has no `Template`.

- [ ] **Step 3: Write the ORM models**

Replace `backend/core/modules/notify/models.py` with:

```python
"""Notify module ORM (D12): templates / notifications / deliveries / preferences."""

import uuid
from datetime import datetime
from decimal import Decimal
from typing import Any

from sqlalchemy import TIMESTAMP, ForeignKey, Integer, Numeric, Text, UniqueConstraint
from sqlalchemy.dialects import postgresql
from sqlalchemy.orm import Mapped, mapped_column

from shared.db import Base, TimestampMixin, UUIDv7PKMixin

_channel = postgresql.ENUM(
    "in_app", "sms", "email", name="notify_channel", schema="notify", create_type=False
)
_status = postgresql.ENUM(
    "pending", "sent", "failed", "dead", name="delivery_status", schema="notify", create_type=False
)
_locale = postgresql.ENUM("en", "ta", "hi", name="notify_locale", schema="notify", create_type=False)


class Template(UUIDv7PKMixin, TimestampMixin, Base):
    """Message template; body uses {var} placeholders (modules/notify/rendering.py)."""

    __tablename__ = "templates"
    __table_args__ = (
        UniqueConstraint("key", "channel", "locale"),
        {"schema": "notify"},
    )

    key: Mapped[str] = mapped_column(Text, nullable=False)
    channel: Mapped[str] = mapped_column(_channel, nullable=False)
    locale: Mapped[str] = mapped_column(_locale, nullable=False)
    subject: Mapped[str | None] = mapped_column(Text, nullable=True)  # email only
    body: Mapped[str] = mapped_column(Text, nullable=False)


class Notification(UUIDv7PKMixin, TimestampMixin, Base):
    """One user-visible in-app notification; body renders at read time."""

    __tablename__ = "notifications"
    __table_args__ = {"schema": "notify"}

    user_id: Mapped[uuid.UUID] = mapped_column(
        postgresql.UUID(as_uuid=True), nullable=False, index=True
    )
    template_key: Mapped[str] = mapped_column(Text, nullable=False)
    payload: Mapped[dict[str, Any]] = mapped_column(postgresql.JSONB, nullable=False, default=dict)
    locale: Mapped[str] = mapped_column(_locale, nullable=False, server_default="en")
    read_at: Mapped[datetime | None] = mapped_column(TIMESTAMP(timezone=True), nullable=True)


class Delivery(UUIDv7PKMixin, TimestampMixin, Base):
    """One channel-send attempt trail for a notification. destination is the
    address this delivery goes to; it is stored for retry, NEVER logged."""

    __tablename__ = "deliveries"
    __table_args__ = {"schema": "notify"}

    notification_id: Mapped[uuid.UUID] = mapped_column(
        postgresql.UUID(as_uuid=True),
        ForeignKey("notify.notifications.id"),
        nullable=False,
        index=True,
    )
    channel: Mapped[str] = mapped_column(_channel, nullable=False)
    status: Mapped[str] = mapped_column(_status, nullable=False, server_default="pending")
    attempts: Mapped[int] = mapped_column(Integer, nullable=False, server_default="0")
    next_attempt_at: Mapped[datetime | None] = mapped_column(TIMESTAMP(timezone=True), nullable=True)
    destination: Mapped[str | None] = mapped_column(Text, nullable=True)
    provider_ref: Mapped[str | None] = mapped_column(Text, nullable=True)
    cost: Mapped[Decimal | None] = mapped_column(Numeric(10, 4), nullable=True)
    last_error: Mapped[str | None] = mapped_column(Text, nullable=True)


class Preference(UUIDv7PKMixin, TimestampMixin, Base):
    """Per-user channel opt-out rows; absence of a row means enabled.
    in_app is not toggleable (router rejects it)."""

    __tablename__ = "preferences"
    __table_args__ = (
        UniqueConstraint("user_id", "channel"),
        {"schema": "notify"},
    )

    user_id: Mapped[uuid.UUID] = mapped_column(postgresql.UUID(as_uuid=True), nullable=False)
    channel: Mapped[str] = mapped_column(_channel, nullable=False)
    enabled: Mapped[bool] = mapped_column(nullable=False, server_default="true")
```

- [ ] **Step 4: Write migration 0013**

```python
# backend/core/alembic/versions/0013_notify_v1.py
"""D12 notify: templates/notifications/deliveries/preferences + seeds + flag.

Revision ID: 0013
Revises: 0012
Create Date: 2026-07-12

"""
# -- THREAT/NOTES:
# downgrade data loss: drops all notify tables (notifications, delivery
#   history, preferences) and the seeded templates + the notify.email_enabled
#   flag row. Acceptable pre-launch.
# locks: CREATE TABLE/TYPE + small bulk inserts; no existing-table rewrites.
# rollout: run after 0012 (app_rt default privileges in schema notify already
#   cover these tables). Deploy with or before the D12 notify code.

import uuid
from collections.abc import Sequence

import sqlalchemy as sa
import uuid6
from sqlalchemy.dialects import postgresql

from alembic import op
from shared.migrations import pk_column, timestamp_columns

revision: str = "0013"
down_revision: str | None = "0012"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

channel_enum = postgresql.ENUM("in_app", "sms", "email", name="notify_channel", schema="notify")
status_enum = postgresql.ENUM(
    "pending", "sent", "failed", "dead", name="delivery_status", schema="notify"
)
locale_enum = postgresql.ENUM("en", "ta", "hi", name="notify_locale", schema="notify")

templates_table = sa.table(
    "templates",
    sa.column("id", postgresql.UUID(as_uuid=True)),
    sa.column("key", sa.Text),
    sa.column("channel", sa.Text),
    sa.column("locale", sa.Text),
    sa.column("subject", sa.Text),
    sa.column("body", sa.Text),
    schema="notify",
)

# (key, channel, locale, subject, body) - every key ships en+ta+hi (CI gate)
SEED_TEMPLATES: list[tuple[str, str, str, str | None, str]] = [
    # welcome - in_app
    ("welcome", "in_app", "en", None, "Welcome to Agri, {agri_id}! Your account is ready."),
    ("welcome", "in_app", "ta", None, "அக்ரிக்கு வரவேற்கிறோம், {agri_id}! உங்கள் கணக்கு தயார்."),
    ("welcome", "in_app", "hi", None, "एग्री में आपका स्वागत है, {agri_id}! आपका खाता तैयार है।"),
    # welcome - email
    ("welcome", "email", "en", "Welcome to Agri", "Hello {agri_id}, your Agri account is ready. You can sign in on agri.in, milk.agri.in and organic.agri.in with one ID."),
    ("welcome", "email", "ta", "அக்ரிக்கு வரவேற்கிறோம்", "வணக்கம் {agri_id}, உங்கள் அக்ரி கணக்கு தயார். ஒரே ஐடியுடன் agri.in, milk.agri.in, organic.agri.in ஆகியவற்றில் உள்நுழையலாம்."),
    ("welcome", "email", "hi", "एग्री में आपका स्वागत है", "नमस्ते {agri_id}, आपका एग्री खाता तैयार है। एक ही आईडी से agri.in, milk.agri.in और organic.agri.in पर साइन इन करें।"),
    # login_new_device - in_app
    ("login_new_device", "in_app", "en", None, "New login to your account from {device}. Not you? Review your devices."),
    ("login_new_device", "in_app", "ta", None, "{device} இலிருந்து உங்கள் கணக்கில் புதிய உள்நுழைவு. நீங்கள் இல்லையா? உங்கள் சாதனங்களைச் சரிபார்க்கவும்."),
    ("login_new_device", "in_app", "hi", None, "{device} से आपके खाते में नया लॉगिन हुआ। आप नहीं थे? अपने डिवाइस जांचें।"),
    # login_new_device - sms
    ("login_new_device", "sms", "en", None, "Agri: new login from {device}. Not you? Review devices at id.agri.in/devices"),
    ("login_new_device", "sms", "ta", None, "அக்ரி: {device} இலிருந்து புதிய உள்நுழைவு. நீங்கள் இல்லையா? id.agri.in/devices"),
    ("login_new_device", "sms", "hi", None, "एग्री: {device} से नया लॉगिन। आप नहीं थे? id.agri.in/devices देखें"),
    # login_new_device - email
    ("login_new_device", "email", "en", "New login to your Agri account", "A new login to your Agri account was made from {device}. If this wasn't you, review your devices at id.agri.in/devices."),
    ("login_new_device", "email", "ta", "உங்கள் அக்ரி கணக்கில் புதிய உள்நுழைவு", "{device} இலிருந்து உங்கள் அக்ரி கணக்கில் புதிய உள்நுழைவு நடந்தது. இது நீங்கள் இல்லையெனில், id.agri.in/devices இல் உங்கள் சாதனங்களைச் சரிபார்க்கவும்."),
    ("login_new_device", "email", "hi", "आपके एग्री खाते में नया लॉगिन", "{device} से आपके एग्री खाते में नया लॉगिन हुआ। यदि यह आप नहीं थे, तो id.agri.in/devices पर अपने डिवाइस जांचें।"),
    # role_changed - in_app
    ("role_changed", "in_app", "en", None, "Your account role was updated: {role}."),
    ("role_changed", "in_app", "ta", None, "உங்கள் கணக்குப் பங்கு புதுப்பிக்கப்பட்டது: {role}."),
    ("role_changed", "in_app", "hi", None, "आपके खाते की भूमिका बदली गई: {role}।"),
    # generic_announce - in_app
    ("generic_announce", "in_app", "en", None, "{message}"),
    ("generic_announce", "in_app", "ta", None, "{message}"),
    ("generic_announce", "in_app", "hi", None, "{message}"),
    # generic_announce - email
    ("generic_announce", "email", "en", "Announcement from Agri", "{message}"),
    ("generic_announce", "email", "ta", "அக்ரி அறிவிப்பு", "{message}"),
    ("generic_announce", "email", "hi", "एग्री की घोषणा", "{message}"),
]


def upgrade() -> None:
    bind = op.get_bind()
    channel_enum.create(bind, checkfirst=True)
    status_enum.create(bind, checkfirst=True)
    locale_enum.create(bind, checkfirst=True)
    no_create = {"create_type": False}
    channel = postgresql.ENUM(
        "in_app", "sms", "email", name="notify_channel", schema="notify", **no_create
    )
    status = postgresql.ENUM(
        "pending", "sent", "failed", "dead", name="delivery_status", schema="notify", **no_create
    )
    locale = postgresql.ENUM("en", "ta", "hi", name="notify_locale", schema="notify", **no_create)

    op.create_table(
        "templates",
        pk_column(),
        *timestamp_columns(),
        sa.Column("key", sa.Text, nullable=False),
        sa.Column("channel", channel, nullable=False),
        sa.Column("locale", locale, nullable=False),
        sa.Column("subject", sa.Text, nullable=True),
        sa.Column("body", sa.Text, nullable=False),
        sa.UniqueConstraint("key", "channel", "locale"),
        schema="notify",
    )
    op.create_table(
        "notifications",
        pk_column(),
        *timestamp_columns(),
        sa.Column("user_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("template_key", sa.Text, nullable=False),
        sa.Column("payload", postgresql.JSONB, nullable=False, server_default=sa.text("'{}'::jsonb")),
        sa.Column("locale", locale, nullable=False, server_default="en"),
        sa.Column("read_at", sa.TIMESTAMP(timezone=True), nullable=True),
        schema="notify",
    )
    op.create_index(None, "notifications", ["user_id"], schema="notify")
    # unread-count is the hot query: partial index on the unread rows only
    op.create_index(
        "ix_notify_notifications_unread",
        "notifications",
        ["user_id"],
        schema="notify",
        postgresql_where=sa.text("read_at IS NULL"),
    )
    op.create_table(
        "deliveries",
        pk_column(),
        *timestamp_columns(),
        sa.Column(
            "notification_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("notify.notifications.id"),
            nullable=False,
        ),
        sa.Column("channel", channel, nullable=False),
        sa.Column("status", status, nullable=False, server_default="pending"),
        sa.Column("attempts", sa.Integer, nullable=False, server_default="0"),
        sa.Column("next_attempt_at", sa.TIMESTAMP(timezone=True), nullable=True),
        sa.Column("destination", sa.Text, nullable=True),
        sa.Column("provider_ref", sa.Text, nullable=True),
        sa.Column("cost", sa.Numeric(10, 4), nullable=True),
        sa.Column("last_error", sa.Text, nullable=True),
        schema="notify",
    )
    op.create_index(None, "deliveries", ["notification_id"], schema="notify")
    op.create_index(
        "ix_notify_deliveries_retry_due",
        "deliveries",
        ["next_attempt_at"],
        schema="notify",
        postgresql_where=sa.text("status = 'failed'"),
    )
    op.create_table(
        "preferences",
        pk_column(),
        *timestamp_columns(),
        sa.Column("user_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("channel", channel, nullable=False),
        sa.Column("enabled", sa.Boolean, nullable=False, server_default=sa.text("true")),
        sa.UniqueConstraint("user_id", "channel"),
        schema="notify",
    )

    op.bulk_insert(
        templates_table,
        [
            {
                "id": uuid6.uuid7(),
                "key": key,
                "channel": chan,
                "locale": loc,
                "subject": subject,
                "body": body,
            }
            for key, chan, loc, subject, body in SEED_TEMPLATES
        ],
    )
    op.execute(
        sa.text(
            "INSERT INTO public.feature_flags (key, enabled, description) "
            "VALUES ('notify.email_enabled', false, "
            "'D12: real/email sends for the notify engine (ZeptoMail driver)') "
            "ON CONFLICT (key) DO NOTHING"
        )
    )


def downgrade() -> None:
    op.execute(sa.text("DELETE FROM public.feature_flags WHERE key = 'notify.email_enabled'"))
    op.drop_table("preferences", schema="notify")
    op.drop_table("deliveries", schema="notify")
    op.drop_table("notifications", schema="notify")
    op.drop_table("templates", schema="notify")
    for enum in (status_enum, channel_enum, locale_enum):
        enum.drop(op.get_bind(), checkfirst=True)
```

- [ ] **Step 5: Run migrate_check + tests + linters**

Run: `python scripts/migrate_check.py && python -m pytest tests/test_notify_templates.py -v && ruff format --check . && ruff check . && mypy . && lint-imports`
Expected: PASS.

- [ ] **Step 6: Commit**

```bash
git add backend/core/alembic/versions/0013_notify_v1.py backend/core/modules/notify/models.py backend/core/tests/test_notify_templates.py
git commit -m "feat(d12): notify schema, seeded templates (en/ta/hi), email flag"
```

---

### Task 7: Template rendering (injection-safe) + locale fallback

**Files:**
- Create: `backend/core/modules/notify/rendering.py`
- Test: `backend/core/tests/test_notify_rendering.py`

**Interfaces:**
- Produces (used by Tasks 9, 11):
  - `class MissingVariableError(KeyError)`
  - `def render_template(body: str, payload: Mapping[str, object], *, escape_html: bool = False, strict: bool = True) -> str` — `{var}` substitution only; strict raises on missing vars (send path), non-strict substitutes `""` (read path).
  - `async def load_template(session, *, key: str, channel: str, locale: str) -> Template | None` — exact locale, else `en`.

- [ ] **Step 1: Write the failing tests**

```python
# backend/core/tests/test_notify_rendering.py
"""D12 threat model: template-variable injection. Values must never alter
template structure; email values are HTML-escaped."""

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from modules.notify.rendering import MissingVariableError, load_template, render_template


def test_renders_simple_variables() -> None:
    assert render_template("Hello {name}!", {"name": "Asha"}) == "Hello Asha!"


def test_missing_variable_is_a_hard_error_when_strict() -> None:
    with pytest.raises(MissingVariableError):
        render_template("Hello {name}!", {})


def test_lenient_mode_substitutes_empty_for_missing() -> None:
    assert render_template("Hello {name}!", {}, strict=False) == "Hello !"


def test_payload_values_cannot_inject_placeholders() -> None:
    # a value containing {other} must land literally, not resolve
    out = render_template("Hi {name}", {"name": "{secret}", "secret": "x"})
    assert out == "Hi {secret}"


def test_html_is_escaped_for_email() -> None:
    out = render_template("Hi {name}", {"name": "<script>alert(1)</script>"}, escape_html=True)
    assert "<script>" not in out
    assert "&lt;script&gt;" in out


def test_format_spec_syntax_is_not_interpreted() -> None:
    # str.format would explode or leak on {name.__class__}; our renderer must
    # treat anything but a bare [a-z0-9_]+ name as literal text
    template = "Hi {name.__class__} and {name!r} and {0}"
    assert render_template(template, {"name": "x"}) == template


async def test_load_template_falls_back_to_english(db_session: AsyncSession) -> None:
    exact = await load_template(db_session, key="welcome", channel="in_app", locale="ta")
    assert exact is not None and exact.locale == "ta"
    # role_changed has no sms row at all -> None even after fallback
    missing = await load_template(db_session, key="role_changed", channel="sms", locale="ta")
    assert missing is None
```

- [ ] **Step 2: Run to verify failure**

Run: `python -m pytest tests/test_notify_rendering.py -v`
Expected: FAIL — module missing.

- [ ] **Step 3: Implement**

```python
# backend/core/modules/notify/rendering.py
"""{var}-only template rendering (D12).

Deliberately NOT str.format: format-spec/attribute syntax ({x.__class__},
{x!r}, {0}) stays literal, so payload values can never traverse objects.
Substitution is single-pass over the TEMPLATE only - braces inside payload
values land as literal text (injection defence, pinned by tests)."""

import html
import re
from collections.abc import Mapping

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from modules.notify.models import Template

_VAR_RE = re.compile(r"\{([a-z0-9_]+)\}")


class MissingVariableError(KeyError):
    """Template references a variable the payload does not carry."""


def render_template(
    body: str,
    payload: Mapping[str, object],
    *,
    escape_html: bool = False,
    strict: bool = True,
) -> str:
    def substitute(match: re.Match[str]) -> str:
        name = match.group(1)
        if name not in payload:
            if strict:
                raise MissingVariableError(name)
            return ""
        value = str(payload[name])
        return html.escape(value) if escape_html else value

    return _VAR_RE.sub(substitute, body)


async def load_template(
    session: AsyncSession, *, key: str, channel: str, locale: str
) -> Template | None:
    """Exact locale, else English (runtime fallback; the seed-completeness CI
    gate makes this a during-deploy safety net, not a normal path)."""
    for candidate in (locale, "en"):
        template = await session.scalar(
            select(Template).where(
                Template.key == key,
                Template.channel == channel,
                Template.locale == candidate,
            )
        )
        if template is not None:
            return template
        if candidate == "en":
            break
    return None
```

- [ ] **Step 4: Run tests + linters**

Run: `python -m pytest tests/test_notify_rendering.py -v && ruff format --check . && ruff check . && mypy . && lint-imports`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add backend/core/modules/notify/rendering.py backend/core/tests/test_notify_rendering.py
git commit -m "feat(d12): injection-safe template rendering with locale fallback"
```

---

### Task 8: Drivers (mock SMS/email, ZeptoMail) + settings + lint contract

**Files:**
- Create: `backend/core/modules/notify/drivers.py`
- Modify: `backend/core/settings.py` (notify settings block)
- Modify: `backend/core/pyproject.toml` (import-linter forbidden contract)
- Modify: `backend/core/tests/conftest.py` (driver outbox resets)
- Test: `backend/core/tests/test_notify_drivers.py`

**Interfaces:**
- Produces (used by Task 9):
  - `class EmailDriver(Protocol): async def send(self, to: str, subject: str, body: str) -> str | None` (returns provider_ref)
  - `class NotifySmsDriver(Protocol): async def send(self, phone: str, body: str) -> str | None`
  - `MockEmailDriver` / `MockNotifySmsDriver` with `ClassVar outbox: list[tuple[str, str, str]]` / `list[tuple[str, str]]` and `reset()`
  - `ZeptoMailDriver(transport: httpx.AsyncBaseTransport | None = None)`
  - `def get_email_driver() -> EmailDriver`, `def get_notify_sms_driver() -> NotifySmsDriver` (single selection points)
  - Settings: `email_provider: Literal["mock", "zeptomail"] = "mock"`, `zeptomail_token: str = ""`, `zeptomail_from: str = "no-reply@agri.in"`, `notify_user_hourly_cap: int = 30`, `notify_worker_enabled: bool = True`

- [ ] **Step 1: Write the failing tests**

```python
# backend/core/tests/test_notify_drivers.py
"""D12 drivers: mock outboxes for tests/dev; ZeptoMail exercised only through
an injected httpx transport (a vendor call from tests is a spec violation)."""

import httpx
import pytest

from modules.notify.drivers import (
    MockEmailDriver,
    MockNotifySmsDriver,
    ZeptoMailDriver,
    get_email_driver,
    get_notify_sms_driver,
)


async def test_mock_email_lands_in_outbox() -> None:
    ref = await MockEmailDriver().send("farmer@example.com", "Hi", "Body")
    assert MockEmailDriver.outbox == [("farmer@example.com", "Hi", "Body")]
    assert ref is None


async def test_mock_sms_lands_in_outbox() -> None:
    await MockNotifySmsDriver().send("+919876500001", "Body")
    assert MockNotifySmsDriver.outbox == [("+919876500001", "Body")]


def test_default_selection_is_mock() -> None:
    assert isinstance(get_email_driver(), MockEmailDriver)
    assert isinstance(get_notify_sms_driver(), MockNotifySmsDriver)


async def test_zeptomail_posts_and_returns_request_id(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("ZEPTOMAIL_TOKEN", "test-token")
    seen: dict[str, object] = {}

    def handler(request: httpx.Request) -> httpx.Response:
        seen["url"] = str(request.url)
        seen["auth"] = request.headers["authorization"]
        return httpx.Response(201, json={"request_id": "zepto-123"})

    driver = ZeptoMailDriver(transport=httpx.MockTransport(handler))
    ref = await driver.send("farmer@example.com", "Hi", "Body")
    assert ref == "zepto-123"
    assert seen["url"] == "https://api.zeptomail.in/v1.1/email"
    assert seen["auth"] == "Zoho-enczapikey test-token"


async def test_zeptomail_raises_on_http_error() -> None:
    driver = ZeptoMailDriver(
        transport=httpx.MockTransport(lambda request: httpx.Response(500, json={}))
    )
    with pytest.raises(httpx.HTTPStatusError):
        await driver.send("farmer@example.com", "Hi", "Body")
```

- [ ] **Step 2: Run to verify failure**

Run: `python -m pytest tests/test_notify_drivers.py -v`
Expected: FAIL — module missing.

- [ ] **Step 3: Implement**

Append to `backend/core/settings.py` (after the msg91 block):

```python
    # Notify engine (D12). Email is mock by default; the ZeptoMail driver is
    # additionally gated by the notify.email_enabled DB flag. The hourly cap
    # is the harassment brake from the threat model.
    email_provider: Literal["mock", "zeptomail"] = "mock"
    zeptomail_token: str = ""
    zeptomail_from: str = "no-reply@agri.in"
    notify_user_hourly_cap: int = 30
    notify_worker_enabled: bool = True
```

Create `backend/core/modules/notify/drivers.py`:

```python
"""Notify channel drivers (D12): mock SMS + mock/ZeptoMail email.

get_*_driver() are the ONLY selection points, mirroring identity's
otp_drivers pattern. An import-linter forbidden contract keeps every other
module away from this file: sends go through the notify engine (preferences,
rate cap, flag) or not at all. Destinations and bodies are never logged."""

from typing import ClassVar, Protocol

import httpx

from settings import get_settings
from shared.telemetry import get_logger

logger = get_logger(__name__)

ZEPTOMAIL_SEND_URL = "https://api.zeptomail.in/v1.1/email"


class EmailDriver(Protocol):
    async def send(self, to: str, subject: str, body: str) -> str | None: ...


class NotifySmsDriver(Protocol):
    async def send(self, phone: str, body: str) -> str | None: ...


class MockEmailDriver:
    """Dev/test: mails land in an inspectable in-memory outbox."""

    outbox: ClassVar[list[tuple[str, str, str]]] = []

    async def send(self, to: str, subject: str, body: str) -> str | None:
        MockEmailDriver.outbox.append((to, subject, body))
        logger.info("mock email queued", extra={"extra_fields": {"subject_len": len(subject)}})
        return None

    @classmethod
    def reset(cls) -> None:
        cls.outbox.clear()


class MockNotifySmsDriver:
    """Dev/test: SMS lands in an inspectable in-memory outbox. The real
    transactional-SMS adapter arrives when DLT templates for notify clear;
    identity's OTP driver is purpose-specific and stays in identity."""

    outbox: ClassVar[list[tuple[str, str]]] = []

    async def send(self, phone: str, body: str) -> str | None:
        MockNotifySmsDriver.outbox.append((phone, body))
        logger.info("mock notify sms queued", extra={"extra_fields": {"body_len": len(body)}})
        return None

    @classmethod
    def reset(cls) -> None:
        cls.outbox.clear()


class ZeptoMailDriver:
    """Zoho ZeptoMail transactional API. Tests use an injected transport only."""

    def __init__(self, transport: httpx.AsyncBaseTransport | None = None) -> None:
        self._transport = transport

    async def send(self, to: str, subject: str, body: str) -> str | None:
        settings = get_settings()
        payload = {
            "from": {"address": settings.zeptomail_from},
            "to": [{"email_address": {"address": to}}],
            "subject": subject,
            "htmlbody": body,
        }
        async with httpx.AsyncClient(transport=self._transport, timeout=10.0) as client:
            response = await client.post(
                ZEPTOMAIL_SEND_URL,
                json=payload,
                headers={"authorization": f"Zoho-enczapikey {settings.zeptomail_token}"},
            )
        response.raise_for_status()
        data = response.json()
        request_id = data.get("request_id")
        logger.info("zeptomail sent", extra={"extra_fields": {"request_id": request_id}})
        return str(request_id) if request_id is not None else None


def get_email_driver() -> EmailDriver:
    if get_settings().email_provider == "zeptomail":
        return ZeptoMailDriver()
    return MockEmailDriver()


def get_notify_sms_driver() -> NotifySmsDriver:
    return MockNotifySmsDriver()
```

Wait — `ZEPTOMAIL_TOKEN` env var: pydantic-settings maps `zeptomail_token` automatically; the monkeypatch in the test plus `get_settings.cache_clear()` in `_reset_state` covers it, but within a single test `get_settings` may be cached BEFORE the monkeypatch. In the test above, call `get_settings.cache_clear()` right after `monkeypatch.setenv` (add that line to the test).

In `backend/core/pyproject.toml`, after the existing contracts add:

```toml
[[tool.importlinter.contracts]]
name = "Notify drivers only reachable from inside notify (D12 lint contract)"
type = "forbidden"
source_modules = [
    "modules.identity",
    "modules.coins",
    "modules.directory",
    "modules.leads",
    "modules.content",
    "modules.market_data",
    "modules.ads",
    "modules.search",
    "modules.billing",
    "modules.ai",
    "shared",
]
forbidden_modules = ["modules.notify.drivers"]
```

In `backend/core/tests/conftest.py`: import `from modules.notify.drivers import MockEmailDriver, MockNotifySmsDriver` and add `MockEmailDriver.reset()` and `MockNotifySmsDriver.reset()` to `_reset_state`.

- [ ] **Step 4: Run tests + linters**

Run: `python -m pytest tests/test_notify_drivers.py -v && ruff format --check . && ruff check . && mypy . && lint-imports`
Expected: PASS (lint-imports now enforces the new contract).

- [ ] **Step 5: Commit**

```bash
git add backend/core/modules/notify/drivers.py backend/core/settings.py backend/core/pyproject.toml backend/core/tests/conftest.py backend/core/tests/test_notify_drivers.py
git commit -m "feat(d12): notify drivers (mock sms/email, zeptomail) behind lint contract"
```

---

### Task 9: Dispatch engine — preferences, rate cap, deliveries, retry/dead-letter

**Files:**
- Modify: `backend/core/modules/notify/service.py` (full implementation)
- Modify: `backend/core/shared/metrics.py` (notify counters)
- Test: `backend/core/tests/test_notify_service.py`

**Interfaces:**
- Consumes: models (T6), rendering (T7), drivers (T8), `shared.flags.flag_enabled`, `shared.cache.get_redis`.
- Produces (used by Tasks 10, 11):
  - `@dataclass(frozen=True) NotifyRequest: user_id: uuid.UUID; template_key: str; payload: dict[str, Any]; locale: str = "en"; email: str | None = None; phone: str | None = None; channels: frozenset[str] = frozenset()` (extra channels beyond always-on in_app)
  - `async def dispatch(session, request: NotifyRequest, *, now: datetime | None = None) -> Notification | None` (None = dropped by rate cap)
  - `async def retry_due_deliveries(session, *, now: datetime | None = None) -> int`
  - `async def channel_enabled(session, user_id, channel) -> bool`
  - `MAX_DELIVERY_ATTEMPTS = 3`, `RETRY_BACKOFF_SECONDS = (60, 300, 1500)`
  - Metrics `NOTIFY_SENT(channel, status)`, `NOTIFY_DROPPED(reason)`

- [ ] **Step 1: Write the failing tests**

```python
# backend/core/tests/test_notify_service.py
"""D12 engine: preference routing, rate cap, retry w/ backoff, dead-letter."""

import uuid
from datetime import UTC, datetime, timedelta

import pytest
from redis.asyncio import Redis
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from modules.notify.drivers import MockEmailDriver, MockNotifySmsDriver
from modules.notify.models import Delivery, Notification, Preference
from modules.notify.service import (
    MAX_DELIVERY_ATTEMPTS,
    RETRY_BACKOFF_SECONDS,
    NotifyRequest,
    dispatch,
    retry_due_deliveries,
)
from shared.flags import FeatureFlag

NOW = datetime(2026, 7, 12, 10, 0, tzinfo=UTC)


def _request(**overrides: object) -> NotifyRequest:
    defaults: dict[str, object] = {
        "user_id": uuid.uuid4(),
        "template_key": "login_new_device",
        "payload": {"device": "Chrome on Android"},
        "locale": "en",
        "email": "farmer@example.com",
        "phone": "+919876500001",
        "channels": frozenset({"sms", "email"}),
    }
    defaults.update(overrides)
    return NotifyRequest(**defaults)  # type: ignore[arg-type]


async def _enable_email_flag(session: AsyncSession) -> None:
    flag = await session.get(FeatureFlag, "notify.email_enabled")
    assert flag is not None
    flag.enabled = True
    await session.flush()


async def test_in_app_row_always_created(db_session: AsyncSession, otp_redis: Redis) -> None:
    request = _request(channels=frozenset())
    notification = await dispatch(db_session, request, now=NOW)
    assert notification is not None and notification.read_at is None
    deliveries = (await db_session.scalars(select(Delivery))).all()
    assert deliveries == []  # no extra channels requested


async def test_sms_opt_out_routes_in_app_only(db_session: AsyncSession, otp_redis: Redis) -> None:
    await _enable_email_flag(db_session)
    request = _request()
    db_session.add(Preference(user_id=request.user_id, channel="sms", enabled=False))
    await db_session.flush()
    await dispatch(db_session, request, now=NOW)
    channels = {d.channel for d in (await db_session.scalars(select(Delivery))).all()}
    assert channels == {"email"}          # sms suppressed by preference
    assert MockNotifySmsDriver.outbox == []
    assert len(MockEmailDriver.outbox) == 1


async def test_email_skipped_when_flag_off(db_session: AsyncSession, otp_redis: Redis) -> None:
    await dispatch(db_session, _request(channels=frozenset({"email"})), now=NOW)
    assert MockEmailDriver.outbox == []
    assert (await db_session.scalars(select(Delivery))).all() == []


async def test_missing_destination_skips_channel(db_session: AsyncSession, otp_redis: Redis) -> None:
    await _enable_email_flag(db_session)
    await dispatch(db_session, _request(email=None), now=NOW)
    channels = {d.channel for d in (await db_session.scalars(select(Delivery))).all()}
    assert channels == {"sms"}


async def test_rate_cap_drops_whole_notification(db_session: AsyncSession, otp_redis: Redis) -> None:
    request = _request(channels=frozenset())
    from settings import get_settings

    cap = get_settings().notify_user_hourly_cap
    for _ in range(cap):
        assert await dispatch(db_session, request, now=NOW) is not None
    assert await dispatch(db_session, request, now=NOW) is None
    count = len((await db_session.scalars(select(Notification))).all())
    assert count == cap


async def test_failed_send_schedules_backoff_then_dead_letters(
    db_session: AsyncSession, otp_redis: Redis, monkeypatch: pytest.MonkeyPatch
) -> None:
    await _enable_email_flag(db_session)

    async def boom(self: object, to: str, subject: str, body: str) -> str | None:
        raise RuntimeError("provider down")

    monkeypatch.setattr(MockEmailDriver, "send", boom)
    await dispatch(db_session, _request(channels=frozenset({"email"})), now=NOW)
    delivery = (await db_session.scalars(select(Delivery))).one()
    assert delivery.status == "failed"
    assert delivery.attempts == 1
    assert delivery.next_attempt_at == NOW + timedelta(seconds=RETRY_BACKOFF_SECONDS[0])

    # drive retries until dead
    for attempt in range(2, MAX_DELIVERY_ATTEMPTS + 1):
        due_at = delivery.next_attempt_at
        retried = await retry_due_deliveries(db_session, now=due_at)
        assert retried == 1
        await db_session.refresh(delivery)
        assert delivery.attempts == attempt
    assert delivery.status == "dead"
    assert delivery.next_attempt_at is None


async def test_retry_succeeds_and_marks_sent(
    db_session: AsyncSession, otp_redis: Redis, monkeypatch: pytest.MonkeyPatch
) -> None:
    await _enable_email_flag(db_session)
    calls = {"n": 0}
    real_send = MockEmailDriver.send

    async def flaky(self: MockEmailDriver, to: str, subject: str, body: str) -> str | None:
        calls["n"] += 1
        if calls["n"] == 1:
            raise RuntimeError("blip")
        return await real_send(self, to, subject, body)

    monkeypatch.setattr(MockEmailDriver, "send", flaky)
    await dispatch(db_session, _request(channels=frozenset({"email"})), now=NOW)
    delivery = (await db_session.scalars(select(Delivery))).one()
    assert delivery.status == "failed"
    await retry_due_deliveries(db_session, now=delivery.next_attempt_at)
    await db_session.refresh(delivery)
    assert delivery.status == "sent"
    assert len(MockEmailDriver.outbox) == 1
```

- [ ] **Step 2: Run to verify failure**

Run: `python -m pytest tests/test_notify_service.py -v`
Expected: FAIL — service is an empty stub.

- [ ] **Step 3: Implement modules/notify/service.py**

```python
"""Notify engine (D12): the ONLY send path.

Every send flows dispatch() -> preferences -> flag -> driver. Modules never
touch drivers (import-linter contract); they publish events and the consumer
calls dispatch(). In-app is unconditional (and not toggleable); sms/email are
opt-out via notify.preferences rows. The per-user hourly cap is the
harassment brake: over-cap events drop entirely, with a metric.

Retries: a failed delivery gets exponential backoff via next_attempt_at and
dies (status 'dead') after MAX_DELIVERY_ATTEMPTS - the delivery-level
dead-letter, distinct from the bus-level :dlq stream."""

import uuid
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from modules.notify.drivers import get_email_driver, get_notify_sms_driver
from modules.notify.models import Delivery, Notification, Preference
from modules.notify.rendering import load_template, render_template
from settings import get_settings
from shared.cache import get_redis
from shared.flags import flag_enabled
from shared.metrics import NOTIFY_DROPPED, NOTIFY_SENT
from shared.telemetry import get_logger

logger = get_logger(__name__)

MAX_DELIVERY_ATTEMPTS = 3
RETRY_BACKOFF_SECONDS = (60, 300, 1500)


@dataclass(frozen=True, slots=True)
class NotifyRequest:
    user_id: uuid.UUID
    template_key: str
    payload: dict[str, Any]
    locale: str = "en"
    email: str | None = None
    phone: str | None = None
    channels: frozenset[str] = field(default_factory=frozenset)  # beyond in_app


async def channel_enabled(session: AsyncSession, user_id: uuid.UUID, channel: str) -> bool:
    """No row means enabled: preferences store opt-outs."""
    row = await session.scalar(
        select(Preference.enabled).where(
            Preference.user_id == user_id, Preference.channel == channel
        )
    )
    return True if row is None else bool(row)


async def _within_rate_cap(user_id: uuid.UUID, now: datetime) -> bool:
    cap = get_settings().notify_user_hourly_cap
    key = f"notify:cap:{user_id}:{now.strftime('%Y%m%d%H')}"
    redis = get_redis()
    count = int(await redis.incr(key))
    if count == 1:
        await redis.expire(key, 3600)
    return count <= cap


async def dispatch(
    session: AsyncSession, request: NotifyRequest, *, now: datetime | None = None
) -> Notification | None:
    """Create the in-app notification (always) + channel deliveries (filtered
    by preference/flag/destination), attempting each send once inline."""
    now = now or datetime.now(UTC)
    if not await _within_rate_cap(request.user_id, now):
        NOTIFY_DROPPED.labels("rate_cap").inc()
        logger.warning(
            "notify.dropped.rate_cap",
            extra={"extra_fields": {"template_key": request.template_key}},
        )
        return None
    notification = Notification(
        user_id=request.user_id,
        template_key=request.template_key,
        payload=request.payload,
        locale=request.locale,
    )
    session.add(notification)
    await session.flush()
    NOTIFY_SENT.labels("in_app", "sent").inc()

    for channel in sorted(request.channels & {"sms", "email"}):
        if not await channel_enabled(session, request.user_id, channel):
            NOTIFY_DROPPED.labels("preference").inc()
            continue
        if channel == "email" and not await flag_enabled("notify.email_enabled", session=session):
            NOTIFY_DROPPED.labels("flag").inc()
            continue
        destination = request.email if channel == "email" else request.phone
        if not destination:
            NOTIFY_DROPPED.labels("no_destination").inc()
            continue
        delivery = Delivery(
            notification_id=notification.id, channel=channel, destination=destination
        )
        session.add(delivery)
        await session.flush()
        await _attempt(session, delivery, notification, now=now)
    return notification


async def _attempt(
    session: AsyncSession, delivery: Delivery, notification: Notification, *, now: datetime
) -> None:
    template = await load_template(
        session,
        key=notification.template_key,
        channel=delivery.channel,
        locale=notification.locale,
    )
    delivery.attempts += 1
    if template is None:
        # a template gap is permanent - retrying cannot fix it
        delivery.status = "dead"
        delivery.next_attempt_at = None
        delivery.last_error = "template_missing"
        NOTIFY_SENT.labels(delivery.channel, "dead").inc()
        return
    try:
        if delivery.channel == "email":
            body = render_template(template.body, notification.payload, escape_html=True)
            subject = render_template(template.subject or "", notification.payload)
            assert delivery.destination is not None
            delivery.provider_ref = await get_email_driver().send(
                delivery.destination, subject, body
            )
        else:
            body = render_template(template.body, notification.payload)
            assert delivery.destination is not None
            delivery.provider_ref = await get_notify_sms_driver().send(delivery.destination, body)
        delivery.status = "sent"
        delivery.next_attempt_at = None
        delivery.last_error = None
        NOTIFY_SENT.labels(delivery.channel, "sent").inc()
    except Exception as exc:
        delivery.last_error = type(exc).__name__  # class only - message may carry PII
        if delivery.attempts >= MAX_DELIVERY_ATTEMPTS:
            delivery.status = "dead"
            delivery.next_attempt_at = None
            NOTIFY_SENT.labels(delivery.channel, "dead").inc()
        else:
            delivery.status = "failed"
            delivery.next_attempt_at = now + timedelta(
                seconds=RETRY_BACKOFF_SECONDS[delivery.attempts - 1]
            )
            NOTIFY_SENT.labels(delivery.channel, "failed").inc()
    await session.flush()


async def retry_due_deliveries(session: AsyncSession, *, now: datetime | None = None) -> int:
    """Re-attempt every failed delivery whose backoff has elapsed."""
    now = now or datetime.now(UTC)
    due = (
        await session.scalars(
            select(Delivery).where(Delivery.status == "failed", Delivery.next_attempt_at <= now)
        )
    ).all()
    for delivery in due:
        notification = await session.get(Notification, delivery.notification_id)
        assert notification is not None  # FK guarantees existence
        await _attempt(session, delivery, notification, now=now)
    return len(due)
```

In `backend/core/shared/metrics.py` add (next to the audit block):

```python
NOTIFY_SENT = Counter(
    "notify_sends_total",
    "Notification channel outcomes",
    ["channel", "status"],  # status: sent | failed | dead
    registry=registry,
)
NOTIFY_DROPPED = Counter(
    "notify_dropped_total",
    "Notifications or channel sends suppressed before any driver call",
    ["reason"],  # rate_cap | preference | flag | no_destination
    registry=registry,
)
```

and add both to `reset_metrics()`.

- [ ] **Step 4: Run tests + linters**

Run: `python -m pytest tests/test_notify_service.py -v && ruff format --check . && ruff check . && mypy . && lint-imports`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add backend/core/modules/notify/service.py backend/core/shared/metrics.py backend/core/tests/test_notify_service.py
git commit -m "feat(d12): notify dispatch engine with preferences, rate cap, retry/dead-letter"
```

---

### Task 10: Event consumers, identity publishes, lifespan worker

**Files:**
- Create: `backend/core/modules/notify/consumers.py`
- Create: `backend/core/modules/notify/worker.py`
- Modify: `backend/core/modules/identity/session_router.py:106-139` (login: signup/new-device events)
- Modify: `backend/core/modules/identity/admin_router.py` (`add_role`: role_changed event)
- Modify: `backend/core/main.py:122-131` (lifespan worker task)
- Test: `backend/core/tests/test_notify_consumers.py`

**Interfaces:**
- Consumes: `shared.events.EventConsumer/publish`, `dispatch()` (T9).
- Produces:
  - Events (payload contract for D13+ too): stream `"identity"` types `identity.signup_completed`, `identity.login_new_device`, `identity.role_changed`; stream `"notify"` type `notify.announce`. Payload shape: `{"user_id": str, "agri_id": str, "locale": str, "email": str | null, "phone": str | null, "vars": {…template vars…}}`.
  - `EVENT_ROUTES: dict[str, tuple[str, frozenset[str]]]` mapping event type → (template_key, extra channels)
  - `async def handle_event(session, event: Event) -> None`
  - `async def run_worker(stop: asyncio.Event, *, poll_interval: float = 2.0) -> None`

- [ ] **Step 1: Write the failing tests**

```python
# backend/core/tests/test_notify_consumers.py
"""D12: modules emit events; the notify consumer maps them to dispatches."""

import uuid

from redis.asyncio import Redis
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from modules.notify.consumers import EVENT_ROUTES, handle_event
from modules.notify.models import Notification
from shared.events import Event


def _event(event_type: str, **vars_: str) -> tuple[Event, str]:
    user_id = str(uuid.uuid4())
    return (
        Event(
            id="1-1",
            type=event_type,
            payload={
                "user_id": user_id,
                "agri_id": "@asha",
                "locale": "ta",
                "email": None,
                "phone": None,
                "vars": dict(vars_),
            },
        ),
        user_id,
    )


async def test_signup_event_creates_welcome_notification(
    db_session: AsyncSession, otp_redis: Redis
) -> None:
    event, user_id = _event("identity.signup_completed", agri_id="@asha")
    await handle_event(db_session, event)
    row = (await db_session.scalars(select(Notification))).one()
    assert row.template_key == "welcome"
    assert str(row.user_id) == user_id
    assert row.locale == "ta"


async def test_unknown_event_type_is_ignored(db_session: AsyncSession, otp_redis: Redis) -> None:
    event, _ = _event("identity.something_else")
    await handle_event(db_session, event)
    assert (await db_session.scalars(select(Notification))).all() == []


def test_route_table_matches_seeded_templates() -> None:
    assert EVENT_ROUTES == {
        "identity.signup_completed": ("welcome", frozenset({"email"})),
        "identity.login_new_device": ("login_new_device", frozenset({"sms", "email"})),
        "identity.role_changed": ("role_changed", frozenset()),
        "notify.announce": ("generic_announce", frozenset({"email"})),
    }
```

- [ ] **Step 2: Run to verify failure**

Run: `python -m pytest tests/test_notify_consumers.py -v`
Expected: FAIL — module missing.

- [ ] **Step 3: Implement consumers + worker**

```python
# backend/core/modules/notify/consumers.py
"""Event -> notification mapping (D12). Producers know nothing about notify;
they publish domain events with a self-contained payload (destination +
locale resolved at emit time, used once here, never logged)."""

import uuid

from sqlalchemy.ext.asyncio import AsyncSession

from modules.notify.service import NotifyRequest, dispatch
from shared.events import Event
from shared.i18n import SUPPORTED_LOCALES
from shared.telemetry import get_logger

logger = get_logger(__name__)

STREAMS = ("identity", "notify")
CONSUMER_GROUP = "notify"

EVENT_ROUTES: dict[str, tuple[str, frozenset[str]]] = {
    "identity.signup_completed": ("welcome", frozenset({"email"})),
    "identity.login_new_device": ("login_new_device", frozenset({"sms", "email"})),
    "identity.role_changed": ("role_changed", frozenset()),
    "notify.announce": ("generic_announce", frozenset({"email"})),
}


async def handle_event(session: AsyncSession, event: Event) -> None:
    route = EVENT_ROUTES.get(event.type)
    if route is None:
        return  # not every identity-stream event is a notification (e.g. profile.completed)
    template_key, channels = route
    payload = event.payload
    locale = payload.get("locale") or "en"
    if locale not in SUPPORTED_LOCALES:
        locale = "en"
    request = NotifyRequest(
        user_id=uuid.UUID(str(payload["user_id"])),
        template_key=template_key,
        payload=dict(payload.get("vars") or {}),
        locale=locale,
        email=payload.get("email"),
        phone=payload.get("phone"),
        channels=channels,
    )
    await dispatch(session, request)
```

```python
# backend/core/modules/notify/worker.py
"""In-process notify worker (D12): consume events, retry due deliveries,
reap poison messages to the bus DLQ. Started from main.py's lifespan when
settings.notify_worker_enabled; tests call handle_event/retry_due_deliveries
directly and never run this loop."""

import asyncio

from modules.notify.consumers import CONSUMER_GROUP, STREAMS, handle_event
from modules.notify.service import retry_due_deliveries
from shared.db import get_sessionmaker
from shared.events import EventConsumer
from shared.telemetry import get_logger

logger = get_logger(__name__)


async def run_worker(stop: asyncio.Event, *, poll_interval: float = 2.0) -> None:
    consumers = [
        EventConsumer(stream, group=CONSUMER_GROUP, name="notify-worker") for stream in STREAMS
    ]
    for consumer in consumers:
        await consumer.ensure_group()
    logger.info("notify worker started")
    while not stop.is_set():
        try:
            for consumer in consumers:
                for event in await consumer.read(count=10):
                    try:
                        async with get_sessionmaker()() as session:
                            await handle_event(session, event)
                            await session.commit()
                        await consumer.ack(event)
                    except Exception as exc:
                        # unacked -> redelivered; >= max_deliveries -> :dlq
                        logger.warning(
                            "notify.event_failed",
                            extra={
                                "extra_fields": {
                                    "event_type": event.type,
                                    "exc_type": type(exc).__name__,
                                }
                            },
                        )
                await consumer.reap_poison()
            async with get_sessionmaker()() as session:
                await retry_due_deliveries(session)
                await session.commit()
        except Exception as exc:  # a redis blip must not kill the loop
            logger.warning(
                "notify.worker_tick_failed",
                extra={"extra_fields": {"exc_type": type(exc).__name__}},
            )
        try:
            await asyncio.wait_for(stop.wait(), timeout=poll_interval)
        except TimeoutError:
            pass
    logger.info("notify worker stopped")
```

In `backend/core/main.py`, extend `lifespan`:

```python
@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    settings = get_settings()
    configure_logging(settings.log_level)
    get_signing_key()
    logger.info("public routes: %s", app.state.public_routes)
    worker_stop: asyncio.Event | None = None
    worker_task: asyncio.Task[None] | None = None
    if settings.notify_worker_enabled and settings.app_env != "test":
        worker_stop = asyncio.Event()
        worker_task = asyncio.create_task(run_worker(worker_stop))
    yield
    if worker_stop is not None and worker_task is not None:
        worker_stop.set()
        await worker_task
    await close_redis()
```

with `from modules.notify.worker import run_worker` added to imports.

Identity publishes — `session_router.py` `login()` (follow profile_router.py:115-133's commit-then-best-effort pattern; add imports `from shared.events import publish`, `from modules.identity.models import Email, SessionWeb`, plus a module-level `EVENT_STREAM = "identity"` and `logger = get_logger(__name__)` if not present):

```python
    # BEFORE create_web_session (needs the pre-insert device view):
    fingerprint = _fingerprint(request)
    known_device = await session.scalar(
        select(SessionWeb.id)
        .where(SessionWeb.user_id == user.id, SessionWeb.device_fingerprint == fingerprint)
        .limit(1)
    )
```

then after `_set_session_cookie(response, sid)`:

```python
    # commit BEFORE announcing (profile.completed precedent): an event for a
    # rolled-back login must not exist. After commit, publish is best-effort.
    language = await _language_for(session, user.id)
    email = await session.scalar(
        select(Email.email).where(Email.user_id == user.id, Email.verified_at.is_not(None))
    )
    await session.commit()
    event_payload = {
        "user_id": str(user.id),
        "agri_id": user.agri_id,
        "locale": language,
        "email": email,
        "phone": None,  # notify-SMS is mock-only; the phone stays out of the bus for now
    }
    try:
        if is_new_user:
            await publish(
                EVENT_STREAM,
                "identity.signup_completed",
                {**event_payload, "vars": {"agri_id": user.agri_id}},
            )
        elif known_device is None:
            await publish(
                EVENT_STREAM,
                "identity.login_new_device",
                {**event_payload, "vars": {"device": body.device_label or "a new device"}},
            )
    except Exception as exc:
        logger.warning(
            "identity.event_publish_failed",
            extra={"extra_fields": {"exc_type": type(exc).__name__}},
        )
```

(reuse the already-computed `language` for the `LoginOut` response instead of calling `_language_for` twice).

`admin_router.py` `add_role()` — after the `_audit` call, publish `identity.role_changed` the same commit-then-best-effort way: `await session.commit()`, then inside try/except-warning `await publish("identity", "identity.role_changed", {"user_id": str(user.id), "agri_id": user.agri_id, "locale": "en", "email": None, "phone": None, "vars": {"role": body.role}})`. (Locale/email enrichment for admin-initiated events is deliberately skipped — in-app only per EVENT_ROUTES.)

- [ ] **Step 4: Extend tests for the publishes**

In the session-router suite, add: successful FIRST login for a fresh phone publishes `identity.signup_completed` on stream `identity` (use the `redis_client`/`otp_redis` fixtures and `XRANGE identity - +` to read entries; the D09 login tests show how a login is driven end-to-end — reuse their client/OTP-proof helpers); second login from a DIFFERENT device label/UA publishes `identity.login_new_device`; second login from the SAME device publishes nothing new. Assert payloads carry `agri_id` and never the phone.

- [ ] **Step 5: Run + lint + full suite**

Run: `python -m pytest tests/test_notify_consumers.py tests/test_session_router.py -v && python -m pytest -q && ruff format --check . && ruff check . && mypy . && lint-imports`
Expected: PASS.

- [ ] **Step 6: Commit**

```bash
git add backend/core/modules/notify backend/core/modules/identity backend/core/main.py backend/core/tests
git commit -m "feat(d12): event consumers, identity event publishes, lifespan notify worker"
```

---

### Task 11: Notify API routes (list/read/unread-count/preferences) + descending pagination

**Files:**
- Modify: `backend/core/shared/pagination.py:54-84` (add `descending` flag)
- Modify: `backend/core/modules/notify/router.py` (full implementation)
- Test: `backend/core/tests/test_pagination.py` (extend — find the existing file name via `ls backend/core/tests | grep -i pagin`), `backend/core/tests/test_notify_router.py`

**Interfaces:**
- Consumes: models (T6), rendering (T7), `require_auth`'s `request.state.principal` (has `.user_id`), `shared.pagination.paginate`.
- Produces (consumed by the frontend, Task 13):
  - `GET /notify/notifications?cursor=&limit=&locale=` → `{"items": [{"id", "body", "created_at", "read_at"}], "next_cursor"}` (newest first)
  - `POST /notify/notifications/{notification_id}/read` → `{"status": "ok"}`
  - `POST /notify/notifications/read-all` → `{"status": "ok"}`
  - `GET /notify/unread-count` → `{"unread": int}`
  - `GET /notify/preferences` → `{"items": [{"channel", "enabled"}]}` (sms + email only)
  - `PUT /notify/preferences` body `{"channel": "sms"|"email", "enabled": bool}` → `{"status": "ok"}`
  - `paginate(..., descending=True)` keyset-pages newest-first.

- [ ] **Step 1: Write the failing pagination test (extend the existing pagination suite)**

```python
async def test_paginate_descending_orders_newest_first(db_session: AsyncSession) -> None:
    # arrange: reuse the suite's existing seeded model rows (N >= 3)
    page = await paginate(db_session, select(Model), limit=2, descending=True)
    ids = [item.id for item in page.items]
    assert ids == sorted(ids, reverse=True)
    assert page.next_cursor is not None
    page2 = await paginate(
        db_session, select(Model), cursor=page.next_cursor, limit=2, descending=True
    )
    assert all(item.id < min(ids) for item in page2.items)
```

(Adapt `Model` to whatever entity the existing pagination tests seed.)

- [ ] **Step 2: Implement the pagination flag**

In `paginate()`: add keyword `descending: bool = False`; the cursor filter becomes `id_column < decode_cursor(cursor)` when descending (`>` otherwise) and ordering `id_column.desc()` when descending. Docstring: one added line — "descending=True pages newest-first (notifications)". Run the pagination suite: PASS.

- [ ] **Step 3: Write the failing router tests**

```python
# backend/core/tests/test_notify_router.py
"""D12 notify API: owner-scoped list/read/unread/preferences."""
```

Model the app/client setup on `tests/test_admin_router.py` (dependency-override `get_session` with `db_session`, register a stub principal resolver that returns a `WebPrincipal`-shaped object for user A). Cases:
1. list returns the caller's notifications newest-first with RENDERED body in the requested locale (`seed: two Notification rows for user A via dispatch() or direct model insert + one for user B; GET /notify/notifications?locale=ta` → 2 items, body equals the ta template rendered with the payload, user B's row absent);
2. `?locale=xx` → 422/400 (validate against `SUPPORTED_LOCALES`);
3. mark-read sets `read_at` once (second POST is a no-op 200), 404 for another user's notification id;
4. read-all zeroes `unread-count` (assert via `GET /notify/unread-count` before/after);
5. preferences: GET default shows sms+email enabled; PUT `{"channel": "sms", "enabled": false}` flips it (and dispatch() then skips sms — one integration assertion reusing Task 9's helpers); PUT with `channel: "in_app"` → 422.

- [ ] **Step 4: Implement the router**

Replace `backend/core/modules/notify/router.py`:

```python
"""Notify routes (D12): notification center + channel preferences.

All private (SecureRouter default); the principal comes from require_auth via
request.state.principal - notify never imports identity. Bodies render at
read time in the requested locale (lenient mode: a stale payload must not
500 the inbox)."""

import uuid
from datetime import UTC, datetime
from typing import Annotated, Literal

from fastapi import Depends, HTTPException, Query, Request
from pydantic import BaseModel
from sqlalchemy import func, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from modules.notify.models import Notification, Preference
from modules.notify.rendering import load_template, render_template
from shared.db import get_session
from shared.i18n import SUPPORTED_LOCALES
from shared.pagination import paginate
from shared.security import SecureRouter

router = SecureRouter(prefix="/notify", tags=["notify"])

SessionDep = Annotated[AsyncSession, Depends(get_session)]

TOGGLEABLE_CHANNELS = ("sms", "email")


def _user_id(request: Request) -> uuid.UUID:
    principal = getattr(request.state, "principal", None)
    assert principal is not None  # require_auth ran (private route)
    return principal.user_id  # type: ignore[no-any-return]


class NotificationOut(BaseModel):
    id: uuid.UUID
    body: str
    created_at: datetime
    read_at: datetime | None


class NotificationPage(BaseModel):
    items: list[NotificationOut]
    next_cursor: str | None


class UnreadOut(BaseModel):
    unread: int


class StatusOut(BaseModel):
    status: Literal["ok"] = "ok"


class PreferenceOut(BaseModel):
    channel: str
    enabled: bool


class PreferencesOut(BaseModel):
    items: list[PreferenceOut]


class PreferenceIn(BaseModel):
    channel: Literal["sms", "email"]
    enabled: bool


@router.get("/notifications")
async def list_notifications(
    request: Request,
    session: SessionDep,
    cursor: str | None = None,
    limit: int = 20,
    locale: Annotated[str, Query(pattern="^(en|ta|hi)$")] = "en",
) -> NotificationPage:
    assert locale in SUPPORTED_LOCALES
    page = await paginate(
        session,
        select(Notification).where(Notification.user_id == _user_id(request)),
        cursor=cursor,
        limit=limit,
        descending=True,
    )
    items: list[NotificationOut] = []
    for row in page.items:
        template = await load_template(
            session, key=row.template_key, channel="in_app", locale=locale
        )
        body = (
            render_template(template.body, row.payload, strict=False)
            if template is not None
            else row.template_key
        )
        items.append(
            NotificationOut(id=row.id, body=body, created_at=row.created_at, read_at=row.read_at)
        )
    return NotificationPage(items=items, next_cursor=page.next_cursor)


@router.post("/notifications/read-all")
async def read_all(request: Request, session: SessionDep) -> StatusOut:
    await session.execute(
        update(Notification)
        .where(Notification.user_id == _user_id(request), Notification.read_at.is_(None))
        .values(read_at=datetime.now(UTC))
    )
    return StatusOut()


@router.post("/notifications/{notification_id}/read")
async def mark_read(notification_id: uuid.UUID, request: Request, session: SessionDep) -> StatusOut:
    row = await session.scalar(
        select(Notification).where(
            Notification.id == notification_id, Notification.user_id == _user_id(request)
        )
    )
    if row is None:
        raise HTTPException(status_code=404, detail="unknown_notification")
    if row.read_at is None:
        row.read_at = datetime.now(UTC)
    return StatusOut()


@router.get("/unread-count")
async def unread_count(request: Request, session: SessionDep) -> UnreadOut:
    count = await session.scalar(
        select(func.count())
        .select_from(Notification)
        .where(Notification.user_id == _user_id(request), Notification.read_at.is_(None))
    )
    return UnreadOut(unread=int(count or 0))


@router.get("/preferences")
async def get_preferences(request: Request, session: SessionDep) -> PreferencesOut:
    rows = (
        await session.scalars(select(Preference).where(Preference.user_id == _user_id(request)))
    ).all()
    stored = {row.channel: row.enabled for row in rows}
    return PreferencesOut(
        items=[
            PreferenceOut(channel=channel, enabled=stored.get(channel, True))
            for channel in TOGGLEABLE_CHANNELS
        ]
    )


@router.put("/preferences")
async def put_preference(body: PreferenceIn, request: Request, session: SessionDep) -> StatusOut:
    user_id = _user_id(request)
    row = await session.scalar(
        select(Preference).where(Preference.user_id == user_id, Preference.channel == body.channel)
    )
    if row is None:
        session.add(Preference(user_id=user_id, channel=body.channel, enabled=body.enabled))
    else:
        row.enabled = body.enabled
    return StatusOut()
```

Note the routing-order trap: `/notifications/read-all` MUST be declared before `/notifications/{notification_id}/read` (as above) or "read-all" parses as a UUID and 422s.

- [ ] **Step 5: Run + lint + public-routes check**

Run: `python -m pytest tests/test_notify_router.py tests/test_pagination*.py -v && ruff format --check . && ruff check . && mypy . && lint-imports && python scripts/dump_public_routes.py`
Expected: tests PASS; the public-routes dump matches `public_routes.txt` unchanged (all new routes private).

- [ ] **Step 6: Commit**

```bash
git add backend/core/shared/pagination.py backend/core/modules/notify/router.py backend/core/tests
git commit -m "feat(d12): notify API (list/read/unread/preferences), descending keyset pages"
```

---

### Task 12: packages/ui — NotificationBell + NotificationsPanel + i18n + demo

**Files:**
- Create: `packages/ui/src/components/notification-bell.tsx`
- Create: `packages/ui/src/composites/notifications-panel.tsx`
- Create: `packages/ui/src/components/notification-bell.test.ts`
- Modify: `packages/ui/src/index.ts`
- Modify: `packages/ui/src/i18n/messages/en.json`, `ta.json`, `hi.json` (`ui.notifications.*`)
- Modify: `apps/web-agri/app/demo/page.tsx` (showcase both)

**Interfaces:**
- Produces (used by Task 13):
  - `NotificationBell({ unread?: number; label: string; className?; ...button props })` — presentational, server-safe; 🔔 glyph + numeric pill (`formatUnread` exported: `0 → ""`, `1..99 → String`, `>99 → "99+"`).
  - `NotificationsPanel({ api, strings })` — `"use client"`; `api: { list(cursor?: string): Promise<{items: NotificationItem[]; next_cursor: string | null}>; markRead(id: string): Promise<void>; markAllRead(): Promise<void> }`; `NotificationItem = { id: string; body: string; created_at: string; read_at: string | null }`; `strings = { title, empty, markAllRead, markRead, loadMore }`.
  - i18n keys `ui.notifications.{bell,title,empty,markAllRead,markRead,loadMore}` in en/ta/hi.

- [ ] **Step 1: Write the failing test**

```typescript
// packages/ui/src/components/notification-bell.test.ts
import { describe, expect, it } from "vitest";

import { formatUnread } from "./notification-bell";

describe("formatUnread", () => {
  it("hides zero, shows counts, caps at 99+", () => {
    expect(formatUnread(0)).toBe("");
    expect(formatUnread(-3)).toBe("");
    expect(formatUnread(1)).toBe("1");
    expect(formatUnread(99)).toBe("99");
    expect(formatUnread(140)).toBe("99+");
  });
});
```

Run: `pnpm --filter @agri/ui test` → FAIL (module missing).

- [ ] **Step 2: Implement the bell**

```tsx
// packages/ui/src/components/notification-bell.tsx
import type { ButtonHTMLAttributes } from "react";

import { cn } from "../lib/cn";

/** Unread badge text: hidden at 0, capped at 99+. */
export function formatUnread(count: number): string {
  if (count <= 0) return "";
  return count > 99 ? "99+" : String(count);
}

/**
 * Notification bell for HeaderStack's `right` slot (D12). Presentational:
 * data wiring lives in @agri/auth-client (NotificationBellIsland). Emoji
 * glyph per design-system icon convention; `rating` token for the badge
 * (amber - the palette ships no red).
 */
export function NotificationBell({
  unread = 0,
  label,
  className,
  ...props
}: ButtonHTMLAttributes<HTMLButtonElement> & { unread?: number; label: string }) {
  const badge = formatUnread(unread);
  return (
    <button
      type="button"
      aria-label={badge ? `${label} (${badge})` : label}
      className={cn(
        "tap-target relative flex items-center justify-center rounded-pill border border-white/30 bg-glass px-3.5 py-[7px] text-[15px] text-white",
        className,
      )}
      {...props}
    >
      <span aria-hidden="true">🔔</span>
      {badge ? (
        <span
          aria-hidden="true"
          className="absolute -right-1 -top-1 flex h-[18px] min-w-[18px] items-center justify-center rounded-pill bg-rating px-1 text-[11px] font-extrabold text-white"
        >
          {badge}
        </span>
      ) : null}
    </button>
  );
}
```

- [ ] **Step 3: Implement the panel**

```tsx
// packages/ui/src/composites/notifications-panel.tsx
"use client";

/**
 * Notification center list (D12): cursor "load more", per-row + bulk
 * mark-read. Data access is injected so web-id (cookie rewrite) and the
 * public apps (bearer BFF proxy) reuse one component.
 */
import { useCallback, useEffect, useState } from "react";

import { Button } from "../components/button";
import { Card } from "../components/card";
import { EmptyState } from "../components/empty-state";
import { Skeleton } from "../components/skeleton";
import { cn } from "../lib/cn";

export interface NotificationItem {
  id: string;
  body: string;
  created_at: string;
  read_at: string | null;
}

export interface NotificationsApi {
  list: (cursor?: string) => Promise<{ items: NotificationItem[]; next_cursor: string | null }>;
  markRead: (id: string) => Promise<void>;
  markAllRead: () => Promise<void>;
}

export interface NotificationsStrings {
  title: string;
  empty: string;
  markAllRead: string;
  markRead: string;
  loadMore: string;
}

export function NotificationsPanel({
  api,
  strings,
}: {
  api: NotificationsApi;
  strings: NotificationsStrings;
}) {
  const [items, setItems] = useState<NotificationItem[] | null>(null);
  const [cursor, setCursor] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  const load = useCallback(
    async (after?: string) => {
      const page = await api.list(after);
      setItems((prev) => (after && prev ? [...prev, ...page.items] : page.items));
      setCursor(page.next_cursor);
    },
    [api],
  );

  useEffect(() => {
    void load().catch(() => setItems([]));
  }, [load]);

  const markRead = useCallback(
    async (id: string) => {
      await api.markRead(id);
      setItems((prev) =>
        prev
          ? prev.map((n) => (n.id === id ? { ...n, read_at: new Date().toISOString() } : n))
          : prev,
      );
    },
    [api],
  );

  const markAllRead = useCallback(async () => {
    setBusy(true);
    try {
      await api.markAllRead();
      const stamp = new Date().toISOString();
      setItems((prev) => (prev ? prev.map((n) => ({ ...n, read_at: n.read_at ?? stamp })) : prev));
    } finally {
      setBusy(false);
    }
  }, [api]);

  if (items === null) {
    return (
      <div className="grid gap-2" data-testid="notifications-loading">
        <Skeleton className="h-16" />
        <Skeleton className="h-16" />
        <Skeleton className="h-16" />
      </div>
    );
  }
  if (items.length === 0) {
    return <EmptyState icon="🔔" title={strings.title} hint={strings.empty} />;
  }
  return (
    <section aria-label={strings.title}>
      <div className="mb-3 flex items-center justify-between">
        <h2 className="font-display text-[18px] font-extrabold text-ink">{strings.title}</h2>
        <Button variant="ghost" disabled={busy} onClick={() => void markAllRead()}>
          {strings.markAllRead}
        </Button>
      </div>
      <ul className="grid gap-2" data-testid="notification-list">
        {items.map((item) => (
          <li key={item.id}>
            <Card className={cn("flex items-start justify-between gap-3 p-4")}>
              <div>
                <p className={cn("text-[14px]", item.read_at ? "text-sub" : "font-bold text-ink")}>
                  {item.body}
                </p>
                <time className="text-[12px] text-sub" dateTime={item.created_at}>
                  {new Date(item.created_at).toLocaleString()}
                </time>
              </div>
              {item.read_at === null ? (
                <Button variant="ghost" onClick={() => void markRead(item.id)}>
                  {strings.markRead}
                </Button>
              ) : null}
            </Card>
          </li>
        ))}
      </ul>
      {cursor ? (
        <div className="mt-3 flex justify-center">
          <Button variant="ghost" onClick={() => void load(cursor)}>
            {strings.loadMore}
          </Button>
        </div>
      ) : null}
    </section>
  );
}
```

Check `EmptyState`'s and `Button`'s actual prop names before use (`grep -n "export function EmptyState" -A 8 packages/ui/src/components/empty-state.tsx`; adjust `icon/title/hint` and `variant="ghost"` to the real API — Button variants are defined in `packages/ui/src/components/button.tsx`).

- [ ] **Step 4: Exports + i18n + demo**

`packages/ui/src/index.ts` — add:

```typescript
export { NotificationBell, formatUnread } from "./components/notification-bell";
export { NotificationsPanel } from "./composites/notifications-panel";
export type { NotificationItem, NotificationsApi, NotificationsStrings } from "./composites/notifications-panel";
```

`packages/ui/src/i18n/messages/en.json` — under `ui` add:

```json
"notifications": {
  "bell": "Notifications",
  "title": "Notifications",
  "empty": "You're all caught up.",
  "markAllRead": "Mark all read",
  "markRead": "Mark read",
  "loadMore": "Load more"
}
```

`ta.json`:

```json
"notifications": {
  "bell": "அறிவிப்புகள்",
  "title": "அறிவிப்புகள்",
  "empty": "புதிய அறிவிப்புகள் இல்லை.",
  "markAllRead": "அனைத்தையும் படித்ததாகக் குறி",
  "markRead": "படித்ததாகக் குறி",
  "loadMore": "மேலும் காட்டு"
}
```

`hi.json`:

```json
"notifications": {
  "bell": "सूचनाएँ",
  "title": "सूचनाएँ",
  "empty": "कोई नई सूचना नहीं।",
  "markAllRead": "सभी पढ़ी हुई चिह्नित करें",
  "markRead": "पढ़ी हुई चिह्नित करें",
  "loadMore": "और दिखाएँ"
}
```

`apps/web-agri/app/demo/page.tsx` — add a "Notifications (D12)" section next to the ProfileNudge one: `<NotificationBell label={t("notifications.bell")} unread={0} />`, `unread={3}`, `unread={120}` variants on the gradient header band, and a static `NotificationsPanel` with a stub `api` resolving two fixture items (one read, one unread) — follow how the demo stubs other interactive composites.

- [ ] **Step 5: Test, build, hex-check**

Run: `pnpm --filter @agri/ui test && pnpm --filter @agri/ui build 2>/dev/null || pnpm -w build --filter @agri/ui; pnpm check:hex && pnpm --filter web-agri build`
(If `@agri/ui` has no build script — it's consumed via transpilePackages — the web-agri build is the compile gate.)
Expected: vitest PASS, no hex violations, app builds.

- [ ] **Step 6: Commit**

```bash
git add packages/ui apps/web-agri/app/demo
git commit -m "feat(d12): NotificationBell + NotificationsPanel with i18n and demo showcase"
```

---

### Task 13: App wiring — bell island, BFF proxies, /notifications pages

**Files:**
- Create: `packages/auth-client/src/notification-bell-island.tsx` (exported from `packages/auth-client/src/react.tsx` or the package's client entry — match how `AuthCluster` is exported)
- Create: `apps/web-agri/app/api/notify/[...path]/route.ts` (and same for `apps/web-milk`, `apps/web-organic`)
- Create: `apps/web-agri/app/notifications/page.tsx` + `apps/web-agri/app/notifications/notifications-client.tsx` (and same for web-milk, web-organic)
- Modify: `apps/web-agri/app/site-header.tsx`, `apps/web-milk/app/site-header.tsx`, `apps/web-organic/app/site-header.tsx`
- Create: `apps/web-id/app/notifications/page.tsx` + `apps/web-id/app/notifications/notifications-manager.tsx`
- Modify: `apps/web-id/app/layout.tsx` (bell strip)

**Interfaces:**
- Consumes: `NotificationBell`, `NotificationsPanel` (T12), `useAgriUser` (auth-client), backend routes (T11).
- Produces: `NotificationBellIsland({ basePath: string; href: string; label: string })` — fetches `${basePath}/unread-count` once after auth resolves + on window focus; renders nothing while loading/unauthenticated; navigates to `href` on click.

- [ ] **Step 1: Bell island in auth-client**

```tsx
// packages/auth-client/src/notification-bell-island.tsx
"use client";

/** Bell + unread badge wired to the notify BFF path (D12). Fetches once
 * after auth resolves and again on window focus - deliberately no polling
 * (the bell rides every page's header, which sits under the Lighthouse
 * home-page budget). */
import { NotificationBell } from "@agri/ui";
import { useEffect, useState } from "react";

import { useAgriUser } from "./react";

export function NotificationBellIsland({
  basePath,
  href,
  label,
}: {
  basePath: string;
  href: string;
  label: string;
}) {
  const { status } = useAgriUser({ autoSilentSso: false });
  const [unread, setUnread] = useState(0);

  useEffect(() => {
    if (status !== "authenticated") return;
    let cancelled = false;
    const refresh = async () => {
      try {
        const res = await fetch(`${basePath}/unread-count`);
        if (!res.ok || cancelled) return;
        const body = (await res.json()) as { unread: number };
        if (!cancelled) setUnread(body.unread);
      } catch {
        /* badge is best-effort */
      }
    };
    void refresh();
    const onFocus = () => void refresh();
    window.addEventListener("focus", onFocus);
    return () => {
      cancelled = true;
      window.removeEventListener("focus", onFocus);
    };
  }, [status, basePath]);

  if (status !== "authenticated") return null;
  return (
    <NotificationBell
      unread={unread}
      label={label}
      onClick={() => window.location.assign(href)}
    />
  );
}
```

Export it beside `AuthCluster` (check `packages/auth-client/package.json` `exports` for the `./react` entry and add the export in the same file/entry). Caveat: `useAgriUser` here runs a second `/api/auth/me` fetch alongside AuthCluster's — acceptable now (both are cheap same-origin BFF hits); if it bothers, note it in the PR as a known follow-up, do NOT build a context provider in this spec.

- [ ] **Step 2: BFF proxy per public app**

`apps/web-agri/app/api/notify/[...path]/route.ts` — copy `apps/web-admin/app/api/admin/[...path]/route.ts` verbatim with two changes: upstream prefix `/notify/` instead of `/admin/`, and export only `GET` and `POST` (notify's browser surface needs no DELETE). Import `auth` from the app's own `@/lib/auth`. Repeat identically for web-milk and web-organic.

- [ ] **Step 3: /notifications page per public app**

`apps/web-agri/app/notifications/notifications-client.tsx`:

```tsx
"use client";

import { NotificationsPanel, type NotificationsApi } from "@agri/ui";
import { useLocale, useTranslations } from "next-intl";
import { useMemo } from "react";

const BASE = "/api/notify";

async function ok(res: Response): Promise<void> {
  if (!res.ok) throw new Error(String(res.status));
}

export function NotificationsClient() {
  const t = useTranslations("ui.notifications");
  const locale = useLocale();
  const api = useMemo<NotificationsApi>(
    () => ({
      list: async (cursor) => {
        const params = new URLSearchParams({ locale });
        if (cursor) params.set("cursor", cursor);
        const res = await fetch(`${BASE}/notifications?${params}`);
        await ok(res);
        return (await res.json()) as Awaited<ReturnType<NotificationsApi["list"]>>;
      },
      markRead: async (id) => ok(await fetch(`${BASE}/notifications/${id}/read`, { method: "POST" })),
      markAllRead: async () => ok(await fetch(`${BASE}/notifications/read-all`, { method: "POST" })),
    }),
    [locale],
  );
  return (
    <NotificationsPanel
      api={api}
      strings={{
        title: t("title"),
        empty: t("empty"),
        markAllRead: t("markAllRead"),
        markRead: t("markRead"),
        loadMore: t("loadMore"),
      }}
    />
  );
}
```

`apps/web-agri/app/notifications/page.tsx`:

```tsx
import type { Metadata } from "next";

import { NotificationsClient } from "./notifications-client";

export const metadata: Metadata = { title: "Notifications", robots: { index: false } };

export default function NotificationsPage() {
  return (
    <main className="mx-auto max-w-[720px] px-4 py-6">
      <NotificationsClient />
    </main>
  );
}
```

Copy both files into web-milk and web-organic unchanged (BASE stays `/api/notify`). Check each app's existing page for the main-wrapper classes convention and match it.

- [ ] **Step 4: Headers**

In each public app's `site-header.tsx`, extend the `right` slot (bell left of the auth cluster) — web-agri shown, milk/organic identical:

```tsx
import { AuthCluster, NotificationBellIsland } from "@agri/auth-client/react";
...
      right={
        <>
          <NotificationBellIsland basePath="/api/notify" href="/notifications" label="Notifications" />
          <AuthCluster />
        </>
      }
```

(`site-header.tsx` is a server component and can't call `useTranslations` for the label without becoming client; pass the plain string "Notifications" only if the file has no translation access — check whether sibling headers already use `getTranslations`; if they do, use `t("ui.notifications.bell")`.)

- [ ] **Step 5: web-id (no shared header)**

`apps/web-id/app/notifications/notifications-manager.tsx` — same as the public apps' client but `const BASE = "/api/id/notify";` and mark-read paths accordingly; web-id has no `useAgriUser` (it IS the IdP), so the page relies on the server-side cookie check. `apps/web-id/app/notifications/page.tsx` — copy the RSC guard pattern from `apps/web-id/app/devices/page.tsx` (read `agri_sid` cookie, `redirect("/login")` when absent) and render the manager. Bell: create `apps/web-id/app/notification-bell.tsx`, a small client component that fetches `/api/id/notify/unread-count` on mount (hide on 401) and renders `<NotificationBell label={t("ui.notifications.bell")} .../>` linking to `/notifications`; mount it in `apps/web-id/app/layout.tsx` inside a slim right-aligned bar above `{children}` (this header strip is new — keep it to one flex row with `bg-header-gradient` and the bell; don't invent more chrome).

- [ ] **Step 6: Verify builds + lint + lighthouse-relevant checks**

Run: `pnpm -w lint && pnpm check:hex && pnpm --filter web-agri build && pnpm --filter web-milk build && pnpm --filter web-organic build && pnpm --filter web-id build`
Expected: all green. (Lighthouse runs in CI; the bell adds no blocking fetch to first paint — `NotificationBellIsland` renders null until auth resolves, matching AuthCluster.)

- [ ] **Step 7: Commit**

```bash
git add packages/auth-client apps/web-agri apps/web-milk apps/web-organic apps/web-id
git commit -m "feat(d12): notification bell + center wired into public apps and web-id"
```

---

### Task 14: Full verification, PR

**Files:** none new (fixes only, if verification finds any).

- [ ] **Step 1: Backend full pass (from backend/core)**

Run: `ruff format --check . && ruff check . && mypy . && lint-imports && python scripts/migrate_check.py && python -m pytest -q`
Expected: everything green, including the D12 suites: audit schema/chain/integrity, notify templates/rendering/drivers/service/consumers/router.

- [ ] **Step 2: Frontend full pass (from repo root)**

Run: `pnpm -w lint && pnpm check:hex && pnpm -r test && pnpm -r build`
Expected: green (matches CI's frontend jobs).

- [ ] **Step 3: Spec DoD checklist**

Confirm each, fixing anything that fails:
- tamper test proves detection (test_audit_integrity: mutate → chain breaks) ✔
- app_rt cannot UPDATE/DELETE audit rows (grant test) ✔
- every send passes preferences; no module imports notify drivers (lint contract) ✔
- all templates in 3 locales or CI fails (test_notify_templates) ✔
- bell live in web-agri/milk/organic/web-id ✔
- `backend/core/public_routes.txt` unchanged ✔

- [ ] **Step 4: Push and open PR to dev**

```bash
git push -u origin feat/d12-audit-notify
gh pr create --base dev --title "feat(d12): audit + notify" --body "$(cat <<'EOF'
## D12 — Audit log + Notify module

**Audit (schema `audit`, shared/audit.py):** append-only entries with per-UTC-day hash
chains (advisory-lock serialized, no UPDATE grants anywhere); `verify_chain()` +
`scripts/verify_audit_chain.py`; tamper + grant-enforcement tests. New NOSUPERUSER
runtime role `app_rt` (INSERT+SELECT only on audit) — runtime DATABASE_URL switched in
dev/CI/tests; alembic stays on `app`. Wired call-site-for-call-site into role
changes, suspensions, OTP-abuse flags, and handle changes.

**Notify (schema `notify`):** templates (en/ta/hi, CI completeness gate),
notifications, deliveries (retry w/ exponential backoff → dead-letter), per-user
channel preferences (in-app always on). Modules publish events
(`identity.signup_completed` / `login_new_device` / `role_changed`, `notify.announce`);
a lifespan worker consumes and dispatches through rate cap (30/user/h) → preferences →
flag → drivers. Drivers: mock SMS/email + ZeptoMail (flag `notify.email_enabled`,
mock in dev); import-linter contract forbids driver access outside notify.
Injection-safe `{var}` rendering (no format-spec traversal; HTML-escaped email).

**UI:** `NotificationBell` + `NotificationsPanel` in @agri/ui (demo'd on /demo),
bell island in auth-client (fetch-on-auth + focus, no polling), `/api/notify` BFF
proxies + `/notifications` pages in web-agri/milk/organic, cookie-rewrite wiring +
bell strip in web-id. i18n keys in en/ta/hi.

**Assumptions confirmed by owner:** logical day-chains (no physical partitioning);
ZeptoMail API as email provider; app_rt runtime role; in-process lifespan worker.

Design: docs/superpowers/specs/2026-07-12-d12-audit-notify-design.md
Plan: docs/superpowers/plans/2026-07-12-d12-audit-notify.md

🤖 Generated with [Claude Code](https://claude.com/claude-code)
EOF
)"
```

Expected: PR opens against dev; CI (8 checks) goes green.

---

## Self-Review Notes (already applied)

- Spec coverage: A→Tasks 1-5, B→Tasks 6-10, C→Tasks 12-13, D→Task 6, E→Tasks 4/9/6(completeness)/7; non-negotiables 1-4 → Tasks 4, 1/2/4, 8/9, 6.
- `web-admin` bell: out of scope per spec ("all 3 public apps + web-id").
- Deleting the newest row of a day is invisible to the chain alone; the grant matrix covers the app role, and the residual risk (owner-credential truncation of the tail) is documented in shared/audit.py's docstring — anchoring day-heads externally is future work, not D12.
- `identity.role_changed` event goes in-app only; role/suspend audit trail is the authoritative record.
- The login publish adds one `SessionWeb` lookup per login (indexed by user_id) — negligible.
