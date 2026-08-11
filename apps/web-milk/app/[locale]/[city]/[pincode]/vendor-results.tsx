"use client";

import { Button, injectSponsored, type ListEntry, type ServedAd, SponsoredListingCard } from "@agri/ui";
import { useTranslations } from "next-intl";
import dynamic from "next/dynamic";
import { useRef, useState } from "react";

import { MilkVendorCard } from "@/components/organisms/MilkVendorCard";
import type { RatingSummary } from "@/lib/home";
import type { MilkCard } from "@/lib/milk";

import type { MapPin } from "./vendor-map";

// MapLibre is ~200KB of client JS: dynamic + ssr:false keeps it entirely out
// of the SSR/ISR payload; it only loads when the user opens the map
// (Lighthouse ≥90 on this audited page — NON-NEGOTIABLE 4 guard).
const VendorMap = dynamic(() => import("./vendor-map"), { ssr: false });

/**
 * The results grids + the D24.D map↔list sync island. Cards render through
 * the SAME `MilkVendorCard` binding as the home vendor grid — the island only
 * owns the selection state and the map toggle.
 */
export function VendorResults({
  vendors,
  brands,
  pincode,
  sponsored = [],
  ratings = {},
  typeLabels = {},
}: {
  vendors: MilkCard[];
  brands: MilkCard[];
  pincode: string;
  /** M3.B sponsored listings, injected at the render layer into the FIRST
   * non-empty section only (page positions 1 and 6). The organic arrays -
   * and the JSON-LD/cursor built from them upstream - are never touched. */
  sponsored?: ServedAd[];
  /** D18 `/reviews/summary` aggregates, business id → rating + count — the
   * same signals the home grid renders. */
  ratings?: Record<string, RatingSummary>;
  /** milk_type value → localised D17 `option_meta` label. */
  typeLabels?: Record<string, string>;
}) {
  const t = useTranslations("ui.results");
  const tVendors = useTranslations("ui.home.vendors");
  const tActions = useTranslations("ui.actions");
  const tBadges = useTranslations("ui.badges");
  const [showMap, setShowMap] = useState(false);
  const [selectedId, setSelectedId] = useState<string | null>(null);
  const listRef = useRef<HTMLDivElement | null>(null);

  const labels = {
    verified: tVendors("verified"),
    recommended: tVendors("recommended"),
    call: tActions("call"),
    whatsapp: tActions("whatsapp"),
  };

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
        <div className="grid gap-2.5 md:grid-cols-2 lg:grid-cols-3">
          {entries.map((entry) =>
            entry.kind === "sponsored" ? (
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
                typeLabels={typeLabels}
                pincode={pincode}
                labels={labels}
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
    <div ref={listRef} className="flex flex-col gap-5" data-testid="vendor-results">
      {pins.length > 0 ? (
        <div>
          <Button
            variant="ghost"
            data-testid="map-toggle"
            className="max-w-[200px]"
            aria-expanded={showMap}
            onClick={() => setShowMap((v) => !v)}
          >
            {showMap ? t("hideMap") : t("showMap")}
          </Button>
          {showMap ? (
            <div className="mt-3">
              <VendorMap cards={pins} selectedId={selectedId} onSelect={selectFromMap} />
            </div>
          ) : null}
        </div>
      ) : null}
      {renderSection(t("localVendors"), vendors, primary === "vendors")}
      {renderSection(t("brandsNearby"), brands, primary === "brands")}
    </div>
  );
}
