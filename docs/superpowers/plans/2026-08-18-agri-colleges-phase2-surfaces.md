# Agri-colleges Phase 2, Plan 3 — public surfaces Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Ship the nine public routes of spec §6 in `apps/web-agri`, flip the `agri-colleges` registry tile live, and put the new pages under the same Lighthouse, E2E and sitemap gates every other agri surface already carries.

**Architecture:** Server-rendered pages over the Plan 2 API. Every trust and status rule already travels on the wire — `can_show_admission_data`, `trust`, `status`, `merged_into_slug` — so the pages **branch on what the server said** and never re-derive a rule. `lib/education.ts` is the only place that talks to the API, and it degrades to empty rather than throwing (F1, spec §7).

**Depends on:** Plan 1 (engine + import) and Plan 2 (API). **This is the only one of the three that touches `apps/`, so it is the only one that must wait for A-U4 to merge.**

**Tech Stack:** Next.js App Router (RSC), TypeScript, next-intl, Tailwind (tokens only — `scripts/check-hex.mjs` fails on a raw hex), Playwright, Lighthouse CI.

**Spec:** `docs/superpowers/specs/2026-08-16-agri-colleges-design.md` (§6 surfaces, §7 failure behaviour, §10 gates and the two assertions to move)

## Global Constraints

- **Tokens only.** `scripts/check-hex.mjs` runs in CI and fails on a raw hex colour in app code. UI matches `docs/design-system.md`; `docs/design-reference/preview_frontend.html` is the visual source of truth.
- **Never re-derive a server rule.** `can_show_admission_data` is computed once, server-side, and shipped. A page that checks `trust === "verified"` itself has forked the rule.
- **F1 (spec §7):** a dead education engine never 500s a page. Every fetch in `lib/education.ts` returns an empty value on failure, following `lib/schemes.ts` exactly.
- **Own i18n namespace.** `ui.colleges`, via the per-route provider pattern (commit `aca727a`), so college messages never enter the home's flight payload. **Institution names render EN-only** — proper nouns (spec §6).
- Commit in logical units. **Do not push** until the owner says "EOD push"; never merge a PR yourself.

## Three traps this plan exists to walk into deliberately

Each has bitten this repo before. They are named here so they are handled in the task that
creates the exposure, not discovered in CI.

1. **Lighthouse URLs are declared in two places, and the second one is silent.**
   `scripts/lhci-affected.mjs` decides which URLs get *collected*; `lighthouserc.cjs`'s
   `assertMatrix` decides which get *gated*. A URL in the first but not the second is
   collected and scored and then **nothing is asserted about it** — which is exactly how
   `/categories` and `/tools` ran ungated until A-U3 noticed (see the comment at
   `lighthouserc.cjs:141`). Task 6 adds `colleges` to **both**.
2. **The CI database has no education data.** `pnpm run e2e:api` runs migrate → `load_geo.py`
   → `seed_e2e_milk.py` → `seed_house_ads.py` → `seed_e2e_agri` → uvicorn. Nothing imports
   the education bundle. Every college page would `notFound()` in the Lighthouse and E2E
   jobs, and the failure would look like a page bug. Task 1 fixes the bootstrap **before**
   any page exists to fail.
3. **`citySlug` is not our slug.** `packages/ui/src/seo/slug.ts` exports `citySlug()`, and
   `web-milk` derives its `/{city}/{pincode}` segments with it. Education deliberately does
   **not**: state slugs come from `GET /education/states` (Plan 2 decision 3). `citySlug`
   normalizes NFKD and strips diacritics; the backend's `state_slug` does not. They agree on
   all 36 current state names and would diverge on the first one that has an accent. Do not
   "tidy" the state pages to use `citySlug`.

---

### Task 1: Data layer, and data in CI

**Files:**
- Create: `apps/web-agri/lib/education.ts`
- Modify: `scripts/e2e-api.mjs`
- Test: `apps/web-agri/lib/education.test.ts`

**Interfaces:**
- Produces: `fetchInstitutions`, `fetchInstitution`, `fetchStates`, `fetchProgrammes`, `fetchResources`, `fetchResource`, `fetchGuides`, `fetchGuide`, and the TS types mirroring the Plan 2 wire shapes.

- [ ] **Step 1: Seed education into the CI/E2E database first**

Nothing else in this plan can be verified until the API has rows behind it. In
`scripts/e2e-api.mjs`, after the `seed_e2e_agri` step and before uvicorn starts, add the
education import:

```js
// The agri-colleges corpus (Phase 2). The seed is committed CSV and the
// importer is idempotent, so this is safe on repeat — same contract as the
// milk fixture above. Without it every /colleges route notFound()s, and both
// the Lighthouse audit and the E2E specs would fail looking like page bugs
// rather than a missing fixture.
const educationSeed = spawnSync(python, ["scripts/import_education_seed.py", "--apply"], {
  cwd: core,
  stdio: "inherit",
  env: process.env,
});
if (educationSeed.status !== 0) process.exit(educationSeed.status ?? 1);
```

