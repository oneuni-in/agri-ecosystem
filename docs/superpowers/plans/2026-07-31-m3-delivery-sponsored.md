# M3 — Delivery Blend + Sponsored Listings Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Delivery engine blend (global+local campaigns with a local boost, serve budgets, per-creative frequency caps, why-served logging) plus sponsored listing cards injected at the render layer into web-milk result lists, and an organic-only "Recommended" rail.

**Architecture:** All delivery logic stays in the ads ENGINE (`backend/core/modules/ads`) — vertical context arrives only via `slot_key` + `category` params. Sponsored listings reuse the existing `/ads/serve` wire contract with a new slot key `milk_sponsored_listing`; injection happens server-side in web-milk pages (organic arrays, cursors, JSON-LD untouched). "Recommended" is a directory-module ranking function — the label's only source.

**Tech Stack:** FastAPI + SQLAlchemy async + Alembic (backend/core), Next.js 15 / React 19 pnpm monorepo (apps/web-milk, packages/ui), vitest (packages/ui), pytest, Playwright (e2e).

## Global Constraints

- Branch `feat/m3-delivery-sponsored` from `dev`. NEVER commit to dev/main. Conventional commits. PR targets dev.
- Endpoints private+rate-limited by default; new public routes require `backend/core/public_routes.txt` + `tests/test_main.py` updates in the same PR (M3 adds NO new routes).
- ads module never imports other modules (import-linter gate); directory module likewise. Cross-module reads go through `shared/lookups.py`.
- Cursor pagination only — OFFSET is test-gated. All IDs UUIDv7.
- Tokens only in UI — no raw hex (`pnpm check:hex` gate). Sponsored is ALWAYS labeled "★ Sponsored" (Badge `sponsored` variant type-forbids children).
- Toolchain: Node 24 / pnpm 11 / Tailwind 3; backend host Python 3.12, no uv, no gh CLI (open PRs via credential-fill API).
- Before push: `mypy`, `ruff check`, `ruff format`, `lint-imports`, full pytest (backend); `pnpm -w typecheck`, `lint`, `test`, `check:hex` (frontend).
- Run `ruff format` per task, not at the end (D16 lesson).
- Non-negotiables (spec): NN1 blend test · NN2 per-category independence · NN3 organic order identical with sponsorship on/off · NN4 every paid unit carries SponsoredBadge (snapshot).

## Design decisions locked in

1. **Budget = serve credits.** `ads.campaigns.budget_serves_total` (NULL = unlimited, the default — house ads unaffected) + `budget_serves_used`. In-budget is a SQL predicate in `eligible_placements`; consumption is an atomic conditional UPDATE at serve time (threat: budget race).
2. **Blend discriminator.** `geo_match_rung()` returns `"global"` (no geo rung declared) or the matched rung `"pincode"|"district"|"state"`, or `None` (no match). `Candidate` NamedTuple `(placement, creative, campaign, rung)` flows through serve. `pick_weighted` multiplies `Placement.weight` by `settings.ads_local_boost` (default 2.0) for non-global rungs.
3. **Freq cap re-keyed per creative** (`ads:freq:{viewer}:{creative_id}:{YYYYMMDD}`) — spec says per user-session per creative; the daily-rotating `viewer_hash` IS the session pseudonym.
4. **Delivery log** `ads.delivery_decisions`: non-partitioned (sampled volume; `directory.profile_views` precedent), append-only by grant + the existing `ads.forbid_tracking_mutation()` trigger. Sampled via `settings.ads_delivery_log_sample` (default 0.1). Row: campaign/placement/creative ids, slot_key, pincode, category, why_served, viewer_hash, occurred_at — no user ids (threat: delivery-log PII).
5. **Sponsored listings** = existing `ServedAdOut` on new slot `milk_sponsored_listing`, fetched SERVER-SIDE in web-milk pages (forwarding `x-forwarded-for` + `user-agent`), injected at render into display flow at page positions 1 and 6 (indexes 0, 5), max 2. Organic arrays/cursor/JSON-LD byte-identical. `SponsoredListingCard` is a client island (visibility-gated impression + click beacon, D18-safe: no contact data on the wire).
6. **Geo-spoof mitigation** at the BFF: `/api/ads/serve` overrides the `pincode` param from the `agri_loc` cookie (the D19 context; profile pincode wins post-login because LiveLocationPill syncs the cookie from `/identity/location`).
7. **Recommended** = `modules/directory/recommended.py:rank_recommended()` — the ONLY label source. Signals: verified (+3.0), rating (`avg × min(count,5)/5`), first-response time (<4h +2.0, <24h +1.0), coverage freshness (≤30d +1.0). `MIN_SCORE = 3.0`, top 3. `subscription_tier` and campaign data must never enter. Rail surfaces on the unfiltered first-page covered landing view via `MilkHomeOut.recommended`.
8. **VendorResults ambiguity resolved:** inject into the FIRST non-empty section (vendors, else brands); CategoryResults and search inject into their single list.

---

### Task 0: Branch + worktree

- [ ] **Step 1:** Use superpowers:using-git-worktrees to create an isolated worktree for branch `feat/m3-delivery-sponsored` cut from `dev` (repo already has `.worktrees/`). All subsequent tasks run inside it.
- [ ] **Step 2:** Confirm baseline is green enough to build on: `cd backend/core && python -m pytest tests/test_ads_serve.py -q` (uses the dockerised test Postgres on port 45432 — see D13 memory — and Redis; start `docker compose` services if not running).

---

### Task 1: Migration 0031 — campaign serve budgets + delivery_decisions

**Files:**
- Create: `backend/core/alembic/versions/0031_ads_delivery_v1.py`
- Modify: `backend/core/modules/ads/models.py` (Campaign + new DeliveryDecision)
- Modify: `backend/core/settings.py:143` (after `ads_freq_cap_per_day`)
- Test: `backend/core/tests/test_ads_migration.py` (extend)

**Interfaces:**
- Produces: `Campaign.budget_serves_total: int | None`, `Campaign.budget_serves_used: int`, `DeliveryDecision` ORM model, `settings.ads_local_boost: float = 2.0`, `settings.ads_delivery_log_sample: float = 0.1`.

- [ ] **Step 1: Write failing migration/model tests** — append to `tests/test_ads_migration.py`, mirroring its existing style (raw SQL over `db_session`):

```python
async def test_campaign_budget_columns(db_session: AsyncSession) -> None:
    cols = {
        r[0]
        for r in await db_session.execute(
            text(
                "SELECT column_name FROM information_schema.columns "
                "WHERE table_schema='ads' AND table_name='campaigns'"
            )
        )
    }
    assert {"budget_serves_total", "budget_serves_used"} <= cols


async def test_delivery_decisions_append_only(db_session: AsyncSession) -> None:
    await db_session.execute(
        text(
            "INSERT INTO ads.delivery_decisions "
            "(id, campaign_id, placement_id, creative_id, slot_key, pincode, category,"
            " why_served, viewer_hash, occurred_at) "
            "VALUES (gen_random_uuid(), gen_random_uuid(), gen_random_uuid(),"
            " gen_random_uuid(), 'milk_sponsored_listing', '641001', NULL,"
            " 'local_pincode', 'vh', now())"
        )
    )
    with pytest.raises(DBAPIError):
        await db_session.execute(text("UPDATE ads.delivery_decisions SET slot_key = 'x'"))
```

(Reuse the file's existing imports; add `from sqlalchemy.exc import DBAPIError` if absent. If `gen_random_uuid()` is unavailable in the file's conventions, use literal uuid4 hex strings.)

- [ ] **Step 2:** Run: `python -m pytest tests/test_ads_migration.py -q` — expect FAIL (missing columns/table).
- [ ] **Step 3: Migration** `0031_ads_delivery_v1.py` (`revision="0031"`, `down_revision="0030"`), following 0022's conventions (`pk_column` import path as used by `0025_vendor_dashboard.py`):

