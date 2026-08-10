import { AdCarousel, AdSlot, Wrap } from "@agri/ui";
import { buildMetadata, canonicalUrl } from "@agri/ui/seo";
import type { Metadata } from "next";
import { getTranslations, setRequestLocale } from "next-intl/server";

import { HouseAdCard } from "@/components/molecules/HouseAdCard";
import {
  BrandsAvailable,
  DairyServices,
  ShowcaseProducts,
} from "@/components/organisms/HomeCommerce";
import {
  HowItWorks,
  PopularNearYou,
  ReviewsStrip,
  StatsBand,
} from "@/components/organisms/HomeEngagement";
import {
  AdvertiseBand,
  FamilyStrip,
  HomeCtaTiles,
  HomeFaq,
  TrustRow,
} from "@/components/organisms/HomeStatic";
import { HomeCategoryBar } from "@/components/organisms/HomeCategoryBar";
import { MilkTypeChips } from "@/components/organisms/MilkTypeChips";
import { Link } from "@/i18n/navigation";
import { PriceTicker } from "@/components/organisms/PriceTicker";
import { VendorGrid } from "@/components/organisms/VendorGrid";
import { CONSOLE_URL, listingsHref } from "@/lib/console";
import { fetchHomeData, homeStats, HOME_PINCODE } from "@/lib/home";
import { getShowcaseProducts } from "@/lib/showcase";
import { fetchMilkTypes, fetchProductCategories } from "@/lib/taxonomy";

import { PincodeHeroFinder } from "./pincode-hero";

const SITE = "https://milk.in";
// Every section renders from cached server-side reads (no per-visitor data),
// so the whole page stays ISR-cacheable.
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

  const [data, categories, milkTypes, showcase, t, tFaq] = await Promise.all([
    fetchHomeData(),
    fetchProductCategories(locale),
    fetchMilkTypes(locale),
    getShowcaseProducts("milk", 4, locale),
    getTranslations("ui"),
    getTranslations("ui.home.faq"),
  ]);

  const home = data.home;
  const pincode = home?.location?.pincode ?? HOME_PINCODE;
  const resultsBase = home?.location
    ? `/${home.location.district.toLowerCase().replace(/\s+/g, "-")}/${pincode}`
    : "/search";
  const recommendedIds = new Set((home?.recommended ?? []).map((card) => card.id));
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
          <PincodeHeroFinder micLabel={t("search.micLabel")} />
        </div>

        {/* §5 — schema-driven category bar (D17 vertical registry). */}
        <div className="mt-3">
          <HomeCategoryBar categories={categories} />
        </div>

        {/* §5c — milk-type chips, schema-driven, feeding D23's filter state. */}
        {home ? (
          <MilkTypeChips filters={home.filters} milkTypes={milkTypes} base={resultsBase} />
        ) : null}

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

        {/* §5b — live price ticker from the D23 price-banner computation. */}
        {home ? <PriceTicker home={home} milkTypes={milkTypes} /> : null}

        {/* §6 — organic trust row (static i18n content component). */}
        <TrustRow />

        {/* §7 — certified products, via the single showcase accessor. */}
        <ShowcaseProducts products={showcase} />

        {/* §8 — vendors, with §8a2's house advertise band inside the block. */}
        <section className="pb-2 pt-[22px]" id="shops">
          <div className="mb-3.5 flex items-baseline justify-between gap-2.5">
            <h2 className="font-display text-xl font-extrabold">{t("home.vendors.title")}</h2>
            <Link
              href={resultsBase}
              prefetch={false}
              className="text-[13px] font-bold text-brand-deep no-underline"
            >
              {t("home.vendors.showMap")}
            </Link>
          </div>
          <VendorGrid
            cards={home?.vendors ?? []}
            ratings={data.ratings}
            recommendedIds={recommendedIds}
            milkTypes={milkTypes}
            pincode={pincode}
          />
          <AdvertiseBand />
        </section>

        {/* §8f — brands available in this pincode (hidden when none). */}
        <BrandsAvailable brands={home?.brands ?? []} milkTypes={milkTypes} pincode={pincode} />

        {/* §8g — dairy services → existing /c/ landing pages. */}
        <DairyServices />

        {/* §8b — stats band from real aggregates. */}
        <StatsBand stats={homeStats(data)} />

        {/* §8c — how it works. */}
        <HowItWorks />

        {/* §8d — approved reviews only; hidden when empty. */}
        <ReviewsStrip reviews={data.reviews} locale={locale} />

        {/* §8e — popular near you, from the real covered-geo feed. */}
        <PopularNearYou covered={data.coveredPincodes} />

        {/* §9 — the two big CTA tiles. */}
        <HomeCtaTiles pincode={pincode} />

        {/* §10c — FAQ (also emitted as FAQPage JSON-LD above). */}
        <HomeFaq />

        {/* §10 — family strip. */}
        <FamilyStrip />
      </Wrap>
    </main>
  );
}