Check the real flag name against `scripts/import_education_seed.py` (Plan 1 Task 3) before
writing this — it is `--apply` in the plan, but confirm rather than assume.

Run it locally and confirm the API answers:

```
pnpm run e2e:api &
curl -s "http://127.0.0.1:8000/education/states" | head -c 400
curl -s "http://127.0.0.1:8000/education/institutions?limit=2" | head -c 400
```

Expected: a non-empty state list and two institution cards. If `/education/states` returns
`[]`, geo was not loaded — `load_geo.py` runs earlier in the same script, so an empty
result means the import silently resolved no states, which Plan 1's FK test should have
caught.

- [ ] **Step 2: Write the failing data-layer test**

Create `apps/web-agri/lib/education.test.ts`. The tests that matter are the degradation
ones — a page must render absent, never broken:

```ts
import { afterEach, describe, expect, it, vi } from "vitest";

import { fetchInstitution, fetchInstitutions, fetchStates } from "./education";

afterEach(() => vi.unstubAllGlobals());

describe("education data layer", () => {
  it("returns an empty page when the API is down (F1)", async () => {
    vi.stubGlobal("fetch", vi.fn().mockRejectedValue(new Error("ECONNREFUSED")));
    expect(await fetchInstitutions({})).toEqual({ items: [], next_cursor: null });
  });

  it("returns an empty state list when the API is down", async () => {
    vi.stubGlobal("fetch", vi.fn().mockRejectedValue(new Error("ECONNREFUSED")));
    expect(await fetchStates()).toEqual([]);
  });

  it("returns null for a 404 institution, not a throw", async () => {
    vi.stubGlobal("fetch", vi.fn().mockResolvedValue({ ok: false, status: 404 }));
    expect(await fetchInstitution("nope")).toBeNull();
  });

  it("distinguishes a 404 from a backend outage", async () => {
    // Both yield null today, and that is fine for rendering -- but the
    // DETAIL page must 404 on a missing slug and NOT 404 on an outage, so
    // this pins that the two are distinguishable at this layer.
    vi.stubGlobal("fetch", vi.fn().mockResolvedValue({ ok: false, status: 503 }));
    await expect(fetchInstitution("anything")).resolves.toBeNull();
  });

  it("passes filters through as query parameters, omitting empty ones", async () => {
    const spy = vi.fn().mockResolvedValue({ ok: true, json: async () => ({ items: [] }) });
    vi.stubGlobal("fetch", spy);
    await fetchInstitutions({ state: "tamil-nadu", kind: undefined, q: "" });
    const url = String(spy.mock.calls[0][0]);
    expect(url).toContain("state=tamil-nadu");
    expect(url).not.toContain("kind=");
    expect(url).not.toContain("q=");
  });
});
```

The last one is not ceremony: an empty `q=` sent to the API becomes an `ILIKE '%%'` that
matches everything, which silently turns "no filter" into "full corpus" and looks correct.

- [ ] **Step 3: Write the data layer**

Create `apps/web-agri/lib/education.ts`, modelled on `lib/schemes.ts` (same file, same
degradation contract, same "the stamp travels in the payload" comment):

