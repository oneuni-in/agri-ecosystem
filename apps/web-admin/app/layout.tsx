import type { SiteTheme } from "@agri/types";
import { ToastProvider } from "@agri/ui";
import { fontVariables } from "@agri/ui/fonts";
import type { Metadata } from "next";
import { NextIntlClientProvider } from "next-intl";
import type { ReactNode } from "react";

import "./globals.css";

import { AdminChrome } from "./admin-chrome";
import { SiteHeader } from "./site-header";

/** Design Spec §1.1 switches brand tokens off this attribute. */
const THEME: SiteTheme = "theme-agri";

export const metadata: Metadata = {
  title: "Agri Admin",
  description: "Internal moderation and operations console.",
};

export default function RootLayout({
  children,
}: Readonly<{ children: ReactNode }>) {
  return (
    <html lang="en" data-theme={THEME} className={fontVariables}>
      <body>
        <NextIntlClientProvider>
          <ToastProvider>
            <SiteHeader />
            <AdminChrome>{children}</AdminChrome>
          </ToastProvider>
        </NextIntlClientProvider>
      </body>
    </html>
  );
}
