"use client";

/**
 * Pre-auth login locale switcher (A-U4b O4, AG-A63). The post-auth language
 * STEP persists a choice to the account — but a Tamil-first user had to read
 * the entire flow in English to reach it. This control sits above every step
 * and needs NO session: it sets the NEXT_LOCALE cookie `i18n/request.ts`
 * reads and calls router.refresh(), so the layout's server render (and the
 * NextIntlClientProvider messages it feeds this client tree) re-resolve in
 * the chosen locale immediately — while React state (typed phone, current
 * step) survives the refresh untouched.
 *
 * Markup mirrors web-agri's A1 §2 `.lang` treatment (EN · த · हि one-tap
 * buttons, never a hamburger/dropdown); colors are the light-surface tokens
 * because this page sits on cream, not the brand header. Language glyphs are
 * written in their own script (never translated — the design-system rule).
 *
 * Accessible names are the glyphs themselves (with `lang` set so AT switches
 * voice), NOT aria-label={full name} like the header switcher: this page's
 * language STEP already has a button accessibly named "English", and
 * e2e/helpers.ts clicks it by `name: /english/i` — a second button named
 * "English" here would be a Playwright strict-mode collision. The full name
 * rides along as `title` (description, not name).
 */
import { cn } from "@agri/ui";
import { useLocale, useTranslations } from "next-intl";
import { useRouter } from "next/navigation";

const LOCALES = [
  { code: "en", glyph: "EN", name: "English" },
  { code: "ta", glyph: "த", name: "தமிழ்" },
  { code: "hi", glyph: "हि", name: "हिंदी" },
] as const;

export function LoginLocaleSwitcher() {
  const t = useTranslations("ui.localeSwitcher");
  const active = useLocale();
  const router = useRouter();

  const switchTo = (code: string) => {
    // a locale code, never a token (agri_sid stays httpOnly) — same cookie
    // the post-auth language step writes, so the two never fight.
    document.cookie = `NEXT_LOCALE=${code}; path=/; max-age=31536000; samesite=lax`;
    router.refresh();
  };

  return (
    <div role="group" aria-label={t("label")} className="flex items-center justify-center">
      {LOCALES.map((locale, index) => (
        <span key={locale.code} className="flex items-center">
          {index > 0 ? (
            <span aria-hidden="true" className="text-[12px] text-muted">
              ·
            </span>
          ) : null}
          <button
            type="button"
            lang={locale.code}
            title={locale.name}
            aria-pressed={locale.code === active}
            className={cn(
              // Real 44px box, not the `.tap-target` overlay: this page has
              // the vertical room, and the button's own box is what WCAG
              // 2.5.8 / Lighthouse target-size actually measure.
              "inline-flex min-h-[44px] min-w-[44px] items-center justify-center px-2 text-[13px]",
              "focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-brand",
              locale.code === active ? "font-extrabold text-brand-deep" : "font-semibold text-sub",
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
