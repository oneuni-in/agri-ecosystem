"use client";

import { Button, buttonVariants, Card, cn, EmptyState, Skeleton } from "@agri/ui";
import { useEffect, useState, type ReactNode } from "react";

import { ApiError, getJson, postJson } from "@/lib/api";

type InquiryType = "contact" | "milk_subscription";
type InquiryStatus = "new" | "responded" | "closed";

interface BusinessOut {
  id: string;
  name: string;
}

interface InboxInquiry {
  id: string;
  type: InquiryType;
  status: InquiryStatus;
  pincode: string;
  category: string | null;
  payload: Record<string, unknown>;
  from_user_id: string | null;
  created_at: string;
}

interface InboxStats {
  total: number;
  responded: number;
  avg_response_seconds: number | null;
}

// Copied verbatim from lead-form.tsx's field styling (D18 idiom) so this
// page reads as one system with the rest of the site.
const FIELD =
  "mt-1 block min-h-[44px] w-full rounded-btn border border-line bg-card px-3 py-2 text-[13px] text-ink";
const LABEL = "block text-[13px] font-semibold text-ink";

const STATUS_LABEL: Record<InquiryStatus, string> = {
  new: "New",
  responded: "Replied",
  closed: "Closed",
};
const STATUS_CLASS: Record<InquiryStatus, string> = {
  new: "bg-sponsored-bg text-sponsored-fg",
  responded: "bg-verified-bg text-verified-fg",
  closed: "bg-line text-sub",
};

function StatusChip({ status }: { status: InquiryStatus }) {
  return (
    <span
      className={cn(
        "inline-flex shrink-0 items-center self-start rounded-pill px-[9px] py-[3px] text-[11px] font-extrabold",
        STATUS_CLASS[status],
      )}
    >
      {STATUS_LABEL[status]}
    </span>
  );
}

function AlertNotice({ children }: { children: ReactNode }) {
  return (
    <div className="rounded-card border border-alert-line bg-alert-bg p-3 text-[13px] font-semibold text-ink">
      {children}
    </div>
  );
}

// Seconds -> "Xh" for >= 1h, else "Xm" (min 1m so a sub-minute reply never
// renders "0m").
function formatAvgResponse(seconds: number): string {
  if (seconds < 3600) return `${Math.max(1, Math.round(seconds / 60))}m`;
  return `${Math.round(seconds / 3600)}h`;
}

function renderPayload(inquiry: InboxInquiry): ReactNode {
  if (inquiry.type === "contact") {
    const message = typeof inquiry.payload.message === "string" ? inquiry.payload.message : "";
    return <p className="text-[13px] text-ink">{message}</p>;
  }
  const { qty_liters, milk_type, schedule } = inquiry.payload;
  return (
    <p className="text-[13px] text-ink">
      {String(qty_liters ?? "?")} L/day · {String(milk_type ?? "?")} · {String(schedule ?? "?")}
    </p>
  );
}

/**
 * Client island for `/business/inbox`. Self-contained (no props) so D20's
 * Business Console shell can mount it directly as the inbox tab's content.
 * Guests never reach this component - the page's server gate redirects
 * before it renders.
 */
