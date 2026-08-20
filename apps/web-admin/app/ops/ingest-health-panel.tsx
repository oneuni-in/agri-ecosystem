"use client";

/**
 * A-U4b C1: missed-day visibility. Both ingest engines write a run ledger
 * (market.ingest_runs / content.ingest_runs) precisely so a missed day is
 * distinguishable from a quiet source — this panel is the first thing that
 * READS them. The load/forbidden/loading shell mirrors pincode-tiers-panel;
 * the point of the panel is the warning line: an IST day in the last week
 * with no ok/empty run is named out loud ("missed: 18 Aug, 19 Aug"), never
 * left to be inferred by SQL. An empty ledger says "no runs recorded" — it
 * never fabricates an OK.
 */

import { Card, EmptyState, Skeleton, StateChip, useToast } from "@agri/ui";
import { useEffect, useState } from "react";

import { ApiError, getJson } from "@/lib/api";

type MarketRun = {
  id: string;
  source: string;
  started_at: string;
  finished_at: string | null;
  outcome: string;
  fetched: number;
  written: number;
  quarantined: number;
  newest_arrival_date: string | null;
  error: string | null;
};

type ContentRun = {
  id: string;
  source_slug: string;
  started_at: string;
  finished_at: string | null;
  outcome: string;
  fetched: number;
  written: number;
  duplicates: number;
  skipped: number;
  error: string | null;
};

/** The one shape both engines render as. */
type Run = {
  id: string;
  source: string;
  startedAt: string;
  outcome: string;
  fetched: number;
  written: number;
  error: string | null;
};

type EngineState = {
  runs: Run[] | null; // null = load failed (distinct from an empty ledger)
  forbidden: boolean;
};

/* ── IST day grouping (UTC+5:30, fixed offset — no library needed) ── */

const IST_OFFSET_MS = 5.5 * 60 * 60 * 1000;
const MONTHS = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"];

function istDayKey(utcMs: number): string {
  return new Date(utcMs + IST_OFFSET_MS).toISOString().slice(0, 10);
}

function istDayLabel(key: string): string {
  const [, month, day] = key.split("-");
  return `${Number(day)} ${MONTHS[Number(month) - 1]}`;
}

/** The 7 IST days before today (yesterday back), oldest first. */
function lastSevenIstDays(nowMs: number): string[] {
  const days: string[] = [];
  for (let back = 7; back >= 1; back -= 1) {
    days.push(istDayKey(nowMs - back * 24 * 60 * 60 * 1000));
  }
  return days;
}

function isCompleted(run: Run): boolean {
  return run.outcome === "ok" || run.outcome === "empty";
}

/* ── one engine's section ── */

