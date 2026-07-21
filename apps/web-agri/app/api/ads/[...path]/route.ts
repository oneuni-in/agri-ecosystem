/**
 * BFF proxy: browser -> same-origin /api/ads/* -> FastAPI /ads/*. These are
 * PUBLIC endpoints (anonymous visitors see ads) so no bearer is attached -
 * the proxy exists to keep API_BASE_URL server-side and same-origin (D20
 * billing-proxy precedent). Allowlist on path[0]: only serve/impressions/
 * clicks are reachable; everything else 404s. While ads_enabled is off the
 * backend 404s every call.
 */
import type { NextRequest } from "next/server";
import { NextResponse } from "next/server";

const API = process.env.API_BASE_URL ?? "http://127.0.0.1:8000";

const ALLOWED_FIRST_SEGMENTS = new Set(["serve", "impressions", "clicks"]);

async function forward(
  req: NextRequest,
  params: Promise<{ path: string[] }>,
  method: "GET" | "POST",
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
  if (method === "POST") headers["content-type"] = "application/json";
  const url = new URL(`${API}/ads/${path.map(encodeURIComponent).join("/")}`);
  url.search = req.nextUrl.search;
  const upstream = await fetch(url, {
    method,
    headers,
    ...(method === "POST" ? { body: await req.text() } : {}),
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