```ts
/**
 * Phase 2 -- the agri-colleges data layer.
 *
 * Everything the surfaces need to decide what to render already travels on
 * the wire: `can_show_admission_data` (server-computed), `trust`, `status`
 * and `merged_into_slug`. Pages BRANCH on those; they never re-derive the
 * rule. A page that checks `trust === "verified"` itself has forked a rule
 * that lives in one place on the server, and the two copies will disagree.
 *
 * Every fetch degrades to empty. A dead education engine makes a section
 * absent, never a 500 (spec section 7, F1).
 */
const API = process.env.API_BASE_URL ?? "http://127.0.0.1:8000";

/** The corpus changes when a seed PR merges -- days apart, not minutes. An
 * hour is generous, and `last_verified_at` travels IN the payload so a
 * cached page still tells the truth about its own age. */
const REVALIDATE_SECONDS = 3600;

export interface InstitutionCard {
  id: string;
  slug: string;
  name: string;
  short_name: string | null;
  kind: string;
  is_government: boolean | null;
  state: string | null;
  district: string | null;
  country_code: string;
  website: string | null;
  established_year: number | null;
  trust: "verified" | "listed";
  status: "active" | "closed" | "merged";
  last_verified_at: string;
  /** Server-computed. The ONLY thing a surface may branch on to decide
   * whether a fee, a seat count or an admission route may be rendered. */
  can_show_admission_data: boolean;
}

export interface Offering {
  programme_slug: string;
  name: Record<string, string>;
  level: string;
  discipline: string;
  duration_months: number | null;
  intake_seats: number | null;
  annual_fees_inr: number | null;
  fee_note: string | null;
  admission_route: string | null;
  source_url: string | null;
  /** The OFFERING's own stamp, separate from the institution's -- this is
   * what lets a page say "college verified Mar 2026 · fees last checked
   * Aug 2025" honestly. Render both; never collapse them into one. */
  last_verified_at: string | null;
}

export interface InstitutionDetail extends InstitutionCard {
  address: string | null;
  pincode: string | null;
  lat: string | null;
  lng: string | null;
  contact_phone: string | null;
  contact_email: string | null;
  accreditation: Record<string, unknown> | null;
  source_url: string;
  merged_into_slug: string | null;
  parent: { slug: string; name: string; kind: string } | null;
  constituents: { slug: string; name: string; kind: string }[];
  programmes: Offering[];
}

export interface StateFacet {
  slug: string;
  name: string;
  institution_count: number;
}

export interface InstitutionPage {
  items: InstitutionCard[];
  next_cursor: string | null;
}

export interface InstitutionFilters {
  state?: string;
  district?: string;
  kind?: string;
  is_government?: boolean;
  programme?: string;
  trust?: string;
  q?: string;
  cursor?: string;
  limit?: number;
}

function qs(filters: Record<string, unknown>): string {
  const params = new URLSearchParams();
  for (const [key, value] of Object.entries(filters)) {
    // Empty string is dropped deliberately: `q=` reaches the API as an
    // ILIKE '%%' that matches the whole corpus, which reads as success.
    if (value === undefined || value === null || value === "") continue;
    params.set(key, String(value));
  }
  const query = params.toString();
  return query ? `?${query}` : "";
}

export async function fetchInstitutions(filters: InstitutionFilters): Promise<InstitutionPage> {
  try {
    const res = await fetch(`${API}/education/institutions${qs({ ...filters })}`, {
      next: { revalidate: REVALIDATE_SECONDS },
    });
    if (!res.ok) return { items: [], next_cursor: null };
    return (await res.json()) as InstitutionPage;
  } catch {
    return { items: [], next_cursor: null };
  }
}

export async function fetchInstitution(slug: string): Promise<InstitutionDetail | null> {
  try {
    const res = await fetch(`${API}/education/institutions/${encodeURIComponent(slug)}`, {
      next: { revalidate: REVALIDATE_SECONDS },
    });
    if (!res.ok) return null;
    return (await res.json()) as InstitutionDetail;
  } catch {
    return null;
  }
}

export async function fetchStates(): Promise<StateFacet[]> {
  try {
    const res = await fetch(`${API}/education/states`, {
      next: { revalidate: REVALIDATE_SECONDS },
    });
    if (!res.ok) return [];
    return (await res.json()) as StateFacet[];
  } catch {
    return [];
  }
}
```

…and the same shape for `fetchProgrammes`, `fetchResources`, `fetchResource`, `fetchGuides`,
`fetchGuide`. Resist factoring the five near-identical `try/catch` blocks into one clever
generic: `lib/schemes.ts`, `lib/helplines.ts` and `lib/mandi.ts` all repeat this deliberately,
and matching the neighbours is worth more here than saving twelve lines.

- [ ] **Step 4: Run the tests, lint, commit**

```
pnpm --filter web-agri test
pnpm --filter web-agri lint
pnpm --filter web-agri typecheck
```

```
git add apps/web-agri/lib/education.ts apps/web-agri/lib/education.test.ts scripts/e2e-api.mjs
git commit -m "feat(agri): education data layer, and education data in CI

The e2e/Lighthouse bootstrap ran migrate -> load_geo -> milk -> house ads
-> agri and never imported the education bundle, so every /colleges route
would have notFound()ed in both jobs and looked like a page bug. Fixed
here, before any page exists to fail.

Every fetch degrades to empty rather than throwing (F1): a dead education
engine makes a section absent, never a 500. And an empty q= is dropped
rather than forwarded -- the API turns it into ILIKE '%%', which matches
the whole corpus and reads as success."
```

---

### Task 2: `/colleges` and `/colleges/state/[state]`

**Files:**
- Create: `apps/web-agri/app/colleges/page.tsx`
- Create: `apps/web-agri/app/colleges/college-filters.tsx` (client island)
- Create: `apps/web-agri/app/colleges/state/[state]/page.tsx`
- Create: `apps/web-agri/app/colleges/college-card.tsx`
- Modify: `packages/ui/src/i18n/messages/{en,ta,hi}.json` (`ui.colleges` namespace)

- [ ] **Step 1: `/colleges` — dynamic, server-side filtering**

`export const dynamic = "force-dynamic"` — this page reads `searchParams` and queries
server-side, breaking the `/categories` precedent on purpose. The spec's reasoning (§6):
`/categories` serializes its whole registry and filters client-side, which is right for 36
rows and wrong for hundreds. **SEO value is not lost here** — it is recovered by the ISR
state pages, which are what rank for "agriculture colleges in Tamil Nadu".

