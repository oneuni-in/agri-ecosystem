import {
  AdSlot,
  Badge,
  EmptyState,
  injectSponsored,
  SponsoredListingCard,
  VendorCard as VendorCardShell,
} from "@agri/ui";
import { LOC_COOKIE, parseLocCookie } from "@agri/ui";
import { buildMetadata, canonicalUrl } from "@agri/ui/seo";
import type { Metadata } from "next";
import { getTranslations, setRequestLocale } from "next-intl/server";
import { cookies } from "next/headers";

import { Link } from "@/i18n/navigation";
import { fetchSponsoredListings } from "@/lib/ads";

import { SearchForm } from "./search-form";

const API = process.env.API_BASE_URL ?? "http://127.0.0.1:8000";
const SITE = "https://milk.in";

// Per-user location cookie -> results order depends on the visitor, so this
// page is never statically generated / ISR'd (D19 Task 10 contract).
export const metadata: Metadata = buildMetadata({
  title: "Search — Milk.in",
  description: "Search dairy businesses and products near you.",
  canonical: canonicalUrl(SITE, "/search"),
  siteName: "Milk.in",
  noIndex: true,
});

/**
 * Wire shape of `GET /search` (D19) — mirrors `SearchHit` in
 * `backend/core/modules/search/router.py:28` field-for-field, including
 * nullability. Everything but `id`/`kind`/`name` is `| None` on the wire
 * (Pydantic `extra="ignore"`, `ConfigDict`), so every field here must stay
 * nullable to match — a `resp.json() as SearchResponse` cast is unchecked,
 * it does not enforce this shape at runtime, only at compile time.
 *
 * `description` is the one field that isn't a plain scalar: it's a
 * locale-keyed map (`{"en": "...", "ta": "..."}` or similar), not a
 * string — rendering it directly crashes React ("Objects are not valid
 * as a React child"). Extract a single locale via `pickDescription()`
 * below before it ever reaches JSX.
 */
interface SearchHit {
  id: string;
  kind: string;
  name: string;
  slug: string | null;
  business_name: string | null;
  business_slug: string | null;
  description: Record<string, string> | null;
  categories: string[] | null;
  vertical: string | null;
  district: string | null;
  state: string | null;
  verified: boolean | null;
  price_display: string | null;
  sites: string[] | null;
}

interface SearchResponse {
  items: SearchHit[];
  next_cursor: string | null;
}

function placeLabel(hit: SearchHit): string | null {
  if (hit.district && hit.state) return `${hit.district}, ${hit.state}`;
  return hit.district ?? hit.state ?? null;
}

/**
 * Locale-keyed description -> single displayable string, defensively.
 * `resp.json()` is trusted only up to a cast, never a runtime check, so a
 * missing/malformed shape (not an object, no "en" key, "en" not a string)
 * must render nothing rather than throw — same D16 precedent as
 * `apps/web-agri/app/directory/businesses/[slug]/page.tsx` (`.description.en`),
 * just guarded since this cast is less trusted than that route's.
 * Deliberately reads the "en" entry: locale routing (D27) governs UI-string
 * translation, not user-authored business/product content — that stays in the
 * language it was written in, so we surface the "en" value regardless of the
 * request locale (localised content is a future backend concern).
 */
function pickDescription(description: SearchHit["description"]): string | null {
  if (!description || typeof description !== "object") return null;
  const en = description.en;
  return typeof en === "string" && en.length > 0 ? en : null;
}

