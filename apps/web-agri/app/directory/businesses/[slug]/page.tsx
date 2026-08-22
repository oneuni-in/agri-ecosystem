import { Badge, RatingStars, Wrap } from "@agri/ui";
import { buildMetadata, canonicalUrl } from "@agri/ui/seo";
import type { Metadata } from "next";
import { getLocale } from "next-intl/server";
import Link from "next/link";
import { notFound } from "next/navigation";

import { ProductThumb } from "@/app/_components/product-thumb";
import { tintFor } from "@/app/_components/product-tints";
import { pick } from "@/lib/content";
import {
  distanceLabel,
  fetchBusinessProducts,
  fetchCoverage,
  type CatalogProduct,
  type CoverageItem,
} from "@/lib/directory";
import { fetchEarnRules } from "@/lib/coins";

import { LeadForm } from "./lead-form";
import { ReportButton } from "./report-button";
import { ShareButton } from "./share-button";
import { RevealContact } from "./reveal-contact";
import { ReviewForm } from "./review-form";
import { SponsoredSlot } from "./sponsored-slot";
import { ViewBeacon } from "./view-beacon";

const API = process.env.API_BASE_URL ?? "http://127.0.0.1:8000";
const SITE = "https://agri.in";

export const revalidate = 300;

/**
 * A-U6 W3 — the A2 reference's E1 directory profile, restyled onto the
 * `.bp-head` / `.bp-grid` anatomy (`docs/design-reference/agri/
 * agri_pages_public_v1.html#/business`).
 *
 * This page already existed and already worked. What changed is layout and
 * three additions, not the data contract:
 *
 *   · the header became the reference's card — 74px logo, trust chips, and a
 *     right-hand action column where Call leads (call > chat > form).
 *   · products now LINK to /products/{slug}. They were dead thumbnails
 *     because no product page existed until W2.
 *   · Report is a real control. The comment that used to sit here said no
 *     route existed behind it, which was true when it was written and stopped
 *     being true at M1.5.A.
 *   · "Similar nearby" is the same coverage read the category landing uses,
 *     anchored on this business's own pincode and category.
 *
 * Still ABSENT because nothing answers them, exactly as before: Established,
 * Response time, Languages, Payment, and the reference's "🕐 Open now · till
 * 8:00 PM". `directory.branches` does carry an `hours` JSONB column, but it
 * is free-form, no console field writes it, and every row is `{}` — so a
 * rendered opening time would be a shape this codebase has not agreed on.
 * The reference's MapLibre panel is a static location card for the same
 * reason it always was: MapLibre is a web-milk dependency, so an interactive
 * map here is a real feature, not a styling change.
 */

type LocalizedText = Record<string, string>;

/** Shapes of the D18 review reads. Declared here now that the page renders
 * the list itself — the old `ReviewsSection` component was a plain card list
 * that the reference's `.panel-c` layout replaces. */
type RatingSummary = { rating_avg: string | null; rating_count: number };
type ReviewItem = {
  id: string;
  rating: number;
  body: LocalizedText | null;
  created_at: string;
};

interface BusinessDetail {
  business: {
    id: string;
    name: string;
    slug: string;
    type: string;
    status: string;
    verification_status: string;
    claimable: boolean;
    primary_pincode: string;
    description: LocalizedText | null;
    /** Powers "on agri.in since" — the A3 reference's tenure line. */
    created_at?: string | null;
  };
  branches: {
    id: string;
    address: string;
    state: string;
    district: string;
    pincode: string;
    /** Already served by the API; used for the Directions link. */
    lat?: string | null;
    lng?: string | null;
  }[];
  categories: { id: string; slug: string; name: LocalizedText }[];
  /** Every pincode this business delivers to — the reference's coverage chips. */
  coverage_pincodes?: string[];
}

/** Business type → its header glyph. Chrome, not content: there is no logo
 * column, so this varies with a real fact rather than inventing a brand mark. */
const TYPE_ICON: Record<string, string> = {
  shop: "🏪",
  vendor: "🥛",
  farm: "🌾",
  lab: "🧪",
  cooperative: "🤝",
  supplier: "🚚",
};

/** "Mar 2026" from an ISO stamp; null rather than a guess if it will not parse. */
function monthYear(iso: string | null | undefined): string | null {
  if (!iso) return null;
  const d = new Date(iso);
  if (Number.isNaN(d.getTime())) return null;
  return d.toLocaleDateString("en-IN", { month: "short", year: "numeric" });
}

