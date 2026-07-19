import { redirect } from "next/navigation";

import { auth } from "@/lib/auth";

import { InquiriesClient } from "./inquiries-client";

export const metadata = { title: "My inquiries", robots: { index: false } };

export default async function InquiriesPage() {
  const user = await auth.getServerUser();
  if (!user) redirect("/api/auth/login?next=/account/inquiries");
  return (
    <main className="mx-auto max-w-3xl px-4 py-6">
      <h1 className="font-display text-[20px] font-extrabold text-ink">My inquiries</h1>
      <InquiriesClient />
    </main>
  );
}
