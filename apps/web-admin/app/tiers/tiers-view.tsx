"use client";

/**
 * Pincode tiers read surface (U3, read-only). Renders M4's computed T1–T5 per
 * pincode WITH the census inputs (population, grade, verified-user count) so an
 * operator can sanity-check the classification before KYC. The tier shown is
 * whatever `GET /admin/ops/pincode-tiers` returns from geo.pincode_tiers —
 * never computed in the UI. The single-pincode override stays in the Ops
 * console; this surface writes nothing.
 */
import {
  AdminDataTable,
  ConsolePageHeader,
  StateChip,
  cn,
  consoleControlClass,
  type AdminColumn,
} from "@agri/ui";
import { useState } from "react";

import { useAdminList } from "@/lib/use-admin-list";

interface TierRow {
  pincode: string;
  tier: number;
  population: number;
  population_grade: string;
  user_count: number;
  method: string;
  computed_at: string | null;
}

const columns: readonly AdminColumn<TierRow>[] = [
  { key: "pincode", header: "Pincode", cell: (r) => r.pincode },
  { key: "tier", header: "Tier", cell: (r) => <StateChip tone="info">{`T${r.tier}`}</StateChip> },
  { key: "population", header: "Population", cell: (r) => r.population.toLocaleString("en-IN"), align: "right" },
  { key: "grade", header: "Census grade", cell: (r) => r.population_grade, hideBelow: "lg" },
  { key: "users", header: "Verified users", cell: (r) => r.user_count.toLocaleString("en-IN"), align: "right", hideBelow: "md" },
  { key: "method", header: "Method", cell: (r) => r.method, hideBelow: "xl" },
];

const TIER_FILTERS = ["all", "1", "2", "3", "4", "5"] as const;

export function TiersView() {
  const [tier, setTier] = useState<(typeof TIER_FILTERS)[number]>("all");
  const path = `/ops/pincode-tiers${tier === "all" ? "" : `?tier=${tier}`}`;
  const { items, cursor, loading, loadingMore, error, reload } = useAdminList<TierRow>(path);

  return (
    <main>
      <ConsolePageHeader
        title="Pincode tiers"
        sub="M4 computed T1–T5 with census inputs · read-only (override lives in Ops)"
      />
      <AdminDataTable
        caption="Pincode tiers"
        columns={columns}
        rows={items}
        rowKey={(r) => r.pincode}
        loading={loading}
        loadingMore={loadingMore}
        {...(error ? { error: `Could not load tiers (${error}).` } : {})}
        empty={{
          icon: "🗺️",
          title: "No pincodes at this tier.",
          description: "Change the tier filter to see the rest of the distribution.",
        }}
        nextCursor={cursor}
        onLoadMore={() => cursor && void reload(cursor)}
        toolbar={
          <label className="flex items-center gap-2 text-[13px] text-sub">
            Tier
            <select
              aria-label="Filter by tier"
              value={tier}
              onChange={(e) => setTier(e.target.value as (typeof TIER_FILTERS)[number])}
              className={cn(consoleControlClass, "mt-0 w-auto")}
            >
              {TIER_FILTERS.map((t) => (
                <option key={t} value={t}>
                  {t === "all" ? "All tiers" : `T${t}`}
                </option>
              ))}
            </select>
          </label>
        }
      />
    </main>
  );
}
