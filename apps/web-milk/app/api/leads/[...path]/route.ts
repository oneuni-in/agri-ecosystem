/**
 * BFF proxy: browser -> same-origin /api/leads/* -> FastAPI /leads/* with the
 * session bearer attached HERE, server-side (tokens never touch JS). Guest-
 * capable: an absent token forwards WITHOUT an Authorization header — the
 * backend enforces auth on protected /leads paths. POST forwards raw bytes
 * (the D25 multipart voice-note keeps its boundary); GET streams bytes back
 * (audio playback), so neither side assumes JSON.
 */
import type { NextRequest } from "next/server";
import { NextResponse } from "next/server";

import { auth } from "@/lib/auth";

const API = process.env.API_BASE_URL ?? "http://127.0.0.1:8000";
const MAX_BODY_BYTES = 6 * 1024 * 1024; // > backend MAX_AUDIO_BYTES, < abuse

function badPath(path: string[]): boolean {
  return path.some((segment) => segment === ".." || segment === "." || segment === "");
}

async function forward(
  req: NextRequest,
  path: string[],
  init: RequestInit,
): Promise<NextResponse> {
  const token = await auth.getAccessToken(); // null for guests — fine
  const url = new URL(`${API}/leads/${path.map(encodeURIComponent).join("/")}`);
  url.search = req.nextUrl.search;
  const upstream = await fetch(url, {
    ...init,
    headers: {
      ...(init.headers ?? {}),
      ...(token ? { authorization: `Bearer ${token}` } : {}),
    },
    cache: "no-store",
  });
  if (upstream.status === 204 || upstream.status === 205 || upstream.status === 304) {
    return new NextResponse(null, { status: upstream.status });
  }
  const body = await upstream.arrayBuffer();
  return new NextResponse(body, {
    status: upstream.status,
    headers: {
      "content-type": upstream.headers.get("content-type") ?? "application/json",
      "cache-control": "private, no-store",
    },
  });
}

export async function GET(
  req: NextRequest,
  ctx: { params: Promise<{ path: string[] }> },
): Promise<NextResponse> {
  const { path } = await ctx.params;
  if (badPath(path)) return NextResponse.json({ detail: "invalid_path" }, { status: 400 });
  return forward(req, path, { method: "GET" });
}

export async function POST(
  req: NextRequest,
  ctx: { params: Promise<{ path: string[] }> },
): Promise<NextResponse> {
  const { path } = await ctx.params;
  if (badPath(path)) return NextResponse.json({ detail: "invalid_path" }, { status: 400 });
  const body = await req.arrayBuffer();
  if (body.byteLength > MAX_BODY_BYTES) {
    return NextResponse.json({ detail: "too_large" }, { status: 413 });
  }
  return forward(req, path, {
    method: "POST",
    headers: { "content-type": req.headers.get("content-type") ?? "application/json" },
    body,
  });
}
