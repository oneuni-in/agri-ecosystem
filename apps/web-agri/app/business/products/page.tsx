import { redirect } from "next/navigation";

import { auth } from "@/lib/auth";

import { ProductsClient } from "./products-client";

export const metadata = { title: "Products", robots: { index: false } };

export default async function ProductsPage() {
  const user = await auth.getServerUser();
  if (!user) redirect("/api/auth/login?next=/business/products");
  return (
    <main className="mx-auto max-w-3xl px-4 py-6">
      <h1 className="font-display text-[20px] font-extrabold text-ink">Products</h1>
      <ProductsClient />
    </main>
  );
}
