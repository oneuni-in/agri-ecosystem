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
  reviews: "⭐",
  listings: "🏪",
  products: "🥛",
  notifications: "🔔",
  analytics: "📈",
  premium: "💎",
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

/** One business's engagement numbers over `days`, owner-scoped (404s for
 * anyone else, same IDOR contract as every vendor read). */
interface Analytics {
  views: number;
  reveals: number;
  leads: number;
  responded: number;
  leadTotal: number;
}

async function businessAnalytics(
  token: string,
  businessId: string,
  days: number,
): Promise<Analytics | null> {
  try {
    const response = await fetch(
      `${API}/directory/businesses/${businessId}/analytics?days=${days}`,
      { headers: { authorization: `Bearer ${token}` }, cache: "no-store" },
    );
    if (!response.ok) return null;
    const body = (await response.json()) as {
      views?: { total?: number };
      reveals?: { total?: number };
      leads?: { total?: number };
      response?: { total?: number; responded?: number };
    };
    return {
      views: body.views?.total ?? 0,
      reveals: body.reveals?.total ?? 0,
      leads: body.leads?.total ?? 0,
      responded: body.response?.responded ?? 0,
      leadTotal: body.response?.total ?? 0,
    };
  } catch {
    return null;
  }
}

/** Sum a window across every owned business, or null if ANY of them failed.
 * A partial sum is a smaller number that looks like a real one — the same
 * rule the lead tiles below already follow. */
function sumAll(rows: (Analytics | null)[]): Analytics | null {
  if (rows.some((row) => row === null)) return null;
  return (rows as Analytics[]).reduce(
    (acc, row) => ({
      views: acc.views + row.views,
      reveals: acc.reveals + row.reveals,
      leads: acc.leads + row.leads,
      responded: acc.responded + row.responded,
      leadTotal: acc.leadTotal + row.leadTotal,
    }),
    { views: 0, reveals: 0, leads: 0, responded: 0, leadTotal: 0 },
  );
}

/** "+18% vs previous 7 days", or null when there is nothing to compare
 * against. NOT a sparkline: the analytics endpoint returns totals and a
 * by-pincode split, never a per-day series, so the reference's little bar
 * charts have no data behind them and are left out rather than drawn from
 * numbers that do not exist. */
function delta(now: number, before: number, label: string): string | null {
  if (before <= 0) return null;
  const pct = Math.round(((now - before) / before) * 100);
  if (pct === 0) return `— ${label}`;
  return `${pct > 0 ? "▲" : "▼"} ${Math.abs(pct)}% ${label}`;
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
  const [[showBilling, showAds], stats, recentRows, priorRows] = await Promise.all([
    Promise.all([billingVisible(), adsVisible()]),
    Promise.all(
      owned.map((business) =>
        token ? inboxStats(token, business.id) : Promise.resolve(null),
      ),
    ),
    // Two windows so "vs previous 7 days" is measured, not asserted: the
    // 14-day total minus the 7-day total IS the week before.
    Promise.all(
      owned.map((business) =>
        token ? businessAnalytics(token, business.id, 7) : Promise.resolve(null),
      ),
    ),
    Promise.all(
      owned.map((business) =>
        token ? businessAnalytics(token, business.id, 14) : Promise.resolve(null),
      ),
    ),
  ]);
  const recent = sumAll(recentRows);
  const fortnight = sumAll(priorRows);
  const prior =
    recent && fortnight
      ? {
          views: fortnight.views - recent.views,
          reveals: fortnight.reveals - recent.reveals,
          leads: fortnight.leads - recent.leads,
        }
      : null;
  const responseRate =
    recent && recent.leadTotal > 0
      ? Math.round((recent.responded / recent.leadTotal) * 100)
      : null;
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

      {/* The A3 reference's engagement row. Real figures from the owner-only
          analytics read, summed across every business this account owns.
          Rendered only when ALL of them reported. */}
      {recent ? (
        <ConsoleStatRow label={t("dashboard.last7")}>
          <ConsoleStatTile
            value={String(recent.views)}
            label={t("dashboard.statViews")}
            hint={delta(recent.views, prior?.views ?? 0, t("dashboard.vsPrev")) ?? t("dashboard.last7")}
          />
          <ConsoleStatTile
            value={String(recent.reveals)}
            label={t("dashboard.statReveals")}
            hint={
              delta(recent.reveals, prior?.reveals ?? 0, t("dashboard.vsPrev")) ??
              t("dashboard.last7")
            }
          />
          <ConsoleStatTile
            value={String(recent.leads)}
            label={t("dashboard.statNewLeads")}
            hint={delta(recent.leads, prior?.leads ?? 0, t("dashboard.vsPrev")) ?? t("dashboard.last7")}
          />
          {responseRate !== null ? (
            <ConsoleStatTile
              value={`${responseRate}%`}
              label={t("dashboard.statResponseRate")}
              hint={t("dashboard.last7")}
            />
          ) : null}
        </ConsoleStatRow>
      ) : null}

      {/* Listing health, from the reference's right rail. Only the checks the
          owner list actually answers — verification. Coverage, products and
          description live on the per-business detail read and would cost one
          request each, so they are not guessed at here. */}
      {owned.some((business) => business.verification_status !== "verified") ? (
        <ConsolePanel title={t("dashboard.completeTitle")} className="mt-4">
          <p className="mb-2 text-[12.5px] text-sub">{t("dashboard.completeSub")}</p>
          <ul className="grid gap-1.5">
            {owned
              .filter((business) => business.verification_status !== "verified")
              .map((business) => (
                <li key={business.id} className="text-[13px] text-ink">
                  <span className="font-semibold">{business.name}</span>{" "}
                  <span className="text-sub">— {t("dashboard.needVerify")}</span>
                </li>
              ))}
          </ul>
        </ConsolePanel>
      ) : null}

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
            <ConsoleModuleCard icon={MODULE_ICONS[entry.id] ?? "🗂️"} title={t(`nav.${entry.id}`)} />
          </Link>
        ))}
      </div>
    </main>
  );
}
