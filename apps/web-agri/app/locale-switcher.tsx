"use client";

/**
 * Public-header locale switcher — A1 §2's compact "EN · த · हि" control.
 *
 * Same mechanism as the console's `ConsoleLocaleSwitcher` (U2): sets the
 * NEXT_LOCALE cookie that `i18n/request.ts` reads and reloads, so server
 * components re-render in the chosen locale. Language glyphs are written in
 * their own script (never translated — the design-system rule), with the
 * full language name as the accessible label.
 */
import { cn } from "@agri/ui";
import { useLocale, useTranslations } from "next-intl";

const LOCALES = [
  { code: "en", glyph: "EN", name: "English" },
  { code: "ta", glyph: "த", name: "தமிழ்" },
  { code: "hi", glyph: "हि", name: "हिंदी" },
] as const;

export function AgriLocaleSwitcher() {
  const t = useTranslations("ui.localeSwitcher");
  const active = useLocale();

  const switchTo = (code: string) => {
    document.cookie = `NEXT_LOCALE=${code}; path=/; max-age=31536000; samesite=lax`;
    window.location.reload();
  };

  return (
    <div role="group" aria-label={t("label")} className="flex items-center">
      {LOCALES.map((locale, index) => (
        <span key={locale.code} className="flex items-center">
          {index > 0 ? (
            <span aria-hidden="true" className="text-[11px] text-brand-soft">
              ·
            </span>
          ) : null}
          <button
            type="button"
            lang={locale.code}
            aria-label={locale.name}
            aria-pressed={locale.code === active}
            // `.tap-target` (§1.5): the visible control is a 13px glyph; the
            // overlay supplies the 44px hit box without growing the header row.
            className={cn(
              // min-h/min-w, not just `.tap-target`: the 44px ::after
              // overlay is invisible to Lighthouse's target-size audit,
              // which measures the button's own box (WCAG 2.5.8 wants
              // 24x24). The glyph stays 13px; only the hit box grows.
              "tap-target inline-flex min-h-[24px] min-w-[24px] items-center justify-center",
              "px-1 text-[13px]",
              locale.code === active ? "font-extrabold text-white" : "text-brand-soft",
            )}
            onClick={() => switchTo(locale.code)}
          >
            {locale.glyph}
          </button>
        </span>
      ))}
    </div>
  );
}
