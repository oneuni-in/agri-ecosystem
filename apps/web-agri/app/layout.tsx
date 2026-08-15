import type { SiteTheme } from "@agri/types";
import { fontVariablesSystemIndic } from "@agri/ui/fonts-latin";
import type { Metadata } from "next";
import { NextIntlClientProvider } from "next-intl";
import { getLocale, getMessages } from "next-intl/server";
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

/**
 * AG-A8 (perf floor): the zero-config provider serializes the ENTIRE ui
 * catalog (~44 KB raw per locale) into every page's flight payload, for the
 * benefit of the handful of client islands. Server components read the full
 * catalog regardless — only CLIENT-side useTranslations() needs messages
 * here, so only those namespaces ship. Adding a client island with a new
 * namespace? Add it to this list, or its strings render as raw keys.
 */
const CLIENT_NAMESPACES = [
  "console", // /business console clients
  "location",
  "notifications",
  "localeSwitcher",
  "agriHome.alert", // MandiAlertCard island
  "agriHome.soonPage", // /c/[slug] NotifyMeForm island
  "tools", // /tools calculator island
] as const;

function pickClientMessages(all: Record<string, unknown>): Record<string, unknown> {
  const ui = (all.ui ?? {}) as Record<string, unknown>;
  const picked: Record<string, unknown> = {};
  for (const path of CLIENT_NAMESPACES) {
    const keys = path.split(".");
    let src: unknown = ui;
    for (const k of keys) src = (src as Record<string, unknown> | undefined)?.[k];
    if (src === undefined) continue;
    let dst = picked;
    for (const k of keys.slice(0, -1)) {
      dst[k] = dst[k] ?? {};
      dst = dst[k] as Record<string, unknown>;
    }
    dst[keys[keys.length - 1] as string] = src;
  }
  return { ui: picked };
}

export default async function RootLayout({
  children,
}: Readonly<{ children: ReactNode }>) {
  // U2: the request locale comes from the NEXT_LOCALE cookie (i18n/request.ts)
  const locale = await getLocale();
  const messages = pickClientMessages(await getMessages());
  return (
    <html lang={locale} data-theme={THEME} className={fontVariablesSystemIndic}>
      {/* A1 §23: the bottom nav is `position: fixed`, so the body reserves
          its height (plus the iOS safe-area inset) — otherwise the last
          footer row sits underneath it. `md:pb-0` drops the reservation
          where the bar itself is hidden (milk's §12 lesson, verbatim). */}
      <body className="pb-[calc(64px+env(safe-area-inset-bottom))] md:pb-0">
        <NextIntlClientProvider messages={messages}>
          <SiteHeader />
          {children}
          <SiteFooter />
          <AgriBottomNav />
        </NextIntlClientProvider>
      </body>
    </html>
  );
}
