# D18 Reviews + Leads Engine Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Two shared engines — polymorphic moderated reviews (coin-hooked via `review.approved` event, 5/week cap) and a lead-gen engine (contact + milk_subscription inquiries routed by coverage(pincode)×category to business inboxes) — plus login-gated, daily-capped, DPDP-logged contact reveal that removes raw phones from the public API.

**Architecture:** Both engines live **inside `modules/directory`** (D17 catalog-in-directory precedent): the import-linter independence contract forbids a separate module from importing `covers()`/`get_owned_business()`, and lead routing + review-target validation need both. Review tables go in the `directory` Postgres schema; lead tables go in the pre-existing `leads` schema (already covered by 0013 default app_rt privileges). All D18 events publish on the existing `"directory"` Redis stream (coins + notify already subscribe to it), commit-first/best-effort. The `modules/leads` stub stays untouched — its CLAUDE.md reserves it for E4 buy/sell intent matchmaking, a different future feature.

**Tech Stack:** FastAPI + SQLAlchemy async (Postgres, Alembic), Redis (caps + event streams), Next.js App Router (web-agri, web-admin), `@agri/auth-client` BFF pattern, `@agri/ui` tokens-only design system.

## Global Constraints

- Branch `feat/d18-reviews-leads` (already checked out), conventional commits, PR targets `dev`, final title `feat(d18): reviews + leads`. NEVER commit to dev/main.
- All backend commands run from `backend/core`. Local gates before push: `ruff format --check .` && `ruff check .` && `mypy .` && `lint-imports` && `pytest -q -m "not slow"`. Run `ruff format .` after each task (D16 lesson: format per task, not at the end).
- `python scripts/migrate_check.py` WIPES the target DB (upgrade→downgrade→upgrade). Only run it with `ALEMBIC_DATABASE_URL` pointed at a throwaway DB (e.g. `agri_test`), never dev data.
- Postgres dev port is **55432**, test fixtures create/drop `agri_test` and connect as `app_rt` (missing grants surface as test failures). Redis test DB 9; tests skip visibly if either is down.
- Every migration needs a `# -- THREAT/NOTES:` comment block and a working `downgrade()`.
- No OFFSET pagination anywhere (test-gated). Every list endpoint is cursor-paginated.
- Every `public=True` route must be added to `backend/core/public_routes.txt` in the same PR (CI diffs it).
- Reviews default `pending` — no auto-publish path. Contact reveal NEVER bypasses the cap. No payment fields in leads.
- Never log request bodies, query strings, or phone numbers — not even relying on the shared/telemetry.py scrubber (it is the last line of defence, not a licence).
- Frontend: tokens only (no raw hex), `min-h-[44px]`/`.tap-target` on interactive elements, design law "Call > chat > form" (reveal buttons lead, inquiry form is the fallback). web-agri has NO `ToastProvider` in its root layout — use inline status state like `claim-form.tsx`, not `useToast`.
- Non-negotiables (each needs a test): 1) one review per user per target + pending default; 2) `review_approved` coins capped 5/week; 3) reveal cap enforced + reveal logged without plaintext phone; 4) lead routes only to businesses covering the pincode (test with 641001).

## Decisions locked by this plan (spec left them open)

1. **Reviews module/schema:** `modules/directory` files `reviews_*.py`, tables in schema `directory` (spec allows "schema directory or reviews"; avoids a brand-new schema + grant surface).
2. **Leads module/schema:** `modules/directory` files `leads_*.py`, tables in schema `leads` (spec mandates schema `leads`; module co-location is forced by import-linter independence).
3. **`vendor` target_type:** there is no vendor table — `target_type='vendor'` points `target_id` at a `directory.businesses` row and validation additionally requires `type='vendor'`. `'business'` accepts any active business.
4. **Routing semantics:** `POST /leads/inquiries` takes optional `business_id`. If provided, the business must cover the pincode (else 422 `business_not_covered`). If omitted, route to the **nearest** covering business (covers() distance order), filtered by `category` when given; none → 422 `no_coverage`. One inquiry row → one business inbox (no fan-out: fan-out amplifies guest spam).
5. **Event stream:** all three events (`review.approved`, `lead.created`, `lead.responded`) publish on stream `"directory"` — the producing module is directory, and coins + notify already consume that stream (zero STREAMS changes).
6. **Coins idem key:** worker builds literal `review:{review_id}` (spec-mandated, mirrors `claim:{business_id}`). Rule `review_approved`: amount **20**, `weekly_cap=5` (amount tunable later via `PUT /admin/coins/rules/review_approved`).
7. **Guest attribution:** new `optional_auth` dependency in `shared/security.py` — resolves a principal when credentials are present, never 401s. Used only by the guest-capable inquiry POST (which is `public=True`).
8. **Reveal cap:** Redis `INCR` fixed daily window, **fail-closed** (Redis down → 503, OTP-throttle precedent, because this is a scraping defence). Default cap 10/day via new setting `contact_reveal_daily_cap`. Reveal log rows are append-only by grant (REVOKE UPDATE/DELETE, audit-table precedent) and contain IDs only — never the phone.

## File structure

Backend (all under `backend/core/`):
- Create: `modules/directory/reviews_models.py`, `reviews_schemas.py`, `reviews_service.py`, `reviews_router.py`, `reviews_admin_router.py`
- Create: `modules/directory/leads_models.py`, `leads_schemas.py`, `leads_service.py`, `leads_router.py`, `modules/directory/reveal.py`
- Create: `alembic/versions/0019_reviews_v1.py`, `alembic/versions/0020_leads_v1.py`
- Modify: `modules/directory/covers.py` (optional category filter), `modules/directory/router.py` + `schemas.py` (public phone strip + reveal route), `modules/coins/worker.py`, `modules/coins/reason_codes.py`, `modules/notify/consumers.py`, `shared/security.py` (`optional_auth`), `settings.py`, `main.py`, `public_routes.txt`
- Tests: `tests/test_reviews_router.py`, `tests/test_reviews_moderation.py`, `tests/test_leads_routing.py`, `tests/test_leads_router.py`, `tests/test_contact_reveal.py`; modify `tests/test_coins_worker.py`, `tests/test_notify_consumers.py`, `tests/test_telemetry.py`, `tests/test_directory_router.py`

Frontend:
- Create: `apps/web-agri/app/api/reviews/[...path]/route.ts`, `apps/web-agri/app/api/leads/[...path]/route.ts`
- Create: `apps/web-agri/app/directory/businesses/[slug]/reveal-contact.tsx`, `lead-form.tsx`, `review-form.tsx`, `reviews-section.tsx`
- Modify: `apps/web-agri/app/directory/businesses/[slug]/page.tsx`
- Create: `apps/web-agri/app/account/inquiries/page.tsx` + `inquiries-client.tsx`, `apps/web-agri/app/business/inbox/page.tsx` + `inbox-client.tsx`
- Create: `apps/web-admin/app/reviews/page.tsx` + `reviews-manager.tsx`

---

### Task 1: Reviews models + migration 0019 (tables, coins rule, notify templates)

**Files:**
- Create: `backend/core/modules/directory/reviews_models.py`
- Create: `backend/core/alembic/versions/0019_reviews_v1.py`
- Modify: `backend/core/modules/coins/reason_codes.py`

**Interfaces:**
- Produces: `Review` (cols: `id`, `author_user_id: UUID`, `target_type: str`, `target_id: UUID`, `rating: int`, `body: Translated | None`, `moderation_status: str` [UGCMixin, default pending], timestamps), `RatingAggregate` (`target_type`, `target_id`, `rating_avg: Decimal`, `rating_count: int`), enum `review_target_type` in schema `directory`. Coins rule row `review_approved` (amount 20, weekly_cap 5). Notify templates `review_approved` ×3 locales.

- [ ] **Step 1: Write `reviews_models.py`**

```python
"""Reviews engine ORM (D18.A): polymorphic reviews + cached rating aggregates.

target_id is a plain UUID (never an FK): 'business'/'vendor' point at
directory.businesses, 'product' at directory.products - validated in
reviews_service, matching the repo-wide no-cross-FK convention.
"""

import uuid
from decimal import Decimal

from sqlalchemy import CheckConstraint, Index, Integer, Numeric, SmallInteger, UniqueConstraint
from sqlalchemy.dialects import postgresql
from sqlalchemy.orm import Mapped, mapped_column

from shared.db import Base, TimestampMixin, UGCMixin, UUIDv7PKMixin
from shared.i18n import Translated, TranslatedString

review_target_enum = postgresql.ENUM(
    "business", "product", "vendor",
    name="review_target_type", schema="directory", create_type=False,
)


class Review(UUIDv7PKMixin, TimestampMixin, UGCMixin, Base):
    __tablename__ = "reviews"
    __table_args__ = (
        # one review per user per target (D18 non-negotiable 1)
        UniqueConstraint(
            "author_user_id", "target_type", "target_id",
            name="uq_directory_reviews_one_per_target",
        ),
        CheckConstraint("rating BETWEEN 1 AND 5", name="rating_1_5"),
        Index("ix_directory_reviews_target_status_id", "target_type", "target_id", "moderation_status", "id"),
        Index("ix_directory_reviews_moderation_status_id", "moderation_status", "id"),
        {"schema": "directory"},
    )

    author_user_id: Mapped[uuid.UUID] = mapped_column(
        postgresql.UUID(as_uuid=True), nullable=False, index=True
    )
    target_type: Mapped[str] = mapped_column(review_target_enum, nullable=False)
    target_id: Mapped[uuid.UUID] = mapped_column(postgresql.UUID(as_uuid=True), nullable=False)
    rating: Mapped[int] = mapped_column(SmallInteger, nullable=False)
    body: Mapped[Translated | None] = mapped_column(TranslatedString, nullable=True)


class RatingAggregate(UUIDv7PKMixin, TimestampMixin, Base):
    """Cached avg+count per target, recomputed on every moderation decision."""

    __tablename__ = "rating_aggregates"
    __table_args__ = (
        UniqueConstraint("target_type", "target_id", name="uq_directory_rating_aggregates_target"),
        {"schema": "directory"},
    )

    target_type: Mapped[str] = mapped_column(review_target_enum, nullable=False)
    target_id: Mapped[uuid.UUID] = mapped_column(postgresql.UUID(as_uuid=True), nullable=False)
    rating_avg: Mapped[Decimal] = mapped_column(Numeric(3, 2), nullable=False)
    rating_count: Mapped[int] = mapped_column(Integer, nullable=False)
```

- [ ] **Step 2: Write migration `0019_reviews_v1.py`**

Model on `0017_claims_v1.py` (enum creation, seed tables, THREAT block). `revision = "0019"`, `down_revision = "0018"`. Upgrade body:

```python
"""reviews v1: polymorphic reviews + rating aggregates + review_approved coin rule.

Revision ID: 0019
Revises: 0018
"""

import sqlalchemy as sa
import uuid6
from alembic import op
from sqlalchemy.dialects import postgresql

from shared.migrations import pk_column, timestamp_columns, ugc_column

revision = "0019"
down_revision = "0018"
branch_labels = None
depends_on = None

# -- THREAT/NOTES:
# - downgrade drops reviews + rating_aggregates (review content loss) and
#   deletes the review_approved coins rule + notify templates; ledger entries
#   already awarded are NOT clawed back (immutable ledger by trigger).
# - review_approved seeds weekly_cap=5 - first rule to exercise the
#   check_numeric_caps weekly window (D18 non-negotiable 2).
# - no table rewrites; enum + create_table only, safe online.

_uuid = postgresql.UUID(as_uuid=True)

target_enum = postgresql.ENUM(
    "business", "product", "vendor", name="review_target_type", schema="directory"
)

channel_enum = postgresql.ENUM(
    "in_app", "sms", "email", name="notify_channel", schema="notify", create_type=False
)
locale_enum = postgresql.ENUM(
    "en", "ta", "hi", name="notify_locale", schema="notify", create_type=False
)

templates_table = sa.table(
    "templates",
    sa.column("id", _uuid), sa.column("key", sa.Text),
    sa.column("channel", channel_enum), sa.column("locale", locale_enum),
    sa.column("subject", sa.Text), sa.column("body", sa.Text),
    schema="notify",
)

rules_table = sa.table(
    "rules",
    sa.column("code", sa.Text), sa.column("amount", sa.BigInteger),
    sa.column("daily_cap", sa.Integer), sa.column("weekly_cap", sa.Integer),
    sa.column("total_cap", sa.Integer),
    schema="coins",
)

# every key ships en+ta+hi (CI gate); template has no {var} placeholders
SEED_TEMPLATES: list[tuple[str, str, str]] = [
    ("review_approved", "en", "Your review is approved and now visible."),
    ("review_approved", "ta", "உங்கள் மதிப்புரை அங்கீகரிக்கப்பட்டு இப்போது காட்டப்படுகிறது."),
    ("review_approved", "hi", "आपकी समीक्षा स्वीकृत हो गई है और अब दिखाई दे रही है."),
]


def upgrade() -> None:
    bind = op.get_bind()
    target_enum.create(bind, checkfirst=True)
    target_col = postgresql.ENUM(
        name="review_target_type", schema="directory", create_type=False
    )

    op.create_table(
        "reviews",
        pk_column(),
        sa.Column("author_user_id", _uuid, nullable=False),
        sa.Column("target_type", target_col, nullable=False),
        sa.Column("target_id", _uuid, nullable=False),
        sa.Column("rating", sa.SmallInteger, nullable=False),
        sa.Column("body", postgresql.JSONB, nullable=True),
        ugc_column(),
        *timestamp_columns(),
        sa.CheckConstraint("rating BETWEEN 1 AND 5", name="rating_1_5"),
        sa.UniqueConstraint(
            "author_user_id", "target_type", "target_id",
            name="uq_directory_reviews_one_per_target",
        ),
        schema="directory",
    )
    op.create_index("ix_directory_reviews_author_user_id", "reviews", ["author_user_id"], schema="directory")
    op.create_index(
        "ix_directory_reviews_target_status_id", "reviews",
        ["target_type", "target_id", "moderation_status", "id"], schema="directory",
    )
    op.create_index(
        "ix_directory_reviews_moderation_status_id", "reviews",
        ["moderation_status", "id"], schema="directory",
    )

    op.create_table(
        "rating_aggregates",
        pk_column(),
        sa.Column("target_type", target_col, nullable=False),
        sa.Column("target_id", _uuid, nullable=False),
        sa.Column("rating_avg", sa.Numeric(3, 2), nullable=False),
        sa.Column("rating_count", sa.Integer, nullable=False),
        *timestamp_columns(),
        sa.UniqueConstraint("target_type", "target_id", name="uq_directory_rating_aggregates_target"),
        schema="directory",
    )

    # 0013's ALTER DEFAULT PRIVILEGES already covers new directory tables;
    # explicit grant keeps the app_rt profile reviewable here (0018 precedent).
    op.execute('GRANT SELECT, INSERT, UPDATE, DELETE ON ALL TABLES IN SCHEMA "directory" TO app_rt')

    op.bulk_insert(
        rules_table,
        [{"code": "review_approved", "amount": 20,
          "daily_cap": None, "weekly_cap": 5, "total_cap": None}],
    )
    op.bulk_insert(
        templates_table,
        [{"id": uuid6.uuid7(), "key": key, "channel": "in_app",
          "locale": locale, "subject": None, "body": body}
         for (key, locale, body) in SEED_TEMPLATES],
    )


def downgrade() -> None:
    bind = op.get_bind()
    op.execute("DELETE FROM notify.templates WHERE key = 'review_approved'")
    op.execute("DELETE FROM coins.rules WHERE code = 'review_approved'")
    op.drop_table("rating_aggregates", schema="directory")
    op.drop_table("reviews", schema="directory")
    sa.Enum(name="review_target_type", schema="directory").drop(bind, checkfirst=True)
```

