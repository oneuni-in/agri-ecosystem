import { AdCarousel, AdSlot, LOC_COOKIE, Wrap } from "@agri/ui";
import { buildMetadata, canonicalUrl } from "@agri/ui/seo";
import type { Metadata } from "next";
import { getTranslations, setRequestLocale } from "next-intl/server";
import { cookies } from "next/headers";
import { Suspense } from "react";

import { HouseAdCard } from "@/components/molecules/HouseAdCard";
import { DairyServices, ShowcaseProducts } from "@/components/organisms/HomeCommerce";
import { HowItWorks } from "@/components/organisms/HomeEngagement";
import { FamilyStrip, HomeFaq, TrustRow } from "@/components/organisms/HomeStatic";
import { HomeCategoryBar } from "@/components/organisms/HomeCategoryBar";
import { CONSOLE_URL, listingsHref } from "@/lib/console";
import { serveAds } from "@/lib/ads";
import { fetchHomeData, resolveHomePincode } from "@/lib/home";
import { getShowcaseProducts } from "@/lib/showcase";
import { fetchMilkTypes, fetchProductCategories } from "@/lib/taxonomy";

import {
  HomeEngagementBlock,
  HomeEngagementSkeleton,
  HomeFilters,
  HomeFiltersSkeleton,
  HomeVendors,
  HomeVendorsSkeleton,
} from "./home-sections";
import { PincodeHeroFinder } from "./pincode-hero";

const SITE = "https://milk.in";
// The page renders for the VISITOR's pincode (their `agri_loc` cookie), so it
// is per-request rather than ISR. The cost is contained: the shell, hero and
// search band do not await the location-bound blend — it streams in behind a
// Suspense boundary whose skeleton reserves the same space (zero CLS).
export const dynamic = "force-dynamic";

