# D26 Vendor Dashboard Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Vendor dashboard in the web-agri Business Console: listing/coverage/delivery-window management, schema-driven product forms, extended lead inbox, intent-only premium tier with premium-first covers() sort, profile-view beacon + analytics-lite by pincode.

**Architecture:** All backend work is thin extensions inside `modules/directory` (the only module that can IDOR-check business ownership; import-linter forbids cross-module imports). Frontend extends the D20 console mount contract: one route segment + one `CONSOLE_MODULES` entry per module, layout never edited. Analytics aggregates `leads.inquiries` / new `directory.profile_views` with direct SQL at request time — no rollup tables, no consumers.

**Tech Stack:** FastAPI + SQLAlchemy async + Alembic (backend/core), Next.js App Router + Tailwind tokens + `@agri/ui` (apps/web-agri, apps/web-milk), pytest, Playwright.

**Design doc:** `docs/superpowers/specs/2026-07-24-d26-vendor-dashboard-design.md` (owner-approved).

## Global Constraints

- Branch `feat/d26-vendor-dashboard` off dev; conventional commits; PR targets dev, title `feat(d26): vendor dashboard`. NEVER commit to dev/main.
- No offset paging anywhere (lint gate); IDs are UUIDv7; keyset cursors only.
- All vendor writes owner-scoped via `service.get_owned_business` / `leads_service.get_owned_inquiry`; not-yours == 404 (same body as missing).
- `Business.subscription_tier` is NEVER client-writable. Owner PATCH rejects it; tier-selection writes only `premium_requested_at`; only the role-gated admin route writes `subscription_tier`.
- Design tokens only in UI — no raw hex (`pnpm check:hex` gate). Console copy is hardcoded English (existing console convention; i18n arrives with D27).
- Every new route on a `SecureRouter`; `public=True` requires a `backend/core/public_routes.txt` line in the same commit (CI diffs via `scripts/dump_public_routes.py --check`).
- Never log request bodies/query strings in modules/directory (business-contact PII).
- Backend test runs use `python -m pytest <file> -q` from `backend/core` with the dev venv, and the full gate is `python -m pytest -m "not slow" -q` (storm suites are separate; never run `test_coins_storm` inline).
- Before first push: `ruff format --check .`, `ruff check .`, `mypy .`, `lint-imports` (from `backend/core`), plus root `pnpm typecheck && pnpm lint`.
- Local dev DB runs on port 55432 (docker); tests recreate their own DB per session. If /ops or geo lookups fail after a volume recreate: `alembic upgrade head` + `python scripts/load_geo.py`.
- Frontend fetches go through same-origin BFF proxies; bearer tokens never reach browser JS.
- Lighthouse floors are untouched: console pages are `robots: {index: false}` and not in the audited URL set. Do not touch web-milk `/` or `/[pincode]` render paths except the fire-and-forget beacon (no layout shift, no new blocking JS).

---

## File Structure (created / modified)

Backend (`backend/core/`):
- Create: `alembic/versions/0025_vendor_dashboard.py` — columns + profile_views table + grants.
- Create: `modules/directory/analytics.py` — viewer hash, view recording, analytics aggregation (one file, one purpose: dashboard counters).
- Modify: `modules/directory/models.py` — `Business.premium_requested_at`, `Business.delivery_windows`, new `ProfileView`.
- Modify: `modules/directory/schemas.py` — tier-selection, delivery-window, beacon, analytics DTOs; `BusinessOut.delivery_windows`.
- Modify: `modules/directory/service.py` — `select_tier`, delivery_windows in `MUTABLE_FIELDS`.
- Modify: `modules/directory/covers.py` — tier_rank sort + widened cursor.
- Modify: `modules/directory/router.py` — tier-selection, analytics, view-beacon routes.
- Modify: `modules/directory/admin_router.py` — admin set-tier route.
- Modify: `modules/directory/leads_router.py` — inbox `type` filter.
- Modify: `modules/directory/catalog_router.py` — authed `GET /catalog/verticals/{vertical}/schema`.
- Modify: `settings.py` — `view_beacon_secret`.
- Modify: `public_routes.txt` — `/directory/businesses/{slug}/view`.
- Tests: `tests/test_d26_migration.py`, `tests/test_tier_selection.py`, `tests/test_directory_admin_tier.py`, `tests/test_covers_premium_sort.py` (plus edits to `tests/test_directory_covers.py`), `tests/test_delivery_windows.py`, `tests/test_profile_views.py`, `tests/test_business_analytics.py`, `tests/test_inbox_type_filter.py`, `tests/test_vertical_schema_route.py`.

Frontend:
- Modify: `apps/web-agri/lib/api.ts` — add `putJson`, `patchJson`, `deleteJson`.
- Modify: `apps/web-agri/app/api/directory/[...path]/route.ts` — add PATCH + PUT forwarding.
- Create: `apps/web-agri/app/api/catalog/[...path]/route.ts` — allowlisted proxy.
- Create: `apps/web-agri/app/api/view/route.ts`, `apps/web-milk/app/api/view/route.ts` — guest view-beacon relays.
- Replace stub: `apps/web-agri/app/business/listings/page.tsx` + create `listings-client.tsx`.
- Replace stub: `apps/web-agri/app/business/products/page.tsx` + create `products-client.tsx`.
- Modify: `apps/web-agri/app/business/inbox/inbox-client.tsx` — type filter, need payload fields, slow-responder nudge.
- Create: `apps/web-agri/app/business/analytics/page.tsx` + `analytics-client.tsx`.
- Create: `apps/web-agri/app/business/premium/page.tsx` + `premium-client.tsx`.
- Modify: `apps/web-agri/lib/console-modules.ts` — `analytics` + `premium` entries.
- Create: `apps/web-agri/app/directory/businesses/[slug]/view-beacon.tsx`; Create: `apps/web-milk/app/directory/businesses/[slug]/view-beacon.tsx`; mount each in its page.
- E2E: `e2e/vendor-dashboard.spec.ts`.

Docs:
- Create: `docs/runbooks/billing-flag-flip.md` (PRE-FLAG-FLIP checklist incl. new tier-sync line).
- Regenerate module docs: edit `backend/core/scripts/gen_module_claude.py` (directory blurb) and rerun it.

---

### Task 1: Migration 0025 + ORM columns + ProfileView model

**Files:**
- Create: `backend/core/alembic/versions/0025_vendor_dashboard.py`
- Modify: `backend/core/modules/directory/models.py`
- Test: `backend/core/tests/test_d26_migration.py`

**Interfaces:**
- Consumes: `shared/migrations.py` `pk_column()`; existing `directory.businesses` table.
- Produces: columns `businesses.premium_requested_at (timestamptz NULL)`, `businesses.delivery_windows (jsonb NULL)`; table `directory.profile_views(id, business_id, pincode, viewer_hash, occurred_at)` with unique `(business_id, viewer_hash)` (name `uq_directory_profile_views_dedupe`) and index `(business_id, occurred_at)`; app_rt grant SELECT+INSERT only (append-only by grant). ORM: `Business.premium_requested_at: datetime | None`, `Business.delivery_windows: list[dict[str, Any]] | None`, class `ProfileView`.

- [ ] **Step 1: Write the failing migration test**

`backend/core/tests/test_d26_migration.py`:

```python
"""D26 schema: tier-intent + delivery-window columns, append-only
profile_views (grant-enforced: app_rt gets SELECT+INSERT only)."""

import pytest
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

pytestmark = pytest.mark.asyncio


async def test_business_columns_added(db_session: AsyncSession) -> None:
    rows = (
        await db_session.execute(
            text(
                "SELECT column_name, is_nullable FROM information_schema.columns "
                "WHERE table_schema = 'directory' AND table_name = 'businesses' "
                "AND column_name IN ('premium_requested_at', 'delivery_windows')"
            )
        )
    ).all()
    found = {row.column_name: row.is_nullable for row in rows}
    assert found == {"premium_requested_at": "YES", "delivery_windows": "YES"}


async def test_profile_views_table_and_dedupe_index(db_session: AsyncSession) -> None:
    columns = {
        row.column_name
        for row in (
            await db_session.execute(
                text(
                    "SELECT column_name FROM information_schema.columns "
                    "WHERE table_schema = 'directory' AND table_name = 'profile_views'"
                )
            )
        ).all()
    }
    assert columns == {"id", "business_id", "pincode", "viewer_hash", "occurred_at"}
    indexes = {
        row.indexname
        for row in (
            await db_session.execute(
                text(
                    "SELECT indexname FROM pg_indexes "
                    "WHERE schemaname = 'directory' AND tablename = 'profile_views'"
                )
            )
        ).all()
    }
    assert "uq_directory_profile_views_dedupe" in indexes


async def test_profile_views_append_only_grant(db_session: AsyncSession) -> None:
    grants = {
        row.privilege_type
        for row in (
            await db_session.execute(
                text(
                    "SELECT privilege_type FROM information_schema.role_table_grants "
                    "WHERE table_schema = 'directory' AND table_name = 'profile_views' "
                    "AND grantee = 'app_rt'"
                )
            )
        ).all()
    }
    assert grants == {"SELECT", "INSERT"}
```

- [ ] **Step 2: Run it to verify failure**

Run (from `backend/core`): `python -m pytest tests/test_d26_migration.py -q`
Expected: FAIL — columns/table missing (empty result sets).

- [ ] **Step 3: Write the migration**

`backend/core/alembic/versions/0025_vendor_dashboard.py`:

```python
# backend/core/alembic/versions/0025_vendor_dashboard.py
"""vendor dashboard v1 (D26): tier intent + delivery windows + profile views.

Revision ID: 0025
Revises: 0024
Create Date: 2026-07-24

"""
# -- THREAT/NOTES:
# - premium_requested_at is INTENT ONLY (owner-writable via tier-selection);
#   subscription_tier stays server-set (admin route / billing at launch) -
#   fake-premium threat model.
# - profile_views is append-only BY GRANT (SELECT+INSERT, no UPDATE/DELETE):
#   a view count must never be editable through the app role.
# - viewer_hash is the ads-style daily-rotating pseudonym; unique
#   (business_id, viewer_hash) IS the 1-view/viewer/business/UTC-day dedupe
#   (the hash rotates daily, so the pair is day-scoped by construction).
# - pincode is nullable: the beacon may fire without browsing context.
# - downgrade drops the view history and both columns.

from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op
from shared.migrations import pk_column

revision: str = "0025"
down_revision: str | None = "0024"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_uuid = postgresql.UUID(as_uuid=True)


def upgrade() -> None:
    op.add_column(
        "businesses",
        sa.Column("premium_requested_at", postgresql.TIMESTAMP(timezone=True), nullable=True),
        schema="directory",
    )
    op.add_column(
        "businesses",
        sa.Column("delivery_windows", postgresql.JSONB, nullable=True),
        schema="directory",
    )

    op.create_table(
        "profile_views",
        pk_column(),
        sa.Column(
            "business_id",
            _uuid,
            sa.ForeignKey("directory.businesses.id"),
            nullable=False,
        ),
        sa.Column("pincode", sa.Text, nullable=True),
        sa.Column("viewer_hash", sa.Text, nullable=False),
        sa.Column("occurred_at", postgresql.TIMESTAMP(timezone=True), nullable=False),
        schema="directory",
    )
    op.create_index(
        "uq_directory_profile_views_dedupe",
        "profile_views",
        ["business_id", "viewer_hash"],
        unique=True,
        schema="directory",
    )
    op.create_index(
        "ix_directory_profile_views_business_occurred",
        "profile_views",
        ["business_id", "occurred_at"],
        schema="directory",
    )
    op.execute("GRANT SELECT, INSERT ON directory.profile_views TO app_rt")


def downgrade() -> None:
    op.drop_table("profile_views", schema="directory")
    op.drop_column("businesses", "delivery_windows", schema="directory")
    op.drop_column("businesses", "premium_requested_at", schema="directory")
```

- [ ] **Step 4: Add the ORM side**

In `backend/core/modules/directory/models.py` — add to the imports (`datetime` and `Any` are already imported at the top of the file), then append to `class Business` after `primary_pincode`:

```python
    # D26: owner-expressed premium intent (activation is server-side only)
    premium_requested_at: Mapped[datetime | None] = mapped_column(
        postgresql.TIMESTAMP(timezone=True), nullable=True
    )
    # D26: list of {"days": [...], "open": "HH:MM", "close": "HH:MM"}
    delivery_windows: Mapped[list[dict[str, Any]] | None] = mapped_column(
        postgresql.JSONB, nullable=True
    )
```

And add the model (after `BusinessCoverage`; import `uuid6` at top: `import uuid6`):

```python
class ProfileView(Base):
    """Append-only (BY GRANT) profile-view log (D26 analytics-lite).

    viewer_hash rotates daily (analytics.viewer_hash), so the UNIQUE
    (business_id, viewer_hash) pair enforces 1 view/viewer/business/UTC-day
    without Redis. No timestamp mixin: occurred_at is the only time that
    matters and rows are never updated."""

    __tablename__ = "profile_views"
    __table_args__ = (
        Index(
            "uq_directory_profile_views_dedupe",
            "business_id",
            "viewer_hash",
            unique=True,
        ),
        Index("ix_directory_profile_views_business_occurred", "business_id", "occurred_at"),
        {"schema": "directory"},
    )

    id: Mapped[uuid.UUID] = mapped_column(
        postgresql.UUID(as_uuid=True), primary_key=True, default=uuid6.uuid7
    )
    business_id: Mapped[uuid.UUID] = mapped_column(
        postgresql.UUID(as_uuid=True), ForeignKey("directory.businesses.id"), nullable=False
    )
    pincode: Mapped[str | None] = mapped_column(Text, nullable=True)
    viewer_hash: Mapped[str] = mapped_column(Text, nullable=False)
    occurred_at: Mapped[datetime] = mapped_column(
        postgresql.TIMESTAMP(timezone=True), nullable=False
    )
```

- [ ] **Step 5: Run the migration test to verify it passes**

Run: `python -m pytest tests/test_d26_migration.py -q`
Expected: 3 passed (the test-session fixture recreates + migrates the DB, picking up 0025).

- [ ] **Step 6: Run the directory migration + model suites for regressions**

Run: `python -m pytest tests/test_directory_migration.py tests/test_directory_covers.py -q`
Expected: PASS.

- [ ] **Step 7: Commit**

```bash
git add backend/core/alembic/versions/0025_vendor_dashboard.py backend/core/modules/directory/models.py backend/core/tests/test_d26_migration.py
git commit -m "feat(d26): migration 0025 - tier intent, delivery windows, profile_views"
```

---

### Task 2: Tier-selection endpoint (intent only)

**Files:**
- Modify: `backend/core/modules/directory/schemas.py`
- Modify: `backend/core/modules/directory/service.py`
- Modify: `backend/core/modules/directory/router.py`
- Test: `backend/core/tests/test_tier_selection.py`

**Interfaces:**
- Consumes: `service.get_owned_business(session, owner_user_id, business_id)` (raises `BusinessNotFoundError`); `_principal_user_id(request)` in router.
- Produces: `PUT /directory/businesses/{business_id}/tier-selection` body `{"tier": "free"|"premium"}` → `TierSelectionOut {subscription_tier: str, premium_requested_at: datetime | None}`. Service: `async def select_tier(session, *, owner_user_id, business_id, tier: str, now: datetime) -> Business`.

- [ ] **Step 1: Create the shared D26 test helper, then write the failing tests**

Five D26 suites need the same authed-ASGI fixture (the `test_contact_reveal.py` idiom). Create it ONCE as `backend/core/tests/d26_helpers.py`; every D26 test file imports it (`from tests.d26_helpers import _as, api  # noqa: F401` — importing the fixture function into the module namespace is how pytest sees it):

```python
"""Shared ASGI fixture for the D26 suites: header-driven principal with
optional roles (x-test-user / x-test-roles), db_session-backed app.
Mirrors tests/test_contact_reveal.py's per-file idiom."""

import uuid
from collections.abc import AsyncIterator

import httpx
import pytest
from fastapi import Request
from sqlalchemy.ext.asyncio import AsyncSession

from main import create_app
from shared.db import get_session
from shared.security import register_principal_resolver


class _Principal:
    def __init__(self, user_id: uuid.UUID, roles: tuple[str, ...]) -> None:
        self.user_id = user_id
        self.roles = roles


def _as(user_id: uuid.UUID, roles: str = "user") -> dict[str, str]:
    return {"x-test-user": str(user_id), "x-test-roles": roles}


@pytest.fixture
async def api(db_session: AsyncSession) -> AsyncIterator[tuple[httpx.AsyncClient, AsyncSession]]:
    app = create_app()

    async def _session_override() -> AsyncIterator[AsyncSession]:
        yield db_session

    async def _resolver(request: Request, session: AsyncSession) -> object | None:
        header = request.headers.get("x-test-user")
        if not header:
            return None
        roles = tuple((request.headers.get("x-test-roles") or "user").split(","))
        return _Principal(uuid.UUID(header), roles)

    app.dependency_overrides[get_session] = _session_override
    register_principal_resolver(_resolver)
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="https://api.test") as client:
        yield client, db_session
```

