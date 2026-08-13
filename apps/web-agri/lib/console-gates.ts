/**
 * Server-side console probes (U2), shared by the console layout and the
 * dashboard so neither re-invents them. All fail closed to "hidden": no
 * token, network error, or non-OK response reads as "not visible / owns
 * nothing" — the console renders less, never breaks.
 */
import { auth } from "@/lib/auth";

const API = process.env.API_BASE_URL ?? "http://127.0.0.1:8000";

/** Owner-list projection (GET /directory/businesses — D15 `list_my_businesses`). */
export interface OwnedBusiness {
  id: string;
  name: string;
  slug: string;
  type: "vendor" | "shop" | "lab" | "farm";
  status: "active" | "suspended" | "disabled";
  primary_pincode: string;
  verification_status: string;
  subscription_tier: string;
  /** M1.5: owner-facing notice text, set while suspended/disabled. */
  enforcement_reason: string | null;
}

/**
 * The vendor/consumer distinction (U2 role-gated rendering). The seeded
 * `business_owner` role is assigned by no code path today, so gating nav on
 * it would lock out every real vendor; ownership of ≥1 business is the
 * truthful signal. Signed-out or failing reads return [] — the caller
 * renders the consumer (nav-less) frame and the page-level auth gate still
 * owns the redirect.
 */
export async function fetchOwnedBusinesses(): Promise<OwnedBusiness[]> {
  const token = await auth.getAccessToken();
  if (!token) return [];
  try {
    const response = await fetch(`${API}/directory/businesses?limit=50`, {
      headers: { authorization: `Bearer ${token}` },
      cache: "no-store",
    });
    if (!response.ok) return [];
    const body: unknown = await response.json();
    const items = (body as { items?: unknown }).items;
    return Array.isArray(items) ? (items as OwnedBusiness[]) : [];
  } catch {
    return [];
  }
}

/** billing_enabled probe: the backend 404s the whole /billing surface while
 * dark, so one status check lights (or hides) the billing module. */
export async function billingVisible(): Promise<boolean> {
  const token = await auth.getAccessToken();
  if (!token) return false;
  try {
    const response = await fetch(`${API}/billing/subscription`, {
      headers: { authorization: `Bearer ${token}` },
      cache: "no-store",
    });
    return response.status !== 404;
  } catch {
    return false;
  }
}

/** ads_enabled probe: the backend 404s the whole /ads/my surface while
 * dark, so one status check lights (or hides) the ads module. */
export async function adsVisible(): Promise<boolean> {
  const token = await auth.getAccessToken();
  if (!token) return false;
  try {
    const response = await fetch(`${API}/ads/my/campaigns?limit=1`, {
      headers: { authorization: `Bearer ${token}` },
      cache: "no-store",
    });
    return response.status !== 404;
  } catch {
    return false;
  }
}
