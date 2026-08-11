import { injectSponsored, Skeleton } from "@agri/ui";
import { getTranslations } from "next-intl/server";

import { BrandsAvailable } from "@/components/organisms/HomeCommerce";
import {
  PopularNearYou,
  ReviewsStrip,
  StatsBand,
} from "@/components/organisms/HomeEngagement";
import { AdvertiseBand, HomeCtaTiles } from "@/components/organisms/HomeStatic";
import { MilkTypeChips } from "@/components/organisms/MilkTypeChips";
import { PriceTicker } from "@/components/organisms/PriceTicker";
import { VendorGrid } from "@/components/organisms/VendorGrid";
import { Link } from "@/i18n/navigation";
import { fetchSponsoredListings } from "@/lib/ads";
import { homeStats, type HomeData } from "@/lib/home";
import type { ProductCategory } from "@/lib/taxonomy";

/**
 * The location-bound half of the home. Each block awaits the SAME
 * `fetchHomeData()` promise the page created, so the blend is fetched once
 * and the three Suspense boundaries resolve together — but the shell, the
 * hero and the search band never wait on it.
 *
 * Skeletons reserve the loaded dimensions (§35), so streaming costs no layout
 * shift.
 */
type Props = {
  data: Promise<HomeData>;
  milkTypes: ProductCategory[];
  locale: string;
};

/** The results page for the visitor's location — the target of the type chips
 * and "Show map", where `?type=` filtering actually lives (D23). */
function resultsBase(data: HomeData): string {
  const loc = data.home?.location;
  if (!loc) return "/search";
  return `/${loc.district.toLowerCase().replace(/\s+/g, "-")}/${loc.pincode}`;
}

/** §5c type chips + §5b price ticker. */
export async function HomeFilters({ data, milkTypes }: Omit<Props, "locale">) {
  const resolved = await data;
  if (!resolved.home) return null;
  return (
    <>
      <MilkTypeChips
        filters={resolved.home.filters}
        milkTypes={milkTypes}
        base={resultsBase(resolved)}
      />
      <PriceTicker home={resolved.home} milkTypes={milkTypes} />
    </>
  );
}

export function HomeFiltersSkeleton() {
  return (
    <>
      <div className="mt-3 flex gap-[9px] overflow-hidden">
        {[0, 1, 2, 3, 4, 5].map((i) => (
          <Skeleton key={i} width="86px" height="74px" className="shrink-0 rounded-card" />
        ))}
      </div>
      <Skeleton width="100%" height="35px" className="mt-3 rounded-pill" />
    </>
  );
}

/**
 * §8 vendors (+ §8a2 house band) and §8f brands.
 *
 * M3.B sponsored listings are injected here at the RENDER layer, exactly as
 * the `/{city}/{pincode}` results page does it: `fetchSponsoredListings`
 * forwards the viewer's IP and user-agent so frequency caps survive the
 * server hop, and `injectSponsored` splices the ads into the rendered flow
 * without reordering, filtering or re-counting the organic array. Positions
 * and caps are the engine's — nothing here decides them.
 *
 * This is server-side, not a client island, because the home now renders
 * per-request (it reads the visitor's location cookie), so there is no ISR
 * window that could cache one advertiser's card for everyone. The cards land
 * in the SSR HTML, which is also why they cost zero CLS.
 */
export async function HomeVendors({ data, milkTypes, locale }: Props) {
  const resolved = await data;
  const t = await getTranslations("ui.home.vendors");
  const pincode = resolved.home?.location?.pincode ?? "";
  const recommendedIds = new Set((resolved.home?.recommended ?? []).map((c) => c.id));
  // Ads must never break a list page: this degrades to no ads on any failure.
  const sponsored = await fetchSponsoredListings({ pincode, locale });
  const entries = injectSponsored(resolved.home?.vendors ?? [], sponsored);
  return (
    <>
      <section className="pb-2 pt-[22px]" id="shops">
        <div className="mb-3.5 flex items-baseline justify-between gap-2.5">
          <h2 className="font-display text-xl font-extrabold">{t("title")}</h2>
          <Link
            href={resultsBase(resolved)}
            prefetch={false}
            // `.tap-target`: same §1.5 treatment as Section's see-link — a
            // 13px heading-row link is ~20px tall, under the 44px floor.
            className="tap-target text-[13px] font-bold text-brand-deep no-underline"
          >
            {t("showMap")}
          </Link>
        </div>
        <VendorGrid
          entries={entries}
          ratings={resolved.ratings}
          recommendedIds={recommendedIds}
          milkTypes={milkTypes}
          pincode={pincode}
        />
        <AdvertiseBand />
      </section>
      <BrandsAvailable
        brands={resolved.home?.brands ?? []}
        milkTypes={milkTypes}
        pincode={pincode}
      />
    </>
  );
}

export function HomeVendorsSkeleton() {
  return (
    <section className="pb-2 pt-[22px]">
      <Skeleton width="220px" height="26px" className="mb-3.5" />
      <div className="grid gap-2.5 md:grid-cols-2 lg:grid-cols-3">
        {[0, 1, 2, 3, 4, 5].map((i) => (
          <Skeleton key={i} width="100%" height="186px" className="rounded-card" />
        ))}
      </div>
      <Skeleton width="100%" height="62px" className="mt-2.5 rounded-card" />
    </section>
  );
}

/** §8b stats, §8d reviews, §8e popular-near-you, §9 CTA tiles. */
export async function HomeEngagementBlock({ data, locale }: Omit<Props, "milkTypes">) {
  const resolved = await data;
  return (
    <>
      <StatsBand stats={homeStats(resolved)} />
      <ReviewsStrip reviews={resolved.reviews} locale={locale} />
      <PopularNearYou covered={resolved.coveredPincodes} />
      <HomeCtaTiles pincode={resolved.home?.location?.pincode ?? ""} />
    </>
  );
}

export function HomeEngagementSkeleton() {
  return (
    <>
      <Skeleton width="100%" height="86px" className="mt-5 rounded-card" />
      <div className="pb-2 pt-[22px]">
        <Skeleton width="180px" height="26px" className="mb-3.5" />
        <div className="grid gap-2.5 md:grid-cols-3">
          {[0, 1, 2].map((i) => (
            <Skeleton key={i} width="100%" height="104px" className="rounded-card" />
          ))}
        </div>
      </div>
      <Skeleton width="100%" height="150px" className="mt-5 rounded-card" />
    </>
  );
}
