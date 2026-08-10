import { Badge, Card, RatingStars, cn } from "@agri/ui";
import { getTranslations } from "next-intl/server";

import { Link } from "@/i18n/navigation";
import type { RatingSummary } from "@/lib/home";
import type { MilkCard } from "@/lib/milk";
import type { ProductCategory } from "@/lib/taxonomy";

/**
 * §8/§24 — the rich vendor card. Every field the current build renders is
 * preserved (verified pill, name, distance, per-type prices, Call/WhatsApp)
 * and the reference's additions are wired to real sources:
 *   · rating WITH review count → D18 `/reviews/summary` aggregate
 *   · Recommended badge        → the M3.C `recommended` array, the ONLY label
 *                                source; paid signals never enter it
 *   · per-type price line      → products[].price_display + the schema's
 *                                localised milk_type label
 *
 * Contact numbers are never in list payloads: Call/WhatsApp link to the
 * profile, where D18's capped, fail-closed reveal flow lives. That gate is
 * untouched — logged-out visitors still meet "Login to view contact" there.
 */
function VendorCard({
  card,
  rating,
  recommended,
  typeLabels,
  pincode,
  labels,
}: {
  card: MilkCard;
  rating?: RatingSummary;
  recommended: boolean;
  typeLabels: Map<string, string>;
  pincode: string;
  labels: { verified: string; recommended: string; call: string; whatsapp: string };
}) {
  const km = (card.distance_m / 1000).toFixed(1);
  const priced = card.products.filter((p) => p.price_display);
  // ?pin= carries the browsing pincode to the D26 profile-view beacon.
  const href = `/directory/businesses/${card.slug}?pin=${pincode}`;

  return (
    <Card
      hover
      data-testid={`home-vendor-${card.slug}`}
      className="flex flex-col gap-1.5 border-cream-line p-4"
    >
      <div className="flex flex-wrap items-center gap-1.5">
        {card.verification_status === "verified" ? (
          <Badge variant="verified">{labels.verified}</Badge>
        ) : null}
        {recommended ? <Badge variant="cert">{labels.recommended}</Badge> : null}
      </div>
      <h3 className="text-[15.5px] font-extrabold leading-[1.3] text-ink">{card.name}</h3>
      <p className="flex flex-wrap items-center gap-1.5 text-[12.5px] text-muted">
        {rating?.rating_avg ? (
          <>
            <RatingStars value={rating.rating_avg} />
            <span>({rating.rating_count})</span>
            <span aria-hidden="true">·</span>
          </>
        ) : null}
        <span>{km} km</span>
      </p>
      {priced.length > 0 ? (
        <p className="text-[13px] text-ink">
          {priced.map((product, index) => (
            <span key={`${product.milk_type}-${index}`}>
              {index > 0 ? <span aria-hidden="true"> · </span> : null}
              {/* `price_display` is free text that already carries its own
                  unit ("₹55/L", "₹340/500ml"), so the pack size is NOT
                  appended — doing so rendered "₹340/500ml 500ml". */}
              <b className="font-semibold">{product.price_display}</b>{" "}
              <span className="text-muted">
                {product.milk_type ? (typeLabels.get(product.milk_type) ?? product.milk_type) : ""}
              </span>
            </span>
          ))}
        </p>
      ) : null}
      <div className="mt-1 flex gap-2">
        <Link
          href={href}
          className="flex min-h-[40px] flex-1 items-center justify-center rounded-btn bg-call text-[12.5px] font-bold text-white no-underline"
        >
          {labels.call}
        </Link>
        <Link
          href={href}
          className="flex min-h-[40px] flex-1 items-center justify-center rounded-btn border border-wa-line bg-wa-soft text-[12.5px] font-bold text-wa-deep no-underline"
        >
          {labels.whatsapp}
        </Link>
      </div>
    </Card>
  );
}

export async function VendorGrid({
  cards,
  ratings,
  recommendedIds,
  milkTypes,
  pincode,
  className,
}: {
  cards: MilkCard[];
  ratings: Record<string, RatingSummary>;
  recommendedIds: Set<string>;
  milkTypes: ProductCategory[];
  pincode: string;
  className?: string;
}) {
  const [t, tActions] = await Promise.all([
    getTranslations("ui.home.vendors"),
    getTranslations("ui.actions"),
  ]);
  const typeLabels = new Map(milkTypes.map((m) => [m.value, m.label]));
  const labels = {
    verified: t("verified"),
    recommended: t("recommended"),
    call: tActions("call"),
    whatsapp: tActions("whatsapp"),
  };

  if (cards.length === 0) {
    return (
      <p className={cn("rounded-card border border-cream-line bg-card p-4 text-sm text-sub", className)}>
        {t("empty", { pincode })}
      </p>
    );
  }
  return (
    <div className={cn("grid gap-2.5 md:grid-cols-2 lg:grid-cols-3", className)}>
      {cards.map((card) => (
        <VendorCard
          key={card.id}
          card={card}
          {...(ratings[card.id] ? { rating: ratings[card.id] } : {})}
          recommended={recommendedIds.has(card.id)}
          typeLabels={typeLabels}
          pincode={pincode}
          labels={labels}
        />
      ))}
    </div>
  );
}
