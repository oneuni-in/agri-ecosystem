import {
  ConsoleCell,
  ConsoleCheckRow,
  ConsoleGrid2,
  ConsoleHeadCell,
  ConsoleKpi,
  ConsoleKpiRow,
  ConsoleMiniNote,
  ConsoleModuleCard,
  ConsoleNotice,
  ConsolePageHeader,
  ConsolePanel,
  ConsoleRow,
  ConsoleTable,
  ConsoleTopbar,
  EmptyState,
  StateChip,
  buttonVariants,
  cn,
  consoleGhostButtonClass,
  consoleMoneyButtonClass,
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
function delta(
  now: number,
  before: number,
  label: string,
): { text: string; tone: "up" | "down" | "flat" } | null {
  if (before <= 0) return null;
  const pct = Math.round(((now - before) / before) * 100);
  if (pct === 0) return { text: `— ${label}`, tone: "flat" };
  return {
    text: `${pct > 0 ? "▲" : "▼"} ${Math.abs(pct)}% ${label}`,
    tone: pct > 0 ? "up" : "down",
  };
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

  const adsHref = modules.find((entry) => entry.id === "ads")?.href ?? null;
  const publicSlug = owned.length === 1 ? owned[0]?.slug : undefined;
  const incomplete = owned.filter((business) => business.verification_status !== "verified");

  return (
    <main>
      {/* A3 reference `.topbar`: eyebrow, greeting, one line of context, and
          the two actions the owner reaches for most. The reference greets by
          time of day; a server render has no timezone to be right about, so
          the greeting is stable rather than guessed. */}
      <ConsoleTopbar
        eyebrow={t("dashboard.eyebrow")}
        title={
          <>
            {t("dashboard.greeting")}
            {owned.length === 1 && owned[0] ? `, ${owned[0].name}` : ""}
          </>
        }
        sub={t("dashboard.ownedCount", {
          count: owned.length,
          verified: owned.length - incomplete.length,
        })}
        actions={
          <>
            {publicSlug ? (
              <Link
                href={`/directory/businesses/${publicSlug}`}
                prefetch={false}
                className={consoleGhostButtonClass}
              >
                {t("dashboard.viewPublic")}
              </Link>
            ) : null}
            {adsHref ? (
              <Link href={adsHref} prefetch={false} className={consoleMoneyButtonClass}>
                {t("dashboard.promote")}
              </Link>
            ) : null}
          </>
        }
      />

      {enforced.length > 0 ? (
        <div className="mb-3 flex flex-col gap-2">
          {enforced.map((business) => (
            <ConsoleNotice key={business.id} tone="alert">
              {business.name}: {business.enforcement_reason}
            </ConsoleNotice>
          ))}
        </div>
      ) : null}

      {/* The reference's KPI row. Real figures from the owner-only analytics
          read, summed across every owned business and rendered only when ALL
          of them reported — a partial sum is a smaller number that looks
          like a real one. No sparkline bars: that read returns totals and a
          by-pincode split, never a per-day series. */}
      {recent ? (
        <ConsoleKpiRow label={t("dashboard.last7")}>
          <ConsoleKpi
            label={t("dashboard.statViews")}
            value={recent.views.toLocaleString("en-IN")}
            {...kpiDelta(
              recent.views,
              prior?.views ?? 0,
              t("dashboard.vsPrev"),
              t("dashboard.last7"),
            )}
          />
          <ConsoleKpi
            label={t("dashboard.statReveals")}
            value={recent.reveals.toLocaleString("en-IN")}
            {...kpiDelta(
              recent.reveals,
              prior?.reveals ?? 0,
              t("dashboard.vsPrev"),
              t("dashboard.last7"),
            )}
          />
          <ConsoleKpi
            label={t("dashboard.statNewLeads")}
            value={recent.leads.toLocaleString("en-IN")}
            {...kpiDelta(
              recent.leads,
              prior?.leads ?? 0,
              t("dashboard.vsPrev"),
              t("dashboard.last7"),
            )}
          />
          <ConsoleKpi
            label={
              responseRate !== null
                ? t("dashboard.statResponseRate")
                : t("dashboard.statBusinesses")
            }
            value={responseRate !== null ? `${responseRate}%` : String(owned.length)}
            {...(responseRate !== null ? { delta: t("dashboard.last7") } : {})}
          />
        </ConsoleKpiRow>
      ) : (
        <ConsoleKpiRow label={t("dashboard.title")}>
          <ConsoleKpi label={t("dashboard.statBusinesses")} value={String(owned.length)} />
          {leadsKnown ? (
            <ConsoleKpi
              label={t("dashboard.statLeads")}
              value={leadsTotal.toLocaleString("en-IN")}
              delta={t("dashboard.allTime")}
            />
          ) : null}
          {leadsKnown ? (
            <ConsoleKpi
              label={t("dashboard.statResponded")}
              value={leadsResponded.toLocaleString("en-IN")}
              delta={t("dashboard.allTime")}
            />
          ) : null}
        </ConsoleKpiRow>
      )}

      {/* A3 `.grid2`: the work on the left, the reference rail on the right. */}
      <ConsoleGrid2>
        <div className="min-w-0 space-y-3">
          <ConsolePanel title={t("dashboard.yourBusinesses")}>
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

          <ConsolePanel title={t("dashboard.manage")}>
            <div className="grid gap-2.5 sm:grid-cols-2">
              {modules.map((entry) => (
                <Link key={entry.id} href={entry.href} className="no-underline">
                  <ConsoleModuleCard icon={entry.icon} title={t(`nav.${entry.id}`)} />
                </Link>
              ))}
            </div>
          </ConsolePanel>
        </div>

        <div className="min-w-0 space-y-3">
          {/* Listing health, from the reference's right rail. Only the check
              the owner list actually answers — verification. Coverage,
              products and description live on the per-business detail read
              and would cost one request each, so they are not guessed at. */}
          <ConsolePanel title={t("dashboard.completeTitle")}>
            {incomplete.length === 0 ? (
              <p className="text-xs text-sub">{t("dashboard.allComplete")}</p>
            ) : (
              <>
                <p className="mb-1 text-[12.5px] text-sub">{t("dashboard.completeSub")}</p>
                {incomplete.map((business) => (
                  <ConsoleCheckRow
                    key={business.id}
                    done={false}
                    right={
                      <Link
                        href="/business/listings"
                        prefetch={false}
                        className="tap-target inline-flex items-center font-medium text-brand no-underline"
                      >
                        {t("dashboard.needVerify")}
                      </Link>
                    }
                  >
                    {business.name}
                  </ConsoleCheckRow>
                ))}
              </>
            )}
          </ConsolePanel>

          {adsHref ? (
            <ConsolePanel title={t("nav.ads")}>
              <p className="text-xs leading-relaxed text-sub">{t("dashboard.promoteBody")}</p>
              <Link
                href={adsHref}
                prefetch={false}
                className={cn(consoleMoneyButtonClass, "mt-2.5 w-full")}
              >
                {t("dashboard.promoteCta")}
              </Link>
              <ConsoleMiniNote>{t("dashboard.promoteNote")}</ConsoleMiniNote>
            </ConsolePanel>
          ) : null}
        </div>
      </ConsoleGrid2>
    </main>
  );
}

/** Spreads onto `ConsoleKpi` as `delta` + `deltaTone`, falling back to the
 * window label when there is no prior period to compare against. */
function kpiDelta(
  now: number,
  before: number,
  vsLabel: string,
  fallback: string,
): { delta: string; deltaTone: "up" | "down" | "flat" } {
  const measured = delta(now, before, vsLabel);
  return measured
    ? { delta: measured.text, deltaTone: measured.tone }
    : { delta: fallback, deltaTone: "flat" };
}
