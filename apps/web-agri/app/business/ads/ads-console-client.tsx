"use client";

/**
 * M5 Task 15/16: advertiser self-serve console shell — business selector +
 * campaign list (via the /api/ads/my/* proxy, Task 14) + the "New campaign"
 * wizard toggle + (Task 16) a post-checkout status banner and a per-campaign
 * detail/analytics panel (pause/resume, budget, stats, invoice).
 */

import {
  Button,
  Card,
  ConsoleMiniNote,
  ConsolePanel,
  ConsoleTopbar,
  EmptyState,
  Skeleton,
  cn,
  consoleMoneyButtonClass,
} from "@agri/ui";
import { useSearchParams } from "next/navigation";
import {
  Fragment,
  Suspense,
  useEffect,
  useRef,
  useState,
  type ReactNode,
} from "react";

import { ApiError, getJson, postJson } from "@/lib/api";

import { CampaignWizard } from "./campaign-wizard";
import { TIER_LABELS, type CreativeOut } from "./wizard-steps";

interface BusinessRef {
  id: string;
  name: string;
}

interface PlacementSnapshot {
  id: string;
  slot_key: string;
  status: string;
}

interface MyCampaign {
  id: string;
  name: string;
  status: string;
  display_status: string;
  price_paise: number | null;
  /** Serve credits: how many of the purchased serves are already used.
   * Both are on the list payload, so the table's Serves column costs
   * nothing extra. */
  budget_serves_total: number | null;
  budget_serves_used: number;
  flight_start: string;
  flight_end: string;
  placements: PlacementSnapshot[];
}

/** The four numbers the campaigns table shows per row. `null` means that
 * row's stats read failed — the row shows dashes, the table survives. */
type RowStats = {
  impressions: number;
  clicks: number;
  ctr_bp: number;
  spend_paise: number | null;
} | null;

const FIELD =
  "mt-1 block min-h-[44px] w-full rounded-btn border border-line bg-card px-3 py-2 text-[13px] text-ink";
const LABEL = "block text-[13px] font-semibold text-ink";

function AlertNotice({ children }: { children: ReactNode }) {
  return (
    <div className="rounded-card border border-alert-line bg-alert-bg p-3 text-[13px] font-semibold text-ink">
      {children}
    </div>
  );
}

function OkNotice({ children }: { children: ReactNode }) {
  return (
    <div className="rounded-card bg-verified-bg p-3 text-[13px] font-semibold text-verified-fg">
      {children}
    </div>
  );
}

function rupees(paise: number): string {
  return `₹${(paise / 100).toLocaleString("en-IN")}`;
}

// display_status (backend/core/modules/ads/lifecycle.py) -> friendly chip.
const DISPLAY_STATUS: Record<string, { label: string; className: string }> = {
  draft: { label: "Draft", className: "bg-line text-ink" },
  pending_payment: { label: "Pending payment", className: "bg-sponsored-bg text-sponsored-fg" },
  pending_moderation: { label: "In review", className: "bg-sponsored-bg text-sponsored-fg" },
  active: { label: "Live", className: "bg-verified-bg text-verified-fg" },
  paused: { label: "Paused", className: "bg-line text-ink" },
  archived: { label: "Finished", className: "bg-alert-bg text-ink" },
  exhausted: { label: "Finished", className: "bg-alert-bg text-ink" },
  expired: { label: "Expired", className: "bg-alert-bg text-ink" },
};

function StatusChip({ status }: { status: string }) {
  const meta = DISPLAY_STATUS[status] ?? { label: status, className: "bg-line text-ink" };
  return (
    <span
      className={cn(
        "inline-flex flex-none items-center self-start rounded-pill px-[9px] py-[3px] text-[11px] font-extrabold",
        meta.className,
      )}
    >
      {meta.label}
    </span>
  );
}

// ---------------------------------------------------------------------------
// M5 Task 16: post-checkout status banner. The Razorpay callback_url
// (modules/billing/ad_orders.py's create_ad_order) is always
// `{console_base_url}/business/ads?paid={campaign_id}` - `paid` carries the
// campaign id, never a boolean. useSearchParams needs a <Suspense> boundary
// (next/navigation precedent: apps/web-milk's view-beacon.tsx), supplied by
// AdsConsoleClient around this component rather than forcing the whole page
// dynamic.

const POLL_INTERVAL_MS = 3000;
const POLL_MAX_TRIES = 20;