export default async function SearchPage({
  params,
  searchParams,
}: {
  params: Promise<{ locale: string }>;
  searchParams: Promise<{ q?: string; cursor?: string }>;
}) {
  const { locale } = await params;
  setRequestLocale(locale);
  const { q = "", cursor } = await searchParams;

  const jar = await cookies();
  const loc = parseLocCookie(jar.get(LOC_COOKIE)?.value);

  const query = new URLSearchParams({ site: "milk", q });
  if (loc?.pincode) {
    // `pincode` alone drives the geo-sort BOOST (nearest first) - it must
    // NOT also set `covered=true`. `covered` is a hard Meili filter, and
    // most businesses never call PUT /coverage (it's optional), so an
    // implicit filter here would make them invisible to every visitor with
    // a location set (D19 review finding 3). `covered` stays available on
    // the backend for a future explicit "only vendors who deliver here"
    // toggle - just not applied by default.
    query.set("pincode", loc.pincode);
  }
  if (cursor) query.set("cursor", cursor);

  // Public read: goes direct to the backend, not through an authed BFF proxy
  // (D16/D18 precedent — /api/* proxies 401 guests, this endpoint is public).
  let page: SearchResponse = { items: [], next_cursor: null };
  try {
    const resp = await fetch(`${API}/search?${query.toString()}`, { cache: "no-store" });
    if (resp.ok) {
      page = (await resp.json()) as SearchResponse;
    }
    // Non-ok (404 unknown site, 422 bad vertical, 400 bad cursor, 5xx) all
    // fall through to the empty-result default — never crash the page.
  } catch {
    // Backend unreachable — same graceful empty state.
  }

  // M3.B: render-layer injection only - page.items and next_cursor (the
  // load-more link below) are byte-identical with sponsorship on or off.
  const sponsoredAds =
    page.items.length > 0
      ? await fetchSponsoredListings({ pincode: loc?.pincode ?? null, locale })
      : [];

  const [t, tBadges] = await Promise.all([
    getTranslations("ui.search"),
    getTranslations("ui.badges"),
  ]);

  return (
    <main className="mx-auto flex w-full max-w-[720px] flex-col gap-4 px-4 py-6">
      <SearchForm
        initialQ={q}
        placeholder={t("placeholder")}
        inputLabel={t("inputLabel")}
        micLabel={t("micLabel")}
      />

      {/* M2: milk_search_inline - no fallback, collapses when the engine is
          dark (mid-page slot; the reserved box only shows while loading). */}
      <AdSlot slotKey="milk_search_inline" pincode={loc?.pincode ?? null} heightClass="h-[64px]" />

      {page.items.length === 0 ? (
        <EmptyState icon="🔍" title={t("results.empty")} />
      ) : (
        <ul className="flex list-none flex-col gap-3 p-0" data-testid="search-results">
          {injectSponsored(page.items, sponsoredAds).map((entry) => {
            if (entry.kind === "sponsored") {
              return (
                <li key={`s-${entry.ad.placement_id}`}>
                  <SponsoredListingCard
                    ad={entry.ad}
                    sponsoredLabel={tBadges("sponsored")}
                    className="rounded-card border-2 border-ad-border"
                  />
                </li>
              );
            }
            const hit = entry.item;
            const place = placeLabel(hit);
            const description = pickDescription(hit.description);
            // Where a hit can go: a business straight to its profile; a
            // product to the business that sells it (there is no product
            // page). A hit with no resolvable slug renders unlinked.
            const slug = hit.kind === "product" ? hit.business_slug : hit.slug;
            const card = (
              <VendorCardShell
                // The catalog shell, action-less: the whole card is the link,
                // so a separate action row would be a nested control (D29).
                className="h-full"
                name={hit.name}
                badges={
                  <>
                    <span className="rounded-pill bg-ghost px-[9px] py-[3px] text-[11px] font-extrabold text-sub">
                      {hit.kind === "product" ? t("results.kindProduct") : t("results.kindBusiness")}
                    </span>
                    {hit.verified ? (
                      <Badge variant="verified">{t("results.verified")}</Badge>
                    ) : null}
                  </>
                }
                meta={
                  <>
                    {hit.kind === "product" && hit.business_name ? (
                      <span>{hit.business_name}</span>
                    ) : null}
                    {place ? <span>{place}</span> : null}
                  </>
                }
                {...(description ? { body: <span className="line-clamp-2">{description}</span> } : {})}
                {...(hit.price_display
                  ? { prices: <b className="font-semibold">{hit.price_display}</b> }
                  : {})}
              />
            );
            return (
              <li key={`${hit.kind}-${hit.id}`}>
                {slug ? (
                  <Link href={`/directory/businesses/${slug}`} className="block no-underline">
                    {card}
                  </Link>
                ) : (
                  card
                )}
              </li>
            );
          })}
        </ul>
      )}

      {page.next_cursor ? (
        <Link
          href={`/search?q=${encodeURIComponent(q)}&cursor=${encodeURIComponent(page.next_cursor)}`}
          className="mx-auto rounded-btn border border-line bg-card px-4 py-2 text-sm font-bold text-ink no-underline"
        >
          {t("results.loadMore")}
        </Link>
      ) : null}
    </main>
  );
}
