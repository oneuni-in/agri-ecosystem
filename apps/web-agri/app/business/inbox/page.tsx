import { ConsolePageHeader } from "@agri/ui";
import { redirect } from "next/navigation";
import { getTranslations } from "next-intl/server";

import { auth } from "@/lib/auth";

import { InboxClient } from "./inbox-client";

export const metadata = { title: "Lead inbox", robots: { index: false } };

export default async function InboxPage() {
  const user = await auth.getServerUser();
  if (!user) redirect("/api/auth/login?next=/business/inbox");
  const t = await getTranslations("ui.console.common");
  return (
    <main className="mx-auto max-w-3xl">
      <ConsolePageHeader title={t("pageTitle.inbox")} />
      <InboxClient />
    </main>
  );
}
