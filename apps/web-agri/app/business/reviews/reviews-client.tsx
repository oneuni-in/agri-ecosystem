"use client";

/**
 * U2 Group C: the owner reviews surface. Lists approved reviews about the
 * selected business (D18 public reads stay approved-only) and lets the owner
 * post ONE reply per review. A reply lands `pending` and is invisible
 * publicly until a moderator approves it — the owner sees their own pending
 * reply here with its status. Built on the shared console catalog, localized
 * via ui.console.reviews.*; the reply itself is Translated (en/ta/hi).
 *
 * Also carries the verification/trust status panel for the selected business.
 */

import {
  Button,
  ConfirmAction,
  ConsoleField,
  ConsoleNotice,
  ConsolePanel,
  RatingStars,
  Skeleton,
  StateChip,
  consoleControlClass,
} from "@agri/ui";
import { useLocale, useTranslations } from "next-intl";
import { useEffect, useState } from "react";

import { ApiError, deleteJson, getJson, postJson } from "@/lib/api";

interface BusinessOut {
  id: string;
  name: string;
  status: string;
  verification_status: string;
  enforcement_reason: string | null;
}

interface ReplyOut {
  id: string;
  review_id: string;
  body: Record<string, string>;
  moderation_status: string;
}

interface ReviewOut {
  id: string;
  rating: number;
  body: Record<string, string> | null;
  created_at: string;
  reply: ReplyOut | null;
}

