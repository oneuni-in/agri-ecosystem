import { Badge, cn, RatingStars, VendorCard as VendorCardShell } from "@agri/ui";

import { Link } from "@/i18n/navigation";
import type { RatingSummary } from "@/lib/home";
import type { MilkCard } from "@/lib/milk";

/** The label strings a card renders — resolved by the SERVER (getTranslations
 * or useTranslations at the call site), passed down so this one binding works
 * inside server components (home VendorGrid, Recommended rail) and client
 * islands (the results map↔list sync) alike. */
export interface MilkVendorCardLabels {
  verified: string;
  recommended: string;
  call: string;
  whatsapp: string;
}

/**
 * §8/§24 — THE binding of the catalog `VendorCard` shell to the `covers()`
 * blend. One component, every surface: the home grid, the pincode results
 * grid and the Recommended rail all render this, so the frame, the rating
 * row and the 44px action pair cannot drift between pages.
 *
 *   · rating WITH review count → D18 `/reviews/summary` aggregate
 *   · Recommended badge        → the M3.C `recommended` array, the ONLY label
 *                                source; paid signals never enter it
 *   · per-type price line      → products[].price_display + the schema's
 *                                localised milk_type label
 *
 * Contact numbers are never in list payloads: Call/WhatsApp link to the
 * profile, where D18's capped, fail-closed reveal flow lives.
 *
 * `selected`/`onSelect` are the D24.D map↔list sync — only the results
 * client island passes them; everywhere else the card is inert. Everything
 * here is serialisable (Records, not Maps) so a server page can hand the
 * props straight to that island.
 */
export function MilkVendorCard({
  card,
  rating,
  recommended = false,
  typeLabels,
  pincode,
  labels,
  testIdPrefix = "vendor-card",
  selected = false,
  onSelect,
  className,
}: {
  card: MilkCard;
  rating?: RatingSummary;
  recommended?: boolean;
  /** milk_type value → localised D17 `option_meta` label. */
  typeLabels: Record<string, string>;
  pincode: string;
  labels: MilkVendorCardLabels;
  testIdPrefix?: string;
  selected?: boolean;
  onSelect?: (id: string) => void;
  className?: string;
}) {
  const km = (card.distance_m / 1000).toFixed(1);
  const priced = card.products.filter((p) => p.price_display);
  // ?pin= carries the browsing pincode to the D26 profile-view beacon.
  const href = `/directory/businesses/${card.slug}?pin=${pincode}`;

  return (
    <VendorCardShell
      data-testid={`${testIdPrefix}-${card.slug}`}
      data-card-id={card.id}
      data-selected={selected}
      // Click selects the card on the map (island surfaces only). The card is
      // NOT exposed as a control: role="button" around the Call/WhatsApp links
      // is an axe nested-interactive (D29) — the links stay the only controls.
      onClick={onSelect ? () => onSelect(card.id) : undefined}
      className={cn(
        selected && "outline outline-[3px] outline-accent outline-offset-2",
        className,
      )}
      name={card.name}
      badges={
        card.verification_status === "verified" || recommended ? (
          <>
            {card.verification_status === "verified" ? (
              <Badge variant="verified">{labels.verified}</Badge>
            ) : null}
            {recommended ? <Badge variant="cert">{labels.recommended}</Badge> : null}
          </>
        ) : undefined
      }
      meta={
        <>
          {rating?.rating_avg ? (
            <>
              <RatingStars value={rating.rating_avg} />
              <span>({rating.rating_count})</span>
              <span aria-hidden="true">·</span>
            </>
          ) : null}
          <span>{km} km</span>
        </>
      }
      {...(priced.length > 0
        ? {
            prices: priced.map((product, index) => (
              <span key={`${product.milk_type}-${index}`}>
                {index > 0 ? <span aria-hidden="true"> · </span> : null}
                {/* `price_display` is free text that already carries its own
                    unit ("₹55/L", "₹340/500ml"), so the pack size is NOT
                    appended — doing so rendered "₹340/500ml 500ml". */}
                <b className="font-semibold">{product.price_display}</b>{" "}
                <span className="text-muted">
                  {product.milk_type
                    ? (typeLabels[product.milk_type] ?? product.milk_type)
                    : ""}
                </span>
              </span>
            )),
          }
        : {})}
      actions={
        <>
          <Link
            href={href}
            className="flex min-h-[44px] flex-1 items-center justify-center rounded-btn bg-call text-[12.5px] font-bold text-white no-underline"
            onClick={onSelect ? (event) => event.stopPropagation() : undefined}
          >
            {labels.call}
          </Link>
          <Link
            href={href}
            className="flex min-h-[44px] flex-1 items-center justify-center rounded-btn border border-wa-line bg-wa-soft text-[12.5px] font-bold text-wa-deep no-underline"
            onClick={onSelect ? (event) => event.stopPropagation() : undefined}
          >
            {labels.whatsapp}
          </Link>
        </>
      }
    />
  );
}
