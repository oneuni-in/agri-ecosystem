import { NextIntlClientProvider } from "next-intl";
import type { Metadata } from "next";
import { getTranslations } from "next-intl/server";

import { pickUiMessages } from "@/lib/client-messages";

import { NotificationsClient } from "./notifications-client";
import { NotificationPrefs } from "./prefs-client";

export const metadata: Metadata = { title: "Notifications", robots: { index: false } };

/**
 * The feed, plus the channels it can reach you on (AG-U5 P4 adds the second
 * half). The feed itself is unchanged — the shell mounts modules, it does not
 * rewrite them.
 */
export default async function NotificationsPage() {
  const t = await getTranslations("ui.account.prefs");
  return (
    <main className="mx-auto max-w-[720px] px-4 py-6">
      {/* AG-A8: nested provider — this route pays for its own client catalog */}
      <NextIntlClientProvider messages={await pickUiMessages(["notifications"])}>
        <NotificationsClient />
      </NextIntlClientProvider>
      {/* Deliberately OUTSIDE that provider: the prefs island takes its copy
          as props, so `ui.account` never enters a client catalog at all. */}
      <NotificationPrefs
        copy={{
          title: t("title"),
          hint: t("hint"),
          sms: t("sms"),
          email: t("email"),
          push: t("push"),
          on: t("on"),
          off: t("off"),
          saved: t("saved"),
          loadFailed: t("loadFailed"),
          saveFailed: t("saveFailed"),
        }}
      />
    </main>
  );
}
