import { Badge, buttonVariants, Card, cn } from "@agri/ui";

import { milkTypeMeta, type MilkCard } from "@/lib/milk";

/**
 * ListingCard anatomy (design-system.md §2, `.card.lc`): badge row → title +
 * meta → optional price-tag → Call/WA action row. Call/WA lead every vendor
 * card, forms never do (UX law 4) — but D23 has no reveal/tracked-contact
 * flow yet (that's D24), so the actions render as plain, non-focusable
 * `<span>`s sharing the exact `.abtn` recipe (`buttonVariants`) rather than a
 * real `<button>`/`<a>` that would silently do nothing on tap.
 *
 * `MilkCard` carries no rating, so the meta line is `distance away` only —
 * the `★ rating ·` segment from the mockup's generic ListingCard doesn't
 * apply here.
 */
export function VendorCard({ card }: { card: MilkCard }) {
  const km = (card.distance_m / 1000).toFixed(1);
  const priceLine = card.products
    .filter((p) => p.price_display)
    .map((p) => `${p.price_display} ${milkTypeMeta(p.milk_type ?? "").en}`.trim())
    .join(" · ");

  return (
    <Card className="flex flex-col gap-1.5 p-4">
      {card.verification_status === "verified" ? (
        <Badge variant="verified">✔ Verified</Badge>
      ) : null}
      <h3 className="text-[15.5px] font-extrabold leading-[1.3] text-ink">{card.name}</h3>
      <p className="text-[12.5px] text-sub">{km} km away</p>
      {priceLine ? <p className="text-[15px] font-extrabold text-ink">{priceLine}</p> : null}
      <div className="mt-1 flex gap-2">
        <span className={cn(buttonVariants({ variant: "call" }), "cursor-default")}>
          📞 Call
        </span>
        <span className={cn(buttonVariants({ variant: "wa" }), "cursor-default")}>WhatsApp</span>
      </div>
    </Card>
  );
}
