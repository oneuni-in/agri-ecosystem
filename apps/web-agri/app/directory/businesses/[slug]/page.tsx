import { Badge, buttonVariants, Card, cn, Wrap } from "@agri/ui";
import { buildMetadata, canonicalUrl } from "@agri/ui/seo";
import type { Metadata } from "next";
import Link from "next/link";
import { notFound } from "next/navigation";

import { LeadForm } from "./lead-form";
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
  };
  branches: {
    id: string;
    address: string;
    state: string;
    district: string;
    pincode: string;
  }[];
  categories: { id: string; slug: string; name: LocalizedText }[];
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
  const { summary, items: reviews } = await fetchReviews(business.id);

  return (
    <main>
      <ViewBeacon slug={slug} />
      <script
        type="application/ld+json"
        dangerouslySetInnerHTML={{ __html: businessJsonLd(detail, canonical, summary) }}
      />
      <Wrap className="max-w-[720px] py-6">
        <header className="space-y-1.5">
          <div className="flex flex-wrap items-center gap-2">
            <h1 className="font-display text-[26px] font-extrabold text-ink">{business.name}</h1>
            {business.verification_status === "verified" ? (
              <Badge variant="verified">Verified</Badge>
            ) : null}
          </div>
          <p className="text-[13px] font-semibold text-sub">
            {business.type} · {business.primary_pincode}
          </p>
          {business.description?.en ? (
            <p className="text-[15px] text-ink">{business.description.en}</p>
          ) : null}
        </header>

        {business.claimable ? (
          <Card className="mt-5 space-y-2 p-4">
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

        {branches.length > 0 ? (
          <section className="mt-6 space-y-2.5">
            <h2 className="font-display text-[16px] font-extrabold text-ink">Branches</h2>
            <ul className="space-y-2">
              {branches.map((branch) => (
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

        {categories.length > 0 ? (
          <p className="mt-5 text-[12.5px] text-sub">
            {categories.map((category) => category.name.en ?? category.slug).join(" · ")}
          </p>
        ) : null}

        <div className="mt-6">
          <SponsoredSlot />
        </div>

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
