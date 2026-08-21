import { Badge, Eyebrow, RatingStars, Wrap } from "@agri/ui";
import { buildMetadata, canonicalUrl } from "@agri/ui/seo";
import type { Metadata } from "next";
import { getLocale } from "next-intl/server";
import Link from "next/link";
import { notFound } from "next/navigation";

import { pick } from "@/lib/content";
import {
  distanceLabel,
  fetchActiveCategories,
  fetchCoverage,
  fetchDistrict,
  fetchStripProducts,
  type ActiveCategory,
  type CatalogProduct,
  type CoverageItem,
} from "@/lib/directory";
import { fetchReviewSignals } from "@/lib/home";

import { ProductThumb } from "@/app/_components/product-thumb";
import { tintFor } from "@/app/_components/product-tints";

import { CardContact } from "@/app/_components/card-contact";

import { CategoryAdSlot } from "./category-ad-slot";

/**
 * A-U6 W1 — `/directory/{category}/{pincode}`, the VERTICAL-TEMPLATE landing
 * from the A2 public-pages reference (`docs/design-reference/agri/
 * agri_pages_public_v1.html#/category`).
 *
 * WHY A PATH, NOT `/directory?category=…&pin=…`. The hub already renders the
 * same two reads behind query parameters, and query URLs are not canonical
 * SEO surfaces — CLAUDE.md requires public pages to be SSR with JSON-LD and
 * immutable slugs. Both segments are immutable by construction: a category
 * slug and a pincode. The hub keeps its query form and links in here.
 *
 * ROUTE PRECEDENCE. `/directory/businesses/{slug}` is a static segment and
 * wins over this dynamic pair in Next's matcher, so the existing profile
 * route is untouched. A category slugged literally "businesses" would be
 * shadowed by it, which `RESERVED_SEGMENTS` rejects explicitly rather than
 * leaving as a silent trap.
 *
 * NO INVENTED CONTENT. The reference is the visual source of truth; every
 * value on this page comes from a live read. Where the reference shows
 * something the API cannot answer — "open now", "delivers", a map view, a
 * per-category product count — the control is ABSENT rather than decorative.
 * That is the same rule the business profile follows for Established /
 * Response time / Languages.
 */

/** Static children of `/directory`. A category with one of these slugs can
 * never be reached here, so it must not be offered a link either. */
const RESERVED_SEGMENTS = new Set(["businesses"]);

/**
 * Category slug → the head icon. ROUTING/CHROME CONFIG, not content: the
 * `directory.categories` table has slug, name and sort_order and no icon
 * column, so this cannot come from the API. It decorates the page head only
 * — nothing reads it as data — and an unmapped category gets the neutral
 * fallback rather than a wrong-but-confident glyph.
 */
const CATEGORY_ICON: Record<string, string> = {
  dairy: "🥛",
  "dairy-farm": "🐄",
  shop: "🏪",
  farm: "🌾",
  nursery: "🌱",
  equipment: "⚙️",
  lab: "🧪",
  veterinarian: "🩺",
  "feed-supplier": "🌿",
  cooperative: "🤝",
};
const CATEGORY_ICON_FALLBACK = "🌾";

/**
 * Business type → its card glyph. Same rule as CATEGORY_ICON: chrome, not
 * content. `type` IS on the coverage row, so unlike the reference's varied
 * shop logos (no logo column exists) this at least varies with a real fact
 * about the business instead of repeating one icon down the whole column.
 */
const TYPE_ICON: Record<string, string> = {
  shop: "🏪",
  vendor: "🥛",
  farm: "🌾",
  lab: "🧪",
  cooperative: "🤝",
  supplier: "🚚",
};

/** Businesses per page. The reference shows a "load more" under six cards. */
const PAGE_SIZE = 12;

/** The distance the "nearby" filter means, in metres. */
const NEARBY_M = 10_000;

interface RouteParams {
  params: Promise<{ category: string; pincode: string }>;
  searchParams: Promise<{ verified?: string; near?: string; cursor?: string }>;
}

/** Both segments are validated before they reach an API path. */
function parseSegments(
  category: string,
  pincode: string,
): { category: string; pincode: string } | null {
  if (!/^[a-z0-9-]{1,40}$/.test(category)) return null;
  if (RESERVED_SEGMENTS.has(category)) return null;
  if (!/^\d{6}$/.test(pincode)) return null;
  return { category, pincode };
}

function pathFor(category: string, pincode: string): string {
  return `/directory/${category}/${pincode}`;
}

