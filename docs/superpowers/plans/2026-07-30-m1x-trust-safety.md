# M1.5 Trust & Safety + Profile Polish Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** User reporting into the existing moderation queue, admin suspend/disable/reinstate enforcement with full propagation (covers/search/profile/dashboard/ads), brand About section, and member-since trust signals.

**Architecture:** Reports are a new `ModerationSource` (`type_key="report"`) owned by the directory module — zero changes to `modules/ops`. Enforcement adds a `disabled` value to the existing `directory.business_status` enum plus two soft-state columns; every public read path already filters `status = 'active'`, and `search_sync.business_snapshot()` already returns `None` for non-active, so suspend/disable propagate by republishing `business.updated`/`product.updated`. Ads get a serve-time `is_servable` check plus a disable-time campaign auto-pause via the D20 shared-DI-registry pattern (no cross-module imports). About and member-since ride existing fields (`Business.description` JSONB, `created_at`s) with new validation and rendering.

**Tech Stack:** FastAPI + SQLAlchemy async + Alembic (backend/core), Redis Streams events, Meilisearch, Next.js 15 + next-intl (apps/web-milk, web-agri, web-admin, web-id), pnpm 11 / Node 24.

## Global Constraints

- Branch `feat/m1x-trust-safety` from dev; conventional commits; PR targets **dev**, never main.
- Directory module never imports identity/ads/ops (import-linter). Cross-module = event bus or shared DI registries (`shared/lookups.py`).
- Every route on SecureRouter; new public routes need `backend/core/public_routes.txt` (this plan adds **no** public routes).
- All list endpoints cursor-paginated (OFFSET banned by test gate). IDs UUIDv7.
- Reports NEVER public: no report fields on any public schema, no reporter identity to vendors; admin surface only.
- No hard delete: suspend/disable are status flips (Constitution soft-delete).
- No auto-suspend on report count — enforcement is a human decision (ReportSource approve does NOT touch business status).
- About: plain text only (reject HTML), max 2000 chars/locale, keys ⊆ {en,ta,hi}.
- i18n: every new EN key needs ta + hi in `packages/ui/src/i18n/messages/*.json` (locale-completeness vitest).
- Tokens only in frontend (check:hex); run `ruff format` per backend task; mypy + lint-imports before push.
- Audit: `shared/audit.py audit()` in caller's txn; metadata never carries phones/PII; capture event payloads BEFORE commit; commit; then best-effort publish.

---

### Task 1: Migration 0030 + models (enum value, enforcement columns, reports table)

**Files:**
- Create: `backend/core/alembic/versions/0030_trust_safety_v1.py`
- Modify: `backend/core/modules/directory/models.py` (enum tuple :24-26, Business fields ~:50-65, new Report model at end)
- Modify: `backend/core/settings.py` (add `report_daily_cap`)

**Interfaces:**
- Produces: `Business.enforcement_reason: str|None`, `Business.enforcement_prior_status: str|None`, `"disabled"` in `business_status_enum`, model `Report(id, business_id, reporter_user_id, reason, detail, moderation_status, created_at, updated_at)`, `settings.report_daily_cap = 5`.

- [ ] **Step 1: models.py** — add `"disabled"` to the `business_status_enum` values tuple; on `Business` add:

```python
enforcement_reason: Mapped[str | None] = mapped_column(Text, nullable=True)
enforcement_prior_status: Mapped[str | None] = mapped_column(business_status_enum, nullable=True)
```

