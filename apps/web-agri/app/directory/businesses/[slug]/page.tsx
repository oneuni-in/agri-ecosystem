import { Badge, buttonVariants, Card, cn, Wrap } from "@agri/ui";
import { buildMetadata, canonicalUrl } from "@agri/ui/seo";
import type { Metadata } from "next";
import Link from "next/link";
import { notFound } from "next/navigation";

import { LeadForm } from "./lead-form";
import { ProductImage } from "./product-image";
import { ShareButton } from "./share-button";
import { RevealContact } from "./reveal-contact";
import { ReviewForm } from "./review-form";
import { ReviewsSection, type RatingSummary, type ReviewItem } from "./reviews-section";
import { SponsoredSlot } from "./sponsored-slot";
import { ViewBeacon } from "./view-beacon";

const API = process.env.API_BASE_URL ?? "http://127.0.0.1:8000";
const SITE = "https://agri.in";

export const revalidate = 300;

type LocalizedText = Record<string, string>;

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

/** One row of `GET /catalog/businesses/{slug}/products` (public, approved-only). */
interface ProductItem {
  id: string;
  name: string;
  slug: string;
  price_display: string | null;
  specs: Record<string, unknown> | null;
  images: string[] | null;
}

/**
 * Products & services — the reference's third block on this page.
 *
 * Tolerant like the review read below it: a business with no catalogue, or a
 * catalogue service having a bad minute, must not take the profile down with
 * it. The section simply does not render.
 */
async function fetchProducts(slug: string): Promise<ProductItem[]> {
  try {
    const res = await fetch(
      `${API}/catalog/businesses/${encodeURIComponent(slug)}/products?limit=6`,
      { next: { revalidate: 300 } },
    );
    if (!res.ok) return [];
    return ((await res.json()) as { items: ProductItem[] }).items ?? [];
  } catch {
    return [];
  }
}

