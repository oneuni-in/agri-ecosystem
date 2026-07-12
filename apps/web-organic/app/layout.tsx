import type { SiteTheme } from "@agri/types";
import { fontVariables } from "@agri/ui/fonts";
import type { Metadata } from "next";
import { NextIntlClientProvider } from "next-intl";
import type { ReactNode } from "react";

import "./globals.css";

import { SiteHeader } from "./site-header";

/** Design Spec §1.1 switches brand tokens off this attribute. */
const THEME: SiteTheme = "theme-organic";

export const metadata: Metadata = {
  title: "OrganicStore.in",
  description: "Certified organic catalog and where-to-buy.",
};

export default function RootLayout({
  children,
}: Readonly<{ children: ReactNode }>) {
  return (
    <html lang="en" data-theme={THEME} className={fontVariables}>
      <body>
        <NextIntlClientProvider>
          <SiteHeader />
          {children}
        </NextIntlClientProvider>
      </body>
    </html>
  );
}
