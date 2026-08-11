import { themeColors } from "@agri/config/theme-colors";
import type { SiteTheme } from "@agri/types";
import { fontVariables } from "@agri/ui/fonts";
import type { Metadata, Viewport } from "next";
import { hasLocale, NextIntlClientProvider } from "next-intl";
import { setRequestLocale } from "next-intl/server";
import { notFound } from "next/navigation";
import type { ReactNode } from "react";

import { routing } from "@/i18n/routing";

import { MilkBottomNav } from "./milk-bottom-nav";
import { PwaClient } from "./pwa-client";
import { SiteFooter } from "./site-footer";
import { SiteHeader } from "./site-header";

/** Design Spec §1.1 switches brand tokens off this attribute. */
const THEME: SiteTheme = "theme-milk";

export const metadata: Metadata = {
  title: "Milk.in",
  description: "Pincode-first dairy discovery.",
  manifest: "/manifest.webmanifest",
  appleWebApp: { capable: true, title: "Milk.in", statusBarStyle: "default" },
  icons: { apple: "/icons/apple-touch-icon.png" },
};

export const viewport: Viewport = { themeColor: themeColors[THEME].brand };

export function generateStaticParams() {
  return routing.locales.map((locale) => ({ locale }));
}

export default async function LocaleLayout({
  children,
  params,
}: Readonly<{ children: ReactNode; params: Promise<{ locale: string }> }>) {
  const { locale } = await params;
  if (!hasLocale(routing.locales, locale)) notFound();
  // Static-rendering guarantee: supplies the locale to next-intl without
  // reading headers(), so every page under [locale] can prerender.
  setRequestLocale(locale);
  return (
    <html lang={locale} data-theme={THEME} className={fontVariables}>
      {/* §12: the bottom nav is `position: fixed`, so the body reserves its
          height (plus the iOS safe-area inset) — otherwise the last footer row
          sits underneath it. `md:pb-0` drops the reservation where the bar
          itself is hidden. */}
      <body className="pb-[calc(64px+env(safe-area-inset-bottom))] md:pb-0">
        <NextIntlClientProvider>
          <SiteHeader locale={locale} />
          {/* The M2 milk_global_header slot used to mount here, on EVERY page.
              It is not in the approved reference, and above the home's
              full-bleed §3 hero it put two ad units above the fold. The home
              hero (milk_home_hero_xl) is now the page's head placement; this
              slot's inventory moves to the pages that have no hero of their
              own rather than stacking on top of one. */}
          {children}
          <SiteFooter locale={locale} />
          <MilkBottomNav />
          <PwaClient />
        </NextIntlClientProvider>
      </body>
    </html>
  );
}
