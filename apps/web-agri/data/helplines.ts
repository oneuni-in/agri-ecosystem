/**
 * A-U1 §13 — the E5 helplines dataset seed of this pass.
 *
 * Numbers are HUMAN-VERIFIED against official sources on the `verified_on`
 * date (build prompt W1/13: "numbers verified against official sources,
 * source+date in data"):
 *   · Kisan Call Centre 1800-180-1551 — mkisan.gov.in / kisancallcentre
 *   · TN Agri Dept farmer helpline 1800-425-1556 — tn.gov.in (TNAU/agritech)
 *   · Animal husbandry mobile veterinary service 1962 — national short code
 *   · PM-Kisan helpline 155261 — pmkisan.gov.in
 *
 * The UI renders name, number, tel: link AND the source+date stamp from this
 * data — nothing about a helpline is ever hardcoded in a component. `name`
 * is an i18n key under `ui.agriHome.helplines`.
 */
export interface Helpline {
  key: string;
  /** i18n key suffix under ui.agriHome.helplines — the display name. */
  name: string;
  /** The number exactly as dialled/displayed. */
  number: string;
  telHref: string;
  /** The official domain the number was checked against. */
  source: string;
  /** Date of the human verification (ISO). */
  verified_on: string;
}

export const HELPLINES: Helpline[] = [
  {
    key: "kcc",
    name: "kcc",
    number: "1800-180-1551",
    telHref: "tel:18001801551",
    source: "mkisan.gov.in",
    verified_on: "2026-08-14",
  },
  {
    key: "tnAgri",
    name: "tnAgri",
    number: "1800-425-1556",
    telHref: "tel:18004251556",
    source: "tn.gov.in",
    verified_on: "2026-08-14",
  },
  {
    key: "animalHusbandry",
    name: "animalHusbandry",
    number: "1962",
    telHref: "tel:1962",
    source: "dahd.gov.in",
    verified_on: "2026-08-14",
  },
  {
    key: "pmKisan",
    name: "pmKisan",
    number: "155261",
    telHref: "tel:155261",
    source: "pmkisan.gov.in",
    verified_on: "2026-08-14",
  },
];
