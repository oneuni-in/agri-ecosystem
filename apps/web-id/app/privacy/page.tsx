import { Card } from "@agri/ui";
import { buildMetadata, canonicalUrl } from "@agri/ui/seo";
import type { Metadata } from "next";
import { getTranslations } from "next-intl/server";

const SITE = "https://id.agri.in";

/**
 * ID-U1 P1 — the destination for the login screen's DPDP sentence.
 *
 * It exists because the alternative was worse. The shipped flow rendered its
 * consent line as plain text with a comment explaining that a link 404ing on
 * a login screen beats a link to nothing; the A7 ADD asks for a real link,
 * and D57's gate item is "DPDP consent/export/delete verified" — a consent
 * sentence pointing nowhere is the weak half of that.
 *
 * It lives on id.agri.in rather than any vertical: the account, the phone
 * number and every DPDP right are owned by the identity app, and the three
 * consumer sites link INTO here rather than each keeping their own version
 * to drift.
 *
 * Public and indexable — unlike every other route in this app. A privacy
 * page nobody can find without signing in is not a privacy page.
 */
export const metadata: Metadata = buildMetadata({
  title: "How your data is handled — AgriID",
  description:
    "What AgriID stores, what it never does with your data, and the rights you have under the DPDP Act 2023.",
  canonical: canonicalUrl(SITE, "/privacy"),
  siteName: "AgriID",
});

export default async function PrivacyPage() {
  const t = await getTranslations("ui.auth.privacy");
  const sections = [
    { key: "store", title: t("storeTitle"), body: t("storeBody") },
    { key: "never", title: t("neverTitle"), body: t("neverBody") },
    { key: "choices", title: t("choicesTitle"), body: t("choicesBody") },
    { key: "rights", title: t("rightsTitle"), body: t("rightsBody") },
    { key: "otp", title: t("otpTitle"), body: t("otpBody") },
  ];
  return (
    <main className="mx-auto flex w-full max-w-[640px] flex-col gap-4 px-4 py-8">
      <h1 className="font-display text-2xl font-bold text-ink">{t("title")}</h1>
      <p className="text-sm leading-[1.6] text-sub">{t("intro")}</p>
      {sections.map((section) => (
        <Card key={section.key} className="space-y-1.5 p-4">
          <h2 className="font-display text-base font-bold text-ink">{section.title}</h2>
          <p className="text-sm leading-[1.6] text-sub">{section.body}</p>
        </Card>
      ))}
      <div className="flex flex-wrap gap-x-4 gap-y-2 text-sm">
        <a className="text-brand underline" href="/account">
          {t("profileLink")}
        </a>
        <a className="text-brand underline" href="/login">
          {t("backLink")}
        </a>
      </div>
    </main>
  );
}
