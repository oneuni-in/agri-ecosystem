import { Badge, Eyebrow, RatingStars, Wrap } from "@agri/ui";
import { buildMetadata, canonicalUrl } from "@agri/ui/seo";
import type { Metadata } from "next";
import { getLocale } from "next-intl/server";
import Link from "next/link";
import { notFound } from "next/navigation";

import { CardContact } from "@/app/_components/card-contact";
import {
  fetchProduct,
  fetchProductReviews,
  fetchSeller,
  groupSpecRows,
  pickLabel,
  specRows,
  type CatalogProduct,
  type ProductDetail,
  type RatingSummary,
} from "@/lib/catalog";
import { fetchEarnRules } from "@/lib/coins";

import { Gallery } from "./gallery";

/**
 * A-U6 W2 — `/products/{slug}`, the A2 reference's E2 catalog detail
 * (`docs/design-reference/agri/agri_pages_public_v1.html#/product`).
 *
 * Nothing rendered this backend read before: `GET /catalog/products/{slug}`
 * has been public since D17 and had no page. Products were reachable only as
 * thumbnails on a business profile, with no URL of their own to share, rank
 * or link to — which is why the category strip's cards had nowhere to go.
 *
 * THE SPEC TABLE IS THE POINT. The endpoint returns the product AND the spec
 * schema it was pinned to at create, so field order, labels and enum wording
 * all come off the wire. This file contains no vertical-specific knowledge —
 * no "HP", no "litres" — and a new vertical gets a correct table without a
 * line changing here. That is the reference's "rendered from admin
 * spec-schema — no hardcoded fields" claim, kept literally.
 *
 * WHAT THE REFERENCE SHOWS AND THIS DOES NOT. The EMI pill, "Compare with 3
 * rivals", "#2 in 40–45 HP segment", the four-thumb gallery on a
 * single-image product, and "Dealers near {pincode}" as a LIST: there is no
 * finance engine, no comparison surface, no segment ranking, and a catalog
 * product belongs to exactly one business — so "dealers" plural would be a
 * list that can only ever hold one row. Each is absent rather than faked.
 */

export const revalidate = 300;

const SITE = "https://agri.in";

interface RouteParams {
  params: Promise<{ slug: string }>;
}

/** Vertical → the gallery's fallback glyph. Chrome, not content: the catalog
 * has no icon column, and an unmapped vertical gets the neutral crop. */
const VERTICAL_GLYPH: Record<string, string> = {
  milk: "🥛",
  seeds: "🌾",
  tractors: "🚜",
  fertilizers: "🧪",
  equipment: "⚙️",
};

function canonicalFor(slug: string): string {
  return canonicalUrl(SITE, `/products/${slug}`);
}

function notFoundMeta(): Metadata {
  return { title: "Product not found", robots: { index: false, follow: true } };
}

export async function generateMetadata({ params }: RouteParams): Promise<Metadata> {
  const { slug } = await params;
  const detail = await fetchProduct(slug);
  if (!detail) return notFoundMeta();
  const { product } = detail;
  const seller = product.business_name ? ` from ${product.business_name}` : "";
  const price = product.price_display ? ` Listed at ${product.price_display}.` : "";
  return buildMetadata({
    title: `${product.name}${seller} | Agri Catalogue`,
    description: `${product.name}${seller} on agri.in.${price} Specifications, seller details and reviews — agri.in lists products and sellers and never sells or adds commission.`,
    canonical: canonicalFor(product.slug),
    siteName: "Agri.in",
  });
}

/**
 * schema.org Product. `offers` is only emitted when there is a real price
 * string, and it is deliberately NOT parsed into a number: `price_display`
 * is the seller's own free text ("₹32/500ml"), and inventing a numeric
 * `price`/`priceCurrency` from it would put a figure in a rich result that
 * the page never showed. `<` is escaped so no field can close the tag.
 */
