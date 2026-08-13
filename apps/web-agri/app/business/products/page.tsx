import { ConsolePageHeader } from "@agri/ui";
import { redirect } from "next/navigation";
import { getTranslations } from "next-intl/server";

import { auth } from "@/lib/auth";

import { ProductsClient } from "./products-client";

export const metadata = { title: "Products", robots: { index: false } };

export default async function ProductsPage() {
  const user = await auth.getServerUser();
  if (!user) redirect("/api/auth/login?next=/business/products");
  const t = await getTranslations("ui.console.common");
  return (
    <main className="mx-auto max-w-3xl">
      <ConsolePageHeader title={t("pageTitle.products")} />
      <ProductsClient />
    </main>
  );
}
