/**
 * Phase 2 — the agri-colleges data layer.
 *
 * Everything the surfaces need to decide what to render already travels on
 * the wire: `can_show_admission_data` (server-computed), `trust`, `status`
 * and `merged_into_slug`. Pages BRANCH on those; they never re-derive the
 * rule. A page that checks `trust === "verified"` itself has forked a rule
 * that lives in one place on the server, and the two copies will disagree.
 *
 * Every LIST fetch degrades to empty. A dead education engine makes a section
 * absent, never a 500 (spec §7, F1).
 *
 * DETAIL fetches do NOT collapse the two failure modes. `null` means the API
 * said 404 — this slug does not exist, and the page must 404 too.
 * `"unavailable"` means we could not ask, and that must NOT become a 404, or
 * a college that exists would serve a hard 404 to Google for the length of an
 * incident. A list has an honest empty state either way; a detail page does
 * not.
 */
const API = process.env.API_BASE_URL ?? "http://127.0.0.1:8000";

/** The corpus changes when a seed PR merges — days apart, not minutes. An
 * hour is generous, and `last_verified_at` travels IN the payload so a cached
 * page still tells the truth about its own age. */
const REVALIDATE_SECONDS = 3600;

export type Translated = Record<string, string>;

export interface InstitutionCard {
  id: string;
  slug: string;
  name: string;
  short_name: string | null;
  kind: string;
  is_government: boolean | null;
  state: string | null;
  district: string | null;
  country_code: string;
  website: string | null;
  established_year: number | null;
  trust: "verified" | "listed";
  status: "active" | "closed" | "merged";
  last_verified_at: string;
  /** Server-computed. The ONLY thing a surface may branch on to decide
   * whether a fee, a seat count or an admission route may be rendered. */
  can_show_admission_data: boolean;
}

export interface Offering {
  programme_slug: string;
  name: Translated;
  level: string;
  discipline: string;
  duration_months: number | null;
  intake_seats: number | null;
  annual_fees_inr: number | null;
  fee_note: string | null;
  admission_route: string | null;
  source_url: string | null;
  /** The OFFERING's own stamp, separate from the institution's — this is what
   * lets a page say "college verified Mar 2026 · fees last checked Aug 2025"
   * honestly. Render both; never collapse them into one. */
  last_verified_at: string | null;
}

export interface RelatedInstitution {
  slug: string;
  name: string;
  kind: string;
}

export interface InstitutionDetail extends InstitutionCard {
  name_ta: string | null;
  name_hi: string | null;
  address: string | null;
  pincode: string | null;
  lat: string | null;
  lng: string | null;
  contact_phone: string | null;
  contact_email: string | null;
  accreditation: Record<string, unknown> | null;
  source_url: string;
  merged_into_slug: string | null;
  parent: RelatedInstitution | null;
  constituents: RelatedInstitution[];
  programmes: Offering[];
}

export interface StateFacet {
  slug: string;
  name: string;
  institution_count: number;
}

export interface InstitutionPage {
  items: InstitutionCard[];
  next_cursor: string | null;
}

export interface ProgrammeItem {
  slug: string;
  name: Translated;
  level: string;
  discipline: string;
  duration_months: number | null;
  description: Translated;
}

export interface ResourceCard {
  id: string;
  slug: string;
  name: Translated;
  kind: "scholarship" | "exam";
  category: string | null;
  scope: string;
  provider: string | null;
  levels: string[];
  benefit: string | null;
  window: Record<string, unknown> | null;
  official_url: string;
  last_verified_at: string;
}

export interface ResourceDetail extends ResourceCard {
  eligibility: Translated;
  applies_to: Record<string, unknown> | null;
}

export interface ResourcePage {
  items: ResourceCard[];
  next_cursor: string | null;
}