Check `shared/migrations.py` for the exact `pk_column()` / `timestamp_columns()` / `ugc_column()` signatures before writing (adjust if they take arguments); check how `0018_catalog_v1.py` invoked them and mirror.

- [ ] **Step 3: Add the reason label** — in `backend/core/modules/coins/reason_codes.py`, add to `REASON_LABEL_KEYS`:

```python
"review_approved": "coins.reason.review_approved",
```

(D16 forgot `business_claim`'s label; do not repeat that. If the dict now shows `business_claim` still missing, leave it — out of D18 scope.)

- [ ] **Step 4: Run migration against the test DB and the model import**

```
cd backend/core
ALEMBIC_DATABASE_URL=postgresql+psycopg://<admin-creds>@localhost:55432/agri_test python -m alembic upgrade head
python -c "from modules.directory.reviews_models import Review, RatingAggregate; print('ok')"
```

(Or simply run any single pytest test — the `database_url` fixture re-migrates `agri_test` from scratch and will fail loudly if 0019 is broken: `pytest -q tests/test_coins_migration.py`.)
Expected: upgrade applies cleanly; import prints ok.

- [ ] **Step 5: Verify downgrade round-trip** (throwaway DB only):

```
ALEMBIC_DATABASE_URL=postgresql+psycopg://<admin-creds>@localhost:55432/agri_test python scripts/migrate_check.py
```

Expected: `upgrade head` → `downgrade base` → `upgrade head` all succeed.

- [ ] **Step 6: Commit**

```bash
git add modules/directory/reviews_models.py alembic/versions/0019_reviews_v1.py modules/coins/reason_codes.py
git commit -m "feat(d18): reviews tables + review_approved coin rule (weekly cap 5)"
```

---

### Task 2: Reviews service + public/authorized router

**Files:**
- Create: `backend/core/modules/directory/reviews_schemas.py`, `reviews_service.py`, `reviews_router.py`
- Modify: `backend/core/main.py`, `backend/core/public_routes.txt`
- Test: `backend/core/tests/test_reviews_router.py`

**Interfaces:**
- Consumes: `Review`, `RatingAggregate` (Task 1); `Business`, `Product` from `modules.directory.models`/`catalog_models`; `paginate` from `shared.pagination`.
- Produces (used by Tasks 3, 11):
  - `reviews_service.create_review(session, *, author_user_id: uuid.UUID, target_type: str, target_id: uuid.UUID, rating: int, body: dict[str, str] | None) -> Review` — raises `TargetNotFoundError`, `ReviewExistsError`
  - `reviews_service.list_public(session, *, target_type: str, target_id: uuid.UUID, cursor: str | None, limit: int) -> Page[Review]`
  - `reviews_service.get_summary(session, *, target_type: str, target_id: uuid.UUID) -> tuple[Decimal | None, int]`
  - `reviews_service.recompute_aggregate(session, *, target_type: str, target_id: uuid.UUID) -> None`
  - Routes: `POST /reviews` (auth, 201), `GET /reviews?target_type&target_id` (public), `GET /reviews/summary?target_type&target_id` (public)

- [ ] **Step 1: Write the failing tests** — `tests/test_reviews_router.py`. Copy the app/fixture scaffold from `tests/test_directory_router.py:36-61` verbatim (`_Principal` with `roles=("user",)`, `x-test-user` header resolver, `app.dependency_overrides[get_session]`, `register_principal_resolver`). Helper to seed a business directly via ORM:

```python
async def _mk_business(session, *, owner=None, btype="shop", status="active") -> Business:
    b = Business(owner_user_id=owner, name="Agri Shop", type=btype,
                 status=status, primary_pincode="641001", slug=f"agri-{uuid.uuid4().hex[:8]}")
    session.add(b)
    await session.flush()
    return b
```

(Adjust constructor kwargs to whatever `tests/test_directory_router.py` actually uses to create businesses — mirror it exactly.) Tests:

```python
async def test_post_review_requires_auth(client, db_session):
    # no x-test-user header -> 401
    resp = await client.post("/reviews", json={...})
    assert resp.status_code == 401

async def test_post_review_defaults_pending(client, db_session):
    b = await _mk_business(db_session)
    resp = await client.post("/reviews", headers=_auth(u1), json={
        "target_type": "business", "target_id": str(b.id),
        "rating": 4, "body": {"en": "Good service"}})
    assert resp.status_code == 201
    assert resp.json()["moderation_status"] == "pending"   # non-negotiable 1b

async def test_one_review_per_user_per_target(client, db_session):
    # same user + same target twice -> 409; different user -> 201
    ... assert second.status_code == 409

async def test_rating_bounds(client, db_session):
    # rating 0 and 6 -> 422

async def test_unknown_target_404(client, db_session):
    # random target_id -> 404

async def test_vendor_target_requires_vendor_type(client, db_session):
    # business with type='shop' reviewed as target_type='vendor' -> 404
    # business with type='vendor' -> 201

async def test_product_target_must_be_approved(client, db_session):
    # product with moderation_status='pending' -> 404; approved product -> 201

async def test_public_list_shows_only_approved(client, db_session):
    # seed one pending + one approved review (set moderation_status directly),
    # GET /reviews?target_type=business&target_id=... without auth header
    # -> 200, only the approved one; envelope has items + next_cursor

async def test_summary_math(client, db_session):
    # approve reviews rated 4 and 5 via reviews_service.moderate is Task 3;
    # here: insert two approved Review rows directly, call
    # reviews_service.recompute_aggregate, then GET /reviews/summary
    # -> {"rating_avg": "4.50", "rating_count": 2}; unknown target -> avg None, count 0
```

- [ ] **Step 2: Run tests, verify they fail** — `pytest -q tests/test_reviews_router.py` → import errors / 404s (router not registered).

- [ ] **Step 3: Write `reviews_schemas.py`**

```python
"""Reviews API request/response schemas (D18.A)."""

import uuid
from datetime import datetime
from decimal import Decimal
from typing import Literal

from pydantic import BaseModel, Field

ReviewTargetType = Literal["business", "product", "vendor"]


class ReviewCreateIn(BaseModel):
    target_type: ReviewTargetType
    target_id: uuid.UUID
    rating: int = Field(ge=1, le=5)
    body: dict[str, str] | None = None


class ReviewOut(BaseModel):
    id: uuid.UUID
    author_user_id: uuid.UUID
    target_type: str
    target_id: uuid.UUID
    rating: int
    body: dict[str, str] | None
    moderation_status: str
    created_at: datetime


class ReviewPageOut(BaseModel):
    items: list[ReviewOut]
    next_cursor: str | None


class RatingSummaryOut(BaseModel):
    target_type: str
    target_id: uuid.UUID
    rating_avg: Decimal | None
    rating_count: int


class AdminReviewPageOut(BaseModel):
    items: list[ReviewOut]
    next_cursor: str | None
```

- [ ] **Step 4: Write `reviews_service.py`**

```python
"""Reviews engine service (D18.A). Target validation + aggregates live here;
the router maps errors to HTTP statuses."""

import uuid
from decimal import Decimal

from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from modules.directory.catalog_models import Product
from modules.directory.models import Business
from modules.directory.reviews_models import RatingAggregate, Review
from shared.i18n import Translated
from shared.pagination import Page, paginate


class ReviewsError(Exception):
    pass


class TargetNotFoundError(ReviewsError):
    pass


class ReviewExistsError(ReviewsError):
    pass


class ReviewDecisionConflictError(ReviewsError):
    pass


class ReviewNotFoundError(ReviewsError):
    pass


async def _target_exists(session: AsyncSession, target_type: str, target_id: uuid.UUID) -> bool:
    if target_type in ("business", "vendor"):
        query = select(Business.id).where(Business.id == target_id, Business.status == "active")
        if target_type == "vendor":
            query = query.where(Business.type == "vendor")
        return (await session.scalar(query)) is not None
    query = select(Product.id).where(
        Product.id == target_id,
        Product.status == "active",
        Product.moderation_status == "approved",
    )
    return (await session.scalar(query)) is not None


async def create_review(
    session: AsyncSession,
    *,
    author_user_id: uuid.UUID,
    target_type: str,
    target_id: uuid.UUID,
    rating: int,
    body: dict[str, str] | None,
) -> Review:
    if not await _target_exists(session, target_type, target_id):
        raise TargetNotFoundError(str(target_id))
    review = Review(
        author_user_id=author_user_id,
        target_type=target_type,
        target_id=target_id,
        rating=rating,
        body=Translated.from_dict(body) if body else None,
    )
    sp = await session.begin_nested()
    try:
        session.add(review)
        await session.flush()
    except IntegrityError as exc:
        await sp.rollback()
        raise ReviewExistsError(str(target_id)) from exc
    await sp.commit()
    return review


async def list_public(
    session: AsyncSession,
    *,
    target_type: str,
    target_id: uuid.UUID,
    cursor: str | None = None,
    limit: int = 20,
) -> Page[Review]:
    query = select(Review).where(
        Review.target_type == target_type,
        Review.target_id == target_id,
        Review.moderation_status == "approved",
    )
    return await paginate(session, query, cursor=cursor, limit=limit, descending=True)


async def get_summary(
    session: AsyncSession, *, target_type: str, target_id: uuid.UUID
) -> tuple[Decimal | None, int]:
    agg = await session.scalar(
        select(RatingAggregate).where(
            RatingAggregate.target_type == target_type,
            RatingAggregate.target_id == target_id,
        )
    )
    if agg is None:
        return None, 0
    return agg.rating_avg, agg.rating_count


async def recompute_aggregate(
    session: AsyncSession, *, target_type: str, target_id: uuid.UUID
) -> None:
    avg, count = (
        await session.execute(
            select(func.avg(Review.rating), func.count()).where(
                Review.target_type == target_type,
                Review.target_id == target_id,
                Review.moderation_status == "approved",
            )
        )
    ).one()
    agg = await session.scalar(
        select(RatingAggregate).where(
            RatingAggregate.target_type == target_type,
            RatingAggregate.target_id == target_id,
        )
    )
    if not count:
        if agg is not None:
            await session.delete(agg)
        await session.flush()
        return
    rounded = Decimal(avg).quantize(Decimal("0.01"))
    if agg is None:
        session.add(
            RatingAggregate(
                target_type=target_type, target_id=target_id,
                rating_avg=rounded, rating_count=int(count),
            )
        )
    else:
        agg.rating_avg = rounded
        agg.rating_count = int(count)
    await session.flush()


async def list_for_moderation(
    session: AsyncSession, *, status: str, cursor: str | None = None, limit: int = 20
) -> Page[Review]:
    query = select(Review).where(Review.moderation_status == status)
    return await paginate(session, query, cursor=cursor, limit=limit)


async def moderate(session: AsyncSession, *, review_id: uuid.UUID, approve: bool) -> Review:
    review = await session.scalar(select(Review).where(Review.id == review_id))
    if review is None:
        raise ReviewNotFoundError(str(review_id))
    if review.moderation_status != "pending":
        raise ReviewDecisionConflictError(review.moderation_status)
    review.moderation_status = "approved" if approve else "rejected"
    await session.flush()
    return review
```

- [ ] **Step 5: Write `reviews_router.py`**

```python
"""Reviews API (D18.A). POST is login-gated (spam defence); reads are public
(keyset + rate limit are the scraping defence). Never log bodies - review
text is user content."""

import uuid
from typing import Annotated

from fastapi import Depends, HTTPException, Query, Request
from sqlalchemy.ext.asyncio import AsyncSession

from modules.directory import reviews_service
from modules.directory.reviews_models import Review
from modules.directory.reviews_schemas import (
    RatingSummaryOut,
    ReviewCreateIn,
    ReviewOut,
    ReviewPageOut,
    ReviewTargetType,
)
from shared.db import get_session
from shared.pagination import InvalidCursorError
from shared.security import SecureRouter

router = SecureRouter(prefix="/reviews", tags=["reviews"])

SessionDep = Annotated[AsyncSession, Depends(get_session)]
LimitQuery = Annotated[int, Query(ge=1, le=100)]


def _principal_user_id(request: Request) -> uuid.UUID:
    principal = request.state.principal  # set by require_auth (shared.security)
    user_id = principal.user_id
    assert isinstance(user_id, uuid.UUID)
    return user_id


def _review_out(review: Review) -> ReviewOut:
    return ReviewOut(
        id=review.id,
        author_user_id=review.author_user_id,
        target_type=review.target_type,
        target_id=review.target_id,
        rating=review.rating,
        body=review.body.to_dict() if review.body else None,
        moderation_status=review.moderation_status,
        created_at=review.created_at,
    )


@router.post("", status_code=201)
async def create_review(
    request: Request, body: ReviewCreateIn, session: SessionDep
) -> ReviewOut:
    try:
        review = await reviews_service.create_review(
            session,
            author_user_id=_principal_user_id(request),
            target_type=body.target_type,
            target_id=body.target_id,
            rating=body.rating,
            body=body.body,
        )
    except reviews_service.TargetNotFoundError as exc:
        raise HTTPException(status_code=404, detail="target not found") from exc
    except reviews_service.ReviewExistsError as exc:
        raise HTTPException(status_code=409, detail="review_exists") from exc
    except ValueError as exc:  # Translated.from_dict rejects unknown locales
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    await session.commit()
    return _review_out(review)


@router.get("", public=True)
async def list_reviews(
    session: SessionDep,
    target_type: ReviewTargetType,
    target_id: uuid.UUID,
    cursor: str | None = None,
    limit: LimitQuery = 20,
) -> ReviewPageOut:
    try:
        page = await reviews_service.list_public(
            session, target_type=target_type, target_id=target_id, cursor=cursor, limit=limit
        )
    except InvalidCursorError as exc:
        raise HTTPException(status_code=400, detail="invalid cursor") from exc
    return ReviewPageOut(
        items=[_review_out(r) for r in page.items], next_cursor=page.next_cursor
    )


@router.get("/summary", public=True)
async def rating_summary(
    session: SessionDep, target_type: ReviewTargetType, target_id: uuid.UUID
) -> RatingSummaryOut:
    avg, count = await reviews_service.get_summary(
        session, target_type=target_type, target_id=target_id
    )
    return RatingSummaryOut(
        target_type=target_type, target_id=target_id, rating_avg=avg, rating_count=count
    )
```

- [ ] **Step 6: Register + declare public routes.** In `main.py`, next to the directory imports: `from modules.directory.reviews_router import router as reviews_router` and add `reviews_router` to `MODULE_ROUTERS`. Append to `public_routes.txt`:

```
/reviews
/reviews/summary
```

- [ ] **Step 7: Run tests to verify they pass** — `pytest -q tests/test_reviews_router.py` → all PASS. Also `python scripts/dump_public_routes.py --check` → clean.

- [ ] **Step 8: Commit**

```bash
git add modules/directory/reviews_schemas.py modules/directory/reviews_service.py modules/directory/reviews_router.py main.py public_routes.txt tests/test_reviews_router.py
git commit -m "feat(d18): review submit + public list/summary (login-gated post, one per target)"
```

---

### Task 3: Review moderation admin router (approve → aggregate + audit + event)

**Files:**
- Create: `backend/core/modules/directory/reviews_admin_router.py`
- Modify: `backend/core/main.py`
- Test: `backend/core/tests/test_reviews_moderation.py`

**Interfaces:**
- Consumes: `reviews_service.list_for_moderation/moderate/recompute_aggregate` (Task 2), `shared.audit.audit`, `shared.events.publish`, `RejectIn` from `modules.directory.schemas`.
- Produces: `GET /admin/reviews?status=`, `POST /admin/reviews/{review_id}/approve`, `POST /admin/reviews/{review_id}/reject` (roles staff/super_admin). Event `review.approved` on stream `"directory"` with payload `{user_id, review_id, target_type, target_id, vars: {}}` (consumed in Task 4).

- [ ] **Step 1: Write the failing tests** — `tests/test_reviews_moderation.py`. Same scaffold as Task 2's test file, but the principal's roles come from the header (copy the roles-header trick from `tests/test_directory_admin*.py` / whatever the claims admin tests use — mirror it exactly; typically `x-test-roles: staff`). Monkeypatch the publisher to capture events:

```python
@pytest.fixture
def published(monkeypatch):
    events: list[tuple[str, str, dict]] = []
    async def _fake_publish(stream, event_type, payload):
        events.append((stream, event_type, payload))
        return "1-1"
    monkeypatch.setattr("modules.directory.reviews_admin_router.publish", _fake_publish)
    return events

async def test_moderation_requires_role(client, db_session):
    # plain user role -> 403 on GET list and POST approve

async def test_approve_flow(client, db_session, published):
    # pending review -> POST approve -> 200
    # review.moderation_status == "approved"
    # rating_aggregates row exists with count 1
    # audit entry action "reviews.review_approved" exists (query AuditEntry)
    # published == [("directory", "review.approved", {"user_id": ..., "review_id": ..., ...})]

async def test_reject_requires_note(client, db_session):
    # POST reject without body note -> 422; with note -> rejected, no event published

async def test_decide_only_from_pending(client, db_session):
    # approving an already-approved review -> 409

async def test_reject_after_approve_recomputes_nothing(client, db_session):
    # (guard) approve then attempt reject -> 409, aggregate unchanged
```

- [ ] **Step 2: Run tests, verify they fail** — `pytest -q tests/test_reviews_moderation.py`.

- [ ] **Step 3: Write `reviews_admin_router.py`** — copy the choreography of `modules/directory/admin_router.py` (role gate, audit-in-transaction, capture-payload-before-commit, commit-then-best-effort-publish):

```python
"""Review moderation queue (D18.A admin).

Auth is ROLE-gated, not permission-gated: modules.directory must never import
modules.identity (import-linter independence) - same trade-off as
modules/directory/admin_router.py and modules/coins/admin_router.py.

Choreography per decision (D16 precedent): decide -> audit (same tx) ->
capture event payload -> commit -> best-effort publish. An event for a
rolled-back decision must never exist; a Redis blip must never roll back
a decision.
"""

import logging
import uuid
from typing import Annotated, Literal

from fastapi import Depends, HTTPException, Query, Request
from sqlalchemy.ext.asyncio import AsyncSession

from modules.directory import reviews_service
from modules.directory.reviews_schemas import AdminReviewPageOut, ReviewOut
from modules.directory.schemas import RejectIn
from shared.audit import audit
from shared.db import get_session
from shared.events import publish
from shared.pagination import InvalidCursorError
from shared.security import SecureRouter

logger = logging.getLogger(__name__)

admin_router = SecureRouter(prefix="/admin/reviews", tags=["admin-reviews"])

SessionDep = Annotated[AsyncSession, Depends(get_session)]
LimitQuery = Annotated[int, Query(ge=1, le=100)]

EVENT_STREAM = "directory"
STAFF = "staff"
SUPER_ADMIN = "super_admin"


def _require_role(request: Request, *allowed: str) -> uuid.UUID:
    """Fail-closed role gate. Returns the acting admin's user_id (for audit)."""
    principal = request.state.principal
    roles = getattr(principal, "roles", ())
    if not any(role in roles for role in allowed):
        raise HTTPException(status_code=403, detail="missing_role")
    user_id = principal.user_id
    assert isinstance(user_id, uuid.UUID)
    return user_id


async def _publish_best_effort(event_type: str, payload: dict[str, object]) -> None:
    try:
        await publish(EVENT_STREAM, event_type, payload)
    except Exception:  # a Redis blip must never roll back an admin decision
        logger.warning(
            "reviews admin: event publish failed",
            extra={"extra_fields": {"event_type": event_type}},
        )


def _review_out(review: object) -> ReviewOut:
    # identical to reviews_router._review_out; import it instead of copying:
    from modules.directory.reviews_router import _review_out as impl
    return impl(review)  # type: ignore[arg-type]


@admin_router.get("")
async def list_reviews_for_moderation(
    request: Request,
    session: SessionDep,
    status: Literal["pending", "approved", "rejected"] = "pending",
    cursor: str | None = None,
    limit: LimitQuery = 20,
) -> AdminReviewPageOut:
    _require_role(request, STAFF, SUPER_ADMIN)
    try:
        page = await reviews_service.list_for_moderation(
            session, status=status, cursor=cursor, limit=limit
        )
    except InvalidCursorError as exc:
        raise HTTPException(status_code=400, detail="invalid cursor") from exc
    return AdminReviewPageOut(
        items=[_review_out(r) for r in page.items], next_cursor=page.next_cursor
    )


@admin_router.post("/{review_id}/approve")
async def approve_review(
    request: Request, review_id: uuid.UUID, session: SessionDep
) -> ReviewOut:
    admin_id = _require_role(request, STAFF, SUPER_ADMIN)
    try:
        review = await reviews_service.moderate(session, review_id=review_id, approve=True)
    except reviews_service.ReviewNotFoundError as exc:
        raise HTTPException(status_code=404, detail="review not found") from exc
    except reviews_service.ReviewDecisionConflictError as exc:
        raise HTTPException(status_code=409, detail="already_decided") from exc
    await reviews_service.recompute_aggregate(
        session, target_type=review.target_type, target_id=review.target_id
    )
    await audit(
        session,
        action="reviews.review_approved",
        actor_user_id=admin_id,
        target_type="review",
        target_id=str(review.id),
        metadata={
            "author_user_id": str(review.author_user_id),
            "review_target_type": review.target_type,
            "review_target_id": str(review.target_id),
        },
        ip=request.client.host if request.client else None,
    )
    # capture BEFORE commit - ORM attributes expire on commit (async lazy-load raises)
    payload: dict[str, object] = {
        "user_id": str(review.author_user_id),
        "review_id": str(review.id),
        "target_type": review.target_type,
        "target_id": str(review.target_id),
        "vars": {},
    }
    out = _review_out(review)
    await session.commit()
    await _publish_best_effort("review.approved", payload)
    return out


@admin_router.post("/{review_id}/reject")
async def reject_review(
    request: Request, review_id: uuid.UUID, body: RejectIn, session: SessionDep
) -> ReviewOut:
    admin_id = _require_role(request, STAFF, SUPER_ADMIN)
    try:
        review = await reviews_service.moderate(session, review_id=review_id, approve=False)
    except reviews_service.ReviewNotFoundError as exc:
        raise HTTPException(status_code=404, detail="review not found") from exc
    except reviews_service.ReviewDecisionConflictError as exc:
        raise HTTPException(status_code=409, detail="already_decided") from exc
    await reviews_service.recompute_aggregate(
        session, target_type=review.target_type, target_id=review.target_id
    )
    await audit(
        session,
        action="reviews.review_rejected",
        actor_user_id=admin_id,
        target_type="review",
        target_id=str(review.id),
        metadata={"note": body.note},
        ip=request.client.host if request.client else None,
    )
    out = _review_out(review)
    await session.commit()
    return out
```

(If the `_review_out` re-export indirection trips mypy, move the serializer into `reviews_schemas.py` as a plain function and import it in both routers instead.)

- [ ] **Step 4: Register** — `main.py`: `from modules.directory.reviews_admin_router import admin_router as reviews_admin_router`, add to `MODULE_ROUTERS`.

- [ ] **Step 5: Run tests to verify pass** — `pytest -q tests/test_reviews_moderation.py tests/test_reviews_router.py`.

- [ ] **Step 6: Commit**

```bash
git add modules/directory/reviews_admin_router.py main.py tests/test_reviews_moderation.py
git commit -m "feat(d18): review moderation queue - approve emits review.approved, audit-chained"
```

---

### Task 4: Event consumers — coins award (5/week cap) + notify on review.approved

**Files:**
- Modify: `backend/core/modules/coins/worker.py`, `backend/core/modules/notify/consumers.py`
- Test: modify `backend/core/tests/test_coins_worker.py`, `backend/core/tests/test_notify_consumers.py`

**Interfaces:**
- Consumes: event `review.approved` payload `{user_id, review_id, target_type, target_id, vars}` (Task 3); `coins.service.award`, `coins.rules.CapExceededError`; notify `EVENT_ROUTES`.
- Produces: coins ledger entry reason `review_approved`, idem key `review:{review_id}`; in-app notification `review_approved`.

- [ ] **Step 1: Write the failing tests.** In `tests/test_coins_worker.py` (reuse its `_ev()` helper and `NOW` constant):

```python
async def test_review_approved_awards_coins(db_session):
    uid = uuid.uuid4()
    rid = uuid.uuid4()
    await handle_event(db_session, _ev("review.approved", {
        "user_id": str(uid), "review_id": str(rid),
        "target_type": "business", "target_id": str(uuid.uuid4()), "vars": {}}), now=NOW)
    assert await service.balance(db_session, uid) == 20

async def test_review_approved_replay_is_idempotent(db_session):
    # same review_id twice -> balance stays 20 (ledger UNIQUE on review:{id})

async def test_review_approved_weekly_cap_five(db_session):
    # non-negotiable 2: 5 distinct reviews award, the 6th within 7 days does not
    uid = uuid.uuid4()
    for _ in range(5):
        await handle_event(db_session, _ev("review.approved", {...str(uuid.uuid4())...}), now=NOW)
    assert await service.balance(db_session, uid) == 100
    await handle_event(db_session, _ev("review.approved", {...6th distinct review...}), now=NOW)
    assert await service.balance(db_session, uid) == 100  # capped, no exception escapes

async def test_review_approved_award_resumes_next_week(db_session):
    # after 5 at NOW, a 6th at NOW + timedelta(days=8) awards again -> 120
```

In `tests/test_notify_consumers.py` (mirror the existing `business.claimed` test shape):

```python
async def test_review_approved_creates_in_app_notification(db_session):
    # handle_event with review.approved -> Notification row for user_id,
    # template_key "review_approved", no sms/email deliveries
```

- [ ] **Step 2: Run to verify failure** — `pytest -q tests/test_coins_worker.py tests/test_notify_consumers.py` → new tests fail (unknown event type is a silent no-op, so balance assertions fail).

- [ ] **Step 3: Coins worker branch.** In `modules/coins/worker.py`, extend the imports (`from modules.coins.rules import CapExceededError` — match the module's existing import style) and add to `handle_event`'s dispatch:

```python
    elif event.type == "review.approved":
        # review_approved: idem key review:{review_id} (spec) makes replay safe;
        # the 5/week cap is data (coins.rules.weekly_cap=5) enforced by
        # check_numeric_caps inside award() - cap-hit is a normal outcome,
        # not a retryable fault, so it must not poison the stream.
        uid = uuid.UUID(str(event.payload["user_id"]))
        review_id = str(event.payload["review_id"])
        try:
            await service.award(
                session,
                user_id=uid,
                rule_code="review_approved",
                ref_id=review_id,
                idempotency_key=f"review:{review_id}",
                now=now,
            )
        except CapExceededError:
            logger.info(
                "review_approved weekly cap reached",
                extra={"extra_fields": {"user_id": str(uid)}},
            )
```

`STREAMS` already contains `"directory"` — no change.

- [ ] **Step 4: Notify route.** In `modules/notify/consumers.py`, add to `EVENT_ROUTES`:

```python
    "review.approved": ("review_approved", frozenset()),
```

(in-app only; template seeded by 0019). `STREAMS` already contains `"directory"` — no change.

- [ ] **Step 5: Run tests to verify pass** — `pytest -q tests/test_coins_worker.py tests/test_notify_consumers.py tests/test_coins_rules.py`. NOTE: never run `tests/test_coins_storm.py` inline with the suite (`-m "not slow"` excludes it; the storm runs as its own CI job).

- [ ] **Step 6: Commit**

```bash
git add modules/coins/worker.py modules/notify/consumers.py tests/test_coins_worker.py tests/test_notify_consumers.py
git commit -m "feat(d18): coins + notify consumers for review.approved (idem review:{id}, 5/week cap)"
```

---

### Task 5: Leads models + migration 0020 (inquiries, responses, reveal log, lead templates)

**Files:**
- Create: `backend/core/modules/directory/leads_models.py`
- Create: `backend/core/alembic/versions/0020_leads_v1.py`

**Interfaces:**
- Produces: `Inquiry` (`id`, `type`, `from_user_id: UUID|None`, `business_id: UUID`, `payload: dict`, `status` default `new`, `pincode`, `category: str|None`, timestamps), `InquiryResponse` (`inquiry_id` FK, `business_user_id`, `body`, timestamps), `ContactReveal` (`user_id`, `business_id`, `branch_id`, timestamps — **no phone column exists, by construction**), enums `inquiry_type` (`contact|milk_subscription`), `inquiry_status` (`new|responded|closed`) in schema `leads`. Notify templates `lead_received`, `lead_response` ×3 locales.

- [ ] **Step 1: Write `leads_models.py`**

```python
"""Leads engine ORM (D18.B/C): inquiries, responses, DPDP contact-reveal log.

Tables live in the `leads` Postgres schema (spec) but the code lives in
modules/directory: routing needs covers() and get_owned_business(), and the
import-linter independence contract bars a separate module from importing
them. The modules/leads stub remains reserved for E4 intent matchmaking.

business_id / user ids are plain UUIDs (no cross-schema FKs) - validated in
leads_service. ContactReveal is append-only by grant (0020) and must NEVER
gain a phone/contact-value column: it records THAT a reveal happened, not
WHAT was revealed (DPDP alignment).
"""

import uuid
from typing import Any

from sqlalchemy import ForeignKey, Index, Text
from sqlalchemy.dialects import postgresql
from sqlalchemy.orm import Mapped, mapped_column

from shared.db import Base, TimestampMixin, UUIDv7PKMixin

inquiry_type_enum = postgresql.ENUM(
    "contact", "milk_subscription", name="inquiry_type", schema="leads", create_type=False
)
inquiry_status_enum = postgresql.ENUM(
    "new", "responded", "closed", name="inquiry_status", schema="leads", create_type=False
)


class Inquiry(UUIDv7PKMixin, TimestampMixin, Base):
    __tablename__ = "inquiries"
    __table_args__ = (
        Index("ix_leads_inquiries_business_id_id", "business_id", "id"),
        Index("ix_leads_inquiries_from_user_id_id", "from_user_id", "id"),
        {"schema": "leads"},
    )

    type: Mapped[str] = mapped_column(inquiry_type_enum, nullable=False)
    from_user_id: Mapped[uuid.UUID | None] = mapped_column(
        postgresql.UUID(as_uuid=True), nullable=True  # NULL = guest submission
    )
    business_id: Mapped[uuid.UUID] = mapped_column(postgresql.UUID(as_uuid=True), nullable=False)
    payload: Mapped[dict[str, Any]] = mapped_column(postgresql.JSONB, nullable=False)
    status: Mapped[str] = mapped_column(inquiry_status_enum, nullable=False, server_default="new")
    pincode: Mapped[str] = mapped_column(Text, nullable=False)
    category: Mapped[str | None] = mapped_column(Text, nullable=True)


class InquiryResponse(UUIDv7PKMixin, TimestampMixin, Base):
    __tablename__ = "responses"
    __table_args__ = (
        Index("ix_leads_responses_inquiry_id_id", "inquiry_id", "id"),
        {"schema": "leads"},
    )

    inquiry_id: Mapped[uuid.UUID] = mapped_column(
        postgresql.UUID(as_uuid=True), ForeignKey("leads.inquiries.id"), nullable=False
    )
    business_user_id: Mapped[uuid.UUID] = mapped_column(postgresql.UUID(as_uuid=True), nullable=False)
    body: Mapped[str] = mapped_column(Text, nullable=False)


class ContactReveal(UUIDv7PKMixin, TimestampMixin, Base):
    __tablename__ = "contact_reveals"
    __table_args__ = (
        Index("ix_leads_contact_reveals_user_id_created_at", "user_id", "created_at"),
        {"schema": "leads"},
    )

    user_id: Mapped[uuid.UUID] = mapped_column(postgresql.UUID(as_uuid=True), nullable=False)
    business_id: Mapped[uuid.UUID] = mapped_column(postgresql.UUID(as_uuid=True), nullable=False)
    branch_id: Mapped[uuid.UUID] = mapped_column(postgresql.UUID(as_uuid=True), nullable=False)
```

- [ ] **Step 2: Write migration `0020_leads_v1.py`** — `revision = "0020"`, `down_revision = "0019"`. Same scaffold as 0019 (templates_table, `uuid6`, `pk_column()`/`timestamp_columns()` helpers):

```python
# -- THREAT/NOTES:
# - downgrade drops inquiries/responses/contact_reveals (lead + DPDP-log loss)
#   and the lead_* notify templates.
# - contact_reveals is append-only by grant (REVOKE UPDATE, DELETE from
#   app_rt) - the reveal log is evidence, not state. It stores IDs only;
#   adding a phone column would be a DPDP violation, refuse in review.
# - leads schema + its app_rt default privileges already exist (0001 + 0013);
#   explicit grant below keeps the profile reviewable (0018 precedent).

def upgrade() -> None:
    bind = op.get_bind()
    postgresql.ENUM("contact", "milk_subscription", name="inquiry_type", schema="leads").create(bind, checkfirst=True)
    postgresql.ENUM("new", "responded", "closed", name="inquiry_status", schema="leads").create(bind, checkfirst=True)
    type_col = postgresql.ENUM(name="inquiry_type", schema="leads", create_type=False)
    status_col = postgresql.ENUM(name="inquiry_status", schema="leads", create_type=False)

    op.create_table(
        "inquiries",
        pk_column(),
        sa.Column("type", type_col, nullable=False),
        sa.Column("from_user_id", _uuid, nullable=True),
        sa.Column("business_id", _uuid, nullable=False),
        sa.Column("payload", postgresql.JSONB, nullable=False),
        sa.Column("status", status_col, nullable=False, server_default="new"),
        sa.Column("pincode", sa.Text, nullable=False),
        sa.Column("category", sa.Text, nullable=True),
        *timestamp_columns(),
        schema="leads",
    )
    op.create_index("ix_leads_inquiries_business_id_id", "inquiries", ["business_id", "id"], schema="leads")
    op.create_index("ix_leads_inquiries_from_user_id_id", "inquiries", ["from_user_id", "id"], schema="leads")

    op.create_table(
        "responses",
        pk_column(),
        sa.Column("inquiry_id", _uuid, sa.ForeignKey("leads.inquiries.id"), nullable=False),
        sa.Column("business_user_id", _uuid, nullable=False),
        sa.Column("body", sa.Text, nullable=False),
        *timestamp_columns(),
        schema="leads",
    )
    op.create_index("ix_leads_responses_inquiry_id_id", "responses", ["inquiry_id", "id"], schema="leads")

    op.create_table(
        "contact_reveals",
        pk_column(),
        sa.Column("user_id", _uuid, nullable=False),
        sa.Column("business_id", _uuid, nullable=False),
        sa.Column("branch_id", _uuid, nullable=False),
        *timestamp_columns(),
        schema="leads",
    )
    op.create_index(
        "ix_leads_contact_reveals_user_id_created_at", "contact_reveals",
        ["user_id", "created_at"], schema="leads",
    )

    op.execute('GRANT SELECT, INSERT, UPDATE, DELETE ON ALL TABLES IN SCHEMA "leads" TO app_rt')
    op.execute("REVOKE UPDATE, DELETE ON leads.contact_reveals FROM app_rt")

    op.bulk_insert(
        templates_table,
        [{"id": uuid6.uuid7(), "key": key, "channel": "in_app",
          "locale": locale, "subject": None, "body": body}
         for (key, locale, body) in SEED_TEMPLATES],
    )
```

with (producers MUST pass `business_name` and, for lead_received, `inquiry_type` — strict `{var}` rendering):

```python
SEED_TEMPLATES: list[tuple[str, str, str]] = [
    ("lead_received", "en", "New {inquiry_type} enquiry for {business_name}."),
    ("lead_received", "ta", "{business_name}க்கு புதிய {inquiry_type} விசாரணை வந்துள்ளது."),
    ("lead_received", "hi", "{business_name} के लिए नई {inquiry_type} पूछताछ आई है."),
    ("lead_response", "en", "{business_name} replied to your enquiry."),
    ("lead_response", "ta", "{business_name} உங்கள் விசாரணைக்கு பதிலளித்துள்ளது."),
    ("lead_response", "hi", "{business_name} ने आपकी पूछताछ का जवाब दिया है."),
]
```

`downgrade()`: delete the two template keys, drop the three tables (responses before inquiries — FK), drop both enums with `sa.Enum(name=..., schema="leads").drop(bind, checkfirst=True)`.

- [ ] **Step 3: Verify** — run `ALEMBIC_DATABASE_URL=...agri_test python scripts/migrate_check.py` (throwaway DB only). Then `python -c "from modules.directory.leads_models import Inquiry, InquiryResponse, ContactReveal; print('ok')"`.

- [ ] **Step 4: Commit**

```bash
git add modules/directory/leads_models.py alembic/versions/0020_leads_v1.py
git commit -m "feat(d18): leads tables (inquiries/responses/append-only reveal log) + lead notify templates"
```

---

### Task 6: Routing service — coverage(pincode) × category

**Files:**
- Modify: `backend/core/modules/directory/covers.py` (optional category filter)
- Create: `backend/core/modules/directory/leads_service.py` (routing half)
- Test: `backend/core/tests/test_leads_routing.py`

**Interfaces:**
- Consumes: `covers()` and `_BASE_SQL` machinery, `Business`, `business_coverage`, `Category`/`BusinessCategory` tables (same module).
- Produces (used by Task 7):
  - `covers(session, *, pincode, cursor=None, limit=..., category: str | None = None)` — new keyword-only param; when set, restricts to businesses assigned that category slug.
  - `leads_service.RoutedBusiness` dataclass: `id: uuid.UUID`, `name: str`, `owner_user_id: uuid.UUID | None`
  - `leads_service.route_inquiry(session, *, pincode: str, category: str | None, business_id: uuid.UUID | None) -> RoutedBusiness` — raises `BusinessNotCoveredError` (explicit business doesn't cover pincode / isn't active), `NoCoverageError` (auto-route found nothing).

- [ ] **Step 1: Write the failing tests** — `tests/test_leads_routing.py`. Seed via ORM: businesses + `BusinessCoverage(business_id=..., pincode="641001")` rows + category assignment (use the same models/inserts `tests/test_directory_router.py` uses for coverage; `geo.pincodes` may not contain 641001 in the test DB — that's fine, covers() falls back to the `UNLOCATABLE_M` sentinel and still returns the business).

```python
PINCODE = "641001"  # non-negotiable 4 mandates this exact pincode

async def test_explicit_business_must_cover_pincode(db_session):
    covered = await _mk_business_with_coverage(db_session, PINCODE)
    uncovered = await _mk_business(db_session)  # no coverage row for 641001
    routed = await leads_service.route_inquiry(
        db_session, pincode=PINCODE, category=None, business_id=covered.id)
    assert routed.id == covered.id
    with pytest.raises(leads_service.BusinessNotCoveredError):
        await leads_service.route_inquiry(
            db_session, pincode=PINCODE, category=None, business_id=uncovered.id)

async def test_suspended_business_never_routed(db_session):
    # covered but status='suspended' -> BusinessNotCoveredError

async def test_auto_route_picks_covering_business(db_session):
    # two businesses, only one covers 641001 -> auto-route (business_id=None) picks it

async def test_auto_route_filters_by_category(db_session):
    # both cover 641001; only one has category 'dairy' -> category='dairy' picks it

async def test_no_coverage_raises(db_session):
    with pytest.raises(leads_service.NoCoverageError):
        await leads_service.route_inquiry(
            db_session, pincode="999999", category=None, business_id=None)
```

- [ ] **Step 2: Run to verify failure.**

- [ ] **Step 3: Add `category` to `covers()`.** In `covers.py`, add the keyword-only param `category: str | None = None` to `covers()`; when set, append to the SQL (after `_BASE_SQL`, before the cursor predicate) and bind `:category`:

```python
_CATEGORY_PREDICATE = """
  AND EXISTS (
      SELECT 1 FROM directory.business_categories bc
      JOIN directory.categories cat ON cat.id = bc.category_id
      WHERE bc.business_id = b.id AND cat.slug = :category
  )
"""
```

```python
    sql = _BASE_SQL
    params: dict[str, object] = {"pincode": pincode, "lim": limit + 1}
    if category is not None:
        sql += _CATEGORY_PREDICATE
        params["category"] = category
```

(Check the exact join-table/column names in `models.py` — `BusinessCategory.__tablename__` / its FK column names — before writing the SQL.) The public covers route is unchanged.

- [ ] **Step 4: Write the routing half of `leads_service.py`**

```python
"""Leads engine service (D18.B): routing, ownership, stats.

Routing rule (locked by plan): an explicit business_id must cover the
pincode (else BusinessNotCoveredError - non-negotiable 4); no business_id
means nearest covering business wins (covers() distance order), category-
filtered when given. One inquiry -> one inbox; no fan-out (guest-spam
amplification)."""

import uuid
from dataclasses import dataclass

from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncSession

from modules.directory.covers import covers
from modules.directory.models import Business


class LeadsError(Exception):
    pass


class BusinessNotCoveredError(LeadsError):
    pass


class NoCoverageError(LeadsError):
    pass


class InquiryNotFoundError(LeadsError):
    pass


@dataclass(frozen=True, slots=True)
class RoutedBusiness:
    id: uuid.UUID
    name: str
    owner_user_id: uuid.UUID | None


_COVERED_SQL = text(
    """
    SELECT b.id, b.name, b.owner_user_id
    FROM directory.businesses b
    JOIN directory.business_coverage c
      ON c.business_id = b.id AND c.pincode = :pincode
    WHERE b.id = :business_id AND b.status = 'active' AND b.deleted_at IS NULL
    """
)


async def route_inquiry(
    session: AsyncSession,
    *,
    pincode: str,
    category: str | None,
    business_id: uuid.UUID | None,
) -> RoutedBusiness:
    if business_id is not None:
        row = (
            await session.execute(_COVERED_SQL, {"pincode": pincode, "business_id": business_id})
        ).first()
        if row is None:
            raise BusinessNotCoveredError(str(business_id))
        m = row._mapping
        return RoutedBusiness(id=m["id"], name=m["name"], owner_user_id=m["owner_user_id"])
    page = await covers(session, pincode=pincode, limit=1, category=category)
    if not page.items:
        raise NoCoverageError(pincode)
    nearest = page.items[0]
    owner = await session.scalar(
        select(Business.owner_user_id).where(Business.id == nearest.id)
    )
    return RoutedBusiness(id=nearest.id, name=nearest.name, owner_user_id=owner)
```

- [ ] **Step 5: Run tests to verify pass** — `pytest -q tests/test_leads_routing.py tests/test_directory_router.py` (the second confirms covers() is unbroken).

- [ ] **Step 6: Commit**

```bash
git add modules/directory/covers.py modules/directory/leads_service.py tests/test_leads_routing.py
git commit -m "feat(d18): coverage x category lead routing (explicit-covered or nearest)"
```

---

### Task 7: Guest-capable inquiry submission (optional_auth + POST /leads/inquiries)

**Files:**
- Modify: `backend/core/shared/security.py` (add `optional_auth`)
- Create: `backend/core/modules/directory/leads_schemas.py`, `backend/core/modules/directory/leads_router.py`
- Modify: `backend/core/main.py`, `backend/core/public_routes.txt`
- Test: `backend/core/tests/test_leads_router.py` (submission tests)

**Interfaces:**
- Consumes: `route_inquiry`/`RoutedBusiness` (Task 6), `Inquiry` (Task 5), `publish`.
- Produces (used by Tasks 8, 10):
  - `optional_auth(request, session) -> None` in `shared/security.py` — sets `request.state.principal` when credentials resolve, silent otherwise.
  - `POST /leads/inquiries` (public + optional_auth, 201) body `{type, business_id?, pincode, category?, payload}` → `InquiryOut {id, type, business_id, business_name, status, pincode, category, payload, created_at}`.
  - Event `lead.created` payload `{user_id: <owner>, inquiry_id, business_id, vars: {business_name, inquiry_type}}` — only when the routed business has an owner.
  - Schemas: `ContactPayloadIn {message}`, `MilkSubscriptionPayloadIn {qty_liters, milk_type, schedule}`.

- [ ] **Step 1: Write the failing tests** (same scaffold as Task 2; `published` fixture monkeypatching `modules.directory.leads_router.publish`):

```python
async def test_guest_can_submit_contact_inquiry(client, db_session, published):
    b = await _mk_business_with_coverage(db_session, "641001", owner=uuid.uuid4())
    resp = await client.post("/leads/inquiries", json={          # NO auth header
        "type": "contact", "business_id": str(b.id), "pincode": "641001",
        "payload": {"message": "Do you deliver on Sundays?"}})
    assert resp.status_code == 201
    body = resp.json()
    assert body["status"] == "new"
    inquiry = await db_session.get(Inquiry, uuid.UUID(body["id"]))
    assert inquiry.from_user_id is None                          # guest
    assert published[0][:2] == ("directory", "lead.created")
    assert published[0][2]["user_id"] == str(b.owner_user_id)

async def test_authed_submit_records_from_user_id(client, db_session):
    # with x-test-user header -> from_user_id == that user

async def test_unclaimed_business_no_notification(client, db_session, published):
    # owner_user_id None -> 201 but published stays empty

async def test_business_not_covering_pincode_422(client, db_session):
    # non-negotiable 4: covered-elsewhere business + pincode 641001 -> 422 "business_not_covered"

async def test_auto_route_no_coverage_422(client, db_session):
    # no business_id, pincode with no coverage -> 422 "no_coverage"

async def test_milk_subscription_payload_validated(client, db_session):
    # type=milk_subscription with contact-shaped payload -> 422
    # with {"qty_liters": "1.5", "milk_type": "cow", "schedule": "daily"} -> 201

async def test_contact_payload_validated(client, db_session):
    # empty message -> 422
```

- [ ] **Step 2: Run to verify failure.**

- [ ] **Step 3: Add `optional_auth` to `shared/security.py`** (below `require_auth`):

```python
async def optional_auth(
    request: Request, session: Annotated[AsyncSession, Depends(get_session)]
) -> None:
    """Attribute the caller when credentials are present; never 401.

    For guest-capable routes (declared public=True): a logged-in caller gets
    request.state.principal set exactly as require_auth would, an anonymous
    caller proceeds without one. Routes must treat the principal as optional."""
    if _principal_resolver is None:
        return
    principal = await _principal_resolver(request, session)
    if principal is not None:
        request.state.principal = principal
```

- [ ] **Step 4: Write `leads_schemas.py`**

```python
"""Leads API request/response schemas (D18.B)."""

import uuid
from datetime import datetime
from decimal import Decimal
from typing import Any, Literal

from pydantic import BaseModel, Field

from modules.directory.schemas import PINCODE_PATTERN, SLUG_PATTERN

InquiryType = Literal["contact", "milk_subscription"]
InquiryStatus = Literal["new", "responded", "closed"]


class ContactPayloadIn(BaseModel):
    message: str = Field(min_length=1, max_length=2000)


class MilkSubscriptionPayloadIn(BaseModel):
    qty_liters: Decimal = Field(gt=0, le=100)
    milk_type: Literal["cow", "buffalo", "goat", "mixed"]
    schedule: Literal["daily", "alternate_days", "weekly"]


class InquiryCreateIn(BaseModel):
    type: InquiryType
    business_id: uuid.UUID | None = None
    pincode: str = Field(pattern=PINCODE_PATTERN)
    category: str | None = Field(default=None, pattern=SLUG_PATTERN)
    payload: dict[str, Any]


class InquiryOut(BaseModel):
    id: uuid.UUID
    type: str
    business_id: uuid.UUID
    business_name: str
    status: str
    pincode: str
    category: str | None
    payload: dict[str, Any]
    created_at: datetime


class ResponseCreateIn(BaseModel):
    body: str = Field(min_length=1, max_length=2000)


class ResponseOut(BaseModel):
    id: uuid.UUID
    inquiry_id: uuid.UUID
    business_user_id: uuid.UUID
    body: str
    created_at: datetime


class InboxInquiryOut(BaseModel):
    id: uuid.UUID
    type: str
    status: str
    pincode: str
    category: str | None
    payload: dict[str, Any]
    from_user_id: uuid.UUID | None
    created_at: datetime


class InboxPageOut(BaseModel):
    items: list[InboxInquiryOut]
    next_cursor: str | None


class MyInquiryOut(BaseModel):
    id: uuid.UUID
    type: str
    business_id: uuid.UUID
    status: str
    payload: dict[str, Any]
    responses: list[ResponseOut]
    created_at: datetime


class MyInquiryPageOut(BaseModel):
    items: list[MyInquiryOut]
    next_cursor: str | None


class InboxStatsOut(BaseModel):
    total: int
    responded: int
    avg_response_seconds: int | None


class ContactRevealOut(BaseModel):
    branch_id: uuid.UUID
    phone: str | None
    whatsapp: str | None
```

- [ ] **Step 5: Write `leads_router.py`** (submission route only in this task):

```python
"""Leads API (D18.B). Inquiry submission is guest-capable (public=True +
optional_auth attribution); everything else is owner- or submitter-gated.
Never log payloads - they carry contact intents (PII-dense)."""

import logging
import uuid
from typing import Annotated

from fastapi import Depends, HTTPException, Query, Request
from pydantic import ValidationError
from sqlalchemy.ext.asyncio import AsyncSession

from modules.directory import leads_service
from modules.directory.leads_models import Inquiry
from modules.directory.leads_schemas import (
    ContactPayloadIn,
    InquiryCreateIn,
    InquiryOut,
    MilkSubscriptionPayloadIn,
)
from shared.db import get_session
from shared.events import publish
from shared.security import SecureRouter, optional_auth

logger = logging.getLogger(__name__)

router = SecureRouter(prefix="/leads", tags=["leads"])

SessionDep = Annotated[AsyncSession, Depends(get_session)]
LimitQuery = Annotated[int, Query(ge=1, le=100)]

EVENT_STREAM = "directory"


def _principal_user_id(request: Request) -> uuid.UUID:
    principal = request.state.principal
    user_id = principal.user_id
    assert isinstance(user_id, uuid.UUID)
    return user_id


async def _publish_best_effort(event_type: str, payload: dict[str, object]) -> None:
    try:
        await publish(EVENT_STREAM, event_type, payload)
    except Exception:  # a Redis blip must never fail a lead submission
        logger.warning(
            "leads: event publish failed",
            extra={"extra_fields": {"event_type": event_type}},
        )


def _validate_payload(inquiry_type: str, payload: dict[str, object]) -> dict[str, object]:
    model = ContactPayloadIn if inquiry_type == "contact" else MilkSubscriptionPayloadIn
    try:
        return model.model_validate(payload).model_dump(mode="json")
    except ValidationError as exc:
        raise HTTPException(status_code=422, detail="invalid_payload") from exc


@router.post("/inquiries", public=True, status_code=201, dependencies=[Depends(optional_auth)])
async def create_inquiry(
    request: Request, body: InquiryCreateIn, session: SessionDep
) -> InquiryOut:
    clean_payload = _validate_payload(body.type, body.payload)
    try:
        routed = await leads_service.route_inquiry(
            session, pincode=body.pincode, category=body.category, business_id=body.business_id
        )
    except leads_service.BusinessNotCoveredError as exc:
        raise HTTPException(status_code=422, detail="business_not_covered") from exc
    except leads_service.NoCoverageError as exc:
        raise HTTPException(status_code=422, detail="no_coverage") from exc

    principal = getattr(request.state, "principal", None)
    inquiry = Inquiry(
        type=body.type,
        from_user_id=principal.user_id if principal is not None else None,
        business_id=routed.id,
        payload=clean_payload,
        pincode=body.pincode,
        category=body.category,
    )
    session.add(inquiry)
    await session.flush()

    out = InquiryOut(
        id=inquiry.id, type=inquiry.type, business_id=routed.id,
        business_name=routed.name, status=inquiry.status,
        pincode=inquiry.pincode, category=inquiry.category,
        payload=inquiry.payload, created_at=inquiry.created_at,
    )
    event_payload: dict[str, object] | None = None
    if routed.owner_user_id is not None:  # unclaimed inboxes have no one to notify
        event_payload = {
            "user_id": str(routed.owner_user_id),
            "inquiry_id": str(inquiry.id),
            "business_id": str(routed.id),
            "vars": {"business_name": routed.name, "inquiry_type": inquiry.type},
        }
    await session.commit()  # commit BEFORE announcing (repo-wide event ordering rule)
    if event_payload is not None:
        await _publish_best_effort("lead.created", event_payload)
    return out
```

Note: `inquiry.status` / `inquiry.created_at` are server-default columns — `flush()` alone doesn't populate server defaults on the ORM object unless the mixins use `server_default` with `eager_defaults`; check how directory routers read `created_at` after flush (they do — `TimestampMixin` works with flush in this codebase; if `status` comes back `None`, read it as `"new"` literal since the row was just created).

- [ ] **Step 6: Register + declare.** `main.py`: `from modules.directory.leads_router import router as leads_engine_router`, append to `MODULE_ROUTERS` (the empty `modules/leads` stub router stays registered and harmless — do not touch it). Append `/leads/inquiries` to `public_routes.txt`.

- [ ] **Step 7: Run tests to verify pass** — `pytest -q tests/test_leads_router.py` and `python scripts/dump_public_routes.py --check`.

- [ ] **Step 8: Commit**

```bash
git add shared/security.py modules/directory/leads_schemas.py modules/directory/leads_router.py main.py public_routes.txt tests/test_leads_router.py
git commit -m "feat(d18): guest-capable lead submission with coverage routing + lead.created notify"
```

---

### Task 8: Inbox, responses, submitter view, response-time stat

**Files:**
- Modify: `backend/core/modules/directory/leads_service.py`, `backend/core/modules/directory/leads_router.py`
- Test: extend `backend/core/tests/test_leads_router.py`

**Interfaces:**
- Consumes: `service.get_owned_business` + `BusinessNotFoundError` from `modules.directory.service`, `paginate`.
- Produces (used by Tasks 10, 12):
  - `GET /leads/inbox?business_id=&status=&cursor=&limit=` → `InboxPageOut` (auth, owner-only, newest first)
  - `GET /leads/inbox/stats?business_id=` → `InboxStatsOut {total, responded, avg_response_seconds}`
  - `POST /leads/inquiries/{inquiry_id}/responses` → `ResponseOut` (201; owner-only; sets status new→responded; emits `lead.responded` to submitter when not guest)
  - `POST /leads/inquiries/{inquiry_id}/close` → `InboxInquiryOut` (owner-only)
  - `GET /leads/mine?cursor=&limit=` → `MyInquiryPageOut` (auth; submitter's inquiries with embedded responses)
  - `leads_service.get_owned_inquiry(session, owner_user_id, inquiry_id) -> Inquiry` (IDOR: not-yours == missing == 404)

- [ ] **Step 1: Write the failing tests** (extend `tests/test_leads_router.py`):

```python
async def test_inbox_requires_auth_and_ownership(client, db_session):
    # no header -> 401; owner -> 200 with the inquiry; OTHER user -> 404 (IDOR, same
    # body as nonexistent business - assert status only)

async def test_inbox_newest_first_keyset(client, db_session):
    # 3 inquiries -> limit=2 gives newest 2 + next_cursor; cursor page gives the 3rd

async def test_inbox_status_filter(client, db_session):
    # ?status=new excludes a responded inquiry

async def test_respond_flow(client, db_session, published):
    # owner responds -> 201, inquiry.status becomes "responded",
    # lead.responded published with user_id == submitter id
    # guest inquiry (from_user_id None) -> respond publishes nothing

async def test_respond_idor(client, db_session):
    # non-owner responding -> 404

async def test_close_inquiry(client, db_session):
    # owner closes -> status "closed"

async def test_mine_lists_own_with_responses(client, db_session):
    # submitter sees their inquiry incl. embedded response bodies; other user sees []

async def test_inbox_stats(client, db_session):
    # 2 inquiries, 1 responded -> total 2, responded 1, avg_response_seconds is int >= 0
```

- [ ] **Step 2: Run to verify failure.**

- [ ] **Step 3: Extend `leads_service.py`**

```python
from modules.directory.leads_models import Inquiry, InquiryResponse
from modules.directory.service import BusinessNotFoundError, get_owned_business


async def get_owned_inquiry(
    session: AsyncSession, owner_user_id: uuid.UUID, inquiry_id: uuid.UUID
) -> Inquiry:
    inquiry = await session.scalar(select(Inquiry).where(Inquiry.id == inquiry_id))
    if inquiry is None:
        raise InquiryNotFoundError(str(inquiry_id))
    try:
        await get_owned_business(session, owner_user_id, inquiry.business_id)
    except BusinessNotFoundError:
        # IDOR: someone else's inquiry and a missing one are the SAME 404
        raise InquiryNotFoundError(str(inquiry_id)) from None
    return inquiry


_STATS_SQL = text(
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
    WHERE i.business_id = :business_id
    """
)


async def inbox_stats(session: AsyncSession, business_id: uuid.UUID) -> tuple[int, int, int | None]:
    row = (await session.execute(_STATS_SQL, {"business_id": business_id})).one()
    m = row._mapping
    avg = m["avg_response_seconds"]
    return int(m["total"]), int(m["responded"]), int(avg) if avg is not None else None
```

(Note: `avg(...)` over the lateral join averages only rows where `first_at` is non-NULL — SQL `avg` ignores NULLs; that is the intended "response-time stat over responded inquiries".)

- [ ] **Step 4: Extend `leads_router.py`** — check the exact `service.get_owned_business` import doesn't collide (`from modules.directory import service as directory_service`):

```python
@router.get("/inbox")
async def inbox(
    request: Request,
    session: SessionDep,
    business_id: uuid.UUID,
    status: InquiryStatus | None = None,
    cursor: str | None = None,
    limit: LimitQuery = 20,
) -> InboxPageOut:
    user_id = _principal_user_id(request)
    try:
        await directory_service.get_owned_business(session, user_id, business_id)
    except directory_service.BusinessNotFoundError as exc:
        raise HTTPException(status_code=404, detail="Business not found") from exc
    query = select(Inquiry).where(Inquiry.business_id == business_id)
    if status is not None:
        query = query.where(Inquiry.status == status)
    try:
        page = await paginate(session, query, cursor=cursor, limit=limit, descending=True)
    except InvalidCursorError as exc:
        raise HTTPException(status_code=400, detail="invalid cursor") from exc
    return InboxPageOut(items=[_inbox_out(i) for i in page.items], next_cursor=page.next_cursor)


@router.get("/inbox/stats")
async def inbox_statistics(
    request: Request, session: SessionDep, business_id: uuid.UUID
) -> InboxStatsOut:
    user_id = _principal_user_id(request)
    try:
        await directory_service.get_owned_business(session, user_id, business_id)
    except directory_service.BusinessNotFoundError as exc:
        raise HTTPException(status_code=404, detail="Business not found") from exc
    total, responded, avg_seconds = await leads_service.inbox_stats(session, business_id)
    return InboxStatsOut(total=total, responded=responded, avg_response_seconds=avg_seconds)


@router.post("/inquiries/{inquiry_id}/responses", status_code=201)
async def respond_to_inquiry(
    request: Request, inquiry_id: uuid.UUID, body: ResponseCreateIn, session: SessionDep
) -> ResponseOut:
    user_id = _principal_user_id(request)
    try:
        inquiry = await leads_service.get_owned_inquiry(session, user_id, inquiry_id)
    except leads_service.InquiryNotFoundError as exc:
        raise HTTPException(status_code=404, detail="Inquiry not found") from exc
    response = InquiryResponse(inquiry_id=inquiry.id, business_user_id=user_id, body=body.body)
    session.add(response)
    if inquiry.status == "new":
        inquiry.status = "responded"
    await session.flush()
    event_payload: dict[str, object] | None = None
    if inquiry.from_user_id is not None:  # guests have no inbox to notify
        business = await session.get(Business, inquiry.business_id)
        event_payload = {
            "user_id": str(inquiry.from_user_id),
            "inquiry_id": str(inquiry.id),
            "vars": {"business_name": business.name if business else ""},
        }
    out = ResponseOut(
        id=response.id, inquiry_id=response.inquiry_id,
        business_user_id=response.business_user_id, body=response.body,
        created_at=response.created_at,
    )
    await session.commit()
    if event_payload is not None:
        await _publish_best_effort("lead.responded", event_payload)
    return out


@router.post("/inquiries/{inquiry_id}/close")
async def close_inquiry(
    request: Request, inquiry_id: uuid.UUID, session: SessionDep
) -> InboxInquiryOut:
    user_id = _principal_user_id(request)
    try:
        inquiry = await leads_service.get_owned_inquiry(session, user_id, inquiry_id)
    except leads_service.InquiryNotFoundError as exc:
        raise HTTPException(status_code=404, detail="Inquiry not found") from exc
    inquiry.status = "closed"
    await session.flush()
    out = _inbox_out(inquiry)
    await session.commit()
    return out


@router.get("/mine")
async def my_inquiries(
    request: Request, session: SessionDep, cursor: str | None = None, limit: LimitQuery = 20
) -> MyInquiryPageOut:
    user_id = _principal_user_id(request)
    query = select(Inquiry).where(Inquiry.from_user_id == user_id)
    try:
        page = await paginate(session, query, cursor=cursor, limit=limit, descending=True)
    except InvalidCursorError as exc:
        raise HTTPException(status_code=400, detail="invalid cursor") from exc
    ids = [i.id for i in page.items]
    responses: dict[uuid.UUID, list[InquiryResponse]] = {}
    if ids:
        rows = await session.scalars(
            select(InquiryResponse)
            .where(InquiryResponse.inquiry_id.in_(ids))
            .order_by(InquiryResponse.id)
        )
        for r in rows:
            responses.setdefault(r.inquiry_id, []).append(r)
    return MyInquiryPageOut(
        items=[
            MyInquiryOut(
                id=i.id, type=i.type, business_id=i.business_id, status=i.status,
                payload=i.payload, created_at=i.created_at,
                responses=[
                    ResponseOut(
                        id=r.id, inquiry_id=r.inquiry_id,
                        business_user_id=r.business_user_id, body=r.body,
                        created_at=r.created_at,
                    )
                    for r in responses.get(i.id, [])
                ],
            )
            for i in page.items
        ],
        next_cursor=page.next_cursor,
    )
```

with the small serializer:

```python
def _inbox_out(inquiry: Inquiry) -> InboxInquiryOut:
    return InboxInquiryOut(
        id=inquiry.id, type=inquiry.type, status=inquiry.status,
        pincode=inquiry.pincode, category=inquiry.category,
        payload=inquiry.payload, from_user_id=inquiry.from_user_id,
        created_at=inquiry.created_at,
    )
```

- [ ] **Step 5: Run tests to verify pass** — `pytest -q tests/test_leads_router.py tests/test_leads_routing.py`.

- [ ] **Step 6: Commit**

```bash
git add modules/directory/leads_service.py modules/directory/leads_router.py tests/test_leads_router.py
git commit -m "feat(d18): business inbox + responses + submitter view + response-time stat (IDOR-gated)"
```

---

### Task 9: Contact reveal — cap + DPDP log + strip public phones + PII coverage

**Files:**
- Modify: `backend/core/settings.py` (add `contact_reveal_daily_cap: int = 10`)
- Create: `backend/core/modules/directory/reveal.py`
- Modify: `backend/core/modules/directory/schemas.py` (add `PublicBranchOut`; change `BusinessDetailOut.branches` to `list[PublicBranchOut]`), `backend/core/modules/directory/router.py`
- Test: `backend/core/tests/test_contact_reveal.py`; modify `tests/test_directory_router.py` (public-detail phone assertions), `tests/test_telemetry.py`

**Interfaces:**
- Consumes: `Branch`, `ContactReveal` (Task 5), `get_redis` from `shared.cache`, `get_settings`.
- Produces (used by Task 10): `POST /directory/branches/{branch_id}/reveal` (auth) → `ContactRevealOut {branch_id, phone, whatsapp}`; 429 `reveal_cap_exceeded`; 503 `reveal_unavailable`. Public `GET /directory/businesses/{slug}` no longer contains `phone`/`whatsapp` keys at all.

- [ ] **Step 1: Write the failing tests** — `tests/test_contact_reveal.py` (scaffold as before; the redis fixture is `redis_client` from conftest):

```python
async def test_public_detail_has_no_contact_fields(client, db_session):
    # business + branch with phone="+916374000001" -> GET /directory/businesses/{slug}
    # branches[0] contains NO "phone"/"whatsapp" keys (not even null - key absence
    # is the contract so scrapers learn nothing)

async def test_reveal_requires_login(client, db_session):
    # no auth header -> 401

async def test_reveal_returns_numbers_and_logs(client, db_session, redis_client):
    # auth -> 200 {"phone": "+916374000001", ...}; a leads.contact_reveals row
    # exists with user_id/business_id/branch_id; row has no phone attribute at all:
    assert not hasattr(ContactReveal, "phone")

async def test_reveal_daily_cap_enforced(client, db_session, redis_client, monkeypatch):
    # monkeypatch settings contact_reveal_daily_cap to 3 (or set env via the
    # settings fixture pattern used in otp throttle tests); reveals 1-3 -> 200,
    # 4th -> 429  (non-negotiable 3)

async def test_reveal_fails_closed_without_redis(client, db_session, monkeypatch):
    # monkeypatch modules.directory.reveal.get_redis to raise -> 503 (never open)

async def test_reveal_log_line_has_no_phone(client, db_session, redis_client, caplog):
    # perform a reveal, then: assert "+916374000001" not in caplog.text
    # and "637400" not in caplog.text
```

In `tests/test_telemetry.py` add (D05 extension — non-negotiable 3's "logged w/o plaintext phone"):

```python
def test_scrub_redacts_e164_phone():
    assert "+916374344282" not in scrub("call +916374344282 now")

def test_scrub_redacts_wa_me_link_digits():
    assert "916374344282" not in scrub("https://wa.me/916374344282")
```

(If the wa.me case fails, extend `_PHONE` in `shared/telemetry.py` minimally to cover digits after `wa.me/` — add the fix only if the test proves the gap.)

In `tests/test_directory_router.py`, update any assertion reading `phone`/`whatsapp` from the **public detail** response (grep the file); owner-scoped `BranchOut` assertions stay untouched.

- [ ] **Step 2: Run to verify failure.**

- [ ] **Step 3: Add the setting** — in `settings.py`, next to the other int settings: `contact_reveal_daily_cap: int = 10`.

- [ ] **Step 4: Write `reveal.py`**

```python
"""Contact reveal throttle (D18.C, anti-scraping).

Fail-closed by design (OTP-throttle precedent): Redis down means 503, never
an uncapped reveal - the cap IS the scraping defence and is never bypassed.
Fixed daily window via INCR+EXPIRE; the increment happens BEFORE the numbers
leave the process, so a crash mid-request costs the user one slot, never
grants a free reveal."""

import uuid
from datetime import datetime

from redis.exceptions import RedisError

from settings import get_settings
from shared.cache import get_redis

_DAY_SECONDS = 86400


class RevealCapExceededError(Exception):
    pass


class RevealUnavailableError(Exception):
    pass


async def claim_reveal_slot(user_id: uuid.UUID, *, now: datetime) -> None:
    cap = get_settings().contact_reveal_daily_cap
    key = f"reveal:{user_id}:{now.strftime('%Y%m%d')}"
    try:
        redis = get_redis()
        count = int(await redis.incr(key))
        if count == 1:
            await redis.expire(key, _DAY_SECONDS)
    except RedisError as exc:
        raise RevealUnavailableError() from exc
    if count > cap:
        raise RevealCapExceededError()
```

(Check how `settings`/`get_settings` and `get_redis` are actually imported elsewhere in the module tree — e.g. `modules/notify/service.py` — and mirror those import paths exactly.)

- [ ] **Step 5: Strip public phones + add the route.** In `schemas.py` add:

```python
class PublicBranchOut(BaseModel):
    """Branch as served on the PUBLIC detail page - contact fields are
    structurally absent (D18.C): reveal is a separate capped endpoint."""

    id: uuid.UUID
    business_id: uuid.UUID
    address: str
    state: str
    district: str
    pincode: str
    lat: Decimal | None
    lng: Decimal | None
    hours: dict[str, Any]


class ContactRevealOut(BaseModel):
    branch_id: uuid.UUID
    phone: str | None
    whatsapp: str | None
```

Change `BusinessDetailOut.branches: list[PublicBranchOut]`. In `router.py`: add `_public_branch_out(branch)` (same as `_branch_out` minus phone/whatsapp), use it in `get_business_detail`; owner CRUD keeps `_branch_out`. Add the reveal route:

```python
@router.post("/branches/{branch_id}/reveal")
async def reveal_branch_contact(
    request: Request, branch_id: uuid.UUID, session: SessionDep
) -> ContactRevealOut:
    """Login-gated, daily-capped, DPDP-logged contact reveal (D18.C).
    Order matters: cap FIRST (never bypassed), log row SECOND, numbers LAST."""
    user_id = _principal_user_id(request)
    branch = await session.scalar(select(Branch).where(Branch.id == branch_id))
    if branch is None:
        raise HTTPException(status_code=404, detail="Branch not found")
    business = await session.scalar(
        select(Business).where(Business.id == branch.business_id, Business.status == "active")
    )
    if business is None:
        raise HTTPException(status_code=404, detail="Branch not found")
    try:
        await claim_reveal_slot(user_id, now=datetime.now(UTC))
    except RevealCapExceededError as exc:
        raise HTTPException(status_code=429, detail="reveal_cap_exceeded") from exc
    except RevealUnavailableError as exc:
        raise HTTPException(status_code=503, detail="reveal_unavailable") from exc
    session.add(
        ContactReveal(user_id=user_id, business_id=branch.business_id, branch_id=branch.id)
    )
    await session.commit()
    # IDs only - never the numbers (DPDP; scrubber is last-line defence, not licence)
    logger.info(
        "contact.revealed",
        extra={"extra_fields": {"user_id": str(user_id), "branch_id": str(branch.id)}},
    )
    return ContactRevealOut(branch_id=branch.id, phone=branch.phone, whatsapp=branch.whatsapp)
```

Add the needed imports to `router.py` (`logging`/`logger`, `datetime`/`UTC`, `select`, `ContactReveal` from `leads_models`, reveal helpers, new schemas).

- [ ] **Step 6: Run tests to verify pass** — `pytest -q tests/test_contact_reveal.py tests/test_directory_router.py tests/test_directory_branches.py tests/test_telemetry.py`.

- [ ] **Step 7: Commit**

```bash
git add settings.py modules/directory/reveal.py modules/directory/schemas.py modules/directory/router.py tests/test_contact_reveal.py tests/test_directory_router.py tests/test_telemetry.py
git commit -m "feat(d18): capped DPDP-logged contact reveal; public API no longer serves raw phones"
```

---

### Task 10: Frontend — BFF proxies + reveal button + lead form on the business page

**Files:**
- Create: `apps/web-agri/app/api/reviews/[...path]/route.ts`, `apps/web-agri/app/api/leads/[...path]/route.ts`
- Create: `apps/web-agri/app/directory/businesses/[slug]/reveal-contact.tsx`, `lead-form.tsx`
- Modify: `apps/web-agri/app/directory/businesses/[slug]/page.tsx`

**Interfaces:**
- Consumes: backend routes from Tasks 7–9; `auth` from `apps/web-agri/lib/auth.ts`; `useAgriUser` from `@agri/auth-client/react`; `Button`, `CallButton`, `WhatsAppButton` from `@agri/ui`.
- Produces: `/api/reviews/*` (auth-required JSON proxy), `/api/leads/*` (guest-capable JSON proxy — attaches bearer only when a session exists). `RevealContact` and `LeadForm` client islands rendered on the business page (used again by Task 11's review components pattern).

- [ ] **Step 1: Read `apps/web-agri/app/api/notify/[...path]/route.ts` and `apps/web-agri/app/directory/businesses/[slug]/page.tsx` in full** (know the exact proxy shape and the page's `BusinessDetail` type + where branches/CallButton render today).

- [ ] **Step 2: Write the reviews proxy** — clone the notify JSON proxy verbatim, changing prefix to `/reviews` (401 when `getAccessToken()` is null, forward JSON, `cache: "no-store"`; "tokens never touch JS - D10 non-negotiable" comment style preserved).

- [ ] **Step 3: Write the leads proxy** — same skeleton, one deliberate difference (guests allowed):

```ts
// Guest-capable proxy (D18): leads submission is public - attach the bearer
// only when a session exists so logged-in submitters get attributed.
const token = await auth.getAccessToken();
const headers: Record<string, string> = { accept: "application/json" };
if (req.headers.get("content-type")) headers["content-type"] = req.headers.get("content-type")!;
if (token) headers.authorization = `Bearer ${token}`;
```

- [ ] **Step 4: Write `reveal-contact.tsx`** (client island; unauthenticated users get the login redirect, capped users a friendly notice):

```tsx
"use client";

import { useState } from "react";
import { Button, CallButton, WhatsAppButton } from "@agri/ui";
import { useAgriUser } from "@agri/auth-client/react";

type Revealed = { branch_id: string; phone: string | null; whatsapp: string | null };

export function RevealContact({ branchId, slug }: { branchId: string; slug: string }) {
  const { status } = useAgriUser({ autoSilentSso: false });
  const [revealed, setRevealed] = useState<Revealed | null>(null);
  const [state, setState] = useState<"idle" | "loading" | "capped" | "error">("idle");

  if (revealed) {
    return (
      <div className="flex gap-2">
        {revealed.phone ? <CallButton phone={revealed.phone} /> : null}
        {revealed.whatsapp ? <WhatsAppButton phone={revealed.whatsapp} /> : null}
      </div>
    );
  }
  if (status === "unauthenticated") {
    return (
      <Button variant="call" asChild className="min-h-[44px]">
        <a href={`/api/auth/login?next=/directory/businesses/${encodeURIComponent(slug)}`}>
          Login to view contact
        </a>
      </Button>
    );
  }
  return (
    <div>
      <Button
        variant="call"
        className="min-h-[44px]"
        disabled={state === "loading"}
        onClick={async () => {
          setState("loading");
          const res = await fetch(`/api/directory/branches/${branchId}/reveal`, { method: "POST" });
          if (res.ok) { setRevealed(await res.json()); setState("idle"); }
          else setState(res.status === 429 ? "capped" : "error");
        }}
      >
        Show phone number
      </Button>
      {state === "capped" ? (
        <p className="mt-1 text-[13px] text-muted">Daily reveal limit reached — try tomorrow.</p>
      ) : null}
      {state === "error" ? (
        <p className="mt-1 text-[13px] text-muted">Could not reveal right now.</p>
      ) : null}
    </div>
  );
}
```

(Check `CallButton`/`WhatsAppButton` prop names in `packages/ui/src/components/button.tsx` before use; adjust `variant`/`asChild` to what `Button` actually supports. `text-muted` must be an existing token class — verify in the Tailwind preset; never a raw hex.)

- [ ] **Step 5: Write `lead-form.tsx`** — client island, guest-capable, styled per the claim-form pattern (inline status state, no toasts). Contact + milk variants:

```tsx
"use client";

import { useState } from "react";
import { Button } from "@agri/ui";

type Props = { businessId: string; defaultPincode: string; milkVertical: boolean };

export function LeadForm({ businessId, defaultPincode, milkVertical }: Props) {
  const [kind, setKind] = useState<"contact" | "milk_subscription">("contact");
  const [state, setState] = useState<"idle" | "submitting" | "done" | "error">("idle");
  const [pincode, setPincode] = useState(defaultPincode);
  const [message, setMessage] = useState("");
  const [qty, setQty] = useState("1");
  const [milkType, setMilkType] = useState("cow");
  const [schedule, setSchedule] = useState("daily");

  if (state === "done") {
    return <p className="text-[14px] font-semibold">Enquiry sent. The business will get back to you.</p>;
  }
  const payload =
    kind === "contact"
      ? { message }
      : { qty_liters: qty, milk_type: milkType, schedule };
  return (
    <form
      className="grid gap-3"
      onSubmit={async (e) => {
        e.preventDefault();
        setState("submitting");
        const res = await fetch("/api/leads/inquiries", {
          method: "POST",
          headers: { "content-type": "application/json" },
          body: JSON.stringify({ type: kind, business_id: businessId, pincode, payload }),
        });
        setState(res.ok ? "done" : "error");
      }}
    >
      {milkVertical ? (
        <div className="flex gap-2">
          <Button type="button" variant={kind === "contact" ? "brand" : "ghost"}
                  className="min-h-[44px]" onClick={() => setKind("contact")}>Message</Button>
          <Button type="button" variant={kind === "milk_subscription" ? "brand" : "ghost"}
                  className="min-h-[44px]" onClick={() => setKind("milk_subscription")}>Milk subscription</Button>
        </div>
      ) : null}
      <input required pattern="\d{6}" value={pincode} onChange={(e) => setPincode(e.target.value)}
             aria-label="Pincode" className="min-h-[44px] rounded-md border border-line px-3" />
      {kind === "contact" ? (
        <textarea required maxLength={2000} value={message} onChange={(e) => setMessage(e.target.value)}
                  aria-label="Message" rows={3} className="rounded-md border border-line px-3 py-2" />
      ) : (
        <div className="grid gap-2">
          <input required type="number" min="0.5" max="100" step="0.5" value={qty}
                 onChange={(e) => setQty(e.target.value)} aria-label="Litres per day"
                 className="min-h-[44px] rounded-md border border-line px-3" />
          <select value={milkType} onChange={(e) => setMilkType(e.target.value)}
                  aria-label="Milk type" className="min-h-[44px] rounded-md border border-line px-3">
            <option value="cow">Cow</option><option value="buffalo">Buffalo</option>
            <option value="goat">Goat</option><option value="mixed">Mixed</option>
          </select>
          <select value={schedule} onChange={(e) => setSchedule(e.target.value)}
                  aria-label="Schedule" className="min-h-[44px] rounded-md border border-line px-3">
            <option value="daily">Daily</option>
            <option value="alternate_days">Alternate days</option>
            <option value="weekly">Weekly</option>
          </select>
        </div>
      )}
      <Button type="submit" variant="brand" className="min-h-[44px]" disabled={state === "submitting"}>
        Send enquiry
      </Button>
      {state === "error" ? <p className="text-[13px] text-muted">Could not send — check pincode coverage.</p> : null}
    </form>
  );
}
```

(Replace `border-line`/`text-muted` with the actual token utility classes used by `claim-form.tsx` — copy its input styling verbatim.)

- [ ] **Step 6: Wire into `page.tsx`** — remove any raw `phone`/`whatsapp` rendering (the API no longer returns them; update the page's `BusinessDetail` TS type accordingly), render `<RevealContact branchId={...} slug={slug} />` where contact actions lived (design law: reveal buttons FIRST), `<LeadForm businessId={...} defaultPincode={business.primary_pincode} milkVertical={...} />` below ("form is fallback"). `milkVertical`: pass `business.type === "vendor"` for now (vertical registry wiring is D19/D23 scope).

- [ ] **Step 7: Verify** — `pnpm --filter @agri/web-agri lint && pnpm --filter @agri/web-agri build` (check exact package name in `apps/web-agri/package.json` first). Expected: clean build.

- [ ] **Step 8: Commit**

```bash
git add apps/web-agri/app/api/reviews apps/web-agri/app/api/leads "apps/web-agri/app/directory/businesses/[slug]"
git commit -m "feat(d18): web-agri reveal-gated contacts + guest lead form + BFF proxies"
```

---

### Task 11: Frontend — reviews UI + aggregateRating JSON-LD on the business page

**Files:**
- Create: `apps/web-agri/app/directory/businesses/[slug]/review-form.tsx`, `reviews-section.tsx`
- Modify: `apps/web-agri/app/directory/businesses/[slug]/page.tsx`

**Interfaces:**
- Consumes: `GET /reviews`, `GET /reviews/summary` (public, fetched server-side with `next: { revalidate: 300 }`), `POST /api/reviews` proxy (Task 10), `RatingStars` from `@agri/ui`, the page's existing hand-rolled `businessJsonLd`.

- [ ] **Step 1: Server-side fetches in `page.tsx`** (alongside `fetchDetail`):

```ts
type RatingSummary = { rating_avg: string | null; rating_count: number };
type ReviewItem = {
  id: string; rating: number; body: Record<string, string> | null;
  created_at: string;
};

async function fetchReviews(businessId: string): Promise<{ summary: RatingSummary; items: ReviewItem[] }> {
  const qs = `target_type=business&target_id=${businessId}`;
  const [sRes, lRes] = await Promise.all([
    fetch(`${API}/reviews/summary?${qs}`, { next: { revalidate: 300 } }),
    fetch(`${API}/reviews?${qs}&limit=10`, { next: { revalidate: 300 } }),
  ]);
  const summary = sRes.ok ? await sRes.json() : { rating_avg: null, rating_count: 0 };
  const items = lRes.ok ? (await lRes.json()).items : [];
  return { summary, items };
}
```

- [ ] **Step 2: Extend the JSON-LD** — in the page's existing `businessJsonLd` builder, add when `rating_count > 0`:

```ts
aggregateRating: {
  "@type": "AggregateRating",
  ratingValue: summary.rating_avg,
  ratingCount: summary.rating_count,
},
```

- [ ] **Step 3: Write `reviews-section.tsx`** (server component — no interactivity needed for display):

```tsx
import { RatingStars } from "@agri/ui";

export function ReviewsSection({ summary, items }: { summary: RatingSummary; items: ReviewItem[] }) {
  return (
    <section aria-labelledby="reviews-h">
      <h2 id="reviews-h" className="text-[16px] font-extrabold">
        Reviews{summary.rating_count > 0 ? <> · <RatingStars value={summary.rating_avg ?? ""} /> ({summary.rating_count})</> : null}
      </h2>
      {items.length === 0 ? (
        <p className="text-[14px] text-muted">No reviews yet.</p>
      ) : (
        <ul className="grid gap-3">
          {items.map((r) => (
            <li key={r.id} className="rounded-lg border border-line p-3">
              <RatingStars value={r.rating} />
              {r.body?.en ? <p className="mt-1 text-[14px]">{r.body.en}</p> : null}
            </li>
          ))}
        </ul>
      )}
    </section>
  );
}
```

(Locale fallback `body.en` is fine for D18 — the page is not locale-routed yet. Token classes: copy from the page's existing cards.)

- [ ] **Step 4: Write `review-form.tsx`** — client island mirroring `lead-form.tsx`'s state machine: star-input as 5 radio buttons (`aria-label="Rate N of 5"`, `min-h-[44px]` each — there is no star-input component in `@agri/ui`, build it as a radio row rendering `★`), optional textarea (posted as `{ body: { en: text } }`), `useAgriUser` gate (unauthenticated → login link, same as RevealContact), POST `/api/reviews` with `{target_type: "business", target_id, rating, body}`; on 409 show "You already reviewed this."; on 201 show "Submitted — visible after moderation." (sets expectation: default pending).

- [ ] **Step 5: Render both in `page.tsx`**, verify `pnpm --filter @agri/web-agri lint && pnpm --filter @agri/web-agri build`.

- [ ] **Step 6: Commit**

```bash
git add "apps/web-agri/app/directory/businesses/[slug]"
git commit -m "feat(d18): business-page reviews UI + aggregateRating JSON-LD"
```

---

### Task 12: Frontend — minimal business inbox + my-inquiries pages

**Files:**
- Create: `apps/web-agri/app/business/inbox/page.tsx`, `inbox-client.tsx`
- Create: `apps/web-agri/app/account/inquiries/page.tsx`, `inquiries-client.tsx`

**Interfaces:**
- Consumes: `GET /directory/businesses` (owner list — existing route `list_my_businesses`), `GET /leads/inbox`, `GET /leads/inbox/stats`, `POST /leads/inquiries/{id}/responses`, `POST /leads/inquiries/{id}/close`, `GET /leads/mine` via the `/api/directory` and `/api/leads` proxies; `auth.getServerUser()` for the login gate.
- D20 note: these are deliberately minimal lists — the Business Console shell (D20) will mount the inbox; keep `inbox-client.tsx` self-contained (one component, props: none) so D20 can import it as the mount-point content.

- [ ] **Step 1: `business/inbox/page.tsx`** (server gate, claim-page pattern):

```tsx
import { redirect } from "next/navigation";
import { auth } from "../../../lib/auth";
import { InboxClient } from "./inbox-client";

export const metadata = { title: "Lead inbox", robots: { index: false } };

export default async function InboxPage() {
  const user = await auth.getServerUser();
  if (!user) redirect("/api/auth/login?next=/business/inbox");
  return (
    <main className="mx-auto max-w-3xl px-4 py-6">
      <h1 className="text-[20px] font-extrabold">Lead inbox</h1>
      <InboxClient />
    </main>
  );
}
```

- [ ] **Step 2: `inbox-client.tsx`** — `"use client"`. On mount: `GET /api/directory/businesses?limit=50` → business select (default first); then `GET /api/leads/inbox?business_id=...&limit=20` (+ cursor "Load more" button — cursor pagination, never offset) and `GET /api/leads/inbox/stats?business_id=...` (render "Avg response: Xh" when non-null). Each inquiry card: type badge, `payload.message` or milk fields, status, a reply `<textarea>` + button POSTing `/api/leads/inquiries/{id}/responses`, and a Close button POSTing `/close`. Empty state: "No leads yet." Use the 401-retry-once fetch helper pattern from `apps/web-admin/lib/api.ts` (copy the ~10-line `request()` into a local `lib`-style helper or inline). No business owned → "Claim your business to receive leads" with a link to `/directory`.

- [ ] **Step 3: `account/inquiries/page.tsx` + `inquiries-client.tsx`** — same gate (`next=/account/inquiries`); client lists `GET /api/leads/mine?limit=20` with "Load more"; each card shows type, business status chip (`new` → "Sent", `responded` → "Replied", `closed` → "Closed") and embedded `responses[].body`.

- [ ] **Step 4: Verify build, commit**

```bash
pnpm --filter @agri/web-agri lint && pnpm --filter @agri/web-agri build
git add apps/web-agri/app/business apps/web-agri/app/account/inquiries
git commit -m "feat(d18): minimal business lead inbox + submitter status view"
```

---

### Task 13: Frontend — web-admin review moderation queue

**Files:**
- Create: `apps/web-admin/app/reviews/page.tsx`, `apps/web-admin/app/reviews/reviews-manager.tsx`

**Interfaces:**
- Consumes: `GET /admin/reviews?status=pending`, `POST /admin/reviews/{id}/approve`, `POST /admin/reviews/{id}/reject` via the existing generic `/api/admin/[...path]` proxy and `lib/api.ts`; `QueueSection`-style pattern from `apps/web-admin/app/claims/claims-manager.tsx`.
- D22 note: the unified moderation queue later absorbs this page; keep it a single self-contained manager component like claims.

- [ ] **Step 1: Read `apps/web-admin/app/claims/page.tsx` + `claims-manager.tsx` in full.**

- [ ] **Step 2: Fork them** — `page.tsx` is the server gate (`redirect("/api/auth/login?next=/reviews")`); `reviews-manager.tsx` reuses the `QueueSection<T>` shape with `T = { id: string; target_type: string; rating: number; body: Record<string,string> | null; moderation_status: string; created_at: string }`, `listPath = "/reviews?status=pending"` mapped onto `getJson(\`/reviews?limit=20&status=pending&cursor=...\`)` against `/api/admin` (i.e. backend `/admin/reviews`), Approve button (Modal-confirmed), Reject button (Modal, note required ≥3 chars — `RejectIn.min_length=3`), `useToast` for outcomes (web-admin HAS ToastProvider). Card body: `★ {rating}` via `RatingStars`, `body.en` text, target type chip.

- [ ] **Step 3: Add a nav entry** if web-admin has a nav/sidebar listing Claims — mirror how `/claims` is linked (grep `"/claims"` in `apps/web-admin/app`).

- [ ] **Step 4: Verify + commit**

```bash
pnpm --filter @agri/web-admin lint && pnpm --filter @agri/web-admin build
git add apps/web-admin/app/reviews
git commit -m "feat(d18): web-admin review moderation queue"
```

---

### Task 14: Module docs, full gates, PR

**Files:**
- Modify: `backend/core/scripts/gen_module_claude.py` (directory module description — mention reviews + leads surfaces; the CLAUDE.md files are generated, never hand-edited), regen `backend/core/modules/directory/CLAUDE.md`.

- [ ] **Step 1: Update the generator** — find the directory module entry in `scripts/gen_module_claude.py`; extend its description with: reviews engine under `/reviews` + `/admin/reviews` (UGC pending default, aggregates), leads engine under `/leads` (guest submission, coverage×category routing, owner inbox), contact reveal (`/directory/branches/{id}/reveal`, capped + logged), events `review.approved`/`lead.created`/`lead.responded` on the directory stream. Run the generator (check its `python scripts/gen_module_claude.py` invocation/`--help`), commit the regenerated CLAUDE.md.

- [ ] **Step 2: Full local gate run** (from `backend/core`):

```
ruff format --check .
ruff check .
mypy .
lint-imports
python scripts/dump_public_routes.py --check
pytest -q -m "not slow"
```

Then, throwaway DB only: `ALEMBIC_DATABASE_URL=...agri_test python scripts/migrate_check.py`. Frontend: `pnpm --filter @agri/web-agri build && pnpm --filter @agri/web-admin build`. Fix anything red; commit fixes with `fix(d18): ...`.

- [ ] **Step 3: Verify the four non-negotiables have green named tests** — run and paste output for:

```
pytest -q tests/test_reviews_router.py::test_one_review_per_user_per_target tests/test_reviews_router.py::test_post_review_defaults_pending
pytest -q tests/test_coins_worker.py::test_review_approved_weekly_cap_five
pytest -q tests/test_contact_reveal.py::test_reveal_daily_cap_enforced tests/test_contact_reveal.py::test_reveal_log_line_has_no_phone
pytest -q tests/test_leads_routing.py::test_explicit_business_must_cover_pincode
```

- [ ] **Step 4: Push + PR** (targeting **dev**, never main):

```bash
git push -u origin feat/d18-reviews-leads
gh pr create --base dev --title "feat(d18): reviews + leads" --body "<summary: reviews engine (pending-default, one-per-target, review.approved -> coins 5/wk + notify), leads engine (guest submission, coverage(pincode)xcategory routing, inbox+responses+stats), capped DPDP-logged contact reveal + public phone strip, minimal web-agri/web-admin UI. Non-negotiable test list.>

🤖 Generated with [Claude Code](https://claude.com/claude-code)"
```

PR-title CI trap (memory): if the title check fails and you edit the title, re-run replays the stale title — push a no-op commit or use the check's re-trigger after editing.

---

## Self-review notes (already applied)

- **Spec coverage:** A → Tasks 1–4, 11, 13; B → Tasks 5–8, 10, 12; C → Task 9 (+ PII tests) ; D → Tasks 8, 12 (API + minimal UI; D20 mounts later) and D12 notify via Tasks 4, 7, 8. DO-NOTs: no payment fields anywhere; pending default (Task 1 UGCMixin + tests); cap-first ordering in reveal route; all lists keyset-paginated.
- **Deviations to flag in the PR body:** (1) both engines live in `modules/directory` (import-linter forces it; `modules/leads` stub reserved for E4); (2) auto-route picks nearest single business, no fan-out; (3) review amount 20 coins — owner-tunable via coins admin.
- **Type consistency:** event payload keys (`user_id`, `review_id`, `inquiry_id`, `vars`) match between producers (Tasks 3, 7, 8) and consumers (Task 4); `RoutedBusiness` fields match usage in Task 7; `InquiryStatus`/`InboxStatsOut` names match between Tasks 7 schemas and Task 8 routes; idem key literal `review:{review_id}` matches spec and worker.
