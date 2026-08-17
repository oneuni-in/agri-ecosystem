/**
 * A-U3 W2 — the `/schemes` listing's data layer.
 *
 * Reads `/market/schemes`, which is the SAME service call the home
 * spotlight uses. That is the whole design: page and home cannot
 * disagree about what a scheme says or when it was last verified,
 * because there is one read and one set of rows behind both.
 *
 * `verified_against` + `verified_on` are rendered, never decorative. A
 * card whose stamp is old looks old, which is the point — the
 * alternative is a page that silently ages into being wrong.
 */
const API = process.env.API_BASE_URL ?? "http://127.0.0.1:8000";

/** Schemes change when a government notification changes them. An hour
 * is plenty, and the verified-on stamp travels IN the payload so a
 * cached page still tells the truth about its own age. */
const REVALIDATE_SECONDS = 3600;

export interface SchemeItem {
  level: "central" | "state" | string;
  state_label: Record<string, string> | null;
  title: Record<string, string>;
  body: Record<string, string>;
  /** Official domain the card was checked against. */
  verified_against: string;
  verified_on: string;
  url: string;
  link_label: Record<string, string>;
}

export interface SchemeDeadline {
  chip: string;
  title: Record<string, string>;
  note: Record<string, string> | null;
}

export interface SchemesBlock {
  items: SchemeItem[];
  deadlines: SchemeDeadline[];
}

/** Empty block on failure — the page then renders absent rather than
 * broken, and never invents a scheme. */
export async function fetchSchemes(): Promise<SchemesBlock> {
  try {
    const res = await fetch(`${API}/market/schemes`, {
      next: { revalidate: REVALIDATE_SECONDS },
    });
    if (!res.ok) return { items: [], deadlines: [] };
    return (await res.json()) as SchemesBlock;
  } catch {
    return { items: [], deadlines: [] };
  }
}
