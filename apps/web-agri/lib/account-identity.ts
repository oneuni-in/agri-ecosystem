/**
 * The one identity read behind /account (AG-U5 P1).
 *
 * `GET /identity/profile` and `GET /auth/me`, in parallel — the same pair
 * web-id's own account page reads, for the same reason: the profile owns the
 * fields, and `/auth/me` owns whether the AgriID is still the generated
 * fallback (`handle_is_fallback`), which the profile shape does not carry.
 *
 * This is deliberately ONE seam rather than a fetch per panel. P1 renders the
 * sidebar card from it; the overview stats, the crops panel and the role
 * states all want the same document, and a second reader would eventually
 * disagree with the first about which pincode the visitor is in.
 *
 * NOTHING here is written. Name, handle, phone and language are AgriID's to
 * change — this dashboard reads them and links out to id.agri.in to edit.
 */

const API = process.env.API_BASE_URL ?? "http://127.0.0.1:8000";

/** `identity.FarmProfile`, as served. Every field nullable, and it stays that
 * way — a NOT NULL here would turn "I did not say" into a claim of zero. */
export interface AccountFarm {
  land_area: string | null;
  land_unit: string | null;
  tenure: string | null;
  cattle: number | null;
  goats: number | null;
  poultry: number | null;
  irrigation: string | null;
}

export interface AccountIdentity {
  agriId: string;
  /** True while the AgriID is still the generated AG-XXXXXXX. */
  handleIsFallback: boolean;
  name: string | null;
  state: string | null;
  district: string | null;
  pincode: string | null;
  language: string | null;
  /** Crops live HERE, not on the farm profile — "one list rather than two"
   * (identity/models.py). The 🌾 panel reads this. */
  interests: string[];
  /** Self-description ("farmer" / "business" / "exploring"), a LIST because
   * you can be both. Decides which sections render; grants nothing. */
  describes: string[];
  ownedBusinesses: string[];
  completionScore: number;
  missing: string[];
  farm: AccountFarm | null;
}

/**
 * How the AgriID reads in the sidebar card.
 *
 * The `@` says "a person picked this". A generated id has not been picked, so
 * it renders bare. The server's flag decides — this side never re-derives the
 * rule from the string's shape, because then two copies of it exist.
 */
export function handleLabel(agriId: string, handleIsFallback: boolean): string {
  return handleIsFallback ? agriId : `@${agriId}`;
}

interface ProfileResponse {
  agri_id: string;
  name: string | null;
  state: string | null;
  district: string | null;
  pincode: string | null;
  language: string | null;
  interests?: string[];
  describes?: string[];
  owned_businesses?: string[];
  completion_score?: number;
  missing?: string[];
  farm?: AccountFarm | null;
}

/**
 * `null` on any failure, never a half-populated card.
 *
 * A dashboard that renders "Coimbatore · —" because one of two reads timed out
 * is worse than one that renders the signed-out shell: the first is wrong and
 * looks right. Callers treat `null` as "not signed in, or we cannot say".
 */
export async function fetchAccountIdentity(token: string): Promise<AccountIdentity | null> {
  const headers = { authorization: `Bearer ${token}` };
  try {
    const [profileRes, meRes] = await Promise.all([
      fetch(`${API}/identity/profile`, { headers, cache: "no-store" }),
      fetch(`${API}/auth/me`, { headers, cache: "no-store" }),
    ]);
    if (!profileRes.ok) return null;
    const profile = (await profileRes.json()) as ProfileResponse;
    // Fail SOFT on /auth/me alone: the profile is the document, and the flag
    // only decides whether an "@" is printed. Assuming "generated" is the
    // conservative half — it under-claims rather than dressing a sequence
    // number up as a chosen name.
    const me = meRes.ok ? ((await meRes.json()) as { handle_is_fallback?: boolean }) : null;
    return {
      agriId: profile.agri_id,
      handleIsFallback: me?.handle_is_fallback ?? true,
      name: profile.name,
      state: profile.state,
      district: profile.district,
      pincode: profile.pincode,
      language: profile.language,
      interests: profile.interests ?? [],
      describes: profile.describes ?? [],
      ownedBusinesses: profile.owned_businesses ?? [],
      completionScore: profile.completion_score ?? 0,
      missing: profile.missing ?? [],
      farm: profile.farm ?? null,
    };
  } catch {
    return null;
  }
}
