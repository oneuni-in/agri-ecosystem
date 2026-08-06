"use client";

/**
 * M5 Task 15: advertiser self-serve console shell — business selector +
 * campaign list (via the /api/ads/my/* proxy, Task 14) + the "New campaign"
 * wizard toggle. Per-campaign detail/creative management is Task 16; this
 * file only ever reads the list, it never mutates a campaign directly.
 */

import { Button, Card, EmptyState, Skeleton, cn } from "@agri/ui";
import { useEffect, useRef, useState, type ReactNode } from "react";

import { getJson } from "@/lib/api";

import { CampaignWizard } from "./campaign-wizard";

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

  // Task 11 lesson (mirrored from products-client.tsx): capture current
  // selection for validation inside async callbacks that may resolve after
  // the user has already switched businesses.
  const selectedIdRef = useRef<string | null>(null);
  useEffect(() => {
    selectedIdRef.current = selectedId;
  }, [selectedId]);

  useEffect(() => {
    void (async () => {
      try {
        const body = await getJson("/api/directory/businesses?limit=50");
        const list = (body.items as BusinessRef[] | undefined) ?? [];
        setBusinesses(list);
        if (list[0]) setSelectedId(list[0].id);
      } catch {
        setBusinessError(true);
      }
    })();
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
            <Card key={campaign.id} className="space-y-1 break-words p-4">
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
