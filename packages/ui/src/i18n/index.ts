import en from "./messages/en.json";
import hi from "./messages/hi.json";
import ta from "./messages/ta.json";

export const locales = ["en", "ta", "hi"] as const;
export type Locale = (typeof locales)[number];

export function isLocale(value: unknown): value is Locale {
  return typeof value === "string" && (locales as readonly string[]).includes(value);
}

const catalogs: Record<Locale, typeof en> = { en, ta, hi };

/**
 * Component-string catalog for next-intl (namespace `ui`), WITHOUT the
 * vendor-console strings (`ui.console.*`).
 *
 * Consumer apps (milk/organic/id/admin) never render the vendor console, so
 * shipping its form labels, validation and error strings in every page's
 * hydration payload is pure weight — U2 grew `ui.console` by ~10KB (en) /
 * ~22KB (ta) / ~19KB (hi), which pushed theorganic.in's home below the
 * Lighthouse 0.90 floor. web-agri (the only console app) loads the full
 * catalog via `getConsoleUiMessages` instead. Return type stays `typeof en`
 * on purpose: no caller's types change; the console subtree is simply absent
 * at runtime for apps that never reference it.
 */
export function getUiMessages(locale: Locale): typeof en {
  const catalog = catalogs[locale];
  const ui = { ...catalog.ui };
  delete (ui as { console?: unknown }).console;
  return { ...catalog, ui } as typeof en;
}

/** Full catalog including `ui.console.*` — only the console app (web-agri)
 * loads this; every other app uses the leaner `getUiMessages`. */
export function getConsoleUiMessages(locale: Locale): typeof en {
  return catalogs[locale];
}
