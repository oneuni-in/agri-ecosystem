import { getUiMessages, isLocale } from "@agri/ui/i18n";
import { cookies } from "next/headers";
import { getRequestConfig } from "next-intl/server";

/**
 * No locale ROUTING yet (D02's note stands — no /ta URL segment). U2 adds
 * the smallest reversible mechanism instead: the NEXT_LOCALE cookie, set by
 * the console's locale switcher, picks the request locale; absent or
 * unknown values fall back to "en". A later spec can still move to
 * URL-segment routing without unwinding this (next-intl's middleware writes
 * the same cookie).
 */
export default getRequestConfig(async ({ requestLocale }) => {
  const requested = await requestLocale;
  let locale = requested !== undefined && isLocale(requested) ? requested : undefined;
  if (!locale) {
    const cookie = (await cookies()).get("NEXT_LOCALE")?.value;
    locale = isLocale(cookie) ? cookie : "en";
  }
  return { locale, messages: getUiMessages(locale) };
});