function PaidReturnBanner({ onSettled }: { onSettled: () => void }) {
  const searchParams = useSearchParams();
  const campaignId = searchParams.get("paid");
  const [phase, setPhase] = useState<"polling" | "success" | "timeout" | null>(null);

  // `onSettled` (refreshCampaigns) is a fresh closure on every AdsConsoleClient
  // render - including the render calling it causes. Depending on it
  // directly in the poll effect below would re-run that effect (tearing
  // down the in-flight setTimeout chain and restarting from tries=0) every
  // single time the campaign left pending_payment, forever: a tight
  // fetch-then-rerender loop that floods GET .../campaigns/{id} and trips
  // the endpoint's rate limit (caught live during Task 16 manual QA). A ref
  // holds the latest callback without making it a dependency.
  const onSettledRef = useRef(onSettled);
  useEffect(() => {
    onSettledRef.current = onSettled;
  }, [onSettled]);

  useEffect(() => {
    if (!campaignId) {
      setPhase(null);
      return;
    }
    let cancelled = false;
    let tries = 0;
    let timer: ReturnType<typeof setTimeout> | undefined;
    setPhase("polling");

    const poll = async () => {
      tries += 1;
      try {
        const body = await getJson(`/api/ads/my/campaigns/${campaignId}`);
        if (cancelled) return;
        if (body.status !== "pending_payment") {
          setPhase("success");
          onSettledRef.current();
          return;
        }
      } catch {
        // transient failure - keep polling until the try budget runs out
      }
      if (cancelled) return;
      if (tries >= POLL_MAX_TRIES) {
        setPhase("timeout");
        return;
      }
      timer = setTimeout(() => void poll(), POLL_INTERVAL_MS);
    };
    void poll();

    return () => {
      cancelled = true;
      if (timer) clearTimeout(timer);
    };
  }, [campaignId]);

  if (!campaignId || phase === null) return null;
  if (phase === "polling") {
    return <AlertNotice>Checking your payment — this can take a few seconds…</AlertNotice>;
  }
  if (phase === "success") {
    return <OkNotice>Payment received — your ads are in review.</OkNotice>;
  }
  return (
    <AlertNotice>
      Still waiting on payment confirmation. Check the campaign in the list below in a few minutes,
      or refresh this page.
    </AlertNotice>
  );
}

// ---------------------------------------------------------------------------
// M5 Task 16: per-campaign detail/analytics panel — pause/resume, budget,
// GET .../stats, and the GST invoice download link. Opened from the
// campaign list's "Manage" button; fetches its own data independently of
// the list (server truth, same rule as ReviewPayStep in wizard-steps.tsx).

interface CampaignDetail {
  id: string;
  name: string;
  status: string;
  display_status: string;
  budget_serves_total: number | null;
  budget_serves_used: number;
  creatives: CreativeOut[];
}

interface StatsKeyCount {
  key: string;
  serves: number;
}

interface StatsDayRow {
  day: string;
  impressions: number;
  clicks: number;
}

interface CampaignStats {
  spend_paise: number;
  impressions: number;
  clicks: number;
  ctr_bp: number;
  by_day: StatsDayRow[];
  by_pincode: StatsKeyCount[];
  by_category: StatsKeyCount[];
  by_tier: StatsKeyCount[];
  sampled: boolean;
}

interface AdOrderSummary {
  status: string;
  checkout_url: string | null;
  invoice_id: string | null;
  has_pdf: boolean;
}

const DAYS_OPTIONS = [7, 30, 90] as const;

// Pause/resume 409 codes (modules/ads/selfserve_router.py pause_campaign /
// resume_campaign).
const PAUSE_ERROR_COPY: Record<string, string> = {
  not_active: "This campaign isn't currently active.",
};
const RESUME_ERROR_COPY: Record<string, string> = {
  not_paused: "This campaign isn't paused.",
  flight_over: "This campaign's flight has already ended.",
  business_not_servable: "Your business account isn't eligible to advertise right now.",
};

function friendlyLifecycleError(err: unknown, table: Record<string, string>): string {
  if (err instanceof ApiError) return table[err.detail] ?? "Something went wrong — please try again.";
  return "Something went wrong — please try again.";
}

