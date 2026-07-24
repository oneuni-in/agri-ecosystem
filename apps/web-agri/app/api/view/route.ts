/**
 * Guest view-beacon relay (D26 analytics-lite): browser -> same-origin
 * /api/view -> public FastAPI beacon. Deliberately NO auth and NO token -
 * profile views are mostly anonymous. Always 204: a lost view must never
 * surface as a user-visible error.
 *
 * Forwards the real client identity (x-forwarded-for, user-agent) so the
 * backend's viewer_hash varies per visitor instead of collapsing every
 * request to the Next server's own IP/UA (final-review fix - see
 * modules/directory/router.py::record_profile_view on the backend side).
 */
import type { NextRequest } from "next/server";
import { NextResponse } from "next/server";

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
  const forwardedFor = req.headers.get("x-forwarded-for");
  if (forwardedFor) headers["x-forwarded-for"] = forwardedFor;
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
