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
  const token = await auth.getAccessToken(); // null for guests - fine
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
  const body = (await upstream.json().catch(() => ({}))) as Record<string, unknown>;
  return NextResponse.json(body, { status: upstream.status });
}

type Ctx = { params: Promise<{ path: string[] }> };

export async function GET(req: NextRequest, ctx: Ctx): Promise<NextResponse> {
  return forward(req, ctx.params, "GET");
}
export async function PATCH(req: NextRequest, ctx: Ctx): Promise<NextResponse> {
  return forward(req, ctx.params, "PATCH");
}