export function ReviewsClient() {
  const t = useTranslations("ui.console.reviews");
  const tTrust = useTranslations("ui.console.trust");
  const locale = useLocale();

  const [businesses, setBusinesses] = useState<BusinessOut[] | null>(null);
  const [businessesError, setBusinessesError] = useState(false);
  const [selectedId, setSelectedId] = useState<string | null>(null);

  const [reviews, setReviews] = useState<ReviewOut[] | null>(null);
  const [cursor, setCursor] = useState<string | null>(null);
  const [loadingMore, setLoadingMore] = useState(false);

  // per-review draft (en/ta/hi) + submit state
  const [drafts, setDrafts] = useState<Record<string, { en: string; ta: string; hi: string }>>({});
  const [submitting, setSubmitting] = useState<Record<string, boolean>>({});
  const [notice, setNotice] = useState<Record<string, { kind: "ok" | "error"; text: string } | null>>({});

  const selected = businesses?.find((b) => b.id === selectedId) ?? null;

  const localized = (body: Record<string, string> | null): string =>
    body ? (body[locale] ?? body.en ?? Object.values(body)[0] ?? "") : "";

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

  const loadReviews = async (businessId: string, cursorParam: string | null, append: boolean) => {
    if (!append) setReviews(null);
    else setLoadingMore(true);
    try {
      const params = new URLSearchParams({ business_id: businessId, limit: "20" });
      if (cursorParam) params.set("cursor", cursorParam);
      const body = await getJson(`/api/reviews/owner?${params.toString()}`);
      const items = (body.items as ReviewOut[] | undefined) ?? [];
      setReviews((prev) => (append && prev ? [...prev, ...items] : items));
      setCursor((body.next_cursor as string | null | undefined) ?? null);
    } catch {
      if (!append) setReviews([]);
    } finally {
      if (append) setLoadingMore(false);
    }
  };

  useEffect(() => {
    if (!selectedId) return;
    setCursor(null);
    void loadReviews(selectedId, null, false);
  }, [selectedId]);

  const setDraft = (reviewId: string, patch: Partial<{ en: string; ta: string; hi: string }>) =>
    setDrafts((d) => ({
      ...d,
      [reviewId]: { en: "", ta: "", hi: "", ...d[reviewId], ...patch },
    }));

  const postReply = async (reviewId: string) => {
    const draft = drafts[reviewId] ?? { en: "", ta: "", hi: "" };
    const body: Record<string, string> = {};
    for (const key of ["en", "ta", "hi"] as const) {
      const value = draft[key].trim();
      if (value) body[key] = value;
    }
    if (Object.keys(body).length === 0) return;
    setSubmitting((s) => ({ ...s, [reviewId]: true }));
    setNotice((n) => ({ ...n, [reviewId]: null }));
    try {
      await postJson(`/api/reviews/${reviewId}/reply`, { body });
      setNotice((n) => ({ ...n, [reviewId]: { kind: "ok", text: t("postedOk") } }));
      setDrafts((d) => ({ ...d, [reviewId]: { en: "", ta: "", hi: "" } }));
      if (selectedId) void loadReviews(selectedId, null, false);
    } catch (err) {
      const text =
        err instanceof ApiError && err.status === 409 && err.detail === "review_not_approved"
          ? t("reply409NotApproved")
          : err instanceof ApiError && err.status === 409 && err.detail === "reply_exists"
            ? t("reply409Exists")
            : t("replyFailed");
      setNotice((n) => ({ ...n, [reviewId]: { kind: "error", text } }));
    } finally {
      setSubmitting((s) => ({ ...s, [reviewId]: false }));
    }
  };

  const deleteReply = async (replyId: string, reviewId: string) => {
    try {
      await deleteJson(`/api/reviews/replies/${replyId}`);
    } catch {
      setNotice((n) => ({ ...n, [reviewId]: { kind: "error", text: t("deleteFailed") } }));
      throw new Error("delete_failed");
    }
    setNotice((n) => ({ ...n, [reviewId]: { kind: "ok", text: t("deletedOk") } }));
    if (selectedId) void loadReviews(selectedId, null, false);
  };

  const replyStatusChip = (status: string) => {
    if (status === "approved")
      return <StateChip tone="ok">{t("replyStatusApproved")}</StateChip>;
    if (status === "rejected")
      return <StateChip tone="alert">{t("replyStatusRejected")}</StateChip>;
    return <StateChip tone="pending">{t("replyStatusPending")}</StateChip>;
  };

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
        <Skeleton width="100%" height="160px" />
      </div>
    );
  }

  return (
    <div className="mt-4 space-y-4">
      <ConsoleField id="reviews-business" label={t("businessPicker")}>
        <select
          id="reviews-business"
          className={consoleControlClass}
          value={selectedId ?? ""}
          onChange={(e) => setSelectedId(e.target.value)}
        >
          {businesses.map((b) => (
            <option key={b.id} value={b.id}>
              {b.name}
            </option>
          ))}
        </select>
      </ConsoleField>

      {/* Verification & trust status */}
      {selected ? (
        <ConsolePanel title={tTrust("title")}>
          <div className="flex flex-wrap items-center gap-2">
            {selected.verification_status === "verified" ? (
              <StateChip tone="ok">{tTrust("verified")}</StateChip>
            ) : selected.verification_status === "pending" ? (
              <StateChip tone="pending">{tTrust("pending")}</StateChip>
            ) : (
              <StateChip tone="neutral">{tTrust("unverified")}</StateChip>
            )}
          </div>
          <p className="mt-2 text-[12px] text-sub">
            {selected.status === "suspended"
              ? tTrust("suspendedBody")
              : selected.status === "disabled"
                ? tTrust("disabledBody")
                : selected.verification_status === "verified"
                  ? tTrust("verifiedBody")
                  : tTrust("unverifiedBody")}
          </p>
        </ConsolePanel>
      ) : null}

      {reviews === null ? (
        <Skeleton width="100%" height="160px" />
      ) : reviews.length === 0 ? (
        <ConsolePanel>
          <div className="py-4 text-center">
            <p className="text-[14px] font-semibold text-ink">{t("empty")}</p>
            <p className="mt-1 text-[12px] text-sub">{t("emptyHint")}</p>
          </div>
        </ConsolePanel>
      ) : (
        <div className="space-y-3">
          {reviews.map((review) => (
            <ConsolePanel key={review.id}>
              <div className="mb-1 flex items-center gap-2">
                <RatingStars value={String(review.rating)} />
                <span className="text-[11px] font-semibold uppercase tracking-wide text-sub">
                  {t("reviewBy")}
                </span>
              </div>
              {review.body ? (
                <p className="text-[13px] leading-relaxed text-ink">{localized(review.body)}</p>
              ) : null}

              {review.reply ? (
                <div className="mt-3 rounded-card border border-cream-line bg-cream p-3">
                  <div className="mb-1 flex items-center justify-between gap-2">
                    <span className="text-[11px] font-bold uppercase tracking-wide text-sub">
                      {t("yourReply")}
                    </span>
                    {replyStatusChip(review.reply.moderation_status)}
                  </div>
                  <p className="text-[13px] text-ink">{localized(review.reply.body)}</p>
                  {review.reply.moderation_status === "pending" ? (
                    <p className="mt-1 text-[11px] text-muted">{t("pendingNote")}</p>
                  ) : null}
                  <div className="mt-2 flex max-w-[220px]">
                    <ConfirmAction
                      trigger={
                        <Button type="button" variant="ghost">
                          {t("deleteReply")}
                        </Button>
                      }
                      title={t("deleteConfirmTitle")}
                      description={t("deleteConfirmBody")}
                      confirmLabel={t("deleteReply")}
                      cancelLabel={t("deleteCancel")}
                      onConfirm={() => deleteReply(review.reply!.id, review.id)}
                    />
                  </div>
                </div>
              ) : (
                <div className="mt-3 space-y-2">
                  <p className="text-[12px] font-semibold text-ink">{t("addReply")}</p>
                  {(["en", "ta", "hi"] as const).map((code) => (
                    <ConsoleField
                      key={code}
                      id={`reply-${review.id}-${code}`}
                      label={t(code === "en" ? "replyEn" : code === "ta" ? "replyTa" : "replyHi")}
                    >
                      <textarea
                        id={`reply-${review.id}-${code}`}
                        lang={code}
                        maxLength={2000}
                        rows={2}
                        className={`${consoleControlClass} min-h-[52px]`}
                        value={drafts[review.id]?.[code] ?? ""}
                        onChange={(e) => setDraft(review.id, { [code]: e.target.value })}
                      />
                    </ConsoleField>
                  ))}
                  <p className="text-[11px] text-muted">{t("replyHint")}</p>
                  <Button
                    type="button"
                    variant="brand"
                    disabled={!!submitting[review.id]}
                    onClick={() => void postReply(review.id)}
                  >
                    {submitting[review.id] ? t("posting") : t("postReply")}
                  </Button>
                </div>
              )}

              {notice[review.id] ? (
                <div className="mt-2">
                  <ConsoleNotice tone={notice[review.id]!.kind === "ok" ? "ok" : "alert"}>
                    {notice[review.id]!.text}
                  </ConsoleNotice>
                </div>
              ) : null}
            </ConsolePanel>
          ))}
          {cursor ? (
            <Button
              type="button"
              variant="ghost"
              disabled={loadingMore}
              onClick={() => selectedId && void loadReviews(selectedId, cursor, true)}
            >
              {t("loadMore")}
            </Button>
          ) : null}
        </div>
      )}
    </div>
  );
}
