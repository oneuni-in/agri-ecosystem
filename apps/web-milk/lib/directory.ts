const API = process.env.API_BASE_URL ?? "http://127.0.0.1:8000";

/**
 * Wire shape for `GET /directory/covers/{pincode}` (D15/D27 Task 2) — mirrors
 * `CoversItemOut` in `backend/core/modules/directory/schemas.py` field-for-
 * field. `lat`/`lng` are `Decimal | None` on the wire, which FastAPI/Pydantic
 * serializes as JSON strings (not numbers) — unlike `lib/milk.ts`'s
 * `MilkCard.lat/lng` (that endpoint's own choice of plain `number | null`),
 * these stay `string | null` end to end. `distance_m` uses the backend's
 * `UNLOCATABLE_M = 1_000_000_000` sentinel (`covers.py`) when neither the
 * business nor a branch resolves a location — callers must treat values `>=`
 * that sentinel as "no distance", never render it as a real number.
 */
export type CoversItem = {
  id: string;
  name: string;
  slug: string;
  type: string;
  verification_status: string;
  subscription_tier: string;
  primary_pincode: string;
  distance_m: number;
  lat: string | null;
  lng: string | null;
};

export interface CoversPage {
  items: CoversItem[];
  next_cursor: string | null;
}

/** Server-side public read — direct to backend (NOT the BFF proxy), with
 * `next: { revalidate: 300 }` for ISR, mirroring `fetchMilkHome`'s style
 * exactly. Returns null on any non-ok response or thrown error so the page
 * can degrade gracefully instead of crashing. */
export async function fetchCovers(pincode: string, category: string): Promise<CoversPage | null> {
  try {
    const res = await fetch(
      `${API}/directory/covers/${encodeURIComponent(pincode)}?category=${encodeURIComponent(category)}`,
      { next: { revalidate: 300 } },
    );
    if (!res.ok) return null;
    return (await res.json()) as CoversPage;
  } catch {
    return null;
  }
}
