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
 * Titles/subs are i18n under `ui.agriHome.sarkari.{key}`.
 */
import raw from "./sarkari.json";

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
}

export const SARKARI_LINKS: SarkariLink[] = raw.entries;