/** `4.71` → `4.7`; the reference shows one decimal. */
function oneDecimal(value: number | string): string {
  const n = typeof value === "number" ? value : Number(value);
  return Number.isFinite(n) ? n.toFixed(1) : String(value);
}

/** The one spec line under a product name, built from whatever specs exist. */
function specLine(specs: Record<string, unknown> | null): string | null {
  if (!specs) return null;
  const parts = Object.entries(specs)
    .filter(([, v]) => v !== null && v !== "" && typeof v !== "object")
    .slice(0, 3)
    .map(([, v]) => String(v));
  return parts.length ? parts.join(" · ") : null;
}

async function fetchDetail(slug: string): Promise<BusinessDetail | null> {
  const res = await fetch(`${API}/directory/businesses/${encodeURIComponent(slug)}`, {
    next: { revalidate: 300 },
  });
  if (res.status === 404) return null;
  if (!res.ok) throw new Error(`directory fetch failed: ${res.status}`);
  return (await res.json()) as BusinessDetail;
}

/**
 * Public review reads, fetched directly from the backend server-side — NOT
 * through `/api/reviews` (that proxy is auth-required by design, Task 10,
 * and would 401 for guests). Tolerant of non-OK responses: falls back to an
 * empty summary/list rather than failing the whole page render.
 */
async function fetchReviews(
  businessId: string,
): Promise<{ summary: RatingSummary; items: ReviewItem[] }> {
  const qs = `target_type=business&target_id=${businessId}`;
  const [summaryRes, listRes] = await Promise.all([
    fetch(`${API}/reviews/summary?${qs}`, { next: { revalidate: 300 } }),
    fetch(`${API}/reviews?${qs}&limit=10`, { next: { revalidate: 300 } }),
  ]);
  const summary: RatingSummary = summaryRes.ok
    ? ((await summaryRes.json()) as RatingSummary)
    : { rating_avg: null, rating_count: 0 };
  const items: ReviewItem[] = listRes.ok
    ? ((await listRes.json()) as { items: ReviewItem[] }).items
    : [];
  return { summary, items };
}

function canonicalFor(slug: string): string {
  return canonicalUrl(SITE, `/directory/businesses/${slug}`);
}

export async function generateMetadata({
  params,
}: {
  params: Promise<{ slug: string }>;
}): Promise<Metadata> {
  const { slug } = await params;
  const detail = await fetchDetail(slug);
  if (!detail) {
    // Hand-built: buildMetadata has no vocabulary for a bare "not found" title
    // plus robots.index:false without also implying noIndex's follow:true default
    // differs from the OG-less shape wanted here — kept minimal on purpose.
    return { title: "Business not found", robots: { index: false, follow: true } };
  }
  const { business } = detail;
  const title = `${business.name} | Agri Directory`;
  const description = business.description?.en;
  const canonical = canonicalFor(business.slug);
  return buildMetadata({
    title,
    ...(description ? { description } : {}),
    canonical,
  });
}

/**
 * Hand-built rather than the shared `localBusinessJsonLd` (@agri/ui/seo):
 * that builder requires `address`, but here a PostalAddress is only known
 * when the business has a branch — omitted entirely otherwise, per D16 spec.
 * `<` is escaped so branch/category content can never close the script tag.
 */
function businessJsonLd(
  detail: BusinessDetail,
  canonical: string,
  summary: RatingSummary,
): string {
  const { business, branches } = detail;
  const firstBranch = branches[0];
  const data = {
    "@context": "https://schema.org",
    "@type": "LocalBusiness",
    name: business.name,
    url: canonical,
    ...(business.description?.en ? { description: business.description.en } : {}),
    ...(firstBranch
      ? {
          address: {
            "@type": "PostalAddress",
            streetAddress: firstBranch.address,
            addressLocality: firstBranch.district,
            addressRegion: firstBranch.state,
            postalCode: firstBranch.pincode,
            addressCountry: "IN",
          },
        }
      : {}),
    ...(summary.rating_count > 0
      ? {
          aggregateRating: {
            "@type": "AggregateRating",
            ratingValue: summary.rating_avg,
            ratingCount: summary.rating_count,
          },
        }
      : {}),
  };
  return JSON.stringify(data).replaceAll("<", "\\u003c");
}

