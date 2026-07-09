import type { SiteTheme } from "@agri/types";
import type { Metadata } from "next";
import type { ReactNode } from "react";

import "./globals.css";

/** Design Spec §1.1 switches brand tokens off this attribute. */
const THEME: SiteTheme = "theme-agri";

export const metadata: Metadata = {
  title: "Agri.in",
  description: "The agriculture hub.",
};

export default function RootLayout({
  children,
}: Readonly<{ children: ReactNode }>) {
  return (
    <html lang="en" data-theme={THEME}>
      <body>{children}</body>
    </html>
  );
}