`backend/core/tests/test_tier_selection.py`:

```python
"""Tier selection (D26): records INTENT only. subscription_tier is never
touched by the owner surface (fake-premium threat model); IDOR contract:
someone else's business == 404."""

import uuid

import httpx
import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from modules.directory import service
from tests.d26_helpers import _as, api  # noqa: F401

pytestmark = pytest.mark.asyncio


async def _business(session: AsyncSession, owner: uuid.UUID) -> uuid.UUID:
    business = await service.create_business(
        session, owner_user_id=owner, name="Tier Dairy", type_="vendor", primary_pincode="641001"
    )
    await session.commit()
    return business.id


async def test_select_premium_records_intent_only(
    api: tuple[httpx.AsyncClient, AsyncSession],
) -> None:
    http, session = api
    owner = uuid.uuid4()
    business_id = await _business(session, owner)
    response = await http.put(
        f"/directory/businesses/{business_id}/tier-selection",
        json={"tier": "premium"},
        headers=_as(owner),
    )
    assert response.status_code == 200
    body = response.json()
    assert body["subscription_tier"] == "free"  # NOT premium - intent only
    assert body["premium_requested_at"] is not None


async def test_select_free_clears_intent(api: tuple[httpx.AsyncClient, AsyncSession]) -> None:
    http, session = api
    owner = uuid.uuid4()
    business_id = await _business(session, owner)
    await http.put(
        f"/directory/businesses/{business_id}/tier-selection",
        json={"tier": "premium"},
        headers=_as(owner),
    )
    response = await http.put(
        f"/directory/businesses/{business_id}/tier-selection",
        json={"tier": "free"},
        headers=_as(owner),
    )
    assert response.status_code == 200
    assert response.json()["premium_requested_at"] is None


async def test_tier_selection_idor_is_404(api: tuple[httpx.AsyncClient, AsyncSession]) -> None:
    http, session = api
    business_id = await _business(session, uuid.uuid4())
    response = await http.put(
        f"/directory/businesses/{business_id}/tier-selection",
        json={"tier": "premium"},
        headers=_as(uuid.uuid4()),  # a different user
    )
    assert response.status_code == 404


async def test_tier_selection_requires_auth(api: tuple[httpx.AsyncClient, AsyncSession]) -> None:
    http, session = api
    business_id = await _business(session, uuid.uuid4())
    response = await http.put(
        f"/directory/businesses/{business_id}/tier-selection", json={"tier": "premium"}
    )
    assert response.status_code == 401


async def test_garbage_tier_is_422(api: tuple[httpx.AsyncClient, AsyncSession]) -> None:
    http, session = api
    owner = uuid.uuid4()
    business_id = await _business(session, owner)
    response = await http.put(
        f"/directory/businesses/{business_id}/tier-selection",
        json={"tier": "platinum"},
        headers=_as(owner),
    )
    assert response.status_code == 422


async def test_patch_cannot_change_subscription_tier(
    api: tuple[httpx.AsyncClient, AsyncSession],
) -> None:
    """Regression pin for the one-way door. Whether Pydantic ignores the
    unknown key (200) or rejects it, the tier must remain free."""
    http, session = api
    owner = uuid.uuid4()
    business_id = await _business(session, owner)
    await http.patch(
        f"/directory/businesses/{business_id}",
        json={"subscription_tier": "premium"},
        headers=_as(owner),
    )
    business = await service.get_owned_business(session, owner, business_id)
    assert business.subscription_tier == "free"
```

- [ ] **Step 2: Run to verify failure**

Run: `python -m pytest tests/test_tier_selection.py -q`
Expected: FAIL — 404/405 on the tier-selection route (route not defined). The two guard tests (garbage tier, PATCH pin) may already pass — that's fine; they're regression pins.

- [ ] **Step 3: Implement**

`schemas.py` — add near the other business schemas:

```python
class TierSelectionIn(BaseModel):
    tier: Literal["free", "premium"]


class TierSelectionOut(BaseModel):
    subscription_tier: str
    premium_requested_at: datetime | None
```

`service.py` — add after `update_business` (import `datetime` from `datetime` at top: `from datetime import datetime`):

```python
async def select_tier(
    session: AsyncSession,
    *,
    owner_user_id: uuid.UUID,
    business_id: uuid.UUID,
    tier: str,
    now: datetime,
) -> Business:
    """Record premium INTENT (D26). Never writes subscription_tier - that
    column stays server-set (admin route / billing at launch): the
    fake-premium threat model's one-way door."""
    business = await get_owned_business(session, owner_user_id, business_id)
    business.premium_requested_at = now if tier == "premium" else None
    await session.flush()
    return business
```

`router.py` — add after `assign_categories` (imports: add `TierSelectionIn`, `TierSelectionOut` to the schemas import; `datetime`/`UTC` are already imported):

```python
@router.put("/businesses/{business_id}/tier-selection")
async def select_tier(
    request: Request, business_id: uuid.UUID, body: TierSelectionIn, session: SessionDep
) -> TierSelectionOut:
    """Premium INTENT while billing is dark (D26): 'activate at launch'.
    subscription_tier is untouched by design - server-set only."""
    try:
        business = await service.select_tier(
            session,
            owner_user_id=_principal_user_id(request),
            business_id=business_id,
            tier=body.tier,
            now=datetime.now(UTC),
        )
    except service.BusinessNotFoundError as exc:
        raise HTTPException(status_code=404, detail="Business not found") from exc
    out = TierSelectionOut(
        subscription_tier=business.subscription_tier,
        premium_requested_at=business.premium_requested_at,
    )
    await session.commit()
    return out
```

- [ ] **Step 4: Run tests to verify pass**

Run: `python -m pytest tests/test_tier_selection.py -q`
Expected: 6 passed.

- [ ] **Step 5: Commit**

```bash
git add backend/core/modules/directory/schemas.py backend/core/modules/directory/service.py backend/core/modules/directory/router.py backend/core/tests/test_tier_selection.py
git commit -m "feat(d26): owner tier-selection records premium intent only"
```

---

### Task 3: Admin set-tier route (role-gated, audited)

**Files:**
- Modify: `backend/core/modules/directory/schemas.py`
- Modify: `backend/core/modules/directory/admin_router.py`
- Test: `backend/core/tests/test_directory_admin_tier.py`

**Interfaces:**
- Consumes: `_require_role(request, STAFF, SUPER_ADMIN)`, `audit(session, ...)` (shared.audit), `search_sync.business_event_payload`, `_publish_best_effort`, `_product_payloads` — all already in `admin_router.py`.
- Produces: `POST /admin/directory/businesses/{business_id}/tier` body `{"tier": "free"|"premium"}` → `BusinessOut`. This is THE only write path for `subscription_tier` (ops activates at launch; tests/seed use it to exercise premium sort). Audit action `directory.tier_set`.

- [ ] **Step 1: Write the failing tests**

`backend/core/tests/test_directory_admin_tier.py` (same api fixture idiom as Task 2, but principal roles configurable):

```python
"""Admin set-tier (D26): the ONLY subscription_tier write path. Role-gated
fail-closed; audited in the same transaction (D12 contract)."""

import uuid

import httpx
import pytest
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from modules.directory import service
from tests.d26_helpers import _as, api  # noqa: F401

pytestmark = pytest.mark.asyncio


async def _business(session: AsyncSession) -> uuid.UUID:
    business = await service.create_business(
        session,
        owner_user_id=uuid.uuid4(),
        name="Tier Target",
        type_="vendor",
        primary_pincode="641001",
    )
    await session.commit()
    return business.id


async def test_non_admin_gets_403(api: tuple[httpx.AsyncClient, AsyncSession]) -> None:
    http, session = api
    business_id = await _business(session)
    response = await http.post(
        f"/admin/directory/businesses/{business_id}/tier",
        json={"tier": "premium"},
        headers=_as(uuid.uuid4(), roles="user"),
    )
    assert response.status_code == 403


async def test_staff_sets_premium_and_audits(
    api: tuple[httpx.AsyncClient, AsyncSession],
) -> None:
    http, session = api
    business_id = await _business(session)
    admin = uuid.uuid4()
    response = await http.post(
        f"/admin/directory/businesses/{business_id}/tier",
        json={"tier": "premium"},
        headers=_as(admin, roles="staff"),
    )
    assert response.status_code == 200
    assert response.json()["subscription_tier"] == "premium"
    audit_row = (
        await session.execute(
            text(
                "SELECT action, actor_user_id FROM audit.entries "
                "WHERE action = 'directory.tier_set' AND target_id = :target"
            ),
            {"target": str(business_id)},
        )
    ).first()
    assert audit_row is not None


async def test_unknown_business_404(api: tuple[httpx.AsyncClient, AsyncSession]) -> None:
    http, _session = api
    response = await http.post(
        f"/admin/directory/businesses/{uuid.uuid4()}/tier",
        json={"tier": "premium"},
        headers=_as(uuid.uuid4(), roles="super_admin"),
    )
    assert response.status_code == 404
```

Before running: check the audit table name used in `shared/audit.py` (`audit.entries` vs `audit.audit_log`) — open `backend/core/shared/audit.py`, use the real table in the SQL above.

- [ ] **Step 2: Run to verify failure**

Run: `python -m pytest tests/test_directory_admin_tier.py -q`
Expected: FAIL (405/404 route missing).

- [ ] **Step 3: Implement**

`schemas.py` — add:

```python
class AdminTierIn(BaseModel):
    tier: Literal["free", "premium"]
```

`admin_router.py` — add route (imports: add `AdminTierIn`, `BusinessOut` to the schemas import, `Business` to the models import, and `from modules.directory.router import _business_out` is NOT allowed — copy the small mapper instead. Add near `_admin_claim_out`):

```python
def _admin_business_out(business: Business) -> BusinessOut:
    return BusinessOut(
        id=business.id,
        name=business.name,
        slug=business.slug,
        type=business.type,
        status=business.status,
        verification_status=business.verification_status,
        subscription_tier=business.subscription_tier,
        claimable=business.owner_user_id is None,
        primary_pincode=business.primary_pincode,
        description=business.description.to_dict() if business.description else None,
        created_at=business.created_at,
    )
```

(Also add `from sqlalchemy import select` and the `Business` model import if missing.)

```python
@admin_router.post("/businesses/{business_id}/tier")
async def set_business_tier(
    request: Request, business_id: uuid.UUID, body: AdminTierIn, session: SessionDep
) -> BusinessOut:
    """THE subscription_tier write path (D26). Owner surfaces only record
    intent; ops flips the real tier here (and billing will, at launch,
    through the flag-flip runbook's sync)."""
    admin_id = _require_role(request, STAFF, SUPER_ADMIN)
    business = await session.scalar(select(Business).where(Business.id == business_id))
    if business is None:
        raise HTTPException(status_code=404, detail="Business not found")
    business.subscription_tier = body.tier
    await session.flush()
    await audit(
        session,
        action="directory.tier_set",
        actor_user_id=admin_id,
        target_type="business",
        target_id=str(business.id),
        metadata={"tier": body.tier},
        ip=request.client.host if request.client else None,
    )
    # tier is snapshot-visible (covers/search carry it): republish
    search_payload = await search_sync.business_event_payload(session, business.id)
    product_payloads = await _product_payloads(session, business.id)
    out = _admin_business_out(business)
    await session.commit()
    await _publish_best_effort("business.updated", search_payload)
    for product_payload in product_payloads:
        await _publish_best_effort("product.updated", product_payload)
    return out
```

- [ ] **Step 4: Run tests**

Run: `python -m pytest tests/test_directory_admin_tier.py tests/test_directory_admin.py -q`
Expected: PASS (new file + no admin regressions).

- [ ] **Step 5: Commit**

```bash
git add backend/core/modules/directory/schemas.py backend/core/modules/directory/admin_router.py backend/core/tests/test_directory_admin_tier.py
git commit -m "feat(d26): role-gated admin set-tier route with audit"
```

### Task 4: covers() premium-first sort + widened cursor

**Files:**
- Modify: `backend/core/modules/directory/covers.py`
- Test: `backend/core/tests/test_covers_premium_sort.py` (new) + update `backend/core/tests/test_directory_covers.py` cursor tests

**Interfaces:**
- Consumes: `Business.subscription_tier` (free|premium).
- Produces: `covers()` ordered by `(tier_rank, distance_m, id)` where premium=0, free=1; cursor format `"{tier_rank}:{distance_m}:{id.hex}"`; `encode_covers_cursor(tier_rank: int, distance_m: int, last_id: uuid.UUID) -> str`; `decode_covers_cursor(cursor) -> tuple[int, int, uuid.UUID]`. Wire shape (`CoversItem`/`CoversItemOut`) unchanged — D23 milk home and D24 lists inherit the ordering with zero frontend change. Old 2-field cursors decode to `InvalidCursorError` (routes 400 `invalid cursor`) — acceptable: cursors are short-lived page tokens.

- [ ] **Step 1: Write the failing tests**

`backend/core/tests/test_covers_premium_sort.py`:

```python
"""Premium-first covers() ordering (D26 NN#2): tier_rank leads the sort and
the keyset, so a premium business beats a nearer free one and pagination
across the tier boundary is gap- and dupe-free."""

import uuid
from decimal import Decimal

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from modules.directory import service
from modules.directory.covers import covers, decode_covers_cursor, encode_covers_cursor
from modules.directory.models import Business
from shared.pagination import InvalidCursorError

pytestmark = pytest.mark.asyncio


async def _covered_business(
    session: AsyncSession,
    name: str,
    *,
    branch_at: tuple[float, float],
    tier: str = "free",
) -> Business:
    owner = uuid.uuid4()
    business = await service.create_business(
        session, owner_user_id=owner, name=name, type_="vendor", primary_pincode="641001"
    )
    await service.set_coverage(
        session, owner_user_id=owner, business_id=business.id, pincodes=["641001"]
    )
    lat, lng = branch_at
    await service.add_branch(
        session,
        owner_user_id=owner,
        business_id=business.id,
        address="1 Main Rd",
        state="Tamil Nadu",
        district="Coimbatore",
        pincode="641001",
        lat=Decimal(str(lat)),
        lng=Decimal(str(lng)),
    )
    if tier == "premium":
        business.subscription_tier = "premium"  # simulates the admin route
        await session.flush()
    return business


async def test_premium_outranks_nearer_free(
    db_session: AsyncSession, tn_geo_sample: None
) -> None:
    await _covered_business(db_session, "NearFree", branch_at=(10.9232, 76.9686))  # ~0 km
    await _covered_business(
        db_session, "FarPremium", branch_at=(11.2832, 76.9686), tier="premium"
    )  # ~40 km
    page = await covers(db_session, pincode="641001")
    assert [i.name for i in page.items] == ["FarPremium", "NearFree"]
    assert page.items[0].subscription_tier == "premium"


async def test_distance_orders_within_a_tier(
    db_session: AsyncSession, tn_geo_sample: None
) -> None:
    await _covered_business(db_session, "PremFar", branch_at=(11.2832, 76.9686), tier="premium")
    await _covered_business(db_session, "PremNear", branch_at=(10.9232, 76.9686), tier="premium")
    await _covered_business(db_session, "FreeNear", branch_at=(10.9232, 76.9686))
    page = await covers(db_session, pincode="641001")
    assert [i.name for i in page.items] == ["PremNear", "PremFar", "FreeNear"]


async def test_keyset_pages_across_tier_boundary(
    db_session: AsyncSession, tn_geo_sample: None
) -> None:
    for index, name in enumerate(["P1", "P2", "P3"]):
        await _covered_business(
            db_session, name, branch_at=(10.9232 + index * 0.02, 76.9686), tier="premium"
        )
    for index, name in enumerate(["F1", "F2", "F3"]):
        await _covered_business(db_session, name, branch_at=(10.9232 + index * 0.02, 76.9686))
    seen: list[str] = []
    cursor: str | None = None
    while True:
        page = await covers(db_session, pincode="641001", cursor=cursor, limit=2)
        seen.extend(i.name for i in page.items)
        if page.next_cursor is None:
            break
        cursor = page.next_cursor
    assert seen == ["P1", "P2", "P3", "F1", "F2", "F3"]  # no gaps, no dupes


async def test_coverage_edit_updates_covers(
    db_session: AsyncSession, tn_geo_sample: None
) -> None:
    """NN#4: the coverage editor's whole-list PUT semantics must be visible
    in covers() immediately - add shows the business, remove hides it."""
    business = await _covered_business(db_session, "Editable", branch_at=(10.9232, 76.9686))
    owner = business.owner_user_id
    assert owner is not None
    page = await covers(db_session, pincode="641001")
    assert [i.name for i in page.items] == ["Editable"]
    # remove 641001 (full-replace with a different pincode)
    await service.set_coverage(
        db_session, owner_user_id=owner, business_id=business.id, pincodes=["641002"]
    )
    page = await covers(db_session, pincode="641001")
    assert page.items == []
    # re-add it
    await service.set_coverage(
        db_session, owner_user_id=owner, business_id=business.id,
        pincodes=["641001", "641002"],
    )
    page = await covers(db_session, pincode="641001")
    assert [i.name for i in page.items] == ["Editable"]


async def test_old_two_field_cursor_is_invalid(
    db_session: AsyncSession, tn_geo_sample: None
) -> None:
    import base64

    stale = base64.urlsafe_b64encode(f"12345:{uuid.uuid4().hex}".encode()).decode().rstrip("=")
    with pytest.raises(InvalidCursorError):
        await covers(db_session, pincode="641001", cursor=stale)


def test_cursor_roundtrip() -> None:
    last_id = uuid.uuid4()
    assert decode_covers_cursor(encode_covers_cursor(0, 987, last_id)) == (0, 987, last_id)
```