/** Reference `.panel-c`: the white card every block on this page sits in. */
function Panel({
  title,
  aside,
  children,
  className = "",
  id,
}: {
  title?: React.ReactNode;
  aside?: React.ReactNode;
  children: React.ReactNode;
  className?: string;
  id?: string;
}) {
  return (
    <section
      {...(id ? { id } : {})}
      className={`rounded-card border border-cream-line bg-card px-[17px] py-[15px] ${className}`}
    >
      {title ? (
        <div className="mb-2 flex flex-wrap items-baseline justify-between gap-2">
          <h2 className="font-display text-[13.5px] font-semibold text-ink">{title}</h2>
          {aside}
        </div>
      ) : null}
      {children}
    </section>
  );
}

export default async function BusinessPage({
  params,
  searchParams,
}: {
  params: Promise<{ slug: string }>;
  searchParams: Promise<{ pin?: string }>;
}) {
  const [{ slug }, query, locale] = await Promise.all([params, searchParams, getLocale()]);
  const detail = await fetchDetail(slug);
  if (!detail) notFound();
  const { business, branches, categories } = detail;
  const canonical = canonicalFor(business.slug);

  const primary = branches[0];
  const anchorPincode = /^\d{6}$/.test(query.pin ?? "")
    ? (query.pin as string)
    : business.primary_pincode;
  const firstCategory = categories[0];

  const [{ summary, items: reviews }, products, earnRules, nearbyPage] = await Promise.all([
    fetchReviews(business.id),
    fetchBusinessProducts(business.slug, 6),
    fetchEarnRules(),
    // "Similar nearby" — the SAME coverage read the category landing uses, so
    // "near here" cannot mean two things on two pages.
    fetchCoverage({
      pincode: anchorPincode,
      ...(firstCategory ? { category: firstCategory.slug } : {}),
      limit: 5,
    }),
  ]);

  const since = monthYear(business.created_at);
  const coverage = detail.coverage_pincodes ?? [];
  const categoryLine = categories.map((c) => pick(locale, c.name)).join(" · ");
  const glyph = TYPE_ICON[business.type] ?? "🏪";
  const reviewCoins = earnRules["review_approved"]?.amount ?? null;
  const nearby = (nearbyPage.items as CoverageItem[])
    .filter((item) => item.slug !== business.slug)
    .slice(0, 4);

  return (
    <main className="bg-cream pb-10">
      <ViewBeacon slug={slug} />
      <script
        type="application/ld+json"
        dangerouslySetInnerHTML={{ __html: businessJsonLd(detail, canonical, summary) }}
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
          {firstCategory ? (
            <>
              <Link
                href={`/directory/${firstCategory.slug}/${anchorPincode}`}
                prefetch={false}
                className="tap-target text-brand no-underline"
              >
                {pick(locale, firstCategory.name)}
              </Link>
              <span aria-hidden="true" className="text-cream-line">
                ›
              </span>
            </>
          ) : null}
          <span>{business.name}</span>
        </nav>

        {/* ── header card (reference `.bp-head`) ──────────────────────── */}
        <header className="mt-3 flex flex-wrap gap-4 rounded-card border border-cream-line bg-card px-5 py-[18px]">
          <span
            aria-hidden="true"
            className="flex h-[74px] w-[74px] flex-none items-center justify-center rounded-[18px] bg-brand-soft text-[34px]"
          >
            {glyph}
          </span>
          <div className="min-w-[220px] flex-1">
            <h1 className="flex flex-wrap items-center gap-2 font-display text-[clamp(19px,2.4vw,26px)] font-semibold leading-tight text-ink">
              {business.name}
              {business.verification_status === "verified" ? (
                <Badge variant="verified">✓ Verified</Badge>
              ) : null}
            </h1>
            <p className="mt-[3px] flex flex-wrap items-center gap-x-2 gap-y-1 text-xs text-sub">
              {summary.rating_avg !== null && summary.rating_count > 0 ? (
                <>
                  <RatingStars value={oneDecimal(summary.rating_avg)} />
                  <span>
                    ({summary.rating_count} {summary.rating_count === 1 ? "review" : "reviews"})
                  </span>
                </>
              ) : null}
              {categoryLine ? <span>{categoryLine}</span> : null}
              {primary ? (
                <span>
                  {primary.district}, {primary.state}
                </span>
              ) : null}
            </p>
            {since ? <p className="mt-[3px] text-xs text-sub">On agri.in since {since}</p> : null}
            {/* Chips are facts on the record. The reference's "Authorised
                dealer — 6 brands" / "GST billed" have no column behind them. */}
            <div className="mt-2 flex flex-wrap gap-1.5">
              <span className="rounded-pill border border-cream-line bg-cream-deep px-2.5 py-[3px] text-[10px] font-medium capitalize text-sub">
                {business.type}
              </span>
              {coverage.length > 0 ? (
                <span className="rounded-pill border border-cream-line bg-cream-deep px-2.5 py-[3px] text-[10px] font-medium text-sub">
                  Delivers to {coverage.length} pincode{coverage.length === 1 ? "" : "s"}
                </span>
              ) : null}
              {products.length > 0 ? (
                <span className="rounded-pill border border-cream-line bg-cream-deep px-2.5 py-[3px] text-[10px] font-medium text-sub">
                  {products.length} listed product{products.length === 1 ? "" : "s"}
                </span>
              ) : null}
            </div>
          </div>

          {/* Call leads, chat second, form last (design law). Numbers are
              never in this HTML — RevealContact runs D18's capped,
              fail-closed reveal. */}
          <div className="flex min-w-[200px] flex-col gap-[7px] max-md:w-full md:ml-auto">
            {primary ? <RevealContact branchId={primary.id} slug={business.slug} /> : null}
            <div className="flex gap-[7px]">
              <ShareButton title={business.name} />
              <ReportButton slug={business.slug} />
            </div>
          </div>
        </header>

        {/* ── two columns (reference `.bp-grid`) ──────────────────────── */}
        <div className="mt-3 grid gap-3 lg:grid-cols-[1.6fr_1fr]">
          <div className="min-w-0 space-y-3">
            {business.description?.en || business.description?.ta ? (
              <Panel title={<>About · எங்களை பற்றி</>}>
                {business.description?.en ? (
                  <p className="text-xs leading-[1.65] text-sub">{business.description.en}</p>
                ) : null}
                {business.description?.ta ? (
                  <p className="mt-2 text-xs leading-[1.65] text-sub">{business.description.ta}</p>
                ) : null}
              </Panel>
            ) : null}

            {products.length > 0 ? (
              <Panel title="Products & services">
                <ul className="grid list-none grid-cols-2 gap-2.5 p-0 md:grid-cols-3">
                  {products.map((product, index) => (
                    <li key={product.id}>
                      <ProductCard product={product} index={index} glyph={glyph} />
                    </li>
                  ))}
                </ul>
              </Panel>
            ) : null}

            <Panel
              title={
                <>
                  Reviews
                  {summary.rating_count > 0 ? ` · ${summary.rating_count}` : null}
                </>
              }
              aside={
                <span className="flex flex-wrap items-center gap-2">
                  <span className="text-[10.5px] font-normal text-muted">
                    approved by moderation, owner replies shown
                  </span>
                  {/* The amount is from coins.rules, not the mockup: the
                      reference prints "earn 5", but 5 is the WEEKLY CAP and
                      the rule pays 20. No rules read => no number. */}
                  {reviewCoins !== null ? (
                    <span className="rounded-pill bg-coins-bg px-3 py-1 text-[11px] font-medium text-coins-fg">
                      🪙 Approved review = {reviewCoins} coins
                    </span>
                  ) : null}
                </span>
              }
            >
              {reviews.length === 0 ? (
                <p className="text-xs text-muted">
                  No reviews yet. Reviews come from signed-in customers and appear once moderation
                  approves them.
                </p>
              ) : (
                <ul className="m-0 list-none p-0">
                  {reviews.map((review) => (
                    <li
                      key={review.id}
                      className="border-t border-cream-line py-2.5 first:border-t-0 first:pt-0"
                    >
                      <span className="text-[11px] tracking-[2px] text-rating" aria-hidden="true">
                        {"★".repeat(Math.max(0, Math.min(5, Math.round(review.rating))))}
                        {"☆".repeat(5 - Math.max(0, Math.min(5, Math.round(review.rating))))}
                      </span>
                      <span className="sr-only">{review.rating} out of 5</span>
                      {review.body?.en ? (
                        <p className="mb-[3px] mt-1 text-xs text-ink">{review.body.en}</p>
                      ) : null}
                      <p className="mt-0.5 text-[10.5px] text-muted">
                        {monthYear(review.created_at) ?? ""}
                      </p>
                    </li>
                  ))}
                </ul>
              )}
              <div className="mt-2.5">
                <ReviewForm businessId={business.id} slug={business.slug} />
              </div>
            </Panel>

            {/* No Panel title: LeadForm carries its own heading. */}
            <Panel id="enquiry">
              <LeadForm
                businessId={business.id}
                defaultPincode={business.primary_pincode}
                milkVertical={business.type === "vendor"}
              />
            </Panel>
          </div>

          {/* ── sidebar. Source order puts it BELOW the content on a phone,
                which is where reference material belongs. ─────────────── */}
          <aside className="min-w-0 space-y-3">
            <Panel title="At a glance">
              {/* Only facts the API actually returns. The reference also shows
                  Established, Response time, Languages and Payment — none of
                  which exists on the business record, and a plausible-looking
                  guess on a trust page is worse than a shorter list. */}
              <dl className="m-0">
                {categoryLine ? <Kv label="Category" value={categoryLine} /> : null}
                <Kv label="Type" value={business.type} capitalize />
                {since ? <Kv label="On agri.in since" value={since} /> : null}
                <Kv label="Verification" value={business.verification_status} capitalize />
                {coverage.length > 0 ? (
                  <Kv
                    label="Delivers to"
                    value={`${coverage.length} pincode${coverage.length === 1 ? "" : "s"}`}
                  />
                ) : null}
              </dl>
            </Panel>

            {coverage.length > 0 ? (
              <Panel
                title={`Delivery coverage · ${coverage.length} pincode${coverage.length === 1 ? "" : "s"}`}
              >
                {/* These became LINKS (they were inert text), so they have to
                    clear the 44px tap floor: 34px of real height plus the
                    `tap-target` overlay, and gap-2 so neighbouring overlays
                    do not swallow each other. */}
                <ul className="m-0 flex list-none flex-wrap gap-2 p-0">
                  {coverage.map((pincode) => (
                    <li key={pincode}>
                      <Link
                        href={
                          firstCategory
                            ? `/directory/${firstCategory.slug}/${pincode}`
                            : `/directory?pin=${pincode}`
                        }
                        prefetch={false}
                        className="tap-target inline-flex min-h-[34px] items-center rounded-pill bg-brand-soft px-3 text-[11px] font-medium text-brand-deep no-underline"
                      >
                        {pincode}
                      </Link>
                    </li>
                  ))}
                </ul>
              </Panel>
            ) : null}

            {primary ? (
              <Panel title="Location">
                {/* The reference's MapLibre panel. MapLibre is a web-milk-only
                    dependency, so an interactive map here is a real feature
                    (bundle + tiles), not a styling change — this is the same
                    surveyed ground the reference draws, with the address and
                    a Directions link doing the actual work. */}
                <div
                  aria-hidden="true"
                  className="relative flex h-[150px] items-center justify-center overflow-hidden rounded-btn bg-brand-soft"
                >
                  {/* The reference draws this grid in the brand green at 12%
                      alpha. Expressed as a color-mix off the token so it
                      follows a theme change - and so check:hex, which bans
                      raw colour literals in app code, stays satisfied. */}
                  <div
                    className="absolute inset-0"
                    style={{
                      backgroundImage: [
                        "repeating-linear-gradient(0deg,transparent 0 34px,var(--map-grid) 34px 35px)",
                        "repeating-linear-gradient(90deg,transparent 0 34px,var(--map-grid) 34px 35px)",
                      ].join(","),
                      ["--map-grid" as string]: "color-mix(in srgb, var(--brand) 12%, transparent)",
                    }}
                  />
                  <span className="relative text-[26px]">📍</span>
                </div>
                <p className="mt-2 text-[11.5px] leading-[1.55] text-sub">
                  {primary.address}
                  <br />
                  {primary.district}, {primary.state} {primary.pincode}
                </p>
                {primary.lat && primary.lng ? (
                  <a
                    href={`https://www.openstreetmap.org/?mlat=${primary.lat}&mlon=${primary.lng}#map=16/${primary.lat}/${primary.lng}`}
                    target="_blank"
                    rel="noopener noreferrer"
                    className="tap-target mt-1.5 inline-flex min-h-[44px] items-center text-[11.5px] font-semibold text-brand no-underline"
                  >
                    Directions →
                  </a>
                ) : null}
              </Panel>
            ) : null}

            {branches.length > 1 ? (
              <Panel title="Other branches">
                <ul className="m-0 list-none space-y-2.5 p-0">
                  {branches.slice(1).map((branch) => (
                    <li key={branch.id} className="border-t border-cream-line pt-2.5 first:border-t-0 first:pt-0">
                      <p className="text-xs font-medium text-ink">{branch.address}</p>
                      <p className="mt-0.5 text-[11px] text-muted">
                        {branch.district}, {branch.state} {branch.pincode}
                      </p>
                      <div className="mt-1.5">
                        <RevealContact branchId={branch.id} slug={business.slug} />
                      </div>
                    </li>
                  ))}
                </ul>
              </Panel>
            ) : null}
          </aside>
        </div>

        {/* ── claim strip (reference `.claim-bar`) ────────────────────── */}
        {business.claimable ? (
          <div className="mt-3 flex flex-wrap items-center gap-2.5 rounded-btn border border-accent bg-trust-bg px-[15px] py-[11px] text-xs">
            <span aria-hidden="true" className="text-lg">
              {glyph}
            </span>
            <span className="text-ink">
              <b className="font-medium">Is this your business?</b> Claim it free — verify with OTP,
              then manage your listing, products and leads.
            </span>
            <Link
              href={`/directory/businesses/${business.slug}/claim`}
              prefetch={false}
              className="tap-target ml-auto inline-flex min-h-[36px] items-center justify-center rounded-pill bg-accent px-3.5 text-[11.5px] font-semibold text-accent-ink no-underline max-md:ml-0"
            >
              Claim this business
            </Link>
          </div>
        ) : null}

        <div className="mt-3">
          <SponsoredSlot />
        </div>

        {/* ── similar nearby (reference "Similar nearby") ─────────────── */}
        {nearby.length > 0 ? (
          <section className="mt-5">
            <div className="flex flex-wrap items-baseline justify-between gap-2.5">
              <h2 className="font-display text-lg font-semibold text-ink">Similar nearby</h2>
              {firstCategory ? (
                <Link
                  href={`/directory/${firstCategory.slug}/${anchorPincode}`}
                  prefetch={false}
                  className="tap-target text-xs text-brand no-underline"
                >
                  All {pick(locale, firstCategory.name).toLowerCase()} →
                </Link>
              ) : null}
            </div>
            <ul className="mt-2.5 grid list-none gap-2.5 p-0 md:grid-cols-2">
              {nearby.map((item) => {
                const km = distanceLabel(item.distance_m);
                return (
                  <li key={item.id}>
                    <Link
                      href={`/directory/businesses/${item.slug}?pin=${anchorPincode}`}
                      prefetch={false}
                      className="flex gap-[11px] rounded-card border border-cream-line bg-card px-[15px] py-[13px] no-underline transition-shadow hover:shadow-lift"
                    >
                      <span
                        aria-hidden="true"
                        className="flex h-[46px] w-[46px] flex-none items-center justify-center rounded-icon bg-brand-soft text-[22px]"
                      >
                        {TYPE_ICON[item.type] ?? "🏪"}
                      </span>
                      <div className="min-w-0">
                        <p className="text-sm font-medium text-ink">{item.name}</p>
                        <p className="mt-0.5 text-[10.5px] text-muted">
                          {km ? `${km} · ` : null}
                          {item.primary_pincode}
                        </p>
                      </div>
                    </Link>
                  </li>
                );
              })}
            </ul>
          </section>
        ) : null}
      </Wrap>
    </main>
  );
}

