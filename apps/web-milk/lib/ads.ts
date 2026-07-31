import { parseServeResponse, type ServedAd, serveQuery } from "@agri/ui";
import { headers } from "next/headers";

const API = process.env.API_BASE_URL ?? "http://127.0.0.1:8000";

export const SPONSORED_LISTING_SLOT = "milk_sponsored_listing";

/**
 * Server-side sponsored-listing fetch (M3.B): the page injects these at the
 * render layer, so organic payloads/cursors/JSON-LD stay byte-identical and
 * there is zero CLS (cards are in the SSR HTML). Client identity (freq caps,
 * viewer_hash) survives the server hop by forwarding x-forwarded-for +
 * user-agent (D26 relay-forwarding precedent; the backend honours XFF only
 * when trust_forwarded_for is set). Any failure degrades to no ads — a list
 * page must never break because ads did.
 */
export async function fetchSponsoredListings(ctx: {
  pincode?: string | null;
  category?: string | null;
  locale?: string;
}): Promise<ServedAd[]> {
  try {
    const h = await headers();
    const fwd: Record<string, string> = { "user-agent": h.get("user-agent") ?? "" };
    const xff = h.get("x-forwarded-for");
    if (xff) fwd["x-forwarded-for"] = xff;
    const res = await fetch(
      `${API}/ads/serve?${serveQuery(SPONSORED_LISTING_SLOT, { ...ctx, count: 2 })}`,
      { cache: "no-store", headers: fwd },
    );
    if (!res.ok) return [];
    return parseServeResponse(await res.json());
  } catch {
    return [];
  }
}
