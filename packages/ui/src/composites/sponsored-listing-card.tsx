"use client";

/**
 * M3.B sponsored listing: a labeled vendor/brand-style card injected into
 * result lists at the RENDER layer (never the cursor stream). Contracts:
 * - SponsoredBadge always (NN4; ServedAd.label is type-narrowed upstream)
 * - impression beacon at >=50% viewport visibility, never on mount (M2 NN2)
 * - click beacon on click
 * - the word "Recommended" must never render here - that label belongs to
 *   the organic ranking fn alone (M3.C)
 * - no contact data on the wire: the card links to a target page where
 *   D18's reveal caps govern contact actions, sponsored or not.
 */
import { ListingCard } from "../components/listing-card";
import { SponsoredBadge } from "../components/sponsored-badge";
import { cn } from "../lib/cn";
import type { ServedAd } from "../lib/sponsored";
import { sendAdBeacon, useImpression } from "./ad-slot";

export function SponsoredListingCard({
  ad,
  endpoint = "/api/ads",
  className,
  sponsoredLabel,
}: {
  ad: ServedAd;
  endpoint?: string;
  className?: string;
  /** Translated wording for the always-on badge. The badge itself is never
   * optional — this only decides which language it is written in. */
  sponsoredLabel?: string;
}) {
  const ref = useImpression(ad, endpoint);
  return (
    <a
      ref={ref}
      href={ad.target_url}
      rel="nofollow sponsored"
      onClick={() => sendAdBeacon(`${endpoint}/clicks`, ad)}
      className={cn("block h-full no-underline", className)}
      data-testid={`sponsored-listing-${ad.placement_id}`}
    >
      <ListingCard
        badge={<SponsoredBadge {...(sponsoredLabel ? { label: sponsoredLabel } : {})} />}
        icon="📢"
        tint="gold"
        title={ad.title}
        meta={ad.body}
        className="h-full"
      />
    </a>
  );
}
