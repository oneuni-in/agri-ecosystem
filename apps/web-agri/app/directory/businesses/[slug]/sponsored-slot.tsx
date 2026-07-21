"use client";

/**
 * The ONE live ad slot (D21). Inventory key "directory_browse" - mounted on
 * the business page (the public directory surface v1). Renders NOTHING when
 * the flag is off (serve 404s), no ad is eligible, or the payload fails the
 * parseServedAd guard (unlabeled/unsafe payloads are dropped, not "fixed").
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

export function SponsoredSlot() {
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
    <SponsoredAd
      ad={ad}
      onImpression={() => beacon("impressions", ad)}
      onClick={() => beacon("clicks", ad)}
    />
  );
}
