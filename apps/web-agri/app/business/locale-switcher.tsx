"use client";

/**
 * Console locale switcher (U2). Sets the NEXT_LOCALE cookie the request
 * config reads and reloads — server components re-render in the chosen
 * locale. Language names are written in their own language (never
 * translated — the design-system rule the milk LocaleSwitcher follows).
 */
import { cn } from "@agri/ui";
import { useLocale, useTranslations } from "next-intl";

const LOCALES = [
  { code: "en", label: "EN" },
  { code: "ta", label: "தமிழ்" },
  { code: "hi", label: "हिंदी" },
] as const;

export function ConsoleLocaleSwitcher() {
  const t = useTranslations("ui.console.common");
  const active = useLocale();

  const switchTo = (code: string) => {
    document.cookie = `NEXT_LOCALE=${code}; path=/; max-age=31536000; samesite=lax`;
    window.location.reload();
  };

  return (
    <div role="group" aria-label={t("language")} className="flex gap-1">
      {LOCALES.map((locale) => (
        <button
          key={locale.code}
          type="button"
          lang={locale.code}
          aria-pressed={locale.code === active}
          className={cn(
            // `min-w-[44px]` as well as the height: "EN" is only 41px wide
            // at this padding, which clears the tap floor in one dimension
            // and misses it in the other.
            "min-h-[44px] min-w-[44px] rounded-pill px-3 text-[12px] font-semibold",
            locale.code === active ? "bg-brand-soft text-brand-deep" : "text-sub hover:bg-line",
          )}
          onClick={() => switchTo(locale.code)}
        >
          {locale.label}
        </button>
      ))}
    </div>
  );
}
