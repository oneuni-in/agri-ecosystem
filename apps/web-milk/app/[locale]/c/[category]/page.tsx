import { buildMetadata, canonicalUrl } from "@agri/ui/seo";
import type { Metadata } from "next";
import { notFound } from "next/navigation";
import { getTranslations, setRequestLocale } from "next-intl/server";

import {
  CATEGORY_MESSAGE_KEY,
  categoryIcon,
  categoryLabel,
  fetchBusinessCategories,
} from "@/lib/categories";
import { routing } from "@/i18n/routing";

import { CategoryPincodeFinder } from "./category-pincode-finder";

const SITE = "https://milk.in";

export const revalidate = 3600;

/**
 * `true` on purpose (same M1 NON-NEGOTIABLE 1 shape as /p/{category}): a
 * category that becomes active AFTER this deploy still renders, on demand,
 * with no rebuild. Unknown slugs 404 below, so this is not an open door.
 */
export const dynamicParams = true;

export async function generateStaticParams() {
  // Backend down (CI builds) ⇒ [] — every page then renders on demand.
  const categories = await fetchBusinessCategories();
  return routing.locales.flatMap((locale) =>
    categories.map((category) => ({ locale, category: category.slug })),
  );
}

type Params = Promise<{ locale: string; category: string }>;

/** Hand-written copy where it exists (the D27 four via ui.dairyCategories),
 * the generic localized line otherwise — copy enrichment only; the taxonomy
 * itself is the public `/directory/categories/active` read. */
async function describeCategory(
  locale: string,
  slug: string,
  label: string,
): Promise<string> {
  const t = await getTranslations({ locale, namespace: "ui" });
  const msgKey = CATEGORY_MESSAGE_KEY[slug];
  return msgKey
    ? t(`dairyCategories.${msgKey}.description`)
    : t("categoryBrowse.genericDescription", { name: label });
}

export async function generateMetadata({ params }: { params: Params }): Promise<Metadata> {
  const { locale, category } = await params;
  const match = (await fetchBusinessCategories()).find((c) => c.slug === category);
  if (!match) return { title: "Milk.in" };
  const label = categoryLabel(match, locale);
  return buildMetadata({
    title: `${label} — Milk.in`,
    description: await describeCategory(locale, category, label),
    canonical: canonicalUrl(SITE, `/c/${category}`),
    siteName: "Milk.in",
  });
}

/**
 * CollectionPage — hand-built (no collectionPage builder in `@agri/ui/seo`,
 * see `apps/web-agri/app/directory/businesses/[slug]/page.tsx` and
 * `apps/web-milk/app/[pincode]/page.tsx` for the hand-built-JSON-LD
 * precedent this follows). `<` escaped so it can never close the script tag.
 */
function collectionJsonLd(name: string, description: string, canonical: string): string {
  return JSON.stringify({
    "@context": "https://schema.org",
    "@type": "CollectionPage",
    name,
    description,
    url: canonical,
  }).replaceAll("<", "\\u003c");
}

export default async function CategoryLandingPage({ params }: { params: Params }) {
  const { locale, category } = await params;
  const match = (await fetchBusinessCategories()).find((c) => c.slug === category);
  if (!match) notFound();
  setRequestLocale(locale);
  const label = categoryLabel(match, locale);
  const description = await describeCategory(locale, category, label);
  const canonical = canonicalUrl(SITE, `/c/${category}`);
  return (
    <main className="mx-auto flex w-full max-w-[720px] flex-col gap-5 px-4 py-6">
      <script
        type="application/ld+json"
        dangerouslySetInnerHTML={{
          __html: collectionJsonLd(label, description, canonical),
        }}
      />
      <h1 className="font-display text-[22px] font-extrabold text-ink">
        <span aria-hidden="true">{categoryIcon(category)}</span> {label}
      </h1>
      <p className="text-[15px] text-sub">{description}</p>
      <CategoryPincodeFinder category={category} />
    </main>
  );
}
