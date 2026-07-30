"use client";

/**
 * M1.5.B business enforcement console. Lookup by slug, then suspend /
 * disable / reinstate with a Modal confirm (users-manager.tsx precedent).
 * Suspend/disable REQUIRE a reason (it lands in the append-only audit log
 * and is shown to the owner); reinstate takes an optional note. The
 * enforcement log below the card reads straight from the audit trail.
 */

import { Button, Card, Modal, Skeleton, cn, useToast } from "@agri/ui";
import { useTranslations } from "next-intl";
import { useState } from "react";

import { ApiError, getJson, postJson } from "@/lib/api";

interface AdminBusiness {
  id: string;
  name: string;
  slug: string;
  type: string;
  status: "active" | "suspended" | "disabled";
  verification_status: string;
  subscription_tier: string;
  claimable: boolean;
  primary_pincode: string;
  created_at: string;
  enforcement_reason: string | null;
  enforcement_prior_status: string | null;
}

interface LogEntry {
  id: string;
  action: string;
  actor_user_id: string | null;
  created_at: string;
  metadata: Record<string, unknown> | null;
}

type Action = "suspend" | "disable" | "reinstate";

const FIELD =
  "mt-1 block min-h-[44px] w-full rounded-btn border border-line bg-card px-3 py-2 text-[13px] text-ink";

function StatusPill({ label }: { label: string }) {
  return (
    <span className="inline-flex items-center self-start rounded-pill border border-line bg-ghost px-[9px] py-[3px] text-[11px] font-extrabold text-ink">
      {label}
    </span>
  );
}

function metaText(entry: LogEntry): string {
  const meta = entry.metadata ?? {};
  const parts: string[] = [];
  for (const key of ["reason", "note", "prior_status", "restored_status"]) {
    const value = meta[key];
    if (typeof value === "string" && value) parts.push(`${key}: ${value}`);
  }
  const paused = meta.campaigns_paused;
  if (Array.isArray(paused) && paused.length > 0) {
    parts.push(`campaigns paused: ${paused.length}`);
  }
  return parts.join(" · ");
}

function ActionModal({
  action,
  business,
  onDone,
}: {
  action: Action;
  business: AdminBusiness;
  onDone: () => void;
}) {
  const t = useTranslations("ui.admin.businesses");
  const { toast } = useToast();
  const [reason, setReason] = useState("");
  const [busy, setBusy] = useState(false);
  const needsReason = action !== "reinstate";

  const run = async () => {
    if (needsReason && !reason.trim()) {
      toast({ title: t("reasonRequired") });
      return;
    }
    setBusy(true);
    try {
      await postJson(
        `/directory/businesses/${business.id}/${action}`,
        needsReason ? { reason: reason.trim() } : reason.trim() ? { note: reason.trim() } : {},
      );
      toast({ title: t(`${action}Done`) });
      onDone();
    } catch (error) {
      toast({ title: error instanceof ApiError ? error.detail : t("error") });
    } finally {
      setBusy(false);
    }
  };

  return (
    <Modal
      key={action}
      trigger={<Button variant={action === "reinstate" ? "ghost" : "brand"}>{t(action)}</Button>}
      title={t(`confirm_${action}`, { name: business.name })}
      description={t(`confirm_${action}_body`)}
      closeLabel={t("cancel")}
    >
      <div className="space-y-3">
        <label className="block text-[13px] font-semibold text-ink">
          {needsReason ? t("reasonLabel") : t("noteLabel")}
          <textarea
            className={cn(FIELD, "min-h-[80px]")}
            maxLength={500}
            value={reason}
            onChange={(event) => setReason(event.target.value)}
          />
        </label>
        <Button variant="brand" disabled={busy} onClick={() => void run()}>
          {busy ? t("working") : t(action)}
        </Button>
      </div>
    </Modal>
  );
}

