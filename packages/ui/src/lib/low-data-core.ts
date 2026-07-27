/** Low-data mode (D28) cookie logic, kept pure for node-env unit tests.
 * The explicit cookie always wins; when unset, the browser's Save-Data
 * signal decides. Client-only by design: ISR pages must not vary on
 * cookies, so SSR always renders the default and effects apply on mount. */

export const LOW_DATA_COOKIE = "milk_lowdata";

export function parseLowDataCookie(cookieHeader: string, saveData: boolean): boolean {
  const match = cookieHeader.match(new RegExp(`(?:^|; )${LOW_DATA_COOKIE}=([^;]*)`));
  if (match) return match[1] === "1";
  return saveData;
}

export function lowDataCookieString(on: boolean): string {
  return `${LOW_DATA_COOKIE}=${on ? "1" : "0"}; path=/; max-age=31536000; samesite=lax`;
}
