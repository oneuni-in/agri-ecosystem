import { cn, type ListEntry, SponsoredListingCard } from "@agri/ui";
import { getTranslations } from "next-intl/server";

import type { RatingSummary } from "@/lib/home";
import type { MilkCard } from "@/lib/milk";
import type { ProductCategory } from "@/lib/taxonomy";

import { MilkVendorCard } from "./MilkVendorCard";

/**
 * §8/§24 — the home's vendor grid. Card binding lives in the shared
 * `MilkVendorCard` (the SAME component the pincode results page renders);
 * this organism only resolves the labels server-side and lays out the grid.
 */
export async function VendorGrid({
  entries,
  ratings,
  recommendedIds,
  milkTypes,
  pincode,
  className,
}: {
  /** Organic cards with M3.B sponsored entries already spliced in by
   * `injectSponsored` — the render-layer flow, never a re-ordered list. */
  entries: ListEntry<MilkCard>[];
  ratings: Record<string, RatingSummary>;
  recommendedIds: Set<string>;
  milkTypes: ProductCategory[];
  pincode: string;
  className?: string;
}) {
  const [t, tActions, tBadges] = await Promise.all([
    getTranslations("ui.home.vendors"),
    getTranslations("ui.actions"),
    getTranslations("ui.badges"),
  ]);
  const typeLabels = Object.fromEntries(milkTypes.map((m) => [m.value, m.label]));
  const labels = {
    verified: t("verified"),
    recommended: t("recommended"),
    call: tActions("call"),
    whatsapp: tActions("whatsapp"),
  };

  if (entries.length === 0) {
    return (
      <p className={cn("rounded-card border border-cream-line bg-card p-4 text-sm text-sub", className)}>
        {t("empty", { pincode })}
      </p>
    );
  }
  return (
    <div className={cn("grid gap-2.5 md:grid-cols-2 lg:grid-cols-3", className)}>
      {entries.map((entry) =>
        entry.kind === "sponsored" ? (
          // §8: a paid card is a 2px golden border plus the floating badge the
          // component already enforces. Placement and caps come from M3 —
          // nothing here decides where it lands.
          <SponsoredListingCard
            key={`s-${entry.ad.placement_id}`}
            ad={entry.ad}
            sponsoredLabel={tBadges("sponsored")}
            className="rounded-card border-2 border-ad-border"
          />
        ) : (
          <MilkVendorCard
            key={entry.item.id}
            card={entry.item}
            {...(ratings[entry.item.id] ? { rating: ratings[entry.item.id] } : {})}
            recommended={recommendedIds.has(entry.item.id)}
            typeLabels={typeLabels}
            pincode={pincode}
            labels={labels}
            testIdPrefix="home-vendor"
          />
        ),
      )}
    </div>
  );
}
