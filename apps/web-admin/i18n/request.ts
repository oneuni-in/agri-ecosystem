import { getUiMessages, isLocale } from "@agri/ui/i18n";
import { getRequestConfig } from "next-intl/server";

/**
 * No locale routing yet (D02): default is "en"; explicit locales come from
 * getTranslations({ locale }) callers. Locale routing lands with a later spec.
 */
export default getRequestConfig(async ({ requestLocale }) => {
  const requested = await requestLocale;
  const locale = requested !== undefined && isLocale(requested) ? requested : "en";
  return { locale, messages: getUiMessages(locale) };
});
