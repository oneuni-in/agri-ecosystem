"use client";

/**
 * A-U6 W1 — the reference's `.inline-ad` on the category landing.
 *
 * Reuses the SAME live D21 inventory key as the business profile
 * ("directory_browse", the public directory surface v1) rather than
 * registering a new slot: an inventory key with no campaigns behind it is
 * advertising space that does not exist, and the honest render for that is
 * nothing at all.
 *
 * Renders NOTHING when the flag is off (serve 404s), when no ad is eligible,
 * when the visitor has no location context, or when the payload fails the
 * `parseServedAd` guard — unlabeled or unsafe payloads are dropped, never
 * "fixed". Every served creative carries its Sponsored label, and this sits
 * BELOW the organic list so a paid placement can never reorder it.
 */
import {
  LOC_COOKIE,
  parseLocCookie,
  parseServedAd,
  SponsoredAd,
  type ServedAd,
} from "@agri/ui";
import { useEffect, useState } from "react";

const SLOT = "directory_browse";

function activePincode(): string | null {
  const match = document.cookie.match(new RegExp(`(?:^|; )${LOC_COOKIE}=([^;]*)`));
  if (!match) return null;
  const pincode = parseLocCookie(match[1])?.pincode ?? null;
  return pincode && /^\d{6}$/.test(pincode) ? pincode : null;
}

function beacon(kind: "impressions" | "clicks", ad: ServedAd): void {
  void fetch(`/api/ads/${kind}`, {
    method: "POST",
    headers: { "content-type": "application/json" },
    body: JSON.stringify({
      placement_id: ad.placement_id,
      creative_id: ad.creative_id,
      slot_key: ad.slot_key,
    }),
    keepalive: true,
  }).catch(() => undefined); // tracking must never break the page
}

export function CategoryAdSlot() {
  const [ad, setAd] = useState<ServedAd | null>(null);

  useEffect(() => {
    const pincode = activePincode();
    if (!pincode) return; // no location context -> no geo-targeted serve
    let cancelled = false;
    void fetch(`/api/ads/serve?slot=${SLOT}&pincode=${pincode}`, { cache: "no-store" })
      .then((r) => (r.ok ? r.json() : null))
      .then((body: { ad?: unknown } | null) => {
        if (cancelled || !body) return;
        setAd(parseServedAd(body.ad ?? null));
      })
      .catch(() => undefined);
    return () => {
      cancelled = true;
    };
  }, []);

  if (!ad) return null;
  return (
    <div className="mt-2.5">
      <SponsoredAd
        ad={ad}
        onImpression={() => beacon("impressions", ad)}
        onClick={() => beacon("clicks", ad)}
      />
    </div>
  );
}
