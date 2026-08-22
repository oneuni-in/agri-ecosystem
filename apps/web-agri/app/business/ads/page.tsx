import { redirect } from "next/navigation";

import { auth } from "@/lib/auth";

import { AdsConsoleClient } from "./ads-console-client";

export const metadata = { title: "Advertise", robots: { index: false } };

/**
 * A-U7 W2 — `/business/ads`, the A3 reference's Campaigns page
 * (docs/design-reference/agri/agri_pages_console_v1.html#/ads).
 *
 * No wrapper and no heading here any more: the console shell supplies the
 * frame, and the topbar (eyebrow + title + the policy line) belongs to the
 * client component that also owns the "+ New campaign" action beside it.
 */
export default async function AdsPage() {
  const user = await auth.getServerUser();
  if (!user) redirect("/api/auth/login?next=/business/ads");
  return (
    <main>
      <AdsConsoleClient />
    </main>
  );
}
