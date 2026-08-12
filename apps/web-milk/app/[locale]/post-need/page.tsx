import type { Metadata } from "next";
import { getTranslations, setRequestLocale } from "next-intl/server";

import { PostNeedForm } from "./post-need-form";

// Utility page (form): noindex keeps the Lighthouse/SEO public-page set
// unchanged. Static shell — the pincode prefill is read client-side from the
// agri_loc cookie so the page stays cacheable.
export const metadata: Metadata = {
  title: "Post my need — Milk.in",
  description: "Tell nearby milk vendors what you need — they reply, you choose.",
  robots: { index: false },
};

export default async function PostNeedPage({
  params,
}: {
  params: Promise<{ locale: string }>;
}) {
  const { locale } = await params;
  setRequestLocale(locale);
  const t = await getTranslations("ui.needs");
  return (
    <main className="mx-auto max-w-[720px] space-y-4 px-4 py-6">
      <header className="space-y-1">
        <h1 className="font-display text-[22px] font-extrabold text-ink">
          {t("title")}
          {locale === "en" ? (
            // The reference's designed Tamil accent — /en only; ta/hi carry
            // the fully translated title (same policy as the results CTA).
            <span className="vern font-normal"> · என் தேவை</span>
          ) : null}
        </h1>
        <p className="text-[13px] text-sub">{t("intro")}</p>
      </header>
      <PostNeedForm />
    </main>
  );
}
