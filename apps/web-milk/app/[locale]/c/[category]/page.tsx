import { buildMetadata, canonicalUrl } from "@agri/ui/seo";
import type { Metadata } from "next";
import { notFound } from "next/navigation";
import { getTranslations, setRequestLocale } from "next-intl/server";

import { CATEGORY_MESSAGE_KEY, DAIRY_CATEGORIES, isDairyCategory } from "@/lib/categories";
import { routing } from "@/i18n/routing";

import { CategoryPincodeFinder } from "./category-pincode-finder";

const SITE = "https://milk.in";

export const revalidate = 3600;

export function generateStaticParams() {
  return routing.locales.flatMap((locale) =>
    DAIRY_CATEGORIES.map((category) => ({ locale, category })),
  );
}

type Params = Promise<{ locale: string; category: string }>;

export async function generateMetadata({ params }: { params: Params }): Promise<Metadata> {
  const { locale, category } = await params;
  if (!isDairyCategory(category)) return { title: "Milk.in" };
  const t = await getTranslations({
    locale,
    namespace: `ui.dairyCategories.${CATEGORY_MESSAGE_KEY[category]}`,
  });
  return buildMetadata({
    title: `${t("name")} — Milk.in`,
    description: t("description"),
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
  if (!isDairyCategory(category)) notFound();
  setRequestLocale(locale);
  const t = await getTranslations(`ui.dairyCategories.${CATEGORY_MESSAGE_KEY[category]}`);
  const canonical = canonicalUrl(SITE, `/c/${category}`);
  return (
    <main className="mx-auto flex w-full max-w-[720px] flex-col gap-5 px-4 py-6">
      <script
        type="application/ld+json"
        dangerouslySetInnerHTML={{
          __html: collectionJsonLd(t("name"), t("description"), canonical),
        }}
      />
      <h1 className="font-display text-[22px] font-extrabold text-ink">{t("name")}</h1>
      <p className="text-[15px] text-sub">{t("description")}</p>
      <CategoryPincodeFinder category={category} />
    </main>
  );
}
