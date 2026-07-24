"use client";

import { Button, Card, cn, EmptyState } from "@agri/ui";
import { useAgriUser } from "@agri/auth-client/react";
import Link from "next/link";
import { useCallback, useEffect, useState } from "react";

interface ResponseOut {
  id: string;
  body: string;
  created_at: string;
}

interface RouteOut {
  inquiry_id: string;
  business_id: string;
  business_name: string;
  status: "new" | "responded" | "closed";
  responses: ResponseOut[];
}

interface NeedOut {
  id: string;
  pincode: string;
  payload: {
    qty_liters?: string;
    milk_type?: string;
    schedule?: string;
    delivery_time?: string;
    note?: string;
  };
  status: "open" | "fulfilled" | "closed";
  accepted_business_id: string | null;
  has_voice: boolean;
  routed_count: number;
  created_at: string;
  routes: RouteOut[];
}

type LoadState = "loading" | "ready" | "error";

const MILK_ICON: Record<string, string> = {
  cow: "🐄",
  buffalo: "🐃",
  goat: "🐐",
  mixed: "🥛",
};

const SCHEDULE_LABEL: Record<string, string> = {
  daily: "Daily",
  alternate_days: "Alternate days",
  weekly: "Weekly",
};

const TIME_LABEL: Record<string, string> = {
  morning: "Morning",
  evening: "Evening",
  any: "Any time",
};

function statusChip(status: NeedOut["status"] | RouteOut["status"]): string {
  switch (status) {
    case "open":
    case "new":
      return "border-brand bg-brand-soft text-ink";
    case "responded":
    case "fulfilled":
      return "border-line bg-verified-bg text-verified-fg";
    default:
      return "border-line bg-card text-sub";
  }
}

function needSummary(need: NeedOut): string {
  const p = need.payload;
  const parts = [
    `${MILK_ICON[p.milk_type ?? ""] ?? "🥛"} ${p.qty_liters ?? "?"}L`,
    SCHEDULE_LABEL[p.schedule ?? ""] ?? p.schedule ?? "",
    TIME_LABEL[p.delivery_time ?? ""] ?? "",
  ];
  return parts.filter(Boolean).join(" · ");
}

/**
 * D25.C: posted needs + per-vendor responses + accept / mark-fulfilled /
 * close. Cursor-paginated "load more" (never offset). Inline status only
 * (no ToastProvider on web-milk).
 */
