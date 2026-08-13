"use client";

/**
 * Payments read surface (U3) — DISPLAY ONLY. Two views of Razorpay activity:
 * the append-only ad-revenue ledger and the raw webhook event log. Both tables
 * are append-only by grant on the backend, so no admin action can alter a row —
 * and this console offers none (no charge / refund / credit / reconcile). Money
 * figures arrive preformatted (`amount_display`) from the backend; the UI never
 * does money arithmetic. `signature_verified` is derived server-side: a logged
 * event is one whose HMAC check passed (bad signatures 400 before persisting).
 */
import {
  AdminDataTable,
  ConsoleNotice,
  ConsolePageHeader,
  StateChip,
  consoleNavLinkClass,
  type AdminColumn,
} from "@agri/ui";
import { useState } from "react";

import { useAdminList } from "@/lib/use-admin-list";

interface LedgerRow {
  id: string;
  entry_type: string;
  amount_display: string;
  currency: string;
  campaign_id: string | null;
  business_id: string;
  razorpay_payment_id: string | null;
  created_at: string;
}

interface EventRow {
  id: string;
  provider: string;
  event_type: string;
  provider_event_id: string;
  outcome: string;
  signature_verified: boolean;
  created_at: string;
}

function shortId(id: string | null): string {
  return id ? `${id.slice(0, 8)}…` : "—";
}

function fmtDate(iso: string): string {
  return new Date(iso).toLocaleDateString("en-IN", { day: "2-digit", month: "short", year: "numeric" });
}

const ledgerColumns: readonly AdminColumn<LedgerRow>[] = [
  {
    key: "type",
    header: "Type",
    cell: (r) =>
      r.entry_type === "ad_refund" ? (
        <StateChip tone="alert">Refund</StateChip>
      ) : (
        <StateChip tone="ok">Charge</StateChip>
      ),
  },
  { key: "amount", header: "Amount", cell: (r) => r.amount_display, align: "right" },
  { key: "campaign", header: "Campaign", cell: (r) => shortId(r.campaign_id), hideBelow: "lg" },
  { key: "business", header: "Business", cell: (r) => shortId(r.business_id), hideBelow: "lg" },
  { key: "payment", header: "Razorpay payment", cell: (r) => r.razorpay_payment_id ?? "—", hideBelow: "xl" },
  { key: "created", header: "Date", cell: (r) => fmtDate(r.created_at) },
];

const eventColumns: readonly AdminColumn<EventRow>[] = [
  { key: "event", header: "Event", cell: (r) => r.event_type },
  {
    key: "sig",
    header: "Signature",
    cell: (r) =>
      r.signature_verified ? (
        <StateChip tone="ok">Verified</StateChip>
      ) : (
        <StateChip tone="alert">Unverified</StateChip>
      ),
  },
  { key: "outcome", header: "Outcome", cell: (r) => r.outcome },
  { key: "provider_event", header: "Provider event id", cell: (r) => r.provider_event_id, hideBelow: "lg" },
  { key: "created", header: "Date", cell: (r) => fmtDate(r.created_at) },
];

function LedgerTable() {
  const { items, cursor, loading, loadingMore, error, reload } = useAdminList<LedgerRow>("/payments/ledger");
  return (
    <AdminDataTable
      caption="Ad-revenue ledger"
      columns={ledgerColumns}
      rows={items}
      rowKey={(r) => r.id}
      loading={loading}
      loadingMore={loadingMore}
      {...(error ? { error: `Could not load the ledger (${error}).` } : {})}
      empty={{ icon: "🧾", title: "No ledger entries yet.", description: "Charges and refunds appear here once payments settle." }}
      nextCursor={cursor}
      onLoadMore={() => cursor && void reload(cursor)}
    />
  );
}

function EventsTable() {
  const { items, cursor, loading, loadingMore, error, reload } = useAdminList<EventRow>("/payments/events");
  return (
    <AdminDataTable
      caption="Razorpay webhook events"
      columns={eventColumns}
      rows={items}
      rowKey={(r) => r.id}
      loading={loading}
      loadingMore={loadingMore}
      {...(error ? { error: `Could not load events (${error}).` } : {})}
      empty={{ icon: "🧾", title: "No webhook events yet.", description: "Verified Razorpay events appear here as they arrive." }}
      nextCursor={cursor}
      onLoadMore={() => cursor && void reload(cursor)}
    />
  );
}

export function PaymentsView() {
  const [tab, setTab] = useState<"ledger" | "events">("ledger");
  return (
    <main className="space-y-3">
      <ConsolePageHeader title="Payments" sub="Razorpay ledger & webhook log · read-only" />
      <ConsoleNotice tone="ok">
        Display only — this console cannot charge, refund, credit or reconcile. Both logs are
        append-only; no action here can alter a row.
      </ConsoleNotice>
      <div className="flex gap-2" role="tablist" aria-label="Payments view">
        <button
          type="button"
          role="tab"
          aria-selected={tab === "ledger"}
          className={consoleNavLinkClass(tab === "ledger")}
          onClick={() => setTab("ledger")}
        >
          Ledger
        </button>
        <button
          type="button"
          role="tab"
          aria-selected={tab === "events"}
          className={consoleNavLinkClass(tab === "events")}
          onClick={() => setTab("events")}
        >
          Webhook events
        </button>
      </div>
      {tab === "ledger" ? <LedgerTable /> : <EventsTable />}
    </main>
  );
}
