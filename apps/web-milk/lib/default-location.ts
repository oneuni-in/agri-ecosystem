/**
 * Where a visitor with no location of their own starts.
 *
 * A guest who has not logged in, typed a pincode or granted GPS still sees a
 * real, populated home rather than an empty state. The header pill shows this
 * label and the server renders every section from this same pincode, so the
 * page can never be internally inconsistent.
 *
 * Its own module because BOTH sides need it: `lib/home.ts` is server-only
 * (it holds `API_BASE_URL` and server `fetch`), and importing that into the
 * client header island would drag server code into the browser bundle.
 *
 * `NEXT_PUBLIC_` so the value is identical on both sides of that boundary.
 */
export const DEFAULT_LOCATION = {
  pincode: process.env.NEXT_PUBLIC_DEFAULT_PINCODE ?? "641001",
  district: process.env.NEXT_PUBLIC_DEFAULT_DISTRICT ?? "Coimbatore",
} as const;