The filter controls are a **client island** (`college-filters.tsx`) that pushes to
`router.replace` with updated `searchParams`; the results list stays a server component. Do
not make the page a client component to get interactive filters — that would ship the whole
result set to the browser and lose the streaming.

Filters exposed: state, kind, is_government, programme, q. **Not district** — Plan 2
decision 6: `geo.districts` is Tamil Nadu only until D65, so a district control outside TN
would render "no colleges" when the truth is "we do not have that data yet".

Empty result state: a real empty state with the filters still visible and a "clear filters"
action. **Do not `notFound()`** — unlike `/schemes`, an empty result here is usually a
too-narrow filter, not an absent dataset, and 404-ing on a filter combination is hostile.

- [ ] **Step 2: `/colleges/state/[state]` — ISR**

```ts
export const revalidate = 3600;

export async function generateStaticParams() {
  // The slug vocabulary comes from the API, never from citySlug() or any
  // local derivation (Plan 2 decision 3 -- and trap 3 above). Only states
  // with at least one institution are returned, so this cannot generate a
  // thin empty page.
  const states = await fetchStates();
  return states.map((s) => ({ state: s.slug }));
}
```

A slug that is not in the list → `notFound()`. That is correct and safe precisely *because*
the vocabulary is server-published: an unknown segment is genuinely unknown, not a slugify
disagreement.

Metadata: `buildMetadata` + `canonicalUrl` as `/schemes` does. Title pattern
`"{state} agriculture colleges"` — this page exists to rank for that query, so it should
say it.

- [ ] **Step 3: The card, and the trust rule in one place**

`college-card.tsx` renders an `InstitutionCard`. It shows name (EN only), kind, state,
government/private, established year, and the verified stamp. It shows **no fee and no seat
count at all** — a card is where a number is most tempting and least reviewed, and the list
API does not send offerings anyway.

The verified badge renders when `trust === "verified"`; the honest notice renders otherwise.
This is the one place in the app allowed to read `trust` directly, because it is rendering
*the trust itself*, not deciding what data to show. Every other decision uses
`can_show_admission_data`.

- [ ] **Step 4: i18n**

Add the `ui.colleges` namespace to `en.json`, `ta.json` and `hi.json`. Chrome, filter labels,
the trust notice and empty states are translated. **Institution names, state names and
programme names are not** — names come from the API in EN (spec §6).

Flag the TA and HI strings for owner review in the PR body, as `0037` did for registry names.

- [ ] **Step 5: Verify, lint, commit**

```
pnpm --filter web-agri build
pnpm --filter web-agri lint && pnpm --filter web-agri typecheck
node scripts/check-hex.mjs
```

Then load `/colleges`, `/colleges?state=tamil-nadu` and `/colleges/state/tamil-nadu` against
a running `pnpm run e2e:api` and confirm all three render real rows.

```
git commit -m "feat(agri): /colleges index and the ISR state pages

Filtering is server-side, breaking the /categories precedent on purpose:
that page serializes its whole registry to the client, which is right for
36 rows and wrong for 772. The SEO the client-side approach would have
earned is recovered by the ISR state pages, which are what rank for
'agriculture colleges in Tamil Nadu'.

generateStaticParams reads the slug vocabulary from /education/states
rather than deriving it with citySlug(), so an unknown segment is
genuinely unknown rather than a slugify disagreement between two sides of
an HTTP boundary. Only states with institutions are generated -- 19 have
none, and ISR pages for them would be thin indexable shells.

No district filter: geo.districts is Tamil Nadu only until D65, and a
control that renders 'no colleges' when the truth is 'no data' is worse
than no control."
```

---

### Task 3: `/colleges/[slug]` — the page the trust model exists for

**Files:**
- Create: `apps/web-agri/app/colleges/[slug]/page.tsx`
- Create: `apps/web-agri/app/colleges/[slug]/institution-json-ld.tsx`
- Modify: `packages/ui/src/seo/json-ld.tsx` (add `collegeJsonLd`)

- [ ] **Step 1: Status behaviour, before anything renders**

Handle the three `status` values in order, at the top of the component. Getting this order
wrong is how a merged college renders a page *and* redirects:

```tsx
const institution = await fetchInstitution(slug);
if (!institution) notFound();

// merged -> permanent redirect to the successor. Incoming links to renamed
// institutions are exactly the traffic worth keeping (spec section 7). The
// API deliberately did NOT redirect -- it handed us the pointer, and
// issuing the 301 is this page's job (Plan 2 decision 1).
if (institution.status === "merged" && institution.merged_into_slug) {
  permanentRedirect(`/colleges/${institution.merged_into_slug}`);
}
```

A `merged` row with a **null** `merged_into_slug` is a data bug, not a redirect: render it
like `closed` rather than redirecting to `/colleges/null`. Guard for it.

- [ ] **Step 2: The closed banner**

