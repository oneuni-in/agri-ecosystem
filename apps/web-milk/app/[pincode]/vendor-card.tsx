"use client";

import { Badge, buttonVariants, Card, cn } from "@agri/ui";
import Link from "next/link";
import type { KeyboardEvent } from "react";

import { milkTypeMeta, type MilkCard } from "@/lib/milk";

/**
 * ListingCard anatomy (design-system.md §2, `.card.lc`): badge row → title +
 * meta → optional price-tag → Call/WA action row. D24 wires the D23
 * placeholder actions: Call/WhatsApp now link to the vendor profile, where
 * the D18 capped reveal flow lives (numbers are NEVER in list payloads).
 *
 * Selection (map↔list sync, D24.D): `selected`/`onSelect` come from the
 * VendorResults island. Container click selects; profile navigation happens
 * only via the explicit action links so a selection tap never navigates.
 */
export function VendorCard({
  card,
  pincode,
  selected = false,
  onSelect,
}: {
  card: MilkCard;
  pincode: string;
  selected?: boolean;
  onSelect?: (id: string) => void;
}) {
  const km = (card.distance_m / 1000).toFixed(1);
  const priceLine = card.products
    .filter((p) => p.price_display)
    .map((p) => `${p.price_display} ${milkTypeMeta(p.milk_type ?? "").en}`.trim())
    .join(" · ");
  // ?pin= carries the browsing pincode to the profile-view beacon (D26) —
  // never in list payloads, just query context for the client island.
  const profileHref = `/directory/businesses/${card.slug}?pin=${pincode}`;

  const handleKeyDown = onSelect
    ? (event: KeyboardEvent<HTMLDivElement>) => {
        if (event.key === "Enter" || event.key === " ") {
          if (event.key === " ") event.preventDefault();
          onSelect(card.id);
        }
      }
    : undefined;

  return (
    <Card
      data-testid={`vendor-card-${card.slug}`}
      data-card-id={card.id}
      data-selected={selected}
      onClick={onSelect ? () => onSelect(card.id) : undefined}
      role={onSelect ? "button" : undefined}
      tabIndex={onSelect ? 0 : undefined}
      onKeyDown={handleKeyDown}
      className={cn(
        "flex flex-col gap-1.5 p-4",
        selected && "outline outline-[3px] outline-accent outline-offset-2",
      )}
    >
      {card.verification_status === "verified" ? (
        <Badge variant="verified">✔ Verified</Badge>
      ) : null}
      <h3 className="text-[15.5px] font-extrabold leading-[1.3] text-ink">{card.name}</h3>
      <p className="text-[12.5px] text-sub">{km} km away</p>
      {priceLine ? <p className="text-[15px] font-extrabold text-ink">{priceLine}</p> : null}
      <div className="mt-1 flex gap-2">
        <Link
          href={profileHref}
          className={cn(buttonVariants({ variant: "call" }), "no-underline")}
          onClick={(event) => event.stopPropagation()}
        >
          📞 Call
        </Link>
        <Link
          href={profileHref}
          className={cn(buttonVariants({ variant: "wa" }), "no-underline")}
          onClick={(event) => event.stopPropagation()}
        >
          WhatsApp
        </Link>
      </div>
    </Card>
  );
}
