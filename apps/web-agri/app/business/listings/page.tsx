import { ConsolePageHeader } from "@agri/ui";
import { redirect } from "next/navigation";
import { getTranslations } from "next-intl/server";

import { auth } from "@/lib/auth";

import { ListingsClient } from "./listings-client";

export const metadata = { title: "Listings", robots: { index: false } };

export default async function ListingsPage() {
  const user = await auth.getServerUser();
  if (!user) redirect("/api/auth/login?next=/business/listings");
  const t = await getTranslations("ui.console.common");
  return (
    <main className="mx-auto max-w-3xl">
      <ConsolePageHeader title={t("pageTitle.listings")} />
      <ListingsClient />
    </main>
  );
}