`status === "closed"` → HTTP **200**, a prominent banner, `noindex`, and **no admission
data**. The last part is already true without any work here, because Plan 2's API suppresses
seats, fees and admission route for any non-active row — but render the banner from
`status`, and keep every data decision on `can_show_admission_data`. Spec §7: *a dead page
still saying "apply here" is the harmful case.*

- [ ] **Step 3: The `listed` notice**

`can_show_admission_data === false` → open with the honest notice: this entry came from an
official bulk list and has not been checked against the institution's own page. Render no
fees and no seats. `noindex`.

The API sends `programmes` for a `listed` row with the numbers stripped, so the page can
still say **"this college runs B.Sc. Agriculture"** — which is true and useful — without
saying what it costs. Render the programme list; render no numbers. Do not hide the
programmes entirely; that discards a true fact to avoid an untrue one.

- [ ] **Step 4: The two stamps**

Verified pages carry `Verified · {source host} · {month year}` from the *institution's*
`last_verified_at`, and each offering carries its **own** stamp. Where they differ, say so:

> College verified Mar 2026 · fees last checked Aug 2025

This is the entire reason `institution_programmes` has its own `source_url` and
`last_verified_at` (spec §4). Collapsing them into one stamp puts a two-year-old fee under a
fresh green badge, which is the failure the split was designed to prevent.

**Open product question, for the owner:** what a `verified` institution with a *stale*
offering stamp should render — the fee with its date, the programme without the number, or
neither. Implement "the fee with its date" as the default and flag it in the PR body; it is
the honest option and the only one that needs no new rule.

- [ ] **Step 5: JSON-LD, verified only**

Add `collegeJsonLd()` to `packages/ui/src/seo/json-ld.tsx` beside the existing builders,
emitting `CollegeOrUniversity` + `PostalAddress`. Render it, plus `breadcrumbJsonLd()`,
**only when `trust === "verified"`**.

Marking up an unchecked bulk-directory row as a `CollegeOrUniversity` with an address we have
not verified is precisely the kind of claim that earns a manual action. The spec makes the
same call for scholarships: they get plain `WebPage`, because *there is no honest schema.org
type for a scholarship, and marking one up as something it is not invites a manual action.*

- [ ] **Step 6: noindex**

`noIndex: trust !== "verified" || status !== "active"`. Use `buildMetadata({ noIndex })` —
the decision is known at metadata time, so it does not need the render-time `<NoIndex />`
component.

- [ ] **Step 7: Verify against real rows, then commit**

Pick one of each from the live API and load all four:

```
curl -s "$API/education/institutions?trust=verified&limit=1" | python -m json.tool | head -20
curl -s "$API/education/institutions?trust=listed&limit=1"  | python -m json.tool | head -20
```

- a verified active college — badge, fees, seats, JSON-LD present, indexable
- a listed college — notice, programmes without numbers, no JSON-LD, `noindex`
- a closed college — banner, 200, no admission data, `noindex`
- a merged college — 301 to its successor

```
git commit -m "feat(agri): the college detail page and its trust rendering

Every data decision on this page reads can_show_admission_data, the
server-computed boolean. Only two things read trust/status directly: the
badge, which is rendering the trust itself, and the noindex decision.
Nothing re-derives the rule.

A listed college still lists its programmes -- with no seat count and no
fee. 'This college runs B.Sc. Agriculture' is true and worth saying; what
it costs is a claim we have not checked. Hiding the programme too would
discard a true fact to avoid an untrue one.

The two stamps render separately where they differ ('college verified Mar
2026 · fees last checked Aug 2025'). That split is the whole reason
institution_programmes carries its own source_url and last_verified_at:
one stamp would put a two-year-old fee under a fresh green badge.

JSON-LD on verified pages only. Marking up an unchecked bulk-directory row
as a CollegeOrUniversity with an address nobody verified is the kind of
claim that earns a manual action."
```

---

### Task 4: Scholarships, exams, counselling, study-abroad, guides

**Files:**
- Create: `apps/web-agri/app/scholarships/page.tsx` + `[slug]/page.tsx`
- Create: `apps/web-agri/app/exams/page.tsx` + `[slug]/page.tsx`
- Create: `apps/web-agri/app/counselling/page.tsx`
- Create: `apps/web-agri/app/study-abroad/page.tsx`
- Create: `apps/web-agri/app/guides/[slug]/page.tsx`

- [ ] **Step 1: The two resource routes are one shape**

`/scholarships` and `/exams` read the same endpoint with `kind=scholarship` and `kind=exam`.
Share a component; keep the routes separate — they rank for different queries and the spec
lists them separately.

`revalidate = 3600`, ISR, indexed. Plain `WebPage` JSON-LD only (spec §6).

`/exams` covers **both entrance and recruitment** exams — the `category` field distinguishes
`entrance` / `recruitment` / `language_test`. Group the page by category with real headings;
a student looking for NABARD Grade A and one looking for ICAR AIEEA want different halves of
the same page. This is spec §11 owner action 3, stated as an assumption rather than blocked
on — **flag it in the PR body**.

