"use client";

/**
 * U2 Group C: the lead inbox, rebuilt onto the shared console catalog and
 * localized via ui.console.inbox.*. Milk-subscription NEEDS (D25) and contact
 * messages arrive in the same inbox; a vendor sees ONLY inquiries in their
 * coverage because the D25 fan-out creates child inquiries for covering
 * businesses only, and the list is business_id-scoped through
 * get_owned_business — enforced backend-side, not here. Data flow is D18's.
 */

import Link from "next/link";

import {
  Button,
  ConsoleField,
  ConsoleNotice,
  ConsolePanel,
  EmptyState,
  Skeleton,
  StateChip,
  buttonVariants,
  cn,
  consoleControlClass,
} from "@agri/ui";
import { useTranslations } from "next-intl";
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

const STATUS_TONE = {
  new: "pending",
  responded: "ok",
  closed: "neutral",
} as const;

export function InboxClient() {
  const t = useTranslations("ui.console.inbox");
  const [businesses, setBusinesses] = useState<BusinessOut[] | null>(null);
  const [businessesError, setBusinessesError] = useState(false);
  const [selectedId, setSelectedId] = useState<string | null>(null);
  const [typeFilter, setTypeFilter] = useState<InquiryType | "all">("all");

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

  // Seconds → "Xh" for ≥ 1h, else "Xm" (min 1m so a sub-minute reply never
  // renders "0m").
  const formatAvgResponse = (seconds: number): string =>
    seconds < 3600 ? `${Math.max(1, Math.round(seconds / 60))}m` : `${Math.round(seconds / 3600)}h`;

  const renderPayload = (inquiry: InboxInquiry): ReactNode => {
    if (inquiry.type === "contact") {
      const message = typeof inquiry.payload.message === "string" ? inquiry.payload.message : "";
      return <p className="text-[13px] text-ink">{message}</p>;
    }
    const { qty_liters, milk_type, schedule, delivery_time, note } = inquiry.payload;
    return (
      <div className="space-y-1">
        <p className="text-[13px] text-ink">
          {String(qty_liters ?? "?")} {t("perDay")} · {String(milk_type ?? "?")} ·{" "}
          {String(schedule ?? "?")}
        </p>
        {typeof delivery_time === "string" && delivery_time ? (
          <p className="text-[12px] text-sub">
            {t("preferredDelivery", { time: delivery_time })}
          </p>
        ) : null}
        {typeof note === "string" && note ? (
          <p className="text-[12px] text-sub">&ldquo;{note}&rdquo;</p>
        ) : null}
      </div>
    );
  };

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
      if (typeFilter !== "all") params.set("type", typeFilter);
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
  }, [selectedId, typeFilter]);

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
        [id]: err instanceof ApiError && err.status === 422 ? t("reply422") : t("replyFailed"),
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

  const statusLabel = (status: InquiryStatus): string =>
    status === "new" ? t("statusNew") : status === "responded" ? t("statusReplied") : t("statusClosed");

  if (businessesError) {
    return (
      <div className="mt-4">
        <ConsoleNotice tone="alert">{t("loadFailed")}</ConsoleNotice>
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
        title={t("noBusiness")}
        action={
          <Link
            href="/directory"
            prefetch={false}
            className={cn(buttonVariants({ variant: "brand" }), "no-underline")}
          >
            {t("browseDirectory")}
          </Link>
        }
      />
    );
  }

  return (
    <div className="mt-4 space-y-4">
      <ConsoleField id="inbox-business" label={t("businessPicker")}>
        <select
          id="inbox-business"
          className={consoleControlClass}
          value={selectedId ?? ""}
          onChange={(event) => setSelectedId(event.target.value)}
        >
          {businesses.map((business) => (
            <option key={business.id} value={business.id}>
              {business.name}
            </option>
          ))}
        </select>
      </ConsoleField>

      <ConsoleField id="inbox-filter" label={t("show")}>
        <select
          id="inbox-filter"
          className={consoleControlClass}
          value={typeFilter}
          onChange={(event) => setTypeFilter(event.target.value as InquiryType | "all")}
        >
          <option value="all">{t("showAll")}</option>
          <option value="contact">{t("showMessages")}</option>
          <option value="milk_subscription">{t("showSubscriptions")}</option>
        </select>
      </ConsoleField>

      {stats ? (
        <p className="text-[13px] text-sub">
          {stats.total} {stats.total === 1 ? t("statNounOne") : t("statNounMany")} · {stats.responded}{" "}
          {t("replied")}
          {stats.avg_response_seconds !== null
            ? ` · ${t("avgResponse")}: ${formatAvgResponse(stats.avg_response_seconds)}`
            : ""}
        </p>
      ) : null}

      {stats && stats.avg_response_seconds !== null && stats.avg_response_seconds > 86400 ? (
        <ConsoleNotice tone="alert">
          {t("slowWarning", { time: formatAvgResponse(stats.avg_response_seconds) })}
        </ConsoleNotice>
      ) : null}

      {itemsLoading ? (
        <Skeleton width="100%" height="120px" />
      ) : itemsError ? (
        <ConsoleNotice tone="alert">{t("loadLeadsFailed")}</ConsoleNotice>
      ) : items.length === 0 ? (
        <ConsolePanel>
          <EmptyState icon="📭" title={t("empty")} description={t("emptyHint")} />
        </ConsolePanel>
      ) : (
        <div className="space-y-3">
          {items.map((inquiry) => (
            <ConsolePanel key={inquiry.id}>
              <div className="mb-2 flex items-center justify-between gap-2">
                <span className="text-[13px] font-extrabold text-ink">
                  {inquiry.type === "contact" ? t("kindMessage") : t("kindSubscription")}
                </span>
                <StateChip tone={STATUS_TONE[inquiry.status]}>{statusLabel(inquiry.status)}</StateChip>
              </div>
              {renderPayload(inquiry)}
              <p className="mt-1 text-[12px] text-sub">{t("pincode", { pincode: inquiry.pincode })}</p>
              {inquiry.status !== "closed" ? (
                <div className="mt-2 space-y-2">
                  <ConsoleField id={`reply-${inquiry.id}`} label={t("reply")}>
                    <textarea
                      id={`reply-${inquiry.id}`}
                      maxLength={2000}
                      rows={2}
                      value={replyText[inquiry.id] ?? ""}
                      onChange={(event) =>
                        setReplyText((s) => ({ ...s, [inquiry.id]: event.target.value }))
                      }
                      className={cn(consoleControlClass, "min-h-[60px]")}
                    />
                  </ConsoleField>
                  {replyError[inquiry.id] ? (
                    <ConsoleNotice tone="alert">{replyError[inquiry.id]}</ConsoleNotice>
                  ) : null}
                  <div className="flex gap-2">
                    <Button
                      type="button"
                      variant="brand"
                      disabled={!!replySubmitting[inquiry.id] || !replyText[inquiry.id]?.trim()}
                      onClick={() => void reply(inquiry.id)}
                    >
                      {replySubmitting[inquiry.id] ? t("sending") : t("reply")}
                    </Button>
                    <Button
                      type="button"
                      variant="ghost"
                      disabled={!!closing[inquiry.id]}
                      onClick={() => void close(inquiry.id)}
                    >
                      {closing[inquiry.id] ? t("closing") : t("close")}
                    </Button>
                  </div>
                </div>
              ) : null}
            </ConsolePanel>
          ))}
          {cursor ? (
            <Button
              type="button"
              variant="ghost"
              disabled={loadingMore}
              onClick={() => selectedId && void loadInbox(selectedId, cursor, true)}
            >
              {loadingMore ? t("loading") : t("loadMore")}
            </Button>
          ) : null}
        </div>
      )}
    </div>
  );
}
