import type { Metadata } from "next";
import { redirect } from "next/navigation";

import { auth } from "@/lib/auth";

import { AdsManager } from "./ads-manager";

/** Private staff console page - never indexed. */
export const metadata: Metadata = {
  robots: { index: false, follow: false },
};

export default async function AdsPage() {
  const user = await auth.getServerUser();
  if (!user) redirect("/api/auth/login?next=/ads");
  return <AdsManager />;
}
