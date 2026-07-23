import { getUiMessages } from "@agri/ui/i18n";
import { getRequestConfig } from "next-intl/server";

/**
 * No locale routing (D02): "en" is the only locale for web-milk. We resolve it
 * as a constant and deliberately DO NOT touch `requestLocale` — reading it calls
 * next-intl's `getRequestLocale()` -> `headers()`, a dynamic API that opts the
 * whole app into per-request (`ƒ`) rendering (see next-intl RequestLocale.js).
 * By never awaiting `requestLocale`, `headers()` is never invoked, so the home
 * and pincode routes can render as static/ISR (`○`) and their FCP/LCP stop
 * paying request-time SSR latency under Lighthouse's throttled model.
 *
 * Explicit non-"en" locales still work via `getTranslations({ locale })`, which
 * passes a `localeOverride` and bypasses this default entirely.
 *
 * web-milk only: web-agri/web-organic/web-id keep their own request.ts (web-id
 * legitimately reads the NEXT_LOCALE cookie), so this change is isolated.
 */
export default getRequestConfig(async () => {
  const locale = "en";
  return { locale, messages: getUiMessages(locale) };
});