```python
"""M3: campaign serve budgets + append-only sampled delivery-decision log."""

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

from shared.migrations import pk_column

revision: str = "0031"
down_revision: str | None = "0030"


def upgrade() -> None:
    op.add_column(
        "campaigns", sa.Column("budget_serves_total", sa.Integer(), nullable=True), schema="ads"
    )
    op.add_column(
        "campaigns",
        sa.Column("budget_serves_used", sa.Integer(), nullable=False, server_default="0"),
        schema="ads",
    )
    op.create_check_constraint(
        "ck_ads_campaigns_budget_total",
        "campaigns",
        "budget_serves_total IS NULL OR budget_serves_total >= 0",
        schema="ads",
    )
    op.create_check_constraint(
        "ck_ads_campaigns_budget_used", "campaigns", "budget_serves_used >= 0", schema="ads"
    )
    op.create_table(
        "delivery_decisions",
        pk_column(),
        sa.Column("campaign_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("placement_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("creative_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("slot_key", sa.Text(), nullable=False),
        sa.Column("pincode", sa.Text(), nullable=True),
        sa.Column("category", sa.Text(), nullable=True),
        sa.Column("why_served", sa.Text(), nullable=False),
        sa.Column("viewer_hash", sa.Text(), nullable=False),
        sa.Column("occurred_at", sa.DateTime(timezone=True), nullable=False),
        schema="ads",
    )
    op.create_index(
        "ix_ads_delivery_decisions_campaign_day",
        "delivery_decisions",
        ["campaign_id", "occurred_at"],
        schema="ads",
    )
    # Append-only: same trigger fn 0022 installed for impressions/clicks,
    # plus belt-and-braces grant revocation (coins 0015 precedent).
    op.execute(
        "CREATE TRIGGER delivery_decisions_append_only BEFORE UPDATE OR DELETE "
        "ON ads.delivery_decisions FOR EACH ROW "
        "EXECUTE FUNCTION ads.forbid_tracking_mutation()"
    )
    op.execute("GRANT SELECT, INSERT ON ads.delivery_decisions TO app_rt")
    op.execute("REVOKE UPDATE, DELETE ON ads.delivery_decisions FROM app_rt")


def downgrade() -> None:
    op.drop_table("delivery_decisions", schema="ads")
    op.drop_constraint("ck_ads_campaigns_budget_used", "campaigns", schema="ads")
    op.drop_constraint("ck_ads_campaigns_budget_total", "campaigns", schema="ads")
    op.drop_column("campaigns", "budget_serves_used", schema="ads")
    op.drop_column("campaigns", "budget_serves_total", schema="ads")
```

Check 0022/0025 for whether grants target `app_rt` conditionally (some migrations guard `DO $$ ... IF EXISTS role`) — copy that guard style if present.

- [ ] **Step 4: Models** — in `modules/ads/models.py`, add to `Campaign`:

```python
    budget_serves_total: Mapped[int | None] = mapped_column(sa.Integer, nullable=True)
    budget_serves_used: Mapped[int] = mapped_column(sa.Integer, nullable=False, server_default="0")
```

