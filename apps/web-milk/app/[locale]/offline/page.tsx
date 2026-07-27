import type { Metadata } from "next";
import { getTranslations, setRequestLocale } from "next-intl/server";

import { OfflineStatus } from "./offline-status";

export const metadata: Metadata = {
  title: "Offline — Milk.in",
  robots: { index: false, follow: false },
};

/** The SW-precached offline shell (D28): helplines that work without
 * internet + the last-seen public price summary from localStorage. Static
 * page, zero fetches — it must render from cache with the network gone. */
export default async function OfflinePage({ params }: { params: Promise<{ locale: string }> }) {
  const { locale } = await params;
  setRequestLocale(locale);
  const t = await getTranslations("ui.offline");
  return (
    <main
      className="mx-auto flex w-full max-w-[720px] flex-col gap-4 px-4 py-8"
      data-testid="offline-shell"
    >
      <h1 className="font-display text-[22px] font-extrabold text-ink">{t("title")}</h1>
      <p className="text-[15px] text-sub">{t("body")}</p>
      <section className="rounded-card border border-line bg-card p-4">
        <h2 className="font-display text-[16px] font-extrabold text-ink">{t("helplineTitle")}</h2>
        <p className="text-[15px] text-ink">
          {t("vetHelpline")}:{" "}
          <a className="font-bold text-brand-deep" href="tel:1962">
            1962
          </a>
        </p>
        <p className="text-[15px] text-ink">
          {t("kisanHelpline")}:{" "}
          <a className="font-bold text-brand-deep" href="tel:18001801551">
            1800-180-1551
          </a>{" "}
          {/* KCC runs 6am-10pm (verified against ICAR/MANAGE). Offline is
              exactly when the user cannot look this up, so a number without
              its hours invites a dead call at midnight. */}
          <span className="text-[13px] text-sub">({t("kisanHours")})</span>
        </p>
      </section>
      <OfflineStatus title={t("lastSeenTitle")} />
    </main>
  );
}
