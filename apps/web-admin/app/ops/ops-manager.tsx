"use client";

/**
 * D21 Task 14: the Ops Console. Type tabs (from /admin/moderation/summary's
 * pending counts) drive ONE <ModerationQueue> instance, remounted per tab
 * (key={active}) rather than re-fetched in place - simplest way to keep the
 * shared queue component ignorant of tab-switching. The Flags panel sits
 * below, always visible, per the Task 14 brief's "below" option.
 */

import { RatingStars, cn, useToast } from "@agri/ui";
import { useEffect, useState, type ReactNode } from "react";

import { ApiError, getJson } from "@/lib/api";
import { ModerationQueue, type ModItem } from "@/components/moderation-queue";

import { FlagsPanel } from "./flags-panel";

const TYPES = [
  { key: "claim", label: "Claims" },
  { key: "verification", label: "Verifications" },
  { key: "review", label: "Reviews" },
  { key: "creative", label: "Ad Creatives" },
] as const;

type TypeKey = (typeof TYPES)[number]["key"];

/** Badge's variant union (sponsored/verified/cert) is fixed marketing
 * semantics - it doesn't model an open-ended target_type/review string, so
 * chips render as a plain token-styled pill instead (same idiom as
 * reviews-manager.tsx's TargetChip / users-manager.tsx's StatusPill). */
function Chip({ label }: { label: string }) {
  return (
    <span className="inline-flex items-center self-start rounded-pill border border-line bg-ghost px-[9px] py-[3px] text-[11px] font-extrabold text-ink">
      {label}
    </span>
  );
}

function stringField(payload: Record<string, unknown>, key: string): string {
  const value = payload[key];
  return typeof value === "string" ? value : "";
}

function bodyText(payload: Record<string, unknown>): string {
  const body = payload.body;
  if (!body || typeof body !== "object") return "—";
  const dict = body as Record<string, unknown>;
  const preferred = dict.en;
  if (typeof preferred === "string" && preferred.trim()) return preferred.trim();
  for (const value of Object.values(dict)) {
    if (typeof value === "string" && value.trim()) return value.trim();
  }
  return "—";
}

function claimRenderItem(item: ModItem): ReactNode {
  return (
    <div className="space-y-1">
      <p className="text-sm font-semibold text-ink">{item.title}</p>
      <p className="text-xs text-sub">Claimed by {stringField(item.payload, "claimant_user_id") || "—"}</p>
    </div>
  );
}

function verificationRenderItem(item: ModItem): ReactNode {
  return (
    <div className="space-y-1">
      <p className="text-sm font-semibold text-ink">{item.title}</p>
      <p className="text-xs text-sub">Method: {stringField(item.payload, "method") || "—"}</p>
    </div>
  );
}

function reviewRenderItem(item: ModItem): ReactNode {
  const rating = item.payload.rating;
  const targetType = stringField(item.payload, "target_type") || "—";
  return (
    <div className="space-y-2">
      <div className="flex items-center justify-between gap-2">
        <RatingStars value={typeof rating === "number" ? rating : 0} />
        <Chip label={targetType} />
      </div>
      <p className="text-sm text-ink">{bodyText(item.payload)}</p>
      <p className="text-xs text-sub">by {stringField(item.payload, "author_user_id") || "—"}</p>
    </div>
  );
}

function creativeRenderItem(item: ModItem): ReactNode {
  const copy = item.payload.copy;
  const en =
    copy && typeof copy === "object" ? (copy as Record<string, unknown>).en : undefined;
  const title =
    en && typeof en === "object"
      ? stringField(en as Record<string, unknown>, "title").trim() || item.title
      : item.title;
  const body =
    en && typeof en === "object"
      ? stringField(en as Record<string, unknown>, "body").trim() || item.summary
      : item.summary;
  const targetUrl = stringField(item.payload, "target_url") || "—";
  return (
    <div className="space-y-1">
      <p className="text-sm font-semibold text-ink">{title}</p>
      {/* Copy is shown as PLAIN TEXT only - never rendered as HTML/markup. */}
      <p className="text-sm text-ink">{body}</p>
      <p className="break-all text-xs text-sub">
        Target URL (text only, never a link): {targetUrl}
      </p>
    </div>
  );
}

function claimMediaUrl(item: ModItem, index: number): string {
  return `/api/admin/directory/claims/${item.id}/evidence/${index}`;
}

function verificationMediaUrl(item: ModItem, index: number): string {
  return `/api/admin/directory/verifications/${item.id}/docs/${index}`;
}

function creativeMediaUrl(item: ModItem, index: number): string {
  return `/api/admin/ads/creatives/${item.id}/media/${index}`;
}

function queueConfig(typeKey: TypeKey): {
  renderItem: (item: ModItem) => ReactNode;
  mediaUrl?: (item: ModItem, index: number) => string;
} {
  switch (typeKey) {
    case "claim":
      return { renderItem: claimRenderItem, mediaUrl: claimMediaUrl };
    case "verification":
      return { renderItem: verificationRenderItem, mediaUrl: verificationMediaUrl };
    case "review":
      return { renderItem: reviewRenderItem };
    case "creative":
      return { renderItem: creativeRenderItem, mediaUrl: creativeMediaUrl };
  }
}

export function OpsManager() {
  const { toast } = useToast();
  const [active, setActive] = useState<TypeKey>("claim");
  const [counts, setCounts] = useState<Record<string, number>>({});
  const [summaryLoading, setSummaryLoading] = useState(true);

  useEffect(() => {
    const loadSummary = async () => {
      setSummaryLoading(true);
      try {
        const body = await getJson("/moderation/summary");
        setCounts((body.counts ?? {}) as Record<string, number>);
      } catch (error) {
        toast({ title: error instanceof ApiError ? error.detail : "Could not load counts" });
      } finally {
        setSummaryLoading(false);
      }
    };
    void loadSummary();
  }, []);

  const config = queueConfig(active);

  // Keep tab chips in sync without a refetch: a decision (or a 409 drop)
  // means one fewer pending item of that type, floored at 0.
  const handleDecided = (typeKey: string) => {
    setCounts((prev) => ({ ...prev, [typeKey]: Math.max(0, (prev[typeKey] ?? 0) - 1) }));
  };

  return (
    <main className="mx-auto max-w-3xl space-y-6 p-4">
      <h1 className="text-xl font-bold text-ink">Ops console</h1>
      <div role="tablist" aria-label="Moderation type" className="flex flex-wrap gap-2">
        {TYPES.map((type) => (
          <button
            key={type.key}
            type="button"
            role="tab"
            aria-selected={active === type.key}
            onClick={() => setActive(type.key)}
            className={cn(
              "flex min-h-[44px] items-center gap-2 rounded-btn px-3 py-2 text-sm font-extrabold",
              active === type.key ? "bg-brand text-white" : "bg-ghost text-ink",
            )}
          >
            {type.label}
            <span className="inline-flex items-center rounded-pill bg-card px-[9px] py-[2px] text-[11px] font-extrabold text-ink">
              {summaryLoading ? "…" : (counts[type.key] ?? 0)}
            </span>
          </button>
        ))}
      </div>
      <ModerationQueue
        key={active}
        typeKey={active}
        renderItem={config.renderItem}
        mediaUrl={config.mediaUrl}
        onDecided={handleDecided}
      />
      <FlagsPanel />
    </main>
  );
}
