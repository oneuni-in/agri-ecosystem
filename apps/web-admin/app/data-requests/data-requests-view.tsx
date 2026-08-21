"use client";

/**
 * DPDP data requests (ID-U1 W4) — the A6 queue the erasure flow reports into.
 *
 * Every row here started as a USER's own request. Staff can see the queue and
 * take exactly two decisions: release a hold, or run an already-due erasure
 * now. There is deliberately no "delete this person" control, because a queue
 * that can begin an irreversible action nobody asked for is a bigger risk
 * than the one it exists to manage.
 *
 * `dpdp.read` gates the list; `dpdp.decide` gates the actions, and it is
 * super-admin only — both actions are one-way for the person concerned.
 */
import {
  AdminDataTable,
  Button,
  ConsolePageHeader,
  cn,
  consoleControlClass,
  type AdminColumn,
} from "@agri/ui";
import { useCallback, useEffect, useState } from "react";

interface DataRequest {
  id: string;
  agri_id: string;
  status: string;
  requested_at: string;
  execute_after: string;
  hold_reasons: string[];
  executed_at: string | null;
}

const STATUSES = ["", "held", "pending", "executed", "cancelled"] as const;

function fmt(iso: string | null): string {
  if (!iso) return "—";
  return new Date(iso).toLocaleString("en-IN", {
    day: "2-digit",
    month: "short",
    year: "numeric",
  });
}

function dueLabel(row: DataRequest): string {
  if (row.status === "executed") return `erased ${fmt(row.executed_at)}`;
  const due = new Date(row.execute_after);
  return due > new Date() ? `due ${fmt(row.execute_after)}` : `due now (${fmt(row.execute_after)})`;
}

export function DataRequestsView() {
  const [rows, setRows] = useState<DataRequest[] | null>(null);
  const [status, setStatus] = useState<string>("");
  const [busy, setBusy] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);

  const load = useCallback(async () => {
    const query = status ? `?status=${status}` : "";
    const res = await fetch(`/api/admin/data-requests${query}`);
    if (!res.ok) {
      setError(String(res.status));
      setRows([]);
      return;
    }
    const body = (await res.json()) as { items: DataRequest[] };
    setRows(body.items);
    setError(null);
  }, [status]);

  useEffect(() => {
    void load();
  }, [load]);

  const act = async (row: DataRequest, action: "release" | "execute" | "cancel") => {
    setBusy(row.id);
    setError(null);
    try {
      const res = await fetch(`/api/admin/data-requests/${row.id}/${action}`, { method: "POST" });
      if (!res.ok) {
        const body = (await res.json().catch(() => ({}))) as { detail?: string };
        setError(body.detail ?? String(res.status));
      }
      await load();
    } finally {
      setBusy(null);
    }
  };

  const columns: readonly AdminColumn<DataRequest>[] = [
    { key: "agri_id", header: "Account", cell: (r) => `@${r.agri_id || "—"}` },
    {
      key: "status",
      header: "Status",
      cell: (r) => (
        <span className={cn("font-semibold", r.status === "held" && "text-down")}>{r.status}</span>
      ),
    },
    { key: "requested_at", header: "Requested", cell: (r) => fmt(r.requested_at) },
    { key: "execute_after", header: "Grace", cell: dueLabel },
    {
      key: "hold_reasons",
      header: "Held by",
      // staff-only context: these name another module's business state and
      // are never returned on the user-facing route
      cell: (r) => (r.hold_reasons.length ? r.hold_reasons.join(", ") : "—"),
    },
    {
      key: "id",
      header: "Actions",
      cell: (r) => {
        const open = r.status === "pending" || r.status === "held";
        if (!open) return "—";
        const due = new Date(r.execute_after) <= new Date();
        return (
          <span className="flex flex-wrap gap-1.5">
            {r.status === "held" && (
              <Button variant="ghost" disabled={busy === r.id} onClick={() => void act(r, "release")}>
                Release hold
              </Button>
            )}
            {/* Only offered once the grace has actually elapsed. Staff can
                skip the scheduler, never the promise made to the user. */}
            {due && (
              <Button variant="ghost" disabled={busy === r.id} onClick={() => void act(r, "execute")}>
                Run now
              </Button>
            )}
            <Button variant="ghost" disabled={busy === r.id} onClick={() => void act(r, "cancel")}>
              Withdraw
            </Button>
          </span>
        );
      },
    },
  ];

  return (
    <div className="space-y-4">
      <ConsolePageHeader
        title="Data requests"
        sub="DPDP 2023 erasure requests. Held requests are the only ones waiting on a human."
      />
      <label className="flex items-center gap-2 text-sm">
        <span className="text-sub">Status</span>
        <select
          className={consoleControlClass}
          value={status}
          onChange={(event) => setStatus(event.target.value)}
        >
          {STATUSES.map((s) => (
            <option key={s || "all"} value={s}>
              {s || "all"}
            </option>
          ))}
        </select>
      </label>
      {error && <p className="text-sm text-down">Could not complete that: {error}</p>}
      <AdminDataTable
        caption="DPDP data requests"
        columns={columns}
        rows={rows ?? []}
        rowKey={(r) => r.id}
        loading={rows === null}
        empty={{
          icon: "🗂️",
          title: "Queue clear",
          description: "No erasure requests are waiting.",
        }}
      />
    </div>
  );
}
