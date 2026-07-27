import { Badge, Card, Wrap } from "@agri/ui";
import { buildMetadata, canonicalUrl } from "@agri/ui/seo";
import type { Metadata } from "next";
import { getTranslations, setRequestLocale } from "next-intl/server";
import { notFound } from "next/navigation";
import { Suspense } from "react";

import { Link } from "@/i18n/navigation";
import { CATEGORY_MESSAGE_KEY, isDairyCategory } from "@/lib/categories";
import {
  fetchBusiness,
  fetchProducts,
  fetchReviews,
  type BusinessDetail,
  type CatalogProduct,
  type PublicBranch,
  type RatingSummary,
} from "@/lib/business";

import { LeadForm } from "./lead-form";
import { NearbyShops } from "./nearby-shops";
import { RevealContact } from "./reveal-contact";
import { ReviewForm } from "./review-form";
import { ReviewsSection } from "./reviews-section";
import { ViewBeacon } from "./view-beacon";

const SITE = "https://milk.in";

export const revalidate = 300;

function canonicalFor(slug: string): string {
  return canonicalUrl(SITE, `/directory/businesses/${slug}`);
}

export async function generateMetadata({
  params,
}: {
  params: Promise<{ locale: string; slug: string }>;
}): Promise<Metadata> {
  const { locale, slug } = await params;
  setRequestLocale(locale);
  const detail = await fetchBusiness(slug);
  if (!detail) {
    return { title: "Vendor not found", robots: { index: false, follow: true } };
  }
  const { business } = detail;
  const description =
    business.description?.en ??
    `Milk from ${business.name} — prices, coverage and contact on Milk.in.`;
  return buildMetadata({
    title: `${business.name} | Milk.in`,
    description,
    canonical: canonicalFor(business.slug),
    siteName: "Milk.in",
  });
}

/**
 * Hand-built LocalBusiness JSON-LD (same precedent as web-agri's business
 * page: the shared builder requires `address`, only known when a branch
 * exists). `<` escaped so content can never close the script tag.
 * NON-NEGOTIABLE 2: must parse as valid LocalBusiness (vendor pages,
 * `isBrand=false`). Brand pages (D27 Task 14) are `shop`-type businesses
 * with a product catalog rather than a single physical premises, so they
 * declare `["Organization", "Brand"]` instead — same fields otherwise.
 */
