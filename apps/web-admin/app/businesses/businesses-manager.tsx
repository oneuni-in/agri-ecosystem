"use client";

/**
 * M1.5.B business enforcement console — lookup by slug, then suspend / disable
 * / reinstate. Re-platformed (U3 Group C) onto the shared reason-capturing
 * ConfirmDialog: the justification is typed INSIDE the confirm and the confirm
 * stays disabled until it is (audit rule 3 — the log cannot fill with blanks),
 * matching the directory-browse enforcement exactly. suspend/disable land a
 * `reason`, reinstate a `note`; both go to the append-only audit log and the
 * owner sees the reason. The enforcement log below reads straight from that
 * trail, on the shared table primitive.
 */

import {
  AdminDataTable,
  Button,
  ConfirmDialog,
  ConsoleNotice,
  ConsolePageHeader,
  ConsolePanel,
  StateChip,
  cn,
  consoleControlClass,
  useToast,
  type AdminColumn,
  type ConsoleStateTone,
} from "@agri/ui";
import { useTranslations } from "next-intl";
import { useState } from "react";

import { ApiError, getJson, postJson } from "@/lib/api";
import { useAdminList } from "@/lib/use-admin-list";

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

const STATUS_TONE: Record<AdminBusiness["status"], ConsoleStateTone> = {
  active: "ok",
  suspended: "alert",
  disabled: "alert",
};

function metaText(entry: LogEntry): string {
  const meta = entry.metadata ?? {};
  const parts: string[] = [];
  for (const key of ["reason", "note", "prior_status", "restored_status"]) {
    const value = meta[key];
    if (typeof value === "string" && value) parts.push(`${key}: ${value}`);
  }
  const paused = meta.campaigns_paused;
  if (Array.isArray(paused) && paused.length > 0) parts.push(`campaigns paused: ${paused.length}`);
  return parts.join(" · ") || "—";
}

function LogTable({ businessId }: { businessId: string }) {
  const t = useTranslations("ui.admin.businesses");
  const { items, cursor, loading, loadingMore, error, reload } = useAdminList<LogEntry>(
    `/directory/businesses/${businessId}/enforcement-log`,
  );
  const columns: readonly AdminColumn<LogEntry>[] = [
    { key: "action", header: "Action", cell: (e) => e.action.replace("directory.business_", "") },
    { key: "when", header: "When", cell: (e) => new Date(e.created_at).toLocaleString("en-IN", { day: "2-digit", month: "short", hour: "2-digit", minute: "2-digit" }) },
    { key: "actor", header: "Actor", cell: (e) => (e.actor_user_id ? `${e.actor_user_id.slice(0, 8)}…` : "—"), hideBelow: "md" },
    { key: "detail", header: "Detail", cell: (e) => metaText(e), hideBelow: "lg" },
  ];
  return (
    <AdminDataTable
      caption={t("logTitle")}
      columns={columns}
      rows={items}
      rowKey={(e) => e.id}
      loading={loading}
      loadingMore={loadingMore}
      {...(error ? { error: t("error") } : {})}
      empty={{ icon: "📜", title: t("logEmpty") }}
      nextCursor={cursor}
      onLoadMore={() => cursor && void reload(cursor)}
    />
  );
}

