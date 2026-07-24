import { redirect } from "next/navigation";

import { auth } from "@/lib/auth";

import { AnalyticsClient } from "./analytics-client";

export const metadata = { title: "Analytics", robots: { index: false } };

export default async function AnalyticsPage() {
  const user = await auth.getServerUser();
  if (!user) redirect("/api/auth/login?next=/business/analytics");
  return (
    <main className="mx-auto max-w-3xl px-4 py-6">
      <h1 className="font-display text-[20px] font-extrabold text-ink">Analytics</h1>
      <AnalyticsClient />
    </main>
  );
}
