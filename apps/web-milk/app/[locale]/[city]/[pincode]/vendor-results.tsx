"use client";

import { Button, injectSponsored, type ListEntry, type ServedAd, SponsoredListingCard } from "@agri/ui";
import dynamic from "next/dynamic";
import { useRef, useState } from "react";

import type { MilkCard } from "@/lib/milk";

import { VendorCard } from "./vendor-card";
import type { MapPin } from "./vendor-map";

// MapLibre is ~200KB of client JS: dynamic + ssr:false keeps it entirely out
// of the SSR/ISR payload; it only loads when the user opens the map
// (Lighthouse ≥90 on this audited page — NON-NEGOTIABLE 4 guard).
const VendorMap = dynamic(() => import("./vendor-map"), { ssr: false });

export function VendorResults({
  vendors,
  brands,
  pincode,
  sponsored = [],
}: {
  vendors: MilkCard[];
  brands: MilkCard[];
  pincode: string;
  /** M3.B sponsored listings, injected at the render layer into the FIRST
   * non-empty section only (page positions 1 and 6). The organic arrays -
   * and the JSON-LD/cursor built from them upstream - are never touched. */
  sponsored?: ServedAd[];
}) {
  const [showMap, setShowMap] = useState(false);
  const [selectedId, setSelectedId] = useState<string | null>(null);
  const listRef = useRef<HTMLDivElement | null>(null);

  const pins: MapPin[] = [...vendors, ...brands]
    .filter((c) => c.lat !== null && c.lng !== null)
    .map((c) => ({ id: c.id, slug: c.slug, name: c.name, lat: c.lat as number, lng: c.lng as number }));

  const selectFromMap = (id: string) => {
    setSelectedId(id);
    listRef.current
      ?.querySelector(`[data-card-id="${id}"]`)
      ?.scrollIntoView({ behavior: "smooth", block: "nearest" });
  };

  const primary: "vendors" | "brands" = vendors.length > 0 ? "vendors" : "brands";

  const renderSection = (title: string, cards: MilkCard[], withSponsored: boolean) => {
    if (cards.length === 0) return null;
    const entries: ListEntry<MilkCard>[] = withSponsored
      ? injectSponsored(cards, sponsored)
      : cards.map((item) => ({ kind: "organic" as const, item }));
    return (
      <section className="flex flex-col gap-2.5">
        <h2 className="font-display text-[16px] font-extrabold text-ink">{title}</h2>
        <div className="grid gap-3 sm:grid-cols-2">
          {entries.map((entry) =>
            entry.kind === "sponsored" ? (
              <SponsoredListingCard key={`s-${entry.ad.placement_id}`} ad={entry.ad} />
            ) : (
              <VendorCard
                key={entry.item.id}
                card={entry.item}
                pincode={pincode}
                selected={selectedId === entry.item.id}
                onSelect={setSelectedId}
              />
            ),
          )}
        </div>
      </section>
    );
  };

  return (
    <div ref={listRef} className="flex flex-col gap-5">
      {pins.length > 0 ? (
        <div>
          <Button
            variant="ghost"
            data-testid="map-toggle"
            className="max-w-[200px]"
            aria-expanded={showMap}
            onClick={() => setShowMap((v) => !v)}
          >
            {showMap ? "Hide map" : "🗺 Show map"}
          </Button>
          {showMap ? (
            <div className="mt-3">
              <VendorMap cards={pins} selectedId={selectedId} onSelect={selectFromMap} />
            </div>
          ) : null}
        </div>
      ) : null}
      {renderSection("Local vendors", vendors, primary === "vendors")}
      {renderSection("Brands & shops nearby", brands, primary === "brands")}
    </div>
  );
}
