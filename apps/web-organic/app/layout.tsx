import type { SiteTheme } from "@agri/types";
import { fontVariables } from "@agri/ui/fonts";
import type { Metadata } from "next";
import type { ReactNode } from "react";

import "./globals.css";

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
      <body>{children}</body>
    </html>
  );
}