function productJsonLd(
  product: CatalogProduct,
  canonical: string,
  summary: RatingSummary,
): string {
  return JSON.stringify({
    "@context": "https://schema.org",
    "@type": "Product",
    name: product.name,
    url: canonical,
    ...(product.images?.length ? { image: product.images } : {}),
    ...(product.business_name
      ? { brand: { "@type": "Organization", name: product.business_name } }
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
  }).replaceAll("<", "\\u003c");
}

/** `4.71` → `4.7`; the reference shows one decimal. */
function oneDecimal(value: number | string): string {
  const n = typeof value === "number" ? value : Number(value);
  return Number.isFinite(n) ? n.toFixed(1) : String(value);
}

/** "Jul 2026" from an ISO stamp; null rather than a guess if it will not parse. */
function monthYear(iso: string | null | undefined): string | null {
  if (!iso) return null;
  const d = new Date(iso);
  return Number.isNaN(d.getTime())
    ? null
    : d.toLocaleDateString("en-IN", { month: "short", year: "numeric" });
}

export default async function ProductPage({ params }: RouteParams) {
  const [{ slug }, locale] = await Promise.all([params, getLocale()]);
  const detail: ProductDetail | null = await fetchProduct(slug);
  if (!detail) notFound();
  const { product, schema_fields } = detail;

  const [{ summary, items: reviews }, seller, earnRules] = await Promise.all([
    fetchProductReviews(product.id),
    product.business_slug ? fetchSeller(product.business_slug) : Promise.resolve(null),
    fetchEarnRules(),
  ]);

  const canonical = canonicalFor(product.slug);
  const rows = specRows(product.specs, schema_fields, locale);
  const groups = groupSpecRows(rows);
  const images = product.images ?? [];
  const glyph = VERTICAL_GLYPH[product.vertical_slug] ?? "🌾";
  const listed = monthYear(product.created_at);
  // The amount comes from `coins.rules`, never from the mockup: the A2
  // reference prints "5 coins", but 5 is the WEEKLY CAP and the rule pays 20.
  // No rule read => no number, rather than a wrong one.
  const reviewCoins = earnRules["review_approved"]?.amount ?? null;
  const sellerBranch = seller?.branches[0]?.id ?? null;
  const sellerCategory = seller?.categories[0];

  return (
    <main className="bg-cream pb-10">
      <script
        type="application/ld+json"
        dangerouslySetInnerHTML={{ __html: productJsonLd(product, canonical, summary) }}
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
          {product.business_slug && product.business_name ? (
            <>
              <span aria-hidden="true" className="text-cream-line">
                ›
              </span>
              <Link
                href={`/directory/businesses/${product.business_slug}`}
                prefetch={false}
                className="tap-target text-brand no-underline"
              >
                {product.business_name}
              </Link>
            </>
          ) : null}
          <span aria-hidden="true" className="text-cream-line">
            ›
          </span>
          <span>{product.name}</span>
        </nav>

        {/* ── two columns (reference `.prod-grid2`) ───────────────────── */}
        <div className="mt-3 grid gap-4 lg:grid-cols-[1.1fr_1.5fr]">
          <div className="min-w-0">
            <Gallery images={images} alt={product.name} glyph={glyph} />
            <p className="mt-3.5 rounded-btn bg-cream-deep px-3.5 py-2.5 text-[10.5px] leading-relaxed text-muted">
              agri.in lists products and sellers — we never sell. The price is the seller&apos;s own
              listing, not an agri.in price; confirm it with the seller before you buy.
            </p>
          </div>

          <div className="min-w-0">
            {/* ── title block (reference `.pd-title`) ─────────────────── */}
            <Eyebrow>
              Catalogue · {product.vertical_slug} · spec schema v{product.schema_version}
            </Eyebrow>
            <h1 className="font-display text-[clamp(19px,2.4vw,26px)] font-semibold leading-[1.2] text-ink">
              {product.name}
            </h1>
            <p className="mt-1 text-xs text-sub">
              {product.business_name ? <>Sold by {product.business_name}</> : null}
              {listed ? <> · listed {listed}</> : null}
            </p>
            {summary.rating_avg !== null && summary.rating_count > 0 ? (
              <p className="mt-1.5 flex flex-wrap items-center gap-1.5 text-xs">
                <RatingStars value={oneDecimal(summary.rating_avg)} />
                <span className="text-muted">
                  ({summary.rating_count} {summary.rating_count === 1 ? "review" : "reviews"})
                </span>
              </p>
            ) : null}

            {/* ── price box (reference `.price-box`) ───────────────────
                One price and one CTA. The reference's EMI pill and "Compare
                with 3 rivals" have no finance engine and no comparison
                surface behind them. */}
            <div className="mt-3 flex flex-wrap items-center gap-4 rounded-card border border-cream-line bg-card px-4 py-3">
              {product.price_display ? (
                <div>
                  <p className="font-display text-2xl font-semibold text-ink">
                    {product.price_display}
                  </p>
                  <p className="text-[10.5px] text-muted">seller&apos;s listed price</p>
                </div>
              ) : (
                <div>
                  <p className="font-display text-lg font-semibold text-ink">Price on request</p>
                  <p className="text-[10.5px] text-muted">this seller has not listed a price</p>
                </div>
              )}
              <a
                href="#seller"
                className="tap-target ml-auto inline-flex min-h-[40px] items-center justify-center rounded-pill bg-accent px-[18px] text-[12.5px] font-semibold text-accent-ink no-underline"
              >
                Contact the seller ↓
              </a>
            </div>

            {/* ── spec table (reference `.spec-table`) ─────────────────
                Every row here came off the wire: the endpoint returns the
                spec schema this product was PINNED to at create, so labels,
                order, units and enum wording are all data. This component
                knows nothing about milk or tractors. */}
            {rows.length > 0 ? (
              <section className="mt-3 overflow-hidden rounded-card border border-cream-line bg-card">
                <div className="flex flex-wrap items-center justify-between gap-2 border-b border-cream-line px-4 py-2.5">
                  <h2 className="text-[12.5px] font-semibold text-ink">Specifications</h2>
                  <span className="text-[10px] text-muted">
                    rendered from the seller&apos;s spec schema — no hardcoded fields
                  </span>
                </div>
                {groups.map(({ group, rows: groupRows }) => (
                  <div key={group ?? "_"}>
                    {group && groups.length > 1 ? (
                      <p className="border-b border-cream-line bg-cream px-4 py-1.5 text-[10px] font-semibold uppercase tracking-wider text-muted">
                        {group}
                      </p>
                    ) : null}
                    <dl className="m-0">
                      {groupRows.map((row) => (
                        <div
                          key={row.key}
                          className="grid grid-cols-2 border-b border-cream-line text-xs last:border-b-0"
                        >
                          <dt className="px-4 py-2.5 text-muted">{row.label}</dt>
                          <dd className="border-l border-cream-line px-4 py-2.5 font-medium text-ink">
                            {row.value}
                          </dd>
                        </div>
                      ))}
                    </dl>
                  </div>
                ))}
              </section>
            ) : null}
          </div>
        </div>

        {/* ── seller (reference "Dealers near 641001") ────────────────────
            "Sold by", not "Dealers": a catalog product belongs to exactly one
            business (D17), so a dealer LIST could only ever hold one row.
            Call/WhatsApp run the same D18 reveal as everywhere else. */}
        {seller ? (
          <section id="seller" className="mt-5 scroll-mt-4">
            <div className="flex flex-wrap items-baseline justify-between gap-2.5">
              <h2 className="font-display text-lg font-semibold text-ink">Sold by</h2>
              <span className="text-[10.5px] text-muted">
                contact reveals are capped per day and logged
              </span>
            </div>
            <div className="mt-2.5 flex flex-wrap items-start gap-3 rounded-card border border-cream-line bg-card px-4 py-3">
              <span
                aria-hidden="true"
                className="flex h-[46px] w-[46px] flex-none items-center justify-center rounded-icon bg-brand-soft text-[22px]"
              >
                🏪
              </span>
              <div className="min-w-0 flex-1">
                <div className="flex flex-wrap items-center gap-2">
                  <p className="text-[13px] font-medium text-ink">{seller.business.name}</p>
                  {seller.business.verification_status === "verified" ? (
                    <Badge variant="verified">✓ Verified</Badge>
                  ) : null}
                </div>
                <p className="mt-0.5 text-[10.5px] text-muted">
                  {sellerCategory ? pickLabel(locale, sellerCategory.name) : null}
                  {seller.branches[0] ? (
                    <>
                      {sellerCategory ? " · " : null}
                      {seller.branches[0].district}, {seller.branches[0].state}{" "}
                      {seller.branches[0].pincode}
                    </>
                  ) : null}
                </p>
              </div>
              <div className="w-full max-w-[340px] max-md:max-w-none">
                <CardContact
                  branchId={sellerBranch}
                  profileHref={`/directory/businesses/${seller.business.slug}`}
                  returnTo={`/products/${product.slug}`}
                />
              </div>
            </div>
          </section>
        ) : null}

        {/* ── reviews (reference "Owner reviews") ─────────────────────── */}
        <section className="mt-5">
          <div className="flex flex-wrap items-baseline justify-between gap-2.5">
            <h2 className="font-display text-lg font-semibold text-ink">
              Reviews
              {summary.rating_count > 0 ? (
                <span className="ml-1.5 text-xs font-normal text-muted">
                  · {summary.rating_count}
                </span>
              ) : null}
            </h2>
            {reviewCoins !== null ? (
              <span className="rounded-pill bg-coins-bg px-3 py-1 text-[11px] font-medium text-coins-fg">
                🪙 Approved review = {reviewCoins} coins
              </span>
            ) : null}
          </div>
          <div className="mt-2.5 rounded-card border border-cream-line bg-card px-[17px] py-[15px]">
            {reviews.length === 0 ? (
              <p className="text-xs text-muted">
                No reviews of this product yet. Reviews come from signed-in buyers and appear here
                once moderation approves them.
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
                    {review.body ? (
                      <p className="mb-[3px] mt-1 text-xs text-ink">{review.body}</p>
                    ) : null}
                    <small className="text-[10.5px] text-muted">
                      {monthYear(review.created_at) ?? "Verified buyer"}
                    </small>
                  </li>
                ))}
              </ul>
            )}
          </div>
        </section>
      </Wrap>
    </main>
  );
}
