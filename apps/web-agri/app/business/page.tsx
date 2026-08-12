import {
  ConsoleCell,
  ConsoleHeadCell,
  ConsoleModuleCard,
  ConsoleNotice,
  ConsolePageHeader,
  ConsolePanel,
  ConsoleRow,
  ConsoleStatRow,
  ConsoleStatTile,
  ConsoleTable,
  EmptyState,
  StateChip,
  buttonVariants,
  cn,
} from "@agri/ui";
import Link from "next/link";
import { redirect } from "next/navigation";
import { getTranslations } from "next-intl/server";

import { auth } from "@/lib/auth";
import {
  adsVisible,
  billingVisible,
  fetchOwnedBusinesses,
  type OwnedBusiness,
} from "@/lib/console-gates";
import { CONSOLE_MODULES } from "@/lib/console-modules";

/**
 * The console dashboard (U2 Group A) — the page /business never had. D26's
 * per-page login gates carried `next=/business/<page>` while /business
 * itself 404'd; this page closes that hole (the middleware and the gate
 * below both name a real destination now).
 *
 * Everything rendered is real data or absent: owned businesses from the D15
 * owner list, lead counts from the D18 inbox stats, module entries from the
 * D20 registry behind their billing/ads dark-launch probes. A stat with no
 * honest source is not rendered (U1 §16 rule).
 */
export const metadata = { title: "Business console", robots: { index: false } };

const API = process.env.API_BASE_URL ?? "http://127.0.0.1:8000";

const MODULE_ICONS: Record<string, string> = {
  inbox: "📥",
  listings: "🏪",
  products: "🥛",
  analytics: "📈",
  premium: "⭐",
  billing: "🧾",
  ads: "📣",
};

async function inboxStats(
  token: string,
  businessId: string,
): Promise<{ total: number; responded: number } | null> {
  try {
    const response = await fetch(`${API}/leads/inbox/stats?business_id=${businessId}`, {
      headers: { authorization: `Bearer ${token}` },
      cache: "no-store",
    });
    if (!response.ok) return null;
    const body = (await response.json()) as { total?: number; responded?: number };
    if (typeof body.total !== "number" || typeof body.responded !== "number") return null;
    return { total: body.total, responded: body.responded };
  } catch {
    return null;
  }
}

function statusChip(business: OwnedBusiness, t: (key: string) => string) {
  if (business.status === "active")
    return <StateChip tone="ok">{t("dashboard.statusActive")}</StateChip>;
  if (business.status === "suspended")
    return <StateChip tone="alert">{t("dashboard.statusSuspended")}</StateChip>;
  return <StateChip tone="alert">{t("dashboard.statusDisabled")}</StateChip>;
}

