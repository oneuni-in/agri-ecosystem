import type { SiteTheme } from "@agri/types";
import { fontVariables } from "@agri/ui/fonts";
import type { Metadata } from "next";
import { NextIntlClientProvider } from "next-intl";
import { getLocale } from "next-intl/server";
import type { ReactNode } from "react";

import "./globals.css";

import { AgriBottomNav } from "./agri-bottom-nav";
import { SiteFooter } from "./site-footer";
import { SiteHeader } from "./site-header";

/** Design Spec §1.1 switches brand tokens off this attribute. */
const THEME: SiteTheme = "theme-agri";

export const metadata: Metadata = {
  title: "Agri.in",
  description: "The agriculture hub.",
};

export default async function RootLayout({
  children,
}: Readonly<{ children: ReactNode }>) {
  // U2: the request locale comes from the NEXT_LOCALE cookie (i18n/request.ts)
  const locale = await getLocale();
  return (
    <html lang={locale} data-theme={THEME} className={fontVariables}>
      {/* A1 §23: the bottom nav is `position: fixed`, so the body reserves
          its height (plus the iOS safe-area inset) — otherwise the last
          footer row sits underneath it. `md:pb-0` drops the reservation
          where the bar itself is hidden (milk's §12 lesson, verbatim). */}
      <body className="pb-[calc(64px+env(safe-area-inset-bottom))] md:pb-0">
        <NextIntlClientProvider>
          <SiteHeader />
          {children}
          <SiteFooter />
          <AgriBottomNav />
        </NextIntlClientProvider>
      </body>
    </html>
  );
}
