"use client";

/**
 * Price-alert management (AG-U5 P2).
 *
 * WHAT THIS LIST IS, AND WHY IT DOES NOT LOOK LIKE THE REFERENCE.
 * A5 draws three rows — "Tomato · Coimbatore market · alert when above
 * ₹30/kg", "Severe weather · Coimbatore district" — implying per-commodity
 * thresholds and a weather channel. The engine has neither. `market.PriceAlert`
 * is keyed on `(user, pincode)` and carries exactly `pincode` and
 * `last_notified_on`; there is no commodity column, no threshold column and no
 * kind. That is a decision, not a gap — `market_data/alerts.py` argues it at
 * length: the source publishes once a day, so a threshold alert is still a
 * once-a-day message that goes silent on the days nothing crossed, which is
 * indistinguishable to the person waiting from the pull having failed.
 *
 * So each row says what a subscription actually is: one pincode, one digest a
 * day. Rendering the reference's design would advertise a threshold nobody
 * can set. Logged in docs/qa/ag-u5-visual-log.md.
 *
 * Deletion goes through the BFF (`/api/market/*`), which attaches the bearer
 * server-side — tokens never touch client JS.
 */

import { Card } from "@agri/ui";
import { useState } from "react";

export interface AlertRow {
  id: string;
  pincode: string;
  last_notified_on: string | null;
}

export interface AlertsCopy {
  digest: string;
  what: string;
  lastSent: string;
  never: string;
  off: string;
  offBusy: string;
  offFailed: string;
  empty: string;
}

export function AlertsManager({
  initial,
  copy,
  showExplainer = false,
}: {
  initial: AlertRow[];
  copy: AlertsCopy;
  showExplainer?: boolean;
}) {
  const [rows, setRows] = useState(initial);
  const [busy, setBusy] = useState<string | null>(null);
  const [failed, setFailed] = useState<string | null>(null);

  const turnOff = async (id: string) => {
    setBusy(id);
    setFailed(null);
    try {
      const res = await fetch(`/api/market/alerts/${id}`, { method: "DELETE" });
      // 404 counts as success: the row is gone either way, and the server
      // answers 404 identically for "not yours" and "does not exist" (the
      // U2 IDOR rule), so there is nothing here to tell apart.
      if (!res.ok && res.status !== 404) throw new Error(String(res.status));
      setRows((current) => current.filter((row) => row.id !== id));
    } catch {
      setFailed(id);
    } finally {
      setBusy(null);
    }
  };

  if (rows.length === 0) {
    return (
      <p className="rounded-card border border-cream-line bg-cream px-3 py-3 text-[12.5px] text-sub">
        {copy.empty}
      </p>
    );
  }

  return (
    <div className="space-y-2">
      {showExplainer ? <p className="text-[12px] text-sub">{copy.what}</p> : null}
      <ul className="space-y-2">
        {rows.map((row) => (
          <li
            key={row.id}
            className="flex flex-wrap items-center gap-2 rounded-card border border-cream-line bg-cream px-3 py-2.5"
          >
            <span aria-hidden="true" className="text-[16px] leading-none">
              🔔
            </span>
            <span className="min-w-0 flex-1">
              <span className="block text-[13px] font-semibold text-ink">
                {copy.digest} · {row.pincode}
              </span>
              <span className="mt-0.5 block text-[11.5px] text-sub">
                {row.last_notified_on
                  ? copy.lastSent.replace("{date}", row.last_notified_on)
                  : copy.never}
              </span>
              {failed === row.id ? (
                <span role="alert" className="mt-0.5 block text-[11.5px] font-semibold text-down">
                  {copy.offFailed}
                </span>
              ) : null}
            </span>
            <button
              type="button"
              onClick={() => void turnOff(row.id)}
              disabled={busy === row.id}
              className="tap-target inline-flex min-h-[36px] items-center rounded-pill border border-cream-line bg-card px-3 text-[12px] font-semibold text-ink disabled:opacity-60"
            >
              {busy === row.id ? copy.offBusy : copy.off}
            </button>
          </li>
        ))}
      </ul>
    </div>
  );
}

/** The same list, wrapped as an overview panel with its own heading. */
export function AlertsPanel({
  initial,
  copy,
  title,
  manageLabel,
}: {
  initial: AlertRow[];
  copy: AlertsCopy;
  title: string;
  manageLabel: string;
}) {
  return (
    <Card className="p-3.5">
      <div className="mb-2.5 flex items-center gap-2">
        <h2 className="font-display text-[15px] font-extrabold text-ink">
          <span aria-hidden="true" className="mr-1.5">
            🔔
          </span>
          {title}
        </h2>
        <span className="flex-1" />
        <a
          href="/account/alerts"
          className="tap-target text-[12.5px] font-semibold text-brand no-underline"
        >
          {manageLabel}
        </a>
      </div>
      <AlertsManager initial={initial} copy={copy} />
    </Card>
  );
}
