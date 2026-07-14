import { buildMetadata, canonicalUrl } from "@agri/ui/seo";
import type { Metadata } from "next";
import { cookies } from "next/headers";
import { redirect } from "next/navigation";

import { NotificationsManager } from "./notifications-manager";

const SITE = "https://id.agri.in";

export const metadata: Metadata = buildMetadata({
  title: "Notifications — AgriID",
  description: "Your AgriID notifications",
  canonical: canonicalUrl(SITE, "/notifications"),
  siteName: "AgriID",
  noIndex: true,
});

export default async function NotificationsPage() {
  const jar = await cookies();
  const sid = jar.get("agri_sid")?.value;
  if (!sid) redirect("/login");
  return (
    <main className="mx-auto max-w-[720px] px-4 py-6">
      <NotificationsManager />
    </main>
  );
}
