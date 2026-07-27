import { getUiMessages } from "@agri/ui/i18n";
import { hasLocale } from "next-intl";
import { getRequestConfig } from "next-intl/server";

import { routing } from "./routing";

/**
 * Locale routing (D27): web-milk now serves en/ta/hi under an `[locale]`
 * segment. Static rendering is preserved NOT by avoiding `requestLocale`
 * (the old D02 pin) but by every page calling `setRequestLocale(locale)`
 * before rendering — that supplies the locale without touching `headers()`,
 * so `/`, `/ta`, `/hi` still prerender (○/●). `requestLocale` here resolves
 * to the segment param on those static builds; it only falls back to
 * `defaultLocale` for unmatched inputs.
 */
export default getRequestConfig(async ({ requestLocale }) => {
  const requested = await requestLocale;
  const locale = hasLocale(routing.locales, requested) ? requested : routing.defaultLocale;
  return { locale, messages: getUiMessages(locale) };
});