export function InboxClient() {
  const [businesses, setBusinesses] = useState<BusinessOut[] | null>(null);
  const [businessesError, setBusinessesError] = useState(false);
  const [selectedId, setSelectedId] = useState<string | null>(null);

  const [items, setItems] = useState<InboxInquiry[]>([]);
  const [cursor, setCursor] = useState<string | null>(null);
  const [itemsLoading, setItemsLoading] = useState(false);
  const [itemsError, setItemsError] = useState(false);
  const [loadingMore, setLoadingMore] = useState(false);

  const [stats, setStats] = useState<InboxStats | null>(null);

  const [replyText, setReplyText] = useState<Record<string, string>>({});
  const [replySubmitting, setReplySubmitting] = useState<Record<string, boolean>>({});
  const [replyError, setReplyError] = useState<Record<string, string | null>>({});
  const [closing, setClosing] = useState<Record<string, boolean>>({});

  useEffect(() => {
    let cancelled = false;
    (async () => {
      try {
        const body = await getJson("/api/directory/businesses?limit=50");
        if (cancelled) return;
        const list = (body.items as BusinessOut[] | undefined) ?? [];
        setBusinesses(list);
        if (list[0]) setSelectedId(list[0].id);
      } catch {
        if (!cancelled) setBusinessesError(true);
      }
    })();
    return () => {
      cancelled = true;
    };
  }, []);

  const loadInbox = async (businessId: string, cursorParam: string | null, append: boolean) => {
    if (append) setLoadingMore(true);
    else {
      setItemsLoading(true);
      setItemsError(false);
    }
    try {
      const params = new URLSearchParams({ business_id: businessId, limit: "20" });
      if (cursorParam) params.set("cursor", cursorParam);
      const body = await getJson(`/api/leads/inbox?${params.toString()}`);
      const newItems = (body.items as InboxInquiry[] | undefined) ?? [];
      setItems((prev) => (append ? [...prev, ...newItems] : newItems));
      setCursor((body.next_cursor as string | null | undefined) ?? null);
    } catch {
      if (!append) setItemsError(true);
    } finally {
      if (append) setLoadingMore(false);
      else setItemsLoading(false);
    }
  };

  const loadStats = async (businessId: string) => {
    try {
      const body = await getJson(`/api/leads/inbox/stats?business_id=${businessId}`);
      setStats(body as unknown as InboxStats);
    } catch {
      setStats(null);
    }
  };

  useEffect(() => {
    if (!selectedId) return;
    setCursor(null);
    void loadInbox(selectedId, null, false);
    void loadStats(selectedId);
  }, [selectedId]);

  const reply = async (id: string) => {
    const body = replyText[id]?.trim();
    if (!body) return;
    setReplySubmitting((s) => ({ ...s, [id]: true }));
    setReplyError((s) => ({ ...s, [id]: null }));
    try {
      await postJson(`/api/leads/inquiries/${id}/responses`, { body });
      setItems((prev) => prev.map((i) => (i.id === id ? { ...i, status: "responded" } : i)));
      setReplyText((s) => ({ ...s, [id]: "" }));
      if (selectedId) void loadStats(selectedId);
    } catch (err) {
      setReplyError((s) => ({
        ...s,
        [id]:
          err instanceof ApiError && err.status === 422
            ? "Reply must be 1-2000 characters."
            : "Could not send reply — please try again.",
      }));
    } finally {
      setReplySubmitting((s) => ({ ...s, [id]: false }));
    }
  };

  const close = async (id: string) => {
    setClosing((s) => ({ ...s, [id]: true }));
    try {
      await postJson(`/api/leads/inquiries/${id}/close`);
      setItems((prev) => prev.map((i) => (i.id === id ? { ...i, status: "closed" } : i)));
    } catch {
      // Inline no-op: card stays actionable so the owner can retry.
    } finally {
      setClosing((s) => ({ ...s, [id]: false }));
    }
  };

  if (businessesError) {
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
    return (
      <EmptyState
        className="mt-4"
        icon="🏢"
        title="Claim your business to receive leads"
        action={
          <a href="/directory" className={cn(buttonVariants({ variant: "brand" }), "no-underline")}>
            Browse directory
          </a>
        }
      />
    );
  }

  return (
    <div className="mt-4 space-y-4">
      <label className={LABEL}>
        Business
        <select
          className={FIELD}
          value={selectedId ?? ""}
          onChange={(event) => setSelectedId(event.target.value)}
        >
          {businesses.map((business) => (
            <option key={business.id} value={business.id}>
              {business.name}
            </option>
          ))}
        </select>
      </label>

      {stats ? (
        <p className="text-[13px] text-sub">
          {stats.total} lead{stats.total === 1 ? "" : "s"} · {stats.responded} replied
          {stats.avg_response_seconds !== null
            ? ` · Avg response: ${formatAvgResponse(stats.avg_response_seconds)}`
            : ""}
        </p>
      ) : null}

      {itemsLoading ? (
        <Skeleton width="100%" height="120px" />
      ) : itemsError ? (
        <AlertNotice>Could not load leads — please try again.</AlertNotice>
      ) : items.length === 0 ? (
        <EmptyState icon="📭" title="No leads yet." />
      ) : (
        <div className="space-y-3">
          {items.map((inquiry) => (
            <Card key={inquiry.id} className="space-y-2 p-4">
              <div className="flex items-center justify-between gap-2">
                <span className="text-[13px] font-extrabold text-ink">
                  {inquiry.type === "contact" ? "Message" : "Milk subscription"}
                </span>
                <StatusChip status={inquiry.status} />
              </div>
              {renderPayload(inquiry)}
              <p className="text-[12px] text-sub">Pincode {inquiry.pincode}</p>
              {inquiry.status !== "closed" ? (
                <div className="space-y-2">
                  <label className={LABEL}>
                    Reply
                    <textarea
                      maxLength={2000}
                      rows={2}
                      value={replyText[inquiry.id] ?? ""}
                      onChange={(event) =>
                        setReplyText((s) => ({ ...s, [inquiry.id]: event.target.value }))
                      }
                      className={cn(FIELD, "min-h-[60px]")}
                    />
                  </label>
                  {replyError[inquiry.id] ? <AlertNotice>{replyError[inquiry.id]}</AlertNotice> : null}
                  <div className="flex gap-2">
                    <Button
                      type="button"
                      variant="brand"
                      disabled={!!replySubmitting[inquiry.id] || !replyText[inquiry.id]?.trim()}
                      onClick={() => void reply(inquiry.id)}
                    >
                      {replySubmitting[inquiry.id] ? "Sending..." : "Reply"}
                    </Button>
                    <Button
                      type="button"
                      variant="ghost"
                      disabled={!!closing[inquiry.id]}
                      onClick={() => void close(inquiry.id)}
                    >
                      {closing[inquiry.id] ? "Closing..." : "Close"}
                    </Button>
                  </div>
                </div>
              ) : null}
            </Card>
          ))}
          {cursor ? (
            <Button
              type="button"
              variant="ghost"
              disabled={loadingMore}
              onClick={() => selectedId && void loadInbox(selectedId, cursor, true)}
            >
              {loadingMore ? "Loading..." : "Load more"}
            </Button>
          ) : null}
        </div>
      )}
    </div>
  );
}
