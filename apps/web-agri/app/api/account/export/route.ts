/**
 * DPDP data export, passed through with its download headers intact
 * (AG-U5 P5).
 *
 * A dedicated route rather than the generic `/api/identity/*` proxy, for one
 * concrete reason: that proxy re-wraps every upstream body in
 * `NextResponse.json()`, which drops the `content-disposition` the backend
 * sets — so the archive would render as a wall of JSON in the tab instead of
 * saving as `agriid-data-YYYYMMDD.json`. The filename is part of the right
 * being exercised: "here is your data" should produce a file.
 *
 * `cache-control: private, no-store` is forwarded verbatim. This is one
 * person's entire record and no shared cache may hold it.
 */
import type { NextRequest } from "next/server";
import { NextResponse } from "next/server";

import { auth } from "@/lib/auth";

const API = process.env.API_BASE_URL ?? "http://127.0.0.1:8000";

export async function GET(_req: NextRequest): Promise<NextResponse> {
  const token = await auth.getAccessToken().catch(() => null);
  if (!token) return NextResponse.json({ detail: "unauthenticated" }, { status: 401 });

  const upstream = await fetch(`${API}/identity/dpdp/export`, {
    headers: { authorization: `Bearer ${token}` },
    cache: "no-store",
  });
  if (!upstream.ok) {
    return NextResponse.json({ detail: "export_failed" }, { status: upstream.status });
  }
  const body = await upstream.text();
  return new NextResponse(body, {
    status: 200,
    headers: {
      "content-type": "application/json",
      "content-disposition":
        upstream.headers.get("content-disposition") ??
        'attachment; filename="agriid-data.json"',
      "cache-control": "private, no-store",
    },
  });
}
