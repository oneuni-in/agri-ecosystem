import { ConsolePageHeader } from "@agri/ui";
import { redirect } from "next/navigation";
import { getTranslations } from "next-intl/server";

import { auth } from "@/lib/auth";

import { NotificationsPrefsClient } from "./notifications-prefs-client";

export const metadata = { title: "Notifications", robots: { index: false } };

export default async function NotificationsPrefsPage() {
  const user = await auth.getServerUser();
  if (!user) redirect("/api/auth/login?next=/business/notifications");
  const t = await getTranslations("ui.console.common");
  return (
    <main className="mx-auto max-w-3xl">
      <ConsolePageHeader title={t("pageTitle.notifications")} />
      <NotificationsPrefsClient />
    </main>
  );
}
