import { Eyebrow } from "@agri/ui";
import type { Metadata } from "next";
import { getTranslations } from "next-intl/server";
import Link from "next/link";
import { redirect } from "next/navigation";

import { auth } from "@/lib/auth";
import { fetchAccountIdentity } from "@/lib/account-identity";
import { fetchOverview } from "@/lib/account-overview";

import { alertsCopy } from "./alerts-copy";
import { AlertsPanel } from "./alerts-manager";
import { CropsPanel, EnquiriesPanel, SavedPanel, StatsRow } from "./overview-panels";

/**
 * /account — the dashboard overview (AG-U5 P1 shell, P2 contents).
 *
 * Two columns from `lg:` and one below it, mirroring A5: the things you are
 * waiting on (enquiries, alerts) lead, and the things you keep (saved, crops)
 * follow.
 *
 * Every number on this page is read, never assumed. Where a read fails its
 * own panel says so and the rest of the page still renders — one dead
 * endpoint must not cost a farmer their coin balance.
 *
 * `noindex`: one person's dashboard has nothing to offer a crawler.
 */
export const metadata: Metadata = { title: "Your account", robots: { index: false } };

export const dynamic = "force-dynamic";

export default async function AccountOverviewPage() {
  const user = await auth.getServerUser();
  // P6 replaces this with the guest state the reference draws (no identity
  // renders, Login in the header). Until then a signed-out visitor goes where
  // every other account surface sends them, carrying /account as `next`.
  if (!user) redirect("/api/auth/login?next=/account");

  const [t, token] = await Promise.all([getTranslations("ui.account"), auth.getAccessToken()]);
  if (!token) redirect("/api/auth/login?next=/account");

  const [identity, data] = await Promise.all([
    fetchAccountIdentity(token),
    fetchOverview(token),
  ]);
  // The layout already degraded to a bare shell if this read failed; a stale
  // cookie that survived getServerUser() lands here, and login is the fix.
  if (!identity) redirect("/api/auth/login?next=/account");

  const idOrigin = process.env.ID_PUBLIC_ORIGIN ?? "http://localhost:3003";
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

      <StatsRow data={data} />

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
    </main>
  );
}