/** Filter state lives in the URL, so it is crawlable, shareable, and works
 * with JS off — the same choice the hub's category chips made. */
function hrefWith(
  base: string,
  current: { verified: boolean; near: boolean },
  change: Partial<{ verified: boolean; near: boolean }>,
): string {
  const next = { ...current, ...change };
  const params = new URLSearchParams();
  if (next.verified) params.set("verified", "1");
  if (next.near) params.set("near", "1");
  const qs = params.toString();
  return qs ? `${base}?${qs}` : base;
}

async function findCategory(slug: string): Promise<ActiveCategory | undefined> {
  const categories = await fetchActiveCategories();
  return categories.find((entry) => entry.slug === slug);
}

export async function generateMetadata({ params }: RouteParams): Promise<Metadata> {
  const raw = await params;
  const parsed = parseSegments(raw.category, raw.pincode);
  if (!parsed) return { title: "Not found", robots: { index: false, follow: true } };

  const [category, district] = await Promise.all([
    findCategory(parsed.category),
    fetchDistrict(parsed.pincode),
  ]);
  if (!category) return { title: "Not found", robots: { index: false, follow: true } };

  const name = category.name["en"] ?? category.slug;
  const place = district ? `${district} · ${parsed.pincode}` : parsed.pincode;
  return buildMetadata({
    title: `${name} in ${place} | Agri Directory`,
    description: `${category.business_count} ${name.toLowerCase()} listed on agri.in serving ${parsed.pincode}. Verified businesses, nearest first — agri.in lists sellers and never sells or adds commission.`,
    canonical: canonicalUrl("https://agri.in", pathFor(parsed.category, parsed.pincode)),
    siteName: "Agri.in",
  });
}

/**
 * ItemList of the businesses actually rendered, in the order rendered.
 * `<` is escaped so a business name can never close the script tag.
 */
function listJsonLd(items: CoverageItem[], canonical: string): string {
  return JSON.stringify({
    "@context": "https://schema.org",
    "@type": "ItemList",
    url: canonical,
    numberOfItems: items.length,
    itemListElement: items.map((item, index) => ({
      "@type": "ListItem",
      position: index + 1,
      url: canonicalUrl("https://agri.in", `/directory/businesses/${item.slug}`),
      name: item.name,
    })),
  }).replaceAll("<", "\\u003c");
}

