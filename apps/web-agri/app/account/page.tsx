import { Eyebrow } from "@agri/ui";
import type { Metadata } from "next";
import { getTranslations } from "next-intl/server";
import Link from "next/link";

import { auth } from "@/lib/auth";
import { fetchAccountIdentity } from "@/lib/account-identity";
import { fetchOverview } from "@/lib/account-overview";
import {
  deriveChecklist,
  fetchCampaignTotals,
  fetchMyCampaigns,
  fetchOwnedBusinesses,
  isFirstRun,
} from "@/lib/account-roles";

import { alertsCopy } from "./alerts-copy";
import { AlertsPanel } from "./alerts-manager";
import { CropsPanel, EnquiriesPanel, SavedPanel, StatsRow } from "./overview-panels";
import { AdvertiserCard, BusinessCard, FirstRunChecklist, GuestState } from "./role-states";

/**
 * /account — the dashboard overview (AG-U5 P1 shell, P2 contents, P6 states).
 *
 * Four states, all real:
 *  - GUEST      — no identity renders; the page explains what an account is
 *                 for and offers the door. Reached because /account is
 *                 deliberately outside middleware.ts's matcher.
 *  - FIRST RUN  — honest zeros plus four things worth doing, each ticked from
 *                 stored state rather than from having clicked anything.
 *  - FARMER     — the default: stats, enquiries, alerts, crops, saved.
 *  - BUSINESS / ADVERTISER — rolecards ON TOP of the farmer view, not instead
 *                 of it. Both can be true at once, and one person often is.
 *
 * Every number is read, never assumed. Where a read fails its own panel says
 * so and the rest of the page still renders.
 */
export const metadata: Metadata = { title: "Your account", robots: { index: false } };

export const dynamic = "force-dynamic";

export default async function AccountOverviewPage() {
  const user = await auth.getServerUser();
  const token = user ? await auth.getAccessToken().catch(() => null) : null;
  if (!user || !token) return <GuestState />;

  const identity = await fetchAccountIdentity(token);
  // A cookie that survived getServerUser() but cannot read the profile is a
  // stale session. The guest state is the honest thing to show — it offers
  // sign-in, which is the fix.
  if (!identity) return <GuestState />;

  const t = await getTranslations("ui.account");
  const idOrigin = process.env.ID_PUBLIC_ORIGIN ?? "http://localhost:3003";

  const [data, businesses, campaigns] = await Promise.all([
    fetchOverview(token),
    fetchOwnedBusinesses(token),
    fetchMyCampaigns(token),
  ]);
  const stats = await fetchCampaignTotals(
    token,
    campaigns.map((campaign) => campaign.id),
  );

  const checklistInput = {
    pincode: identity.pincode,
    interests: identity.interests,
    alerts: data.counts.alerts,
    threads: data.counts.activeThreads,
    saved: data.counts.saved,
  };
  const firstRun = isFirstRun(checklistInput);
  const place = [identity.district, identity.pincode].filter(Boolean).join(" · ");

  return (
    <main className="pb-4">
      <div className="flex flex-wrap items-start gap-3">
        <div className="min-w-0">
          <Eyebrow>{t("eyebrow")}</Eyebrow>
          <h1 className="mt-1 font-display text-[22px] font-extrabold leading-tight text-ink sm:text-[26px]">
            {identity.name ? t("greeting", { name: identity.name }) : t("greetingNoName")}
          </h1>
          {place ? <p className="mt-1 text-[13px] text-sub">{place}</p> : null}
        </div>
        <span className="flex-1" />
        <Link
          href="/"
          prefetch={false}
          className="tap-target inline-flex items-center rounded-pill border border-cream-line px-3.5 py-2 text-[12.5px] font-semibold text-ink no-underline"
        >
          {t("back")}
        </Link>
      </div>

      {/* Rolecards sit above the stats: if you run a shop, the shop is the
          first thing you came here for. */}
      <BusinessCard businesses={businesses} />
      <AdvertiserCard campaigns={campaigns} stats={stats} />

      <StatsRow data={data} />

      {firstRun ? (
        // The checklist REPLACES the panels while every one of them would be
        // empty. Four empty cards teach nothing; four things to do teach the
        // shape of the place.
        <FirstRunChecklist steps={deriveChecklist(checklistInput)} idOrigin={idOrigin} />
      ) : (
        <div className="mt-4 grid gap-3 lg:grid-cols-2">
          <div className="space-y-3">
            <EnquiriesPanel data={data} />
            <AlertsPanel
              initial={data.alerts}
              copy={alertsCopy(t)}
              title={t("panels.alerts")}
              manageLabel={t("panels.alertsManage")}
            />
          </div>
          <div className="space-y-3">
            <CropsPanel identity={identity} idOrigin={idOrigin} />
            <SavedPanel data={data} />
          </div>
        </div>
      )}
    </main>
  );
}