- [ ] **Step 2: Run to verify failure**

Run: `python -m pytest tests/test_covers_premium_sort.py -q`
Expected: FAIL — encode takes 2 args; premium ordering asserts fail.

- [ ] **Step 3: Implement in `covers.py`**

Replace the cursor helpers:

```python
def encode_covers_cursor(tier_rank: int, distance_m: int, last_id: uuid.UUID) -> str:
    raw = f"{tier_rank}:{distance_m}:{last_id.hex}".encode()
    return base64.urlsafe_b64encode(raw).decode().rstrip("=")


def decode_covers_cursor(cursor: str) -> tuple[int, int, uuid.UUID]:
    try:
        padded = cursor + "=" * (-len(cursor) % 4)
        parts = base64.urlsafe_b64decode(padded).decode().split(":")
        if len(parts) != 3:  # pre-D26 2-field cursors land here too
            raise ValueError(f"expected 3 fields, got {len(parts)}")
        return int(parts[0]), int(parts[1]), uuid.UUID(hex=parts[2])
    except (ValueError, TypeError) as exc:
        raise InvalidCursorError(f"malformed cursor: {cursor!r}") from exc
```

Add the tier-rank expression and use it in the select list, predicate, and order (premium sorts first as rank 0):

```python
_TIER_RANK = "CASE WHEN b.subscription_tier = 'premium' THEN 0 ELSE 1 END"
```

In `_BASE_SQL`, extend the select list: `SELECT b.id, ..., d.distance_m, nb.lat, nb.lng, {_TIER_RANK} AS tier_rank` (f-string interpolation like `{_BRANCH_DISTANCE}`).

Replace `_CURSOR_PREDICATE` (strict lexicographic step over the triple):

```python
_CURSOR_PREDICATE = f"""
  AND ({_TIER_RANK} > :cursor_tier
       OR ({_TIER_RANK} = :cursor_tier AND d.distance_m > :cursor_distance)
       OR ({_TIER_RANK} = :cursor_tier AND d.distance_m = :cursor_distance
           AND b.id > :cursor_id))
"""
```

Replace `_ORDER_LIMIT`:

```python
_ORDER_LIMIT = "\nORDER BY tier_rank, d.distance_m, b.id\nLIMIT :lim"
```

In `covers()`, update the cursor branch and next_cursor:

```python
    if cursor is not None:
        cursor_tier, cursor_distance, cursor_id = decode_covers_cursor(cursor)
        sql += _CURSOR_PREDICATE
        params |= {
            "cursor_tier": cursor_tier,
            "cursor_distance": cursor_distance,
            "cursor_id": cursor_id,
        }
```

```python
    next_cursor = (
        encode_covers_cursor(
            0 if items[-1].subscription_tier == "premium" else 1,
            items[-1].distance_m,
            items[-1].id,
        )
        if len(rows) > limit
        else None
    )
```

Update the module docstring's cursor description to `(tier_rank, distance_m, last_id)`.

- [ ] **Step 4: Fix the existing cursor tests**

In `backend/core/tests/test_directory_covers.py`, any direct `encode_covers_cursor(distance, id)` / `decode_covers_cursor(...)` usages need the third field (tier_rank first). Search the file for `covers_cursor` and update call shapes; ordering tests are tier-free (all free tier) and must still pass unchanged.

- [ ] **Step 5: Run the covers suites**

