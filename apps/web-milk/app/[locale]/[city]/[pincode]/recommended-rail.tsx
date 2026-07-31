import { getTranslations } from "next-intl/server";

import type { MilkCard } from "@/lib/milk";

import { VendorCard } from "./vendor-card";

/** M3.C organic-only rail. Data source: MilkHomeOut.recommended, populated
 * exclusively by modules/directory/recommended.py's ranking fn (verified +
 * rating + response-time + coverage freshness) - paid units render through
 * SponsoredListingCard and can never reach this component, so paid can never
 * buy the "Recommended" label. */
export async function RecommendedRail({
  cards,
  pincode,
}: {
  cards: MilkCard[];
  pincode: string;
}) {
  if (cards.length === 0) return null;
  const t = await getTranslations("ui.recommended");
  return (
    <section className="flex flex-col gap-2.5" data-testid="recommended-rail">
      <h2 className="font-display text-[16px] font-extrabold text-ink">⭐ {t("heading")}</h2>
      <div className="grid gap-3 sm:grid-cols-2">
        {cards.map((c) => (
          <VendorCard key={c.id} card={c} pincode={pincode} />
        ))}
      </div>
    </section>
  );
}
