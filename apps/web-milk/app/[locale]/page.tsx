import { AdCarousel, PincodeHero, Wrap } from "@agri/ui";
import { buildMetadata, canonicalUrl } from "@agri/ui/seo";
import type { Metadata } from "next";
import { getTranslations, setRequestLocale } from "next-intl/server";

import { HouseAdCard } from "@/components/molecules/HouseAdCard";
import { HomeCategoryBar } from "@/components/organisms/HomeCategoryBar";
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
 * The Milk.in home, rebuilt to the approved reference
 * (`docs/design-reference/desktop v3.html`). Pass 1 lands the frame:
 * §3 hero ad · §4 search band · §5 category bar. The commerce and
 * engagement sections below them arrive in passes 2 and 3.
 */
export default async function HomePage({
  params,
}: {
  params: Promise<{ locale: string }>;
}) {
  const { locale } = await params;
  setRequestLocale(locale);
  const [categories, t] = await Promise.all([
    fetchProductCategories(locale),
    getTranslations("ui"),
  ]);
  return (
    <main className="bg-cream pb-6">
      <script type="application/ld+json" dangerouslySetInnerHTML={{ __html: homeJsonLd() }} />

      {/* §3 — full-bleed hero ad, D21 slot milk_home_hero_xl. Approved
          creatives only: that is the engine's contract, re-checked in the
          parse layer (NN1 defense in depth), so nothing here can weaken it.
          The box is reserved by aspect ratio at the two seeded creative
          sizes (750x360 mobile, 1600x420 desktop) — loading, empty and full
          all occupy the same space, so the hero contributes zero CLS. */}
      <AdCarousel
        slotKey="milk_home_hero_xl"
        heightClass="aspect-[750/360] md:aspect-[1600/420]"
        badgeClassName="right-3 top-3"
        arrows={{ prevLabel: t("heroAd.prev"), nextLabel: t("heroAd.next") }}
        fallback={
          <HouseAdCard
            title="List your dairy business"
            vern="உங்கள் வணிகத்தைப் பதிவு செய்யுங்கள்"
            href={listingsHref(CONSOLE_URL)}
          />
        }
      />

      <Wrap>
        {/* §4 — the ONE search on home. Same pincode/geo logic as before
            (`PincodeHeroFinder` → `/{pincode}`, GPS via /api/identity/location),
            restyled into the reference's contained band, plus the §29 voice
            door into the D25 pipeline. */}
        <PincodeHero
          banded
          className="mt-3.5"
          title={t("pincode.title")}
          subtitle={t("pincode.subtitle")}
        >
          <PincodeHeroFinder micLabel={t("search.micLabel")} />
        </PincodeHero>

        {/* §5 — schema-driven category bar (D17 vertical registry). */}
        <div className="mt-3">
          <HomeCategoryBar categories={categories} />
        </div>

        {/* The killer flow (D25): demand posts its need, covering vendors
            reply. Interim placement — pass 3 replaces it with the §9 CTA
            tiles. */}
        <div className="mt-4">
          <Link
            href="/post-need"
            prefetch={false}
            className="block rounded-card border border-cream-line bg-card px-4 py-3 text-center text-[14px] font-bold text-ink no-underline"
            data-testid="home-post-need-cta"
          >
            🥛 Post my need — vendors reply to you{" "}
            <span className="vern font-normal text-sub">· என் தேவை</span>
          </Link>
        </div>
      </Wrap>
    </main>
  );
}
