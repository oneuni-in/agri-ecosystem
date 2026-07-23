/**
 * BFF proxy: browser -> same-origin /api/leads/* -> FastAPI /leads/* with the
 * session bearer attached HERE, server-side (tokens never touch JS). Mirrors
 * the guest-capable /api/identity proxy: /leads/pincode-interest is public
 * (optional_auth), so an absent token forwards WITHOUT an Authorization header
 * rather than 401-ing — the backend enforces auth on protected /leads paths.
 */
import type { NextRequest } from "next/server";
import { NextResponse } from "next/server";

import { auth } from "@/lib/auth";

const API = process.env.API_BASE_URL ?? "http://127.0.0.1:8000";

export async function POST(
  req: NextRequest,
  ctx: { params: Promise<{ path: string[] }> },
): Promise<NextResponse> {
  const { path } = await ctx.params;
  if (path.some((segment) => segment === ".." || segment === "." || segment === "")) {
    return NextResponse.json({ detail: "invalid_path" }, { status: 400 });
  }
  const token = await auth.getAccessToken(); // null for guests — fine
  const url = new URL(`${API}/leads/${path.map(encodeURIComponent).join("/")}`);
  url.search = req.nextUrl.search;
  const upstream = await fetch(url, {
    method: "POST",
    headers: {
      ...(token ? { authorization: `Bearer ${token}` } : {}),
      "content-type": "application/json",
    },
    body: await req.text(),
    cache: "no-store",
  });
  if (upstream.status === 204 || upstream.status === 205 || upstream.status === 304) {
    return new NextResponse(null, { status: upstream.status });
  }
  const body = (await upstream.json().catch(() => ({}))) as Record<string, unknown>;
  return NextResponse.json(body, { status: upstream.status });
}
