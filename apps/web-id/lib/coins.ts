/**
 * ID-U1 — the coins read layer for id.agri.in.
 *
 * Mirrors apps/web-agri/lib/coins.ts deliberately rather than sharing it:
 * the two apps read the same public endpoint but neither owns the other's
 * fetch caching, and a shared module would put web-agri's revalidate window
 * in charge of what the login screen promises a farmer.
 *
 * Every coin figure this app renders comes from here. The A7 reference
 * prints +100 / +250 / +200 beside its referral, done and profile blocks;
 * those are illustrative design copy. `coins.rules` is the data, and the
 * build prompt is explicit that no amount may be hardcoded — A-U1 already
 * paid for that lesson once, when the home shipped a coin glyph where a
 * number belonged.
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

/** The rule codes this app renders. Named so a reader of the login screen
 * can find the row in the rules table without guessing at the string. */
export const RULE_REFEREE = "referral_referee";
export const RULE_REFERRER = "referral_referrer";
export const RULE_SIGNUP = "signup_complete";
export const RULE_PROFILE_100 = "profile_100";

export type RuleAmounts = Record<string, number>;

/**
 * Active earn-rule amounts, keyed by code.
 *
 * Cached for an hour: an amount changes when someone edits config, which is
 * rare and never urgent. `{}` on any failure, which is the honest degrade —
 * every caller here renders its block WITHOUT the number rather than with an
 * invented one, and the referral banner drops out entirely (its whole job is
 * naming the reward).
 */
export async function fetchRuleAmounts(): Promise<RuleAmounts> {
  try {
    const res = await fetch(`${API}/coins/rules`, { next: { revalidate: 3600 } });
    if (!res.ok) return {};
    const body = (await res.json()) as { items?: EarnRule[] };
    return Object.fromEntries((body.items ?? []).map((rule) => [rule.code, rule.amount]));
  } catch {
    return {};
  }
}
