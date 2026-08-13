"use client";

/**
 * Ad performance read surface (U3, read-only). Impressions, clicks and CTR by
 * slot AND by creative from the M2/M3 beacons (ads.impressions / ads.clicks)
 * over a date range. This is NOT the unified analytics funnel (A6, deferred):
 * slot and creative counters only, no clicks→views→reveals→leads chain. CTR is
 * the plain ratio the backend already computed; the UI only formats it.
 */
import {
  AdminDataTable,
  Button,
  ConsolePageHeader,
  ConsolePanel,
  cn,
  consoleControlClass,
  type AdminColumn,
} from "@agri/ui";
import { useCallback, useEffect, useState } from "react";

import { ApiError, getJson } from "@/lib/api";

interface PerfRow {
  key: string;
  impressions: number;
  clicks: number;
  ctr: number;
}

function isoDaysAgo(days: number): string {
  const d = new Date();
  d.setUTCDate(d.getUTCDate() - days);
  return d.toISOString().slice(0, 10);
}

function columns(keyHeader: string): readonly AdminColumn<PerfRow>[] {
  return [
    { key: "key", header: keyHeader, cell: (r) => r.key },
    { key: "impr", header: "Impressions", cell: (r) => r.impressions.toLocaleString("en-IN"), align: "right" },
    { key: "clicks", header: "Clicks", cell: (r) => r.clicks.toLocaleString("en-IN"), align: "right" },
    { key: "ctr", header: "CTR", cell: (r) => `${(r.ctr * 100).toFixed(2)}%`, align: "right" },
  ];
}

export function AdPerformanceView() {
  const [from, setFrom] = useState(isoDaysAgo(14));
  const [to, setTo] = useState(isoDaysAgo(0));
  const [bySlot, setBySlot] = useState<PerfRow[]>([]);
  const [byCreative, setByCreative] = useState<PerfRow[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | undefined>(undefined);

  const load = useCallback(async () => {
    setLoading(true);
    setError(undefined);
    try {
      const body = (await getJson(
        `/ads/performance?date_from=${from}&date_to=${to}`,
      )) as { by_slot: PerfRow[]; by_creative: PerfRow[] };
      setBySlot(body.by_slot ?? []);
      setByCreative(body.by_creative ?? []);
    } catch (e) {
      setError(e instanceof ApiError ? e.detail : "request_failed");
    } finally {
      setLoading(false);
    }
  }, [from, to]);

  useEffect(() => {
    void load();
  }, [load]);

  const emptySlot = { icon: "📈", title: "No impressions in range.", description: "Widen the date range, or wait for the beacons to fire." };

  return (
    <main className="space-y-4">
      <ConsolePageHeader
        title="Ad performance"
        sub="Slot & creative counters from the M2/M3 beacons · read-only · not the analytics funnel"
        action={
          <div className="flex flex-wrap items-end gap-2">
            <label className="text-[12px] text-sub">
              From
              <input
                type="date"
                aria-label="From date"
                value={from}
                max={to}
                onChange={(e) => setFrom(e.target.value)}
                className={cn(consoleControlClass, "mt-0.5 w-auto")}
              />
            </label>
            <label className="text-[12px] text-sub">
              To
              <input
                type="date"
                aria-label="To date"
                value={to}
                min={from}
                onChange={(e) => setTo(e.target.value)}
                className={cn(consoleControlClass, "mt-0.5 w-auto")}
              />
            </label>
            <Button variant="ghost" className="flex-none px-4" onClick={() => void load()}>
              Refresh
            </Button>
          </div>
        }
      />
      <ConsolePanel title="By slot">
        <AdminDataTable
          caption="Ad performance by slot"
          columns={columns("Slot")}
          rows={bySlot}
          rowKey={(r) => r.key}
          loading={loading}
          {...(error ? { error: `Could not load performance (${error}).` } : {})}
          empty={emptySlot}
        />
      </ConsolePanel>
      <ConsolePanel title="By creative">
        <AdminDataTable
          caption="Ad performance by creative"
          columns={columns("Creative")}
          rows={byCreative}
          rowKey={(r) => r.key}
          loading={loading}
          {...(error ? { error: `Could not load performance (${error}).` } : {})}
          empty={{ ...emptySlot, title: "No creative activity in range." }}
        />
      </ConsolePanel>
    </main>
  );
}