function businessJsonLd(
  detail: BusinessDetail,
  canonical: string,
  summary: RatingSummary,
  isBrand: boolean,
): string {
  const { business, branches } = detail;
  const firstBranch = branches[0];
  const data = {
    "@context": "https://schema.org",
    "@type": isBrand ? ["Organization", "Brand"] : "LocalBusiness",
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
    ...(firstBranch?.lat != null && firstBranch?.lng != null
      ? {
          geo: {
            "@type": "GeoCoordinates",
            latitude: Number(firstBranch.lat),
            longitude: Number(firstBranch.lng),
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

function specText(specs: Record<string, unknown>, key: string): string | null {
  const value = specs[key];
  return typeof value === "string" && value ? value : null;
}

function ProductCardLite({ product }: { product: CatalogProduct }) {
  const meta = [specText(product.specs, "milk_type"), specText(product.specs, "pack_size")]
    .filter(Boolean)
    .join(" · ");
  return (
    <Card className="space-y-1 p-3">
      <h3 className="text-[14.5px] font-extrabold leading-[1.3] text-ink">{product.name}</h3>
      {meta ? <p className="text-[12.5px] text-sub">{meta}</p> : null}
      {product.price_display ? (
        <p className="text-[15px] font-extrabold text-ink">{product.price_display}</p>
      ) : null}
    </Card>
  );
}

/** Delivery windows render from Branch.hours (free-shape JSONB) — structured
 * delivery-window schema is deferred (design decision 3). */
function BranchHours({ branch }: { branch: PublicBranch }) {
  const entries = Object.entries(branch.hours);
  if (entries.length === 0) return null;
  return (
    <p className="text-[12.5px] text-sub">
      {entries.map(([label, value]) => `${label}: ${String(value)}`).join(" · ")}
    </p>
  );
}

const MAX_PINCODES_SHOWN = 12;

export default async function VendorProfilePage({
  params,
}: {
  params: Promise<{ locale: string; slug: string }>;
}) {
  const { locale, slug } = await params;
  setRequestLocale(locale);
  const detail = await fetchBusiness(slug);
  if (!detail) notFound();
  const { business, branches, categories, coverage_pincodes } = detail;
  const canonical = canonicalFor(business.slug);
  const [products, { summary, items: reviews }] = await Promise.all([
    fetchProducts(business.slug),
    fetchReviews(business.id),
  ]);
  // Brand variant (D27 Task 14): `shop`-type businesses with a catalog read
  // as a brand (many outlets, one product line) rather than a single
  // physical premises. A `shop` with no products keeps the vendor layout.
  const isBrand = business.type === "shop" && products.length > 0;
  const t = await getTranslations("ui");
  const shownPincodes = coverage_pincodes.slice(0, MAX_PINCODES_SHOWN);
  const morePincodes = coverage_pincodes.length - shownPincodes.length;

  return (
    <main>
      <Suspense fallback={null}>
        <ViewBeacon slug={slug} />
      </Suspense>
      <script
        type="application/ld+json"
        dangerouslySetInnerHTML={{ __html: businessJsonLd(detail, canonical, summary, isBrand) }}
      />
      <Wrap className="max-w-[720px] py-6">
        <header className="space-y-1.5">
          <div className="flex flex-wrap items-center gap-2">
            <h1 className="font-display text-[26px] font-extrabold text-ink">{business.name}</h1>
            {business.verification_status === "verified" ? (
              <Badge variant="verified">✔ Verified</Badge>
            ) : null}
          </div>
          <p className="text-[13px] font-semibold text-sub">
            {business.type} · {business.primary_pincode}
          </p>
          {business.description?.en ? (
            <p className="text-[15px] text-ink">{business.description.en}</p>
          ) : null}
          {categories.length > 0 ? (
            <div className="flex flex-wrap gap-2" data-testid="category-chips">
              {categories.map((category) =>
                isDairyCategory(category.slug) ? (
                  <Link
                    key={category.slug}
                    href={`/c/${category.slug}`}
                    className="rounded-pill border-2 border-line bg-card px-3.5 py-2.5 text-[12.5px] font-extrabold text-ink no-underline"
                    data-testid={`category-chip-${category.slug}`}
                  >
                    {t(`dairyCategories.${CATEGORY_MESSAGE_KEY[category.slug]}.name`)}
                  </Link>
                ) : (
                  <Badge key={category.slug} variant="neutral">
                    {category.name.en ?? category.slug}
                  </Badge>
                ),
              )}
            </div>
          ) : null}
        </header>

        {products.length > 0 ? (
          <section className="mt-6 space-y-2.5" aria-labelledby="products-h">
            <h2 id="products-h" className="font-display text-[16px] font-extrabold text-ink">
              {isBrand ? t("brandPage.products") : "Milk products"}
            </h2>
            <div className="grid gap-3 sm:grid-cols-2">
              {products.map((product) => (
                <ProductCardLite key={product.id} product={product} />
              ))}
            </div>
          </section>
        ) : null}

        {isBrand ? (
          <NearbyShops slug={business.slug} initialPincode={business.primary_pincode} />
        ) : null}

        {coverage_pincodes.length > 0 ? (
          <section className="mt-6 space-y-1.5" aria-labelledby="coverage-h">
            <h2 id="coverage-h" className="font-display text-[16px] font-extrabold text-ink">
              Delivery area
            </h2>
            <p className="text-[12.5px] text-sub" data-testid="coverage-pincodes">
              {shownPincodes.join(", ")}
              {morePincodes > 0 ? ` + ${morePincodes} more` : ""}
            </p>
          </section>
        ) : null}

        {branches.length > 0 ? (
          <section className="mt-6 space-y-2.5" aria-labelledby="branches-h">
            <h2 id="branches-h" className="font-display text-[16px] font-extrabold text-ink">
              Branches &amp; delivery hours
            </h2>
            <ul className="space-y-2">
              {branches.map((branch) => (
                <li key={branch.id}>
                  <Card className="space-y-2 p-3">
                    <p className="text-[13.5px] font-semibold text-ink">{branch.address}</p>
                    <p className="text-[12.5px] text-sub">
                      {branch.district}, {branch.state} {branch.pincode}
                    </p>
                    <BranchHours branch={branch} />
                    <RevealContact branchId={branch.id} slug={business.slug} />
                  </Card>
                </li>
              ))}
            </ul>
          </section>
        ) : null}

        <div className="mt-6">
          <LeadForm
            businessId={business.id}
            defaultPincode={business.primary_pincode}
            milkVertical={business.type === "vendor"}
          />
        </div>

        <ReviewsSection summary={summary} items={reviews} />

        <div className="mt-6">
          <ReviewForm businessId={business.id} slug={business.slug} />
        </div>
      </Wrap>
    </main>
  );
}
