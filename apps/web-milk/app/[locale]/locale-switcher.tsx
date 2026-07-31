"use client";

import { useLocale, useTranslations } from "next-intl";
import { useSearchParams } from "next/navigation";
import type { ReactNode } from "react";

import { DevanagariGlyph, TamilGlyph } from "@/components/atoms/IndicGlyphs";
import { Link, usePathname } from "@/i18n/navigation";

/**
 * `த` (Tamil) and `हिं` (Devanagari) below are rendered as inline SVG glyph
 * outlines (see `components/atoms/IndicGlyphs.tsx`) instead of literal
 * characters. Fonts download on Unicode-range glyph *usage*, and this
 * switcher is in the header of every page - so the literal `हिं` glyph
 * forced ~121 KB of Noto Sans Devanagari onto every English/Tamil page for
 * a label nobody reads as running text (issue #45).
 *
 * `name` below is the accessible name (identical to the old literal glyph
 * text, so e2e's `getByRole("link", { name: ... })` selectors are
 * unaffected); `content` is what actually paints - text for `en`, an SVG
 * for `ta`/`hi`. `aria-hidden` on the glyphs + the Link's `aria-label` keep
 * the accessible name from being announced twice.
 */
const LABELS: Record<"en" | "ta" | "hi", { name: string; content: ReactNode }> = {
  en: { name: "EN", content: "EN" },
  ta: { name: "த", content: <TamilGlyph /> },
  hi: { name: "हिं", content: <DevanagariGlyph /> },
};

// `usePathname()` (next-intl) excludes the query string, so switching
// locale on e.g. /search?q=milk or /641001?category=veterinarian would
// otherwise silently drop it. `useSearchParams()` requires a Suspense
// boundary in a static page (see view-beacon.tsx) - the caller
// (site-header.tsx) wraps <LocaleSwitcher /> accordingly.
export function LocaleSwitcher() {
  const pathname = usePathname();
  const searchParams = useSearchParams();
  const query = searchParams.toString();
  const href = query ? `${pathname}?${query}` : pathname;
  const active = useLocale();
  const t = useTranslations("ui.localeSwitcher");
  return (
    <nav aria-label={t("label")} className="flex items-center gap-0.5">
      {(Object.keys(LABELS) as Array<keyof typeof LABELS>).map((locale) => (
        <Link
          key={locale}
          href={href}
          locale={locale}
          prefetch={false}
          aria-label={LABELS[locale].name}
          aria-current={locale === active ? "true" : undefined}
          className={`flex min-h-11 min-w-11 items-center justify-center rounded-card px-1.5 text-[12.5px] font-bold no-underline ${
            locale === active ? "bg-brand-soft text-brand-deep" : "text-sub"
          }`}
        >
          {LABELS[locale].content}
        </Link>
      ))}
    </nav>
  );
}
