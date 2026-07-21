"use client";

/**
 * Subscription card + cursor-paginated invoice list via the /api/billing BFF
 * proxy. Placeholder tier prices render until Pricing v1; checkout is a
 * redirect to Razorpay's hosted short_url - no payment JS ever loads here.
 */

import { useCallback, useEffect, useState } from "react";

import { ApiError, getJson } from "@/lib/api";

interface SubscriptionView {
  id: string;
  tier: string;
  status: string;
  current_period_end: string | null;
}

interface TierView {
  key: string;
  display_name: string;
  monthly_price_paise: number;
}

interface InvoiceView {
  id: string;
  amount_paise: number;
  currency: string;
  status: string;
  created_at: string;
}

function rupees(paise: number): string {
  return `₹${(paise / 100).toLocaleString("en-IN")}`;
}

export function BillingClient() {
  const [subscription, setSubscription] = useState<SubscriptionView | null>(null);
  const [businessName, setBusinessName] = useState<string | null>(null);
  const [tiers, setTiers] = useState<TierView[]>([]);
  const [invoices, setInvoices] = useState<InvoiceView[]>([]);
  const [cursor, setCursor] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);

  const loadInvoices = useCallback(async (after: string | null) => {
    const query = after ? `?cursor=${encodeURIComponent(after)}` : "";
    const body = await getJson(`/api/billing/invoices${query}`);
    setInvoices((existing) => [...existing, ...(body.items as unknown as InvoiceView[])]);
    setCursor((body.next_cursor as string | null) ?? null);
  }, []);

  useEffect(() => {
    (async () => {
      try {
        const body = await getJson("/api/billing/subscription");
        setSubscription(body.subscription as unknown as SubscriptionView | null);
        setBusinessName((body.business_name as string | null) ?? null);
        setTiers(body.tiers as unknown as TierView[]);
        await loadInvoices(null);
      } catch (caught) {
        setError(caught instanceof ApiError ? caught.detail : "request_failed");
      } finally {
        setLoading(false);
      }
    })();
  }, [loadInvoices]);

  if (loading) return <p className="mt-4 text-[13px] text-sub">Loading…</p>;
  if (error) {
    return (
      <p className="mt-4 rounded-card border border-alert-line bg-alert-bg p-3 text-[13px] font-semibold text-ink">
        Could not load billing: {error}
      </p>
    );
  }
  return (
    <div className="mt-4 space-y-4">
      <section className="rounded-card border border-line bg-card p-4">
        {subscription ? (
          <>
            <p className="text-[13px] font-extrabold text-ink">
              {businessName} — {subscription.tier} ({subscription.status})
            </p>
            <p className="mt-1 text-[13px] text-sub">
              {subscription.current_period_end
                ? `Current period ends ${new Date(subscription.current_period_end).toLocaleDateString("en-IN")}`
                : "Awaiting first payment"}
            </p>
          </>
        ) : (
          <>
            <p className="text-[13px] font-extrabold text-ink">Free plan</p>
            <p className="mt-1 text-[13px] text-sub">
              Paid tiers (placeholder pricing until launch):{" "}
              {tiers
                .map((tier) => `${tier.display_name} ${rupees(tier.monthly_price_paise)}/mo`)
                .join(" · ")}
            </p>
          </>
        )}
      </section>
      <section>
        <h2 className="text-[15px] font-extrabold text-ink">Invoices</h2>
        {invoices.length === 0 ? (
          <p className="mt-2 text-[13px] text-sub">No invoices yet.</p>
        ) : (
          <ul className="mt-2 space-y-2">
            {invoices.map((invoice) => (
              <li
                key={invoice.id}
                className="flex items-center justify-between rounded-card border border-line bg-card p-3"
              >
                <span className="text-[13px] text-ink">
                  {new Date(invoice.created_at).toLocaleDateString("en-IN")}
                </span>
                <span className="text-[13px] text-sub">{invoice.status}</span>
                <span className="text-[13px] font-extrabold text-ink">
                  {rupees(invoice.amount_paise)}
                </span>
              </li>
            ))}
          </ul>
        )}
        {cursor ? (
          <button
            type="button"
            onClick={() => void loadInvoices(cursor)}
            className="mt-3 rounded-card border border-line px-3 py-2 text-[13px] font-semibold text-ink"
          >
            Load more
          </button>
        ) : null}
      </section>
    </div>
  );
}
