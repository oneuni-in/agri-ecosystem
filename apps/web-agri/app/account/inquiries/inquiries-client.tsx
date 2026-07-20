"use client";

import { Card, cn, EmptyState, Skeleton, Button } from "@agri/ui";
import { useEffect, useState, type ReactNode } from "react";

import { getJson } from "@/lib/api";

type InquiryType = "contact" | "milk_subscription";
type InquiryStatus = "new" | "responded" | "closed";

interface ResponseOut {
  id: string;
  body: string;
  created_at: string;
}

interface MyInquiry {
  id: string;
  type: InquiryType;
  business_id: string;
  status: InquiryStatus;
  payload: Record<string, unknown>;
  responses: ResponseOut[];
  created_at: string;
}

// Submitter-facing labels differ from the owner inbox's ("new" -> "Sent",
// not "New") - kept as a separate map/component per-file, matching the
// repo's existing lead-form.tsx/review-form.tsx "copied verbatim" idiom.
const STATUS_LABEL: Record<InquiryStatus, string> = {
  new: "Sent",
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

function renderPayload(inquiry: MyInquiry): ReactNode {
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
 * Client island for `/account/inquiries` - the submitter-side counterpart to
 * `InboxClient`. Self-contained (no props), lists the caller's own
 * inquiries newest-first with cursor "Load more" and each reply thread
 * embedded inline.
 */
export function InquiriesClient() {
  const [items, setItems] = useState<MyInquiry[]>([]);
  const [cursor, setCursor] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(false);
  const [loadingMore, setLoadingMore] = useState(false);

  const load = async (cursorParam: string | null, append: boolean) => {
    if (append) setLoadingMore(true);
    else {
      setLoading(true);
      setError(false);
    }
    try {
      const params = new URLSearchParams({ limit: "20" });
      if (cursorParam) params.set("cursor", cursorParam);
      const body = await getJson(`/api/leads/mine?${params.toString()}`);
      const newItems = (body.items as MyInquiry[] | undefined) ?? [];
      setItems((prev) => (append ? [...prev, ...newItems] : newItems));
      setCursor((body.next_cursor as string | null | undefined) ?? null);
    } catch {
      if (!append) setError(true);
    } finally {
      if (append) setLoadingMore(false);
      else setLoading(false);
    }
  };

  useEffect(() => {
    void load(null, false);
  }, []);

  if (loading) {
    return (
      <div className="mt-4 space-y-3">
        <Skeleton width="100%" height="120px" />
        <Skeleton width="100%" height="120px" />
      </div>
    );
  }

  if (error) {
    return (
      <div className="mt-4">
        <AlertNotice>Could not load your inquiries — please try again.</AlertNotice>
      </div>
    );
  }

  if (items.length === 0) {
    return <EmptyState className="mt-4" icon="📭" title="No inquiries yet." />;
  }

  return (
    <div className="mt-4 space-y-3">
      {items.map((inquiry) => (
        <Card key={inquiry.id} className="space-y-2 p-4">
          <div className="flex items-center justify-between gap-2">
            <span className="text-[13px] font-extrabold text-ink">
              {inquiry.type === "contact" ? "Message" : "Milk subscription"}
            </span>
            <StatusChip status={inquiry.status} />
          </div>
          {renderPayload(inquiry)}
          {inquiry.responses.length > 0 ? (
            <div className="space-y-2 border-t border-line pt-2">
              {inquiry.responses.map((response) => (
                <p key={response.id} className="text-[13px] text-ink">
                  {response.body}
                </p>
              ))}
            </div>
          ) : null}
        </Card>
      ))}
      {cursor ? (
        <Button
          type="button"
          variant="ghost"
          disabled={loadingMore}
          onClick={() => void load(cursor, true)}
        >
          {loadingMore ? "Loading..." : "Load more"}
        </Button>
      ) : null}
    </div>
  );
}
