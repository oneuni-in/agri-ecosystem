import { parseServeResponse, type ServedAd, serveQuery } from "@agri/ui";
import { headers } from "next/headers";

import { forwardedClientIp } from "@/lib/client-ip";

const API = process.env.API_BASE_URL ?? "http://127.0.0.1:8000";

/** A-U1 §4 — the D21 hero slot, config-registered and house-seeded. */
export const HOME_HERO_SLOT = "agri_home_hero_xl";

/**
 * Server-side serve for ANY slot (ported from web-milk's `lib/ads.ts`), so a
 * slot above the fold renders its creative in the SSR HTML instead of
 * waiting on a client fetch — milk measured 2372ms of LCP load delay on the
 * client-fetched hero before this pattern landed.
 *
 * Client identity survives the server hop via lib/client-ip + user-agent —
 * never the inbound x-forwarded-for, which page JavaScript can set on a
 * same-origin fetch. /ads/serve is a SecureRouter route, so this address is
 * its rate-limit bucket; the viewer_hash itself is still derived from the
 * socket address in modules/ads/router.py::_viewer, a separate open
 * question. Without a declared edge there is no address to send and every
 * server render shares one bucket. Any failure degrades to no ads: a page
 * must never break because ads did.
 */
export async function serveAds(
  slotKey: string,
  ctx: { pincode?: string | null; category?: string | null; locale?: string },
  count: number,
): Promise<ServedAd[]> {
  try {
    const h = await headers();
    const fwd: Record<string, string> = { "user-agent": h.get("user-agent") ?? "" };
    const clientIp = forwardedClientIp(h);
    if (clientIp) fwd["x-forwarded-for"] = clientIp;
    const res = await fetch(`${API}/ads/serve?${serveQuery(slotKey, { ...ctx, count })}`, {
      cache: "no-store",
      headers: fwd,
    });
    if (!res.ok) return [];
    return parseServeResponse(await res.json());
  } catch {
    return [];
  }
}
