"use client";

/**
 * Directory browse (U3). Lists every business (any status) with the D24 brand
 * type, over `GET /admin/directory/businesses` (paginate on directory.businesses
 * — the public covers() path is active-only, an enforcement console must see
 * suspended/disabled too). Row-open → detail drawer with the enforcement
 * actions this pass already owns: suspend / disable / reinstate, each capturing
 * its reason inside the confirm (audit rule 3) and writing an audit row in the
 * same transaction. Nothing new is invented here — the confirm posts to the
 * existing D16/M1.5 enforcement routes.
 */
import {
  AdminDataTable,
  Button,
  ConfirmDialog,
  ConsolePageHeader,
  DetailDrawer,
  StateChip,
  cn,
  consoleControlClass,
  useToast,
  type AdminColumn,
  type ConsoleStateTone,
} from "@agri/ui";
import { useState } from "react";

import { ApiError, postJson } from "@/lib/api";
import { useAdminList } from "@/lib/use-admin-list";

interface Business {
  id: string;
  name: string;
  slug: string;
  type: string;
  status: "active" | "suspended" | "disabled";
  verification_status: string;
  subscription_tier: string;
  primary_pincode: string;
  enforcement_reason: string | null;
}

const STATUS_TONE: Record<Business["status"], ConsoleStateTone> = {
  active: "ok",
  suspended: "alert",
  disabled: "alert",
};

const columns: readonly AdminColumn<Business>[] = [
  { key: "name", header: "Business", cell: (r) => r.name },
  { key: "type", header: "Type", cell: (r) => r.type, hideBelow: "lg" },
  { key: "pincode", header: "Pincode", cell: (r) => r.primary_pincode },
  { key: "status", header: "Status", cell: (r) => <StateChip tone={STATUS_TONE[r.status]}>{r.status}</StateChip> },
  { key: "verification", header: "Verification", cell: (r) => r.verification_status, hideBelow: "md" },
  { key: "tier", header: "Tier", cell: (r) => r.subscription_tier, hideBelow: "xl" },
];

const STATUSES = ["all", "active", "suspended", "disabled"] as const;
const TYPES = ["all", "vendor", "shop", "lab", "farm"] as const;

