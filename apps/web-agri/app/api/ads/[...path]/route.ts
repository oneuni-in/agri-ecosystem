/**
 * BFF proxy: browser -> same-origin /api/ads/* -> FastAPI /ads/*.
 *
 * serve/impressions/clicks are PUBLIC beacons (anonymous visitors see and
 * report on ads) so no bearer is attached for them - the proxy exists to
 * keep API_BASE_URL server-side and same-origin (D20 billing-proxy
 * precedent). `my` is the M5 self-serve campaign surface (Task 8+): it
 * requires a session, the bearer is attached HERE server-side (tokens never
 * touch JS - D10 non-negotiable), and a missing session 401s before the
 * upstream is ever touched. Allowlist on path[0]: only serve/impressions/
 * clicks/my are reachable; everything else 404s. While ads_enabled is off
 * the backend 404s every call.
 *
 * Request bodies are forwarded as raw bytes with their original
 * content-type (catalog-proxy pattern): Task 8's creative upload
 * (POST/PATCH /ads/my/campaigns/{id}/creatives) is multipart/form-data and
 * the boundary lives in that header - parsing it into text()/formData()
 * here would lose it.
 */
import { LOC_COOKIE, parseLocCookie } from "@agri/ui";
import type { NextRequest } from "next/server";
import { NextResponse } from "next/server";

import { auth } from "@/lib/auth";

const API = process.env.API_BASE_URL ?? "http://127.0.0.1:8000";
// 5 files x 5MiB cap + multipart overhead (catalog-proxy precedent).
const MAX_BODY_BYTES = 30 * 1024 * 1024;

const ALLOWED_FIRST_SEGMENTS = new Set(["serve", "impressions", "clicks", "my"]);

async function forward(
  req: NextRequest,
  params: Promise<{ path: string[] }>,
  method: "GET" | "POST" | "PATCH",
): Promise<NextResponse> {
  const { path } = await params;
  if (path.some((segment) => segment === ".." || segment === "." || segment === "")) {
    return NextResponse.json({ detail: "invalid_path" }, { status: 400 });
  }
  const [firstSegment] = path;
  if (!firstSegment || !ALLOWED_FIRST_SEGMENTS.has(firstSegment)) {
    return NextResponse.json({ detail: "not_found" }, { status: 404 });
  }
  const headers: Record<string, string> = { accept: "application/json" };
  if (firstSegment === "my") {
    const token = await auth.getAccessToken();
    if (!token) return NextResponse.json({ detail: "unauthenticated" }, { status: 401 });
    headers.authorization = `Bearer ${token}`;
  }
  if (method !== "GET") {
    const contentLength = Number(req.headers.get("content-length"));
    if (Number.isFinite(contentLength) && contentLength > MAX_BODY_BYTES) {
      return NextResponse.json({ detail: "payload too large" }, { status: 413 });
    }
    const contentType = req.headers.get("content-type");
    if (contentType) headers["content-type"] = contentType;
  }
  const url = new URL(`${API}/ads/${path.map(encodeURIComponent).join("/")}`);
  url.search = req.nextUrl.search;
  // M3 threat "geo spoofing for cheap-tier arbitrage": for serve, the pincode
  // comes from the location CONTEXT (agri_loc cookie — D19; kept in sync with
  // the profile pincode after login by LiveLocationPill), never a bare
  // client-supplied query param. No cookie -> no pincode (fail closed to
  // global-only inventory). Honest clients already derive the param from this
  // same cookie, so behaviour is unchanged for them. Scoped to serve only -
  // /ads/my/* requests (authenticated self-serve) must never have their
  // query params rewritten.
  if (firstSegment === "serve") {
    const loc = parseLocCookie(req.cookies.get(LOC_COOKIE)?.value);
    if (loc?.pincode) url.searchParams.set("pincode", loc.pincode);
    else url.searchParams.delete("pincode");
  }
  const upstream = await fetch(url, {
    method,
    headers,
    // Raw bytes, not text(): preserves the multipart boundary for creative
    // uploads untouched.
    ...(method !== "GET" ? { body: Buffer.from(await req.arrayBuffer()) } : {}),
    cache: "no-store",
  });
  const body = (await upstream.json().catch(() => ({}))) as Record<string, unknown>;
  return NextResponse.json(body, { status: upstream.status });
}

type Ctx = { params: Promise<{ path: string[] }> };

export async function GET(req: NextRequest, ctx: Ctx): Promise<NextResponse> {
  return forward(req, ctx.params, "GET");
}

export async function POST(req: NextRequest, ctx: Ctx): Promise<NextResponse> {
  return forward(req, ctx.params, "POST");
}

export async function PATCH(req: NextRequest, ctx: Ctx): Promise<NextResponse> {
  return forward(req, ctx.params, "PATCH");
}
