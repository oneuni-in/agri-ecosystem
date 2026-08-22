/**
 * Role states and the first-run checklist (AG-U5 P6).
 *
 * WHICH ROLE SOMEONE IS, AND HOW WE KNOW.
 * Not from a role claim. `console-gates.ts` records why, and the same
 * reasoning governs here: the seeded `business_owner` role is assigned by no
 * code path, so gating on it would hide the console from every real vendor.
 * Ownership of at least one business is the truthful signal, and holding at
 * least one ad campaign is the truthful signal for an advertiser. Both are
 * reads, both fail closed to "not that role".
 *
 * Roles are not exclusive. A farmer who runs a shop and buys ads sees three
 * things, which is what the reference draws and what `describes` being a
 * LIST already established on the identity side.
 */

const API = process.env.API_BASE_URL ?? "http://127.0.0.1:8000";

export interface ChecklistInput {
  pincode: string | null;
  interests: string[];
  alerts: number;
  threads: number;
  saved: number;
}

export interface ChecklistStep {
  id: "location" | "crops" | "alerts" | "ask";
  done: boolean;
  href: string;
  /** True when the step is finished somewhere other than agri.in. */
  external?: true;
}

/**
 * The four steps, each ticked by a thing the SERVER holds.
 *
 * Never by a click. A checklist that remembers you visited a page is a
 * checklist that lies on a new phone, and one that congratulates you for
 * looking at something rather than doing it.
 */
export function deriveChecklist(input: ChecklistInput): ChecklistStep[] {
  return [
    { id: "location", done: Boolean(input.pincode), href: "/account", external: undefined },
    { id: "crops", done: input.interests.length > 0, href: "/account", external: undefined },
    { id: "alerts", done: input.alerts > 0, href: "/#mandi" },
    { id: "ask", done: input.threads > 0, href: "/directory" },
  ].map((step) => ({ ...step }) as ChecklistStep);
}

/**
 * Whether the dashboard should lead with the checklist.
 *
 * True only while the account is genuinely untouched. Saved items count even
 * though no step asks for one — the checklist has four entries because five
 * is a wall, not because saving an article is not a start. The moment
 * somebody has done anything real, the panels below are more useful than a
 * list of things to do.
 */
export function isFirstRun(input: ChecklistInput): boolean {
  return (
    !input.pincode &&
    input.interests.length === 0 &&
    input.alerts === 0 &&
    input.threads === 0 &&
    input.saved === 0
  );
}

export interface OwnedBusinessBrief {
  id: string;
  name: string;
  slug: string;
  status: string;
  verification_status: string;
}

export interface CampaignBrief {
  id: string;
  name: string;
  status: string;
  budget_display: string;
}

export interface CampaignStats {
  impressions: number;
  clicks: number;
  ctr_bp: number;
  spend_paise: number;
}

/** Businesses this person owns. `[]` on any failure — the rolecard is then
 * absent, never wrong. */
export async function fetchOwnedBusinesses(token: string): Promise<OwnedBusinessBrief[]> {
  try {
    const res = await fetch(`${API}/directory/businesses?limit=10`, {
      headers: { authorization: `Bearer ${token}` },
      cache: "no-store",
    });
    if (!res.ok) return [];
    const body = (await res.json()) as { items?: OwnedBusinessBrief[] };
    return body.items ?? [];
  } catch {
    return [];
  }
}

/**
 * Ad campaigns this person holds.
 *
 * A 404 here is not an error — the whole `/ads/my` surface 404s while the
 * `ads_enabled` flag is dark, which is exactly how `console-gates.adsVisible`
 * probes it. Either way the answer is "no advertiser card".
 */
export async function fetchMyCampaigns(token: string): Promise<CampaignBrief[]> {
  try {
    const res = await fetch(`${API}/ads/my/campaigns?limit=10`, {
      headers: { authorization: `Bearer ${token}` },
      cache: "no-store",
    });
    if (!res.ok) return [];
    const body = (await res.json()) as { items?: CampaignBrief[] };
    return body.items ?? [];
  } catch {
    return [];
  }
}

/**
 * The analytics strip's numbers, summed across the person's campaigns.
 *
 * THE SAME COUNTERS THE ADMIN CONSOLE READS, and that is an assertion worth
 * stating precisely because a drift between them is an incident: both
 * `/ads/my/campaigns/{id}/stats` and admin's `/ads/admin/stats` count rows in
 * `ads.impressions` and `ads.clicks` keyed by `placement_id`. Admin scopes to
 * one placement; this scopes to every placement of a campaign. So a
 * campaign's total here equals the sum of its placements' admin numbers over
 * the same window — one counter, two readers, no second source.
 *
 * `null` when nothing could be read, so the strip can say so instead of
 * printing zeroes that look like "nobody saw your ad".
 */
export async function fetchCampaignTotals(
  token: string,
  campaignIds: string[],
): Promise<CampaignStats | null> {
  if (campaignIds.length === 0) return null;
  try {
    const results = await Promise.all(
      campaignIds.map(async (id) => {
        const res = await fetch(`${API}/ads/my/campaigns/${id}/stats?days=30`, {
          headers: { authorization: `Bearer ${token}` },
          cache: "no-store",
        });
        return res.ok ? ((await res.json()) as CampaignStats) : null;
      }),
    );
    const readable = results.filter((row): row is CampaignStats => row !== null);
    if (readable.length === 0) return null;
    const impressions = readable.reduce((total, row) => total + (row.impressions ?? 0), 0);
    const clicks = readable.reduce((total, row) => total + (row.clicks ?? 0), 0);
    return {
      impressions,
      clicks,
      // Recomputed from the totals rather than averaged from each campaign's
      // ctr_bp: averaging ratios weights a 10-impression campaign the same as
      // a 10,000-impression one. Same basis-point convention as the server.
      ctr_bp: impressions > 0 ? Math.floor((clicks * 10000) / impressions) : 0,
      spend_paise: readable.reduce((total, row) => total + (row.spend_paise ?? 0), 0),
    };
  } catch {
    return null;
  }
}
