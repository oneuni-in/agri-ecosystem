import { redirect } from "next/navigation";

import { auth } from "@/lib/auth";

import { ListingsClient } from "./listings-client";

export const metadata = { title: "Listings", robots: { index: false } };

export default async function ListingsPage() {
  const user = await auth.getServerUser();
  if (!user) redirect("/api/auth/login?next=/business/listings");
  return (
    <main className="mx-auto max-w-3xl px-4 py-6">
      <h1 className="font-display text-[20px] font-extrabold text-ink">Listings</h1>
      <ListingsClient />
    </main>
  );
}