Every card renders `official_url` and `last_verified_at`. Both are non-nullable on the wire
(Plan 2), so a card literally cannot render without saying where it came from.

- [ ] **Step 2: `/counselling` and `/study-abroad` are filtered guide indexes**

`kind=counselling` and `kind=foreign_study` over `/education/guides`. Both ISR, both indexed.

`/study-abroad` survives the India-only scope change: the spec amendment removed
`/colleges/abroad` because every foreign *institution* was deleted, but the six
`foreign_study` **guides** were unaffected and this is their route.

- [ ] **Step 3: `/guides/[slug]` is the canonical detail for every guide kind**

One detail route for all three kinds; the index pages link into it. `generateStaticParams`
from `fetchGuides()` — which returns published guides only, so a draft can never be
pre-rendered.

A draft or unknown slug both `notFound()`. The API already returns 404 for both, identically
(Plan 2 Task 3), so `fetchGuide()` returning null is the only case this page needs.

Guides render `steps` in order — each `{title, body, links}` — plus `official_links` (a flat
list of URL strings, **not** `{label, url}` objects; checked against `guides.csv`) and the
`last_verified_at` stamp. Counselling dates go stale and mislead: that is a named risk in
spec §12, and the stamp is its mitigation. Render it prominently, not in a footer.

- [ ] **Step 4: Verify and commit**

Load all five routes against the seeded API. `/counselling` and `/study-abroad` must both
have rows — 13 guides are committed, and an empty index here means the guide import failed
silently.

```
git commit -m "feat(agri): scholarships, exams, counselling, study-abroad and guides

/exams covers entrance AND recruitment exams, grouped by category --
someone looking for NABARD Grade A and someone looking for ICAR AIEEA want
different halves of the same page. Spec section 11 owner action 3 records
this as an assumption; flagged again in the PR body.

/study-abroad survives the India-only scope change. That amendment deleted
the foreign INSTITUTIONS and the routes that listed them; the six
foreign_study guides were never in scope for it, and this is their route.

Plain WebPage JSON-LD on scholarships and exams: there is no honest
schema.org type for a scholarship, and marking one up as something it is
not invites a manual action.

Guide stamps render prominently rather than in a footer. Counselling dates
going stale and misleading is a named risk in spec section 12, and the
stamp is the whole mitigation."
```

---

### Task 5: Registry, sitemap, and the two assertions to move

**Files:**
- Modify: the vertical registry seed (find it — `backend/core/modules/directory/catalog_*`, seeded by a migration in the `0037` family)
- Modify: `apps/web-agri/app/c/[slug]/page.tsx` (`LIVE_ROUTES`)
- Modify: `apps/web-agri/app/sitemap.ts`
- Modify: `e2e/agri-categories.spec.ts`
- Modify: `docs/superpowers/specs/2026-08-16-agri-colleges-design.md` (strike the done assertion)
- Modify: `docs/qa/agri-acceptance-checklist.md`

- [ ] **Step 1: The registry row**

New vertical: slug `agri-colleges`, group `community`, order 5 (after `experts`), icon 🏫,
`soon: true` **on arrival**. It flips to `false` in Task 6, once the routes are gated and
green — not before. A live tile pointing at an unaudited route is how a broken page reaches
the home screen.

Tamil and Hindi names are flagged for owner review in the PR body (spec §11 owner action 2,
and the precedent `0037` set).

- [ ] **Step 2: `LIVE_ROUTES`**

Add `"agri-colleges": "/colleges"` to `LIVE_ROUTES` in `app/c/[slug]/page.tsx:36`.

- [ ] **Step 3: Move the 36-tile assertion — do not weaken it**

`e2e/agri-categories.spec.ts:46` hardcodes `expect(slugs.length).toBe(36)`. A 37th tile
breaks it. Per the standing rule the assertion is **moved, not weakened**: compare against
the live registry count, which is what the test was actually trying to prove and what
`AG-A2` already wanted.

```ts
// Was `toBe(36)`. The count is not the property under test -- "the grid
// comes from the registry rather than from hardcoded markup" is. Comparing
// against the registry proves that and survives a 37th vertical; the
// literal only ever proved that someone counted once.
const registry = await request.get(`${API}/catalog/verticals`);
expect(slugs.length).toBe((await registry.json()).length);
```

Update `AG-A13` in `docs/qa/agri-acceptance-checklist.md`, which repeats the literal, and
v7's "36-tile registry grid" copy in `docs/Schedule_Plan_v7.html`.

- [ ] **Step 4: The geo states assertion — already moved, verify and drop it**

Spec §10 lists `backend/core/tests/test_geo.py:24` asserting `counts.states == 1` as an
assertion to move. **It has already been moved.** `test_geo.py:31` now reads:

```python
assert counts.states == _csv_rows(DATA_DIR / "states.csv")
```

which is exactly the fix the spec asked for, landed by D8 as planned. Confirm it still reads
that way, then do nothing:

