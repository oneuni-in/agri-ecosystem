# D15 — Directory Engine + Vendor↔Pincode Coverage — Design

**Date:** 2026-07-15 · **Branch:** `feat/d15-directory` · **Module:** `backend/core/modules/directory`

## Goal

First shared engine (~60% of the ecosystem rides on it). Businesses = any org/place
(vendors, shops, labs, farms). Milk.in is the first consumer; the module is
vertical-agnostic. Geo is TN-only (v5 D3 note), which is all Milk.in needs.

Out of scope (later specs): products (D17), reviews (D18), claim flow (D16).
Hard constraints: no cross-module imports (directory must not import identity —
`owner_user_id` is taken as a value from `request.state.principal`); no offset
pagination anywhere.

## 1. Data model — migration `0016_directory_v1` (schema `directory`)

- Chain: `Revises: 0015` (next in the committed chain; chain-linearity test extends to 0016).
- Schema `directory` already exists (created in `0001_schemas`); tables use the
  migration template helpers `pk_column()`, `timestamp_columns()`, `soft_delete_column()`
  and carry the standard `-- THREAT/NOTES:` header.
- **No immutability trigger** — business data is mutable and owner-scoped.
- **Grants:** explicit `GRANT SELECT, INSERT, UPDATE, DELETE ON <each table> TO app_rt`
  (0013 default privileges already cover new tables; the explicit grants are
  belt-and-braces and self-documenting, per the integration surface).

### Enums (schema `directory`)

| Enum | Values |
|---|---|
| `business_type` | `vendor`, `shop`, `lab`, `farm` |
| `business_status` | `active`, `suspended` |
| `verification_status` | `unverified`, `pending`, `verified` |
| `subscription_tier` | `free`, `premium` |

### Tables

**`directory.businesses`** — `id` (UUIDv7 PK), timestamps, `deleted_at`,
`owner_user_id` UUID NOT NULL (plain value, **no FK to identity**), `name` Text NOT NULL,
`slug` Text unique (ImmutableSlugMixin), `description` TranslatedString JSONB nullable,
`type` business_type NOT NULL, `status` business_status default `active`,
`verification_status` default `unverified`, `subscription_tier` default `free`,
`primary_pincode` Text NOT NULL.

> Status-default reconciliation: the global "user content defaults to pending"
> invariant is honored by anonymous UGC (D18 reviews). An owner-authenticated
> listing is first-party data: `status` defaults to `active`; the not-yet-trusted
> signal is `verification_status = unverified`, promoted by the D16 claim/verify flow.
> (Approved in brainstorming.)

**`directory.branches`** — `id`, timestamps, `deleted_at`, `business_id` FK →
businesses NOT NULL (indexed), `address` Text NOT NULL, `state` Text NOT NULL,
`district` Text NOT NULL, `pincode` Text NOT NULL (indexed), `lat`/`lng` Numeric(9,6)
nullable, `phone`/`whatsapp` Text nullable, `hours` JSONB default `{}`.

**`directory.categories`** — `id`, timestamps, `slug` Text unique, `name`
TranslatedString NOT NULL, `sort_order` Integer default 0. Seeded flat and
vertical-agnostic: farm, dairy, shop, lab, nursery, equipment, service, other.

**`directory.business_categories`** — `id`, timestamps, `business_id` FK,
`category_id` FK, UNIQUE(`business_id`, `category_id`).

**`directory.business_coverage`** — `id`, timestamps, `business_id` FK,
`pincode` Text NOT NULL, UNIQUE(`business_id`, `pincode`), index on (`pincode`).

Additional index: `businesses(primary_pincode)`.

## 2. `covers(pincode)` — distance-ordered keyset search