export function generateMetadata(): Metadata {
  return {
    ...buildMetadata({
      title: "Milk near you — all options, one place | Milk.in",
      description:
        "Enter your pincode to find cow, buffalo, A2 and organic milk vendors, brands and farm-fresh delivery near you across Tamil Nadu.",
      canonical: canonicalUrl(SITE, "/"),
      siteName: "Milk.in",
    }),
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
 * WebSite + Organization + FAQPage (§21). Hand-built, following the
 * hand-built-JSON-LD precedent elsewhere in this app. `<` is escaped so the
 * payload can never close the script tag.
 */
function homeJsonLd(faq: { q: string; a: string }[]): string {
  const graph = {
    "@context": "https://schema.org",
    "@graph": [
      { "@type": "WebSite", name: "Milk.in", url: SITE },
      { "@type": "Organization", name: "Milk.in", url: SITE },
      {
        "@type": "FAQPage",
        mainEntity: faq.map((item) => ({
          "@type": "Question",
          name: item.q,
          acceptedAnswer: { "@type": "Answer", text: item.a },
        })),
      },
    ],
  };
  return JSON.stringify(graph).replaceAll("<", "\\u003c");
}

/**
 * The Milk.in consumer home, built to the approved reference
 * (`docs/design-reference/desktop v3.html`). Section numbers below are the
 * reference's own.
 *
 * Every data-bearing section renders from a real backend source through
 * `fetchHomeData()` — one server-side aggregate, no client fetch, no mock
 * rows. The page is ISR, so it renders a configured pincode (`HOME_PINCODE`)
 * exactly as the reference does; the location pill and the §4 pincode box move
 * the visitor to their own `/{city}/{pincode}`.
 */
export default async function HomePage({
  params,
}: {
  params: Promise<{ locale: string }>;
}) {
  const { locale } = await params;
  setRequestLocale(locale);

  // The visitor's own pincode (header pill / §4 box / GPS all write this
  // cookie), falling back to the launch city for a first-time guest.
  const pincode = resolveHomePincode((await cookies()).get(LOC_COOKIE)?.value);
  // Deliberately NOT awaited here: the shell, hero and search band render
  // immediately and the location-bound sections stream in behind Suspense.
  const dataPromise = fetchHomeData(pincode);

  const [categories, milkTypes, showcase, heroAds, t, tFaq] = await Promise.all([
    fetchProductCategories(locale),
    fetchMilkTypes(locale),
    getShowcaseProducts("milk", 4, locale),
    // Served here, not in the browser: the hero is the LCP element, and a
    // client fetch delays its image until after hydration.
    serveAds("milk_home_hero_xl", { pincode, locale }, 5),
    getTranslations("ui"),
    getTranslations("ui.home.faq"),
  ]);

  const faq = (["1", "2", "3", "4"] as const).map((n) => ({
    q: tFaq(`q${n}`),
    a: tFaq(`a${n}`),
  }));

  return (
    <main className="bg-cream pb-6">
      <script type="application/ld+json" dangerouslySetInnerHTML={{ __html: homeJsonLd(faq) }} />

      {/* §3 — full-bleed hero ad, D21 slot milk_home_hero_xl. Approved
          creatives only (engine contract, re-checked in the parse layer). The
          box is reserved by aspect ratio at the two seeded creative sizes, so
          loading, empty and full all occupy the same space. */}
      <AdCarousel
        slotKey="milk_home_hero_xl"
        initialAds={heroAds}
        heightClass="aspect-[750/360] md:aspect-[1600/420]"
        badgeClassName="right-3 top-3"
        sponsoredLabel={t("badges.sponsored")}
        arrows={{ prevLabel: t("heroAd.prev"), nextLabel: t("heroAd.next") }}
        fallback={
          <HouseAdCard
            title={t("utility.listBusiness")}
            href={listingsHref(CONSOLE_URL)}
          />
        }
      />

      <Wrap>
        {/* §4 — the ONE search on home. Unchanged D19/D23 pincode + GPS logic,
            restyled, plus the §29 voice door into the D25 pipeline. */}
        <div className="mt-3.5 rounded-card bg-header-gradient px-4 pb-[22px] pt-[26px] text-center text-white">
          <h1 className="mb-1 font-display text-[clamp(22px,4.5vw,32px)] font-extrabold">
            {t("pincode.title")}
          </h1>
          <p className="mb-4 text-sm text-brand-soft">{t("pincode.subtitle")}</p>
          <PincodeHeroFinder micLabel={t("search.micLabel")} setsLocation />
        </div>

        {/* §5 — schema-driven category bar (D17 vertical registry). */}
        <div className="mt-3">
          <HomeCategoryBar categories={categories} />
        </div>

        {/* §5c type chips + §5b price ticker — both bound to the visitor's
            pincode, so they stream rather than block the shell. */}
        <Suspense fallback={<HomeFiltersSkeleton />}>
          <HomeFilters data={dataPromise} milkTypes={milkTypes} />
        </Suspense>

        {/* §5d — category-partner banner, D21 slot, approved-only, collapses
            when the slot is empty (no fallback passed). */}
        <AdSlot
          slotKey="milk_category_banner"
          // The reserved box matches the slot's creative ratio (1200x160, see
          // scripts/seed_sample_media.py `_SLOT_SIZES`). A box that disagrees
          // with the creative renders an unreadable slice, because AdImage is
          // object-cover by contract.
          heightClass="aspect-[1200/160]"
          className="mt-3 overflow-hidden rounded-btn"
          badgeClassName="right-2 top-2"
          sponsoredLabel={t("badges.sponsored")}
        />

        {/* Everything from here down is below the fold on a phone. See
            `.below-fold` in globals.css: these skip layout/paint until scrolled
            near, which is what keeps a 44-section page's first paint cheap. */}
        <div className="below-fold">
        {/* §6 — organic trust row (static i18n content component). */}
        <TrustRow />

        {/* §7 — certified products, via the single showcase accessor. */}
        <ShowcaseProducts products={showcase} />

        {/* §8 vendors (+ §8a2 house band) and §8f brands. */}
        <Suspense fallback={<HomeVendorsSkeleton />}>
          <HomeVendors data={dataPromise} milkTypes={milkTypes} locale={locale} />
        </Suspense>

        {/* §8g — dairy services → existing /c/ landing pages. */}
        <DairyServices />

        {/* §8c — how it works (static i18n). */}
        <HowItWorks />

        {/* §8b stats, §8d approved reviews, §8e popular-near-you, §9 CTA tiles. */}
        <Suspense fallback={<HomeEngagementSkeleton />}>
          <HomeEngagementBlock data={dataPromise} locale={locale} />
        </Suspense>

        {/* §10c — FAQ (also emitted as FAQPage JSON-LD above). */}
        <HomeFaq />

        {/* §10 — family strip. */}
        <FamilyStrip />
        </div>
      </Wrap>
    </main>
  );
}