/** Reference `.kv`: label left, value right, hairline between. */
function Kv({
  label,
  value,
  capitalize = false,
}: {
  label: string;
  value: string;
  capitalize?: boolean;
}) {
  return (
    <div className="flex justify-between gap-3 border-b border-cream-line py-[7px] text-xs last:border-b-0">
      <dt className="text-muted">{label}</dt>
      <dd className={`text-right font-medium text-ink ${capitalize ? "capitalize" : ""}`}>
        {value}
      </dd>
    </div>
  );
}

/** Reference `.pcard`, now a real link: /products/{slug} shipped at W2, so
 * these stopped being dead thumbnails. */
function ProductCard({
  product,
  index,
  glyph,
}: {
  product: CatalogProduct;
  index: number;
  glyph: string;
}) {
  const spec = specLine(product.specs);
  return (
    <Link
      href={`/products/${product.slug}`}
      prefetch={false}
      className="flex h-full flex-col overflow-hidden rounded-card border border-cream-line bg-card no-underline transition-shadow hover:shadow-lift"
    >
      <ProductThumb
        src={product.images?.[0]}
        alt={product.name}
        tint={tintFor(index)}
        glyph={glyph}
      />
      <div className="px-[11px] py-[9px]">
        <p className="text-xs font-medium leading-[1.3] text-ink">{product.name}</p>
        {spec ? <p className="mt-[3px] text-[10px] text-muted">{spec}</p> : null}
        {product.price_display ? (
          <p className="mt-1.5 font-display text-sm font-semibold text-ink">
            {product.price_display}
          </p>
        ) : null}
      </div>
    </Link>
  );
}