(match the file's existing import idiom — it may import column types directly rather than `sa.`) and append:

```python
class DeliveryDecision(UUIDv7PKMixin, Base):
    """M3.E why-served log: append-only BY GRANT + trigger, SAMPLED at serve
    time (settings.ads_delivery_log_sample). viewer_hash is the daily-rotating
    pseudonym - never a user id (threat model: delivery-log PII)."""

    __tablename__ = "delivery_decisions"
    __table_args__ = (
        Index("ix_ads_delivery_decisions_campaign_day", "campaign_id", "occurred_at"),
        {"schema": "ads"},
    )

    campaign_id: Mapped[uuid.UUID] = mapped_column(postgresql.UUID(as_uuid=True), nullable=False)
    placement_id: Mapped[uuid.UUID] = mapped_column(postgresql.UUID(as_uuid=True), nullable=False)
    creative_id: Mapped[uuid.UUID] = mapped_column(postgresql.UUID(as_uuid=True), nullable=False)
    slot_key: Mapped[str] = mapped_column(Text, nullable=False)
    pincode: Mapped[str | None] = mapped_column(Text, nullable=True)
    category: Mapped[str | None] = mapped_column(Text, nullable=True)
    why_served: Mapped[str] = mapped_column(Text, nullable=False)
    viewer_hash: Mapped[str] = mapped_column(Text, nullable=False)
    occurred_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
```

- [ ] **Step 5: Settings** — in `settings.py` after `ads_freq_cap_per_day`:

```python
    # M3 delivery
    ads_local_boost: float = 2.0  # local-targeted placements × this in rotation (item 8)
    ads_delivery_log_sample: float = 0.1  # why-served log sampling rate (M3.E)
```

- [ ] **Step 6:** `alembic upgrade head` against the test DB happens inside conftest; just run `python -m pytest tests/test_ads_migration.py -q` — expect PASS. Also run `python -m pytest tests/test_ads_serve.py -q` (no regressions).
- [ ] **Step 7:** `ruff format . && ruff check .` then commit: `feat(m3): campaign serve budgets + delivery_decisions table`

---

### Task 2: Admin budget plumbing (backend)

**Files:**
- Modify: `backend/core/modules/ads/schemas.py:29-54` (CampaignIn/CampaignOut)
- Modify: `backend/core/modules/ads/admin_router.py:61-77` (create_campaign)
- Test: `backend/core/tests/test_ads_admin.py` (extend)

**Interfaces:**
- Produces: wire fields `budget_serves_total: int | None` (in+out), `budget_serves_used: int` (out).

- [ ] **Step 1: Failing test** — in `test_ads_admin.py`, copy the existing create-campaign test's auth/setup pattern and add:

```python
async def test_campaign_budget_roundtrip(...existing fixtures...) -> None:
    resp = await <staff_client>.post(
        "/admin/ads/campaigns",
        json={ ...existing valid body..., "budget_serves_total": 100 },
    )
    assert resp.status_code == 201
    body = resp.json()
    assert body["budget_serves_total"] == 100
    assert body["budget_serves_used"] == 0

    resp2 = await <staff_client>.post(
        "/admin/ads/campaigns",
        json={ ...existing valid body... },  # no budget key
    )
    assert resp2.json()["budget_serves_total"] is None
```

- [ ] **Step 2:** Run: `python -m pytest tests/test_ads_admin.py -q` — expect FAIL (unknown field ignored / missing in response).
- [ ] **Step 3:** Schemas — `CampaignIn` gains `budget_serves_total: Annotated[int, Field(ge=0)] | None = None`; `CampaignOut` gains `budget_serves_total: int | None` and `budget_serves_used: int`. `create_campaign` passes `budget_serves_total=body.budget_serves_total` into the `Campaign(...)` constructor.
- [ ] **Step 4:** Run: `python -m pytest tests/test_ads_admin.py -q` — PASS.
- [ ] **Step 5:** `ruff format . && ruff check .` · commit `feat(m3): admin budget_serves_total on campaigns`

---

### Task 3: Engine blend — geo rung + Candidate + local boost (NN1)

**Files:**
- Modify: `backend/core/modules/ads/service.py` (`geo_matches` → `geo_match_rung`, `eligible_placements`, `pick_weighted`)
- Modify: `backend/core/modules/ads/router.py:75-96` (serve loop uses Candidate + boost)
- Test: `backend/core/tests/test_ads_serve.py`

**Interfaces:**
- Consumes: `Campaign.budget_serves_total` (Task 1 — carried on Candidate for Task 4).
- Produces:
  - `class Candidate(NamedTuple): placement: Placement; creative: Creative; campaign: Campaign; rung: str`
  - `geo_match_rung(geo_target, *, pincode, district_lgd, state_lgd) -> str | None` (`"global"|"pincode"|"district"|"state"|None`)
  - `eligible_placements(...) -> list[Candidate]` (same kwargs as today)
  - `pick_weighted(candidates: list[Candidate], rand, *, local_boost: float = 1.0) -> Candidate`

- [ ] **Step 1: Failing tests** — add to `test_ads_serve.py` (reuse its `api`, `ads_redis`, `tn_geo_sample`, `_enable_ads`, `_seed_ad` helpers; `COIMBATORE_PINCODE = "641001"`; add `DELHI_PINCODE = "110001"` — not in the TN geo sample, so it resolves to no district):

```python
async def test_blend_global_and_local_serve_together(
    api, db_session, ads_redis, tn_geo_sample
) -> None:
    """NON-NEGOTIABLE 1: a global (ALL-pincode) campaign and a 641001-local
    campaign BOTH serve at 641001; the local one is absent at 110001."""
    await _enable_ads(db_session)
    global_p = await _seed_ad(db_session, geo_target={})
    local_p = await _seed_ad(db_session, geo_target={"pincodes": [COIMBATORE_PINCODE]})

    resp = await api.get(
        "/ads/serve",
        params={"slot": "directory_browse", "pincode": COIMBATORE_PINCODE, "count": 5},
    )
    assert resp.status_code == 200
    at_local = {ad["placement_id"] for ad in resp.json()["ads"]}
    assert {str(global_p.id), str(local_p.id)} <= at_local

    resp = await api.get(
        "/ads/serve", params={"slot": "directory_browse", "pincode": DELHI_PINCODE, "count": 5}
    )
    at_remote = {ad["placement_id"] for ad in resp.json()["ads"]}
    assert str(local_p.id) not in at_remote
    assert str(global_p.id) in at_remote


async def test_local_boost_share_of_voice(
    api, db_session, ads_redis, tn_geo_sample, monkeypatch
) -> None:
    """Equal placement weights: the 641001-targeted placement should win
    ~2/3 of single-ad serves under the default ads_local_boost=2.0."""
    await _enable_ads(db_session)
    await _seed_ad(db_session, geo_target={})
    local_p = await _seed_ad(db_session, geo_target={"pincodes": [COIMBATORE_PINCODE]})
    # copy the monkeypatching from test_share_of_voice_weighted_rotation:
    # seeded _rng, always-true under_freq_cap, raised RATE_LIMIT_REQUESTS
    ...
    wins = 0
    for _ in range(200):
        resp = await api.get(
            "/ads/serve", params={"slot": "directory_browse", "pincode": COIMBATORE_PINCODE}
        )
        if resp.json()["ads"][0]["placement_id"] == str(local_p.id):
            wins += 1
    assert 0.55 <= wins / 200 <= 0.80


async def test_ghee_campaign_never_serves_on_paneer_page(
    api, db_session, ads_redis, tn_geo_sample
) -> None:
    """NON-NEGOTIABLE 2: category dimension is independent per slot instance."""
    await _enable_ads(db_session)
    ghee_p = await _seed_ad(db_session, geo_target={"categories": ["ghee"]})

    resp = await api.get(
        "/ads/serve",
        params={
            "slot": "directory_browse",
            "pincode": COIMBATORE_PINCODE,
            "category": "paneer",
            "count": 5,
        },
    )
    assert str(ghee_p.id) not in {ad["placement_id"] for ad in resp.json()["ads"]}

    resp = await api.get(
        "/ads/serve",
        params={
            "slot": "directory_browse",
            "pincode": COIMBATORE_PINCODE,
            "category": "ghee",
            "count": 5,
        },
    )
    assert str(ghee_p.id) in {ad["placement_id"] for ad in resp.json()["ads"]}
```

For the boost test, copy the exact monkeypatch block from `test_share_of_voice_weighted_rotation` (`test_ads_serve.py:338-375`): `monkeypatch.setattr(router_module, "_rng", random.Random(42))`, an `under_freq_cap` stub returning True, and the raised rate-limit — that block is proven against this API fixture.

- [ ] **Step 2:** Run: `python -m pytest tests/test_ads_serve.py -k "blend or boost or ghee" -q` — blend/ghee may PASS already (existing engine handles union + category); boost must FAIL (no boost yet). That's expected: NN1/NN2 become regression locks.
- [ ] **Step 3: Implement** in `service.py`:

```python
class Candidate(NamedTuple):
    """One servable (placement, newest-approved-creative) pair. `rung` is the
    geo rung that matched - the blend discriminator (M3.A): "global" for
    untargeted placements, else the most specific matched rung. Feeds both
    the local-boost rotation and the why-served log."""

    placement: Placement
    creative: Creative
    campaign: Campaign
    rung: str


def geo_match_rung(
    geo_target: dict[str, Any],
    *,
    pincode: str | None,
    district_lgd: int | None,
    state_lgd: int | None,
) -> str | None:
    """None = no match. "global" = no geo rung declared (serves everywhere -
    the M2 `categories` key is NOT a geo rung). Otherwise the most specific
    declared rung that matched; unknown viewer location (pincode=None)
    matches only geo-untargeted placements - fail closed."""
    if not any(geo_target.get(k) for k in _GEO_RUNGS):
        return "global"
    pincodes = geo_target.get("pincodes") or []
    if pincode is not None and pincode in pincodes:
        return "pincode"
    district = geo_target.get("district")
    if district is not None and district_lgd is not None and district == district_lgd:
        return "district"
    state = geo_target.get("state")
    if state is not None and state_lgd is not None and state == state_lgd:
        return "state"
    return None


def geo_matches(
    geo_target: dict[str, Any],
    *,
    pincode: str | None,
    district_lgd: int | None,
    state_lgd: int | None,
) -> bool:
    return (
        geo_match_rung(
            geo_target, pincode=pincode, district_lgd=district_lgd, state_lgd=state_lgd
        )
        is not None
    )
```

`eligible_placements` changes: select `Placement, Creative, Campaign` (whole entity), keep every existing predicate, key the `servable` map on `campaign.advertiser_business_id`, and build `Candidate(placement, creative, campaign, rung)` where `rung = geo_match_rung(...)`; skip when `rung is None or not category_matches(...)`. Return type `list[Candidate]`.

`pick_weighted`:

```python
def pick_weighted(
    candidates: list[Candidate], rand: random.Random, *, local_boost: float = 1.0
) -> Candidate:
    """Weighted rotation with the M3 blend boost: local-targeted candidates
    (any matched geo rung) count local_boost x their placement weight so
    village advertisers aren't drowned by national ALL-pincode brands."""
    weights = [
        c.placement.weight * (local_boost if c.rung != "global" else 1.0) for c in candidates
    ]
    return rand.choices(candidates, weights=weights, k=1)[0]
```

Add `from typing import NamedTuple` import. In `router.py`, rewrite the serve loop to use Candidates (final form lands in Task 5; intermediate form here):

```python
    candidates = await service.eligible_placements(
        session, slot_key=slot, pincode=pincode, category=category, today=now.date()
    )
    pool: list[service.Candidate] = []
    for cand in candidates:
        if await service.under_freq_cap(
            viewer, cand.placement.id, cap=settings.ads_freq_cap_per_day, now=now
        ):
            pool.append(cand)
    served: list[ServedAdOut] = []
    while pool and len(served) < count:
        cand = service.pick_weighted(pool, _rng, local_boost=settings.ads_local_boost)
        pool = [c for c in pool if c.placement.id != cand.placement.id]
        try:
            service.validate_target_url(cand.creative.target_url)
        except ValueError:
            continue
        await service.record_serve(viewer, cand.placement.id, now=now)
        served.append(
            _to_served(cand.placement, cand.creative, locale=locale, base=settings.media_public_base_url)
        )
```

Fix any test that destructures 2-tuples from `eligible_placements` (grep `eligible_placements` across tests).

- [ ] **Step 4:** Run: `python -m pytest tests/test_ads_serve.py tests/test_ads_beacons.py -q` — all PASS (including the M2 suite lines 412-513 and the old share-of-voice test, which stubs `under_freq_cap` — its stub signature must still match).
- [ ] **Step 5:** `ruff format . && ruff check . && mypy .` · commit `feat(m3): global+local blend with configurable local boost`

---

### Task 4: In-budget predicate + atomic consume (threat: budget race)

**Files:**
- Modify: `backend/core/modules/ads/service.py` (predicate + `consume_budget`)
- Modify: `backend/core/modules/ads/router.py` (consume in loop + commit)
- Test: `backend/core/tests/test_ads_serve.py`, `backend/core/tests/test_ads_storm.py`

**Interfaces:**
- Produces: `async consume_budget(session, campaign: Campaign) -> bool`.

- [ ] **Step 1: Failing tests:**

```python
# test_ads_serve.py
async def test_budget_exhaustion_stops_serving(api, db_session, ads_redis, tn_geo_sample) -> None:
    await _enable_ads(db_session)
    placement = await _seed_ad(db_session, geo_target={})
    campaign = await db_session.get(Campaign, placement.campaign_id)
    campaign.budget_serves_total = 2
    await db_session.flush()

    ids = []
    for _ in range(3):
        resp = await api.get(
            "/ads/serve", params={"slot": "directory_browse", "pincode": COIMBATORE_PINCODE}
        )
        ids.append([ad["placement_id"] for ad in resp.json()["ads"]])
    assert ids[0] and ids[1]  # two credits -> two serves
    assert ids[2] == []       # out of budget -> excluded by the SQL predicate
    await db_session.refresh(campaign)
    assert campaign.budget_serves_used == 2
```

(`ads_freq_cap_per_day` default is 3, so the cap does not interfere; import `Campaign` from `modules.ads.models` at top of file if not present.)

```python
# test_ads_storm.py — same engine/maker scaffolding as the existing storm test
@pytest.mark.slow
async def test_budget_race_never_oversells(database_url: str) -> None:
    """M3 threat model: concurrent serves must not spend more credits than
    exist. 100 racers, 50 credits -> exactly 50 winners, used == 50."""
    engine = create_async_engine(database_url, poolclass=NullPool)
    maker = async_sessionmaker(engine, expire_on_commit=False)
    campaign_id = uuid.uuid4()
    try:
        async with maker() as s:
            s.add(
                Campaign(
                    id=campaign_id,
                    advertiser_business_id=uuid.uuid4(),
                    name="budget race",
                    status="active",
                    budget_display="",
                    budget_serves_total=50,
                    flight_start=datetime.now(UTC).date(),
                    flight_end=datetime.now(UTC).date(),
                )
            )
            await s.commit()

        sem = asyncio.Semaphore(CONCURRENCY)

        async def spend() -> bool:
            async with sem, maker() as s:
                campaign = await s.get(Campaign, campaign_id)
                assert campaign is not None
                ok = await service.consume_budget(s, campaign)
                await s.commit()
                return ok

        results = await asyncio.gather(*(spend() for _ in range(100)))
        assert sum(results) == 50
        async with maker() as s:
            used = await s.scalar(
                text("SELECT budget_serves_used FROM ads.campaigns WHERE id = :c"),
                {"c": campaign_id},
            )
        assert used == 50
    finally:
        await engine.dispose()
```

(add `from modules.ads import service` to the storm file's imports.)

- [ ] **Step 2:** Run: `python -m pytest tests/test_ads_serve.py -k budget -q` — FAIL (`consume_budget` undefined / no predicate).
- [ ] **Step 3: Implement.** In `eligible_placements`'s WHERE add (import `or_` from sqlalchemy):

```python
                or_(
                    Campaign.budget_serves_total.is_(None),
                    Campaign.budget_serves_used < Campaign.budget_serves_total,
                ),
```

New service function:

```python
async def consume_budget(session: AsyncSession, campaign: Campaign) -> bool:
    """Atomic serve-credit decrement (M3 threat: budget race on concurrent
    serves). Unlimited campaigns (budget_serves_total IS NULL) never touch
    the row - no hot-row contention on house ads. The conditional UPDATE is
    the atomicity: a concurrent loser blocks on the row lock, re-evaluates
    the WHERE against the committed value, and matches zero rows once the
    last credit is gone - it must then NOT serve."""
    if campaign.budget_serves_total is None:
        return True
    result = await session.execute(
        update(Campaign)
        .where(
            Campaign.id == campaign.id,
            Campaign.budget_serves_used < Campaign.budget_serves_total,
        )
        .values(budget_serves_used=Campaign.budget_serves_used + 1)
    )
    return result.rowcount == 1
```

(import `update` from sqlalchemy). In the router loop, after the URL re-check:

```python
        if not await service.consume_budget(session, cand.campaign):
            continue  # lost the race for the last credit - never over-serve
        dirty = dirty or cand.campaign.budget_serves_total is not None
```

initialize `dirty = False` before the loop and after it:

```python
    if dirty:
        await session.commit()
```

- [ ] **Step 4:** Run: `python -m pytest tests/test_ads_serve.py -q` then `python -m pytest tests/test_ads_storm.py -m slow -q` (needs the isolated storm DB — see D22 memory `storm-needs-isolated-DB`; run it the way `test_ads_storm.py`'s docstring says). All PASS.
- [ ] **Step 5:** `ruff format . && ruff check . && mypy .` · commit `feat(m3): in-budget predicate + atomic serve-credit decrement`

---

### Task 5: Frequency cap per creative + delivery-decision logging

**Files:**
- Modify: `backend/core/modules/ads/service.py` (`_freq_key`/`under_freq_cap`/`record_serve` re-key; new `log_delivery`)
- Modify: `backend/core/modules/ads/router.py` (creative-keyed cap; log call)
- Test: `backend/core/tests/test_ads_serve.py`

**Interfaces:**
- Produces: `under_freq_cap(viewer, creative_id, *, cap, now)`, `record_serve(viewer, creative_id, *, now)`, `log_delivery(session, *, candidate, slot_key, pincode, category, viewer, now, rand) -> bool`.

- [ ] **Step 1: Failing tests:**

```python
async def test_freq_cap_keyed_per_creative(api, db_session, ads_redis, tn_geo_sample) -> None:
    """M3.A: cap is per user-session (daily viewer_hash) per CREATIVE."""
    await _enable_ads(db_session)
    placement = await _seed_ad(db_session, geo_target={})
    creative_id = (
        await db_session.scalar(
            select(Creative.id).where(Creative.campaign_id == placement.campaign_id)
        )
    )
    resp = await api.get("/ads/serve", params={"slot": "directory_browse"})
    assert resp.json()["ads"]
    keys = [k async for k in get_redis().scan_iter(match="ads:freq:*")]
    assert len(keys) == 1
    assert str(creative_id) in keys[0].decode() if isinstance(keys[0], bytes) else keys[0]


async def test_delivery_log_written_with_why_served(
    api, db_session, ads_redis, tn_geo_sample, monkeypatch
) -> None:
    """M3.E: sampled append-only why-served log; local rung recorded."""
    monkeypatch.setattr(get_settings(), "ads_delivery_log_sample", 1.0)
    await _enable_ads(db_session)
    await _seed_ad(db_session, geo_target={"pincodes": [COIMBATORE_PINCODE]})
    resp = await api.get(
        "/ads/serve", params={"slot": "directory_browse", "pincode": COIMBATORE_PINCODE}
    )
    assert resp.json()["ads"]
    row = (
        await db_session.execute(
            text("SELECT why_served, pincode, category, viewer_hash FROM ads.delivery_decisions")
        )
    ).one()
    assert row.why_served == "local_pincode"
    assert row.pincode == COIMBATORE_PINCODE
    assert len(row.viewer_hash) == 64  # sha256 pseudonym, never a raw ip/user id


async def test_delivery_log_sampling_zero_writes_nothing(
    api, db_session, ads_redis, tn_geo_sample, monkeypatch
) -> None:
    monkeypatch.setattr(get_settings(), "ads_delivery_log_sample", 0.0)
    await _enable_ads(db_session)
    await _seed_ad(db_session, geo_target={})
    await api.get("/ads/serve", params={"slot": "directory_browse"})
    count = await db_session.scalar(text("SELECT count(*) FROM ads.delivery_decisions"))
    assert count == 0
```

(`get_settings` is `@lru_cache`d, so `monkeypatch.setattr(get_settings(), ...)` mutates the shared instance and auto-restores — check whether existing tests already use this pattern and copy it; imports: `get_settings` from `settings`, `get_redis` from `shared.cache`, `text` from sqlalchemy.)

- [ ] **Step 2:** Run: `python -m pytest tests/test_ads_serve.py -k "freq_cap_keyed or delivery_log" -q` — FAIL.
- [ ] **Step 3: Implement.** Rename the freq-cap key param from `placement_id` to `creative_id` in `_freq_key`, `under_freq_cap`, `record_serve` (key string becomes `f"ads:freq:{viewer}:{creative_id}:{now:%Y%m%d}"`). Router passes `cand.creative.id` to both. Add:

```python
def log_delivery(
    session: AsyncSession,
    *,
    candidate: Candidate,
    slot_key: str,
    pincode: str | None,
    category: str | None,
    viewer: str,
    now: datetime,
    rand: random.Random,
) -> bool:
    """M3.E: append-only, SAMPLED why-served row for advertiser analytics
    (M5) and dispute resolution. Returns True when a row was staged (the
    caller owns the commit). pincode/category are serve context - fine to
    keep; viewer is the daily-rotating hash - no other user identifier."""
    rate = get_settings().ads_delivery_log_sample
    if rate <= 0 or rand.random() >= rate:
        return False
    session.add(
        DeliveryDecision(
            campaign_id=candidate.campaign.id,
            placement_id=candidate.placement.id,
            creative_id=candidate.creative.id,
            slot_key=slot_key,
            pincode=pincode,
            category=category,
            why_served="global" if candidate.rung == "global" else f"local_{candidate.rung}",
            viewer_hash=viewer,
            occurred_at=now,
        )
    )
    return True
```

Router: after the successful `consume_budget`:

```python
        if service.log_delivery(
            session,
            candidate=cand,
            slot_key=slot,
            pincode=pincode,
            category=category,
            viewer=viewer,
            now=now,
            rand=_rng,
        ):
            dirty = True
        await service.record_serve(viewer, cand.creative.id, now=now)
```

(import `DeliveryDecision` in service.py.) Update the old freq-cap tests that pass placement ids and the share-of-voice stub if its signature is positional.

- [ ] **Step 4:** Run full ads suite: `python -m pytest tests/test_ads_serve.py tests/test_ads_beacons.py tests/test_ads_admin.py -q` — PASS.
- [ ] **Step 5:** `ruff format . && ruff check . && mypy .` · commit `feat(m3): per-creative freq cap + sampled why-served delivery log`

---

### Task 6: `milk_sponsored_listing` slot + house seed flag

**Files:**
- Modify: `backend/core/modules/ads/service.py:20-31` (SLOT_KEYS)
- Modify: `backend/core/scripts/seed_house_ads.py`
- Modify: `backend/core/tests/test_ads_serve.py` (`test_milk_slot_keys_are_registered`)
- Modify: `scripts/e2e-api.mjs` (seed flag)

- [ ] **Step 1:** Extend `test_milk_slot_keys_are_registered` (test_ads_serve.py:412+) to include `"milk_sponsored_listing"`. Run — FAIL.
- [ ] **Step 2:** Add `"milk_sponsored_listing"` to `SLOT_KEYS` (one line, per the naming-contract comment). Run — PASS.
- [ ] **Step 3:** In `seed_house_ads.py` add a CLI flag `--with-sponsored-listing` (default off — a house card at position 1 of every list is an e2e determinism tool, not a prod default). When set, after the normal slots loop call `_ensure_house_ad` once:

```python
    if with_sponsored_listing:
        await _ensure_house_ad(
            session,
            advertiser_id=advertiser_id,
            slot_key="milk_sponsored_listing",
            tag="discover",
            copy={
                "en": {"title": "Milk.in Partner Dairy", "body": "Fresh local milk, delivered"},
                "ta": {"title": "Milk.in கூட்டாளர் பால் பண்ணை", "body": "புதிய உள்ளூர் பால்"},
                "hi": {"title": "Milk.in पार्टनर डेयरी", "body": "ताज़ा स्थानीय दूध"},
            },
            target_url=f"{base_url}/coimbatore/641001",
        )
```

Thread the flag through `run(...)` and argparse exactly the way `--enable-flag` is threaded (no prod guard needed — it seeds a normal campaign).

- [ ] **Step 4:** In `scripts/e2e-api.mjs`, append `"--with-sponsored-listing"` to the existing `seed_house_ads.py` argv (next to `--enable-flag --reset-caps`).
- [ ] **Step 5:** Sanity: `python -m pytest tests/test_ads_serve.py -q` — PASS. `ruff format . && ruff check .` · commit `feat(m3): milk_sponsored_listing slot + house seed flag`

---### Task 7: Recommended ranking fn + milk-home integration (M3.C)

**Files:**
- Create: `backend/core/modules/directory/recommended.py`
- Modify: `backend/core/modules/directory/milk_home.py` (`MilkHomeResult.recommended`, compute in `milk_home()`)
- Modify: `backend/core/modules/directory/milk_home_schemas.py` (`MilkHomeOut.recommended`)
- Test: create `backend/core/tests/test_milk_home_recommended.py`

**Interfaces:**
- Produces: `rank_recommended(session, cards: Sequence[MilkCard], *, now: datetime) -> list[uuid.UUID]` (ordered, filtered, ≤3); `MilkHomeOut.recommended: list[MilkCardOut] = []`.
- Consumes: `RatingAggregate` (reviews_models), `leads.inquiries`/`leads.responses` (same SQL family as `leads_service._STATS_SQL`), `BusinessCoverage.updated_at` — all directory-module-internal, no boundary crossing.

- [ ] **Step 1: Failing tests** in `tests/test_milk_home_recommended.py`. Borrow seeding helpers from the existing `test_milk_home*.py` files (they already create covering businesses with products at 641001 via `directory_service` + coverage rows — copy their fixture imports wholesale). Core cases:

```python
def _card(business, *, verified: bool, tier: str = "free") -> MilkCard:
    return MilkCard(
        id=business.id, name=business.name, slug=business.slug, type="vendor",
        verification_status="verified" if verified else "unverified",
        subscription_tier=tier, distance_m=1000, lat=None, lng=None, products=[],
    )


async def test_paid_signals_never_enter_ranking(db_session, tn_geo_sample) -> None:
    """M3.C: subscription_tier and ad campaigns must not move the ranking -
    two verified businesses identical on every organic signal keep their
    input (organic) order even when one is premium AND runs a campaign."""
    a = await _mk_business(db_session)   # helper from test_milk_home*.py
    b = await _mk_business(db_session)
    b.subscription_tier = "premium"
    db_session.add(Campaign(  # paid activity on b - must be invisible here
        advertiser_business_id=b.id, name="paid", status="active",
        budget_display="", flight_start=date.today(), flight_end=date.today(),
    ))
    for biz in (a, b):
        biz.verification_status = "verified"
    ranked = await rank_recommended(
        db_session,
        [_card(a, verified=True), _card(b, verified=True, tier="premium")],
        now=datetime.now(UTC),
    )
    assert ranked == [a.id, b.id]  # input order preserved - premium bought nothing


async def test_rating_and_verification_rank(db_session, tn_geo_sample) -> None:
    a = await _mk_business(db_session)  # verified + rated 4.5x10
    b = await _mk_business(db_session)  # verified, unrated
    c = await _mk_business(db_session)  # unverified, unrated -> below MIN_SCORE
    a.verification_status = "verified"
    b.verification_status = "verified"
    db_session.add(RatingAggregate(
        target_type="business", target_id=a.id,
        rating_avg=Decimal("4.50"), rating_count=10,
    ))
    ranked = await rank_recommended(
        db_session,
        [_card(b, verified=True), _card(a, verified=True), _card(c, verified=False)],
        now=datetime.now(UTC),
    )
    assert ranked[0] == a.id
    assert c.id not in ranked  # bare unverified noise never rails


async def test_milk_home_carries_recommended_only_unfiltered_first_page(
    db_session, tn_geo_sample
) -> None:
    # seed a covered pincode the way test_milk_home*.py does, with one
    # verified business, then:
    result = await milk_home(
        db_session, pincode="641001", milk_type=None, product_category=None,
        cursor=None, limit=20,
    )
    assert [c.id for c in result.recommended] == [<verified business id>]
    filtered = await milk_home(
        db_session, pincode="641001", milk_type="cow", product_category=None,
        cursor=None, limit=20,
    )
    assert filtered.recommended == []
```

- [ ] **Step 2:** Run: `python -m pytest tests/test_milk_home_recommended.py -q` — FAIL (module missing).
- [ ] **Step 3: Implement** `modules/directory/recommended.py`:

```python
"""M3.C: the "Recommended" rail ranking - ORGANIC ONLY.

This function is the single source of the Recommended label (the frontend
renders the label exclusively from milk-home's `recommended` field, which
only this fn populates). Inputs are trust + service-quality signals:
verification, approved-review ratings, lead first-response time, coverage
freshness. Paid signals - subscription_tier, campaigns, budgets - MUST
NEVER enter this scoring. Paid can never buy the label (spec M3.C;
test_milk_home_recommended.py::test_paid_signals_never_enter_ranking)."""

import uuid
from collections.abc import Sequence
from datetime import datetime, timedelta
from typing import TYPE_CHECKING

from sqlalchemy import func, select, text
from sqlalchemy.ext.asyncio import AsyncSession

from modules.directory.models import BusinessCoverage
from modules.directory.reviews_models import RatingAggregate

if TYPE_CHECKING:
    from modules.directory.milk_home import MilkCard

RECOMMENDED_LIMIT = 3
MIN_SCORE = 3.0  # verified floor - a no-signal unverified card never rails
_VERIFIED_POINTS = 3.0
_FAST_RESPONSE_S = 4 * 3600   # < 4h  -> +2.0
_OK_RESPONSE_S = 24 * 3600    # < 24h -> +1.0
_FRESH_COVERAGE = timedelta(days=30)  # coverage touched recently -> +1.0

# Batched flavour of leads_service._STATS_SQL (same lateral join, grouped).
_RESPONSE_SQL = text(
    """
    SELECT i.business_id,
           CAST(avg(EXTRACT(EPOCH FROM fr.first_at - i.created_at)) AS BIGINT)
               AS avg_response_seconds
    FROM leads.inquiries i
    LEFT JOIN LATERAL (
        SELECT min(r.created_at) AS first_at
        FROM leads.responses r WHERE r.inquiry_id = i.id
    ) fr ON true
    WHERE i.business_id = ANY(:ids)
    GROUP BY i.business_id
    """
)


async def rank_recommended(
    session: AsyncSession, cards: Sequence["MilkCard"], *, now: datetime
) -> list[uuid.UUID]:
    """Top-RECOMMENDED_LIMIT business ids among `cards`, best first. Ties keep
    the caller's (organic covers) order. Only cards clearing MIN_SCORE rail."""
    if not cards:
        return []
    ids = [c.id for c in cards]

    ratings = {
        row.target_id: (float(row.rating_avg), row.rating_count)
        for row in await session.scalars(
            select(RatingAggregate).where(
                RatingAggregate.target_type == "business",
                RatingAggregate.target_id.in_(ids),
            )
        )
    }
    response = {
        m["business_id"]: m["avg_response_seconds"]
        for m in (
            r._mapping
            for r in await session.execute(_RESPONSE_SQL, {"ids": ids})
        )
        if m["avg_response_seconds"] is not None
    }
    freshness = {
        business_id: latest
        for business_id, latest in await session.execute(
            select(BusinessCoverage.business_id, func.max(BusinessCoverage.updated_at))
            .where(BusinessCoverage.business_id.in_(ids))
            .group_by(BusinessCoverage.business_id)
        )
    }

    def score(card: "MilkCard") -> float:
        s = _VERIFIED_POINTS if card.verification_status == "verified" else 0.0
        rated = ratings.get(card.id)
        if rated is not None:
            avg, count = rated
            s += avg * min(count, 5) / 5
        avg_s = response.get(card.id)
        if avg_s is not None:
            if avg_s < _FAST_RESPONSE_S:
                s += 2.0
            elif avg_s < _OK_RESPONSE_S:
                s += 1.0
        latest = freshness.get(card.id)
        if latest is not None and (now - latest) <= _FRESH_COVERAGE:
            s += 1.0
        return s

    scored = [(card, score(card)) for card in cards]
    ranked = sorted(
        (entry for entry in scored if entry[1] >= MIN_SCORE),
        key=lambda entry: -entry[1],  # sorted() is stable -> organic order breaks ties
    )
    return [card.id for card, _ in ranked[:RECOMMENDED_LIMIT]]
```

(If `BusinessCoverage.updated_at` comes back tz-aware/naive mismatched vs `now`, normalize with `.replace(tzinfo=UTC)` guard — TimestampMixin columns are timezone-aware, so `now=datetime.now(UTC)` should compare cleanly.)

- [ ] **Step 4: milk_home wiring.** `MilkHomeResult` gains `recommended: list[MilkCard] = field(default_factory=list)` (add `field` import; keep it LAST in the dataclass). The two empty-state returns pass nothing (default). In the covered return path, before constructing the result:

```python
    recommended: list[MilkCard] = []
    unfiltered_view = (
        cursor is None
        and (milk_type in (None, "all"))
        and (product_category in (None, "all"))
    )
    if unfiltered_view and (vendors or brands):
        from modules.directory.recommended import rank_recommended

        ranked = await rank_recommended(
            session, [*vendors, *brands], now=datetime.now(UTC)
        )
        by_id = {c.id: c for c in [*vendors, *brands]}
        recommended = [by_id[i] for i in ranked]
```

and pass `recommended=recommended`. `milk_home_schemas.py`: `MilkHomeOut` gains `recommended: list[MilkCardOut] = []`; `milk_home_out()` maps `recommended=[_card_out(c) for c in result.recommended]`.

- [ ] **Step 5:** Run: `python -m pytest tests/test_milk_home_recommended.py tests/ -k "milk_home" -q` — PASS (existing milk-home tests must not break: `recommended` defaults keep old constructions valid).
- [ ] **Step 6:** `ruff format . && ruff check . && mypy . && lint-imports` · commit `feat(m3): organic-only Recommended ranking + milk-home rail field`

---

### Task 8: `injectSponsored` render-layer util (NN3)

**Files:**
- Modify: `packages/ui/src/lib/sponsored.ts`
- Test: `packages/ui/src/lib/sponsored.test.ts` (extend)

**Interfaces:**
- Produces: `type ListEntry<T>`, `injectSponsored<T>(organic, ads, positions?) -> ListEntry<T>[]`, `SPONSORED_POSITIONS = [0, 5]`, `MAX_SPONSORED_PER_PAGE = 2` — all exported from the `@agri/ui` barrel.

- [ ] **Step 1: Failing tests** (extend `sponsored.test.ts`; build `ServedAd` fixtures with the file's existing valid-ad helper or an inline literal with `label: "sponsored"`):

```ts
describe("injectSponsored (M3 NN3)", () => {
  const ads = [ad("a1"), ad("a2")]; // helper returning a valid ServedAd

  it("preserves organic order and identity exactly (sponsorship on)", () => {
    const organic = [{ id: 1 }, { id: 2 }, { id: 3 }, { id: 4 }, { id: 5 }, { id: 6 }];
    const entries = injectSponsored(organic, ads);
    const organicOut = entries.filter((e) => e.kind === "organic").map((e) => e.item);
    expect(organicOut).toEqual(organic);            // same order, same length
    organicOut.forEach((item, i) => expect(item).toBe(organic[i])); // same refs
  });

  it("is the identity on the organic stream with sponsorship off", () => {
    const organic = [{ id: 1 }, { id: 2 }];
    expect(injectSponsored(organic, []).map((e) => e.kind === "organic" && e.item)).toEqual(
      organic,
    );
  });

  it("places sponsored entries at page positions 1 and 6", () => {
    const organic = Array.from({ length: 8 }, (_, i) => i);
    const entries = injectSponsored(organic, ads);
    expect(entries[0].kind).toBe("sponsored");
    expect(entries[5].kind).toBe("sponsored");
    expect(entries.filter((e) => e.kind === "sponsored")).toHaveLength(2);
  });

  it("caps at 2 sponsored per page", () => {
    const five = [ad("1"), ad("2"), ad("3"), ad("4"), ad("5")];
    const entries = injectSponsored([1, 2, 3, 4, 5, 6, 7], five);
    expect(entries.filter((e) => e.kind === "sponsored")).toHaveLength(2);
  });

  it("appends past-the-end positions to short lists", () => {
    const entries = injectSponsored([1, 2, 3], ads);
    expect(entries[0].kind).toBe("sponsored");
    expect(entries[entries.length - 1].kind).toBe("sponsored");
  });

  it("never injects into an empty organic list (no ad-only pages)", () => {
    expect(injectSponsored([], ads)).toEqual([]);
  });
});
```

- [ ] **Step 2:** Run: `pnpm --filter @agri/ui test` — FAIL.
- [ ] **Step 3: Implement** in `sponsored.ts`:

```ts
/** M3.B sponsored-listing injection — page positions 1 and 6 (0-indexed
 * display slots 0 and 5), max 2 per page. */
export const SPONSORED_POSITIONS: readonly number[] = [0, 5];
export const MAX_SPONSORED_PER_PAGE = 2;

export type ListEntry<T> =
  | { kind: "organic"; item: T }
  | { kind: "sponsored"; ad: ServedAd };

/** Render-layer injection (M3.B / NN3): the organic array is NEVER
 * reordered, filtered or re-counted — sponsored entries are spliced into the
 * RENDERED flow only, so the cursor stream (built from organic items) is
 * byte-identical with sponsorship on or off. Empty organic list ⇒ nothing is
 * injected (no ad-only pages); positions past the end clamp to the end. */
export function injectSponsored<T>(
  organic: readonly T[],
  ads: readonly ServedAd[],
  positions: readonly number[] = SPONSORED_POSITIONS,
): ListEntry<T>[] {
  const out: ListEntry<T>[] = organic.map((item) => ({ kind: "organic", item }));
  if (out.length === 0) return out;
  ads.slice(0, MAX_SPONSORED_PER_PAGE).forEach((ad, i) => {
    const pos = positions[i];
    if (pos === undefined) return;
    out.splice(Math.min(pos, out.length), 0, { kind: "sponsored", ad });
  });
  return out;
}
```

Barrel (`packages/ui/src/index.ts:57-61` block): add `injectSponsored, MAX_SPONSORED_PER_PAGE, SPONSORED_POSITIONS` to the value export and `ListEntry` to the type export.

- [ ] **Step 4:** Run: `pnpm --filter @agri/ui test` — PASS. `pnpm --filter @agri/ui typecheck lint`.
- [ ] **Step 5:** Commit `feat(m3): render-layer sponsored injection util`

---

### Task 9: `SponsoredListingCard` (NN4)

**Files:**
- Create: `packages/ui/src/composites/sponsored-listing-card.tsx`
- Test: create `packages/ui/src/composites/sponsored-listing-card.test.tsx`
- Modify: `packages/ui/src/index.ts` (export)

**Interfaces:**
- Produces: `SponsoredListingCard({ ad: ServedAd; endpoint?: string; className?: string })`.

- [ ] **Step 1: Failing test** (vitest env is node — use `renderToStaticMarkup`, no jsdom):

```tsx
import { renderToStaticMarkup } from "react-dom/server";
import { describe, expect, it } from "vitest";

import { SponsoredListingCard } from "./sponsored-listing-card";

const AD = {
  placement_id: "p1",
  creative_id: "c1",
  slot_key: "milk_sponsored_listing",
  label: "sponsored",
  title: "Kovai Fresh Dairy",
  body: "Farm milk in 641001",
  media_urls: [],
  target_url: "https://kovai.example.com/",
} as const;

describe("SponsoredListingCard (M3 NN4)", () => {
  const html = renderToStaticMarkup(<SponsoredListingCard ad={AD} />);

  it("always carries the Sponsored badge", () => {
    expect(html).toContain("★ Sponsored");
  });

  it("never carries the organic Recommended label", () => {
    expect(html).not.toContain("Recommended");
  });

  it("is a nofollow-sponsored link to the target", () => {
    expect(html).toContain('rel="nofollow sponsored"');
    expect(html).toContain('href="https://kovai.example.com/"');
  });

  it("matches snapshot", () => {
    expect(html).toMatchSnapshot();
  });
});
```

- [ ] **Step 2:** Run: `pnpm --filter @agri/ui test` — FAIL (module missing).
- [ ] **Step 3: Implement:**

```tsx
"use client";

/**
 * M3.B sponsored listing: a labeled vendor/brand-style card injected into
 * result lists at the RENDER layer (never the cursor stream). Contracts:
 * - SponsoredBadge always (NN4; ServedAd.label is type-narrowed upstream)
 * - impression beacon at >=50% visibility, never on mount (M2 NN2)
 * - click beacon on click
 * - the word "Recommended" must never render here - that label belongs to
 *   the organic ranking fn alone (M3.C)
 * - no contact data on the wire: the card links to the profile page where
 *   D18's reveal caps govern contact actions, sponsored or not.
 */
import { ListingCard } from "../components/listing-card";
import { SponsoredBadge } from "../components/sponsored-badge";
import { cn } from "../lib/cn";
import type { ServedAd } from "../lib/sponsored";
import { sendAdBeacon, useImpression } from "./ad-slot";

export function SponsoredListingCard({
  ad,
  endpoint = "/api/ads",
  className,
}: {
  ad: ServedAd;
  endpoint?: string;
  className?: string;
}) {
  const ref = useImpression(ad, endpoint);
  return (
    <a
      ref={ref}
      href={ad.target_url}
      rel="nofollow sponsored"
      onClick={() => sendAdBeacon(`${endpoint}/clicks`, ad)}
      className={cn("block h-full no-underline", className)}
      data-testid={`sponsored-listing-${ad.placement_id}`}
    >
      <ListingCard
        badge={<SponsoredBadge />}
        icon="📢"
        tint="gold"
        title={ad.title}
        meta={ad.body}
        className="h-full"
      />
    </a>
  );
}
```

Barrel: `export { SponsoredListingCard } from "./composites/sponsored-listing-card";` near the AdSlot export (line ~65). Note `optimizePackageImports: ["@agri/ui"]` in web-milk's next.config keeps unused composites out of client graphs — no extra config needed, but do NOT import this from any server-only path in packages/ui.

- [ ] **Step 4:** Run: `pnpm --filter @agri/ui test` — PASS (snapshot written on first run; re-run to confirm stable). `pnpm --filter @agri/ui typecheck lint`.
- [ ] **Step 5:** Commit `feat(m3): SponsoredListingCard with badge + beacons`

---

### Task 10: web-milk serve fetch helper + BFF pincode-context override

**Files:**
- Create: `apps/web-milk/lib/ads.ts`
- Modify: `apps/web-milk/app/api/ads/[...path]/route.ts`
- Modify: `apps/web-agri/app/api/ads/[...path]/route.ts` (same override — keep the twins identical)

**Interfaces:**
- Produces: `fetchSponsoredListings(ctx: { pincode?: string | null; category?: string | null; locale?: string }): Promise<ServedAd[]>`, `SPONSORED_LISTING_SLOT = "milk_sponsored_listing"`.

- [ ] **Step 1:** `apps/web-milk/lib/ads.ts`:

```ts
import { parseServeResponse, type ServedAd, serveQuery } from "@agri/ui";
import { headers } from "next/headers";

const API = process.env.API_BASE_URL ?? "http://127.0.0.1:8000";

export const SPONSORED_LISTING_SLOT = "milk_sponsored_listing";

/**
 * Server-side sponsored-listing fetch (M3.B): the page injects these at the
 * render layer, so organic payloads/cursors/JSON-LD stay byte-identical.
 * Client identity (freq caps, viewer_hash) survives the server hop by
 * forwarding x-forwarded-for + user-agent (D26 relay-forwarding precedent;
 * the backend honours XFF only when trust_forwarded_for is set). Any failure
 * degrades to no ads - a list page must never break because ads did.
 */
export async function fetchSponsoredListings(ctx: {
  pincode?: string | null;
  category?: string | null;
  locale?: string;
}): Promise<ServedAd[]> {
  try {
    const h = await headers();
    const fwd: Record<string, string> = { "user-agent": h.get("user-agent") ?? "" };
    const xff = h.get("x-forwarded-for");
    if (xff) fwd["x-forwarded-for"] = xff;
    const res = await fetch(
      `${API}/ads/serve?${serveQuery(SPONSORED_LISTING_SLOT, { ...ctx, count: 2 })}`,
      { cache: "no-store", headers: fwd },
    );
    if (!res.ok) return [];
    return parseServeResponse(await res.json());
  } catch {
    return [];
  }
}
```

- [ ] **Step 2: BFF override** — in both ads BFF `route.ts` files, after `url.search = req.nextUrl.search;` add:

```ts
  // M3 threat "geo spoofing for cheap-tier arbitrage": for serve, the
  // pincode comes from the location CONTEXT (agri_loc cookie - D19; kept in
  // sync with the profile pincode after login by LiveLocationPill), never a
  // bare client-supplied query param. No cookie -> no pincode (fail closed
  // to global-only inventory).
  if (firstSegment === "serve") {
    const loc = parseLocCookie(req.cookies.get(LOC_COOKIE)?.value);
    if (loc?.pincode) url.searchParams.set("pincode", loc.pincode);
    else url.searchParams.delete("pincode");
  }
```

with `import { LOC_COOKIE, parseLocCookie } from "@agri/ui";` — honest clients already derive the param from the same cookie, so behaviour is unchanged for them.

- [ ] **Step 3:** `pnpm --filter web-milk typecheck lint` and `pnpm --filter web-agri typecheck lint` — PASS.
- [ ] **Step 4:** Commit `feat(m3): server-side sponsored fetch + BFF pincode-context override`

---

### Task 11: Inject sponsored listings into the three surfaces

**Files:**
- Modify: `apps/web-milk/app/[locale]/[city]/[pincode]/page.tsx` (fetch + pass into both branches)
- Modify: `apps/web-milk/app/[locale]/[city]/[pincode]/vendor-results.tsx`
- Modify: `apps/web-milk/app/[locale]/[city]/[pincode]/category-results.tsx`
- Modify: `apps/web-milk/app/[locale]/search/page.tsx`

**Interfaces:**
- Consumes: `fetchSponsoredListings` (Task 10), `injectSponsored`/`ListEntry` (Task 8), `SponsoredListingCard` (Task 9).

- [ ] **Step 1: Landing page (`page.tsx`).** Category branch — after `fetchCovers` succeeds:

```tsx
    const sponsored = await fetchSponsoredListings({ pincode, category, locale });
```

pass `sponsored={sponsored}` to `CategoryResults`. Covered branch — right before the `return` (only when `!filteredEmpty`):

```tsx
  const sponsored = filteredEmpty
    ? []
    : await fetchSponsoredListings({
        pincode,
        category: product_category && product_category !== "all" ? product_category : null,
        locale,
      });
```

pass `sponsored={sponsored}` to `VendorResults`. **Do not touch `itemListJsonLd`** — it iterates `data.vendors`/`data.brands`, which stay pristine (structured-data pollution guard).

- [ ] **Step 2: `vendor-results.tsx`.** Add `sponsored: ServedAd[]` prop (import `injectSponsored, SponsoredListingCard, type ListEntry, type ServedAd` from `@agri/ui`). Inject into the FIRST non-empty section only (decision #8):

```tsx
  const primary: "vendors" | "brands" = vendors.length > 0 ? "vendors" : "brands";

  const renderSection = (title: string, cards: MilkCard[], withSponsored: boolean) => {
    const entries: ListEntry<MilkCard>[] = withSponsored
      ? injectSponsored(cards, sponsored)
      : cards.map((item) => ({ kind: "organic" as const, item }));
    return cards.length > 0 ? (
      <section className="flex flex-col gap-2.5">
        <h2 className="font-display text-[16px] font-extrabold text-ink">{title}</h2>
        <div className="grid gap-3 sm:grid-cols-2">
          {entries.map((entry) =>
            entry.kind === "sponsored" ? (
              <SponsoredListingCard key={`s-${entry.ad.placement_id}`} ad={entry.ad} />
            ) : (
              <VendorCard
                key={entry.item.id}
                card={entry.item}
                pincode={pincode}
                selected={selectedId === entry.item.id}
                onSelect={setSelectedId}
              />
            ),
          )}
        </div>
      </section>
    ) : null;
  };
```

call sites: `renderSection("Local vendors", vendors, primary === "vendors")` / `renderSection("Brands & shops nearby", brands, primary === "brands")`. `pins` still maps over `[...vendors, ...brands]` only — sponsored cards never enter the map.

- [ ] **Step 3: `category-results.tsx`.** Add `sponsored: ServedAd[]` prop; replace the `items.map` with `injectSponsored(items, sponsored).map(...)` rendering `<li key={...}>` around either `SponsoredListingCard` or the existing organic `Card`. Empty-state branch unchanged (injectSponsored returns [] for empty organic anyway — keep the early return first).
- [ ] **Step 4: Search page.** After the results fetch:

```tsx
  const sponsoredAds =
    page.items.length > 0
      ? await fetchSponsoredListings({ pincode: loc?.pincode ?? null, locale })
      : [];
```

and render `injectSponsored(page.items, sponsoredAds).map(...)` inside the `<ul data-testid="search-results">`, with sponsored entries as `<li key={`s-${entry.ad.placement_id}`}><SponsoredListingCard ad={entry.ad} /></li>` and the existing hit `<li>` markup for organic entries. The `next_cursor` load-more `Link` is untouched (cursor byte-identical — NN3's page-level half).
- [ ] **Step 5:** `pnpm --filter web-milk typecheck lint test` (if the app has tests) — PASS. Manually smoke if the stack is up: `pnpm dev` + `/coimbatore/641001` (requires seeded DB per dev-db-setup-gotchas memory; skip if stack down — e2e covers it in Task 14).
- [ ] **Step 6:** Commit `feat(m3): sponsored listing injection on landing/category/search`

---

### Task 12: Recommended rail UI

**Files:**
- Modify: `apps/web-milk/lib/milk.ts` (`MilkHome.recommended`)
- Create: `apps/web-milk/app/[locale]/[city]/[pincode]/recommended-rail.tsx`
- Modify: `apps/web-milk/app/[locale]/[city]/[pincode]/page.tsx` (mount)
- Modify: `packages/ui/src/i18n/messages/{en,ta,hi}.json` (heading string)

- [ ] **Step 1:** `lib/milk.ts`: add `recommended: MilkCard[];` to `MilkHome` (mirrors `MilkHomeOut`).
- [ ] **Step 2:** i18n — under the `"ui"` namespace (sibling of `categoryBrowse`) in all three message files:
  - en: `"recommended": { "heading": "Recommended" }`
  - ta: `"recommended": { "heading": "பரிந்துரைக்கப்பட்டவை" }`
  - hi: `"recommended": { "heading": "अनुशंसित" }`
  (`locale-completeness.test.ts` gates parity — run `pnpm --filter @agri/ui test` after.)
- [ ] **Step 3:** `recommended-rail.tsx` — server component; the heading IS the label, and its ONLY data source is `MilkHomeOut.recommended` (ranking fn output — M3.C):

```tsx
import { getTranslations } from "next-intl/server";

import type { MilkCard } from "@/lib/milk";

import { VendorCard } from "./vendor-card";

/** M3.C organic-only rail. Data source: MilkHomeOut.recommended, populated
 * exclusively by modules/directory/recommended.py's ranking fn - paid units
 * render through SponsoredListingCard and can never reach this component. */
export async function RecommendedRail({
  cards,
  pincode,
}: {
  cards: MilkCard[];
  pincode: string;
}) {
  if (cards.length === 0) return null;
  const t = await getTranslations("ui.recommended");
  return (
    <section className="flex flex-col gap-2.5" data-testid="recommended-rail">
      <h2 className="font-display text-[16px] font-extrabold text-ink">⭐ {t("heading")}</h2>
      <div className="grid gap-3 sm:grid-cols-2">
        {cards.map((c) => (
          <VendorCard key={c.id} card={c} pincode={pincode} />
        ))}
      </div>
    </section>
  );
}
```

(`VendorCard` is `"use client"` — rendering it from a server component is fine; `selected`/`onSelect` are optional.)
- [ ] **Step 4:** Mount in `page.tsx` covered branch, between the post-need CTA and the results block:

```tsx
      {!filteredEmpty ? <RecommendedRail cards={data.recommended} pincode={pincode} /> : null}
```

- [ ] **Step 5:** `pnpm --filter @agri/ui test` (locale-completeness) + `pnpm --filter web-milk typecheck lint` — PASS.
- [ ] **Step 6:** Commit `feat(m3): organic Recommended rail on landing page`

---

### Task 13: web-admin — slot key + budget fields

**Files:**
- Modify: `apps/web-admin/app/ads/ads-manager.tsx`

- [ ] **Step 1:** Add `"milk_sponsored_listing"` to the `SLOT_KEYS` array (line ~28).
- [ ] **Step 2:** Campaign create form: add an optional "Serve budget (blank = unlimited)" `<input type="number" min={0}>` bound into the create payload as `budget_serves_total` (number or omitted — never send `""`). Campaign list/table: render `budget_serves_used` / `budget_serves_total ?? "∞"` in a new column or the existing meta line, following the file's local idioms exactly (it's a large client component — copy an adjacent field's state/handler pattern).
- [ ] **Step 3:** `pnpm --filter web-admin typecheck lint` — PASS.
- [ ] **Step 4:** Commit `feat(m3): admin serve-budget field + sponsored-listing slot`

---

### Task 14: e2e — sponsored listings live

**Files:**
- Create: `e2e/sponsored-listing.spec.ts`

(Seed flag already wired in Task 6. Remember the port-8000 trap: stop the dev docker API container before running e2e — Playwright must boot its own peek-enabled API.)

- [ ] **Step 1: Spec:**

```ts
import { expect, test } from "@playwright/test";

import { API, MILK } from "./helpers";

// M3.B: house sponsored-listing campaign is seeded globally (e2e-api.mjs
// --with-sponsored-listing), so every covered landing page carries exactly
// one sponsored card at position 1 of the primary grid.

test("sponsored listing injects at position 1, labeled, organic count unchanged", async ({
  page,
  request,
}) => {
  const home = await request.get(`${API}/catalog/milk/home/641001`);
  expect(home.ok()).toBeTruthy();
  const data = await home.json();
  const organicVendorCount = data.vendors.length;

  await page.goto(`${MILK}/coimbatore/641001`);
  const sponsoredCard = page.locator('[data-testid^="sponsored-listing-"]').first();
  await expect(sponsoredCard).toBeVisible();
  await expect(sponsoredCard).toContainText("★ Sponsored");

  // NN3 (page half): every organic vendor still renders - injection never
  // consumes an organic slot or the cursor stream.
  await expect(page.locator('[data-testid^="vendor-card-"]')).toHaveCount(organicVendorCount);

  // Position 1: the sponsored card is the first cell of the primary grid.
  const grid = page.locator("section", { hasText: "Local vendors" }).locator("div.grid").first();
  await expect(grid.locator("> *").first()).toHaveAttribute("data-testid", /sponsored-listing-/);
});

test("sponsored listings never enter the JSON-LD ItemList", async ({ page }) => {
  await page.goto(`${MILK}/coimbatore/641001`);
  const jsonLd = await page.locator('script[type="application/ld+json"]').first().textContent();
  expect(jsonLd).toBeTruthy();
  expect(jsonLd).not.toContain("Milk.in Partner Dairy"); // the house sponsored title
});
```

(Adjust the position-1 locator to the real DOM if the section wrapper differs — assert against what Task 11 rendered. If seed data at 641001 fills the vendors section, `primary === "vendors"` holds.)

- [ ] **Step 2:** Run the suite: from repo root, the documented e2e flow (`pnpm e2e` or `npx playwright test e2e/sponsored-listing.spec.ts` after `node scripts/e2e-api.mjs` + web servers — follow `e2e/playwright.config.ts` `webServer` blocks; it self-boots). Expect PASS. Also re-run `e2e/ads-surfaces.spec.ts` (serve-loop changes touched its surface).
- [ ] **Step 3:** Commit `test(m3): sponsored-listing e2e`

---

### Task 15: Docs, full gates, PR

- [ ] **Step 1:** Append an "M3 — delivery blend + sponsored listings" section to `docs/qa/manual-test-d23-d29.md` following its existing per-milestone format: how to seed (`seed_house_ads.py --with-sponsored-listing`), what to check (sponsored card at position 1 with ★ Sponsored, Recommended rail on unfiltered landing, budget exhaustion via admin, why-served rows in `ads.delivery_decisions`).
- [ ] **Step 2: Full local gates** (run-full-ci-gates-locally memory):
  - backend: `python -m pytest -q` (plus `-m slow` for storm), `mypy .`, `ruff check .`, `ruff format --check .`, `lint-imports`, `python scripts/dump_public_routes.py --check`
  - frontend: `pnpm -w typecheck && pnpm -w lint && pnpm -w test && pnpm check:hex`
  - e2e: full `npx playwright test`
- [ ] **Step 3:** Push branch, open PR to `dev` titled `feat(m3): delivery blend + sponsored listings` (PR via credential-fill API — no gh CLI). PR body: summary, the four NNs with their test names, threat-model coverage table, and the M2→M3 contract notes (freq-cap re-key, Candidate refactor).

---

## Self-Review (run after writing, before executing)

- **Spec coverage:** A→Tasks 3/4/5 (blend, boost, budget, freq, category independence) · B→6/8/9/10/11 (slot, cap 2, positions 1+6, badge, render-layer injection) · C→7/12 (ranking fn sole label source) · D→10 (BFF cookie context; profile takeover via existing LiveLocationPill sync) · E→1/5 (append-only sampled log) · NN1→Task 3 test · NN2→Task 3 ghee/paneer test · NN3→Task 8 tests + Task 14 count assertion · NN4→Task 9 snapshot · threats: label laundering→NN4+type-level label; budget race→Task 4 storm test; geo spoofing→Task 10 BFF; log PII→viewer_hash-only column set (Task 5 test).
- **Type consistency:** `Candidate(placement, creative, campaign, rung)` used in Tasks 3-5 router/service consistently; `ServedAd` unchanged on the wire; `ListEntry` shared by Tasks 8/11.
- **Known judgment calls (flag in PR):** budget is serve-credits not currency (M5 owns money); freq-cap "session" = daily viewer_hash; sampled log default 0.1; Recommended rail limited to unfiltered first page.