function BudgetBar({ used, total }: { used: number; total: number | null }) {
  if (total === null || total <= 0) {
    return <p className="text-[12px] text-sub">{used.toLocaleString("en-IN")} views served</p>;
  }
  const pct = Math.min(100, Math.round((used / total) * 100));
  return (
    <div className="space-y-1">
      <div className="h-2 w-full overflow-hidden rounded-pill bg-line">
        <div className="h-full rounded-pill bg-brand" style={{ width: `${pct}%` }} />
      </div>
      <p className="text-[12px] text-sub">
        {used.toLocaleString("en-IN")} / {total.toLocaleString("en-IN")} views ({pct}%)
      </p>
    </div>
  );
}

function StatTile({ label, value }: { label: string; value: string }) {
  return (
    <Card className="p-4">
      <p className="text-[12px] font-semibold uppercase tracking-wide text-sub">{label}</p>
      <p className="font-display text-[24px] font-extrabold text-ink">{value}</p>
    </Card>
  );
}

function KeyCountRows({
  title,
  rows,
  labelFor,
}: {
  title: string;
  rows: StatsKeyCount[];
  labelFor?: (key: string) => string;
}) {
  if (rows.length === 0) return null;
  return (
    <Card className="space-y-2 p-4">
      <p className="text-[13px] font-extrabold text-ink">{title}</p>
      <ul className="space-y-1">
        {rows.map((row) => (
          <li key={row.key} className="flex justify-between gap-2 text-[13px] text-ink">
            <span className="min-w-0 break-words">
              {row.key === "unknown" ? "Unknown" : (labelFor?.(row.key) ?? row.key)}
            </span>
            <span className="flex-none font-semibold">{row.serves}</span>
          </li>
        ))}
      </ul>
    </Card>
  );
}