export function BusinessesManager() {
  const t = useTranslations("ui.admin.businesses");
  const { toast } = useToast();
  const [slug, setSlug] = useState("");
  const [loading, setLoading] = useState(false);
  const [notFound, setNotFound] = useState(false);
  const [business, setBusiness] = useState<AdminBusiness | null>(null);
  const [log, setLog] = useState<LogEntry[]>([]);
  const [logCursor, setLogCursor] = useState<string | null>(null);

  const loadLog = async (businessId: string, cursor?: string) => {
    try {
      const params = new URLSearchParams();
      if (cursor) params.set("cursor", cursor);
      const body = await getJson(
        `/directory/businesses/${businessId}/enforcement-log?${params}`,
      );
      const page = (body.items ?? []) as LogEntry[];
      setLog((prev) => (cursor ? [...prev, ...page] : page));
      setLogCursor((body.next_cursor ?? null) as string | null);
    } catch {
      setLog([]);
      setLogCursor(null);
    }
  };

  const lookup = async (slugOverride?: string) => {
    const target = (slugOverride ?? slug).trim();
    if (!target) return;
    setLoading(true);
    setNotFound(false);
    try {
      const body = await getJson(`/directory/businesses/${encodeURIComponent(target)}`);
      const found = body as unknown as AdminBusiness;
      setBusiness(found);
      await loadLog(found.id);
    } catch (error) {
      setBusiness(null);
      setLog([]);
      if (error instanceof ApiError && error.status === 404) setNotFound(true);
      else toast({ title: error instanceof ApiError ? error.detail : t("error") });
    } finally {
      setLoading(false);
    }
  };

  const refresh = () => {
    if (business) void lookup(business.slug);
  };

  return (
    <main className="mx-auto max-w-3xl space-y-4 p-4">
      <h1 className="text-xl font-bold text-ink">{t("title")}</h1>
      <p className="text-sm text-sub">{t("hint")}</p>
      <form
        className="flex gap-2"
        onSubmit={(event) => {
          event.preventDefault();
          void lookup();
        }}
      >
        <input
          className="min-h-[44px] min-w-0 flex-1 rounded-btn border border-line bg-card px-3 py-2 text-ink"
          aria-label={t("searchLabel")}
          placeholder={t("searchPlaceholder")}
          value={slug}
          onChange={(event) => setSlug(event.target.value)}
        />
        <Button type="submit" variant="brand">
          {t("search")}
        </Button>
      </form>

      {loading ? <Skeleton width="100%" height="120px" /> : null}
      {notFound ? <p className="text-sm text-sub">{t("empty")}</p> : null}

      {business && !loading ? (
        <Card className="space-y-3 p-4">
          <div className="flex items-center justify-between gap-2">
            <div>
              <p className="font-semibold text-ink">{business.name}</p>
              <p className="text-sm text-sub">
                /{business.slug} · {business.type} · {business.primary_pincode} ·{" "}
                {business.verification_status} · {business.subscription_tier}
              </p>
            </div>
            <StatusPill label={t(`status.${business.status}`)} />
          </div>
          {business.enforcement_reason ? (
            <p className="text-sm text-ink">
              {t("reasonShown")}: {business.enforcement_reason}
            </p>
          ) : null}
          <div className="flex flex-wrap gap-2">
            {business.status !== "suspended" && business.status !== "disabled" ? (
              <ActionModal action="suspend" business={business} onDone={refresh} />
            ) : null}
            {business.status !== "disabled" ? (
              <ActionModal action="disable" business={business} onDone={refresh} />
            ) : null}
            {business.status !== "active" ? (
              <ActionModal action="reinstate" business={business} onDone={refresh} />
            ) : null}
          </div>

          <div>
            <p className="text-sm font-semibold text-ink">{t("logTitle")}</p>
            {log.length === 0 ? (
              <p className="text-sm text-sub">{t("logEmpty")}</p>
            ) : (
              <ul className="mt-1 space-y-1">
                {log.map((entry) => (
                  <li key={entry.id} className="rounded-card border border-line p-2">
                    <p className="text-sm font-semibold text-ink">
                      {entry.action.replace("directory.business_", "")} ·{" "}
                      {new Date(entry.created_at).toLocaleString()}
                    </p>
                    <p className="text-xs text-sub">
                      {t("byActor", { actor: entry.actor_user_id ?? "—" })}
                      {metaText(entry) ? ` · ${metaText(entry)}` : ""}
                    </p>
                  </li>
                ))}
              </ul>
            )}
            {logCursor && business ? (
              <Button
                variant="ghost"
                className="mt-2"
                onClick={() => void loadLog(business.id, logCursor)}
              >
                {t("loadMore")}
              </Button>
            ) : null}
          </div>
        </Card>
      ) : null}
    </main>
  );
}
