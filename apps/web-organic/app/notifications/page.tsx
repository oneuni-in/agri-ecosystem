import type { Metadata } from "next";

import { NotificationsClient } from "./notifications-client";

export const metadata: Metadata = { title: "Notifications", robots: { index: false } };

export default function NotificationsPage() {
  return (
    <main className="mx-auto max-w-[720px] px-4 py-6">
      <NotificationsClient />
    </main>
  );
}
