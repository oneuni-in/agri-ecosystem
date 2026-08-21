import { NextIntlClientProvider } from "next-intl";
import type { Metadata } from "next";

import { pickUiMessages } from "@/lib/client-messages";
import { NotificationsClient } from "./notifications-client";

export const metadata: Metadata = { title: "Notifications", robots: { index: false } };

export default async function NotificationsPage() {
  return (
    <main className="mx-auto max-w-[720px] px-4 py-6">
      {/* AG-A8: nested provider — this route pays for its own client catalog */}
      <NextIntlClientProvider messages={await pickUiMessages(["notifications"])}>
        <NotificationsClient />
      </NextIntlClientProvider>
    </main>
  );
}
