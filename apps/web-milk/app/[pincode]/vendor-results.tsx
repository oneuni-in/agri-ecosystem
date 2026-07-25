"use client";

import { Button } from "@agri/ui";
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
}: {
  vendors: MilkCard[];
  brands: MilkCard[];
  pincode: string;
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

  const renderSection = (title: string, cards: MilkCard[]) =>
    cards.length > 0 ? (
      <section className="flex flex-col gap-2.5">
        <h2 className="font-display text-[16px] font-extrabold text-ink">{title}</h2>
        <div className="grid gap-3 sm:grid-cols-2">
          {cards.map((c) => (
            <VendorCard
              key={c.id}
              card={c}
              pincode={pincode}
              selected={selectedId === c.id}
              onSelect={setSelectedId}
            />
          ))}
        </div>
      </section>
    ) : null;

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
      {renderSection("Local vendors", vendors)}
      {renderSection("Brands & shops nearby", brands)}
    </div>
  );
}
