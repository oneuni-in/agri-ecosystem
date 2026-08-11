import { getTranslations } from "next-intl/server";

import { MilkVendorCard } from "@/components/organisms/MilkVendorCard";
import type { RatingSummary } from "@/lib/home";
import type { MilkCard } from "@/lib/milk";

/** M3.C organic-only rail. Data source: MilkHomeOut.recommended, populated
 * exclusively by modules/directory/recommended.py's ranking fn (verified +
 * rating + response-time + coverage freshness) - paid units render through
 * SponsoredListingCard and can never reach this component, so paid can never
 * buy the "Recommended" label. Cards render through the SAME shared
 * `MilkVendorCard` binding as every other vendor grid. */
export async function RecommendedRail({
  cards,
  pincode,
  ratings = {},
  typeLabels = {},
}: {
  cards: MilkCard[];
  pincode: string;
  ratings?: Record<string, RatingSummary>;
  typeLabels?: Record<string, string>;
}) {
  if (cards.length === 0) return null;
  const [t, tVendors, tActions] = await Promise.all([
    getTranslations("ui.recommended"),
    getTranslations("ui.home.vendors"),
    getTranslations("ui.actions"),
  ]);
  const labels = {
    verified: tVendors("verified"),
    recommended: tVendors("recommended"),
    call: tActions("call"),
    whatsapp: tActions("whatsapp"),
  };
  return (
    <section className="flex flex-col gap-2.5" data-testid="recommended-rail">
      <h2 className="font-display text-[16px] font-extrabold text-ink">⭐ {t("heading")}</h2>
      <div className="grid gap-2.5 md:grid-cols-2 lg:grid-cols-3">
        {cards.map((c) => (
          <MilkVendorCard
            key={c.id}
            card={c}
            {...(ratings[c.id] ? { rating: ratings[c.id] } : {})}
            typeLabels={typeLabels}
            pincode={pincode}
            labels={labels}
          />
        ))}
      </div>
    </section>
  );
}
