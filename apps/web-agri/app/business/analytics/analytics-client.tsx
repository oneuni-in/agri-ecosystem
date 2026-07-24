"use client";

import { Card, EmptyState, Skeleton, cn } from "@agri/ui";
import { useEffect, useState, type ReactNode } from "react";

import { getJson } from "@/lib/api";

interface BusinessRef {
  id: string;
  name: string;
}

interface PincodeCount {
  pincode: string;
  count: number;
}

interface Section {
  total: number;
  by_pincode: PincodeCount[];
}

interface Analytics {
  days: number;
  views: Section;
  reveals: Section;
  leads: Section;
  response: { total: number; responded: number; avg_response_seconds: number | null };
}

const FIELD =
  "mt-1 block min-h-[44px] w-full rounded-btn border border-line bg-card px-3 py-2 text-[13px] text-ink";
const LABEL = "block text-[13px] font-semibold text-ink";
const RANGES = [7, 30, 90] as const;

function AlertNotice({ children }: { children: ReactNode }) {
  return (
    <div className="rounded-card border border-alert-line bg-alert-bg p-3 text-[13px] font-semibold text-ink">
      {children}
    </div>
  );
}

function formatAvg(seconds: number | null): string {
  if (seconds === null) return "—";
  if (seconds < 3600) return `${Math.max(1, Math.round(seconds / 60))}m`;
  return `${Math.round(seconds / 3600)}h`;
}

function StatTile({ label, value }: { label: string; value: string }) {
  return (
    <Card className="p-4">
      <p className="text-[12px] font-semibold uppercase tracking-wide text-sub">{label}</p>
      <p className="font-display text-[24px] font-extrabold text-ink">{value}</p>
    </Card>
  );
}

function PincodeRows({ title, section }: { title: string; section: Section }) {
  if (section.by_pincode.length === 0) return null;
  return (
    <Card className="space-y-2 p-4">
      <p className="text-[13px] font-extrabold text-ink">{title} by pincode</p>
      <ul className="space-y-1">
        {section.by_pincode.map((row) => (
          <li key={row.pincode} className="flex justify-between text-[13px] text-ink">
            <span>{row.pincode === "unknown" ? "Unknown pincode" : row.pincode}</span>
            <span className="font-semibold">{row.count}</span>
          </li>
        ))}
      </ul>
    </Card>
  );
}

export function AnalyticsClient() {
  const [businesses, setBusinesses] = useState<BusinessRef[] | null>(null);
  const [loadError, setLoadError] = useState(false);
  const [selectedId, setSelectedId] = useState<string | null>(null);
  const [days, setDays] = useState<(typeof RANGES)[number]>(30);
  const [data, setData] = useState<Analytics | null>(null);
  const [dataError, setDataError] = useState(false);

  useEffect(() => {
    void (async () => {
      try {
        const body = await getJson("/api/directory/businesses?limit=50");
        const list = (body.items as BusinessRef[] | undefined) ?? [];
        setBusinesses(list);
        if (list[0]) setSelectedId(list[0].id);
      } catch {
        setLoadError(true);
      }
    })();
  }, []);

  useEffect(() => {
    if (!selectedId) return;
    setData(null);
    setDataError(false);
    let cancelled = false;
    void (async () => {
      try {
        const body = await getJson(`/api/directory/businesses/${selectedId}/analytics?days=${days}`);
        if (cancelled) return;
        setData(body as unknown as Analytics);
      } catch {
        if (cancelled) return;
        setDataError(true);
      }
    })();
    return () => { cancelled = true; };
  }, [selectedId, days]);

  if (loadError) {
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
        <Skeleton width="100%" height="120px" />
      </div>
    );
  }
  if (businesses.length === 0) {
    return <EmptyState className="mt-4" icon="📈" title="Create a listing to see analytics." />;
  }

  return (
    <div className="mt-4 space-y-4">
      <label className={LABEL}>
        Business
        <select className={FIELD} value={selectedId ?? ""} onChange={(e) => setSelectedId(e.target.value)}>
          {businesses.map((b) => (
            <option key={b.id} value={b.id}>{b.name}</option>
          ))}
        </select>
      </label>

      <div className="flex gap-2" role="group" aria-label="Date range">
        {RANGES.map((range) => (
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

      {dataError ? (
        <AlertNotice>Could not load analytics — please try again.</AlertNotice>
      ) : data === null ? (
        <Skeleton width="100%" height="160px" />
      ) : (
        <>
          <div className="grid grid-cols-2 gap-3 sm:grid-cols-4">
            <StatTile label="Profile views" value={String(data.views.total)} />
            <StatTile label="Contact reveals" value={String(data.reveals.total)} />
            <StatTile label="Leads" value={String(data.leads.total)} />
            <StatTile label="Avg response" value={formatAvg(data.response.avg_response_seconds)} />
          </div>
          <PincodeRows title="Views" section={data.views} />
          <PincodeRows title="Reveals" section={data.reveals} />
          <PincodeRows title="Leads" section={data.leads} />
        </>
      )}
    </div>
  );
}
