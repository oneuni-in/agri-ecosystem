import { AdSlot } from "@agri/ui";
import { buildMetadata, canonicalUrl } from "@agri/ui/seo";
import type { Metadata } from "next";
import { notFound } from "next/navigation";
import { setRequestLocale } from "next-intl/server";

import { HouseAdCard } from "@/components/molecules/HouseAdCard";
import { routing } from "@/i18n/routing";
import { fetchProductCategories } from "@/lib/taxonomy";

import { ProductPincodeFinder } from "./product-pincode-finder";

const SITE = "https://milk.in";

export const revalidate = 3600;

/**
 * `true` on purpose (M1 NON-NEGOTIABLE 1): a category added to the schema
 * AFTER this deploy still renders, on demand, with no rebuild. Unknown
 * values 404 below, so this is not an open door.
 */
export const dynamicParams = true;

export async function generateStaticParams() {
  const categories = await fetchProductCategories("en");
  return routing.locales.flatMap((locale) =>
    categories.map((category) => ({ locale, category: category.value })),
  );
}

type Params = Promise<{ locale: string; category: string }>;

export async function generateMetadata({ params }: { params: Params }): Promise<Metadata> {
  const { locale, category } = await params;
  const match = (await fetchProductCategories(locale)).find((c) => c.value === category);
  if (!match) return { title: "Milk.in" };
  return buildMetadata({
    title: `${match.label} near you — Milk.in`,
    description: `Find ${match.label} from verified dairy brands, local vendors and farms near you across Tamil Nadu.`,
    canonical: canonicalUrl(SITE, `/p/${category}`),
    siteName: "Milk.in",
  });
}

/**
 * CollectionPage — hand-built, following the precedent in
 * `app/[locale]/c/[category]/page.tsx`. `<` escaped so it can never close
 * the script tag.
 */
function collectionJsonLd(name: string, canonical: string): string {
  return JSON.stringify({
    "@context": "https://schema.org",
    "@type": "CollectionPage",
    name,
    url: canonical,
  }).replaceAll("<", "\\u003c");
}

export default async function ProductCategoryPage({ params }: { params: Params }) {
  const { locale, category } = await params;
  setRequestLocale(locale);
  const match = (await fetchProductCategories(locale)).find((c) => c.value === category);
  if (!match) notFound();
  const canonical = canonicalUrl(SITE, `/p/${category}`);
  return (
    <main className="mx-auto flex w-full max-w-[720px] flex-col gap-5 px-4 py-6">
      <script
        type="application/ld+json"
        dangerouslySetInnerHTML={{ __html: collectionJsonLd(match.label, canonical) }}
      />
      <h1 className="font-display text-[22px] font-extrabold text-ink">
        {match.label} near you
      </h1>
      {match.vern ? <p className="vern text-[15px] text-sub">{match.vern}</p> : null}
      {/* M2: milk_category_banner - context is the M1 schema category value,
          so a schema-added category is targetable inventory automatically. */}
      <AdSlot
        slotKey="milk_category_banner"
        category={category}
        heightClass="h-[72px]"
        fallback={
          <HouseAdCard
            title="🥛 Post your need — vendors reply to you"
            vern="என் தேவை"
            href="/post-need"
          />
        }
      />
      <ProductPincodeFinder category={category} />
    </main>
  );
}
