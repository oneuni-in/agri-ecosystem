"use client";

/**
 * M5 Task 15/16: advertiser self-serve console shell — business selector +
 * campaign list (via the /api/ads/my/* proxy, Task 14) + the "New campaign"
 * wizard toggle + (Task 16) a post-checkout status banner and a per-campaign
 * detail/analytics panel (pause/resume, budget, stats, invoice).
 */

import { Button, Card, EmptyState, Skeleton, cn } from "@agri/ui";
import { useSearchParams } from "next/navigation";
import { Suspense, useEffect, useRef, useState, type ReactNode } from "react";

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
  flight_start: string;
  flight_end: string;
  placements: PlacementSnapshot[];
}

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

export function AdsConsoleClient() {
  const [businesses, setBusinesses] = useState<BusinessRef[] | null>(null);
  const [businessError, setBusinessError] = useState(false);
  const [selectedId, setSelectedId] = useState<string | null>(null);

  const [campaigns, setCampaigns] = useState<MyCampaign[]>([]);
  const [cursor, setCursor] = useState<string | null>(null);
  const [listLoading, setListLoading] = useState(false);
  const [listError, setListError] = useState(false);
  const [loadingMore, setLoadingMore] = useState(false);

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
    void loadCampaigns(selectedId, null, false);
  }, [selectedId]);

  const handleLoadMore = () => {
    if (loadingMore || !cursor || !selectedId) return; // D20 load-more lesson: guard the in-flight state
    void loadCampaigns(selectedId, cursor, true);
  };

  const refreshCampaigns = () => {
    if (selectedId) void loadCampaigns(selectedId, null, false);
  };

  if (businessError) {
    return (
      <div className="mt-4">
        <AlertNotice>Could not load your businesses — please try again.</AlertNotice>
      </div>
    );
  }
  if (businesses === null) {
    return (
      <div className="mt-4 space-y-3">
        <Skeleton width="100%" height="44px" />
        <Skeleton width="100%" height="160px" />
      </div>
    );
  }
  if (businesses.length === 0) {
    return (
      <EmptyState
        className="mt-4"
        icon="📣"
        title="Create a listing first"
        action={
          <a href="/business/listings" className="text-[13px] font-semibold text-ink underline">
            Go to listings
          </a>
        }
      />
    );
  }

  return (
    <div className="mt-4 space-y-4">
      <Suspense fallback={null}>
        <PaidReturnBanner onSettled={refreshCampaigns} />
      </Suspense>

      <label className={LABEL}>
        Business
        <select className={FIELD} value={selectedId ?? ""} onChange={(e) => setSelectedId(e.target.value)}>
          {businesses.map((b) => (
            <option key={b.id} value={b.id}>
              {b.name}
            </option>
          ))}
        </select>
      </label>

      {listError ? (
        <AlertNotice>Could not load campaigns — please try again.</AlertNotice>
      ) : listLoading ? (
        <Skeleton width="100%" height="120px" />
      ) : campaigns.length === 0 ? (
        <EmptyState icon="📢" title="No campaigns yet — start one below." />
      ) : (
        <div className="space-y-3">
          {campaigns.map((campaign) => (
            <Card key={campaign.id} className="space-y-2 break-words p-4">
              <div className="flex flex-wrap items-center gap-x-2 gap-y-1">
                <span className="min-w-0 break-words text-[13px] font-extrabold text-ink">
                  {campaign.name}
                </span>
                <StatusChip status={campaign.display_status} />
              </div>
              <p className="text-[12px] text-sub">
                {campaign.flight_start} → {campaign.flight_end}
                {campaign.price_paise != null ? ` · ${rupees(campaign.price_paise)}` : " · Not priced yet"}
              </p>
              {campaign.placements.length > 0 ? (
                <p className="text-[12px] text-sub">
                  {campaign.placements.map((p) => p.slot_key).join(", ")}
                </p>
              ) : null}
              <Button
                type="button"
                variant="ghost"
                className="min-h-[44px] min-w-0 max-w-[200px] break-words"
                onClick={() => setExpandedId((prev) => (prev === campaign.id ? null : campaign.id))}
              >
                {expandedId === campaign.id ? "Hide details" : "Manage"}
              </Button>
              {expandedId === campaign.id ? (
                <CampaignDetailPanel campaignId={campaign.id} onChanged={refreshCampaigns} />
              ) : null}
            </Card>
          ))}
          {cursor ? (
            <Button type="button" variant="ghost" disabled={loadingMore} onClick={handleLoadMore}>
              {loadingMore ? "Loading..." : "Load more"}
            </Button>
          ) : null}
        </div>
      )}

      {wizardOpen && selectedId ? (
        <CampaignWizard
          businessId={selectedId}
          onDone={() => {
            setWizardOpen(false);
            refreshCampaigns();
          }}
        />
      ) : (
        <Button type="button" variant="brand" onClick={() => setWizardOpen(true)}>
          New campaign
        </Button>
      )}
    </div>
  );
}