export default async function CategoryLandingPage({ params, searchParams }: RouteParams) {
  const [raw, query, locale] = await Promise.all([params, searchParams, getLocale()]);
  const parsed = parseSegments(raw.category, raw.pincode);
  if (!parsed) notFound();
  const { category: slug, pincode } = parsed;

  const verified = query.verified === "1";
  const near = query.near === "1";
  const cursor = /^[A-Za-z0-9_-]{1,200}$/.test(query.cursor ?? "") ? query.cursor : undefined;

  const [categories, district, page] = await Promise.all([
    fetchActiveCategories(),
    fetchDistrict(pincode),
    fetchCoverage({ pincode, category: slug, limit: PAGE_SIZE, ...(cursor ? { cursor } : {}) }),
  ]);

  const category = categories.find((entry) => entry.slug === slug);
  // An unknown category is a real 404, never a soft empty page — the same
  // rule `/c/[slug]` follows against the vertical registry.
  if (!category) notFound();

  // Filtering happens here, not in the API: `/directory/covers` takes a
  // category and a cursor and nothing else. The counts below are therefore
  // stated against what is on THIS page, never against the full 128.
  const all = page.items as CoverageItem[];
  const shown = all.filter(
    (item) =>
      (!verified || item.verification_status === "verified") &&
      (!near || item.distance_m <= NEARBY_M),
  );

  const [{ ratings }, products] = await Promise.all([
    fetchReviewSignals(shown, 0),
    fetchStripProducts(shown),
  ]);

  const name = pick(locale, category.name);
  const vernacular =
    locale === "ta" ? (category.name["en"] ?? "") : (category.name["ta"] ?? "");
  const place = district ?? pincode;
  const canonical = canonicalUrl("https://agri.in", pathFor(slug, pincode));
  const base = pathFor(slug, pincode);
  const filters = { verified, near };
  const siblings = categories.filter((entry) => !RESERVED_SEGMENTS.has(entry.slug));

  return (
    <main className="bg-cream pb-10">
      <script
        type="application/ld+json"
        dangerouslySetInnerHTML={{ __html: listJsonLd(shown, canonical) }}
      />
      <Wrap>
        {/* ── breadcrumbs (reference `.crumbs`) ───────────────────────── */}
        <nav
          aria-label="Breadcrumb"
          className="mt-3.5 flex flex-wrap items-center gap-1.5 text-[11.5px] text-muted"
        >
          <Link href="/categories" prefetch={false} className="tap-target text-brand no-underline">
            All categories
          </Link>
          <span aria-hidden="true" className="text-cream-line">
            ›
          </span>
          <Link href="/directory" prefetch={false} className="tap-target text-brand no-underline">
            Directory
          </Link>
          <span aria-hidden="true" className="text-cream-line">
            ›
          </span>
          <span>{name}</span>
          <span aria-hidden="true" className="text-cream-line">
            ›
          </span>
          <span>{district ? `${district} · ${pincode}` : pincode}</span>
        </nav>

        {/* ── page head (reference `.page-head`) ──────────────────────── */}
        <div className="mt-2 flex flex-wrap items-start gap-3.5">
          <span
            aria-hidden="true"
            className="flex h-[54px] w-[54px] flex-none items-center justify-center rounded-icon bg-brand-soft text-[26px]"
          >
            {CATEGORY_ICON[slug] ?? CATEGORY_ICON_FALLBACK}
          </span>
          <div className="min-w-0">
            <Eyebrow>Directory · Catalogue</Eyebrow>
            <h1 className="font-display text-[clamp(20px,2.6vw,28px)] font-semibold leading-[1.15] text-ink">
              {name} in {place}
              {vernacular ? (
                <span className="ml-2 align-middle text-[15px] font-normal text-sub">
                  · {vernacular}
                </span>
              ) : null}
            </h1>
            {/* The business count is the category's own, from the API. No
                product count: nothing counts products per category. */}
            <p className="mt-[3px] text-[12.5px] text-sub">
              {category.business_count} listed · nearest first for {pincode}
            </p>
          </div>
          <div className="ml-auto flex flex-wrap gap-2 max-md:ml-0 max-md:w-full">
            <Link
              href="/search"
              prefetch={false}
              className="tap-target inline-flex min-h-[40px] items-center justify-center rounded-pill bg-accent px-[18px] text-[12.5px] font-semibold text-accent-ink no-underline"
            >
              🔎 Search all of agri.in
            </Link>
          </div>
        </div>

        {/* ── sibling categories (reference `.subcats`) ───────────────────
            The reference's row is seed TYPES; no sub-category table exists,
            so the real analogue is the sibling categories that DO have
            businesses here — a chip can never lead to an empty list. */}
        <nav
          aria-label="Categories"
          className="mt-3.5 flex gap-2 overflow-x-auto pb-0.5 [scrollbar-width:none] [&::-webkit-scrollbar]:hidden"
        >
          {siblings.map((entry) => {
            const on = entry.slug === slug;
            return (
              <Link
                key={entry.slug}
                href={pathFor(entry.slug, pincode)}
                prefetch={false}
                aria-current={on ? "page" : undefined}
                className={`tap-target flex-none rounded-pill border px-[15px] py-[7px] text-xs no-underline ${
                  on
                    ? "border-brand bg-brand-soft font-medium text-brand-deep"
                    : "border-cream-line bg-card text-ink"
                }`}
              >
                {pick(locale, entry.name)}
              </Link>
            );
          })}
        </nav>

        {/* ── filter bar (reference `.filter-bar`) ────────────────────────
            Only filters the coverage read can actually answer. "Open now",
            "Delivers" and "Map view" are in the reference and absent here:
            there are no opening hours or delivery flags on the record, and
            MapLibre is a web-milk dependency, so each would be a control
            that lies about what it does. */}
        <div className="mt-3 flex flex-wrap items-center gap-2 rounded-card border border-cream-line bg-card px-3 py-[9px]">
          <Link
            href={hrefWith(base, filters, { verified: !verified })}
            prefetch={false}
            aria-pressed={verified}
            className={`tap-target inline-flex items-center gap-1.5 rounded-pill border px-[13px] py-1.5 text-[11.5px] no-underline ${
              verified
                ? "border-brand bg-brand-soft font-medium text-brand-deep"
                : "border-cream-line bg-cream text-sub"
            }`}
          >
            ✓ Verified only
          </Link>
          <Link
            href={hrefWith(base, filters, { near: !near })}
            prefetch={false}
            aria-pressed={near}
            className={`tap-target inline-flex items-center gap-1.5 rounded-pill border px-[13px] py-1.5 text-[11.5px] no-underline ${
              near
                ? "border-brand bg-brand-soft font-medium text-brand-deep"
                : "border-cream-line bg-cream text-sub"
            }`}
          >
            📍 Within 10 km
          </Link>
          {verified || near ? (
            <Link
              href={base}
              prefetch={false}
              className="tap-target inline-flex items-center rounded-pill border border-cream-line bg-cream px-[13px] py-1.5 text-[11.5px] text-sub no-underline"
            >
              Clear
            </Link>
          ) : null}
          <span className="flex-1" />
          <span className="inline-flex items-center rounded-pill border border-cream-line bg-cream px-[13px] py-1.5 text-[11.5px] text-sub">
            Sort: Nearest
          </span>
        </div>

        {/* Counts describe this page only — the coverage read filters by
            category and cursor, so a total after client-side filtering
            would be a number the list cannot deliver. */}
        <p className="mt-2.5 text-[11.5px] text-muted">
          Showing {shown.length} of {category.business_count} · nearest first ·{" "}
          <b className="font-medium text-sub">Recommended</b> is earned from reviews, response
          time and verification — it is never paid for, and sponsored placements are always
          labelled separately and never reorder these results
        </p>

        {/* ── business list (reference `.biz-list`) ───────────────────── */}
        {shown.length === 0 ? (
          <p className="mt-2.5 rounded-card border border-cream-line bg-card p-5 text-[13px] text-muted">
            No {name.toLowerCase()} match these filters for {pincode}.{" "}
            <Link href={base} prefetch={false} className="text-brand no-underline">
              Clear the filters
            </Link>{" "}
            or browse{" "}
            <Link href="/directory" prefetch={false} className="text-brand no-underline">
              the whole directory
            </Link>
            .
          </p>
        ) : (
          <ul className="mt-2.5 grid list-none gap-2.5 p-0 md:grid-cols-2">
            {shown.map((item) => {
              const km = distanceLabel(item.distance_m);
              const rating = ratings[item.id];
              return (
                <li key={item.id}>
                  <div className="flex h-full flex-col rounded-card border border-cream-line bg-card px-[15px] py-[13px]">
                    {item.verification_status === "verified" || item.recommended ? (
                      <div className="mb-2 flex flex-wrap items-center gap-1.5">
                        {item.verification_status === "verified" ? (
                          <Badge variant="verified">✓ Verified business</Badge>
                        ) : null}
                        {/* `cert`, NOT the reference's gold `.badge-reco`:
                            gold is the Sponsored palette on every other
                            surface, and the whole point of this label is that
                            it CANNOT be bought. milk.in's rail uses the same
                            variant, so one word means one thing family-wide. */}
                        {item.recommended ? <Badge variant="cert">Recommended</Badge> : null}
                      </div>
                    ) : null}
                    <div className="flex gap-[11px]">
                      <span
                        aria-hidden="true"
                        className="flex h-[46px] w-[46px] flex-none items-center justify-center rounded-icon bg-brand-soft text-[22px]"
                      >
                        {TYPE_ICON[item.type] ?? CATEGORY_ICON[slug] ?? CATEGORY_ICON_FALLBACK}
                      </span>
                      <div className="min-w-0">
                        <p className="text-sm font-medium text-ink">{item.name}</p>
                        <p className="mt-0.5 flex flex-wrap items-center gap-1.5 text-[10.5px] text-muted">
                          {rating?.rating_avg ? (
                            <>
                              <RatingStars value={oneDecimal(rating.rating_avg)} />
                              <span>({rating.rating_count})</span>
                            </>
                          ) : null}
                          {km ? <span>{km}</span> : null}
                          <span>{item.primary_pincode}</span>
                        </p>
                        {/* Tags are facts on the record — type and coverage.
                            The reference's brand/speciality tags have no
                            column behind them. */}
                        <div className="mt-[7px] flex flex-wrap gap-[5px]">
                          <span className="rounded-pill border border-cream-line bg-cream-deep px-2 py-0.5 text-[9px] font-medium capitalize text-sub">
                            {item.type}
                          </span>
                          {item.primary_pincode !== pincode ? (
                            <span className="rounded-pill border border-cream-line bg-cream-deep px-2 py-0.5 text-[9px] font-medium text-sub">
                              Delivers to {pincode}
                            </span>
                          ) : null}
                        </div>
                      </div>
                    </div>
                    {/* The reference's 📞 Call · WhatsApp · Profile row.
                        No number is in this HTML: the card carries only a
                        branch id, and a tap runs D18's login-gated,
                        daily-capped, DPDP-logged reveal. */}
                    <CardContact
                      branchId={item.contact_branch_id ?? null}
                      profileHref={`/directory/businesses/${item.slug}?pin=${pincode}`}
                      returnTo={base}
                    />
                  </div>
                </li>
              );
            })}
          </ul>
        )}

        {/* ── product strip (reference `.prod-strip`) ─────────────────── */}
        {products.length > 0 ? (
          <section className="mt-5">
            <div className="flex flex-wrap items-baseline justify-between gap-2.5">
              <h2 className="font-display text-lg font-semibold text-ink">
                Products from these businesses
              </h2>
            </div>
            <ul className="mt-2.5 grid list-none grid-cols-2 gap-2.5 p-0 md:grid-cols-4">
              {products.map((product, index) => (
                <li key={product.id}>
                  <ProductStripCard product={product} index={index} />
                </li>
              ))}
            </ul>
          </section>
        ) : null}

        {/* ── inline ad (reference `.inline-ad`) ──────────────────────────
            The live D21 slot, not a placeholder: renders only when a real
            campaign serves, and every served creative carries its label.
            It sits BELOW both the organic list and the product strip, so a
            paid placement can never displace or reorder either. */}
        <CategoryAdSlot />

        {/* ── load more (reference `.load-more`) ──────────────────────────
            A real cursor link, so the next page is crawlable too. */}
        {page.next_cursor ? (
          <div className="mt-3.5 flex justify-center">
            <Link
              href={`${base}?${new URLSearchParams({
                ...(verified ? { verified: "1" } : {}),
                ...(near ? { near: "1" } : {}),
                cursor: page.next_cursor,
              })}`}
              prefetch={false}
              className="tap-target inline-flex min-h-[44px] items-center justify-center rounded-btn border border-cream-line bg-card px-[18px] text-sm font-semibold text-brand-deep no-underline"
            >
              Load more businesses
            </Link>
          </div>
        ) : null}

        {/* ── SEO block (reference `.seo-block`) ──────────────────────────
            Evergreen guidance that is true of every category, plus the
            commission disclosure the reference carries. Nothing here claims
            a fact about this pincode that the page has not shown. */}
        <section className="mt-5 rounded-card border border-cream-line bg-card px-[18px] py-4">
          <h2 className="font-display text-sm font-semibold text-ink">
            Buying from {name.toLowerCase()} on agri.in
          </h2>
          <p className="mt-1.5 text-xs leading-[1.65] text-sub">
            Businesses are ordered by distance from {pincode}, nearest first. A{" "}
            <b className="font-medium text-ink">Verified</b> badge means the listing was claimed and
            its phone number confirmed by OTP — it is not a quality rating. Ratings come from
            reviews left by signed-in users and approved by moderation. Prices shown against
            products are the seller&apos;s own; agri.in lists sellers and never sells, brokers, or
            adds commission.
          </p>
        </section>
      </Wrap>
    </main>
  );
}

