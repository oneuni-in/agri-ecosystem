import type { ReactNode } from "react";

import "./globals.css";

/**
 * Root passthrough (D27): locale routing lives under `app/[locale]`, which
 * owns `<html>`/`<body>` and the next-intl provider. This shell only pulls in
 * global CSS so it applies to every locale segment.
 */
export default function RootLayout({ children }: Readonly<{ children: ReactNode }>) {
  return children;
}
