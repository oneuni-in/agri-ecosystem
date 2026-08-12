import type { Metadata } from "next";
import { getTranslations, setRequestLocale } from "next-intl/server";

import { MyNeedsClient } from "./my-needs-client";

// Private per-user page: noindex, client-fetched through the auth BFF.
export const metadata: Metadata = {
  title: "My needs — Milk.in",
  robots: { index: false },
};

export default async function MyNeedsPage({
  params,
}: {
  params: Promise<{ locale: string }>;
}) {
  const { locale } = await params;
  setRequestLocale(locale);
  const t = await getTranslations("ui.needs");
  return (
    <main className="mx-auto max-w-[720px] space-y-4 px-4 py-6">
      <h1 className="font-display text-[22px] font-extrabold text-ink">
        {t("myTitle")}
        {locale === "en" ? (
          // Designed Tamil accent — /en only (results-CTA policy).
          <span className="vern font-normal"> · என் தேவைகள்</span>
        ) : null}
      </h1>
      <MyNeedsClient />
    </main>
  );
}
