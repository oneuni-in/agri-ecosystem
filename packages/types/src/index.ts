/**
 * @agri/types — the single source of shared types across the five apps.
 *
 * Runtime-free by construction: this package must never ship executable code,
 * only `type` / `interface` declarations, so importing it from a Server
 * Component or an Edge route adds zero bytes.
 *
 * D01-B lands `backend/openapi.json`; `pnpm gen:types` then writes
 * `src/generated/openapi.ts` and the re-export below goes live.
 */

/** UUIDv7 — every id in the ecosystem (CLAUDE.md Constitution). */
export type Uuid = string & { readonly __brand: "uuid-v7" };

/** Opaque cursor for the mandated cursor-pagination on every list endpoint. */
export type Cursor = string & { readonly __brand: "cursor" };

/** All user-submitted content defaults to `pending` (CLAUDE.md Constitution). */
export type ModerationStatus = "pending" | "approved" | "rejected";

/** Shape every paginated list endpoint returns. */
export interface Page<T> {
  readonly items: readonly T[];
  readonly nextCursor: Cursor | null;
}

/** The three storefront themes; `data-theme` on each app's root element. */
export type SiteTheme = "theme-agri" | "theme-milk" | "theme-organic";

// D01-B → after `pnpm gen:types`, uncomment:
// export type { components, paths, operations } from "./generated/openapi.js";

/* ── A-U1 W3 — the agri.in TODAY payload: THE frozen A-U2 contract ──────
 * Mirror of backend/core/modules/market_data/schemas.py, field for field.
 * The agri home renders Today sections FROM this shape; A-U2's real
 * workers (Open-Meteo D42, Agmarknet D43, schemes E5) must fill it
 * without the UI changing. Change only with a matching schemas.py change
 * and an A-U2 sign-off note. Flag contract: `agri_today` OFF → the
 * endpoint 404s → `fetchToday()` is null → sections ABSENT from the DOM.
 */

/** Editorial text rides in all three locales (E5 TranslatedString rule). */
export interface TranslatedText {
  readonly en: string;
  readonly ta: string;
  readonly hi: string;
}

export interface WeatherDay {
  readonly label: TranslatedText;
  readonly icon: string;
  readonly high_c: number;
  readonly low_c: number;
}

export interface WeatherAdvisory {
  readonly kind: "spray" | (string & {});
  readonly title: TranslatedText;
  readonly body: TranslatedText;
}

export interface DailyTip {
  readonly title: TranslatedText;
  readonly body: TranslatedText;
}

export interface WeatherBlock {
  readonly temp_c: number;
  readonly condition_icon: string;
  readonly condition: TranslatedText;
  /** 7 entries, today first. */
  readonly days: readonly WeatherDay[];
  readonly humidity_pct: number;
  readonly wind_kmh: number;
  readonly wind_dir: string;
  readonly rain_chance_pct: number | null;
  readonly soil_temp_c: number | null;
  /** Rendered verbatim — the as-of/source stamp is DATA, never hardcoded. */
  readonly source: string;
  readonly advisory: WeatherAdvisory | null;
  readonly tip: DailyTip | null;
}

export interface SevereAlert {
  readonly headline: TranslatedText;
  readonly district: string;
  readonly window: TranslatedText;
  readonly source: string;
  readonly details_url: string | null;
}

export interface MandiCommodity {
  readonly slug: string;
  readonly name: TranslatedText;
  readonly emoji: string;
  readonly market: string;
  readonly unit: "kg" | "pc" | "qtl" | (string & {});
  readonly price: number;
  /** Signed day-over-day delta; 0 renders the flat "—". */
  readonly change: number;
  /** Oldest first — the sparkline input. */
  readonly series_30d: readonly number[];
  readonly range_low: number;
  readonly range_high: number;
  readonly modal: number | null;
  readonly arrivals_qtl: number | null;
  readonly note: TranslatedText | null;
}

export interface MandiBlock {
  readonly market: string;
  readonly as_of: string;
  readonly source: string;
  readonly commodities: readonly MandiCommodity[];
}

export interface CalendarMonth {
  readonly label: string;
  readonly in_season: boolean;
  readonly current: boolean;
}

export interface CropWindow {
  readonly icon: string;
  readonly label: TranslatedText;
  readonly until: TranslatedText | null;
}

export interface CalendarBlock {
  readonly zone: TranslatedText;
  readonly months: readonly CalendarMonth[];
  readonly sowing: readonly CropWindow[];
  readonly harvesting: readonly CropWindow[];
}

export interface SchemeItem {
  readonly level: "central" | "state";
  readonly state_label: TranslatedText | null;
  readonly title: TranslatedText;
  readonly body: TranslatedText;
  /** Official domain the entry was verified against — rendered from data. */
  readonly verified_against: string;
  /** ISO date of the human verification. */
  readonly verified_on: string;
  readonly url: string;
  readonly link_label: TranslatedText;
}

export interface SchemeDeadline {
  readonly chip: string;
  readonly title: TranslatedText;
  readonly note: TranslatedText | null;
}

export interface SchemesBlock {
  readonly items: readonly SchemeItem[];
  readonly deadlines: readonly SchemeDeadline[];
}

/** GET /market/today/{pincode} — 404 while `agri_today` is off. */
export interface TodayPayload {
  readonly pincode: string;
  readonly district: string | null;
  readonly generated_at: string;
  /** True until A-U2 replaces fixtures with real workers. */
  readonly stub: boolean;
  readonly weather: WeatherBlock;
  readonly severe_alert: SevereAlert | null;
  readonly mandi: MandiBlock;
  readonly calendar: CalendarBlock;
  readonly schemes: SchemesBlock;
}
