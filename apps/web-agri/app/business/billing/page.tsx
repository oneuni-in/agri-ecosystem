import { notFound, redirect } from "next/navigation";

import { auth } from "@/lib/auth";

import { BillingClient } from "./billing-client";

export const metadata = { title: "Subscription & invoices", robots: { index: false } };

const API = process.env.API_BASE_URL ?? "http://127.0.0.1:8000";

export default async function BillingPage() {
  const user = await auth.getServerUser();
  if (!user) redirect("/api/auth/login?next=/business/billing");
  const token = await auth.getAccessToken();
  const response = await fetch(`${API}/billing/subscription`, {
    headers: { authorization: `Bearer ${token}` },
    cache: "no-store",
  });
  if (response.status === 404) notFound(); // billing_enabled off: page does not exist
  return (
    <main>
      <h1 className="font-display text-[20px] font-extrabold text-ink">
        Subscription &amp; invoices
      </h1>
      <BillingClient />
    </main>
  );
}
