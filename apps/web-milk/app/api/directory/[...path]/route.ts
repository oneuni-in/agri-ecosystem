/**
 * BFF proxy: browser -> same-origin /api/directory/* -> FastAPI /directory/*
 * with the session's bearer token attached HERE, server-side (tokens never
 * touch JS - D10 non-negotiable). Only the backend's /directory prefix is
 * reachable through this route by construction.
 *
 * Unlike the /api/notify proxy, request/response bodies are forwarded as raw
 * bytes with their original content-type: the claim submission is
 * multipart/form-data (evidence photos) and the boundary lives in that
 * header - parsing it into formData() here would lose it.
 */
import type { NextRequest } from "next/server";
import { NextResponse } from "next/server";

import { auth } from "@/lib/auth";
import { forwardedClientIp } from "@/lib/client-ip";

const API = process.env.API_BASE_URL ?? "http://127.0.0.1:8000";
const NULL_BODY_STATUSES = new Set([204, 205, 304]);
// 5 files x 5MiB cap + multipart overhead.
const MAX_BODY_BYTES = 30 * 1024 * 1024;

// This proxy exists to attach the session bearer server-side (D10 - tokens
// never touch JS), so it 401s up front when there is no session. D27 Task 14
// adds the first GUEST-facing route behind it: nearby-branches is declared
// `public=True` on the backend (public_routes.txt) - "shops near you" must
// work for anonymous brand-page visitors, who are most of them. Rather than
// gate the whole proxy open, only this one declared-public GET path skips
// the token requirement; everything else keeps the default-private behavior.
const PUBLIC_GET_PATTERNS = [/^businesses\/[^/]+\/nearby-branches$/];

function isPublicGet(method: "GET" | "POST", path: string[]): boolean {
  return method === "GET" && PUBLIC_GET_PATTERNS.some((re) => re.test(path.join("/")));
}

async function forward(
  req: NextRequest,
  params: Promise<{ path: string[] }>,
  method: "GET" | "POST",
): Promise<NextResponse> {
  const { path } = await params;
  if (path.some((segment) => segment === ".." || segment === "." || segment === "")) {
    return NextResponse.json({ detail: "invalid_path" }, { status: 400 });
  }
  if (method === "POST") {
    const contentLength = Number(req.headers.get("content-length"));
    if (Number.isFinite(contentLength) && contentLength > MAX_BODY_BYTES) {
      return NextResponse.json({ detail: "payload too large" }, { status: 413 });
    }
  }
  const publicGet = isPublicGet(method, path);
  const token = await auth.getAccessToken();
  if (!token && !publicGet) {
    return NextResponse.json({ detail: "unauthenticated" }, { status: 401 });
  }
  const url = new URL(`${API}/directory/${path.map(encodeURIComponent).join("/")}`);
  url.search = req.nextUrl.search;
  const headers: Record<string, string> = {};
  if (token) headers.authorization = `Bearer ${token}`;
  const contentType = req.headers.get("content-type");
  if (contentType) headers["content-type"] = contentType;
  // Forward the visitor's address (mirrors /api/view's relay pattern): the
  // backend's rate limiter keys on client_ip + path (SecureRouter's
  // Depends(rate_limit) is unconditional, public or private), so without this
  // every caller through this proxy collapses into the Next server's own
  // single shared bucket.
  //
  // It comes from lib/client-ip and NOT from the inbound x-forwarded-for.
  // Forwarding that header let the caller pick its own rate-limit key, which
  // made the limit advisory - the exact thing this block exists to enforce.
  const clientIp = forwardedClientIp(req.headers);
  if (clientIp) headers["x-forwarded-for"] = clientIp;
  const userAgent = req.headers.get("user-agent");
  if (userAgent) headers["user-agent"] = userAgent;
  const upstream = await fetch(url, {
    method,
    headers,
    // Raw bytes, not formData()/text(): preserves the multipart boundary
    // for evidence-photo uploads (claim submission) untouched.
    ...(method === "POST" ? { body: Buffer.from(await req.arrayBuffer()) } : {}),
    cache: "no-store",
  });
  if (NULL_BODY_STATUSES.has(upstream.status)) {
    return new NextResponse(null, { status: upstream.status });
  }
  const responseHeaders: Record<string, string> = {
    "content-type": upstream.headers.get("content-type") ?? "application/json",
  };
  const cacheControl = upstream.headers.get("cache-control");
  if (cacheControl) responseHeaders["cache-control"] = cacheControl;
  return new NextResponse(Buffer.from(await upstream.arrayBuffer()), {
    status: upstream.status,
    headers: responseHeaders,
  });
}

type Ctx = { params: Promise<{ path: string[] }> };

export async function GET(req: NextRequest, ctx: Ctx): Promise<NextResponse> {
  return forward(req, ctx.params, "GET");
}
export async function POST(req: NextRequest, ctx: Ctx): Promise<NextResponse> {
  return forward(req, ctx.params, "POST");
}
