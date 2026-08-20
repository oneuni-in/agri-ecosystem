/**
 * Guest view-beacon relay (D26 analytics-lite): browser -> same-origin
 * /api/view -> public FastAPI beacon. Deliberately NO auth and NO token -
 * profile views are mostly anonymous. Always 204: a lost view must never
 * surface as a user-visible error.
 *
 * Forwards the visitor's identity so the backend's viewer_hash varies per
 * visitor instead of collapsing every request to the Next server's own IP/UA
 * (see modules/directory/router.py::record_profile_view). The address comes
 * from lib/client-ip, NOT from the inbound x-forwarded-for: page JavaScript
 * can set that header on a same-origin fetch, and forwarding it let a caller
 * choose its own rate-limit key and mint unlimited viewer pseudonyms.
 */
import type { NextRequest } from "next/server";
import { NextResponse } from "next/server";

import { forwardedClientIp } from "@/lib/client-ip";

const API = process.env.API_BASE_URL ?? "http://127.0.0.1:8000";
const SLUG_RE = /^[a-z0-9]+(?:-[a-z0-9]+)*$/;
const PINCODE_RE = /^\d{6}$/;

export async function POST(req: NextRequest): Promise<NextResponse> {
  const body = (await req.json().catch(() => null)) as {
    slug?: unknown;
    pincode?: unknown;
  } | null;
  const slug = typeof body?.slug === "string" ? body.slug : "";
  if (!SLUG_RE.test(slug)) return new NextResponse(null, { status: 204 });
  const pincode =
    typeof body?.pincode === "string" && PINCODE_RE.test(body.pincode)
      ? body.pincode
      : undefined;
  const headers: Record<string, string> = { "content-type": "application/json" };
  const clientIp = forwardedClientIp(req.headers);
  if (clientIp) headers["x-forwarded-for"] = clientIp;
  const userAgent = req.headers.get("user-agent");
  if (userAgent) headers["user-agent"] = userAgent;
  try {
    await fetch(`${API}/directory/businesses/${encodeURIComponent(slug)}/view`, {
      method: "POST",
      headers,
      body: JSON.stringify(pincode ? { pincode } : {}),
      cache: "no-store",
    });
  } catch {
    // fire-and-forget by contract
  }
  return new NextResponse(null, { status: 204 });
}
