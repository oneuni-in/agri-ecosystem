"use client";

import { useCallback, useEffect, useState } from "react";

/**
 * A-U4 W2 — the coins centre's live half: balance, ledger, referral share.
 *
 * Everything here goes through the BFF proxy (`/api/coins/*`), which attaches
 * the session bearer server-side — tokens never touch JS (D10).
 *
 * The ledger is rendered from `reason_code` + a server-supplied label KEY,
 * never from server-sent prose: the API deliberately returns
 * `coins.reason.review_approved` rather than "Review approved", so the same
 * ledger reads correctly in EN, TA and HI without the server knowing the
 * visitor's language.
 */

interface HistoryItem {
  id: string;
  delta: number;
  reason_code: string;
  reason_label_key: string;
  ref_type: string;
  created_at: string;
}

export interface CoinsCopy {
  balanceLabel: string;
  historyTitle: string;
  historyEmpty: string;
  loadMore: string;
  referralTitle: string;
  referralSub: string;
  copyCode: string;
  copied: string;
  shareWhatsapp: string;
  shareText: string;
  error: string;
  loading: string;
  notMoney: string;
}

export function CoinsClient({
  copy,
  reasonLabels,
}: {
  copy: CoinsCopy;
  reasonLabels: Record<string, string>;
}) {
  const [balance, setBalance] = useState<number | null>(null);
  const [items, setItems] = useState<HistoryItem[]>([]);
  const [cursor, setCursor] = useState<string | null>(null);
  const [code, setCode] = useState<string | null>(null);
  const [failed, setFailed] = useState(false);
  const [copied, setCopied] = useState(false);

  const loadPage = useCallback(async (next: string | null) => {
    const qs = next ? `?cursor=${encodeURIComponent(next)}` : "";
    const res = await fetch(`/api/coins/history${qs}`, { cache: "no-store" });
    if (!res.ok) throw new Error(String(res.status));
    const body = (await res.json()) as { items: HistoryItem[]; next_cursor: string | null };
    setItems((prev) => [...prev, ...body.items]);
    setCursor(body.next_cursor);
  }, []);

  useEffect(() => {
    let cancelled = false;
    (async () => {
      try {
        const [balanceRes, codeRes] = await Promise.all([
          fetch("/api/coins/balance", { cache: "no-store" }),
          fetch("/api/coins/referral-code", { cache: "no-store" }),
        ]);
        if (!balanceRes.ok || !codeRes.ok) throw new Error("load failed");
        const balanceBody = (await balanceRes.json()) as { balance: number };
        const codeBody = (await codeRes.json()) as { code: string };
        if (cancelled) return;
        setBalance(balanceBody.balance);
        setCode(codeBody.code);
        await loadPage(null);
      } catch {
        if (!cancelled) setFailed(true);
      }
    })();
    return () => {
      cancelled = true;
    };
  }, [loadPage]);

  const label = (item: HistoryItem) => {
    // The server sends "coins.reason.<code>"; the page resolved every known
    // code into `reasonLabels`. An unmapped code falls back to the generic
    // label rather than rendering a raw key at a user.
    const key = item.reason_label_key.replace("coins.reason.", "");
    return reasonLabels[key] ?? reasonLabels.unknown ?? item.reason_code;
  };

  const shareHref = code
    ? `https://wa.me/?text=${encodeURIComponent(`${copy.shareText} ${code}`)}`
    : undefined;

  if (failed) {
    return (
      <p className="mt-5 rounded-card border border-severe bg-severe-bg px-4 py-3 text-[13px] text-severe-ink">
        {copy.error}
      </p>
    );
  }

  return (
    <div className="mt-5 flex flex-col gap-5">
      {/* balance */}
      <section
        aria-label={copy.balanceLabel}
        className="rounded-band border border-cream-line bg-coins-bg px-5 py-5"
      >
        <span className="block text-[11px] font-medium uppercase tracking-wide text-coins-fg">
          {copy.balanceLabel}
        </span>
        <b
          aria-live="polite"
          className="mt-1 block font-display text-[34px] font-extrabold leading-none text-coins-fg"
        >
          {balance === null ? copy.loading : `🪙 ${balance.toLocaleString("en-IN")}`}
        </b>
      </section>

      {/* referral share */}
      <section
        aria-labelledby="coins-referral"
        className="rounded-card border border-cream-line bg-card px-5 py-4"
      >
        <h2 id="coins-referral" className="font-display text-base font-semibold text-ink">
          {copy.referralTitle}
        </h2>
        <p className="mt-1 text-[12px] text-sub">{copy.referralSub}</p>
        <div className="mt-3 flex flex-wrap items-center gap-2.5">
          <code className="rounded-btn border border-cream-line bg-cream-deep px-4 py-2.5 font-mono text-[15px] font-semibold tracking-wider text-ink">
            {code ?? "…"}
          </code>
          <button
            type="button"
            disabled={!code}
            onClick={async () => {
              if (!code) return;
              await navigator.clipboard.writeText(code);
              setCopied(true);
              setTimeout(() => setCopied(false), 2000);
            }}
            className="tap-target inline-flex min-h-[44px] items-center rounded-btn border border-cream-line bg-card px-4 text-[12.5px] font-bold text-ink disabled:opacity-50"
          >
            {copied ? copy.copied : copy.copyCode}
          </button>
          {shareHref ? (
            <a
              href={shareHref}
              target="_blank"
              rel="noopener noreferrer"
              className="tap-target inline-flex min-h-[44px] items-center rounded-btn border border-wa-line bg-wa-soft px-4 text-[12.5px] font-bold text-wa-deep no-underline"
            >
              {copy.shareWhatsapp}
            </a>
          ) : null}
        </div>
      </section>

      {/* ledger */}
      <section aria-labelledby="coins-history">
        <h2 id="coins-history" className="font-display text-base font-semibold text-ink">
          {copy.historyTitle}
        </h2>
        {items.length === 0 ? (
          <p className="mt-2 rounded-card border border-cream-line bg-card px-4 py-5 text-center text-[12.5px] text-muted">
            {balance === null ? copy.loading : copy.historyEmpty}
          </p>
        ) : (
          <ul className="mt-2 flex flex-col divide-y divide-cream-line rounded-card border border-cream-line bg-card">
            {items.map((item) => (
              <li key={item.id} className="flex items-center gap-3 px-4 py-3">
                <span className="min-w-0 flex-1">
                  <b className="block text-[13px] font-medium text-ink">{label(item)}</b>
                  <small className="text-[10.5px] text-muted">
                    {new Date(item.created_at).toLocaleDateString()}
                  </small>
                </span>
                <span
                  className={`font-display text-[15px] font-semibold ${
                    item.delta >= 0 ? "text-coins-fg" : "text-down"
                  }`}
                >
                  {item.delta >= 0 ? `+${item.delta}` : item.delta}
                </span>
              </li>
            ))}
          </ul>
        )}
        {cursor ? (
          <button
            type="button"
            onClick={() => void loadPage(cursor).catch(() => setFailed(true))}
            className="tap-target mt-3 inline-flex min-h-[44px] items-center rounded-btn border border-cream-line bg-card px-4 text-[12.5px] font-bold text-ink"
          >
            {copy.loadMore}
          </button>
        ) : null}
      </section>
    </div>
  );
}
