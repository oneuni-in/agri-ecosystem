import { ConsolePageHeader } from "@agri/ui";
import { redirect } from "next/navigation";
import { getTranslations } from "next-intl/server";

import { auth } from "@/lib/auth";

import { ReviewsClient } from "./reviews-client";

export const metadata = { title: "Reviews", robots: { index: false } };

export default async function ReviewsPage() {
  const user = await auth.getServerUser();
  if (!user) redirect("/api/auth/login?next=/business/reviews");
  const t = await getTranslations("ui.console.common");
  return (
    <main className="mx-auto max-w-3xl">
      <ConsolePageHeader title={t("pageTitle.reviews")} />
      <ReviewsClient />
    </main>
  );
}