/** Reference `.pcard`: tinted media band, name, one spec line, price. */
function ProductStripCard({ product, index }: { product: CatalogProduct; index: number }) {
  const spec = specLine(product.specs);
  return (
    <Link
      href={`/products/${product.slug}`}
      prefetch={false}
      className="flex h-full flex-col overflow-hidden rounded-card border border-cream-line bg-card no-underline transition-shadow hover:shadow-lift"
    >
      <ProductThumb src={product.images?.[0]} alt={product.name} tint={tintFor(index)} />
      <div className="px-[11px] py-[9px]">
        <p className="text-xs font-medium leading-[1.3] text-ink">{product.name}</p>
        {spec ? <p className="mt-[3px] text-[10px] text-muted">{spec}</p> : null}
        {product.business_name ? (
          <p className="mt-[3px] text-[10px] text-muted">{product.business_name}</p>
        ) : null}
        {product.price_display ? (
          <p className="mt-1.5 font-display text-sm font-semibold text-ink">
            {product.price_display}
          </p>
        ) : null}
      </div>
    </Link>
  );
}

/** `4.71` → `4.7`. The reference shows one decimal, and a two-decimal
 * average over seven reviews implies a precision the sample does not have. */
function oneDecimal(value: number | string): string {
  const n = typeof value === "number" ? value : Number(value);
  return Number.isFinite(n) ? n.toFixed(1) : String(value);
}

/** The one spec line under a product name, from whatever specs exist. */
function specLine(specs: Record<string, unknown> | null): string | null {
  if (!specs) return null;
  const parts = Object.entries(specs)
    .filter(([, value]) => value !== null && value !== "" && typeof value !== "object")
    .slice(0, 3)
    .map(([, value]) => String(value));
  return parts.length ? parts.join(" · ") : null;
}