function EngineSection({ title, state }: { title: string; state: EngineState }) {
  if (state.forbidden) {
    return (
      <EmptyState
        icon="🔒"
        title={`${title} runs are restricted`}
        description="You don't have permission to view this ingest ledger."
      />
    );
  }
  const runs = state.runs;
  if (runs === null) {
    return <p className="text-sm text-sub">{title}: could not load the run ledger.</p>;
  }

  const nowMs = Date.now();
  const todayKey = istDayKey(nowMs);
  const lastGood = runs.find(isCompleted); // API pages newest-first
  const completedDays = new Set(runs.filter(isCompleted).map((r) => istDayKey(Date.parse(r.startedAt))));
  const missed = lastSevenIstDays(nowMs).filter((day) => !completedDays.has(day));

  return (
    <div className="space-y-2">
      <div className="flex flex-wrap items-center gap-2">
        <h3 className="text-sm font-extrabold text-ink">{title}</h3>
        {runs.length === 0 ? (
          <span className="text-sm text-sub">no runs recorded</span>
        ) : lastGood ? (
          <>
            <StateChip
              tone={istDayKey(Date.parse(lastGood.startedAt)) === todayKey ? "ok" : "neutral"}
            >
              last run {istDayLabel(istDayKey(Date.parse(lastGood.startedAt)))} · {lastGood.outcome}
            </StateChip>
            {istDayKey(Date.parse(lastGood.startedAt)) !== todayKey ? (
              <span className="text-xs text-sub">no completed run yet today (IST)</span>
            ) : null}
          </>
        ) : (
          <StateChip tone="alert">no successful run on record</StateChip>
        )}
      </div>
      {missed.length > 0 && runs.length > 0 ? (
        <div className="rounded-card border border-alert-line bg-alert-bg p-3 text-[13px] font-semibold text-ink">
          ⚠ Days with no ok/empty run (last 7, IST) — missed: {missed.map(istDayLabel).join(", ")}
        </div>
      ) : null}
      {runs.length > 0 ? (
        <div className="overflow-x-auto">
          <table className="w-full min-w-[480px] text-left text-xs">
            <thead>
              <tr className="text-sub">
                <th className="py-1 pr-3 font-extrabold">Day (IST)</th>
                <th className="py-1 pr-3 font-extrabold">Source</th>
                <th className="py-1 pr-3 font-extrabold">Outcome</th>
                <th className="py-1 pr-3 font-extrabold">Fetched → written</th>
                <th className="py-1 font-extrabold">Error</th>
              </tr>
            </thead>
            <tbody>
              {runs.map((run) => (
                <tr key={run.id} className="border-t border-line text-ink">
                  <td className="py-1 pr-3 tabular-nums">
                    {istDayLabel(istDayKey(Date.parse(run.startedAt)))}
                  </td>
                  <td className="py-1 pr-3">{run.source}</td>
                  <td className="py-1 pr-3">
                    <StateChip tone={isCompleted(run) ? "ok" : "alert"}>{run.outcome}</StateChip>
                  </td>
                  <td className="py-1 pr-3 tabular-nums">
                    {run.fetched} → {run.written}
                  </td>
                  <td className="py-1 text-sub">{run.error ?? "—"}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      ) : null}
    </div>
  );
}

/* ── the panel ── */

export function IngestHealthPanel() {
  const { toast } = useToast();
  const [market, setMarket] = useState<EngineState>({ runs: null, forbidden: false });
  const [content, setContent] = useState<EngineState>({ runs: null, forbidden: false });
  const [loading, setLoading] = useState(true);

  const loadEngine = async (
    path: string,
    toRun: (item: Record<string, unknown>) => Run,
    set: (state: EngineState) => void,
  ) => {
    try {
      const body = await getJson(path);
      const items = Array.isArray(body.items) ? (body.items as Record<string, unknown>[]) : [];
      set({ runs: items.map(toRun), forbidden: false });
    } catch (error) {
      if (error instanceof ApiError && error.status === 403) {
        set({ runs: null, forbidden: true });
      } else {
        set({ runs: null, forbidden: false });
        toast({ title: error instanceof ApiError ? error.detail : "Could not load ingest runs" });
      }
    }
  };

  useEffect(() => {
    const load = async () => {
      setLoading(true);
      await Promise.all([
        loadEngine(
          "/market/ingest-runs?limit=50",
          (item) => {
            const run = item as unknown as MarketRun;
            return {
              id: run.id,
              source: run.source,
              startedAt: run.started_at,
              outcome: run.outcome,
              fetched: run.fetched,
              written: run.written,
              error: run.error,
            };
          },
          setMarket,
        ),
        loadEngine(
          "/content/ingest-runs?limit=50",
          (item) => {
            const run = item as unknown as ContentRun;
            return {
              id: run.id,
              source: run.source_slug,
              startedAt: run.started_at,
              outcome: run.outcome,
              fetched: run.fetched,
              written: run.written,
              error: run.error,
            };
          },
          setContent,
        ),
      ]);
      setLoading(false);
    };
    void load();
  }, []);

  return (
    <Card className="space-y-4 p-4">
      <h2 className="font-display text-lg font-extrabold text-ink">Ingest health</h2>
      {loading ? (
        <div className="space-y-2">
          <Skeleton width="100%" height="56px" />
          <Skeleton width="100%" height="56px" />
        </div>
      ) : (
        <>
          <EngineSection title="Mandi prices" state={market} />
          <EngineSection title="Content pull" state={content} />
        </>
      )}
    </Card>
  );
}
