"use client";

/**
 * Subscription card + cursor-paginated invoice list via the /api/billing BFF
 * proxy. Placeholder tier prices render until Pricing v1; checkout is a
 * redirect to Razorpay's hosted short_url - no payment JS ever loads here.
 */

import { Button, Card, EmptyState, Skeleton } from "@agri/ui";
import { useCallback, useEffect, useState, type ReactNode } from "react";

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

function AlertNotice({ children }: { children: ReactNode }) {
  return (
    <div className="rounded-card border border-alert-line bg-alert-bg p-3 text-[13px] font-semibold text-ink">
      {children}
    </div>
  );
}

export function BillingClient() {
  const [subscription, setSubscription] = useState<SubscriptionView | null>(null);
  const [businessName, setBusinessName] = useState<string | null>(null);
  const [tiers, setTiers] = useState<TierView[]>([]);
  const [invoices, setInvoices] = useState<InvoiceView[]>([]);
  const [cursor, setCursor] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);
  const [loadingMore, setLoadingMore] = useState(false);

  const loadInvoices = useCallback(async (after: string | null, append: boolean) => {
    if (append) setLoadingMore(true);
    try {
      const query = after ? `?cursor=${encodeURIComponent(after)}` : "";
      const body = await getJson(`/api/billing/invoices${query}`);
      const newItems = (body.items as InvoiceView[] | undefined) ?? [];
      setInvoices((existing) => (append ? [...existing, ...newItems] : newItems));
      setCursor((body.next_cursor as string | null | undefined) ?? null);
    } finally {
      if (append) setLoadingMore(false);
    }
  }, []);

  useEffect(() => {
    (async () => {
      try {
        const body = await getJson("/api/billing/subscription");
        setSubscription((body.subscription as SubscriptionView | null | undefined) ?? null);
        setBusinessName((body.business_name as string | null | undefined) ?? null);
        setTiers((body.tiers as TierView[] | undefined) ?? []);
        await loadInvoices(null, false);
      } catch (caught) {
        setError(caught instanceof ApiError ? caught.detail : "request_failed");
      } finally {
        setLoading(false);
      }
    })();
  }, [loadInvoices]);

  if (loading) {
    return (
      <div className="mt-4 space-y-4">
        <Skeleton width="100%" height="76px" />
        <div className="space-y-2">
          <Skeleton width="100%" height="48px" />
          <Skeleton width="100%" height="48px" />
        </div>
      </div>
    );
  }
  if (error) {
    return (
      <div className="mt-4">
        <AlertNotice>Could not load billing: {error}</AlertNotice>
      </div>
    );
  }
  return (
    <div className="mt-4 space-y-4">
      <Card className="p-4">
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
      </Card>
      <section>
        <h2 className="text-[15px] font-extrabold text-ink">Invoices</h2>
        {invoices.length === 0 ? (
          <EmptyState className="mt-2" icon="🧾" title="No invoices yet." />
        ) : (
          <div className="mt-2 space-y-2">
            {invoices.map((invoice) => (
              <Card key={invoice.id} className="flex items-center justify-between p-3">
                <span className="text-[13px] text-ink">
                  {new Date(invoice.created_at).toLocaleDateString("en-IN")}
                </span>
                <span className="text-[13px] text-sub">{invoice.status}</span>
                <span className="text-[13px] font-extrabold text-ink">
                  {rupees(invoice.amount_paise)}
                </span>
              </Card>
            ))}
          </div>
        )}
        {cursor ? (
          <Button
            type="button"
            variant="ghost"
            className="mt-3"
            disabled={loadingMore}
            onClick={() => void loadInvoices(cursor, true)}
          >
            {loadingMore ? "Loading..." : "Load more"}
          </Button>
        ) : null}
      </section>
    </div>
  );
}
