/**
 * BFF proxy: browser -> same-origin /api/identity/* -> FastAPI /identity/*
 * with the session's bearer token attached HERE, server-side (tokens never
 * touch JS - D10 non-negotiable). Only the backend's /identity prefix is
 * reachable through this route by construction.
 *
 * Unlike the /coins proxy this one is GUEST-CAPABLE: /identity/location is a
 * public endpoint (D19), so an absent token forwards the request WITHOUT an
 * Authorization header instead of short-circuiting with 401 - the backend
 * itself 401s the protected paths (e.g. /identity/profile) on its own.
 */
import type { NextRequest } from "next/server";
import { NextResponse } from "next/server";

import { auth } from "@/lib/auth";

const API = process.env.API_BASE_URL ?? "http://127.0.0.1:8000";

async function forward(
  req: NextRequest,
  params: Promise<{ path: string[] }>,
  method: "GET" | "PATCH",
): Promise<NextResponse> {
  const { path } = await params;
  if (path.some((segment) => segment === ".." || segment === "." || segment === "")) {
    return NextResponse.json({ detail: "invalid_path" }, { status: 400 });
  }
  // getAccessToken() can THROW, not just return null: config resolution is
  // lazy, so on a secretless prod boot the AUTH_SESSION_SECRET guard fires
  // here - upstream of the null-token tolerance below - and used to 500 this
  // public-class read on the guest page (A-U4b C3, the milk §2b lesson:
  // secretless prod boot = guest, never 500). For this guest-capable proxy an
  // unresolvable auth config IS "no token", so degrade to an unauthenticated
  // forward; the loud operator-facing failure lives at /api/auth/*
  // (auth_not_configured + server log), not in every guest's console.
  const token = await auth.getAccessToken().catch(() => null); // null for guests - fine
  const url = new URL(`${API}/identity/${path.map(encodeURIComponent).join("/")}`);
  url.search = req.nextUrl.search;
  const upstream = await fetch(url, {
    method,
    headers: {
      ...(token ? { authorization: `Bearer ${token}` } : {}),
      ...(method !== "GET" ? { "content-type": "application/json" } : {}),
    },
    ...(method !== "GET" ? { body: await req.text() } : {}),
    cache: "no-store",
  });
  if (upstream.status === 204 || upstream.status === 205 || upstream.status === 304) {
    return new NextResponse(null, { status: upstream.status });
  }
  // Raw bytes with the upstream content-type, NOT `upstream.json()`.
  // `GET /identity/profile/avatar` answers with image bytes; parsing every
  // response as JSON turned an uploaded profile photo into `{}` served as
  // application/json, so the header avatar could never render one. JSON
  // responses are unaffected — they keep their own content-type and body.
  const headers: Record<string, string> = {
    "content-type": upstream.headers.get("content-type") ?? "application/json",
  };
  // The avatar route marks itself `private, must-revalidate` precisely so no
  // shared cache holds one person's face; forward that rather than drop it.
  const cacheControl = upstream.headers.get("cache-control");
  if (cacheControl) headers["cache-control"] = cacheControl;
  return new NextResponse(Buffer.from(await upstream.arrayBuffer()), {
    status: upstream.status,
    headers,
  });
}

type Ctx = { params: Promise<{ path: string[] }> };

export async function GET(req: NextRequest, ctx: Ctx): Promise<NextResponse> {
  return forward(req, ctx.params, "GET");
}
export async function PATCH(req: NextRequest, ctx: Ctx): Promise<NextResponse> {
  return forward(req, ctx.params, "PATCH");
}