export function BusinessesManager() {
  const t = useTranslations("ui.admin.businesses");
  const { toast } = useToast();
  const [slug, setSlug] = useState("");
  const [loading, setLoading] = useState(false);
  const [notFound, setNotFound] = useState(false);
  const [business, setBusiness] = useState<AdminBusiness | null>(null);

  const lookup = async (slugOverride?: string) => {
    const target = (slugOverride ?? slug).trim();
    if (!target) return;
    setLoading(true);
    setNotFound(false);
    try {
      const body = await getJson(`/directory/businesses/${encodeURIComponent(target)}`);
      setBusiness(body as unknown as AdminBusiness);
    } catch (error) {
      setBusiness(null);
      if (error instanceof ApiError && error.status === 404) setNotFound(true);
      else toast({ title: error instanceof ApiError ? error.detail : t("error") });
    } finally {
      setLoading(false);
    }
  };

  const enforce = async (action: "suspend" | "disable" | "reinstate", reason: string) => {
    if (!business) return;
    try {
      const payload = action === "reinstate" ? { note: reason } : { reason };
      await postJson(`/directory/businesses/${business.id}/${action}`, payload);
      toast({ title: t(`${action}Done`) });
      await lookup(business.slug);
    } catch (error) {
      toast({ title: error instanceof ApiError ? error.detail : t("error") });
      throw error; // keep the confirm open so the typed reason isn't lost
    }
  };

  return (
    <main className="space-y-4">
      <ConsolePageHeader title={t("title")} sub={t("hint")} />
      <form
        className="flex max-w-lg gap-2"
        onSubmit={(event) => {
          event.preventDefault();
          void lookup();
        }}
      >
        <input
          className={cn(consoleControlClass, "mt-0 flex-1")}
          aria-label={t("searchLabel")}
          placeholder={t("searchPlaceholder")}
          value={slug}
          onChange={(event) => setSlug(event.target.value)}
        />
        <Button type="submit" variant="brand" className="flex-none px-5">
          {t("search")}
        </Button>
      </form>

      {notFound ? <ConsoleNotice tone="alert">{t("empty")}</ConsoleNotice> : null}

      {business && !loading ? (
        <>
          <ConsolePanel>
            <div className="flex flex-wrap items-start justify-between gap-2">
              <div className="min-w-0">
                <p className="font-display text-[16px] font-extrabold text-ink">{business.name}</p>
                <p className="text-[13px] text-sub">
                  /{business.slug} · {business.type} · {business.primary_pincode} ·{" "}
                  {business.verification_status} · {business.subscription_tier}
                </p>
              </div>
              <StateChip tone={STATUS_TONE[business.status]}>{t(`status.${business.status}`)}</StateChip>
            </div>
            {business.enforcement_reason ? (
              <p className="mt-2 text-[13px] text-ink">
                {t("reasonShown")}: {business.enforcement_reason}
              </p>
            ) : null}
            <div className="mt-3 flex flex-wrap gap-2 border-t border-line pt-3">
              {business.status !== "suspended" && business.status !== "disabled" ? (
                <ConfirmDialog
                  trigger={<Button variant="ghost" className="flex-none px-4">{t("suspend")}</Button>}
                  title={t("confirm_suspend", { name: business.name })}
                  description={t("confirm_suspend_body")}
                  confirmLabel={t("suspend")}
                  cancelLabel={t("cancel")}
                  reasonLabel={t("reasonLabel")}
                  reasonHint={t("reasonShown")}
                  onConfirm={(reason) => enforce("suspend", reason)}
                />
              ) : null}
              {business.status !== "disabled" ? (
                <ConfirmDialog
                  trigger={<Button variant="ghost" className="flex-none px-4">{t("disable")}</Button>}
                  title={t("confirm_disable", { name: business.name })}
                  description={t("confirm_disable_body")}
                  confirmLabel={t("disable")}
                  cancelLabel={t("cancel")}
                  reasonLabel={t("reasonLabel")}
                  reasonHint={t("reasonShown")}
                  onConfirm={(reason) => enforce("disable", reason)}
                />
              ) : null}
              {business.status !== "active" ? (
                <ConfirmDialog
                  trigger={<Button variant="ghost" className="flex-none px-4">{t("reinstate")}</Button>}
                  title={t("confirm_reinstate", { name: business.name })}
                  description={t("confirm_reinstate_body")}
                  confirmLabel={t("reinstate")}
                  cancelLabel={t("cancel")}
                  reasonLabel={t("noteLabel")}
                  onConfirm={(note) => enforce("reinstate", note)}
                />
              ) : null}
            </div>
          </ConsolePanel>

          <ConsolePanel title={t("logTitle")}>
            <LogTable businessId={business.id} />
          </ConsolePanel>
        </>
      ) : null}
    </main>
  );
}
