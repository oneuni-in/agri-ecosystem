import { redirect } from "next/navigation";

import { auth } from "@/lib/auth";

import { PremiumClient } from "./premium-client";

export const metadata = { title: "Premium", robots: { index: false } };

const API = process.env.API_BASE_URL ?? "http://127.0.0.1:8000";

async function billingLive(): Promise<boolean> {
  const token = await auth.getAccessToken();
  if (!token) return false;
  try {
    const response = await fetch(`${API}/billing/subscription`, {
      headers: { authorization: `Bearer ${token}` },
      cache: "no-store",
    });
    return response.status !== 404;
  } catch {
    return false;
  }
}

export default async function PremiumPage() {
  const user = await auth.getServerUser();
  if (!user) redirect("/api/auth/login?next=/business/premium");
  const live = await billingLive();
  return (
    <main className="mx-auto max-w-3xl px-4 py-6">
      <h1 className="font-display text-[20px] font-extrabold text-ink">Premium</h1>
      <PremiumClient billingLive={live} />
    </main>
  );
}
