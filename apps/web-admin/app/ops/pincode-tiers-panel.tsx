"use client";

/**
 * M4 Task 8: read-only histogram of GET /admin/ops/pincode-tiers/distribution
 * (Task 7). Modeled line-for-line on flags-panel.tsx's load/forbidden/loading
 * shell - a non-403 load failure surfaces as a toast (same idiom as
 * flags-panel), a 403 shows a restricted notice in place of the histogram.
 */

import { Card, EmptyState, Skeleton, useToast } from "@agri/ui";
import { useEffect, useState } from "react";

import { ApiError, getJson } from "@/lib/api";

type TierDistribution = {
  buckets: { tier: number; count: number }[];
  by_method: Record<string, number>;
  unclassified: number;
  total: number;
};

export function PincodeTiersPanel() {
  const { toast } = useToast();
  const [dist, setDist] = useState<TierDistribution | null>(null);
  const [loading, setLoading] = useState(true);
  const [forbidden, setForbidden] = useState(false);

  const load = async () => {
    setLoading(true);
    try {
      const body = await getJson("/ops/pincode-tiers/distribution");
      setDist(body as unknown as TierDistribution);
      setForbidden(false);
    } catch (error) {
      if (error instanceof ApiError && error.status === 403) {
        setForbidden(true);
      } else {
        toast({ title: error instanceof ApiError ? error.detail : "Could not load pincode tiers" });
      }
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    void load();
  }, []);

  if (!loading && forbidden) {
    return (
      <Card className="space-y-3 p-4">
        <h2 className="font-display text-lg font-extrabold text-ink">Pincode tiers</h2>
        <EmptyState
          icon="🔒"
          title="Pincode tiers are restricted"
          description="You don't have permission to view pincode tier distribution."
        />
      </Card>
    );
  }

  const byMethod = dist ? Object.entries(dist.by_method) : [];

  return (
    <Card className="space-y-3 p-4">
      <h2 className="font-display text-lg font-extrabold text-ink">Pincode tiers</h2>
      {loading ? (
        <div className="space-y-2">
          <Skeleton width="100%" height="56px" />
          <Skeleton width="100%" height="56px" />
        </div>
      ) : null}
      {!loading && (!dist || dist.total === 0) ? (
        <EmptyState icon="📍" title="No pincode tiers loaded yet" />
      ) : null}
      {!loading && dist && dist.total > 0 ? (
        <>
          <p className="text-xs text-sub">
            T1 metro &rarr; T5 extreme rural &middot; {dist.total} pincodes
            {dist.unclassified > 0 ? ` · ${dist.unclassified} unclassified` : ""}
          </p>
          <div className="mt-3 space-y-2">
            {(() => {
              const max = Math.max(1, ...dist.buckets.map((b) => b.count));
              return dist.buckets.map((b) => (
                <div key={b.tier} className="flex items-center gap-2">
                  <span className="w-8 text-sm text-sub">T{b.tier}</span>
                  <div className="h-4 flex-1 overflow-hidden rounded-pill bg-ghost">
                    <div
                      className="h-full rounded-pill bg-brand"
                      style={{ width: `${(b.count / max) * 100}%` }}
                    />
                  </div>
                  <span className="w-16 text-right text-sm tabular-nums text-ink">{b.count}</span>
                </div>
              ));
            })()}
          </div>
          {byMethod.length > 0 ? (
            <p className="mt-3 text-xs text-sub">
              {byMethod.map(([method, count]) => `${method}: ${count}`).join(" · ")}
            </p>
          ) : null}
        </>
      ) : null}
    </Card>
  );
}