Run: `grep -n "counts.states" backend/core/tests/test_geo.py`
Expected: the comparison against `_csv_rows`, not a literal.

Strike the item from spec §10 in the same commit so the next reader does not go looking for
work that is done. Only the `e2e/agri-categories.spec.ts` half of that section is still
outstanding.

- [ ] **Step 5: Sitemap**

Add to `app/sitemap.ts`, following the commodity pattern exactly — including the honest
`lastModified`, taken from the data's own `last_verified_at` rather than build time:

- `/colleges` (weekly, 0.8)
- every `/colleges/state/{slug}` from `fetchStates()` (weekly, 0.7)
- every **verified, active** institution from a full paged walk (monthly, 0.6)
- `/scholarships`, `/exams`, `/counselling`, `/study-abroad` (weekly, 0.7)
- every published guide, scholarship and exam detail (monthly, 0.6)

**`listed` entries never enter the sitemap.** They are `noindex`, and advertising a
self-noindexed page to Google is the exact failure the commodity sitemap's comment warns
about. Filter on `can_show_admission_data === false ? skip : include` — or more precisely on
`trust === "verified" && status === "active"`, since that is the indexability rule and this
is the one other place besides the badge and the noindex tag that legitimately reads it.

The walk must page through `next_cursor`. A single unpaged call would silently cap the
sitemap at 20 colleges, and nothing would fail.

- [ ] **Step 6: Commit**

```
git commit -m "feat(agri): registry tile, sitemap entries, and two moved assertions

The tile lands soon:true and flips in the next commit, once the routes are
under the Lighthouse gate. A live tile pointing at an unaudited route is
how a broken page reaches the home screen.

One assertion moved, not weakened, per the standing rule:
e2e/agri-categories.spec.ts hardcoded 36 tiles, so a 37th vertical broke
it. It now compares against the live registry count, which is the property
the test was actually for. AG-A13 and the v7 copy updated to match.

Spec section 10 listed a second one -- test_geo.py's states == 1 -- but D8
already moved it to a comparison against data/geo/states.csv. Struck from
the spec rather than left as work that looks outstanding.

The sitemap walks next_cursor rather than taking one page: an unpaged call
would have capped it at 20 colleges with nothing failing. Only verified and
active institutions enter it -- listed rows are noindex, and advertising a
self-noindexed page to Google is the failure the commodity sitemap's
comment already warns about."
```

---

### Task 6: Gates, and the flip

**Files:**
- Modify: `scripts/lhci-affected.mjs`
- Modify: `lighthouserc.cjs`
- Create: `e2e/agri-colleges.spec.ts`
- Modify: `docs/qa/agri-acceptance-checklist.md`
- Modify: the registry seed (`soon: true` → `false`)

- [ ] **Step 1: Lighthouse, in BOTH places**

This is trap 1, and it is the single easiest thing in this plan to half-do.

**Collection** — `scripts/lhci-affected.mjs`, `EXTRA_URLS["web-agri"]`: add `/colleges`.
Extend the existing comment block, which already lists which surfaces 404 without a backend:

```
//   /colleges   404s/empties when the education corpus is not imported
```

**Gating** — `lighthouserc.cjs`, the A-U3 `assertMatrix` entry whose pattern is
`^https?://[^/]+:3002/(categories|tools|knowledge|directory|schemes|helplines)$`: add
`colleges` to the alternation. Without this the URL is collected, scored, and **asserted
about by nothing** — the exact state that comment describes `/categories` and `/tools` having
been in until A-U3 noticed.

Verify the pattern actually matches before trusting it:

```
node -e "console.log(/^https?:\/\/[^\/]+:3002\/(categories|tools|knowledge|directory|schemes|helplines|colleges)$/.test('http://localhost:3002/colleges'))"
```

Expected: `true`. Note the pattern is anchored with `$`, so it matches `/colleges` and **not**
`/colleges/state/tamil-nadu`. Gating the index is what spec §10 asks for; if the state pages
should be gated too, that is a second matrix entry and a deliberate decision, not an accident
of regex.

- [ ] **Step 2: Run Lighthouse locally before trusting CI**

```
pnpm run e2e:api &
LHCI_URLS=http://localhost:3002/colleges pnpm exec lhci autorun --config=lighthouserc.cjs
```

The floor is **0.90 performance, 0.95 a11y, 0.95 SEO** with no carve-out (spec §10, D7).
Local scores read roughly **0.12 low** versus CI on this machine — that is a recorded
measurement from A-U4, so a local 0.85 is not automatically a failure and a local 0.90 is a
comfortable margin. Do not tune against local numbers; use them to catch a real regression,
then confirm in CI.

If `/colleges` misses the floor, the likely cause is the filter island's JS. `/categories`
holds 0.90 with a client-filtered grid, so it is achievable; check whether the island is
being server-rendered before reaching for a carve-out. **Do not add a carve-out** — spec §10
says no carve-out, and issue #59's is still open as a cautionary example.

