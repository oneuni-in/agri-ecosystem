import { themeColors } from "@agri/config/theme-colors";
import type { SiteTheme } from "@agri/types";
import { fontVariables } from "@agri/ui/fonts";
import type { Metadata, Viewport } from "next";
import { hasLocale, NextIntlClientProvider } from "next-intl";
import { setRequestLocale } from "next-intl/server";
import { notFound } from "next/navigation";
import type { ReactNode } from "react";

import { GlobalAdBanner } from "@/components/organisms/GlobalAdBanner";
import { routing } from "@/i18n/routing";

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
      <body>
        <NextIntlClientProvider>
          <SiteHeader />
          {/* M2: milk_global_header ad slot on EVERY page. Client island -
              the layout stays static (no headers()/cookies() here). */}
          <GlobalAdBanner />
          {children}
          <SiteFooter />
          <PwaClient />
        </NextIntlClientProvider>
      </body>
    </html>
  );
}