export function DirectoryBrowse() {
  const { toast } = useToast();
  const [status, setStatus] = useState<(typeof STATUSES)[number]>("all");
  const [type, setType] = useState<(typeof TYPES)[number]>("all");
  const [open, setOpen] = useState<Business | null>(null);

  const params = new URLSearchParams();
  if (status !== "all") params.set("status", status);
  if (type !== "all") params.set("type", type);
  const qs = params.toString();
  const { items, cursor, loading, loadingMore, error, reload } = useAdminList<Business>(
    `/directory/businesses${qs ? `?${qs}` : ""}`,
  );

  const enforce = async (
    business: Business,
    action: "suspend" | "disable" | "reinstate",
    reason: string,
  ) => {
    try {
      const payload = action === "reinstate" ? { note: reason } : { reason };
      await postJson(`/directory/businesses/${business.id}/${action}`, payload);
      toast({ title: `${business.name}: ${action}d` });
      setOpen(null);
      await reload();
    } catch (e) {
      toast({ title: e instanceof ApiError ? e.detail : "action_failed" });
      throw e; // keep the confirm dialog open so the reason isn't lost
    }
  };

  return (
    <main>
      <ConsolePageHeader title="Directory" sub="Browse & enforce all listings" />
      <AdminDataTable
        caption="Directory businesses"
        columns={columns}
        rows={items}
        rowKey={(r) => r.id}
        loading={loading}
        loadingMore={loadingMore}
        {...(error ? { error: `Could not load the directory (${error}).` } : {})}
        empty={{ icon: "🏪", title: "No businesses match.", description: "Clear the filters to see every listing." }}
        nextCursor={cursor}
        onLoadMore={() => cursor && void reload(cursor)}
        onRowOpen={(b) => setOpen(b)}
        rowOpenLabel={(b) => `Open ${b.name}`}
        toolbar={
          <div className="flex flex-wrap items-center gap-2">
            <label className="flex items-center gap-1.5 text-[13px] text-sub">
              Status
              <select
                aria-label="Filter by status"
                value={status}
                onChange={(e) => setStatus(e.target.value as (typeof STATUSES)[number])}
                className={cn(consoleControlClass, "mt-0 w-auto")}
              >
                {STATUSES.map((s) => (
                  <option key={s} value={s}>
                    {s === "all" ? "All statuses" : s}
                  </option>
                ))}
              </select>
            </label>
            <label className="flex items-center gap-1.5 text-[13px] text-sub">
              Type
              <select
                aria-label="Filter by type"
                value={type}
                onChange={(e) => setType(e.target.value as (typeof TYPES)[number])}
                className={cn(consoleControlClass, "mt-0 w-auto")}
              >
                {TYPES.map((t) => (
                  <option key={t} value={t}>
                    {t === "all" ? "All types" : t}
                  </option>
                ))}
              </select>
            </label>
          </div>
        }
      />

      <DetailDrawer
        open={open !== null}
        onOpenChange={(next) => {
          if (!next) setOpen(null);
        }}
        title={open?.name ?? ""}
        description={open ? `${open.type} · ${open.primary_pincode}` : undefined}
      >
        {open ? (
          <div className="flex flex-col gap-4 text-[13px] text-ink">
            <dl className="grid grid-cols-[auto,1fr] gap-x-4 gap-y-1.5">
              <dt className="text-sub">Status</dt>
              <dd>
                <StateChip tone={STATUS_TONE[open.status]}>{open.status}</StateChip>
              </dd>
              <dt className="text-sub">Verification</dt>
              <dd>{open.verification_status}</dd>
              <dt className="text-sub">Tier</dt>
              <dd>{open.subscription_tier}</dd>
              <dt className="text-sub">Slug</dt>
              <dd className="break-all">{open.slug}</dd>
              {open.enforcement_reason ? (
                <>
                  <dt className="text-sub">Enforcement reason</dt>
                  <dd>{open.enforcement_reason}</dd>
                </>
              ) : null}
            </dl>

            <div className="flex flex-wrap gap-2 border-t border-line pt-3">
              {open.status === "active" ? (
                <>
                  <ConfirmDialog
                    trigger={<Button variant="ghost" className="flex-none px-4">Suspend</Button>}
                    title={`Suspend ${open.name}?`}
                    description="Hidden from consumer results immediately; the profile 410s. The owner keeps console access and sees the reason. Reinstating restores it."
                    confirmLabel="Suspend"
                    cancelLabel="Keep it live"
                    reasonHint="Recorded in the audit log with your name."
                    onConfirm={(reason) => enforce(open, "suspend", reason)}
                  />
                  <ConfirmDialog
                    trigger={<Button variant="ghost" className="flex-none px-4">Disable</Button>}
                    title={`Disable ${open.name}?`}
                    description="Hard-off: owner console locked, all serving stops, active ad campaigns auto-pause. Reinstating restores the prior state."
                    confirmLabel="Disable"
                    cancelLabel="Cancel"
                    reasonHint="Recorded in the audit log with your name."
                    onConfirm={(reason) => enforce(open, "disable", reason)}
                  />
                </>
              ) : null}
              {open.status === "suspended" ? (
                <>
                  <ConfirmDialog
                    trigger={<Button variant="ghost" className="flex-none px-4">Reinstate</Button>}
                    title={`Reinstate ${open.name}?`}
                    description="Restores the listing to consumer results."
                    confirmLabel="Reinstate"
                    cancelLabel="Cancel"
                    reasonLabel="Note"
                    reasonHint="Recorded in the audit log with your name."
                    onConfirm={(note) => enforce(open, "reinstate", note)}
                  />
                  <ConfirmDialog
                    trigger={<Button variant="ghost" className="flex-none px-4">Disable</Button>}
                    title={`Disable ${open.name}?`}
                    description="Hard-off: owner console locked, all serving stops, active ad campaigns auto-pause."
                    confirmLabel="Disable"
                    cancelLabel="Cancel"
                    reasonHint="Recorded in the audit log with your name."
                    onConfirm={(reason) => enforce(open, "disable", reason)}
                  />
                </>
              ) : null}
              {open.status === "disabled" ? (
                <ConfirmDialog
                  trigger={<Button variant="ghost" className="flex-none px-4">Reinstate</Button>}
                  title={`Reinstate ${open.name}?`}
                  description="Restores the prior state (a disabled-over-suspended listing returns to suspended first)."
                  confirmLabel="Reinstate"
                  cancelLabel="Cancel"
                  reasonLabel="Note"
                  reasonHint="Recorded in the audit log with your name."
                  onConfirm={(note) => enforce(open, "reinstate", note)}
                />
              ) : null}
            </div>
          </div>
        ) : null}
      </DetailDrawer>
    </main>
  );
}