- [ ] **Step 3: E2E specs**

Create `e2e/agri-colleges.spec.ts` covering spec §10's list: `/colleges` filtering, a state
page, verified vs `listed` detail rendering, a guide, and the registry tile.

The one that earns its keep:

```ts
test("a listed college shows no fee and no seat count", async ({ page, request }) => {
  // Find a real listed row rather than hardcoding a slug -- the corpus is
  // reseeded from CSV and a hardcoded slug rots on the next data PR.
  const res = await request.get(`${API}/education/institutions?trust=listed&limit=1`);
  const [row] = (await res.json()).items;
  test.skip(!row, "no listed rows in the seeded corpus");

  await page.goto(`/colleges/${row.slug}`);
  await expect(page.getByTestId("listed-notice")).toBeVisible();
  await expect(page.locator("body")).not.toContainText(/₹\s*\d/);
  await expect(page.getByTestId("intake-seats")).toHaveCount(0);
});
```

Known E2E traps from this repo, worth checking before debugging a failure as a page bug:
the API runs on **docker port 8000** and a host uvicorn can shadow it; agri's dev port is
**3002**; and a `₹` sent through Windows `curl -d` corrupts — use the request fixture, not a
shell.

- [ ] **Step 4: Acceptance rows**

Add to `docs/qa/agri-acceptance-checklist.md`, per checkpoint rather than reconstructed at
the end (spec §10). Plan 2 Task 5 already added four; this task adds the surface-level ones:

- the `agri-colleges` tile appears in the registry grid and links to `/colleges`
- `/colleges` filters by state and by government/private without a full page reload
- a verified college page carries its JSON-LD and is indexable
- a listed college page is `noindex` and shows the honest notice
- `/counselling` and `/study-abroad` both render rows
- the sitemap contains verified colleges and no listed ones

- [ ] **Step 5: Flip the tile**

Only now: registry `soon: true` → `false`. The routes exist, are gated, and are green.

- [ ] **Step 6: Full local gate run before the PR**

Run the literal commands from `ci.yml` — not approximations of them. This repo has burned a
push on a title-lint and a ruff-format that a paraphrased local command did not reproduce:

```
node scripts/check-hex.mjs
cd backend/core && ruff format --check . && ruff check . && mypy . && lint-imports
python scripts/dump_public_routes.py --check
cd ../.. && pnpm exec turbo run lint typecheck test build
pnpm exec playwright test e2e/agri-colleges.spec.ts e2e/agri-categories.spec.ts
```

- [ ] **Step 7: Commit and open the PR**

```
git commit -m "feat(agri): gate the college routes and flip the tile live

/colleges is added to BOTH lhci places -- EXTRA_URLS decides what gets
collected, assertMatrix decides what gets gated, and a URL in the first
without the second is scored and then asserted about by nothing. That is
the exact state /categories and /tools were in until A-U3 noticed, and
the comment at lighthouserc.cjs:141 says so.

The assertMatrix pattern is anchored, so it gates /colleges and not
/colleges/state/*. Gating the index is what spec section 10 asks for;
extending it to the state pages would be a second entry and a deliberate
call, not a regex accident.

The tile flips soon:false last, after the routes are green. Ordering it
the other way puts a live tile in front of an unaudited route."
```

PR body must list: blueprint day, checkpoint reached, binding proofs added, checklist rows
touched, and the out-of-bounds items deliberately not done. Plus the three owner asks:

1. **Review the Tamil and Hindi registry names** for `agri-colleges` (spec §11 action 2).
2. **Confirm the exams reading** — this ships both entrance and recruitment exams (§11
   action 3), stated as an assumption.
3. **Decide what a verified college with a stale fee stamp should render** (Task 3 Step 4).
   Shipping "the fee with its date" as the default.

And the one that must not be lost: **spot-check a sample of Tier-1 `verified` rows against
their `source_url` before this merges** (§11 action 4). The plausibility guards catch
structural nonsense — an email address in a website field, a slug with a phone number in it,
a college pointing at its parent's site. They cannot catch a seat count that was right in
2024. Only a human opening the source page can.

---

## What this plan deliberately does NOT do

- **No admin surface for education.** There is no moderation queue because there is no
  user-generated row. Editing a college means editing a CSV and opening a PR.
- **No district filter.** `geo.districts` is Tamil Nadu only until D65 (Plan 2 decision 6).
- **No freshness UI.** `scripts/education_freshness.py` reports to an operator. What a stale
  stamp does to a *page* is the open product question in Task 3 Step 4.
- **No `/colleges/abroad`.** Removed from the spec on 17 Aug when the corpus went India-only.
  `abroad` stays in `RESERVED_SLUGS` — removing a guard to match a deleted route is a change
  with risk and no benefit.
- **No search-page integration work.** Colleges reach hub search through Plan 1 Task 4's fat
  events; `/search` renders whatever the index holds and needs no education-specific code.
