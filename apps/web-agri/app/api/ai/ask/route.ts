/**
 * BFF proxy: browser -> same-origin /api/ai/ask -> FastAPI /ai/ask with the
 * session's bearer token attached HERE, server-side (tokens never touch JS —
 * D10 non-negotiable).
 *
 * Deliberately NOT a `[...path]` catch-all like the other proxies. The
 * assistant has exactly one endpoint, and a catch-all would make every future
 * /ai/* route reachable from the browser the moment it is written — including
 * one that should not be. One route, one file: adding a second is a
 * deliberate, reviewable act.
 */
import type { NextRequest } from "next/server";
import { NextResponse } from "next/server";

import { auth } from "@/lib/auth";

const API = process.env.API_BASE_URL ?? "http://127.0.0.1:8000";

export async function POST(req: NextRequest): Promise<NextResponse> {
  const token = await auth.getAccessToken();
  if (!token) return NextResponse.json({ detail: "unauthenticated" }, { status: 401 });

  const upstream = await fetch(`${API}/ai/ask`, {
    method: "POST",
    headers: {
      authorization: `Bearer ${token}`,
      "content-type": "application/json",
    },
    body: await req.text(),
    cache: "no-store",
  });
  const body = (await upstream.json().catch(() => ({}))) as Record<string, unknown>;
  return NextResponse.json(body, { status: upstream.status });
}
