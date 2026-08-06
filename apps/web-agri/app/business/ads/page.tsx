import { redirect } from "next/navigation";

import { auth } from "@/lib/auth";

import { AdsConsoleClient } from "./ads-console-client";

export const metadata = { title: "Advertise", robots: { index: false } };

export default async function AdsPage() {
  const user = await auth.getServerUser();
  if (!user) redirect("/api/auth/login?next=/business/ads");
  return (
    <main className="mx-auto max-w-3xl px-4 py-6">
      <h1 className="font-display text-[20px] font-extrabold text-ink">Advertise</h1>
      <AdsConsoleClient />
    </main>
  );
}
