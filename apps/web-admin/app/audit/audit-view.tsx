"use client";

/**
 * Audit timeline (U3) — the reader D12's hash-chained log never had. READ-ONLY
 * by construction: the backend exposes only GET /admin/audit (no purge, no
 * edit, no delete — a purgeable audit log is not an audit log), and the app
 * role has INSERT+SELECT only. Filters by actor / action / entity / date;
 * newest first, keyset-paginated. `audit.read` gated.
 */
import {
  AdminDataTable,
  Button,
  ConsolePageHeader,
  cn,
  consoleControlClass,
  type AdminColumn,
} from "@agri/ui";
import { useState } from "react";

import { useAdminList } from "@/lib/use-admin-list";

interface AuditRow {
  id: string;
  created_at: string;
  actor_user_id: string | null;
  action: string;
  target_type: string | null;
  target_id: string | null;
  metadata: Record<string, unknown>;
}

/** The reason/note an operator typed lands in metadata; surface it plainly. */
function why(meta: Record<string, unknown>): string {
  for (const key of ["reason", "note"]) {
    const v = meta[key];
    if (typeof v === "string" && v) return v;
  }
  const keys = Object.keys(meta);
  return keys.length ? keys.map((k) => `${k}: ${String(meta[k])}`).join(" · ") : "—";
}

function shortActor(id: string | null): string {
  return id ? `${id.slice(0, 8)}…` : "system";
}

function fmt(iso: string): string {
  return new Date(iso).toLocaleString("en-IN", {
    day: "2-digit",
    month: "short",
    hour: "2-digit",
    minute: "2-digit",
  });
}

const columns: readonly AdminColumn<AuditRow>[] = [
  { key: "when", header: "When", cell: (r) => fmt(r.created_at) },
  { key: "action", header: "Action", cell: (r) => r.action },
  { key: "actor", header: "Actor", cell: (r) => shortActor(r.actor_user_id), hideBelow: "md" },
  {
    key: "entity",
    header: "Entity",
    cell: (r) => (r.target_type ? `${r.target_type} ${r.target_id ? `${r.target_id.slice(0, 8)}…` : ""}` : "—"),
    hideBelow: "lg",
  },
  { key: "why", header: "Reason / detail", cell: (r) => why(r.metadata), hideBelow: "xl" },
];

export function AuditView() {
  const [actor, setActor] = useState("");
  const [action, setAction] = useState("");
  const [entityType, setEntityType] = useState("");
  const [dateFrom, setDateFrom] = useState("");
  const [dateTo, setDateTo] = useState("");
  // Applied filters (the path). Kept separate from the inputs so typing an
  // actor UUID doesn't fire a request per keystroke.
  const [applied, setApplied] = useState("");

  const { items, cursor, loading, loadingMore, error, reload } = useAdminList<AuditRow>(
    `/audit${applied ? `?${applied}` : ""}`,
  );

  const apply = () => {
    const params = new URLSearchParams();
    if (actor.trim()) params.set("actor", actor.trim());
    if (action.trim()) params.set("action", action.trim());
    if (entityType.trim()) params.set("entity_type", entityType.trim());
    if (dateFrom) params.set("date_from", dateFrom);
    if (dateTo) params.set("date_to", dateTo);
    setApplied(params.toString());
  };

  const clear = () => {
    setActor("");
    setAction("");
    setEntityType("");
    setDateFrom("");
    setDateTo("");
    setApplied("");
  };

  const field = cn(consoleControlClass, "mt-0");

  return (
    <main>
      <ConsolePageHeader
        title="Audit log"
        sub="Append-only, hash-chained · read-only · no purge, edit or delete"
      />
      <AdminDataTable
        caption="Audit timeline"
        columns={columns}
        rows={items}
        rowKey={(r) => r.id}
        loading={loading}
        loadingMore={loadingMore}
        {...(error ? { error: `Could not load the audit log (${error}).` } : {})}
        empty={{ icon: "📜", title: "No matching entries.", description: "Adjust the filters or clear them to see the full timeline." }}
        nextCursor={cursor}
        onLoadMore={() => cursor && void reload(cursor)}
        toolbar={
          <form
            className="flex w-full flex-wrap items-end gap-2"
            onSubmit={(e) => {
              e.preventDefault();
              apply();
            }}
          >
            <label className="text-[12px] text-sub">
              Actor (user id)
              <input aria-label="Filter by actor user id" value={actor} onChange={(e) => setActor(e.target.value)} className={cn(field, "w-[220px] max-w-full")} placeholder="uuid" />
            </label>
            <label className="text-[12px] text-sub">
              Action
              <input aria-label="Filter by action" value={action} onChange={(e) => setAction(e.target.value)} className={cn(field, "w-[200px] max-w-full")} placeholder="directory.business_suspended" />
            </label>
            <label className="text-[12px] text-sub">
              Entity type
              <input aria-label="Filter by entity type" value={entityType} onChange={(e) => setEntityType(e.target.value)} className={cn(field, "w-[140px]")} placeholder="business" />
            </label>
            <label className="text-[12px] text-sub">
              From
              <input type="date" aria-label="From date" value={dateFrom} onChange={(e) => setDateFrom(e.target.value)} className={cn(field, "w-auto")} />
            </label>
            <label className="text-[12px] text-sub">
              To
              <input type="date" aria-label="To date" value={dateTo} onChange={(e) => setDateTo(e.target.value)} className={cn(field, "w-auto")} />
            </label>
            <Button type="submit" variant="brand" className="flex-none px-4">
              Apply
            </Button>
            <Button type="button" variant="ghost" className="flex-none px-4" onClick={clear}>
              Clear
            </Button>
          </form>
        }
      />
    </main>
  );
}
