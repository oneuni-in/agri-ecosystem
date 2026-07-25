"use client";

import { useLocale, useTranslations } from "next-intl";
import { useSearchParams } from "next/navigation";

import { Link, usePathname } from "@/i18n/navigation";

const LABELS = { en: "EN", ta: "த", hi: "हिं" } as const;

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
          aria-current={locale === active ? "true" : undefined}
          className={`flex min-h-11 min-w-11 items-center justify-center rounded-card px-1.5 text-[12.5px] font-bold no-underline ${
            locale === active ? "bg-brand-soft text-brand-deep" : "text-sub"
          }`}
        >
          {LABELS[locale]}
        </Link>
      ))}
    </nav>
  );
}
