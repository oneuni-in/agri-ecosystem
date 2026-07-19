import { redirect } from "next/navigation";

import { auth } from "@/lib/auth";

import { InboxClient } from "./inbox-client";

export const metadata = { title: "Lead inbox", robots: { index: false } };

export default async function InboxPage() {
  const user = await auth.getServerUser();
  if (!user) redirect("/api/auth/login?next=/business/inbox");
  return (
    <main className="mx-auto max-w-3xl px-4 py-6">
      <h1 className="font-display text-[20px] font-extrabold text-ink">Lead inbox</h1>
      <InboxClient />
    </main>
  );
}
