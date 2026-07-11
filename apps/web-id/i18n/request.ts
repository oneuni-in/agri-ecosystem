import { getUiMessages, isLocale } from "@agri/ui/i18n";
import { getRequestConfig } from "next-intl/server";
import { cookies } from "next/headers";

/**
 * Locale = NEXT_LOCALE cookie (set by the language screen), else "en".
 * The cookie holds a locale code, never a token - localStorage stays empty
 * and agri_sid stays httpOnly (D09 non-negotiable 2).
 */
export default getRequestConfig(async ({ requestLocale }) => {
  const requested = await requestLocale;
  if (requested !== undefined && isLocale(requested)) {
    return { locale: requested, messages: getUiMessages(requested) };
  }
  const jar = await cookies();
  const fromCookie = jar.get("NEXT_LOCALE")?.value;
  const locale = isLocale(fromCookie) ? fromCookie : "en";
  return { locale, messages: getUiMessages(locale) };
});