export default async function BusinessDashboardPage() {
  const user = await auth.getServerUser();
  if (!user) redirect("/api/auth/login?next=/business");
  const t = await getTranslations("ui.console");
  const owned = await fetchOwnedBusinesses();

  // Consumer session: no vendor nav (the layout already rendered none) and
  // no dashboard — the create/claim onboarding is the whole page.
  if (owned.length === 0) {
    return (
      <main>
        <ConsolePageHeader title={t("dashboard.onboardTitle")} />
        <ConsolePanel className="max-w-[560px]">
          <EmptyState
            icon="🏪"
            title={t("dashboard.onboardTitle")}
            description={t("dashboard.onboardBody")}
            action={
              <Link
                href="/business/listings"
                className={cn(buttonVariants({ variant: "brand" }), "flex-none px-4 no-underline")}
              >
                {t("dashboard.onboardCta")}
              </Link>
            }
          />
          <p className="mt-3 text-[12px] text-muted">{t("dashboard.onboardClaimHint")}</p>
        </ConsolePanel>
      </main>
    );
  }

  const token = await auth.getAccessToken();
  const [[showBilling, showAds], stats] = await Promise.all([
    Promise.all([billingVisible(), adsVisible()]),
    Promise.all(
      owned.map((business) =>
        token ? inboxStats(token, business.id) : Promise.resolve(null),
      ),
    ),
  ]);
  const statValues = stats.filter(
    (entry): entry is { total: number; responded: number } => entry !== null,
  );
  // Honest numbers: render lead tiles only when every owned business
  // reported — a partial sum reads as a smaller truth, not a failure.
  const leadsKnown = statValues.length === owned.length;
  const leadsTotal = statValues.reduce((sum, entry) => sum + entry.total, 0);
  const leadsResponded = statValues.reduce((sum, entry) => sum + entry.responded, 0);

  const modules = CONSOLE_MODULES.filter((entry) => {
    if (entry.id === "dashboard") return false;
    if (entry.gate === "billing") return showBilling;
    if (entry.gate === "ads") return showAds;
    return true;
  });

  const enforced = owned.filter((business) => business.enforcement_reason);

  return (
    <main>
      <ConsolePageHeader
        title={t("dashboard.title")}
        sub={owned.length === 1 ? owned[0]?.name : undefined}
      />

      {enforced.length > 0 ? (
        <div className="mb-4 flex flex-col gap-2">
          {enforced.map((business) => (
            <ConsoleNotice key={business.id} tone="alert">
              {business.name}: {business.enforcement_reason}
            </ConsoleNotice>
          ))}
        </div>
      ) : null}

      <ConsoleStatRow label={t("dashboard.title")}>
        <ConsoleStatTile
          value={String(owned.length)}
          label={t("dashboard.statBusinesses")}
        />
        {leadsKnown ? (
          <ConsoleStatTile
            value={String(leadsTotal)}
            label={t("dashboard.statLeads")}
            hint={t("dashboard.allTime")}
          />
        ) : null}
        {leadsKnown ? (
          <ConsoleStatTile
            value={String(leadsResponded)}
            label={t("dashboard.statResponded")}
            hint={t("dashboard.allTime")}
          />
        ) : null}
      </ConsoleStatRow>

      <ConsolePanel title={t("dashboard.yourBusinesses")} className="mt-4">
        <ConsoleTable
          caption={t("dashboard.yourBusinesses")}
          head={
            <>
              <ConsoleHeadCell>{t("dashboard.colBusiness")}</ConsoleHeadCell>
              <ConsoleHeadCell>{t("dashboard.colPincode")}</ConsoleHeadCell>
              <ConsoleHeadCell>{t("dashboard.colStatus")}</ConsoleHeadCell>
              <ConsoleHeadCell>{t("dashboard.colPlan")}</ConsoleHeadCell>
            </>
          }
        >
          {owned.map((business) => (
            <ConsoleRow key={business.id}>
              <ConsoleCell label={t("dashboard.colBusiness")}>
                <span className="font-semibold">{business.name}</span>
                {business.verification_status === "verified" ? (
                  <>
                    {" "}
                    <StateChip tone="ok">{t("dashboard.verified")}</StateChip>
                  </>
                ) : null}
              </ConsoleCell>
              <ConsoleCell label={t("dashboard.colPincode")}>
                {business.primary_pincode}
              </ConsoleCell>
              <ConsoleCell label={t("dashboard.colStatus")}>
                {statusChip(business, t)}
              </ConsoleCell>
              <ConsoleCell label={t("dashboard.colPlan")}>
                {business.subscription_tier === "free" ? (
                  <StateChip tone="neutral">{t("dashboard.planFree")}</StateChip>
                ) : (
                  <StateChip tone="info">{business.subscription_tier}</StateChip>
                )}
              </ConsoleCell>
            </ConsoleRow>
          ))}
        </ConsoleTable>
      </ConsolePanel>

      <h2 className="mb-2.5 mt-5 font-display text-[15px] font-extrabold text-ink">
        {t("dashboard.manage")}
      </h2>
      <div className="grid gap-2.5 md:grid-cols-2 lg:grid-cols-3">
        {modules.map((entry) => (
          <Link key={entry.id} href={entry.href} className="no-underline">
            <ConsoleModuleCard icon={MODULE_ICONS[entry.id] ?? "🗂️"} title={entry.title} />
          </Link>
        ))}
      </div>
    </main>
  );
}
