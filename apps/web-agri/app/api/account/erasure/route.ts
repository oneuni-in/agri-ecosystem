/**
 * DPDP erasure: request it, or take it back (AG-U5 P5).
 *
 * A NARROW route rather than adding POST/DELETE to the generic
 * `/api/identity/*` proxy. That proxy forwards whatever path it is handed, so
 * teaching it to write would make every identity endpoint writable from the
 * browser — a much wider door than this one surface needs. The backend
 * enforces permissions either way, but the smaller opening is the one worth
 * having on the path that deletes an account.
 *
 * Both verbs are the caller's own: the backend resolves the subject from the
 * bearer token, and there is no parameter here that could name someone else.
 */
import type { NextRequest } from "next/server";
import { NextResponse } from "next/server";

import { auth } from "@/lib/auth";

const API = process.env.API_BASE_URL ?? "http://127.0.0.1:8000";

async function forward(method: "POST" | "DELETE"): Promise<NextResponse> {
  const token = await auth.getAccessToken().catch(() => null);
  if (!token) return NextResponse.json({ detail: "unauthenticated" }, { status: 401 });

  const upstream = await fetch(`${API}/identity/dpdp/erasure`, {
    method,
    headers: { authorization: `Bearer ${token}` },
    cache: "no-store",
  });
  if (upstream.status === 204) return new NextResponse(null, { status: 204 });
  const body = (await upstream.json().catch(() => ({}))) as Record<string, unknown>;
  return NextResponse.json(body, { status: upstream.status });
}

/** Ask for deletion. Idempotent upstream — a second tap is the same wish. */
export async function POST(_req: NextRequest): Promise<NextResponse> {
  return forward("POST");
}

/** Change your mind, during the grace window. */
export async function DELETE(_req: NextRequest): Promise<NextResponse> {
  return forward("DELETE");
}
