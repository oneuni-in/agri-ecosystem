import en from "./messages/en.json";
import hi from "./messages/hi.json";
import ta from "./messages/ta.json";

export const locales = ["en", "ta", "hi"] as const;
export type Locale = (typeof locales)[number];

export function isLocale(value: unknown): value is Locale {
  return typeof value === "string" && (locales as readonly string[]).includes(value);
}

const catalogs: Record<Locale, typeof en> = { en, ta, hi };

/** Component-string catalogs for next-intl (namespace `ui`). */
export function getUiMessages(locale: Locale): typeof en {
  return catalogs[locale];
}