New enum + model (mirror Claim's shape, plain UUID for reporter, UGC moderation status):

```python
report_reason_enum = postgresql.ENUM(
    "fake_listing", "wrong_info", "abusive", "fraud_scam", "other",
    name="report_reason", schema="directory", create_type=False,
)

class Report(UUIDv7PKMixin, TimestampMixin, UGCMixin, Base):
    __tablename__ = "reports"
    __table_args__ = (
        Index("ix_directory_reports_status_id", "moderation_status", "id"),
        Index(
            "uq_directory_reports_one_pending", "business_id", "reporter_user_id",
            unique=True, postgresql_where=sa.text("moderation_status = 'pending'"),
        ),
        {"schema": "directory"},
    )
    business_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("directory.businesses.id"), nullable=False, index=True
    )
    reporter_user_id: Mapped[uuid.UUID] = mapped_column(Uuid, nullable=False, index=True)
    reason: Mapped[str] = mapped_column(report_reason_enum, nullable=False)
    detail: Mapped[str | None] = mapped_column(Text, nullable=True)
```

(match the module's actual import style/`sa.text` availability — models.py may use `text` from sqlalchemy directly; follow the Claim partial-index precedent at models.py:179-185 verbatim.)

- [ ] **Step 2: settings.py** — next to `need_post_daily_cap`: `report_daily_cap: int = 5`.
- [ ] **Step 3: migration 0030_trust_safety_v1.py** — `revision="0030"`, `down_revision="0029"`, first-line path comment + THREAT/NOTES block (downgrade drops reports table + columns — data loss called out; `ALTER TYPE ADD VALUE` is irreversible → downgrade leaves the enum value in place, note it). Upgrade:
  - `op.execute("ALTER TYPE directory.business_status ADD VALUE IF NOT EXISTS 'disabled'")`
  - `op.add_column` × 2 on `directory.businesses` (Text nullable; `postgresql.ENUM(name="business_status", schema="directory", create_type=False)` nullable)
  - `report_reason` enum `.create(bind, checkfirst=True)`; `op.create_table("reports", pk_column(), *timestamp_columns(), ugc_column(), business_id FK, reporter_user_id UUID, reason enum, detail Text, schema="directory")`; both indexes (partial unique via `postgresql_where`); `GRANT SELECT, INSERT, UPDATE, DELETE ON directory.reports TO app_rt`.
- [ ] **Step 4:** `alembic upgrade head` against dev DB (port 55432 env per docs/dev setup) — verify clean; `ruff format` + `mypy` clean.
- [ ] **Step 5: Commit** `feat(m1x): add disabled status, enforcement columns and reports table`

---

### Task 2: Report service + user-facing POST route (TDD)

**Files:**
- Create: `backend/core/modules/directory/reports_service.py`
- Modify: `backend/core/modules/directory/router.py` (new route after the reviews/view-beacon block)
- Modify: `backend/core/modules/directory/schemas.py` (ReportIn/ReportCreatedOut)
- Test: `backend/core/tests/test_reports.py`

**Interfaces:**
- Consumes: `Report` model, `settings.report_daily_cap`, `claim_need_slot` Redis-cap pattern (`needs_service.py:54-67`), savepoint-dup pattern (`reviews_service.py:70-77`).
- Produces: `create_report(session, *, business_id, reporter_user_id, reason, detail) -> Report` raising `ReportExistsError`; `claim_report_slot(user_id, *, now)` raising `ReportCapExceededError | ReportsUnavailableError`; `list_for_moderation(session, *, status, cursor, limit) -> Page[Report]`; `moderate(session, *, report_id, approve) -> Report` raising `ReportNotFoundError | ReportDecisionConflictError`; route `POST /directory/businesses/{slug}/report` (private).

- [ ] **Step 1: failing tests** in `test_reports.py` (copy fixture style from the reviews router tests: `x-test-user` auth headers, app fixture):
  - guest POST → 401
  - authed POST valid reason → 201 `{"status": "pending"}`; row exists `moderation_status="pending"`
  - duplicate pending same user+business → 409 `report_exists`
  - `reason="other"` without detail → 422; with detail → 201
  - 6th report same user same day (cap 5, monkeypatch redis or loop distinct businesses) → 429 `report_cap_exceeded`
  - reporting a suspended business → 404 (target must be active, `reviews_service._target_exists` precedent)
  - **NN1 public-invisibility half**: `GET /directory/businesses/{slug}` response JSON, serialized, contains no `report` substring / reporter id; covers() item schema likewise.
- [ ] **Step 2:** run → fail (module missing).
- [ ] **Step 3: implement.** `reports_service.py`: exceptions + `claim_report_slot` (key `f"report:{user_id}:{now:%Y%m%d}"`, `_DAY_SECONDS=86400`, fail-closed 503 pattern copied from `needs_service`), `create_report` (savepoint → `IntegrityError` → `ReportExistsError`), `list_for_moderation` via `shared.pagination.paginate` keyset on `(id)` filtered `moderation_status==status`, `moderate` with `with_for_update()` + `already_decided` conflict + status flip + `flush()`. Schemas:

```python
ReportReason = Literal["fake_listing", "wrong_info", "abusive", "fraud_scam", "other"]

class ReportIn(BaseModel):
    reason: ReportReason
    detail: str | None = Field(default=None, min_length=1, max_length=1000)

    @model_validator(mode="after")
    def _other_requires_detail(self) -> "ReportIn":
        if self.reason == "other" and not self.detail:
            raise ValueError("detail is required when reason is 'other'")
        return self

class ReportCreatedOut(BaseModel):
    status: Literal["pending"] = "pending"
```

Route in `router.py` (SecureRouter default = auth required; reuse `_principal_user_id(request)`): resolve active business by slug (`service.get_by_slug` 404 branch), `claim_report_slot`, `create_report`, map `ReportExistsError→409 "report_exists"`, `ReportCapExceededError→429 "report_cap_exceeded"`, `ReportsUnavailableError→503`, commit, return 201.
- [ ] **Step 4:** tests pass; `ruff format`, mypy.
- [ ] **Step 5: Commit** `feat(m1x): user report flow on business profiles`

---

### Task 3: ReportSource in the moderation queue (TDD)

**Files:**
- Modify: `backend/core/modules/directory/moderation_sources.py` (add `ReportSource`, register in `register_directory_moderation_sources()` :447)
- Test: `backend/core/tests/test_reports.py` (extend)

**Interfaces:**
- Consumes: `ModerationSource` Protocol (`shared/moderation.py:63`), `reports_service.*`, `shared.audit.audit`.
- Produces: `type_key="report"` visible in `GET /admin/moderation/summary` and `?type=report`; approve→`moderation_status="approved"` + audit `directory.report_actioned`; reject→`"rejected"` + audit `directory.report_dismissed`; `ModDecision.events = ()` (no downstream fan-out — enforcement is a separate human action).

- [ ] **Step 1: failing tests** (mirror `test_ops_moderation_router.py` fixture that registers sources after `create_app()`):
  - staff `GET /admin/moderation/summary` includes `"report": 1` after a report
  - `GET /admin/moderation/queue?type=report` returns the item; payload has `business_slug`, `reason`, `detail`, `reporter_user_id`, `reporter_reports_30d` (admin sees reporter patterns)
  - role `user` → 403; approve → row approved + `AuditEntry` action `directory.report_actioned` with `target_type="business_report"`; second approve → 409 `already_decided`; reject without note → 422.
- [ ] **Step 2:** run → fail.
- [ ] **Step 3: implement** `ReportSource` modeled on `CreativeSource` (`ads/moderation_sources.py:44-131`): `_report_item()` builds `ModItem(type_key="report", id, created_at, title=f"Report: {business.name}", summary=f"{reason}: {detail or ''}"[:140], payload={business_id/slug/name, reason, detail, reporter_user_id: str, reporter_reports_30d: count})`; `reporter_reports_30d` = `select(func.count()).where(Report.reporter_user_id==..., Report.created_at >= now-30d)`. approve/reject delegate to `reports_service.moderate`, translate errors, `audit(...)`, return `ModDecision(item=..., events=())`. **Never commit.** Register in `register_directory_moderation_sources()`.
- [ ] **Step 4:** tests pass; format/mypy.
- [ ] **Step 5: Commit** `feat(m1x): report moderation source in ops queue`

---

### Task 4: Enforcement admin routes + 410 profile + owner lockout (TDD)

**Files:**
- Modify: `backend/core/modules/directory/admin_router.py` (3 routes + `GET /admin/directory/businesses/{slug}` lookup + enforcement-log list)
- Modify: `backend/core/modules/directory/service.py` (`get_owned_business` disabled check; `get_by_slug_any_status`)
- Modify: `backend/core/modules/directory/router.py` (`get_business_detail` 410 branch)
- Modify: `backend/core/modules/directory/schemas.py` (`BusinessOut.enforcement_reason`, `EnforceIn`, admin outs)
- Modify: `backend/core/main.py` (exception handler for `BusinessDisabledError` → 403)
- Test: `backend/core/tests/test_business_enforcement.py`

**Interfaces:**
- Consumes: `set_business_tier` template (`admin_router.py:387-417`), `search_sync.business_event_payload` + `_product_payloads`, `audit()`, identity suspend 409 semantics.
- Produces: `POST /admin/directory/businesses/{business_id}/suspend|disable|reinstate`; `BusinessDisabledError`; 410 `business_unavailable` on public detail; `BusinessOut.enforcement_reason: str | None`; audit actions `directory.business_suspended|business_disabled|business_reinstated`; `GET /admin/directory/businesses/{slug}` → admin business out; `GET /admin/directory/businesses/{business_id}/enforcement-log` (cursor-paginated audit rows).

- [ ] **Step 1: failing tests** (staff role headers; seed business + product):
  - suspend with reason → 200; business.status=="suspended", enforcement_reason set, prior recorded; `AuditEntry` `directory.business_suspended` metadata `{"reason", "prior_status": "active"}` (NN4 half)
  - published events captured (monkeypatch `admin_router.publish`): `business.updated` with `snapshot: None` + one `product.updated` per product with `snapshot: None` (**NN2 search half** — indexer deletion is already covered by `test_search_indexing.py::test_delete_on_null_snapshot`)
  - covers() for the seed pincode no longer returns it; public `GET /directory/businesses/{slug}` → **410** `business_unavailable`; owner `GET /directory/businesses` still lists it with status+reason (**NN2**)
  - suspend twice → 409 `already_suspended`; suspend a disabled business → 409 `business_disabled`; reason required (422 when missing)
  - disable from active → status disabled; owner-scoped route (PATCH the business as owner) → **403 `business_disabled`**; owner list still shows it (**NN3 lockout half**)
  - disable from suspended → `enforcement_prior_status=="suspended"`; reinstate → status back to `"suspended"` (prior state restored); reinstate again → `"active"`, both enforcement fields None, audit `directory.business_reinstated`, republished payload has `snapshot` non-None (**NN4**)
  - reinstate an active business → 409 `not_enforced`
  - `GET /admin/directory/businesses/{slug}` returns enforcement fields; enforcement-log returns the audit rows newest-first with cursor.
- [ ] **Step 2:** run → fail.
- [ ] **Step 3: implement.**

`schemas.py`:
```python
class EnforceIn(BaseModel):
    reason: str = Field(min_length=1, max_length=500)

class ReinstateIn(BaseModel):
    note: str | None = Field(default=None, max_length=500)
```
`BusinessOut` gains `enforcement_reason: str | None` (safe: public surfaces only ever serve active businesses, where it is None); both `_business_out` mappers pass it.

`service.py`:
```python
class BusinessDisabledError(Exception): ...

# in get_owned_business, after the ownership 404 check:
if business.status == "disabled":
    raise BusinessDisabledError(str(business.id))

async def get_by_slug_any_status(session, slug: str) -> Business | None:
    return await session.scalar(select(Business).where(Business.slug == slug))
```
`main.py`: `app.add_exception_handler(BusinessDisabledError, ...)` → `JSONResponse(status_code=403, content={"detail": "business_disabled"})` (follow existing handler style if one exists; otherwise a small closure in `create_app`).

`router.py get_business_detail`: on the existing 404 branch, check `get_by_slug_any_status`; if found (and not soft-deleted) with status != "active" → `HTTPException(410, "business_unavailable")` — same 410 for suspended and disabled (no state leak). Keep renamed-slug 301 behavior first.

`admin_router.py` — one `_enforce` helper mirroring `set_business_tier` exactly: `_require_role(STAFF, SUPER_ADMIN)` → load business (404) → validate transition (409 codes above) → mutate:
- suspend: `prior = business.status`; `enforcement_prior_status = prior`; `status = "suspended"`; `enforcement_reason = body.reason`
- disable: `prior = business.status`; `enforcement_prior_status = prior`; `status = "disabled"`; `enforcement_reason = body.reason`; `paused = await pause_campaigns_for_business(session, business.id)` (Task 5; returns `[]` until wired — call through `shared.lookups`)
- reinstate: `restored = business.enforcement_prior_status or "active"`; `status = restored`; `enforcement_prior_status = None`; `if restored == "active": enforcement_reason = None`

then `flush()` → `audit(session, action=..., actor_user_id=admin_id, target_type="business", target_id=str(business.id), metadata={"reason"/"note", "prior_status": prior / "restored_status": restored, **({"campaigns_paused": paused} if disable)}, ip=...)` → capture `business_event_payload` + `_product_payloads` **before commit** → `commit()` → `_publish_best_effort` each.

Admin lookup: `GET /admin/directory/businesses/{slug}` → `_admin_business_out` + enforcement fields. Enforcement log: `GET /admin/directory/businesses/{business_id}/enforcement-log` → `paginate` over `AuditEntry` where `action.in_([...3 actions])`, `target_type=="business"`, `target_id==str(id)`, keyset on `id` desc, out schema `{id, action, actor_user_id, created_at, metadata}` (admin-only surface; actor UUID acceptable, matches ops conventions).
- [ ] **Step 4:** tests pass; format/mypy; `lint-imports`.
- [ ] **Step 5: Commit** `feat(m1x): suspend/disable/reinstate enforcement with audit + propagation`

---

### Task 5: is_servable seam + ads auto-pause + serve-time filter (TDD)

**Files:**
- Modify: `backend/core/shared/lookups.py` (two new registries)
- Modify: `backend/core/modules/directory/lookups.py` (`business_is_servable`)
- Modify: `backend/core/modules/ads/service.py` (`pause_active_campaigns`, serve-time filter in `eligible_placements`)
- Modify: `backend/core/main.py` (wire both registrations)
- Test: `backend/core/tests/test_business_enforcement.py` (extend), `backend/core/tests/test_ads_serving.py` or existing ads service test file (extend)

**Interfaces:**
- Consumes: `shared/lookups.py` registry style (`resolve_business` :62), `Campaign` model (`ads/models.py:17`), `eligible_placements` (`ads/service.py:87-130`).
- Produces (the M3 seam): `shared.lookups.is_servable(session, business_id) -> bool` (fail-closed: no resolver or unknown id → False); `shared.lookups.pause_campaigns_for_business(session, business_id) -> list[str]` (no pauser registered → `[]`); directory impl `business_is_servable` (status=="active" and not soft-deleted); ads impl `pause_active_campaigns` (active→paused, returns ids, audit left to caller metadata).

- [ ] **Step 1: failing tests:**
  - `is_servable` True for active, False for suspended, False for disabled, False for unknown id (**NN3 is_servable half** — the M3 ad-serving test written now, per spec)
  - disable route pauses the advertiser's active campaigns (seed campaign status "active" via ORM) → status "paused", audit metadata `campaigns_paused` lists it; draft/archived campaigns untouched
  - `eligible_placements` excludes placements whose advertiser business is suspended (seed a servable setup from the existing ads serving test, then flip status) — closes the "suspended vendor's ads still serving" threat with today's D21 serving path.
- [ ] **Step 2:** run → fail.
- [ ] **Step 3: implement.** `shared/lookups.py` (mirror existing registry shape):

```python
ServableResolver = Callable[[AsyncSession, uuid.UUID], Awaitable[bool]]
CampaignPauser = Callable[[AsyncSession, uuid.UUID], Awaitable[list[str]]]

def register_servable_resolver(fn) / register_campaign_pauser(fn); reset_* test hooks

async def is_servable(session, business_id) -> bool:
    return False if _servable_resolver is None else await _servable_resolver(session, business_id)

async def pause_campaigns_for_business(session, business_id) -> list[str]:
    return [] if _campaign_pauser is None else await _campaign_pauser(session, business_id)
```

`directory/lookups.py`: `business_is_servable` — `select(Business.status).where(id==, deleted_at is None)` → `row == "active"`.
`ads/service.py`: `pause_active_campaigns` — `select(Campaign).where(advertiser_business_id==, status=="active")` → set `"paused"`, `flush()`, return ids; in `eligible_placements`, after the row query: distinct advertiser ids → `{bid: await is_servable(session, bid)}` → filter rows.
`main.py`: `register_servable_resolver(directory_lookups.business_is_servable)` next to `register_business_resolver`; `register_campaign_pauser(ads_service.pause_active_campaigns)` (main.py already imports both modules for wiring).
- [ ] **Step 4:** tests pass; format/mypy/lint-imports (registrations live in main.py, not cross-module imports).
- [ ] **Step 5: Commit** `feat(m1x): is_servable seam, disable-time campaign auto-pause, serve-time status check`

---

### Task 6: About validation + member_since (backend, TDD)

**Files:**
- Modify: `backend/core/modules/directory/schemas.py` (description validator on `BusinessCreateIn` + `BusinessPatchIn`)
- Modify: `backend/core/modules/identity/profile_router.py` (`ProfileOut.member_since`)
- Test: `backend/core/tests/test_reports.py`… no — extend the existing directory business + identity profile test files where BusinessPatchIn/ProfileOut are already covered.

**Interfaces:**
- Produces: `ABOUT_LOCALES = ("en","ta","hi")`, `ABOUT_MAX_LEN = 2000`, shared validator `_validate_description(v)`; `ProfileOut.member_since: datetime` (= `User.created_at`).

- [ ] **Step 1: failing tests:** PATCH business description with key `"fr"` → 422; value 2001 chars → 422; value containing `<b>hi</b>` → 422; valid 3-locale plain text → 200 and echoed in `BusinessOut.description`. Identity: `GET /identity/profile` includes `member_since` equal to the user's created_at.
- [ ] **Step 2:** run → fail.
- [ ] **Step 3: implement.**

```python
ABOUT_LOCALES = ("en", "ta", "hi")
ABOUT_MAX_LEN = 2000
_HTML_RE = re.compile(r"<[^>]*>")

def _validate_description(v: dict[str, str] | None) -> dict[str, str] | None:
    if v is None:
        return v
    for key, value in v.items():
        if key not in ABOUT_LOCALES:
            raise ValueError(f"unsupported locale '{key}' (allowed: en, ta, hi)")
        if len(value) > ABOUT_MAX_LEN:
            raise ValueError(f"description[{key}] exceeds {ABOUT_MAX_LEN} characters")
        if _HTML_RE.search(value):
            raise ValueError(f"description[{key}] must be plain text (no HTML)")
    return v
```
wired via `field_validator("description")` on both schemas. `ProfileOut` gains `member_since: datetime`; `_profile_out(...)` passes `user.created_at` (IdentityPublicSchema guard allows datetime; check any test asserting the exact ProfileOut key set and update it).
- [ ] **Step 4:** tests pass; format/mypy.
- [ ] **Step 5: Commit** `feat(m1x): about-field validation + member_since on profile`

---

### Task 7: web-milk — ReportDialog, About, since-line, unavailable page, JSON-LD

**Files:**
- Modify: `apps/web-milk/lib/business.ts` (types + 410 sentinel)
- Modify: `apps/web-milk/app/[locale]/directory/businesses/[slug]/page.tsx`
- Create: `apps/web-milk/app/[locale]/directory/businesses/[slug]/report-dialog.tsx`
- Modify: `packages/ui/src/i18n/messages/en.json`, `ta.json`, `hi.json`

**Interfaces:**
- Consumes: backend 410 `business_unavailable`, `BusinessOut.created_at`/`description`, Modal from `@agri/ui`, `useAgriUser` from `@agri/auth-client`, web-milk `/api/directory` BFF proxy (POST is auth-forwarding by default — correct for reports).
- Produces: report POST `/api/directory/businesses/{slug}/report`; new i18n namespace `ui.report.*` + `ui.brandPage.{about,onSince,unavailableTitle,unavailableBody}`.

- [ ] **Step 1: lib/business.ts** — add `created_at: string`, `description: Record<string, string> | null` (if absent) to the business interface; change `fetchBusiness` to `Promise<BusinessDetail | "gone" | null>`: `if (res.status === 410) return "gone";` before the 404 branch.
- [ ] **Step 2: page.tsx** — after fetch: `if (detail === "gone")` render the unavailable state (no notFound): centered card, `t("brandPage.unavailableTitle")` / `unavailableBody`, plus `robots: {index:false}` via metadata branch (`generateMetadata` must handle "gone" → title + noindex; JSON-LD skipped). For live pages:
  - meta line (~:194-196) gains ` · {t("brandPage.onSince", {date})}` with `date = new Intl.DateTimeFormat(locale, {month: "long", year: "numeric"}).format(new Date(business.created_at))`
  - About section after the header description `<p>`: locale-aware `business.description?.[locale] ?? business.description?.en` rendered in a `<section>` with heading `t("brandPage.about")` (plain text, `whitespace-pre-line`)
  - `businessJsonLd` `description:` prefers the same locale-aware about text
  - render `<ReportDialog slug={business.slug} locale={locale} />` after `<ReviewForm …>`.
- [ ] **Step 3: report-dialog.tsx** — `"use client"`; copy the `review-form.tsx` state machine + `FIELD/LABEL` consts. `useAgriUser({autoSilentSso: false})`; unauthenticated → login anchor `/api/auth/login?next=…` (match review-form's exact idiom incl. locale handling). Authenticated → `Modal` (uncontrolled — success rendered inside): radio list of 5 reasons from `ui.report.reasons.*`, optional textarea (required when "other"; client-side check), submit → `fetch("/api/directory/businesses/" + slug + "/report", {method:"POST", headers:{"Content-Type":"application/json"}, body: JSON.stringify({reason, detail: detail || null})})`; branches: 201→done state ("thanks, our team will review"), 409→already-reported state, 429→cap message, else→error. Trigger button: quiet ghost variant "Report this listing".
- [ ] **Step 4: i18n** — add to en/ta/hi (author real Tamil/Hindi translations, no placeholders):
  `ui.report`: `trigger, title, description, reasons.{fake_listing,wrong_info,abusive,fraud_scam,other}, detailLabel, detailRequired, submit, submitting, done, alreadyReported, capExceeded, error, loginPrompt, loginCta`; `ui.brandPage`: `about, onSince ("On Milk.in since {date}"), unavailableTitle, unavailableBody`.
- [ ] **Step 5:** `pnpm --filter @agri/ui test` (locale completeness) + `pnpm --filter web-milk build` (or turbo build for the app) green.
- [ ] **Step 6: Commit** `feat(m1x): report dialog, about section, since-line and unavailable page on milk profiles`

---

### Task 8: web-agri console — About editor, suspension banner, disabled lock

**Files:**
- Modify: `apps/web-agri/app/business/listings/listings-client.tsx`
- Modify: `packages/ui/src/i18n/messages/*.json` (console strings live in the shared catalog; web-agri console is EN-rendered but keys still need 3-locale parity)

**Interfaces:**
- Consumes: `BusinessOut.status`/`enforcement_reason` (interface gains both), existing `saveListing` JSONB-merge, local `AlertNotice` helper, backend 403 `business_disabled`.

- [ ] **Step 1:** extend the local `Business` interface with `status: string; enforcement_reason: string | null`.
- [ ] **Step 2:** About: after "Description (English)" textarea add "About (Tamil)" and "About (Hindi)" textareas (`maxLength={2000}` on all three), state + merge handling identical to the existing `existingDescription` en-merge (preserve unknown keys, delete key when blanked).
- [ ] **Step 3:** banner block above the business `<select>`: `status === "suspended"` → `AlertNotice` "This listing is suspended and hidden from Milk.in. Reason: {enforcement_reason}. Contact support to resolve."; `status === "disabled"` → `AlertNotice` "This listing has been disabled by Milk.in administrators." **and** hide the edit/save forms for that business (render the banner only) — backend 403 backs this. Map `ApiError` 403 `business_disabled` in `saveListing` to the same message (defense in depth).
- [ ] **Step 4:** run the app typecheck/build; locale test if new keys added.
- [ ] **Step 5: Commit** `feat(m1x): console about editor + enforcement notices/lock`

---

### Task 9: web-admin — Reports queue tab + business enforcement page

**Files:**
- Modify: `apps/web-admin/app/ops/ops-manager.tsx` (TYPES + renderItem + queueConfig case)
- Create: `apps/web-admin/app/businesses/page.tsx`, `apps/web-admin/app/businesses/businesses-manager.tsx`
- Modify: `apps/web-admin/app/page.tsx` (link list entry)
- Modify: `packages/ui/src/i18n/messages/*.json` (`ui.admin.businesses.*` keys ×3 locales)

**Interfaces:**
- Consumes: generic `ModerationQueue` (`{typeKey, renderItem, onDecided}`), admin `lib/api.ts` (paths relative to `/api/admin`), backend `GET /admin/directory/businesses/{slug}`, `POST /admin/directory/businesses/{id}/suspend|disable|reinstate`, `GET .../enforcement-log`, `users-manager.tsx` Modal-confirm precedent.

- [ ] **Step 1: reports tab** — `TYPES` gains `{key: "report", label: "Reports"}`; `reportRenderItem(item)` shows `payload.business_name` (link `MILK_URL/directory/businesses/{business_slug}` if a public-origin env is available in that component; else plain slug text), reason pill, detail, `reporter_reports_30d` count ("N reports in 30d" — the brigading signal); approve/reject labels come free from `ModerationQueue`.
- [ ] **Step 2: businesses-manager.tsx** — client component mirroring `users-manager.tsx`: slug search input → `getJson(\`/directory/businesses/${slug}\`)` → card with name, status `StatusPill`, verification, tier, enforcement_reason; action row:
  - status active → "Suspend" + "Disable" buttons; suspended → "Disable" + "Reinstate"; disabled → "Reinstate"
  - each in a `Modal` confirm with required reason textarea (suspend/disable) / optional note (reinstate) → `postJson(\`/directory/businesses/${id}/${action}\`, {reason}|{note})`, toast result, refetch; 409/403 → toast the detail code.
  - enforcement log list under the card: `getJson(\`/directory/businesses/${id}/enforcement-log\`)` → rows `action · when · reason/prior from metadata` + "load more" via cursor.
- [ ] **Step 3: page.tsx** — server page copying `app/users/page.tsx` (auth redirect + noindex metadata) rendering the manager; add "Businesses" link on the admin home list.
- [ ] **Step 4:** i18n keys `ui.admin.businesses.*` (title, search, suspend, disable, reinstate, reasonLabel, confirmSuspend, confirmDisable, confirmReinstate, log heading, empty) ×3 locales; `pnpm --filter @agri/ui test`; app builds.
- [ ] **Step 5: Commit** `feat(m1x): ops reports tab + business enforcement console`

---

### Task 10: web-id — Member since

**Files:**
- Modify: `apps/web-id/app/account/account-manager.tsx` (`ProfileData.member_since: string`; render line)
- Modify: `packages/ui/src/i18n/messages/*.json` (`ui.auth.profile.memberSince` ×3)

- [ ] **Step 1:** add `member_since: string` to `ProfileData`; in the completion `<Card>` render `t("memberSince", {date})` with `Intl.DateTimeFormat` month+year using the account page's locale convention (web-id is EN-surface; use "en").
- [ ] **Step 2:** i18n key ×3 ("Member since {date}"); locale test; build.
- [ ] **Step 3: Commit** `feat(m1x): member-since on account dashboard`

---

### Task 11: Full gates, self-review, PR

- [ ] Backend: `pytest` full suite; `ruff format --check` / `ruff check`; `mypy`; `lint-imports`; verify no OFFSET/public-route gate breaks (`scripts/dump_public_routes.py --check` — no public routes added).
- [ ] Frontend: `pnpm turbo build` (or per-app builds), `pnpm --filter @agri/ui test`, check:hex.
- [ ] Verify the 4 non-negotiables map to green tests: NN1 `test_reports.py` (queue + invisibility), NN2+NN4 `test_business_enforcement.py`, NN3 enforcement + ads tests.
- [ ] Push `feat/m1x-trust-safety`, open PR → dev: `feat(m1x): reporting + enforcement + profile polish`, body summarizing A–E + threat-model coverage + test list.
