/**
 * A-U4 W2 — the coins read layer.
 *
 * `GET /coins/rules` is public and returns the ACTIVE earn rules with their
 * configured amounts. This exists to close a recorded A-U1 deviation: the
 * home's "Earn AgriCoins" cards shipped with a coin glyph where a number
 * belongs, because no rules read existed and inventing amounts was rightly
 * refused ("Never invent amounts").
 *
 * Note the engine and the A1 mockup disagree, and the engine wins. The
 * mockup prints +5 for a review and +25 for a referral; `coins.rules` pays
 * 20 and 250. The mockup's figures are illustrative design copy — the rules
 * table is the data, and this is the same "registry as data" rule that
 * governs the category grid.
 */

const API = process.env.API_BASE_URL ?? "http://127.0.0.1:8000";

export interface EarnRule {
  code: string;
  amount: number;
  label_key: string;
  daily_cap: number | null;
  weekly_cap: number | null;
  total_cap: number | null;
}

/**
 * Active earn rules, keyed by code for card lookup.
 *
 * Cached for an hour: a rule amount changes when someone edits config, which
 * is rare and never urgent. `{}` on any failure — the caller then renders the
 * card without an amount rather than with a wrong one.
 */
export async function fetchEarnRules(): Promise<Record<string, EarnRule>> {
  try {
    const res = await fetch(`${API}/coins/rules`, { next: { revalidate: 3600 } });
    if (!res.ok) return {};
    const body = (await res.json()) as { items?: EarnRule[] };
    return Object.fromEntries((body.items ?? []).map((rule) => [rule.code, rule]));
  } catch {
    return {};
  }
}

/**
 * The A1 §15b earn cards, mapped to the rule that actually pays them.
 *
 * `code: null` is the honest case, not an oversight. The A1 reference shows
 * an "Attend a webinar" card, but events are a Stage D surface and no
 * `webinar_attend` rule exists — a card promising coins for something no
 * code path can award would be advertising a reward nobody can earn. It
 * renders with the Soon treatment the rest of the platform uses for
 * not-yet-built verticals, and gains an amount when events ship.
 */
export const EARN_CARDS = [
  { key: "e1", icon: "⭐", code: "review_approved" },
  { key: "e2", icon: "🎪", code: null },
  { key: "e3", icon: "🤝", code: "referral_referrer" },
  { key: "e4", icon: "📅", code: "daily_visit_streak" },
] as const;