export function MyNeedsClient() {
  const { status } = useAgriUser({ autoSilentSso: false });
  const [needs, setNeeds] = useState<NeedOut[]>([]);
  const [nextCursor, setNextCursor] = useState<string | null>(null);
  const [state, setState] = useState<LoadState>("loading");
  const [actionError, setActionError] = useState<string | null>(null);
  const [busy, setBusy] = useState<string | null>(null); // need id being acted on

  const load = useCallback(async (cursor?: string | null) => {
    try {
      const url = cursor
        ? `/api/leads/needs/mine?cursor=${encodeURIComponent(cursor)}`
        : "/api/leads/needs/mine";
      const res = await fetch(url);
      if (!res.ok) {
        setState("error");
        return;
      }
      const body = (await res.json()) as { items: NeedOut[]; next_cursor: string | null };
      setNeeds((old) => (cursor ? [...old, ...body.items] : body.items));
      setNextCursor(body.next_cursor);
      setState("ready");
    } catch {
      setState("error");
    }
  }, []);

  useEffect(() => {
    if (status === "authenticated") void load();
  }, [status, load]);

  if (status === "loading") {
    return <p className="text-[13px] text-sub">Loading...</p>;
  }

  if (status === "unauthenticated") {
    return (
      <Card className="space-y-2 p-4">
        <p className="text-[13px] text-sub">Login with your phone to see your posted needs.</p>
        <a
          href={`/api/auth/login?next=${encodeURIComponent("/my-needs")}`}
          className="inline-block min-h-[44px] rounded-btn bg-brand px-4 py-3 text-[13px] font-bold text-white no-underline"
        >
          📱 Continue with phone · OTP
        </a>
      </Card>
    );
  }

  if (state === "loading") {
    return <p className="text-[13px] text-sub">Loading...</p>;
  }

  if (state === "error") {
    return (
      <Card className="p-4">
        <p className="text-[13px] font-semibold text-ink">
          Could not load your needs — please refresh.
        </p>
      </Card>
    );
  }

  if (needs.length === 0) {
    return (
      <EmptyState
        icon="🥛"
        title="No needs posted yet"
        description="Tell vendors near you what milk you need — everyone covering your pincode gets it."
        action={
          <Link
            href="/post-need"
            className="inline-block w-full min-h-[44px] rounded-btn bg-brand px-4 py-3 text-[13px] font-bold text-white no-underline"
          >
            Post my need · என் தேவை
          </Link>
        }
      />
    );
  }

  const act = async (needId: string, path: "fulfill" | "close", businessId?: string) => {
    setBusy(needId);
    setActionError(null);
    try {
      const res = await fetch(`/api/leads/needs/${needId}/${path}`, {
        method: "POST",
        headers: { "content-type": "application/json" },
        body: JSON.stringify(path === "fulfill" && businessId ? { business_id: businessId } : {}),
      });
      if (!res.ok) {
        setActionError("Could not update — please refresh and try again.");
      } else {
        await load();
      }
    } catch {
      setActionError("Could not update — please refresh and try again.");
    } finally {
      setBusy(null);
    }
  };

  return (
    <div className="space-y-3" data-testid="my-needs-list">
      {actionError ? (
        <div className="rounded-card border border-alert-line bg-alert-bg p-3 text-[13px] font-semibold text-ink">
          {actionError}
        </div>
      ) : null}
      {needs.map((need) => (
        <Card key={need.id} className="space-y-3 p-4" data-testid="need-card">
          <header className="flex flex-wrap items-center justify-between gap-2">
            <div>
              <p className="text-[15px] font-extrabold text-ink">{needSummary(need)}</p>
              <p className="text-[12px] text-sub">
                📍 {need.pincode} · {new Date(need.created_at).toLocaleDateString("en-IN")} · sent
                to {need.routed_count} vendor{need.routed_count === 1 ? "" : "s"}
              </p>
            </div>
            <span
              className={cn(
                "rounded-btn border px-2 py-1 text-[12px] font-bold capitalize",
                statusChip(need.status),
              )}
              data-testid="need-status"
            >
              {need.status}
            </span>
          </header>

          {need.has_voice ? (
            <audio
              controls
              preload="none"
              src={`/api/leads/needs/${need.id}/voice`}
              className="h-11 max-w-full"
            />
          ) : null}

          <ul className="space-y-2">
            {need.routes.map((route) => (
              <li key={route.inquiry_id} className="rounded-card border border-line p-3">
                <div className="flex flex-wrap items-center justify-between gap-2">
                  <span className="text-[13px] font-bold text-ink">{route.business_name}</span>
                  <span
                    className={cn(
                      "rounded-btn border px-2 py-0.5 text-[11px] font-bold capitalize",
                      statusChip(route.status),
                    )}
                  >
                    {route.status}
                  </span>
                </div>
                {route.responses.map((response) => (
                  <p
                    key={response.id}
                    className="mt-2 rounded-card bg-brand-soft p-2 text-[13px] text-ink"
                    data-testid="need-response"
                  >
                    {response.body}
                  </p>
                ))}
                {need.status === "open" && route.responses.length > 0 ? (
                  <Button
                    type="button"
                    variant="brand"
                    className="mt-2 max-w-[220px]"
                    disabled={busy === need.id}
                    onClick={() => void act(need.id, "fulfill", route.business_id)}
                    data-testid="accept-vendor"
                  >
                    ✅ Accept <span className="vern">· ஏற்றுக்கொள்</span>
                  </Button>
                ) : null}
              </li>
            ))}
          </ul>

          {need.status === "open" ? (
            <footer className="flex flex-wrap gap-2">
              <Button
                type="button"
                variant="ghost"
                className="max-w-[200px]"
                disabled={busy === need.id}
                onClick={() => void act(need.id, "fulfill")}
                data-testid="mark-fulfilled"
              >
                ✅ Mark fulfilled
              </Button>
              <Button
                type="button"
                variant="ghost"
                className="max-w-[140px]"
                disabled={busy === need.id}
                onClick={() => void act(need.id, "close")}
                data-testid="close-need"
              >
                ✖ Close
              </Button>
            </footer>
          ) : null}
        </Card>
      ))}
      {nextCursor ? (
        <Button
          type="button"
          variant="ghost"
          className="max-w-[200px]"
          onClick={() => void load(nextCursor)}
        >
          Load more
        </Button>
      ) : null}
    </div>
  );
}
