import type { Metadata } from "next";
import { setRequestLocale } from "next-intl/server";

import { NotificationsClient } from "./notifications-client";
import { PushAlertsCard } from "./push-alerts-card";

export const metadata: Metadata = { title: "Notifications", robots: { index: false } };

export default async function NotificationsPage({
  params,
}: {
  params: Promise<{ locale: string }>;
}) {
  const { locale } = await params;
  setRequestLocale(locale);
  return (
    <main className="mx-auto max-w-[720px] px-4 py-6">
      <PushAlertsCard />
      <NotificationsClient />
    </main>
  );
}