export interface GuideCard {
  id: string;
  slug: string;
  title: Translated;
  kind: "counselling" | "foreign_study" | "general";
  country_code: string | null;
  state: string | null;
  summary: Translated;
  last_verified_at: string;
}

export interface GuideDetail extends GuideCard {
  steps: { title?: string; body?: string; links?: string[] }[];
  official_links: string[];
}

/** Every field is `| undefined` explicitly, not just optional. The repo runs
 * `exactOptionalPropertyTypes`, and callers build these from `searchParams`,
 * where an absent filter genuinely IS `undefined` rather than missing. */
export interface InstitutionFilters {
  state?: string | undefined;
  district?: string | undefined;
  kind?: string | undefined;
  is_government?: boolean | undefined;
  programme?: string | undefined;
  trust?: string | undefined;
  q?: string | undefined;
  cursor?: string | undefined;
  limit?: number | undefined;
}

export interface ResourceFilters {
  kind?: string | undefined;
  category?: string | undefined;
  scope?: string | undefined;
  cursor?: string | undefined;
  limit?: number | undefined;
}

export interface GuideFilters {
  kind?: string | undefined;
  country?: string | undefined;
  state?: string | undefined;
}

/** `"unavailable"` is a third outcome, not a nicer null — see the file
 * comment. Detail routes must never turn an outage into a 404. */
export type Unavailable = "unavailable";

export function qs(filters: Record<string, unknown>): string {
  const params = new URLSearchParams();
  for (const [key, value] of Object.entries(filters)) {
    // Empty string is dropped deliberately: `q=` reaches the API as an
    // ILIKE '%%' that matches the whole corpus, which reads as success.
    if (value === undefined || value === null || value === "") continue;
    params.set(key, String(value));
  }
  const query = params.toString();
  return query ? `?${query}` : "";
}

async function getList<T>(path: string, fallback: T): Promise<T> {
  try {
    const res = await fetch(`${API}${path}`, { next: { revalidate: REVALIDATE_SECONDS } });
    if (!res.ok) return fallback;
    return (await res.json()) as T;
  } catch {
    return fallback;
  }
}

async function getDetail<T>(path: string): Promise<T | null | Unavailable> {
  try {
    const res = await fetch(`${API}${path}`, { next: { revalidate: REVALIDATE_SECONDS } });
    if (res.status === 404) return null;
    if (!res.ok) return "unavailable";
    return (await res.json()) as T;
  } catch {
    return "unavailable";
  }
}

export function fetchInstitutions(filters: InstitutionFilters): Promise<InstitutionPage> {
  return getList<InstitutionPage>(`/education/institutions${qs({ ...filters })}`, {
    items: [],
    next_cursor: null,
  });
}

export function fetchInstitution(slug: string): Promise<InstitutionDetail | null | Unavailable> {
  return getDetail<InstitutionDetail>(`/education/institutions/${encodeURIComponent(slug)}`);
}

export function fetchStates(): Promise<StateFacet[]> {
  return getList<StateFacet[]>("/education/states", []);
}

export function fetchProgrammes(): Promise<ProgrammeItem[]> {
  return getList<ProgrammeItem[]>("/education/programmes", []);
}

export function fetchResources(filters: ResourceFilters = {}): Promise<ResourcePage> {
  return getList<ResourcePage>(`/education/student-resources${qs({ ...filters })}`, {
    items: [],
    next_cursor: null,
  });
}

export function fetchResource(slug: string): Promise<ResourceDetail | null | Unavailable> {
  return getDetail<ResourceDetail>(`/education/student-resources/${encodeURIComponent(slug)}`);
}

export function fetchGuides(filters: GuideFilters = {}): Promise<GuideCard[]> {
  return getList<GuideCard[]>(`/education/guides${qs({ ...filters })}`, []);
}

export function fetchGuide(slug: string): Promise<GuideDetail | null | Unavailable> {
  return getDetail<GuideDetail>(`/education/guides/${encodeURIComponent(slug)}`);
}
