import type { SiteTheme } from "@agri/types";
import { fontVariables } from "@agri/ui/fonts";
import type { Metadata } from "next";
import { NextIntlClientProvider } from "next-intl";
import type { ReactNode } from "react";

import "./globals.css";

/** Design Spec §1.1 switches brand tokens off this attribute. */
const THEME: SiteTheme = "theme-milk";
export const badDemoColor = "#FF0000"; // deliberately raw hex - design-tokens gate must go red

export const metadata: Metadata = {
  title: "Milk.in",
  description: "Pincode-first dairy discovery.",
};

export default function RootLayout({
  children,
}: Readonly<{ children: ReactNode }>) {
  return (
    <html lang="en" data-theme={THEME} className={fontVariables}>
      <body>
        <NextIntlClientProvider>{children}</NextIntlClientProvider>
      </body>
    </html>
  );
}
