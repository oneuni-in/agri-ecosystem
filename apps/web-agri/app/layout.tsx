import type { SiteTheme } from "@agri/types";
import { fontVariables } from "@agri/ui/fonts";
import type { Metadata } from "next";
import { NextIntlClientProvider } from "next-intl";
import { getLocale } from "next-intl/server";
import type { ReactNode } from "react";

import "./globals.css";

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
      <body>
        <NextIntlClientProvider>
          <SiteHeader />
          {children}
        </NextIntlClientProvider>
      </body>
    </html>
  );
}
