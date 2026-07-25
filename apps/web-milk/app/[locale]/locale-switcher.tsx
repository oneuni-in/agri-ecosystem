"use client";

import { useLocale, useTranslations } from "next-intl";

import { Link, usePathname } from "@/i18n/navigation";

const LABELS = { en: "EN", ta: "த", hi: "हिं" } as const;

export function LocaleSwitcher() {
  const pathname = usePathname();
  const active = useLocale();
  const t = useTranslations("ui.localeSwitcher");
  return (
    <nav aria-label={t("label")} className="flex items-center gap-0.5">
      {(Object.keys(LABELS) as Array<keyof typeof LABELS>).map((locale) => (
        <Link
          key={locale}
          href={pathname}
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