Run: `python -m pytest tests/test_covers_premium_sort.py tests/test_directory_covers.py tests/test_milk_home.py -q`
(If `tests/test_milk_home.py` doesn't exist under that name, run `python -m pytest -q -k "milk_home or covers"`.)
Expected: PASS — milk-home blend rides covers() and must not break.

- [ ] **Step 6: Commit**

```bash
git add backend/core/modules/directory/covers.py backend/core/tests/test_covers_premium_sort.py backend/core/tests/test_directory_covers.py
git commit -m "feat(d26): premium-first covers() ordering with widened keyset cursor"
```

---

### Task 5: Delivery windows (validated, owner-editable, public)

**Files:**
- Modify: `backend/core/modules/directory/schemas.py`
- Modify: `backend/core/modules/directory/service.py`
- Modify: `backend/core/modules/directory/router.py` (only if `_business_out` needs the new field — it does)
- Test: `backend/core/tests/test_delivery_windows.py`

**Interfaces:**
- Consumes: `update_business` PATCH path, `BusinessOut` mapper `_business_out`.
- Produces: `BusinessPatchIn.delivery_windows: list[DeliveryWindowIn] | None`; `BusinessOut.delivery_windows: list[dict] | None` (public via `/directory/businesses/{slug}` because `BusinessDetailOut.business` is a `BusinessOut`). Validation lives in Pydantic (`DeliveryWindowIn`): known days, HH:MM, open < close, max 7 windows.

- [ ] **Step 1: Write the failing tests**

`backend/core/tests/test_delivery_windows.py`:

```python
"""Delivery windows (D26.A): owner-editable via PATCH, validated shape,
served on the public business detail."""

import uuid

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from modules.directory import service
from tests.d26_helpers import _as, api  # noqa: F401

pytestmark = pytest.mark.asyncio


async def _business(session: AsyncSession, owner: uuid.UUID) -> uuid.UUID:
    business = await service.create_business(
        session, owner_user_id=owner, name="Window Dairy", type_="vendor",
        primary_pincode="641001",
    )
    await session.commit()
    return business.id


WINDOW = {"days": ["mon", "tue", "wed"], "open": "06:00", "close": "09:30"}


async def test_patch_sets_delivery_windows(api) -> None:
    http, session = api
    owner = uuid.uuid4()
    business_id = await _business(session, owner)
    response = await http.patch(
        f"/directory/businesses/{business_id}",
        json={"delivery_windows": [WINDOW]},
        headers=_as(owner),
    )
    assert response.status_code == 200
    assert response.json()["delivery_windows"] == [WINDOW]


async def test_public_detail_serves_windows(api) -> None:
    http, session = api
    owner = uuid.uuid4()
    business_id = await _business(session, owner)
    await http.patch(
        f"/directory/businesses/{business_id}",
        json={"delivery_windows": [WINDOW]},
        headers=_as(owner),
    )
    business = await service.get_owned_business(session, owner, business_id)
    detail = await http.get(f"/directory/businesses/{business.slug}")
    assert detail.status_code == 200
    assert detail.json()["business"]["delivery_windows"] == [WINDOW]


@pytest.mark.parametrize(
    "bad",
    [
        {"days": ["funday"], "open": "06:00", "close": "09:00"},   # unknown day
        {"days": ["mon"], "open": "25:00", "close": "26:00"},      # bad time
        {"days": ["mon"], "open": "09:00", "close": "06:00"},      # open >= close
        {"days": ["mon"], "open": "09:00", "close": "09:00"},      # zero-length
        {"days": [], "open": "06:00", "close": "09:00"},           # no days
    ],
)
async def test_invalid_windows_rejected(api, bad: dict) -> None:
    http, session = api
    owner = uuid.uuid4()
    business_id = await _business(session, owner)
    response = await http.patch(
        f"/directory/businesses/{business_id}",
        json={"delivery_windows": [bad]},
        headers=_as(owner),
    )
    assert response.status_code == 422


async def test_more_than_seven_windows_rejected(api) -> None:
    http, session = api
    owner = uuid.uuid4()
    business_id = await _business(session, owner)
    response = await http.patch(
        f"/directory/businesses/{business_id}",
        json={"delivery_windows": [WINDOW] * 8},
        headers=_as(owner),
    )
    assert response.status_code == 422
```

Mypy note (applies to every D26 test file): where the snippets show bare `api` parameters, annotate them as `api: tuple[httpx.AsyncClient, AsyncSession]` (adding the `httpx` import) — the backend mypy gate covers tests.

- [ ] **Step 2: Run to verify failure**

Run: `python -m pytest tests/test_delivery_windows.py -q`
Expected: FAIL — 400 `immutable or unknown fields` / missing response field.

- [ ] **Step 3: Implement**

`schemas.py`:

```python
Weekday = Literal["mon", "tue", "wed", "thu", "fri", "sat", "sun"]
TIME_PATTERN = r"^([01]\d|2[0-3]):[0-5]\d$"


class DeliveryWindowIn(BaseModel):
    days: list[Weekday] = Field(min_length=1, max_length=7)
    open: str = Field(pattern=TIME_PATTERN)
    close: str = Field(pattern=TIME_PATTERN)

    @model_validator(mode="after")
    def _open_before_close(self) -> "DeliveryWindowIn":
        if self.open >= self.close:  # HH:MM strings compare lexicographically
            raise ValueError("open must be before close (overnight windows unsupported)")
        return self
```

(Add `model_validator` to the pydantic import.) Extend `BusinessPatchIn`:

```python
    delivery_windows: list[DeliveryWindowIn] | None = Field(default=None, max_length=7)
```

Extend `BusinessOut`:

```python
    delivery_windows: list[dict[str, Any]] | None
```

`service.py` — one-line change plus dump handling:

```python
MUTABLE_FIELDS = {"name", "type", "primary_pincode", "description", "delivery_windows"}
```

In `router.py` `update_business`, `body.model_dump(exclude_unset=True)` already turns `DeliveryWindowIn` models into plain dicts — no service change needed beyond the field allowlist. In `_business_out` add:

```python
        delivery_windows=business.delivery_windows,
```

- [ ] **Step 4: Run tests + full directory suite**

Run: `python -m pytest tests/test_delivery_windows.py tests/test_directory_branches.py tests/test_tier_selection.py -q`
Expected: PASS. Note: adding a required field to `BusinessOut` touches every `BusinessOut(...)` construction — grep `BusinessOut(` across `modules/` and fix any other constructor (e.g. admin `_admin_business_out` from Task 3) in the same commit.

- [ ] **Step 5: Commit**

```bash
git add backend/core/modules/directory/schemas.py backend/core/modules/directory/service.py backend/core/modules/directory/router.py backend/core/modules/directory/admin_router.py backend/core/tests/test_delivery_windows.py
git commit -m "feat(d26): validated owner-editable delivery windows"
```

---

### Task 6: Profile-view beacon (public, deduped, append-only)

**Files:**
- Create: `backend/core/modules/directory/analytics.py`
- Modify: `backend/core/settings.py`, `backend/core/modules/directory/schemas.py`, `backend/core/modules/directory/router.py`, `backend/core/public_routes.txt`
- Test: `backend/core/tests/test_profile_views.py`

**Interfaces:**
- Consumes: `ProfileView` model (Task 1), `get_settings()`.
- Produces: `POST /directory/businesses/{slug}/view` (public) body `{"pincode": "641001"?}` → `{"status": "ok"}` (200; mirrors the ads beacon shape). `analytics.viewer_hash(ip, user_agent, *, now) -> str` (daily-rotating); `analytics.record_view(session, *, business_id, pincode, viewer_hash, now) -> None` (INSERT .. ON CONFLICT DO NOTHING on `uq_directory_profile_views_dedupe`). Setting `view_beacon_secret`.

- [ ] **Step 1: Write the failing tests**

`backend/core/tests/test_profile_views.py` (api fixture from Task 2; the beacon route needs NO auth):

```python
"""Profile-view beacon (D26.D): public, no PII (daily-rotating viewer hash),
DB-deduped 1/viewer/business/day, append-only storage."""

import uuid

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from modules.directory import service
from modules.directory.models import ProfileView
from tests.d26_helpers import _as, api  # noqa: F401

pytestmark = pytest.mark.asyncio


async def _active_business(session: AsyncSession) -> tuple[uuid.UUID, str]:
    business = await service.create_business(
        session, owner_user_id=uuid.uuid4(), name="Viewed Dairy", type_="vendor",
        primary_pincode="641001",
    )
    await session.commit()
    return business.id, business.slug


async def test_beacon_records_view_without_auth(api) -> None:
    http, session = api
    business_id, slug = await _active_business(session)
    response = await http.post(f"/directory/businesses/{slug}/view", json={"pincode": "641001"})
    assert response.status_code == 200
    rows = (await session.scalars(select(ProfileView))).all()
    assert len(rows) == 1
    assert rows[0].business_id == business_id
    assert rows[0].pincode == "641001"
    assert rows[0].viewer_hash  # never empty


async def test_same_viewer_same_day_dedupes(api) -> None:
    http, session = api
    _business_id, slug = await _active_business(session)
    for _ in range(3):
        response = await http.post(f"/directory/businesses/{slug}/view", json={})
        assert response.status_code == 200  # dedupe is silent, never an error
    rows = (await session.scalars(select(ProfileView))).all()
    assert len(rows) == 1  # same transport => same ip+ua => same daily hash


async def test_unknown_slug_404(api) -> None:
    http, _session = api
    response = await http.post("/directory/businesses/no-such-biz/view", json={})
    assert response.status_code == 404


async def test_bad_pincode_422(api) -> None:
    http, session = api
    _business_id, slug = await _active_business(session)
    response = await http.post(f"/directory/businesses/{slug}/view", json={"pincode": "64100"})
    assert response.status_code == 422


async def test_viewer_hash_rotates_daily() -> None:
    from datetime import UTC, datetime
    from modules.directory import analytics

    day1 = analytics.viewer_hash("1.2.3.4", "UA", now=datetime(2026, 7, 24, tzinfo=UTC))
    day2 = analytics.viewer_hash("1.2.3.4", "UA", now=datetime(2026, 7, 25, tzinfo=UTC))
    assert day1 != day2  # unlinkable across days (DPDP-minimal)
```

- [ ] **Step 2: Run to verify failure**

Run: `python -m pytest tests/test_profile_views.py -q`
Expected: FAIL (no module `analytics`, no route).

- [ ] **Step 3: Implement**

`settings.py` — next to `contact_reveal_daily_cap` add:

```python
    # Profile-view beacon (D26 analytics-lite). The secret salts the ads-style
    # daily-rotating viewer pseudonym; dedupe is the DB unique index, so a
    # missing Redis costs nothing here.
    view_beacon_secret: str = "dev-view-beacon-secret"
```

`modules/directory/analytics.py` (new):

```python
"""Analytics-lite (D26.D): profile-view recording + dashboard aggregates.

Views are DPDP-minimal by construction: the beacon stores a daily-rotating
viewer pseudonym (ads-module precedent), never IP/UA, and the table is
append-only by grant. Dedupe (1 view/viewer/business/UTC-day) is the DB
unique index - the hash itself rotates daily, so (business_id, viewer_hash)
is day-scoped without any Redis state."""

import hashlib
import uuid
from datetime import datetime

from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession

from modules.directory.models import ProfileView
from settings import get_settings


def viewer_hash(ip: str, user_agent: str, *, now: datetime) -> str:
    secret = get_settings().view_beacon_secret
    raw = f"{secret}:{now:%Y%m%d}:{ip}:{user_agent}"
    return hashlib.sha256(raw.encode()).hexdigest()


async def record_view(
    session: AsyncSession,
    *,
    business_id: uuid.UUID,
    pincode: str | None,
    viewer_hash_value: str,
    now: datetime,
) -> None:
    await session.execute(
        pg_insert(ProfileView)
        .values(
            business_id=business_id,
            pincode=pincode,
            viewer_hash=viewer_hash_value,
            occurred_at=now,
        )
        .on_conflict_do_nothing(index_elements=["business_id", "viewer_hash"])
    )
```

`schemas.py`:

```python
class ViewBeaconIn(BaseModel):
    pincode: str | None = Field(default=None, pattern=PINCODE_PATTERN)


class ViewBeaconOut(BaseModel):
    status: str
```

`router.py` — add near the public reads (import `analytics` alongside the other module imports and the two new schemas):

```python
@router.post("/businesses/{slug}/view", public=True)
async def record_profile_view(
    request: Request, slug: str, body: ViewBeaconIn, session: SessionDep
) -> ViewBeaconOut:
    """Fire-and-forget view beacon (D26.D). Public: guests are most views.
    Stores a daily-rotating pseudonym only; the unique index makes repeats
    a no-op. Rate limiting comes from SecureRouter defaults."""
    business_id = await session.scalar(
        select(Business.id).where(Business.slug == slug, Business.status == "active")
    )
    if business_id is None:
        raise HTTPException(status_code=404, detail="Business not found")
    now = datetime.now(UTC)
    ip = request.client.host if request.client else ""
    hashed = analytics.viewer_hash(ip, request.headers.get("user-agent", ""), now=now)
    await analytics.record_view(
        session, business_id=business_id, pincode=body.pincode, viewer_hash_value=hashed, now=now
    )
    await session.commit()
    return ViewBeaconOut(status="ok")
```

`public_routes.txt` — append (with the comment):

```
# /directory/businesses/{slug}/view: profile-view beacon (D26 analytics) -
# anonymous visitors are most views. Stores daily-rotating pseudonym only
# (no IP/UA), DB-unique dedupe, append-only table, rate-limited.
/directory/businesses/{slug}/view
```

- [ ] **Step 4: Run tests + the public-routes check**

Run: `python -m pytest tests/test_profile_views.py -q && python scripts/dump_public_routes.py --check`
Expected: tests pass; route registry check green.

- [ ] **Step 5: Commit**

```bash
git add backend/core/modules/directory/analytics.py backend/core/settings.py backend/core/modules/directory/schemas.py backend/core/modules/directory/router.py backend/core/public_routes.txt backend/core/tests/test_profile_views.py
git commit -m "feat(d26): public deduped profile-view beacon"
```

---

### Task 7: Owner analytics endpoint (views/reveals/leads by pincode + response stats)

**Files:**
- Modify: `backend/core/modules/directory/analytics.py`, `backend/core/modules/directory/schemas.py`, `backend/core/modules/directory/router.py`
- Test: `backend/core/tests/test_business_analytics.py`

**Interfaces:**
- Consumes: `directory.profile_views`, `leads.inquiries` (`payload->>'source' = 'contact_reveal'` marks reveal-attribution rows), `leads.responses`; `get_owned_business` for IDOR.
- Produces: `GET /directory/businesses/{business_id}/analytics?days=30` (days ∈ {7,30,90}) → `BusinessAnalyticsOut {days, views: {total, by_pincode: [{pincode, count}]}, reveals: {...}, leads: {...}, response: {total, responded, avg_response_seconds}}`. `analytics.business_analytics(session, *, business_id, since) -> AnalyticsData` (dataclass mirroring the DTO). By-pincode lists: top 20 by count desc then pincode asc; NULL pincode groups as `"unknown"`.

- [ ] **Step 1: Write the failing tests**

`backend/core/tests/test_business_analytics.py` (api fixture from Task 2):

```python
"""Owner analytics (D26.D): correct source split (views / reveal-attribution
/ real leads), pincode grouping, day windowing, owner-only access."""

import uuid
from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from modules.directory import service
from modules.directory.leads_models import Inquiry, InquiryResponse
from modules.directory.models import ProfileView
from tests.d26_helpers import _as, api  # noqa: F401

pytestmark = pytest.mark.asyncio


async def _business(session: AsyncSession, owner: uuid.UUID) -> uuid.UUID:
    business = await service.create_business(
        session, owner_user_id=owner, name="Stats Dairy", type_="vendor",
        primary_pincode="641001",
    )
    await session.commit()
    return business.id


def _view(business_id: uuid.UUID, pincode: str | None, days_ago: int, tag: str) -> ProfileView:
    return ProfileView(
        business_id=business_id,
        pincode=pincode,
        viewer_hash=f"hash-{tag}",
        occurred_at=datetime.now(UTC) - timedelta(days=days_ago),
    )


async def test_analytics_splits_sources_and_groups_by_pincode(api) -> None:
    http, session = api
    owner = uuid.uuid4()
    business_id = await _business(session, owner)
    session.add_all(
        [
            _view(business_id, "641001", 1, "a"),
            _view(business_id, "641001", 2, "b"),
            _view(business_id, None, 1, "c"),
            _view(business_id, "641001", 60, "old"),  # outside 30d window
        ]
    )
    session.add(  # reveal-attribution inquiry (counts as reveal, NOT lead)
        Inquiry(
            type="contact", from_user_id=uuid.uuid4(), business_id=business_id,
            payload={"message": "x", "source": "contact_reveal"}, pincode="641001",
        )
    )
    session.add(  # a real lead
        Inquiry(
            type="milk_subscription", from_user_id=uuid.uuid4(), business_id=business_id,
            payload={"qty_liters": 2, "milk_type": "cow", "schedule": "daily"},
            pincode="641002",
        )
    )
    await session.commit()
    response = await http.get(
        f"/directory/businesses/{business_id}/analytics?days=30", headers=_as(owner)
    )
    assert response.status_code == 200
    body = response.json()
    assert body["days"] == 30
    assert body["views"]["total"] == 3
    assert body["views"]["by_pincode"] == [
        {"pincode": "641001", "count": 2},
        {"pincode": "unknown", "count": 1},
    ]
    assert body["reveals"]["total"] == 1
    assert body["reveals"]["by_pincode"] == [{"pincode": "641001", "count": 1}]
    assert body["leads"]["total"] == 1
    assert body["leads"]["by_pincode"] == [{"pincode": "641002", "count": 1}]
    assert body["response"]["total"] == 2  # reveal-attribution rows sit in the inbox too


async def test_response_time_stat_is_accurate(api) -> None:
    """NN#3: exact avg over seeded deltas (600s and 1200s -> 900s)."""
    http, session = api
    owner = uuid.uuid4()
    business_id = await _business(session, owner)
    base = datetime.now(UTC) - timedelta(days=1)
    for offset_s in (600, 1200):
        inquiry = Inquiry(
            type="contact", from_user_id=uuid.uuid4(), business_id=business_id,
            payload={"message": "hello"}, pincode="641001", status="responded",
        )
        session.add(inquiry)
        await session.flush()
        # pin created_at explicitly so the delta is exact
        inquiry.created_at = base
        session.add(
            InquiryResponse(
                inquiry_id=inquiry.id, business_user_id=owner, body="reply",
            )
        )
        await session.flush()
        response_row = (
            await session.scalars(
                select(InquiryResponse).where(InquiryResponse.inquiry_id == inquiry.id)
            )
        ).one()
        response_row.created_at = base + timedelta(seconds=offset_s)
    await session.commit()
    result = await http.get(
        f"/directory/businesses/{business_id}/analytics?days=7", headers=_as(owner)
    )
    assert result.status_code == 200
    assert result.json()["response"]["avg_response_seconds"] == 900


async def test_analytics_idor_is_404(api) -> None:
    http, session = api
    business_id = await _business(session, uuid.uuid4())
    response = await http.get(
        f"/directory/businesses/{business_id}/analytics", headers=_as(uuid.uuid4())
    )
    assert response.status_code == 404


async def test_bad_days_rejected(api) -> None:
    http, session = api
    owner = uuid.uuid4()
    business_id = await _business(session, owner)
    response = await http.get(
        f"/directory/businesses/{business_id}/analytics?days=14", headers=_as(owner)
    )
    assert response.status_code == 422
```

(If `created_at` is server-defaulted and refuses ORM assignment, set it with a raw `UPDATE` via `session.execute(text(...))` — the invariant is the exact 900s average, not the mechanism.)

- [ ] **Step 2: Run to verify failure**

Run: `python -m pytest tests/test_business_analytics.py -q`
Expected: FAIL (404 route missing).

- [ ] **Step 3: Implement**

Append to `modules/directory/analytics.py`:

```python
from dataclasses import dataclass

from sqlalchemy import text

_BY_PINCODE_LIMIT = 20

_VIEWS_SQL = text(
    """
    SELECT COALESCE(pincode, 'unknown') AS pincode, count(*) AS count
    FROM directory.profile_views
    WHERE business_id = :business_id AND occurred_at >= :since
    GROUP BY 1 ORDER BY count DESC, pincode ASC LIMIT :lim
    """
)
_VIEWS_TOTAL_SQL = text(
    """
    SELECT count(*) FROM directory.profile_views
    WHERE business_id = :business_id AND occurred_at >= :since
    """
)
# reveal-attribution rows are inquiries with payload.source == 'contact_reveal'
# (leads_service.record_reveal_inquiry); everything else in the inbox is a
# real lead (direct contact + need fan-out children alike).
_INQUIRY_SQL = text(
    """
    SELECT COALESCE(pincode, 'unknown') AS pincode, count(*) AS count
    FROM leads.inquiries
    WHERE business_id = :business_id AND created_at >= :since
      AND (payload->>'source' IS NOT DISTINCT FROM 'contact_reveal') = :is_reveal
    GROUP BY 1 ORDER BY count DESC, pincode ASC LIMIT :lim
    """
)
_INQUIRY_TOTAL_SQL = text(
    """
    SELECT count(*) FROM leads.inquiries
    WHERE business_id = :business_id AND created_at >= :since
      AND (payload->>'source' IS NOT DISTINCT FROM 'contact_reveal') = :is_reveal
    """
)
_RESPONSE_SQL = text(
    """
    SELECT
        count(*) AS total,
        count(*) FILTER (WHERE i.status <> 'new') AS responded,
        CAST(avg(EXTRACT(EPOCH FROM fr.first_at - i.created_at)) AS BIGINT)
            AS avg_response_seconds
    FROM leads.inquiries i
    LEFT JOIN LATERAL (
        SELECT min(r.created_at) AS first_at
        FROM leads.responses r WHERE r.inquiry_id = i.id
    ) fr ON true
    WHERE i.business_id = :business_id AND i.created_at >= :since
    """
)


@dataclass(frozen=True, slots=True)
class PincodeCount:
    pincode: str
    count: int


@dataclass(frozen=True, slots=True)
class Section:
    total: int
    by_pincode: list[PincodeCount]


@dataclass(frozen=True, slots=True)
class ResponseStats:
    total: int
    responded: int
    avg_response_seconds: int | None


@dataclass(frozen=True, slots=True)
class AnalyticsData:
    views: Section
    reveals: Section
    leads: Section
    response: ResponseStats


async def _section(
    session: AsyncSession, total_sql, by_sql, params: dict[str, object]
) -> Section:
    total = int(await session.scalar(total_sql, params) or 0)
    rows = (await session.execute(by_sql, {**params, "lim": _BY_PINCODE_LIMIT})).all()
    return Section(
        total=total,
        by_pincode=[
            PincodeCount(pincode=m["pincode"], count=int(m["count"]))
            for m in (row._mapping for row in rows)
        ],
    )


async def business_analytics(
    session: AsyncSession, *, business_id: uuid.UUID, since: datetime
) -> AnalyticsData:
    base = {"business_id": business_id, "since": since}
    views = await _section(session, _VIEWS_TOTAL_SQL, _VIEWS_SQL, base)
    reveals = await _section(
        session, _INQUIRY_TOTAL_SQL, _INQUIRY_SQL, {**base, "is_reveal": True}
    )
    leads = await _section(
        session, _INQUIRY_TOTAL_SQL, _INQUIRY_SQL, {**base, "is_reveal": False}
    )
    row = (await session.execute(_RESPONSE_SQL, base)).one()._mapping
    avg = row["avg_response_seconds"]
    return AnalyticsData(
        views=views,
        reveals=reveals,
        leads=leads,
        response=ResponseStats(
            total=int(row["total"]),
            responded=int(row["responded"]),
            avg_response_seconds=int(avg) if avg is not None else None,
        ),
    )
```

`schemas.py`:

```python
class PincodeCountOut(BaseModel):
    pincode: str
    count: int


class AnalyticsSectionOut(BaseModel):
    total: int
    by_pincode: list[PincodeCountOut]


class AnalyticsResponseOut(BaseModel):
    total: int
    responded: int
    avg_response_seconds: int | None


class BusinessAnalyticsOut(BaseModel):
    days: int
    views: AnalyticsSectionOut
    reveals: AnalyticsSectionOut
    leads: AnalyticsSectionOut
    response: AnalyticsResponseOut
```

`router.py` (import `Literal` from typing, `timedelta` from datetime, plus the new schemas):

```python
@router.get("/businesses/{business_id}/analytics")
async def business_analytics(
    request: Request,
    business_id: uuid.UUID,
    session: SessionDep,
    days: Literal[7, 30, 90] = 30,
) -> BusinessAnalyticsOut:
    """Analytics-lite (D26.D): request-time SQL over inquiries + profile
    views. Owner-only - the same 404 IDOR contract as every vendor write."""
    try:
        await service.get_owned_business(session, _principal_user_id(request), business_id)
    except service.BusinessNotFoundError as exc:
        raise HTTPException(status_code=404, detail="Business not found") from exc
    since = datetime.now(UTC) - timedelta(days=days)
    data = await analytics.business_analytics(session, business_id=business_id, since=since)
    return BusinessAnalyticsOut(
        days=days,
        views=AnalyticsSectionOut(
            total=data.views.total,
            by_pincode=[PincodeCountOut(**asdict(p)) for p in data.views.by_pincode],
        ),
        reveals=AnalyticsSectionOut(
            total=data.reveals.total,
            by_pincode=[PincodeCountOut(**asdict(p)) for p in data.reveals.by_pincode],
        ),
        leads=AnalyticsSectionOut(
            total=data.leads.total,
            by_pincode=[PincodeCountOut(**asdict(p)) for p in data.leads.by_pincode],
        ),
        response=AnalyticsResponseOut(**asdict(data.response)),
    )
```

- [ ] **Step 4: Run tests**

Run: `python -m pytest tests/test_business_analytics.py tests/test_profile_views.py -q`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add backend/core/modules/directory/analytics.py backend/core/modules/directory/schemas.py backend/core/modules/directory/router.py backend/core/tests/test_business_analytics.py
git commit -m "feat(d26): owner analytics endpoint - views/reveals/leads by pincode"
```

---

### Task 8: Inbox `type` filter

**Files:**
- Modify: `backend/core/modules/directory/leads_router.py`
- Test: `backend/core/tests/test_inbox_type_filter.py`

**Interfaces:**
- Consumes: existing `GET /leads/inbox` (business_id + status + keyset).
- Produces: optional `type=contact|milk_subscription` query param, combinable with `status`.

- [ ] **Step 1: Write the failing test** — `tests/test_inbox_type_filter.py` (api fixture from Task 2; seed one `contact` + one `milk_subscription` inquiry for an owned business, then `GET /leads/inbox?business_id=...&type=milk_subscription` returns only the milk one; `type=bogus` → 422; combined `type` + `status` filters both).

```python
"""Inbox type filter (D26.B): needs arrive as milk_subscription children;
vendors filter them from plain contact leads."""

import uuid

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from modules.directory import service
from modules.directory.leads_models import Inquiry
from tests.d26_helpers import _as, api  # noqa: F401

pytestmark = pytest.mark.asyncio


async def _seeded_inbox(session: AsyncSession, owner: uuid.UUID) -> uuid.UUID:
    business = await service.create_business(
        session, owner_user_id=owner, name="Inbox Dairy", type_="vendor",
        primary_pincode="641001",
    )
    session.add_all(
        [
            Inquiry(type="contact", from_user_id=uuid.uuid4(), business_id=business.id,
                    payload={"message": "hi"}, pincode="641001"),
            Inquiry(type="milk_subscription", from_user_id=uuid.uuid4(),
                    business_id=business.id,
                    payload={"qty_liters": 2, "milk_type": "cow", "schedule": "daily"},
                    pincode="641001"),
        ]
    )
    await session.commit()
    return business.id


async def test_type_filter_returns_only_matching(api) -> None:
    http, session = api
    owner = uuid.uuid4()
    business_id = await _seeded_inbox(session, owner)
    response = await http.get(
        f"/leads/inbox?business_id={business_id}&type=milk_subscription", headers=_as(owner)
    )
    assert response.status_code == 200
    items = response.json()["items"]
    assert len(items) == 1
    assert items[0]["type"] == "milk_subscription"


async def test_no_filter_returns_all(api) -> None:
    http, session = api
    owner = uuid.uuid4()
    business_id = await _seeded_inbox(session, owner)
    response = await http.get(f"/leads/inbox?business_id={business_id}", headers=_as(owner))
    assert len(response.json()["items"]) == 2


async def test_bogus_type_422(api) -> None:
    http, session = api
    owner = uuid.uuid4()
    business_id = await _seeded_inbox(session, owner)
    response = await http.get(
        f"/leads/inbox?business_id={business_id}&type=carrier_pigeon", headers=_as(owner)
    )
    assert response.status_code == 422
```

- [ ] **Step 2: Run to verify failure** — `python -m pytest tests/test_inbox_type_filter.py -q` → the filter test fails (param ignored → 2 items).

- [ ] **Step 3: Implement** — in `leads_router.py` `inbox()` signature add `type: InquiryType | None = None,` (the `InquiryType` Literal is already imported from `leads_schemas`) and after the status filter:

```python
    if type is not None:
        query = query.where(Inquiry.type == type)
```

- [ ] **Step 4: Run** — `python -m pytest tests/test_inbox_type_filter.py -q` → 3 passed. Also `python -m pytest -q -k "leads"` for regressions.

- [ ] **Step 5: Commit**

```bash
git add backend/core/modules/directory/leads_router.py backend/core/tests/test_inbox_type_filter.py
git commit -m "feat(d26): inbox type filter (contact vs milk_subscription)"
```

---

### Task 9: Authed vertical-schema route (create-form source)

**Files:**
- Modify: `backend/core/modules/directory/catalog_router.py`
- Test: `backend/core/tests/test_vertical_schema_route.py`

**Interfaces:**
- Consumes: `catalog_service.get_vertical(session, slug)`, `catalog_service.active_schema(session, vertical_slug) -> SpecSchema | None`, existing `SchemaVersionOut` DTO.
- Produces: `GET /catalog/verticals/{vertical}/schema` (authed, NOT public) → `SchemaVersionOut {vertical_slug, version, fields, created_at}`. The products console renders create forms from `fields`. 404 when the vertical is missing/inactive or has no schema.

- [ ] **Step 1: Write the failing test** — `tests/test_vertical_schema_route.py` (api fixture from Task 2). Seeding: look at `tests/test_catalog_router.py` for the existing vertical+schema seeding helper (a `Vertical` row + `SpecSchema` row via `catalog_service.create_schema_version` or direct model inserts) and reuse that idiom. Tests: (a) authed GET returns the ACTIVE (highest) version's fields; (b) unknown vertical → 404; (c) unauthenticated → 401.

```python
"""Vertical schema fetch (D26 products console): the create form needs the
active field defs BEFORE any product exists."""

import uuid

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from tests.d26_helpers import _as, api  # noqa: F401

pytestmark = pytest.mark.asyncio

# Seeding: create a Vertical row + a SpecSchema v1 for it. Reuse the exact
# seeding helper/idiom from tests/test_catalog_router.py (open that file and
# copy its vertical+schema setup into a local `_seed_milk_vertical(session)`
# helper here) - the column names live in modules/directory/catalog_models.py.


async def test_returns_active_schema_fields(api) -> None:
    http, session = api
    # seed vertical "milk" with schema v1 fields [{"key": "qty", ...}]
    response = await http.get("/catalog/verticals/milk/schema", headers=_as(uuid.uuid4()))
    assert response.status_code == 200
    body = response.json()
    assert body["vertical_slug"] == "milk"
    assert body["version"] >= 1
    assert isinstance(body["fields"], list) and body["fields"]


async def test_unknown_vertical_404(api) -> None:
    http, _session = api
    response = await http.get("/catalog/verticals/nope/schema", headers=_as(uuid.uuid4()))
    assert response.status_code == 404


async def test_requires_auth(api) -> None:
    http, _session = api
    response = await http.get("/catalog/verticals/milk/schema")
    assert response.status_code == 401
```

- [ ] **Step 2: Run to verify failure** — `python -m pytest tests/test_vertical_schema_route.py -q` → 404/405.

- [ ] **Step 3: Implement** — in `catalog_router.py`, next to the other vertical routes (NOT public; SecureRouter default-private is the point — vendors are logged in, and keeping it private avoids widening the anonymous surface):

```python
@router.get("/verticals/{vertical}/schema")
async def get_vertical_schema(
    request: Request, vertical: str, session: SessionDep
) -> SchemaVersionOut:
    """Active field definitions for a vertical (D26 products console) - the
    create form's source of truth. Authed: vendors only need this."""
    found = await catalog_service.get_vertical(session, vertical)
    if found is None or found.status != "active":
        raise HTTPException(status_code=404, detail="Vertical not found")
    schema = await catalog_service.active_schema(session, vertical)
    if schema is None:
        raise HTTPException(status_code=404, detail="Vertical not found")
    return SchemaVersionOut(
        vertical_slug=schema.vertical_slug,
        version=schema.version,
        fields=schema.fields,
        created_at=schema.created_at,
    )
```

(Match `SpecSchema`'s actual field attribute name — check `catalog_models.py:43-59`; if the column is `fields_json` or similar, map accordingly.)

- [ ] **Step 4: Run** — `python -m pytest tests/test_vertical_schema_route.py tests/test_catalog_router.py -q` → PASS.

- [ ] **Step 5: Backend gate sweep + commit**

Run from `backend/core`:

```bash
ruff format . && ruff check . && mypy . && lint-imports && python scripts/dump_public_routes.py --check && python -m pytest -m "not slow" -q
```

Expected: all green (fix anything that isn't before committing).

```bash
git add backend/core/modules/directory/catalog_router.py backend/core/tests/test_vertical_schema_route.py
git commit -m "feat(d26): authed vertical schema route for product forms"
```

---

### Task 10: Frontend plumbing — api helpers, proxy methods, catalog proxy, view relays

**Files:**
- Modify: `apps/web-agri/lib/api.ts`
- Modify: `apps/web-agri/app/api/directory/[...path]/route.ts`
- Create: `apps/web-agri/app/api/catalog/[...path]/route.ts`
- Create: `apps/web-agri/app/api/view/route.ts`
- Create: `apps/web-milk/app/api/view/route.ts`

**Interfaces:**
- Produces: `putJson(path, payload)`, `patchJson(path, payload)`, `deleteJson(path)` in `lib/api.ts` (same 401-retry-once semantics as `postJson`); directory proxy forwards PATCH + PUT (raw-bytes style, same as its POST); catalog proxy (auth-required, allowlist `verticals|my|products|businesses`, methods GET/POST/PATCH/DELETE, raw-bytes bodies for image multipart); `/api/view` relays `{slug, pincode?}` to the public backend beacon with NO auth (guests are most views) and always answers 204.

- [ ] **Step 1: Extend `apps/web-agri/lib/api.ts`** — append below `postJson`:

```typescript
export function putJson(path: string, payload?: unknown): Promise<JsonBody> {
  return request(path, {
    method: "PUT",
    headers: { "content-type": "application/json" },
    body: JSON.stringify(payload ?? {}),
  });
}

export function patchJson(path: string, payload?: unknown): Promise<JsonBody> {
  return request(path, {
    method: "PATCH",
    headers: { "content-type": "application/json" },
    body: JSON.stringify(payload ?? {}),
  });
}

export function deleteJson(path: string): Promise<JsonBody> {
  return request(path, { method: "DELETE" });
}
```

- [ ] **Step 2: Add PATCH + PUT to the directory proxy** — in `apps/web-agri/app/api/directory/[...path]/route.ts`, widen the method union and body condition:

```typescript
async function forward(
  req: NextRequest,
  params: Promise<{ path: string[] }>,
  method: "GET" | "POST" | "PATCH" | "PUT",
): Promise<NextResponse> {
```

Body-bearing check becomes `method !== "GET"` in both the content-length guard and the fetch body spread:

```typescript
  if (method !== "GET") {
    const contentLength = Number(req.headers.get("content-length"));
    if (Number.isFinite(contentLength) && contentLength > MAX_BODY_BYTES) {
      return NextResponse.json({ detail: "payload too large" }, { status: 413 });
    }
  }
  ...
    ...(method !== "GET" ? { body: Buffer.from(await req.arrayBuffer()) } : {}),
```

And export the two new handlers:

```typescript
export async function PATCH(req: NextRequest, ctx: Ctx): Promise<NextResponse> {
  return forward(req, ctx.params, "PATCH");
}
export async function PUT(req: NextRequest, ctx: Ctx): Promise<NextResponse> {
  return forward(req, ctx.params, "PUT");
}
```

- [ ] **Step 3: Create the catalog proxy** — `apps/web-agri/app/api/catalog/[...path]/route.ts`. Copy the directory proxy file wholesale, then change: upstream prefix `${API}/catalog/`, add the allowlist gate right after the traversal guard (billing-proxy idiom), method union `"GET" | "POST" | "PATCH" | "DELETE"`, and the four exports:

```typescript
// Only vendor-facing catalog surfaces; admin/* must never ride the
// browser-authenticated proxy.
const ALLOWED_FIRST_SEGMENTS = new Set(["verticals", "my", "products", "businesses"]);
```

```typescript
  const [firstSegment] = path;
  if (!firstSegment || !ALLOWED_FIRST_SEGMENTS.has(firstSegment)) {
    return NextResponse.json({ detail: "not_found" }, { status: 404 });
  }
```

- [ ] **Step 4: Create the view relays** — `apps/web-agri/app/api/view/route.ts` and byte-identical `apps/web-milk/app/api/view/route.ts`:

```typescript
/**
 * Guest view-beacon relay (D26 analytics-lite): browser -> same-origin
 * /api/view -> public FastAPI beacon. Deliberately NO auth and NO token -
 * profile views are mostly anonymous. Always 204: a lost view must never
 * surface as a user-visible error.
 */
import type { NextRequest } from "next/server";
import { NextResponse } from "next/server";

const API = process.env.API_BASE_URL ?? "http://127.0.0.1:8000";
const SLUG_RE = /^[a-z0-9]+(?:-[a-z0-9]+)*$/;
const PINCODE_RE = /^\d{6}$/;

export async function POST(req: NextRequest): Promise<NextResponse> {
  const body = (await req.json().catch(() => null)) as {
    slug?: unknown;
    pincode?: unknown;
  } | null;
  const slug = typeof body?.slug === "string" ? body.slug : "";
  if (!SLUG_RE.test(slug)) return new NextResponse(null, { status: 204 });
  const pincode =
    typeof body?.pincode === "string" && PINCODE_RE.test(body.pincode)
      ? body.pincode
      : undefined;
  try {
    await fetch(`${API}/directory/businesses/${encodeURIComponent(slug)}/view`, {
      method: "POST",
      headers: { "content-type": "application/json" },
      body: JSON.stringify(pincode ? { pincode } : {}),
      cache: "no-store",
    });
  } catch {
    // fire-and-forget by contract
  }
  return new NextResponse(null, { status: 204 });
}
```

- [ ] **Step 5: Verify + commit**

Run (repo root): `pnpm typecheck && pnpm lint`
Expected: green.

```bash
git add apps/web-agri/lib/api.ts "apps/web-agri/app/api/directory/[...path]/route.ts" "apps/web-agri/app/api/catalog/[...path]/route.ts" apps/web-agri/app/api/view/route.ts apps/web-milk/app/api/view/route.ts
git commit -m "feat(d26): BFF plumbing - PATCH/PUT proxying, catalog proxy, view relays"
```

---

### Task 11: Listings console page (manage listing + coverage + delivery windows)

**Files:**
- Replace: `apps/web-agri/app/business/listings/page.tsx`
- Create: `apps/web-agri/app/business/listings/listings-client.tsx`

**Interfaces:**
- Consumes: `getJson/patchJson/putJson/postJson` + `ApiError` from `@/lib/api`; `GET /api/directory/businesses?limit=50` (picker), `GET /api/directory/businesses/{slug}` (detail incl. `coverage_pincodes` + `business.delivery_windows`), `PATCH /api/directory/businesses/{id}`, `PUT /api/directory/businesses/{id}/coverage`, `POST /api/directory/businesses` (create); `@agri/ui` `Button, Card, EmptyState, Skeleton, cn`.
- Produces: the `/business/listings` module page. Section order: business picker (or create form when the user owns none) → listing fields (name, type, primary pincode, description-en) → delivery-windows editor → coverage-pincodes editor.

- [ ] **Step 1: Replace the stub page** — `apps/web-agri/app/business/listings/page.tsx`:

```tsx
import { redirect } from "next/navigation";

import { auth } from "@/lib/auth";

import { ListingsClient } from "./listings-client";

export const metadata = { title: "Listings", robots: { index: false } };

export default async function ListingsPage() {
  const user = await auth.getServerUser();
  if (!user) redirect("/api/auth/login?next=/business/listings");
  return (
    <main className="mx-auto max-w-3xl px-4 py-6">
      <h1 className="font-display text-[20px] font-extrabold text-ink">Listings</h1>
      <ListingsClient />
    </main>
  );
}
```

- [ ] **Step 2: Create `listings-client.tsx`** — follow inbox-client idioms exactly (FIELD/LABEL constants, AlertNotice, picker effect). Full component:

```tsx
"use client";

import { Button, Card, EmptyState, Skeleton, cn } from "@agri/ui";
import { useEffect, useState, type ReactNode } from "react";

import { ApiError, getJson, patchJson, postJson, putJson } from "@/lib/api";

type BusinessType = "vendor" | "shop" | "lab" | "farm";

interface DeliveryWindow {
  days: string[];
  open: string;
  close: string;
}

interface BusinessOut {
  id: string;
  name: string;
  slug: string;
  type: BusinessType;
  primary_pincode: string;
  description: Record<string, string> | null;
  delivery_windows: DeliveryWindow[] | null;
  verification_status: string;
  subscription_tier: string;
}

const FIELD =
  "mt-1 block min-h-[44px] w-full rounded-btn border border-line bg-card px-3 py-2 text-[13px] text-ink";
const LABEL = "block text-[13px] font-semibold text-ink";
const DAYS = ["mon", "tue", "wed", "thu", "fri", "sat", "sun"] as const;
const TYPES: BusinessType[] = ["vendor", "shop", "lab", "farm"];
const PINCODE_RE = /^\d{6}$/;

function AlertNotice({ children }: { children: ReactNode }) {
  return (
    <div className="rounded-card border border-alert-line bg-alert-bg p-3 text-[13px] font-semibold text-ink">
      {children}
    </div>
  );
}

function OkNotice({ children }: { children: ReactNode }) {
  return (
    <div className="rounded-card bg-verified-bg p-3 text-[13px] font-semibold text-verified-fg">
      {children}
    </div>
  );
}

export function ListingsClient() {
  const [businesses, setBusinesses] = useState<BusinessOut[] | null>(null);
  const [loadError, setLoadError] = useState(false);
  const [selectedId, setSelectedId] = useState<string | null>(null);

  // create-business form (fresh vendors own nothing yet)
  const [newName, setNewName] = useState("");
  const [newType, setNewType] = useState<BusinessType>("vendor");
  const [newPincode, setNewPincode] = useState("");
  const [creating, setCreating] = useState(false);
  const [createError, setCreateError] = useState<string | null>(null);

  // listing form
  const [name, setName] = useState("");
  const [type, setType] = useState<BusinessType>("vendor");
  const [primaryPincode, setPrimaryPincode] = useState("");
  const [descriptionEn, setDescriptionEn] = useState("");
  const [windows, setWindows] = useState<DeliveryWindow[]>([]);
  const [coverage, setCoverage] = useState<string[]>([]);
  const [coverageInput, setCoverageInput] = useState("");
  const [detailLoading, setDetailLoading] = useState(false);
  const [saving, setSaving] = useState<"listing" | "coverage" | null>(null);
  const [notice, setNotice] = useState<{ kind: "ok" | "error"; text: string } | null>(null);

  const loadBusinesses = async () => {
    try {
      const body = await getJson("/api/directory/businesses?limit=50");
      const list = (body.items as BusinessOut[] | undefined) ?? [];
      setBusinesses(list);
      if (list[0] && !selectedId) setSelectedId(list[0].id);
    } catch {
      setLoadError(true);
    }
  };

  useEffect(() => {
    void loadBusinesses();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  useEffect(() => {
    const selected = businesses?.find((b) => b.id === selectedId);
    if (!selected) return;
    setName(selected.name);
    setType(selected.type);
    setPrimaryPincode(selected.primary_pincode);
    setDescriptionEn(selected.description?.en ?? "");
    setWindows(selected.delivery_windows ?? []);
    setDetailLoading(true);
    setNotice(null);
    void (async () => {
      try {
        const detail = await getJson(`/api/directory/businesses/${selected.slug}`);
        setCoverage((detail.coverage_pincodes as string[] | undefined) ?? []);
      } catch {
        setCoverage([]);
      } finally {
        setDetailLoading(false);
      }
    })();
  }, [selectedId, businesses]);

  const create = async () => {
    if (!newName.trim() || !PINCODE_RE.test(newPincode)) {
      setCreateError("Name and a 6-digit pincode are required.");
      return;
    }
    setCreating(true);
    setCreateError(null);
    try {
      const created = await postJson("/api/directory/businesses", {
        name: newName.trim(),
        type: newType,
        primary_pincode: newPincode,
      });
      await loadBusinesses();
      setSelectedId(created.id as string);
    } catch (err) {
      setCreateError(
        err instanceof ApiError ? `Could not create listing (${err.detail}).` : "Could not create listing.",
      );
    } finally {
      setCreating(false);
    }
  };

  const saveListing = async () => {
    if (!selectedId) return;
    setSaving("listing");
    setNotice(null);
    try {
      const description = descriptionEn.trim()
        ? { ...(businesses?.find((b) => b.id === selectedId)?.description ?? {}), en: descriptionEn.trim() }
        : null;
      await patchJson(`/api/directory/businesses/${selectedId}`, {
        name: name.trim(),
        type,
        primary_pincode: primaryPincode,
        description,
        delivery_windows: windows,
      });
      setNotice({ kind: "ok", text: "Listing saved." });
      void loadBusinesses();
    } catch (err) {
      setNotice({
        kind: "error",
        text:
          err instanceof ApiError && err.status === 422
            ? "Check the highlighted fields — delivery windows need valid days and open < close times."
            : "Could not save — please try again.",
      });
    } finally {
      setSaving(null);
    }
  };

  const addCoveragePincode = () => {
    const value = coverageInput.trim();
    if (!PINCODE_RE.test(value) || coverage.includes(value)) return;
    setCoverage((prev) => [...prev, value].sort());
    setCoverageInput("");
  };

  const saveCoverage = async () => {
    if (!selectedId) return;
    setSaving("coverage");
    setNotice(null);
    try {
      await putJson(`/api/directory/businesses/${selectedId}/coverage`, { pincodes: coverage });
      setNotice({ kind: "ok", text: "Coverage saved — customers in these pincodes can now find you." });
    } catch {
      setNotice({ kind: "error", text: "Could not save coverage — please try again." });
    } finally {
      setSaving(null);
    }
  };

  const updateWindow = (index: number, patch: Partial<DeliveryWindow>) => {
    setWindows((prev) => prev.map((w, i) => (i === index ? { ...w, ...patch } : w)));
  };

  if (loadError) {
    return (
      <div className="mt-4">
        <AlertNotice>Could not load your businesses — please try again.</AlertNotice>
      </div>
    );
  }
  if (businesses === null) {
    return (
      <div className="mt-4 space-y-3">
        <Skeleton width="100%" height="44px" />
        <Skeleton width="100%" height="200px" />
      </div>
    );
  }

  return (
    <div className="mt-4 space-y-4">
      {businesses.length === 0 ? (
        <Card className="space-y-3 p-4">
          <p className="text-[13px] font-extrabold text-ink">Create your listing</p>
          <label className={LABEL}>
            Business name
            <input className={FIELD} value={newName} maxLength={200} onChange={(e) => setNewName(e.target.value)} />
          </label>
          <label className={LABEL}>
            Type
            <select className={FIELD} value={newType} onChange={(e) => setNewType(e.target.value as BusinessType)}>
              {TYPES.map((t) => (
                <option key={t} value={t}>{t}</option>
              ))}
            </select>
          </label>
          <label className={LABEL}>
            Primary pincode
            <input className={FIELD} value={newPincode} maxLength={6} inputMode="numeric" onChange={(e) => setNewPincode(e.target.value)} />
          </label>
          {createError ? <AlertNotice>{createError}</AlertNotice> : null}
          <Button type="button" variant="brand" disabled={creating} onClick={() => void create()}>
            {creating ? "Creating..." : "Create listing"}
          </Button>
        </Card>
      ) : (
        <>
          <label className={LABEL}>
            Business
            <select className={FIELD} value={selectedId ?? ""} onChange={(e) => setSelectedId(e.target.value)}>
              {businesses.map((b) => (
                <option key={b.id} value={b.id}>{b.name}</option>
              ))}
            </select>
          </label>

          {notice ? (
            notice.kind === "ok" ? <OkNotice>{notice.text}</OkNotice> : <AlertNotice>{notice.text}</AlertNotice>
          ) : null}

          <Card className="space-y-3 p-4">
            <p className="text-[13px] font-extrabold text-ink">Listing details</p>
            <label className={LABEL}>
              Name
              <input className={FIELD} value={name} maxLength={200} onChange={(e) => setName(e.target.value)} />
            </label>
            <label className={LABEL}>
              Type
              <select className={FIELD} value={type} onChange={(e) => setType(e.target.value as BusinessType)}>
                {TYPES.map((t) => (
                  <option key={t} value={t}>{t}</option>
                ))}
              </select>
            </label>
            <label className={LABEL}>
              Primary pincode
              <input className={FIELD} value={primaryPincode} maxLength={6} inputMode="numeric" onChange={(e) => setPrimaryPincode(e.target.value)} />
            </label>
            <label className={LABEL}>
              Description (English)
              <textarea className={cn(FIELD, "min-h-[80px]")} value={descriptionEn} maxLength={2000} onChange={(e) => setDescriptionEn(e.target.value)} />
            </label>

            <p className="text-[13px] font-extrabold text-ink">Delivery windows</p>
            {windows.map((window, index) => (
              <div key={index} className="space-y-2 rounded-card border border-line p-3">
                <div className="flex flex-wrap gap-2">
                  {DAYS.map((day) => (
                    <label key={day} className="flex min-h-[44px] items-center gap-1 text-[13px] text-ink">
                      <input
                        type="checkbox"
                        checked={window.days.includes(day)}
                        onChange={(e) =>
                          updateWindow(index, {
                            days: e.target.checked
                              ? [...window.days, day]
                              : window.days.filter((d) => d !== day),
                          })
                        }
                      />
                      {day}
                    </label>
                  ))}
                </div>
                <div className="flex items-end gap-2">
                  <label className={LABEL}>
                    Open
                    <input type="time" className={FIELD} value={window.open} onChange={(e) => updateWindow(index, { open: e.target.value })} />
                  </label>
                  <label className={LABEL}>
                    Close
                    <input type="time" className={FIELD} value={window.close} onChange={(e) => updateWindow(index, { close: e.target.value })} />
                  </label>
                  <Button type="button" variant="ghost" onClick={() => setWindows((prev) => prev.filter((_, i) => i !== index))}>
                    Remove
                  </Button>
                </div>
              </div>
            ))}
            {windows.length < 7 ? (
              <Button
                type="button"
                variant="ghost"
                onClick={() => setWindows((prev) => [...prev, { days: ["mon"], open: "06:00", close: "09:00" }])}
              >
                Add delivery window
              </Button>
            ) : null}

            <Button type="button" variant="brand" disabled={saving === "listing"} onClick={() => void saveListing()}>
              {saving === "listing" ? "Saving..." : "Save listing"}
            </Button>
          </Card>

          <Card className="space-y-3 p-4">
            <p className="text-[13px] font-extrabold text-ink">Coverage pincodes</p>
            <p className="text-[12px] text-sub">
              Customers searching these pincodes will find this business. Up to 500.
            </p>
            {detailLoading ? (
              <Skeleton width="100%" height="44px" />
            ) : (
              <div className="flex flex-wrap gap-2">
                {coverage.map((pincode) => (
                  <span key={pincode} className="inline-flex items-center gap-1 rounded-pill bg-line px-[9px] py-[3px] text-[12px] font-semibold text-ink">
                    {pincode}
                    <button
                      type="button"
                      aria-label={`Remove ${pincode}`}
                      className="min-h-[24px] min-w-[24px]"
                      onClick={() => setCoverage((prev) => prev.filter((p) => p !== pincode))}
                    >
                      ×
                    </button>
                  </span>
                ))}
                {coverage.length === 0 ? <span className="text-[12px] text-sub">No coverage yet.</span> : null}
              </div>
            )}
            <div className="flex items-end gap-2">
              <label className={cn(LABEL, "flex-1")}>
                Add pincode
                <input
                  className={FIELD}
                  value={coverageInput}
                  maxLength={6}
                  inputMode="numeric"
                  onChange={(e) => setCoverageInput(e.target.value)}
                  onKeyDown={(e) => {
                    if (e.key === "Enter") {
                      e.preventDefault();
                      addCoveragePincode();
                    }
                  }}
                />
              </label>
              <Button type="button" variant="ghost" onClick={addCoveragePincode}>
                Add
              </Button>
            </div>
            <Button type="button" variant="brand" disabled={saving === "coverage"} onClick={() => void saveCoverage()}>
              {saving === "coverage" ? "Saving..." : "Save coverage"}
            </Button>
          </Card>
        </>
      )}
    </div>
  );
}
```

(Unused import `EmptyState` — drop it if lint flags it.)

- [ ] **Step 3: Verify + commit**

Run: `pnpm typecheck && pnpm lint && pnpm check:hex`
Expected: green.

```bash
git add apps/web-agri/app/business/listings
git commit -m "feat(d26): listings console - listing fields, delivery windows, coverage editor"
```

---

### Task 12: Products console page (schema-driven forms)

**Files:**
- Replace: `apps/web-agri/app/business/products/page.tsx`
- Create: `apps/web-agri/app/business/products/products-client.tsx`

**Interfaces:**
- Consumes: `GET /api/catalog/verticals` (`items: [{slug, name: {en,...}}]`), `GET /api/catalog/verticals/{slug}/schema` (`{version, fields: [{key, label?, type, required?, values?, min?, max?, max_length?}]}` — confirm exact field-def keys against `modules/directory/specs.py FieldDef` before coding), `GET /api/catalog/my/products?business_id=`, `POST /api/catalog/businesses/{id}/products`, `PATCH /api/catalog/products/{id}`; 422 errors carry `{detail: {code, field}}` or a `{code, field}` detail — map to inline errors.
- Produces: `/business/products` page: business picker → vertical picker → product list (name, price, status + moderation badges, archive button, "load more") → create form rendered from schema fields (string→text input, number→number input, boolean→checkbox, enum→select).

- [ ] **Step 1: Replace the stub page** — same server-gate shell as Task 11 (`title: "Products"`, `next=/business/products`, mounts `<ProductsClient />`).

- [ ] **Step 2: Create `products-client.tsx`**:

```tsx
"use client";

import { Button, Card, EmptyState, Skeleton, cn } from "@agri/ui";
import { useEffect, useState, type ReactNode } from "react";

import { ApiError, getJson, patchJson, postJson } from "@/lib/api";

interface BusinessRef {
  id: string;
  name: string;
}

interface Vertical {
  slug: string;
  name: Record<string, string>;
}

interface SpecField {
  key: string;
  label?: Record<string, string> | string;
  type: "string" | "number" | "boolean" | "enum";
  required?: boolean;
  values?: string[];
  min?: number;
  max?: number;
  max_length?: number;
}

interface Product {
  id: string;
  vertical_slug: string;
  name: string;
  specs: Record<string, unknown>;
  price_display: string | null;
  status: string;
  moderation_status: string;
}

const FIELD =
  "mt-1 block min-h-[44px] w-full rounded-btn border border-line bg-card px-3 py-2 text-[13px] text-ink";
const LABEL = "block text-[13px] font-semibold text-ink";

function AlertNotice({ children }: { children: ReactNode }) {
  return (
    <div className="rounded-card border border-alert-line bg-alert-bg p-3 text-[13px] font-semibold text-ink">
      {children}
    </div>
  );
}

function fieldLabel(field: SpecField): string {
  if (typeof field.label === "string") return field.label;
  return field.label?.en ?? field.key;
}

function ModerationChip({ status }: { status: string }) {
  const classes =
    status === "approved"
      ? "bg-verified-bg text-verified-fg"
      : status === "rejected"
        ? "bg-alert-bg text-ink"
        : "bg-sponsored-bg text-sponsored-fg";
  return (
    <span className={cn("inline-flex items-center rounded-pill px-[9px] py-[3px] text-[11px] font-extrabold", classes)}>
      {status}
    </span>
  );
}

export function ProductsClient() {
  const [businesses, setBusinesses] = useState<BusinessRef[] | null>(null);
  const [businessError, setBusinessError] = useState(false);
  const [selectedId, setSelectedId] = useState<string | null>(null);

  const [verticals, setVerticals] = useState<Vertical[]>([]);
  const [verticalSlug, setVerticalSlug] = useState<string>("");
  const [fields, setFields] = useState<SpecField[] | null>(null);

  const [products, setProducts] = useState<Product[]>([]);
  const [cursor, setCursor] = useState<string | null>(null);
  const [listLoading, setListLoading] = useState(false);

  const [productName, setProductName] = useState("");
  const [priceDisplay, setPriceDisplay] = useState("");
  const [specValues, setSpecValues] = useState<Record<string, string | boolean>>({});
  const [submitting, setSubmitting] = useState(false);
  const [formError, setFormError] = useState<string | null>(null);

  useEffect(() => {
    void (async () => {
      try {
        const [bizBody, vertBody] = await Promise.all([
          getJson("/api/directory/businesses?limit=50"),
          getJson("/api/catalog/verticals?limit=50"),
        ]);
        const list = (bizBody.items as BusinessRef[] | undefined) ?? [];
        setBusinesses(list);
        if (list[0]) setSelectedId(list[0].id);
        const verts = (vertBody.items as Vertical[] | undefined) ?? [];
        setVerticals(verts);
        if (verts[0]) setVerticalSlug(verts[0].slug);
      } catch {
        setBusinessError(true);
      }
    })();
  }, []);

  useEffect(() => {
    if (!verticalSlug) return;
    setFields(null);
    void (async () => {
      try {
        const body = await getJson(`/api/catalog/verticals/${verticalSlug}/schema`);
        setFields((body.fields as SpecField[] | undefined) ?? []);
        setSpecValues({});
      } catch {
        setFields([]);
      }
    })();
  }, [verticalSlug]);

  const loadProducts = async (businessId: string, cursorParam: string | null, append: boolean) => {
    setListLoading(!append);
    try {
      const params = new URLSearchParams({ business_id: businessId, limit: "20" });
      if (cursorParam) params.set("cursor", cursorParam);
      const body = await getJson(`/api/catalog/my/products?${params.toString()}`);
      const items = (body.items as Product[] | undefined) ?? [];
      setProducts((prev) => (append ? [...prev, ...items] : items));
      setCursor((body.next_cursor as string | null | undefined) ?? null);
    } catch {
      if (!append) setProducts([]);
    } finally {
      setListLoading(false);
    }
  };

  useEffect(() => {
    if (!selectedId) return;
    setCursor(null);
    void loadProducts(selectedId, null, false);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [selectedId]);

  const buildSpecs = (): Record<string, unknown> => {
    const specs: Record<string, unknown> = {};
    for (const field of fields ?? []) {
      const raw = specValues[field.key];
      if (field.type === "boolean") {
        specs[field.key] = raw === true;
        continue;
      }
      if (raw === undefined || raw === "") continue; // omitted optional
      specs[field.key] = field.type === "number" ? Number(raw) : raw;
    }
    return specs;
  };

  const createProduct = async () => {
    if (!selectedId || !productName.trim()) return;
    setSubmitting(true);
    setFormError(null);
    try {
      await postJson(`/api/catalog/businesses/${selectedId}/products`, {
        vertical_slug: verticalSlug,
        name: productName.trim(),
        specs: buildSpecs(),
        price_display: priceDisplay.trim() || null,
      });
      setProductName("");
      setPriceDisplay("");
      setSpecValues({});
      void loadProducts(selectedId, null, false);
    } catch (err) {
      setFormError(
        err instanceof ApiError && err.status === 422
          ? `Check the form: ${err.detail}`
          : "Could not save the product — please try again.",
      );
    } finally {
      setSubmitting(false);
    }
  };

  const archive = async (productId: string) => {
    try {
      await patchJson(`/api/catalog/products/${productId}`, { status: "archived" });
      if (selectedId) void loadProducts(selectedId, null, false);
    } catch {
      // list stays actionable; owner can retry
    }
  };

  if (businessError) {
    return (
      <div className="mt-4">
        <AlertNotice>Could not load your businesses — please try again.</AlertNotice>
      </div>
    );
  }
  if (businesses === null) {
    return (
      <div className="mt-4 space-y-3">
        <Skeleton width="100%" height="44px" />
        <Skeleton width="100%" height="160px" />
      </div>
    );
  }
  if (businesses.length === 0) {
    return (
      <EmptyState
        className="mt-4"
        icon="📦"
        title="Create a listing first"
        action={
          <a href="/business/listings" className="text-[13px] font-semibold text-ink underline">
            Go to listings
          </a>
        }
      />
    );
  }

  return (
    <div className="mt-4 space-y-4">
      <label className={LABEL}>
        Business
        <select className={FIELD} value={selectedId ?? ""} onChange={(e) => setSelectedId(e.target.value)}>
          {businesses.map((b) => (
            <option key={b.id} value={b.id}>{b.name}</option>
          ))}
        </select>
      </label>

      {listLoading ? (
        <Skeleton width="100%" height="120px" />
      ) : products.length === 0 ? (
        <EmptyState icon="🧺" title="No products yet — add your first below." />
      ) : (
        <div className="space-y-3">
          {products.map((product) => (
            <Card key={product.id} className="space-y-1 p-4">
              <div className="flex items-center justify-between gap-2">
                <span className="text-[13px] font-extrabold text-ink">{product.name}</span>
                <ModerationChip status={product.moderation_status} />
              </div>
              <p className="text-[12px] text-sub">
                {product.vertical_slug}
                {product.price_display ? ` · ${product.price_display}` : ""} · {product.status}
              </p>
              {product.status !== "archived" ? (
                <Button type="button" variant="ghost" onClick={() => void archive(product.id)}>
                  Archive
                </Button>
              ) : null}
            </Card>
          ))}
          {cursor ? (
            <Button type="button" variant="ghost" onClick={() => selectedId && void loadProducts(selectedId, cursor, true)}>
              Load more
            </Button>
          ) : null}
        </div>
      )}

      <Card className="space-y-3 p-4">
        <p className="text-[13px] font-extrabold text-ink">Add a product</p>
        <label className={LABEL}>
          Vertical
          <select className={FIELD} value={verticalSlug} onChange={(e) => setVerticalSlug(e.target.value)}>
            {verticals.map((v) => (
              <option key={v.slug} value={v.slug}>{v.name.en ?? v.slug}</option>
            ))}
          </select>
        </label>
        <label className={LABEL}>
          Name
          <input className={FIELD} value={productName} maxLength={200} onChange={(e) => setProductName(e.target.value)} />
        </label>
        <label className={LABEL}>
          Price (display text)
          <input className={FIELD} value={priceDisplay} maxLength={100} onChange={(e) => setPriceDisplay(e.target.value)} placeholder="₹60/litre" />
        </label>

        {fields === null ? (
          <Skeleton width="100%" height="60px" />
        ) : (
          fields.map((field) => (
            <label key={field.key} className={LABEL}>
              {fieldLabel(field)}
              {field.required ? " *" : ""}
              {field.type === "boolean" ? (
                <input
                  type="checkbox"
                  className="ml-2 min-h-[20px] min-w-[20px] align-middle"
                  checked={specValues[field.key] === true}
                  onChange={(e) => setSpecValues((s) => ({ ...s, [field.key]: e.target.checked }))}
                />
              ) : field.type === "enum" ? (
                <select
                  className={FIELD}
                  value={String(specValues[field.key] ?? "")}
                  onChange={(e) => setSpecValues((s) => ({ ...s, [field.key]: e.target.value }))}
                >
                  <option value="">—</option>
                  {(field.values ?? []).map((value) => (
                    <option key={value} value={value}>{value}</option>
                  ))}
                </select>
              ) : (
                <input
                  className={FIELD}
                  type={field.type === "number" ? "number" : "text"}
                  value={String(specValues[field.key] ?? "")}
                  maxLength={field.max_length}
                  onChange={(e) => setSpecValues((s) => ({ ...s, [field.key]: e.target.value }))}
                />
              )}
            </label>
          ))
        )}

        {formError ? <AlertNotice>{formError}</AlertNotice> : null}
        <Button
          type="button"
          variant="brand"
          disabled={submitting || !productName.trim() || !verticalSlug}
          onClick={() => void createProduct()}
        >
          {submitting ? "Saving..." : "Add product"}
        </Button>
        <p className="text-[12px] text-sub">New products are reviewed before they appear publicly.</p>
      </Card>
    </div>
  );
}
```

Before coding, confirm the `FieldDef` attribute names in `backend/core/modules/directory/specs.py:28` (e.g. `values` vs `options`, `max_length` vs `maxLength`) and align the `SpecField` interface.

- [ ] **Step 3: Verify + commit**

Run: `pnpm typecheck && pnpm lint`

```bash
git add apps/web-agri/app/business/products
git commit -m "feat(d26): products console - schema-driven create form, list, archive"
```

---

### Task 13: Inbox extension — type filter, need payloads, slow-responder nudge

**Files:**
- Modify: `apps/web-agri/app/business/inbox/inbox-client.tsx`

**Interfaces:**
- Consumes: `GET /api/leads/inbox?...&type=` (Task 8), existing stats endpoint.
- Produces: type filter select (All / Messages / Milk subscriptions), milk-subscription payload rendering including optional `delivery_time` and `note` (D25 need children), amber nudge banner when `avg_response_seconds > 86400`.

- [ ] **Step 1: Add the type filter state + param** — in `InboxClient`: `const [typeFilter, setTypeFilter] = useState<InquiryType | "all">("all");`. In `loadInbox`, after the `params` construction: `if (typeFilter !== "all") params.set("type", typeFilter);` and add `typeFilter` to the reload effect deps (`useEffect(..., [selectedId, typeFilter])`). Render next to the business picker:

```tsx
      <label className={LABEL}>
        Show
        <select
          className={FIELD}
          value={typeFilter}
          onChange={(event) => setTypeFilter(event.target.value as InquiryType | "all")}
        >
          <option value="all">All leads</option>
          <option value="contact">Messages</option>
          <option value="milk_subscription">Milk subscriptions</option>
        </select>
      </label>
```

- [ ] **Step 2: Render need extras** — extend `renderPayload`'s milk branch:

```tsx
  const { qty_liters, milk_type, schedule, delivery_time, note } = inquiry.payload;
  return (
    <div className="space-y-1">
      <p className="text-[13px] text-ink">
        {String(qty_liters ?? "?")} L/day · {String(milk_type ?? "?")} · {String(schedule ?? "?")}
      </p>
      {typeof delivery_time === "string" && delivery_time ? (
        <p className="text-[12px] text-sub">Preferred delivery: {delivery_time}</p>
      ) : null}
      {typeof note === "string" && note ? <p className="text-[12px] text-sub">“{note}”</p> : null}
    </div>
  );
```

- [ ] **Step 3: Nudge banner** — below the stats line:

```tsx
      {stats && stats.avg_response_seconds !== null && stats.avg_response_seconds > 86400 ? (
        <AlertNotice>
          Your average reply time is {formatAvgResponse(stats.avg_response_seconds)}. Fast replies
          win more customers — aim for under a day.
        </AlertNotice>
      ) : null}
```

- [ ] **Step 4: Verify + commit**

Run: `pnpm typecheck && pnpm lint`

```bash
git add apps/web-agri/app/business/inbox/inbox-client.tsx
git commit -m "feat(d26): inbox type filter, need details, slow-responder nudge"
```

---

### Task 14: Analytics console page

**Files:**
- Create: `apps/web-agri/app/business/analytics/page.tsx`, `apps/web-agri/app/business/analytics/analytics-client.tsx`
- Modify: `apps/web-agri/lib/console-modules.ts`

**Interfaces:**
- Consumes: `GET /api/directory/businesses/{id}/analytics?days=` (Task 7 shape).
- Produces: `/business/analytics` page + registry entry `{ id: "analytics", title: "Analytics", href: "/business/analytics" }` (insert after `products`). Stat tiles from `Card` + tokens (no chart primitive — deliberate), 7/30/90 toggle, per-source by-pincode rows.

- [ ] **Step 1: Registry entry** — append to `CONSOLE_MODULES` after `products`:

```typescript
  { id: "analytics", title: "Analytics", href: "/business/analytics" },
```

- [ ] **Step 2: Page** — same server-gate shell (`title: "Analytics"`, `next=/business/analytics`, mounts `<AnalyticsClient />`).

- [ ] **Step 3: Client** — `analytics-client.tsx`:

```tsx
"use client";

import { Card, EmptyState, Skeleton, cn } from "@agri/ui";
import { useEffect, useState, type ReactNode } from "react";

import { getJson } from "@/lib/api";

interface BusinessRef {
  id: string;
  name: string;
}

interface PincodeCount {
  pincode: string;
  count: number;
}

interface Section {
  total: number;
  by_pincode: PincodeCount[];
}

interface Analytics {
  days: number;
  views: Section;
  reveals: Section;
  leads: Section;
  response: { total: number; responded: number; avg_response_seconds: number | null };
}

const FIELD =
  "mt-1 block min-h-[44px] w-full rounded-btn border border-line bg-card px-3 py-2 text-[13px] text-ink";
const LABEL = "block text-[13px] font-semibold text-ink";
const RANGES = [7, 30, 90] as const;

function AlertNotice({ children }: { children: ReactNode }) {
  return (
    <div className="rounded-card border border-alert-line bg-alert-bg p-3 text-[13px] font-semibold text-ink">
      {children}
    </div>
  );
}

function formatAvg(seconds: number | null): string {
  if (seconds === null) return "—";
  if (seconds < 3600) return `${Math.max(1, Math.round(seconds / 60))}m`;
  return `${Math.round(seconds / 3600)}h`;
}

function StatTile({ label, value }: { label: string; value: string }) {
  return (
    <Card className="p-4">
      <p className="text-[12px] font-semibold uppercase tracking-wide text-sub">{label}</p>
      <p className="font-display text-[24px] font-extrabold text-ink">{value}</p>
    </Card>
  );
}

function PincodeRows({ title, section }: { title: string; section: Section }) {
  if (section.by_pincode.length === 0) return null;
  return (
    <Card className="space-y-2 p-4">
      <p className="text-[13px] font-extrabold text-ink">{title} by pincode</p>
      <ul className="space-y-1">
        {section.by_pincode.map((row) => (
          <li key={row.pincode} className="flex justify-between text-[13px] text-ink">
            <span>{row.pincode === "unknown" ? "Unknown pincode" : row.pincode}</span>
            <span className="font-semibold">{row.count}</span>
          </li>
        ))}
      </ul>
    </Card>
  );
}

export function AnalyticsClient() {
  const [businesses, setBusinesses] = useState<BusinessRef[] | null>(null);
  const [loadError, setLoadError] = useState(false);
  const [selectedId, setSelectedId] = useState<string | null>(null);
  const [days, setDays] = useState<(typeof RANGES)[number]>(30);
  const [data, setData] = useState<Analytics | null>(null);
  const [dataError, setDataError] = useState(false);

  useEffect(() => {
    void (async () => {
      try {
        const body = await getJson("/api/directory/businesses?limit=50");
        const list = (body.items as BusinessRef[] | undefined) ?? [];
        setBusinesses(list);
        if (list[0]) setSelectedId(list[0].id);
      } catch {
        setLoadError(true);
      }
    })();
  }, []);

  useEffect(() => {
    if (!selectedId) return;
    setData(null);
    setDataError(false);
    void (async () => {
      try {
        const body = await getJson(`/api/directory/businesses/${selectedId}/analytics?days=${days}`);
        setData(body as unknown as Analytics);
      } catch {
        setDataError(true);
      }
    })();
  }, [selectedId, days]);

  if (loadError) {
    return (
      <div className="mt-4">
        <AlertNotice>Could not load your businesses — please try again.</AlertNotice>
      </div>
    );
  }
  if (businesses === null) {
    return (
      <div className="mt-4 space-y-3">
        <Skeleton width="100%" height="44px" />
        <Skeleton width="100%" height="120px" />
      </div>
    );
  }
  if (businesses.length === 0) {
    return <EmptyState className="mt-4" icon="📈" title="Create a listing to see analytics." />;
  }

  return (
    <div className="mt-4 space-y-4">
      <label className={LABEL}>
        Business
        <select className={FIELD} value={selectedId ?? ""} onChange={(e) => setSelectedId(e.target.value)}>
          {businesses.map((b) => (
            <option key={b.id} value={b.id}>{b.name}</option>
          ))}
        </select>
      </label>

      <div className="flex gap-2" role="group" aria-label="Date range">
        {RANGES.map((range) => (
          <button
            key={range}
            type="button"
            onClick={() => setDays(range)}
            className={cn(
              "min-h-[44px] rounded-pill px-4 text-[13px] font-semibold",
              days === range ? "bg-ink text-card" : "bg-line text-ink",
            )}
          >
            {range} days
          </button>
        ))}
      </div>

      {dataError ? (
        <AlertNotice>Could not load analytics — please try again.</AlertNotice>
      ) : data === null ? (
        <Skeleton width="100%" height="160px" />
      ) : (
        <>
          <div className="grid grid-cols-2 gap-3 sm:grid-cols-4">
            <StatTile label="Profile views" value={String(data.views.total)} />
            <StatTile label="Contact reveals" value={String(data.reveals.total)} />
            <StatTile label="Leads" value={String(data.leads.total)} />
            <StatTile label="Avg response" value={formatAvg(data.response.avg_response_seconds)} />
          </div>
          <PincodeRows title="Views" section={data.views} />
          <PincodeRows title="Reveals" section={data.reveals} />
          <PincodeRows title="Leads" section={data.leads} />
        </>
      )}
    </div>
  );
}
```

(Token check: `bg-ink text-card` for the active pill — if those combinations don't exist in the token set, use the closest existing active-chip idiom from `TypeFilter` in `packages/ui`; never raw hex.)

- [ ] **Step 4: Verify + commit**

Run: `pnpm typecheck && pnpm lint && pnpm check:hex`

```bash
git add apps/web-agri/app/business/analytics apps/web-agri/lib/console-modules.ts
git commit -m "feat(d26): analytics console - stat tiles and by-pincode breakdowns"
```

---

### Task 15: Premium console page (tier selection, billing-aware)

**Files:**
- Create: `apps/web-agri/app/business/premium/page.tsx`, `apps/web-agri/app/business/premium/premium-client.tsx`
- Modify: `apps/web-agri/lib/console-modules.ts`
- Modify (small backend addition): `backend/core/modules/directory/router.py` + `backend/core/tests/test_tier_selection.py`

**Interfaces:**
- Consumes: `PUT /directory/businesses/{id}/tier-selection` (Task 2); NEW `GET /directory/businesses/{id}/tier-selection` → `TierSelectionOut` (owner-scoped read of current tier + intent — added here because the premium page must render persisted state on load); server-side billing probe (layout's `billingVisible()` pattern).
- Produces: registry entry `{ id: "premium", title: "Premium", href: "/business/premium" }` (after `analytics`; NOT billing-gated — visible while billing is dark, that's the point). Page passes `billingLive: boolean` to the client. Billing dark → tier cards with "Activates at launch" + selection persisted via tier-selection. Billing live → premium card links to `/business/billing` (checkout initiation is Pricing v1 per the D20 pre-flag-flip checklist; this page never POSTs to billing).

- [ ] **Step 1: Backend GET route + test** — in `router.py` next to the PUT:

```python
@router.get("/businesses/{business_id}/tier-selection")
async def get_tier_selection(
    request: Request, business_id: uuid.UUID, session: SessionDep
) -> TierSelectionOut:
    try:
        business = await service.get_owned_business(
            session, _principal_user_id(request), business_id
        )
    except service.BusinessNotFoundError as exc:
        raise HTTPException(status_code=404, detail="Business not found") from exc
    return TierSelectionOut(
        subscription_tier=business.subscription_tier,
        premium_requested_at=business.premium_requested_at,
    )
```

Add to `tests/test_tier_selection.py`:

```python
async def test_get_tier_selection_roundtrip(api: tuple[httpx.AsyncClient, AsyncSession]) -> None:
    http, session = api
    owner = uuid.uuid4()
    business_id = await _business(session, owner)
    await http.put(
        f"/directory/businesses/{business_id}/tier-selection",
        json={"tier": "premium"},
        headers=_as(owner),
    )
    response = await http.get(
        f"/directory/businesses/{business_id}/tier-selection", headers=_as(owner)
    )
    assert response.status_code == 200
    assert response.json()["premium_requested_at"] is not None


async def test_get_tier_selection_idor_404(api: tuple[httpx.AsyncClient, AsyncSession]) -> None:
    http, session = api
    business_id = await _business(session, uuid.uuid4())
    response = await http.get(
        f"/directory/businesses/{business_id}/tier-selection", headers=_as(uuid.uuid4())
    )
    assert response.status_code == 404
```

Run: `python -m pytest tests/test_tier_selection.py -q` → PASS.

- [ ] **Step 2: Registry entry** — append after `analytics`:

```typescript
  { id: "premium", title: "Premium", href: "/business/premium" },
```

- [ ] **Step 3: Page (server, billing probe)** — `apps/web-agri/app/business/premium/page.tsx`:

```tsx
import { redirect } from "next/navigation";

import { auth } from "@/lib/auth";

import { PremiumClient } from "./premium-client";

export const metadata = { title: "Premium", robots: { index: false } };

const API = process.env.API_BASE_URL ?? "http://127.0.0.1:8000";

async function billingLive(): Promise<boolean> {
  const token = await auth.getAccessToken();
  if (!token) return false;
  try {
    const response = await fetch(`${API}/billing/subscription`, {
      headers: { authorization: `Bearer ${token}` },
      cache: "no-store",
    });
    return response.status !== 404;
  } catch {
    return false;
  }
}

export default async function PremiumPage() {
  const user = await auth.getServerUser();
  if (!user) redirect("/api/auth/login?next=/business/premium");
  const live = await billingLive();
  return (
    <main className="mx-auto max-w-3xl px-4 py-6">
      <h1 className="font-display text-[20px] font-extrabold text-ink">Premium</h1>
      <PremiumClient billingLive={live} />
    </main>
  );
}
```

- [ ] **Step 4: Client** — `premium-client.tsx`:

```tsx
"use client";

import { Button, Card, EmptyState, Skeleton, cn } from "@agri/ui";
import Link from "next/link";
import { useEffect, useState, type ReactNode } from "react";

import { getJson, putJson } from "@/lib/api";

interface BusinessRef {
  id: string;
  name: string;
}

interface TierSelection {
  subscription_tier: "free" | "premium";
  premium_requested_at: string | null;
}

const FIELD =
  "mt-1 block min-h-[44px] w-full rounded-btn border border-line bg-card px-3 py-2 text-[13px] text-ink";
const LABEL = "block text-[13px] font-semibold text-ink";

function AlertNotice({ children }: { children: ReactNode }) {
  return (
    <div className="rounded-card border border-alert-line bg-alert-bg p-3 text-[13px] font-semibold text-ink">
      {children}
    </div>
  );
}

export function PremiumClient({ billingLive }: { billingLive: boolean }) {
  const [businesses, setBusinesses] = useState<BusinessRef[] | null>(null);
  const [loadError, setLoadError] = useState(false);
  const [selectedId, setSelectedId] = useState<string | null>(null);
  const [selection, setSelection] = useState<TierSelection | null>(null);
  const [saving, setSaving] = useState(false);
  const [saveError, setSaveError] = useState(false);

  useEffect(() => {
    void (async () => {
      try {
        const body = await getJson("/api/directory/businesses?limit=50");
        const list = (body.items as BusinessRef[] | undefined) ?? [];
        setBusinesses(list);
        if (list[0]) setSelectedId(list[0].id);
      } catch {
        setLoadError(true);
      }
    })();
  }, []);

  useEffect(() => {
    if (!selectedId) return;
    setSelection(null);
    void (async () => {
      try {
        const body = await getJson(`/api/directory/businesses/${selectedId}/tier-selection`);
        setSelection(body as unknown as TierSelection);
      } catch {
        setSelection(null);
      }
    })();
  }, [selectedId]);

  const select = async (tier: "free" | "premium") => {
    if (!selectedId) return;
    setSaving(true);
    setSaveError(false);
    try {
      const body = await putJson(`/api/directory/businesses/${selectedId}/tier-selection`, { tier });
      setSelection(body as unknown as TierSelection);
    } catch {
      setSaveError(true);
    } finally {
      setSaving(false);
    }
  };

  if (loadError) {
    return (
      <div className="mt-4">
        <AlertNotice>Could not load your businesses — please try again.</AlertNotice>
      </div>
    );
  }
  if (businesses === null) {
    return (
      <div className="mt-4 space-y-3">
        <Skeleton width="100%" height="44px" />
        <Skeleton width="100%" height="160px" />
      </div>
    );
  }
  if (businesses.length === 0) {
    return <EmptyState className="mt-4" icon="⭐" title="Create a listing first to go premium." />;
  }

  const isPremiumActive = selection?.subscription_tier === "premium";
  const premiumRequested = Boolean(selection?.premium_requested_at);

  return (
    <div className="mt-4 space-y-4">
      <label className={LABEL}>
        Business
        <select className={FIELD} value={selectedId ?? ""} onChange={(e) => setSelectedId(e.target.value)}>
          {businesses.map((b) => (
            <option key={b.id} value={b.id}>{b.name}</option>
          ))}
        </select>
      </label>

      {saveError ? <AlertNotice>Could not save your choice — please try again.</AlertNotice> : null}

      {selection === null ? (
        <Skeleton width="100%" height="160px" />
      ) : (
        <div className="grid gap-3 sm:grid-cols-2">
          <Card className={cn("space-y-2 p-4", !premiumRequested && !isPremiumActive && "border-ink")}>
            <p className="text-[13px] font-extrabold text-ink">Free</p>
            <p className="text-[13px] text-ink">Standard listing, leads inbox, analytics.</p>
            <Button
              type="button"
              variant="ghost"
              disabled={saving || (!premiumRequested && !isPremiumActive)}
              onClick={() => void select("free")}
            >
              {!premiumRequested && !isPremiumActive ? "Current plan" : "Switch to free"}
            </Button>
          </Card>

          <Card className={cn("space-y-2 p-4", (premiumRequested || isPremiumActive) && "border-ink")}>
            <div className="flex items-center justify-between">
              <p className="text-[13px] font-extrabold text-ink">Premium</p>
              {isPremiumActive ? (
                <span className="rounded-pill bg-verified-bg px-[9px] py-[3px] text-[11px] font-extrabold text-verified-fg">
                  Active
                </span>
              ) : premiumRequested ? (
                <span className="rounded-pill bg-sponsored-bg px-[9px] py-[3px] text-[11px] font-extrabold text-sponsored-fg">
                  Activates at launch
                </span>
              ) : null}
            </div>
            <p className="text-[13px] text-ink">
              Priority placement in search results — premium listings appear first for every pincode
              you cover.
            </p>
            {isPremiumActive ? (
              <p className="text-[12px] text-sub">Premium is active for this business.</p>
            ) : billingLive ? (
              <Link
                href="/business/billing"
                className="inline-block text-[13px] font-semibold text-ink underline"
              >
                Manage subscription
              </Link>
            ) : (
              <>
                <Button
                  type="button"
                  variant="brand"
                  disabled={saving || premiumRequested}
                  onClick={() => void select("premium")}
                >
                  {premiumRequested ? "Selected" : saving ? "Saving..." : "Choose premium"}
                </Button>
                <p className="text-[12px] text-sub">
                  Billing opens at launch — choosing now reserves premium and activates it then. No
                  charges today.
                </p>
              </>
            )}
          </Card>
        </div>
      )}
    </div>
  );
}
```

- [ ] **Step 5: Verify + commit**

Run: `pnpm typecheck && pnpm lint` and `python -m pytest tests/test_tier_selection.py -q` (from `backend/core`).

```bash
git add apps/web-agri/app/business/premium apps/web-agri/lib/console-modules.ts backend/core/modules/directory/router.py backend/core/tests/test_tier_selection.py
git commit -m "feat(d26): premium console - intent selection with activate-at-launch state"
```

---

### Task 16: View-beacon wiring on public profile pages

**Files:**
- Create: `apps/web-milk/app/directory/businesses/[slug]/view-beacon.tsx`
- Create: `apps/web-agri/app/directory/businesses/[slug]/view-beacon.tsx`
- Modify: both `[slug]/page.tsx` files (mount only)
- Modify: web-milk result-card links (pass browsing pincode as `?pin=`)

**Interfaces:**
- Consumes: `/api/view` relay (Task 10).
- Produces: `<ViewBeacon slug pincode?>` — a null-rendering client island that fires once per mount via `navigator.sendBeacon` (fetch keepalive fallback). web-milk passes the browsing pincode via a `?pin=641001` query param added to profile links on the `/[pincode]` results page; web-agri sends no pincode (no browsing context there).

- [ ] **Step 1: Create the beacon components** — TWO variants: web-agri gets the plain props variant below; web-milk gets the `useSearchParams` variant in Step 2 (its profile page is ISR and must not read `searchParams` server-side). Plain variant (`apps/web-agri/.../view-beacon.tsx`):

```tsx
"use client";

import { useEffect } from "react";

/** Fire-and-forget profile-view beacon (D26 analytics-lite). Renders
 * nothing; failures are silent by contract - a lost view is harmless. */
export function ViewBeacon({ slug, pincode }: { slug: string; pincode?: string | null }) {
  useEffect(() => {
    const payload = JSON.stringify({ slug, pincode: pincode ?? undefined });
    try {
      const sent = navigator.sendBeacon?.(
        "/api/view",
        new Blob([payload], { type: "application/json" }),
      );
      if (!sent) {
        void fetch("/api/view", {
          method: "POST",
          headers: { "content-type": "application/json" },
          body: payload,
          keepalive: true,
        }).catch(() => undefined);
      }
    } catch {
      // never surface beacon failures
    }
  }, [slug, pincode]);
  return null;
}
```

- [ ] **Step 2: Mount in web-milk profile page** — in `apps/web-milk/app/directory/businesses/[slug]/page.tsx`: the page is an async server component receiving `params` (and possibly `searchParams`). Add `searchParams` to the signature if absent (`searchParams: Promise<Record<string, string | string[] | undefined>>` in Next 15 style — match the file's existing `params` idiom), read `pin`, validate `/^\d{6}$/`, and render `<ViewBeacon slug={slug} pincode={pin} />` just inside the page's top-level fragment. ISR note: the beacon is a client island, so the static shell stays cacheable; `searchParams` usage forces dynamic rendering — if the page is currently ISR (`revalidate = 300`), do NOT read `searchParams` server-side; instead read the `pin` param inside `ViewBeacon` itself via `useSearchParams()` from `next/navigation` (client-side, no ISR impact) and drop the `pincode` prop in web-milk. Choose the `useSearchParams` variant if `export const revalidate` exists in the page.

`useSearchParams` variant of the component (web-milk only):

```tsx
"use client";

import { useSearchParams } from "next/navigation";
import { useEffect } from "react";

export function ViewBeacon({ slug }: { slug: string }) {
  const searchParams = useSearchParams();
  const pin = searchParams.get("pin") ?? undefined;
  useEffect(() => {
    const pincode = pin && /^\d{6}$/.test(pin) ? pin : undefined;
    const payload = JSON.stringify({ slug, pincode });
    try {
      const sent = navigator.sendBeacon?.(
        "/api/view",
        new Blob([payload], { type: "application/json" }),
      );
      if (!sent) {
        void fetch("/api/view", {
          method: "POST",
          headers: { "content-type": "application/json" },
          body: payload,
          keepalive: true,
        }).catch(() => undefined);
      }
    } catch {
      // silent by contract
    }
  }, [slug, pin]);
  return null;
}
```

(`useSearchParams` requires a `<Suspense>` boundary in static pages — wrap the mount: `<Suspense fallback={null}><ViewBeacon slug={slug} /></Suspense>`.)

- [ ] **Step 3: Pass the pincode from web-milk results** — in the `/[pincode]` results components (`apps/web-milk/app/[pincode]/` — the vendor card link to `/directory/businesses/{slug}`), append `?pin=${pincode}` to the href. Find the exact link component with `grep -rn "directory/businesses/" apps/web-milk/app/[pincode]`.

- [ ] **Step 4: Mount in web-agri directory page** — `apps/web-agri/app/directory/businesses/[slug]/page.tsx`: `<ViewBeacon slug={slug} />` (plain variant, no pincode).

- [ ] **Step 5: Verify + commit**

Run: `pnpm typecheck && pnpm lint`. Manual check (optional but recommended): `pnpm dev`, open a business profile on web-milk, confirm a `directory.profile_views` row appears (`psql` on port 55432) and NO layout shift.

```bash
git add apps/web-milk/app/directory/businesses apps/web-agri/app/directory/businesses "apps/web-milk/app/[pincode]"
git commit -m "feat(d26): profile-view beacons on public vendor pages"
```

---

### Task 17: E2E console walk + full gates

**Files:**
- Create: `e2e/vendor-dashboard.spec.ts`

**Interfaces:**
- Consumes: `completeLoginResilient` + helpers from `e2e/post-need.spec.ts` (D25) — import or copy the resilient-login pattern (hydration-race refill, new-user handle "Skip for now" + language tile steps); root config `e2e/playwright.config.ts` (webServers for 3000/3001/3003/8000).
- Produces: one spec covering the DoD walk: login (web-agri, port 3000) → listings: create business + save coverage 641001 → premium: choose premium → "Activates at launch" chip persists after reload → analytics renders zero-state tiles → inbox loads. Products form is exercised only if the dev seed ships an active vertical schema (`GET /catalog/verticals` non-empty) — skip that section gracefully otherwise (log a skip, don't fail).

- [ ] **Step 1: Write the spec** — `e2e/vendor-dashboard.spec.ts`. Structure (use exact selectors from the components built above — label text, button text):

```typescript
import { expect, test } from "@playwright/test";

// Reuse the D25 login helper pattern (e2e/post-need.spec.ts): resilient
// phone fill (dev-JIT hydration race), fresh phones walk handle-skip +
// language steps. Copy the helper if it isn't exported.

const AGRI = "http://127.0.0.1:3000";

test.describe("vendor dashboard (D26)", () => {
  test("console walk: listing -> coverage -> premium intent -> analytics", async ({ page }) => {
    test.setTimeout(180_000);
    const phone = `+9163743${Math.floor(100000 + Math.random() * 899999)}`;
    await loginResilient(page, AGRI, phone); // copied helper

    // Listings: create
    await page.goto(`${AGRI}/business/listings`);
    await page.getByLabel("Business name").fill("E2E Dairy");
    await page.getByLabel("Primary pincode").fill("641001");
    await page.getByRole("button", { name: "Create listing" }).click();
    await expect(page.getByLabel("Business")).toBeVisible({ timeout: 15_000 });

    // Coverage: add + save
    await page.getByLabel("Add pincode").fill("641001");
    await page.getByRole("button", { name: "Add", exact: true }).click();
    await page.getByRole("button", { name: "Save coverage" }).click();
    await expect(page.getByText("Coverage saved", { exact: false })).toBeVisible({
      timeout: 15_000,
    });

    // Premium: choose intent, survives reload
    await page.goto(`${AGRI}/business/premium`);
    await page.getByRole("button", { name: "Choose premium" }).click();
    await expect(page.getByText("Activates at launch")).toBeVisible({ timeout: 15_000 });
    await page.reload();
    await expect(page.getByText("Activates at launch")).toBeVisible({ timeout: 15_000 });

    // Analytics: zero-state renders
    await page.goto(`${AGRI}/business/analytics`);
    await expect(page.getByText("Profile views")).toBeVisible({ timeout: 15_000 });

    // Inbox: loads without error
    await page.goto(`${AGRI}/business/inbox`);
    await expect(page.getByText("No leads yet.").or(page.getByText("lead"))).toBeVisible({
      timeout: 15_000,
    });
  });
});
```

E2E environment traps (from D24/D25 — apply before running): kill listeners on ports 3000/3001/3003/8000; stop the `agri-dev-api-1` docker container (it squats :8000 and skips the migrate+seed bootstrap); run via `pnpm run e2e e2e/vendor-dashboard.spec.ts` (bare `pnpm exec playwright test` finds no config); clear `apps/web-milk/.next/cache/fetch-cache` if seed data changed; the `agri_sid` cookie is Secure — any request-context API call needs the explicit `cookie:` header trick.

- [ ] **Step 2: Run the spec** — `pnpm run e2e e2e/vendor-dashboard.spec.ts`
Expected: PASS. Iterate on selectors/timeouts as needed (the components are ours — prefer fixing an ambiguous label in the component over a brittle selector).

- [ ] **Step 3: Full gate sweep**

```bash
cd backend/core && ruff format --check . && ruff check . && mypy . && lint-imports && python scripts/dump_public_routes.py --check && python -m pytest -m "not slow" -q
cd ../.. && pnpm typecheck && pnpm lint && pnpm check:hex && pnpm run e2e e2e/vendor-dashboard.spec.ts
```

Expected: everything green.

- [ ] **Step 4: Commit**

```bash
git add e2e/vendor-dashboard.spec.ts
git commit -m "test(d26): vendor dashboard console-walk e2e"
```

---

### Task 18: Docs — flag-flip runbook, module doc regen

**Files:**
- Create: `docs/runbooks/billing-flag-flip.md`
- Modify: `backend/core/scripts/gen_module_claude.py` (directory module blurb) + regenerate

**Interfaces:**
- Produces: the PRE-FLAG-FLIP checklist as a durable runbook (it currently lives only in PR #29 notes) including the NEW D26 line; regenerated `modules/directory/CLAUDE.md` mentioning tier-selection/analytics/view-beacon surfaces.

- [ ] **Step 1: Write the runbook** — `docs/runbooks/billing-flag-flip.md`:

```markdown
# Billing flag flip (billing_enabled) — pre-flight checklist

The `billing_enabled` DB flag turns the entire /billing surface on without a
deploy (request-time 404s while off). Do NOT flip it in prod before every box
below is checked. Source: PR #29 notes (D20) + D26 additions.

## From D20 (PR #29)
- [ ] Webhook rate-limit carve-out or 429 alerting (shared per-IP 60/min
      bucket vs Razorpay egress IPs).
- [ ] Checkout-initiation UI shipped (Pricing v1 — POST /billing/subscriptions
      + hosted short_url exist backend-only today).
- [ ] Razorpay creds + plan ids present in env.
- [ ] Reconcile fetch-failure counting + invoice-loop bounding reviewed.

## Added by D26 (premium tier)
- [ ] Billing → directory tier sync exists: an ACTIVE subscription must set
      `directory.businesses.subscription_tier = 'premium'` and a
      cancel/terminal-dunning transition must set it back to `'free'`
      (event consumer or explicit ops step). Until that ships, activation is
      manual: `POST /admin/directory/businesses/{id}/tier` (role-gated,
      audited as `directory.tier_set`).
- [ ] Vendors with recorded intent (`businesses.premium_requested_at IS NOT
      NULL`) get activated (and charged only per their consent flow) at
      launch — the "activate at launch" promise made by the premium console
      page.
- [ ] Note: billing tiers are `growth|pro`; the directory field is
      `free|premium`. The sync must define the mapping (any live paid tier →
      premium).
```

- [ ] **Step 2: Regenerate the directory module doc** — edit the directory blurb in `backend/core/scripts/gen_module_claude.py` to append (matching its prose style): "D26 adds owner tier-selection (intent only; subscription_tier is admin-set via /admin/directory .../tier, audited), premium-first covers() ordering, a public profile-view beacon (/directory/businesses/{slug}/view, daily-rotating pseudonym, append-only), and owner analytics (/directory/businesses/{id}/analytics)." Then run the generator (check its header for the exact invocation, typically `python scripts/gen_module_claude.py` from `backend/core`) and commit the regenerated `modules/directory/CLAUDE.md`.

- [ ] **Step 3: Commit**

```bash
git add docs/runbooks/billing-flag-flip.md backend/core/scripts/gen_module_claude.py backend/core/modules/directory/CLAUDE.md
git commit -m "docs(d26): billing flag-flip runbook + directory module doc regen"
```

---

## Completion

After all tasks: push the branch and open the PR to dev titled exactly `feat(d26): vendor dashboard` (set the title explicitly — auto-titles from branch names fail the conventional-commits gate). PR body: DoD evidence (owner-scoped + premium-sort + coverage-edit test names), the design doc link, accepted debt (billing→tier sync deferred to flag-flip runbook; view beacon has no bot filtering beyond rate-limit + dedupe; coverage editor is whole-list PUT). Note: if the GitHub Actions monthly quota is still exhausted (D24/D25 situation), stop after pushing and hand the PR to the owner per `never-delete-remote-branches` / owner-merge precedent.