1. Resolve the searched pincode's centroid via `shared.geo.service.centroid_for_pincode()`.
   Unknown pincode → empty page (200, not 404 — it's a search).
2. Candidate set: businesses with a `business_coverage` row for that pincode,
   `status = 'active'`, `deleted_at IS NULL`.
3. **Distance anchor (decided):** nearest geocoded branch —
   `MIN(haversine(query_centroid, branch.lat/lng))` over the business's branches
   with non-null lat/lng; `COALESCE` fallback to
   `haversine(query_centroid, centroid of business.primary_pincode)` so every
   business always resolves an anchor.
4. Distance is computed in SQL (haversine expression over Numeric lat/lng) and
   **rounded to integer metres** so keyset comparisons are exact.
5. **Compound keyset** (custom, in the directory service — `shared.pagination.paginate()`
   is id-only): order by `(distance_m, id)`; opaque url-safe base64 cursor encoding
   `(distance_m: int, last_id: UUIDv7)`; page predicate
   `distance_m > :d OR (distance_m = :d AND id > :id)`; `limit+1` look-ahead for
   `next_cursor`, same style as `shared.pagination`. Malformed cursor → 400
   (`InvalidCursorError` semantics). No offset — deep-offset enumeration is
   structurally impossible (scraping threat model).

## 3. Service layer (`modules/directory/service.py`)

All owner-scoped: every write first loads the business via
`owned_by(select(Business), user_id, column="owner_user_id")`; a non-owner sees
no row → 404. Branch/coverage/category writes resolve ownership through the
parent business the same way (IDOR threat model).

- `create_business(session, owner_user_id, data)` — slugify name; on slug
  collision append a short suffix; sets defaults per §1.
- `update_business(session, owner_user_id, business_id, patch)` — mutable fields
  only (name, description, type, primary_pincode, contact-ish); **never** `slug`,
  `verification_status`, `subscription_tier`, `owner_user_id` (tier/verification
  change via D16/billing flows, not this API).
- `rename_business(session, owner_user_id, business_id, new_slug)` — wraps
  `shared.slugs.change_slug()`: updates slug and records
  `/directory/businesses/{old}` → `/directory/businesses/{new}` in
  `slug_redirects` in the same transaction (301 served by SlugRedirectMiddleware).
- `add_branch` / `update_branch` — via parent ownership.
- `set_coverage(session, owner_user_id, business_id, pincodes: list[str])` —
  declarative replace (delete missing, insert new; UNIQUE makes it idempotent).
  Pincodes validated as 6-digit strings; capped (e.g. 500) to bound abuse.
- `assign_categories(session, owner_user_id, business_id, category_ids)` —
  declarative replace against seeded categories.
- `list_my_businesses(session, owner_user_id, cursor, limit)` — `paginate()`.
- Public reads: `get_by_slug(session, slug)` (active, not deleted; joined
  branches + categories), `covers(session, pincode, cursor, limit)` per §2.
- `list_categories(session)` — small, seeded; still cursor-paginated via `paginate()`.

## 4. API (`modules/directory/router.py`, SecureRouter, prefix `/directory`)

**Public (`public=True`, rate-limited; added to `public_routes.txt` — exactly two):**

| Route | Justification |
|---|---|
| `GET /directory/businesses/{slug}` | SSR public business profile page (detail by slug). |
| `GET /directory/covers/{pincode}` | The vendor-discovery search Milk.in rides on; keyset + rate limit blunt scraping. |

**Private (default: auth + rate limit):**

- `POST /directory/businesses` — create (owner = principal).
- `GET /directory/businesses` — list my businesses (cursor).
- `PATCH /directory/businesses/{id}` — update (owner-scoped).
- `POST /directory/businesses/{id}/rename` — sanctioned slug change → 301.
- `POST /directory/businesses/{id}/branches` / `PATCH /directory/branches/{branch_id}`.
- `PUT /directory/businesses/{id}/coverage` — replace coverage set.
- `PUT /directory/businesses/{id}/categories` — replace category set.
- `GET /directory/categories` — seeded category list (private is fine for v1;
  public pages get categories embedded in the detail response).

Principal resolution copies the coins pattern: read
`request.state.principal.user_id` (set by `require_auth`) — no identity import.
Never log request bodies or query strings (module holds contact PII).

## 5. Events / headers

No header or event-stream changes in this spec (per integration surface).

## 6. Tests (non-negotiables first)

1. **covers(641001)** — seed businesses with branches/coverage around Coimbatore
   (real TN pincodes incl. 641001); assert distance ordering, the
   primary-pincode fallback for a branch-less business, and keyset paging across
   a page boundary (no duplicates/gaps; cursor tampering → 400).
2. **IDOR** — user B PATCHing/branching/covering user A's business → 404;
   B's list never contains A's rows.
3. **Slug** — direct `business.slug = x` raises `ImmutableSlugError`; rename
   endpoint records `slug_redirects` row; middleware serves 301 old → new;
   new slug serves 200.
4. **Migration chain** — linear through 0016 (extend existing chain test);
   migration round-trips (upgrade → downgrade → upgrade) on the test DB.
5. Router contract — the two public routes match `public_routes.txt`
   (`dump_public_routes.py --check` gate); everything else 401s unauthenticated.
6. Service unit tests — coverage replace idempotency, category assignment,
   pincode validation, unknown-pincode covers() → empty page.

## Definition of done

covers(641001) test green · IDOR + slug tests green · chain linear ·
`public_routes.txt` updated with exactly the two reads · PR → `dev` merged as
`feat(d15): directory engine`.
