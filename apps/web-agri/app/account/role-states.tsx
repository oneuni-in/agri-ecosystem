import { Card } from "@agri/ui";
import { getTranslations } from "next-intl/server";
import Link from "next/link";

import type { ChecklistStep } from "@/lib/account-roles";
import type { CampaignBrief, CampaignStats, OwnedBusinessBrief } from "@/lib/account-roles";

/**
 * The role states (AG-U5 P6).
 *
 * Modules render by role, and role is read rather than claimed: owning a
 * business makes the business card appear, holding a campaign makes the
 * advertiser card appear. Both can be true at once — the reference is
 * explicit that a farmer who runs a shop and buys ads sees all three, and
 * `describes` being a list on the identity side says the same thing.
 */

/**
 * Guest — no identity renders, at all.
 *
 * /account is deliberately outside `middleware.ts`'s matcher so a signed-out
 * visitor arrives here rather than being bounced to a login form that
 * explains nothing. The page says what the account is FOR, then offers the
 * door. Nothing personal is fetched, because there is no one to fetch for.
 */
export async function GuestState() {
  const t = await getTranslations("ui.account.guest");
  return (
    <main className="pb-8">
      <h1 className="font-display text-[24px] font-extrabold leading-tight text-ink sm:text-[28px]">
        {t("title")}
      </h1>
      <p className="mt-2 max-w-[54ch] text-[14px] leading-relaxed text-sub">{t("sub")}</p>
      <ul className="mt-4 space-y-2">
        {["b1", "b2", "b3"].map((key) => (
          <li key={key} className="flex items-start gap-2.5 text-[13.5px] text-ink">
            <span aria-hidden="true" className="text-brand">
              ·
            </span>
            {t(key)}
          </li>
        ))}
      </ul>
      <div className="mt-5 flex flex-wrap gap-2.5">
        {/* A real navigation, not a <Link>. /api/auth/login is a route
            handler that 302s into the OAuth flow on another origin; a
            client-side transition would try to render it as a page and the
            redirect would never happen. The rule is about <a> to PAGES.
            (app/mandi-alert-card.tsx does the same thing and only escapes
            the rule because its href is a template literal.) */}
        {/* eslint-disable-next-line @next/next/no-html-link-for-pages */}
        <a
          href="/api/auth/login?next=/account"
          className="tap-target inline-flex min-h-[44px] items-center rounded-pill bg-brand px-5 text-[13.5px] font-semibold text-white no-underline"
        >
          {t("login")}
        </a>
        <Link
          href="/"
          prefetch={false}
          className="tap-target inline-flex min-h-[44px] items-center rounded-pill border border-cream-line px-5 text-[13.5px] font-semibold text-ink no-underline"
        >
          {t("browse")}
        </Link>
      </div>
    </main>
  );
}

/**
 * First run — honest zeros and four things worth doing.
 *
 * Every tick comes from stored state (`deriveChecklist`), never from having
 * visited a page: a checklist that remembers clicks lies on a new phone and
 * congratulates people for looking rather than doing.
 */
export async function FirstRunChecklist({
  steps,
  idOrigin,
}: {
  steps: ChecklistStep[];
  idOrigin: string;
}) {
  const t = await getTranslations("ui.account.firstRun");
  return (
    <Card className="mt-4 p-4">
      <h2 className="font-display text-[16px] font-extrabold text-ink">
        <span aria-hidden="true" className="mr-1.5">
          🌱
        </span>
        {t("title")}
      </h2>
      <p className="mb-3 mt-1 text-[12.5px] text-sub">{t("sub")}</p>
      <ol className="space-y-2">
        {steps.map((step) => {
          // Location and crops are edited on AgriID; the other two happen here.
          const href =
            step.id === "location" || step.id === "crops"
              ? `${idOrigin.replace(/\/+$/, "")}/account`
              : step.href;
          const isExternal = step.id === "location" || step.id === "crops";
          return (
            <li
              key={step.id}
              className="flex flex-wrap items-center gap-2 rounded-card border border-cream-line bg-cream px-3 py-2.5"
            >
              <span
                aria-hidden="true"
                className={`flex h-6 w-6 flex-none items-center justify-center rounded-pill text-[12px] font-extrabold ${
                  step.done ? "bg-verified-bg text-verified-fg" : "bg-line text-sub"
                }`}
              >
                {step.done ? "✓" : "·"}
              </span>
              <span className="flex-1 text-[13px] font-semibold text-ink">{t(step.id)}</span>
              {step.done ? (
                <span className="text-[11.5px] font-semibold text-verified-fg">{t("done")}</span>
              ) : isExternal ? (
                <a
                  href={href}
                  className="tap-target inline-flex min-h-[36px] items-center rounded-pill border border-cream-line bg-card px-3 text-[12px] font-semibold text-ink no-underline"
                >
                  {t("todo")}
                </a>
              ) : (
                <Link
                  href={href}
                  prefetch={false}
                  className="tap-target inline-flex min-h-[36px] items-center rounded-pill border border-cream-line bg-card px-3 text-[12px] font-semibold text-ink no-underline"
                >
                  {t("todo")}
                </Link>
              )}
            </li>
          );
        })}
      </ol>
    </Card>
  );
}