/** "Mar 2026" from an ISO stamp; null rather than a guess if it will not parse. */
function monthYear(iso: string | null | undefined): string | null {
  if (!iso) return null;
  const d = new Date(iso);
  if (Number.isNaN(d.getTime())) return null;
  return d.toLocaleDateString("en-IN", { month: "short", year: "numeric" });
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
async function fetchReviews(businessId: string): Promise<{ summary: RatingSummary; items: ReviewItem[] }> {
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
function businessJsonLd(detail: BusinessDetail, canonical: string, summary: RatingSummary): string {
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

export default async function BusinessPage({
  params,
}: {
  params: Promise<{ slug: string }>;
}) {
  const { slug } = await params;
  const detail = await fetchDetail(slug);
  if (!detail) notFound();
  const { business, branches, categories } = detail;
  const canonical = canonicalFor(business.slug);
  const [{ summary, items: reviews }, products] = await Promise.all([
    fetchReviews(business.id),
    fetchProducts(business.slug),
  ]);
  const since = monthYear(business.created_at);
  const coverage = detail.coverage_pincodes ?? [];
  const primary = branches[0];
  const categoryLine = categories.map((c) => c.name.en ?? c.slug).join(" \u00b7 ");

  return (
    <main className="bg-cream pb-10">
      <ViewBeacon slug={slug} />
      <script
        type="application/ld+json"
        dangerouslySetInnerHTML={{ __html: businessJsonLd(detail, canonical, summary) }}
      />
      <Wrap className="py-6">
        {/* Two columns from md up, one below \u2014 the A3 reference layout. The
            sidebar is reference material (at a glance, coverage, location);
            on a phone that belongs BELOW what the visitor came for, which is
            what source order gives us for free. */}
        <div className="grid gap-5 md:grid-cols-[minmax(0,1fr)_320px] md:items-start">
          <div className="min-w-0">
            <Card className="p-4 md:p-5">
              <div className="flex flex-wrap items-center gap-2">
                <h1 className="font-display text-[26px] font-extrabold leading-tight text-ink">
                  {business.name}
                </h1>
                {business.verification_status === "verified" ? (
                  <Badge variant="verified">Verified</Badge>
                ) : null}
              </div>

              <p className="mt-1 flex flex-wrap items-center gap-x-2 gap-y-1 text-[13px] text-sub">
                {summary.rating_avg !== null ? (
                  <span className="font-semibold text-ink">
                    {"\u2605"} {Number(summary.rating_avg).toFixed(1)}{" "}
                    <span className="font-normal text-sub">({summary.rating_count})</span>
                  </span>
                ) : null}
                {categoryLine ? <span>{categoryLine}</span> : null}
                {primary ? (
                  <span>
                    {primary.district}, {primary.state}
                  </span>
                ) : null}
              </p>

              {since ? (
                <p className="mt-1 text-[12.5px] text-muted">On agri.in since {since}</p>
              ) : null}

              {/* Call is the consent-first reveal flow; Share is local. No
                  "Report" button until a route exists behind it \u2014 a control
                  that does nothing is worse than no control. */}
              <div className="mt-3.5 flex flex-wrap items-center gap-2">
                {primary ? <RevealContact branchId={primary.id} slug={business.slug} /> : null}
                <ShareButton title={business.name} />
              </div>
            </Card>

            {business.claimable ? (
              <Card className="mt-4 space-y-2 p-4">
                <h2 className="font-display text-[16px] font-extrabold text-ink">
                  Is this your business?
                </h2>
                <p className="text-[13px] text-sub">
                  Claim this listing to manage it and earn the verified badge.
                </p>
                <Link
                  href={`/directory/businesses/${business.slug}/claim`}
                  className={cn(buttonVariants({ variant: "brand" }), "mt-1 max-w-[240px]")}
                >
                  Claim this listing
                </Link>
              </Card>
            ) : null}

            {business.description?.en || business.description?.ta ? (
              <Card className="mt-4 p-4">
                <h2 className="font-display text-[16px] font-extrabold text-ink">
                  About {"\u00b7"} {"\u0b8e\u0b99\u0bcd\u0b95\u0bb3\u0bc8 \u0baa\u0bb1\u0bcd\u0bb1\u0bbf"}
                </h2>
                {business.description?.en ? (
                  <p className="mt-2 text-[14px] leading-[1.6] text-ink">
                    {business.description.en}
                  </p>
                ) : null}
                {business.description?.ta ? (
                  <p className="mt-2 text-[13.5px] leading-[1.6] text-sub">
                    {business.description.ta}
                  </p>
                ) : null}
              </Card>
            ) : null}

            {products.length > 0 ? (
              <section className="mt-4">
                <h2 className="font-display text-[16px] font-extrabold text-ink">
                  Products &amp; services
                </h2>
                <ul className="mt-2.5 grid gap-2.5 max-md:grid-cols-2 md:grid-cols-3">
                  {products.map((product) => {
                    const spec = specLine(product.specs);
                    return (
                      <li key={product.id}>
                        <Card className="h-full overflow-hidden p-0">
                          {product.images?.[0] ? (
                            <ProductImage src={product.images[0]} alt={product.name} />
                          ) : (
                            <div
                              aria-hidden="true"
                              className="flex h-[104px] w-full items-center justify-center bg-cream text-[26px]"
                            >
                              🌾
                            </div>
                          )}
                          <div className="p-3">
                            <p className="text-[13px] font-semibold leading-snug text-ink">
                              {product.name}
                            </p>
                            {spec ? <p className="mt-0.5 text-[11.5px] text-muted">{spec}</p> : null}
                            {product.price_display ? (
                              <p className="mt-1 font-display text-[14px] font-semibold text-ink">
                                {product.price_display}
                              </p>
                            ) : null}
                          </div>
                        </Card>
                      </li>
                    );
                  })}
                </ul>
              </section>
            ) : null}

            {branches.length > 1 ? (
              <section className="mt-4 space-y-2.5">
                <h2 className="font-display text-[16px] font-extrabold text-ink">Other branches</h2>
                <ul className="space-y-2">
                  {branches.slice(1).map((branch) => (
                    <li key={branch.id}>
                      <Card className="space-y-2 p-3">
                        <p className="text-[13.5px] font-semibold text-ink">{branch.address}</p>
                        <p className="text-[12.5px] text-sub">
                          {branch.district}, {branch.state} {branch.pincode}
                        </p>
                        <RevealContact branchId={branch.id} slug={business.slug} />
                      </Card>
                    </li>
                  ))}
                </ul>
              </section>
            ) : null}

            <div className="mt-4">
              <SponsoredSlot />
            </div>

            <div className="mt-4">
              <LeadForm
                businessId={business.id}
                defaultPincode={business.primary_pincode}
                milkVertical={business.type === "vendor"}
              />
            </div>

            <ReviewsSection summary={summary} items={reviews} />

            <div className="mt-4">
              <ReviewForm businessId={business.id} slug={business.slug} />
            </div>
          </div>

          <aside className="min-w-0 space-y-4">
            <Card className="p-4">
              <h2 className="font-display text-[15px] font-extrabold text-ink">At a glance</h2>
              {/* Only facts the API actually returns. The A3 reference also
                  shows Established, Response time, Languages and Payment \u2014
                  none of which exists on the business record yet, and a
                  plausible-looking guess on a trust page is worse than a
                  shorter list. */}
              <dl className="mt-2 divide-y divide-cream-line text-[12.5px]">
                {categoryLine ? (
                  <div className="flex justify-between gap-3 py-2">
                    <dt className="text-sub">Category</dt>
                    <dd className="text-right font-medium text-ink">{categoryLine}</dd>
                  </div>
                ) : null}
                <div className="flex justify-between gap-3 py-2">
                  <dt className="text-sub">Type</dt>
                  <dd className="text-right font-medium capitalize text-ink">{business.type}</dd>
                </div>
                {since ? (
                  <div className="flex justify-between gap-3 py-2">
                    <dt className="text-sub">On agri.in since</dt>
                    <dd className="text-right font-medium text-ink">{since}</dd>
                  </div>
                ) : null}
                <div className="flex justify-between gap-3 py-2">
                  <dt className="text-sub">Verification</dt>
                  <dd className="text-right font-medium capitalize text-ink">
                    {business.verification_status}
                  </dd>
                </div>
                {coverage.length > 0 ? (
                  <div className="flex justify-between gap-3 py-2">
                    <dt className="text-sub">Delivers to</dt>
                    <dd className="text-right font-medium text-ink">
                      {coverage.length} pincode{coverage.length === 1 ? "" : "s"}
                    </dd>
                  </div>
                ) : null}
              </dl>
            </Card>

            {coverage.length > 0 ? (
              <Card className="p-4">
                <h2 className="font-display text-[15px] font-extrabold text-ink">
                  Delivery coverage {"\u00b7"} {coverage.length} pincode
                  {coverage.length === 1 ? "" : "s"}
                </h2>
                <ul className="mt-2.5 flex flex-wrap gap-1.5">
                  {coverage.map((pincode) => (
                    <li
                      key={pincode}
                      className="rounded-full bg-cream px-2.5 py-1 text-[11.5px] font-medium text-sub"
                    >
                      {pincode}
                    </li>
                  ))}
                </ul>
              </Card>
            ) : null}

            {primary ? (
              <Card className="p-4">
                <h2 className="font-display text-[15px] font-extrabold text-ink">Location</h2>
                <p className="mt-2 text-[12.5px] leading-[1.55] text-sub">
                  {primary.address}
                  <br />
                  {primary.district}, {primary.state} {primary.pincode}
                </p>
                {/* Directions, not an embedded map: MapLibre is a web-milk-only
                    dependency today, so an interactive map here is a real
                    feature (bundle + tiles), not a styling change. */}
                {primary.lat && primary.lng ? (
                  <a
                    href={`https://www.openstreetmap.org/?mlat=${primary.lat}&mlon=${primary.lng}#map=16/${primary.lat}/${primary.lng}`}
                    target="_blank"
                    rel="noopener noreferrer"
                    className="tap-target mt-2 inline-flex min-h-[44px] items-center text-[12.5px] font-semibold text-brand no-underline"
                  >
                    Directions {"\u2192"}
                  </a>
                ) : null}
              </Card>
            ) : null}
          </aside>
        </div>
      </Wrap>
    </main>
  );
}
