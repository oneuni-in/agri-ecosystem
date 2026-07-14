/**
 * BFF proxy: browser -> same-origin /api/admin/* -> FastAPI /admin/* with the
 * session's bearer token attached HERE, server-side (tokens never touch JS -
 * D10 non-negotiable). Only the backend's /admin prefix is reachable through
 * this route by construction.
 */
import type { NextRequest } from "next/server";
import { NextResponse } from "next/server";

import { auth } from "@/lib/auth";

const API = process.env.API_BASE_URL ?? "http://127.0.0.1:8000";

async function forward(
  req: NextRequest,
  params: Promise<{ path: string[] }>,
  method: "GET" | "POST" | "PUT" | "DELETE",
): Promise<NextResponse> {
  const token = await auth.getAccessToken();
  if (!token) return NextResponse.json({ detail: "unauthenticated" }, { status: 401 });
  const { path } = await params;
  const url = new URL(`${API}/admin/${path.map(encodeURIComponent).join("/")}`);
  url.search = req.nextUrl.search;
  const hasBody = method === "POST" || method === "PUT";
  const upstream = await fetch(url, {
    method,
    headers: {
      authorization: `Bearer ${token}`,
      ...(hasBody ? { "content-type": "application/json" } : {}),
    },
    ...(hasBody ? { body: await req.text() } : {}),
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
export async function PUT(req: NextRequest, ctx: Ctx): Promise<NextResponse> {
  return forward(req, ctx.params, "PUT");
}
export async function DELETE(req: NextRequest, ctx: Ctx): Promise<NextResponse> {
  return forward(req, ctx.params, "DELETE");
}
