/**
 * A-U1 §9b — the sarkari services hub dataset (E5 verified official links).
 *
 * We LINK to official government portals only — agri.in never fetches or
 * stores anyone's records (DPDP + scope fence). Every entry was opened and
 * human-verified on its `verified_on` date; the UI renders the domain + the
 * stamp FROM this data, never hardcoded.
 *
 * The entries live in `sarkari.json` (single source) so the AG-A11 link
 * checker — `scripts/check-sarkari-links.mjs`, run at launch prep — reads
 * the exact same rows this module serves to the page: URL host must end
 * with the declared official domain, domain must be on the gov.in/nic.in
 * allowlist, and the URL must resolve.
 *
 * A-U4b O2 (AG-A61): each entry also carries `detail` — the descriptive
 * copy the click-intercept dialog renders (what / eligibility / documents,
 * per locale) plus its own `source` + `last_verified` stamp. The copy is
 * E5-class: it describes what the OFFICIAL portal states, conservatively
 * worded, and is re-stamped whenever it is re-checked against the source.
 * DPDP still holds — the dialog is words only; the island fetches nothing.
 *
 * Titles/subs are i18n under `ui.agriHome.sarkari.{key}`.
 */
import type { SarkariText } from "../lib/sarkari";

import raw from "./sarkari.json";

export interface SarkariDetail {
  /** What the scheme/service is — descriptive only, never a status proxy. */
  what: SarkariText;
  /** Who is eligible, as stated by the scheme's published guidelines. */
  eligibility: SarkariText;
  /** Documents the OFFICIAL portal asks for — agri.in never collects them. */
  documents: SarkariText;
  /** The official domain the copy was checked against (equals `domain`). */
  source: string;
  /** ISO date the detail copy was last checked against `source`. */
  last_verified: string;
}

export interface SarkariLink {
  /** i18n key suffix under ui.agriHome.sarkari — title/sub live there. */
  key: string;
  /** Deep link to the official service page (https, official domain). */
  url: string;
  /** The official domain, rendered in the card stamp. */
  domain: string;
  /** ISO date the link was human-verified (rendered in the stamp). */
  verified_on: string;
  icon: string;
  /** AG-A61 — the detail-dialog copy for this entry. */
  detail: SarkariDetail;
}

export const SARKARI_LINKS: SarkariLink[] = raw.entries;
