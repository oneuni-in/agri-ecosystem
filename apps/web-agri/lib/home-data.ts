import { cache } from "react";

import { HOME_HERO_SLOT, serveAds } from "./ads";
import { fetchKnowledgeSection } from "./content";
import { fetchHelplines } from "./helplines";
import {
  fetchDirectoryRow,
  fetchReviewSignals,
  fetchToday,
  fetchVerticals,
} from "./home";

/**
 * A-U4 W0 — the home's read layer, one accessor per data class.
 *
 * WHY THIS FILE EXISTS. Before W0 the home awaited all eight reads in a single
 * `Promise.all` and rendered the whole 1,066-element document in one shot, so
 * nothing painted until the slowest read returned: measured server-response
 * 900 ms on `/` against 60 ms on `/categories`. W0 puts every below-fold
 * section behind its own Suspense boundary, which means those sections now
 * fetch independently — and a section that fetches independently will refetch
 * the SAME endpoint its neighbour just asked for.
 *
 * `cache()` is what makes that safe: it memoises per REQUEST, so §3, §6b, §7,
 * §7b, §8 and §9 can each call `todayFor(pincode)` and exactly one HTTP call
 * leaves the server. Without it, splitting the page into boundaries would
 * trade first-byte latency for a fan-out storm — the "no unbounded
 * per-request fan-out" rule, enforced in code rather than by convention.
 *
 * CACHE WINDOWS, by data class. Each is a claim about how fast the underlying
 * truth moves, not a knob turned until the number looked good:
 *   - mandi + weather (`todayFor`) ....... 60 s   — prices move intraday
 *   - directory / reviews ................ 300 s  — a business's row is stable
 *   - editorial content .................. 300 s  — changes on human approval
 *   - vertical registry .................. 3600 s — changes on a migration
 *   - helplines .......................... 86400 s — changes on the order of years
 *   - ads ................................ NEVER  — see `heroAdsFor`
 */

/**
 * §2b/§3/§6b/§7/§7b/§8/§9 — the TODAY payload.
 *
 * Read by six sections spread across the page; `cache()` collapses them to one
 * call. The 60 s window is a deliberate change from A-U1's `cache: "no-store"`:
 * that comment argued "a cached today is yesterday's lie", which is true of a
 * DAY and false of a minute. Mandi prices are published per session and weather
 * per hour, so a minute-old payload is the same payload — while `no-store` put
 * a guaranteed upstream round trip in front of first byte on every single hit,
 * including the crawler's and the returning visitor's.
 */
export const todayFor = cache(async (pincode: string) =>
  fetchToday(pincode, { revalidate: 60 }),
);

/** §6 category grid + §14 stats band — the registry. Adding a vertical is a
 * migration, so an hour is generous and still same-day. */
export const verticalsForHome = cache(async () => fetchVerticals());

/** §10 directory row — businesses covering the visitor's pincode. */
export const directoryFor = cache(async (pincode: string) =>
  fetchDirectoryRow(pincode),
);

/**
 * §10 rating meta + §15 review strip + §14's review total, from the SAME D18
 * signals seam. Chained off `directoryFor` so the two stay consistent: the
 * ratings rendered on a card and the reviews rendered below it describe the
 * same set of businesses, and `cache()` means the §10, §14 and §15 boundaries
 * share one resolution of that chain.
 */
export const reviewSignalsFor = cache(async (pincode: string) =>
  fetchReviewSignals(await directoryFor(pincode), 2),
);

/** §11 knowledge cards + news rail — one call, deduped against itself upstream
 * so a story cannot appear twice. */
export const knowledgeForHome = cache(async () => fetchKnowledgeSection(3, 6));

/** §13 helpline band. */
export const helplinesForHome = cache(async () => fetchHelplines());

/**
 * §4 hero ad — the ONE read that must never be cached.
 *
 * `serveAds` forwards the viewer's UA and XFF so the engine can apply
 * per-viewer frequency caps (D21). Caching the response would hand one
 * viewer's serve to everyone behind it and make the caps meaningless — an
 * ads-integrity bug wearing a performance costume. It stays per-request, and
 * W0 pays for it with a Suspense boundary instead: the shell flushes without
 * waiting, and the creative streams into a box whose height is already
 * reserved, so the cost is zero CLS rather than blocked first byte.
 *
 * `cache()` still applies — it dedupes within ONE request, which is correct
 * even here; it never shares across requests.
 */
export const heroAdsFor = cache(async (pincode: string, locale: string) =>
  serveAds(HOME_HERO_SLOT, { pincode, locale }, 5),
);
