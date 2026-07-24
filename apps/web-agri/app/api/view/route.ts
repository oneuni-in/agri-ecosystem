/**
 * Guest view-beacon relay (D26 analytics-lite): browser -> same-origin
 * /api/view -> public FastAPI beacon. Deliberately NO auth and NO token -
 * profile views are mostly anonymous. Always 204: a lost view must never
 * surface as a user-visible error.
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
  try {
    await fetch(`${API}/directory/businesses/${encodeURIComponent(slug)}/view`, {
      method: "POST",
      headers: { "content-type": "application/json" },
      body: JSON.stringify(pincode ? { pincode } : {}),
      cache: "no-store",
    });
  } catch {
    // fire-and-forget by contract
  }
  return new NextResponse(null, { status: 204 });
}
