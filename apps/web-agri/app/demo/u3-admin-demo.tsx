"use client";

/**
 * U3 admin-console demo island: the interactive contracts SSR can't show —
 * AdminDataTable's toolbar filter + keyboard row-open, DetailDrawer opening
 * from a row, ConfirmDialog capturing the justification INSIDE the confirm
 * step (audit rule 3), and cursor-driven load-more. Same components the
 * web-admin routes render — never a copy of their markup.
 */
import {
  AdminDataTable,
  Button,
  ConfirmDialog,
  ConsoleNotice,
  DetailDrawer,
  StateChip,
  cn,
  consoleControlClass,
  type AdminColumn,
} from "@agri/ui";
import { useState } from "react";

interface DemoBusiness {
  id: string;
  name: string;
  pincode: string;
  kind: string;
  status: "active" | "suspended";
}

const FIRST_PAGE: readonly DemoBusiness[] = [
  { id: "b1", name: "Sakthi Dairy Farm", pincode: "641001", kind: "Vendor", status: "active" },
  { id: "b2", name: "Ponni Milk Depot", pincode: "600001", kind: "Shop", status: "active" },
  { id: "b3", name: "Velan Organic Farm", pincode: "641035", kind: "Farm", status: "suspended" },
];

const SECOND_PAGE: readonly DemoBusiness[] = [
  { id: "b4", name: "Amudham Dairy", pincode: "600042", kind: "Vendor", status: "active" },
  { id: "b5", name: "Kaveri Milk Point", pincode: "620001", kind: "Shop", status: "active" },
];

export function U3AdminDemo() {
  const [rows, setRows] = useState<readonly DemoBusiness[]>(FIRST_PAGE);
  const [cursor, setCursor] = useState<string | null>("demo-cursor-page-2");
  const [query, setQuery] = useState("");
  const [openRow, setOpenRow] = useState<DemoBusiness | null>(null);
  const [lastAction, setLastAction] = useState<string | null>(null);

  const visible = rows.filter((row) =>
    row.name.toLowerCase().includes(query.trim().toLowerCase()),
  );

  const columns: readonly AdminColumn<DemoBusiness>[] = [
    { key: "name", header: "Business", cell: (row) => row.name },
    { key: "kind", header: "Type", cell: (row) => row.kind, hideBelow: "lg" },
    { key: "pincode", header: "Pincode", cell: (row) => row.pincode },
    {
      key: "status",
      header: "Status",
      cell: (row) =>
        row.status === "active" ? (
          <StateChip tone="ok">Active</StateChip>
        ) : (
          <StateChip tone="alert">Suspended</StateChip>
        ),
    },
  ];

  return (
    <div className="flex flex-col gap-3">
      <AdminDataTable
        caption="Businesses (demo)"
        columns={columns}
        rows={visible}
        rowKey={(row) => row.id}
        toolbar={
          <input
            aria-label="Search businesses"
            placeholder="Search businesses"
            value={query}
            onChange={(event) => setQuery(event.target.value)}
            className={cn(consoleControlClass, "mt-0 max-w-[260px]")}
          />
        }
        empty={{
          icon: "✅",
          title: "No businesses match.",
          description: "Clear the search to see the full list.",
        }}
        nextCursor={cursor}
        onLoadMore={() => {
          setRows((current) => [...current, ...SECOND_PAGE]);
          setCursor(null);
        }}
        onRowOpen={(row) => setOpenRow(row)}
        rowOpenLabel={(row) => `Open ${row.name}`}
      />

      {lastAction ? <ConsoleNotice tone="ok">{lastAction}</ConsoleNotice> : null}

      <DetailDrawer
        open={openRow !== null}
        onOpenChange={(next) => {
          if (!next) setOpenRow(null);
        }}
        title={openRow?.name ?? ""}
        description={openRow ? `${openRow.kind} · ${openRow.pincode}` : undefined}
      >
        {openRow ? (
          <div className="flex flex-col gap-3 text-[13px] text-ink">
            <p>
              Detail drawer body — Group B renders the entity's fields, audit trail and
              enforcement state here.
            </p>
            <ConfirmDialog
              trigger={
                <Button variant="ghost" className="flex-none px-4">
                  Suspend business
                </Button>
              }
              title={`Suspend ${openRow.name}?`}
              description="It is hidden from consumer results immediately. Reinstating restores it."
              confirmLabel="Suspend"
              cancelLabel="Keep it live"
              reasonLabel="Reason"
              reasonHint="Recorded in the audit log with your name."
              onConfirm={(reason) => {
                setLastAction(`Suspended ${openRow.name} — reason recorded: "${reason}"`);
                setOpenRow(null);
              }}
            />
          </div>
        ) : null}
      </DetailDrawer>
    </div>
  );
}
