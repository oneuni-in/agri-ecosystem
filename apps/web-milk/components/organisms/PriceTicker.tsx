import { getTranslations } from "next-intl/server";

import type { MilkHome } from "@/lib/milk";
import type { ProductCategory } from "@/lib/taxonomy";

/**
 * §5b live price ticker. Reads the EXISTING D23 price-banner computation —
 * `compute_price_banner()` derives every band from real approved listings in
 * this pincode, so nothing here is authored copy.
 *
 * Type names come from the D17 schema's `option_meta` labels (localised), not
 * from a hardcoded map — at `/ta` the whole strip is Tamil.
 *
 * The lane is duplicated because the marquee translates by -50%: the second
 * copy is what makes the loop seamless. It is `aria-hidden` so screen readers
 * hear the prices once. Motion is CSS-only and the whole animation is off
 * under `prefers-reduced-motion`, where it degrades to a static row.
 */
export async function PriceTicker({
  home,
  milkTypes,
}: {
  home: MilkHome;
  milkTypes: ProductCategory[];
}) {
  const banner = home.price_banner;
  const pincode = home.location?.pincode;
  if (!banner || banner.lines.length === 0 || !pincode) return null;
  const t = await getTranslations("ui.home.ticker");
  const labels = new Map(milkTypes.map((m) => [m.value, m.label]));

  const lane = (
    <>
      <span>{t("today", { pincode })}</span>
      {banner.lines.map((band) => {
        const range = band.low === band.high ? `₹${band.low}` : `₹${band.low}–${band.high}`;
        return (
          <span key={band.milk_type}>
            {labels.get(band.milk_type) ?? band.milk_type}{" "}
            <b className="font-medium text-ink">
              {range}
              {band.unit ? `/${band.unit}` : ""}
            </b>
          </span>
        );
      })}
      <span>
        <b className="font-medium text-ink">
          {t("sellers", { count: banner.seller_count, pincode })}
        </b>
      </span>
    </>
  );

  return (
    <div
      className="relative mt-3 overflow-hidden rounded-pill border border-brand-soft-2 bg-brand-soft"
      aria-label={t("today", { pincode })}
      data-testid="price-ticker"
    >
      <div className="flex w-max gap-[34px] whitespace-nowrap py-2 text-[12px] text-brand-deep [animation:ticker_28s_linear_infinite] hover:[animation-play-state:paused] motion-reduce:[animation:none]">
        {lane}
        <span aria-hidden="true" className="contents">
          {lane}
        </span>
      </div>
    </div>
  );
}