/** The business rolecard — present only when this person owns one. */
export async function BusinessCard({ businesses }: { businesses: OwnedBusinessBrief[] }) {
  const t = await getTranslations("ui.account.roles");
  if (businesses.length === 0) return null;
  const first = businesses[0];
  if (!first) return null;
  const verified = first.verification_status === "verified";
  return (
    <Card className="mt-3 flex flex-wrap items-center gap-3 border-brand-soft-2 p-3.5">
      <span aria-hidden="true" className="text-[22px] leading-none">
        🏪
      </span>
      <div className="min-w-0 flex-1">
        <p className="truncate font-display text-[14.5px] font-extrabold text-ink">
          {businesses.length === 1 ? t("business", { name: first.name }) : t("businessOne")}
        </p>
        <p className="mt-0.5 text-[12px] text-sub">
          {verified ? t("verified") : t("unverified")}
        </p>
      </div>
      <Link
        href="/business"
        prefetch={false}
        className="tap-target inline-flex min-h-[40px] items-center rounded-pill bg-accent px-4 text-[12.5px] font-bold text-accent-ink no-underline"
      >
        {t("openConsole")}
      </Link>
    </Card>
  );
}

/**
 * The advertiser rolecard and its analytics strip.
 *
 * The numbers are the SAME counters the admin console reads — `ads.impressions`
 * and `ads.clicks` keyed by placement — which makes reconciliation an
 * assertion rather than a hope. `null` totals print the "unavailable" line
 * instead of zeroes: "0 impressions" and "we could not read your impressions"
 * are very different things to tell someone who paid.
 */
export async function AdvertiserCard({
  campaigns,
  stats,
}: {
  campaigns: CampaignBrief[];
  stats: CampaignStats | null;
}) {
  const t = await getTranslations("ui.account.roles");
  if (campaigns.length === 0) return null;
  const rupees = (paise: number) => `₹${Math.round(paise / 100).toLocaleString("en-IN")}`;
  return (
    <Card className="mt-3 p-3.5">
      <div className="flex flex-wrap items-center gap-3">
        <span aria-hidden="true" className="text-[22px] leading-none">
          📣
        </span>
        <div className="min-w-0 flex-1">
          <p className="font-display text-[14.5px] font-extrabold text-ink">{t("advertiser")}</p>
          <p className="mt-0.5 text-[12px] text-sub">
            {t("campaigns", { count: campaigns.length })} · {t("window")}
          </p>
        </div>
        <Link
          href="/business/ads"
          prefetch={false}
          className="tap-target inline-flex min-h-[40px] items-center rounded-pill border border-cream-line px-4 text-[12.5px] font-semibold text-ink no-underline"
        >
          {t("openAds")}
        </Link>
      </div>
      {stats === null ? (
        <p className="mt-3 text-[12.5px] text-muted">{t("statsUnavailable")}</p>
      ) : (
        <>
          <dl className="mt-3 grid grid-cols-2 gap-2 lg:grid-cols-4">
            {[
              { label: t("impressions"), value: stats.impressions.toLocaleString("en-IN") },
              { label: t("clicks"), value: stats.clicks.toLocaleString("en-IN") },
              { label: t("ctr"), value: `${(stats.ctr_bp / 100).toFixed(2)}%` },
              { label: t("spend"), value: rupees(stats.spend_paise) },
            ].map((tile) => (
              <div
                key={tile.label}
                className="rounded-card border border-cream-line bg-cream px-3 py-2"
              >
                <dt className="text-[10.5px] font-extrabold uppercase tracking-wide text-muted">
                  {tile.label}
                </dt>
                <dd className="mt-0.5 font-display text-[18px] font-extrabold text-ink">
                  {tile.value}
                </dd>
              </div>
            ))}
          </dl>
          <p className="mt-2 text-[11px] text-muted">{t("sameCounters")}</p>
        </>
      )}
    </Card>
  );
}
