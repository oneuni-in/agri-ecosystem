import { AdSlot, PincodeHero } from "@agri/ui";
import { buildMetadata, canonicalUrl } from "@agri/ui/seo";
import type { Metadata } from "next";
import { setRequestLocale } from "next-intl/server";

import { HouseAdCard } from "@/components/molecules/HouseAdCard";
import { CategoryTileRow } from "@/components/organisms/CategoryTileRow";
import { Link } from "@/i18n/navigation";
import { CONSOLE_URL, listingsHref } from "@/lib/console";
import { fetchProductCategories } from "@/lib/taxonomy";

import { PincodeHeroFinder } from "./pincode-hero";

const SITE = "https://milk.in";
// Static hero — no per-visitor data on this page, so it stays ISR-cacheable.
export const revalidate = 3600;

export function generateMetadata(): Metadata {
  return {
    ...buildMetadata({
      title: "Milk near you — all options, one place | Milk.in",
      description:
        "Enter your pincode to find cow, buffalo, A2 and organic milk vendors, brands and farm-fresh delivery near you across Tamil Nadu.",
      canonical: canonicalUrl(SITE, "/"),
      siteName: "Milk.in",
    }),
    // hreflang: "/" is the canonical English URL; ta/hi live under /ta /hi.
    alternates: {
      canonical: `${SITE}/`,
      languages: {
        en: `${SITE}/`,
        ta: `${SITE}/ta`,
        hi: `${SITE}/hi`,
        "x-default": `${SITE}/`,
      },
    },
  };
}

/**
 * WebSite + Organization — hand-built (no webSite/organization builder in
 * `@agri/ui/seo`; follows the hand-built-JSON-LD precedent in
 * `apps/web-agri/app/directory/businesses/[slug]/page.tsx` and
 * `apps/web-milk/app/[pincode]/page.tsx`). `<` escaped so it can never close
 * the script tag.
 */
function homeJsonLd(): string {
  const graph = {
    "@context": "https://schema.org",
    "@graph": [
      { "@type": "WebSite", name: "Milk.in", url: SITE },
      { "@type": "Organization", name: "Milk.in", url: SITE },
    ],
  };
  return JSON.stringify(graph).replaceAll("<", "\\u003c");
}

/**
 * "Milk.in's homepage IS a pincode box" — the whole page above the
 * (untouched) site header is the `.pin-hero` pattern: `PincodeHero` is the
 * shared `@agri/ui` shell (title/subtitle/padding, already used for this
 * exact pattern in `apps/web-agri/app/demo/page.tsx`); `PincodeHeroFinder`
 * supplies the interactive pincode box + GPS pill.
 */
export default async function HomePage({
  params,
}: {
  params: Promise<{ locale: string }>;
}) {
  const { locale } = await params;
  setRequestLocale(locale);
  const categories = await fetchProductCategories(locale);
  return (
    <main className="bg-header-gradient">
      <script type="application/ld+json" dangerouslySetInnerHTML={{ __html: homeJsonLd() }} />
      <PincodeHero
        className="mx-auto max-w-[720px]"
        title="Milk near you — all options, one place"
        subtitle="உங்கள் பகுதியில் உள்ள எல்லா பால் · brands, local vendors, farm-fresh delivery"
      >
        <PincodeHeroFinder />
      </PincodeHero>
      <div className="mx-auto w-full max-w-[720px] pt-4">
        <CategoryTileRow categories={categories} heading="Dairy categories" />
      </div>
      {/* M2: milk_home_hero ad slot. */}
      <div className="mx-auto w-full max-w-[720px] px-4 pt-4">
        <AdSlot
          slotKey="milk_home_hero"
          heightClass="h-[84px]"
          fallback={
            <HouseAdCard
              title="List your dairy business"
              vern="உங்கள் வணிகத்தைப் பதிவு செய்யுங்கள்"
              href={listingsHref(CONSOLE_URL)}
            />
          }
        />
      </div>
      {/* The killer flow (D25): demand posts its need, covering vendors reply. */}
      <div className="mx-auto max-w-[720px] px-4 pb-6">
        <Link
          href="/post-need"
          prefetch={false}
          className="block rounded-card border border-line bg-card px-4 py-3 text-center text-[14px] font-bold text-ink no-underline"
          data-testid="home-post-need-cta"
        >
          🥛 Post my need — vendors reply to you{" "}
          <span className="vern font-normal text-sub">· என் தேவை</span>
        </Link>
      </div>
    </main>
  );
}
