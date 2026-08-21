import { Eyebrow, Wrap } from "@agri/ui";
import { getTranslations } from "next-intl/server";
import Link from "next/link";
import { redirect } from "next/navigation";

import { auth } from "@/lib/auth";
import { fetchEarnRules, EARN_CARDS } from "@/lib/coins";

import { CoinsClient } from "./coins-client";

/**
 * A-U4 W2 — the AgriCoins centre.
 *
 * `noindex`: a balance page is per-user and has nothing to offer a crawler.
 *
 * ONE WALLET, ONE BALANCE. There is no agri-specific balance here and there
 * is deliberately no way to make one: `coins.balances` holds a single row per
 * user, the engine is one schema shared across the family, and no per-vertical
 * column exists. A visitor who earned coins on milk.in sees the same number
 * here — not because this page reconciles anything, but because there is only
 * ever one figure to read. That is the cross-platform requirement satisfied by
 * construction rather than by synchronisation.
 *
 * The balance, history and referral code are fetched CLIENT-side through the
 * BFF proxy (`/api/coins/*`), which attaches the session's bearer token
 * server-side — tokens never touch JS (D10). The page itself only proves the
 * visitor is logged in and hands down the copy.
 */

export const metadata = { title: "AgriCoins", robots: { index: false } };

export default async function CoinsPage() {
  const user = await auth.getServerUser();
  if (!user) redirect("/api/auth/login?next=/account/coins");

  // Earn rules are public and cached, so the "how to earn" list renders from
  // the same source the home's cards use — the two can never disagree about
  // what a review is worth.
  const [t, rules] = await Promise.all([getTranslations("ui"), fetchEarnRules()]);

  return (
    <main className="bg-cream pb-10">
      <Wrap>
        <nav className="mt-3.5 flex flex-wrap items-center gap-1.5 text-[11.5px] text-muted">
          <Link href="/" prefetch={false} className="tap-target text-brand no-underline">
            {t("agriHome.categoriesPage.crumbHome")}
          </Link>
          <span aria-hidden="true" className="text-cream-line">
            ›
          </span>
          <span>{t("agriCoins.heading")}</span>
        </nav>

        <div className="mt-2 flex flex-wrap items-start gap-3.5">
          <span
            aria-hidden="true"
            className="flex h-[54px] w-[54px] flex-none items-center justify-center rounded-icon bg-coins-bg text-[26px]"
          >
            🪙
          </span>
          <div className="min-w-0">
            <Eyebrow>{t("agriCoins.eyebrow")}</Eyebrow>
            <h1 className="font-display text-[clamp(20px,2.6vw,28px)] font-semibold leading-[1.15]">
              {t("agriCoins.heading")}
            </h1>
            <p className="mt-[3px] text-[12.5px] text-sub">{t("agriCoins.sub")}</p>
          </div>
        </div>

        <CoinsClient
          copy={{
            balanceLabel: t("agriCoins.balanceLabel"),
            historyTitle: t("agriCoins.historyTitle"),
            historyEmpty: t("agriCoins.historyEmpty"),
            loadMore: t("agriCoins.loadMore"),
            referralTitle: t("agriCoins.referralTitle"),
            referralSub: t("agriCoins.referralSub"),
            copyCode: t("agriCoins.copyCode"),
            copied: t("agriCoins.copied"),
            shareWhatsapp: t("agriCoins.shareWhatsapp"),
            shareText: t("agriCoins.shareText"),
            error: t("agriCoins.error"),
            loading: t("agriCoins.loading"),
            notMoney: t("agriCoins.notMoney"),
          }}
          reasonLabels={REASON_KEYS.reduce<Record<string, string>>((acc, key) => {
            acc[key] = t(`coins.reason.${key}`);
            return acc;
          }, {})}
        />

        {/* How to earn — rendered from the SAME public rules read the home's
            cards use, so the two surfaces cannot disagree about what an
            action is worth. A card with no active rule shows no number. */}
        <section aria-labelledby="coins-earn" className="mt-6">
          <h2 id="coins-earn" className="font-display text-lg font-extrabold">
            {t("agriHome.earn.title")}
          </h2>
          <div className="mt-3 grid gap-2.5 max-md:grid-cols-2 md:grid-cols-4">
            {EARN_CARDS.map((card) => {
              const rule = card.code ? rules[card.code] : undefined;
              return (
                <div
                  key={card.key}
                  className="flex items-center gap-2.5 rounded-card border border-cream-line bg-coins-bg px-4 py-3"
                >
                  <span aria-hidden="true" className="text-xl">
                    {card.icon}
                  </span>
                  <span className="min-w-0 flex-1">
                    <b className="block text-[12px] font-medium text-coins-fg">
                      {t(`agriHome.earn.${card.key}t`)}
                    </b>
                    <small className="text-[10px] text-coins-fg">
                      {t(`agriHome.earn.${card.key}d`)}
                    </small>
                  </span>
                  <span className="font-display text-[15px] font-semibold text-coins-fg">
                    {rule ? `+${rule.amount}` : t("agriHome.soon")}
                  </span>
                </div>
              );
            })}
          </div>
        </section>

        {/* AgriCoins are NOT money. Stated on the surface that shows a
            balance, because that is where someone might assume otherwise. */}
        <p className="mt-5 text-[11px] leading-[1.55] text-muted">
          {t("agriCoins.notMoney")}
        </p>
      </Wrap>
    </main>
  );
}

/** Reason codes the ledger can show. Resolved server-side so the client
 * island never has to know the i18n namespace. */
const REASON_KEYS = [
  "signup_complete",
  "profile_100",
  "daily_visit",
  "daily_visit_streak",
  "referral_referrer",
  "referral_referee",
  "review_approved",
  "business_claim",
  "redeem",
  "manual_adjust",
  "compensation",
  "unknown",
] as const;