function CampaignDetailPanel({
  campaignId,
  onChanged,
}: {
  campaignId: string;
  onChanged: () => void;
}) {
  const [campaign, setCampaign] = useState<CampaignDetail | null>(null);
  const [loadError, setLoadError] = useState(false);
  const [resumeUrl, setResumeUrl] = useState<string | null>(null);
  const [invoiceId, setInvoiceId] = useState<string | null>(null);
  const [lifecycleBusy, setLifecycleBusy] = useState(false);
  const [lifecycleError, setLifecycleError] = useState<string | null>(null);

  const [days, setDays] = useState<(typeof DAYS_OPTIONS)[number]>(30);
  const [stats, setStats] = useState<CampaignStats | null>(null);
  const [statsError, setStatsError] = useState(false);

  useEffect(() => {
    let cancelled = false;
    void (async () => {
      try {
        const body = await getJson(`/api/ads/my/campaigns/${campaignId}`);
        if (cancelled) return;
        setCampaign(body as unknown as CampaignDetail);
        setLoadError(false);
      } catch {
        if (!cancelled) setLoadError(true);
        return;
      }
      try {
        const orders = await getJson(`/api/billing/ad-orders?campaign_id=${campaignId}&limit=5`);
        if (cancelled) return;
        const items = (orders.items as AdOrderSummary[] | undefined) ?? [];
        setResumeUrl(items.find((o) => o.status === "created" && o.checkout_url)?.checkout_url ?? null);
        setInvoiceId(items.find((o) => o.invoice_id)?.invoice_id ?? null);
      } catch {
        // orders are supplementary (resume link / invoice) - a failure here
        // must not block the rest of the panel from rendering.
      }
    })();
    return () => {
      cancelled = true;
    };
  }, [campaignId]);

  useEffect(() => {
    let cancelled = false;
    setStats(null);
    setStatsError(false);
    void (async () => {
      try {
        const body = await getJson(`/api/ads/my/campaigns/${campaignId}/stats?days=${days}`);
        if (cancelled) return;
        setStats(body as unknown as CampaignStats);
      } catch {
        if (!cancelled) setStatsError(true);
      }
    })();
    return () => {
      cancelled = true;
    };
  }, [campaignId, days]);

  const runLifecycleAction = async (action: "pause" | "resume") => {
    setLifecycleBusy(true);
    setLifecycleError(null);
    try {
      const body = await postJson(`/api/ads/my/campaigns/${campaignId}/${action}`);
      setCampaign(body as unknown as CampaignDetail);
      onChanged();
    } catch (err) {
      setLifecycleError(
        friendlyLifecycleError(err, action === "pause" ? PAUSE_ERROR_COPY : RESUME_ERROR_COPY),
      );
    } finally {
      setLifecycleBusy(false);
    }
  };

  if (loadError) return <AlertNotice>Could not load this campaign — please try again.</AlertNotice>;
  if (campaign === null) return <Skeleton width="100%" height="200px" />;

  const approvedCount = campaign.creatives.filter((c) => c.moderation_status === "approved").length;

  return (
    <Card className="space-y-4 break-words p-4">
      <div className="flex flex-wrap items-center justify-between gap-2">
        <div className="min-w-0 space-y-1">
          <p className="break-words text-[14px] font-extrabold text-ink">{campaign.name}</p>
          <StatusChip status={campaign.display_status} />
        </div>
        <div className="flex gap-2">
          {campaign.status === "active" ? (
            <Button
              type="button"
              variant="ghost"
              disabled={lifecycleBusy}
              className="min-h-[44px]"
              onClick={() => void runLifecycleAction("pause")}
            >
              Pause
            </Button>
          ) : null}
          {campaign.status === "paused" ? (
            <Button
              type="button"
              variant="brand"
              disabled={lifecycleBusy}
              className="min-h-[44px]"
              onClick={() => void runLifecycleAction("resume")}
            >
              Resume
            </Button>
          ) : null}
        </div>
      </div>
      {lifecycleError ? <AlertNotice>{lifecycleError}</AlertNotice> : null}

      {resumeUrl ? (
        <div className="space-y-2">
          <AlertNotice>Payment wasn&apos;t completed for this campaign.</AlertNotice>
          <a
            href={resumeUrl}
            className="inline-flex min-h-[44px] items-center rounded-btn bg-ink px-4 text-[13px] font-semibold text-card"
          >
            Resume payment
          </a>
        </div>
      ) : null}

      <div className="space-y-1">
        <p className="text-[13px] font-extrabold text-ink">Budget</p>
        <BudgetBar used={campaign.budget_serves_used} total={campaign.budget_serves_total} />
      </div>

      <p className="text-[12px] text-sub">
        {campaign.creatives.length} creative{campaign.creatives.length === 1 ? "" : "s"}
        {campaign.creatives.length > 0 ? ` — ${approvedCount} approved` : ""}
      </p>

      {invoiceId ? (
        <a
          href={`/api/billing/ad-invoices/${invoiceId}/pdf`}
          className="inline-flex min-h-[44px] items-center text-[13px] font-semibold text-ink underline"
        >
          Download GST invoice (PDF)
        </a>
      ) : null}

      <div className="space-y-3 border-t border-line pt-3">
        <p className="text-[13px] font-extrabold text-ink">Performance</p>
        <div className="flex gap-2" role="group" aria-label="Analytics date range">
          {DAYS_OPTIONS.map((range) => (
            <button
              key={range}
              type="button"
              onClick={() => setDays(range)}
              className={cn(
                "min-h-[44px] rounded-pill px-4 text-[13px] font-semibold",
                days === range ? "bg-ink text-card" : "bg-line text-ink",
              )}
            >
              {range} days
            </button>
          ))}
        </div>

        {statsError ? (
          <AlertNotice>Could not load analytics — please try again.</AlertNotice>
        ) : stats === null ? (
          <Skeleton width="100%" height="160px" />
        ) : (
          <>
            <div className="grid grid-cols-2 gap-3 sm:grid-cols-4">
              <StatTile label="Impressions" value={stats.impressions.toLocaleString("en-IN")} />
              <StatTile label="Clicks" value={stats.clicks.toLocaleString("en-IN")} />
              <StatTile label="CTR" value={`${(stats.ctr_bp / 100).toFixed(2)}%`} />
              <StatTile label="Spend" value={rupees(stats.spend_paise)} />
            </div>
            <KeyCountRows title="By pincode" rows={stats.by_pincode} />
            <KeyCountRows title="By category" rows={stats.by_category} />
            <KeyCountRows
              title="By town tier"
              rows={stats.by_tier}
              labelFor={(key) => TIER_LABELS[Number(key)] ?? key}
            />
            {stats.by_day.length > 0 ? (
              <div className="overflow-x-auto">
                <table className="w-full min-w-[320px] text-left text-[12px]">
                  <thead>
                    <tr className="text-sub">
                      <th className="py-1 pr-3 font-semibold">Day</th>
                      <th className="py-1 pr-3 font-semibold">Impressions</th>
                      <th className="py-1 font-semibold">Clicks</th>
                    </tr>
                  </thead>
                  <tbody>
                    {stats.by_day.map((row) => (
                      <tr key={row.day} className="border-t border-line text-ink">
                        <td className="py-1 pr-3">{row.day}</td>
                        <td className="py-1 pr-3">{row.impressions}</td>
                        <td className="py-1">{row.clicks}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            ) : null}
            {stats.sampled ? (
              <p className="text-[12px] text-sub">
                This is a house/unpriced campaign — the traffic figures above are sampled, not an
                exact count.
              </p>
            ) : null}
          </>
        )}
      </div>
    </Card>
  );
}

/**
 * A-U7 W2 — the A3 reference's campaigns table (`#/ads`).
 *
 * Per-row impressions / clicks / CTR / spend come from
 * `GET /ads/my/campaigns/{id}/stats`, one request per campaign on the visible
 * page. The list payload does not carry them (they live in the day-
 * partitioned tracking tables), and the reference's table is mostly those
 * columns — so the choice was N bounded requests or a table of dashes. They
 * fire in parallel, they are capped by the list's own page size, and a row
 * whose stats have not landed shows "…" rather than a zero that looks
 * measured.
 *
 * NO WALLET CARD. The reference leads with an ad balance ("₹2,150 · auto-
 * invoiced with GST") and an "Add funds" button. There is no wallet:
 * payment is per-campaign, at checkout, through `POST /billing/ad-orders`.
 * A balance card would be an account that does not exist. The reference's
 * Razorpay TEST-mode chip is left out for the same reason — no endpoint
 * tells this client which mode billing is running in, and a hardcoded
 * "TEST" would be a claim about production the page cannot make.
 */
function StatCells({ stats }: { stats: RowStats | undefined }) {
  if (stats === undefined) {
    return (
      <>
        <td className={TD_NUM}>…</td>
        <td className={TD_NUM}>…</td>
        <td className={TD_NUM}>…</td>
      </>
    );
  }
  if (stats === null) {
    return (
      <>
        <td className={TD_NUM}>—</td>
        <td className={TD_NUM}>—</td>
        <td className={TD_NUM}>—</td>
      </>
    );
  }
  return (
    <>
      <td className={TD_NUM}>{stats.impressions.toLocaleString("en-IN")}</td>
      <td className={TD_NUM}>{stats.clicks.toLocaleString("en-IN")}</td>
      <td className={TD_NUM}>{(stats.ctr_bp / 100).toFixed(1)}%</td>
    </>
  );
}

const TH =
  "border-b border-cream-line px-3 py-2.5 text-left text-[10px] font-semibold uppercase tracking-[0.06em] text-muted";
const TD = "border-b border-cream-line px-3 py-2.5 align-middle";
const TD_NUM = `${TD} font-display font-semibold`;

export function AdsConsoleClient() {
  const [businesses, setBusinesses] = useState<BusinessRef[] | null>(null);
  const [businessError, setBusinessError] = useState(false);
  const [selectedId, setSelectedId] = useState<string | null>(null);

  const [campaigns, setCampaigns] = useState<MyCampaign[]>([]);
  const [cursor, setCursor] = useState<string | null>(null);
  const [listLoading, setListLoading] = useState(false);
  const [listError, setListError] = useState(false);
  const [loadingMore, setLoadingMore] = useState(false);
  /** campaign id → stats, `null` once a fetch failed for that row. */
  const [rowStats, setRowStats] = useState<Record<string, RowStats>>({});

  const [wizardOpen, setWizardOpen] = useState(false);
  const [expandedId, setExpandedId] = useState<string | null>(null);

  // Task 11 lesson (mirrored from products-client.tsx): capture current
  // selection for validation inside async callbacks that may resolve after
  // the user has already switched businesses.
  const selectedIdRef = useRef<string | null>(null);
  useEffect(() => {
    selectedIdRef.current = selectedId;
  }, [selectedId]);

  useEffect(() => {
    let cancelled = false;
    void (async () => {
      try {
        const body = await getJson("/api/directory/businesses?limit=50");
        if (cancelled) return;
        const list = (body.items as BusinessRef[] | undefined) ?? [];
        setBusinesses(list);
        if (list[0]) setSelectedId(list[0].id);
      } catch {
        if (!cancelled) setBusinessError(true);
      }
    })();
    return () => {
      cancelled = true;
    };
  }, []);

  /** One stats read per campaign, in parallel. A failure is that row's
   * problem: it shows dashes, the rest of the table is unaffected. */
  const loadStats = (rows: MyCampaign[], businessId: string) => {
    for (const row of rows) {
      void (async () => {
        try {
          const body = await getJson(`/api/ads/my/campaigns/${row.id}/stats?days=30`);
          if (selectedIdRef.current !== businessId) return;
          setRowStats((prev) => ({
            ...prev,
            [row.id]: {
              impressions: Number(body.impressions ?? 0),
              clicks: Number(body.clicks ?? 0),
              ctr_bp: Number(body.ctr_bp ?? 0),
              spend_paise: body.spend_paise == null ? null : Number(body.spend_paise),
            },
          }));
        } catch {
          if (selectedIdRef.current !== businessId) return;
          setRowStats((prev) => ({ ...prev, [row.id]: null }));
        }
      })();
    }
  };

  const loadCampaigns = async (businessId: string, cursorParam: string | null, append: boolean) => {
    if (append) setLoadingMore(true);
    else setListLoading(true);
    setListError(false);
    try {
      const params = new URLSearchParams({ business_id: businessId, limit: "20" });
      if (cursorParam) params.set("cursor", cursorParam);
      const body = await getJson(`/api/ads/my/campaigns?${params.toString()}`);
      if (selectedIdRef.current !== businessId) return;
      const items = (body.items as MyCampaign[] | undefined) ?? [];
      setCampaigns((prev) => (append ? [...prev, ...items] : items));
      setCursor((body.next_cursor as string | null | undefined) ?? null);
      loadStats(items, businessId);
    } catch {
      if (selectedIdRef.current !== businessId) return;
      if (!append) {
        setCampaigns([]);
        setListError(true);
      }
    } finally {
      if (selectedIdRef.current === businessId) {
        if (append) setLoadingMore(false);
        else setListLoading(false);
      }
    }
  };

  useEffect(() => {
    if (!selectedId) return;
    setCursor(null);
    setWizardOpen(false);
    setExpandedId(null);
    setRowStats({});
    void loadCampaigns(selectedId, null, false);
  }, [selectedId]);

  const handleLoadMore = () => {
    if (loadingMore || !cursor || !selectedId) return; // D20 load-more lesson: guard the in-flight state
    void loadCampaigns(selectedId, cursor, true);
  };

  const refreshCampaigns = () => {
    if (selectedId) void loadCampaigns(selectedId, null, false);
  };

  const topbar = (
    <ConsoleTopbar
      eyebrow="Ad engine · shared module, config per vertical"
      title="Advertise · Campaigns"
      sub="Sponsored is always labelled · organic ranking is never for sale · creatives are approved before they serve"
      actions={
        !wizardOpen && selectedId ? (
          <button type="button" className={consoleMoneyButtonClass} onClick={() => setWizardOpen(true)}>
            + New campaign
          </button>
        ) : null
      }
    />
  );

  if (businessError) {
    return (
      <>
        {topbar}
        <AlertNotice>Could not load your businesses — please try again.</AlertNotice>
      </>
    );
  }
  if (businesses === null) {
    return (
      <>
        {topbar}
        <div className="space-y-3">
          <Skeleton width="100%" height="44px" />
          <Skeleton width="100%" height="160px" />
        </div>
      </>
    );
  }
  if (businesses.length === 0) {
    return (
      <>
        {topbar}
        <EmptyState
          icon="📣"
          title="Create a listing first"
          action={
            <a href="/business/listings" className="text-[13px] font-semibold text-ink underline">
              Go to listings
            </a>
          }
        />
      </>
    );
  }

  return (
    <>
      {topbar}
      <div className="space-y-3">
        <Suspense fallback={null}>
          <PaidReturnBanner onSettled={refreshCampaigns} />
        </Suspense>

        {businesses.length > 1 ? (
          <label className={LABEL}>
            Business
            <select
              className={FIELD}
              value={selectedId ?? ""}
              onChange={(e) => setSelectedId(e.target.value)}
            >
              {businesses.map((b) => (
                <option key={b.id} value={b.id}>
                  {b.name}
                </option>
              ))}
            </select>
          </label>
        ) : null}

        {wizardOpen && selectedId ? (
          <CampaignWizard
            businessId={selectedId}
            onCancel={() => setWizardOpen(false)}
            onDone={() => {
              setWizardOpen(false);
              refreshCampaigns();
            }}
          />
        ) : listError ? (
          <AlertNotice>Could not load campaigns — please try again.</AlertNotice>
        ) : listLoading ? (
          <Skeleton width="100%" height="160px" />
        ) : campaigns.length === 0 ? (
          <ConsolePanel>
            <EmptyState
              icon="📢"
              title="No campaigns yet"
              description="Sponsored placement puts your listing at the top of your categories and pincodes. Approved creatives only — paid placement never changes organic ranking."
              action={
                <button
                  type="button"
                  className={consoleMoneyButtonClass}
                  onClick={() => setWizardOpen(true)}
                >
                  + New campaign
                </button>
              }
            />
          </ConsolePanel>
        ) : (
          <ConsolePanel title={`Your campaigns · ${campaigns.length}`}>
            {/* A3 `.tbl-wrap` — the table scrolls, the page never does. */}
            <div className="overflow-x-auto">
              <table className="w-full min-w-[720px] border-collapse text-xs">
                <thead>
                  <tr>
                    <th className={TH}>Campaign</th>
                    <th className={TH}>Status</th>
                    <th className={TH}>Placement</th>
                    <th className={TH}>Serves</th>
                    <th className={TH}>Impressions</th>
                    <th className={TH}>Clicks</th>
                    <th className={TH}>CTR</th>
                    <th className={TH}>Spend</th>
                    <th className={TH} />
                  </tr>
                </thead>
                <tbody>
                  {campaigns.map((campaign) => {
                    const stats = rowStats[campaign.id];
                    const spend =
                      stats && stats.spend_paise != null ? rupees(stats.spend_paise) : null;
                    return (
                      <Fragment key={campaign.id}>
                        <tr className="transition-colors hover:bg-cream">
                          <td className={TD}>
                            <b className="font-medium text-ink">{campaign.name}</b>
                            <br />
                            <small className="text-muted">
                              {campaign.flight_start} – {campaign.flight_end}
                            </small>
                          </td>
                          <td className={TD}>
                            <StatusChip status={campaign.display_status} />
                          </td>
                          <td className={TD}>
                            {campaign.placements.length > 0
                              ? campaign.placements.map((p) => p.slot_key).join(", ")
                              : "—"}
                          </td>
                          <td className={TD_NUM}>
                            {campaign.budget_serves_total == null
                              ? "—"
                              : `${campaign.budget_serves_used.toLocaleString(
                                  "en-IN",
                                )} / ${campaign.budget_serves_total.toLocaleString("en-IN")}`}
                          </td>
                          <StatCells stats={stats} />
                          <td className={TD_NUM}>
                            {spend ??
                              (campaign.price_paise != null ? rupees(campaign.price_paise) : "—")}
                          </td>
                          <td className={TD}>
                            <button
                              type="button"
                              className="tap-target inline-flex min-h-[32px] items-center rounded-btn border border-cream-line bg-card px-3 text-[11px] font-medium text-brand-deep"
                              onClick={() =>
                                setExpandedId((prev) => (prev === campaign.id ? null : campaign.id))
                              }
                            >
                              {expandedId === campaign.id ? "Hide" : "Manage"}
                            </button>
                          </td>
                        </tr>
                        {expandedId === campaign.id ? (
                          <tr>
                            <td className={`${TD} bg-cream`} colSpan={9}>
                              <CampaignDetailPanel
                                campaignId={campaign.id}
                                onChanged={refreshCampaigns}
                              />
                            </td>
                          </tr>
                        ) : null}
                      </Fragment>
                    );
                  })}
                </tbody>
              </table>
            </div>

            {cursor ? (
              <div className="mt-3">
                <Button type="button" variant="ghost" disabled={loadingMore} onClick={handleLoadMore}>
                  {loadingMore ? "Loading..." : "Load more"}
                </Button>
              </div>
            ) : null}

            {/* The frequency cap is a server setting (ads_freq_cap_per_day),
                not something this client is told — so it is described, not
                quoted as a number the page cannot verify. */}
            <ConsoleMiniNote>
              Impressions, clicks and spend are per campaign over the last 30 days; open Manage for
              the by-pincode and by-category split. Delivery is frequency-capped per viewer per day
              and every served creative carries its Sponsored label.
            </ConsoleMiniNote>
          </ConsolePanel>
        )}
      </div>
    </>
  );
}
