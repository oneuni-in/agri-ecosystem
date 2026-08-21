import type { SiteTheme } from "@agri/types";
import { ToastProvider } from "@agri/ui";
import { fontVariables } from "@agri/ui/fonts";
import type { Metadata } from "next";
import { NextIntlClientProvider } from "next-intl";
import { getLocale } from "next-intl/server";
import { cookies } from "next/headers";
import type { ReactNode } from "react";

import "./globals.css";

import { NotificationBellWidget } from "./notification-bell";

/** Design Spec §1.1 switches brand tokens off this attribute. */
const THEME: SiteTheme = "theme-agri";

export const metadata: Metadata = {
  title: "AgriID",
  description: "Single sign-on for the agri ecosystem.",
};

export default async function RootLayout({
  children,
}: Readonly<{ children: ReactNode }>) {
  // AG-A63: locale comes from the NEXT_LOCALE cookie (i18n/request.ts) — the
  // login switcher and the post-auth language step both write it, and the
  // document language must follow it (web-agri's layout does the same).
  const locale = await getLocale();
  // The bell strip renders only for a signed-in visitor, decided HERE on the
  // server because the session cookie is httpOnly and the widget cannot read
  // it. Two things were wrong without this. The bell fetched
  // /notify/unread-count on every page including /login, and while it handles
  // the 401 correctly (it hides), the BROWSER still logs the failed request —
  // so the sign-in screen greeted a first-time visitor with console errors,
  // the AG-A1 defect class this project has already paid for twice. And the
  // strip itself rendered as an empty gradient band above the login card,
  // chrome the A7 reference does not have and that nothing occupied.
  const signedIn = (await cookies()).has("agri_sid");
  return (
    <html lang={locale} data-theme={THEME} className={fontVariables}>
      <body>
        <NextIntlClientProvider>
          <ToastProvider>
            {signedIn && (
              <div className="flex justify-end bg-header-gradient px-4 py-2">
                <NotificationBellWidget />
              </div>
            )}
            {children}
          </ToastProvider>
        </NextIntlClientProvider>
      </body>
    </html>
  );
}
