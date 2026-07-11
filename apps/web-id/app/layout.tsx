import type { SiteTheme } from "@agri/types";
import { ToastProvider } from "@agri/ui";
import { fontVariables } from "@agri/ui/fonts";
import type { Metadata } from "next";
import { NextIntlClientProvider } from "next-intl";
import type { ReactNode } from "react";

import "./globals.css";

/** Design Spec §1.1 switches brand tokens off this attribute. */
const THEME: SiteTheme = "theme-agri";

export const metadata: Metadata = {
  title: "AgriID",
  description: "Single sign-on for the agri ecosystem.",
};

export default function RootLayout({
  children,
}: Readonly<{ children: ReactNode }>) {
  return (
    <html lang="en" data-theme={THEME} className={fontVariables}>
      <body>
        <NextIntlClientProvider>
          <ToastProvider>{children}</ToastProvider>
        </NextIntlClientProvider>
      </body>
    </html>
  );
}
