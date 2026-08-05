/**
 * BFF proxy: browser -> same-origin /api/billing/* -> FastAPI /billing/*
 * with the session's bearer token attached HERE, server-side (tokens never
 * touch JS - D10 non-negotiable). Auth-required (unlike /api/leads): no
 * session -> 401 without touching the backend. The backend's flag gate
 * still applies - while billing_enabled is off every proxied call 404s.
 * Only user-facing surfaces are forwardable: an allowlist on path[0]
 * rejects everything else (webhook, admin/*, ...) with 404 before the
 * bearer token is ever attached.
 */
import type { NextRequest } from "next/server";
import { NextResponse } from "next/server";

import { auth } from "@/lib/auth";

const API = process.env.API_BASE_URL ?? "http://127.0.0.1:8000";

// Only these top-level billing paths are user-facing; everything else
// (webhook/razorpay, admin/*, ...) must never be reachable through the
// browser-authenticated proxy.
const ALLOWED_FIRST_SEGMENTS = new Set(["subscription", "subscriptions", "invoices", "ad-orders"]);

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
  const token = await auth.getAccessToken();
  if (!token) {
    return NextResponse.json({ detail: "authentication required" }, { status: 401 });
  }
  const headers: Record<string, string> = {
    accept: "application/json",
    authorization: `Bearer ${token}`,
  };
  if (method === "POST") headers["content-type"] = "application/json";
  const url = new URL(`${API}/billing/${path.map(encodeURIComponent).join("/")}`);
  url.search = req.nextUrl.search;
  const upstream = await fetch(url, {
    method,
    headers,
    ...(method === "POST" ? { body: await req.text() } : {}),
    cache: "no-store",
  });
  if (upstream.status === 204 || upstream.status === 205 || upstream.status === 304) {
    return new NextResponse(null, { status: upstream.status });
  }
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
