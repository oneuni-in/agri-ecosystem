"use client";

import { Button, Card, EmptyState, Skeleton, cn } from "@agri/ui";
import Link from "next/link";
import { useEffect, useRef, useState, type ReactNode } from "react";

import { getJson, putJson } from "@/lib/api";

interface BusinessRef {
  id: string;
  name: string;
}

interface TierSelection {
  subscription_tier: "free" | "premium";
  premium_requested_at: string | null;
}

const FIELD =
  "mt-1 block min-h-[44px] w-full rounded-btn border border-line bg-card px-3 py-2 text-[13px] text-ink";
const LABEL = "block text-[13px] font-semibold text-ink";

function AlertNotice({ children }: { children: ReactNode }) {
  return (
    <div className="rounded-card border border-alert-line bg-alert-bg p-3 text-[13px] font-semibold text-ink">
      {children}
    </div>
  );
}

export function PremiumClient({ billingLive }: { billingLive: boolean }) {
  const [businesses, setBusinesses] = useState<BusinessRef[] | null>(null);
  const [loadError, setLoadError] = useState(false);
  const [selectedId, setSelectedId] = useState<string | null>(null);
  const [selection, setSelection] = useState<TierSelection | null>(null);
  const [saving, setSaving] = useState(false);
  const [saveError, setSaveError] = useState(false);

  // Capture current selectedId in ref for save guards (D26 pattern)
  const selectedIdRef = useRef<string | null>(null);

  useEffect(() => {
    selectedIdRef.current = selectedId;
  }, [selectedId]);

  useEffect(() => {
    void (async () => {
      try {
        const body = await getJson("/api/directory/businesses?limit=50");
        const list = (body.items as BusinessRef[] | undefined) ?? [];
        setBusinesses(list);
        if (list[0]) setSelectedId(list[0].id);
      } catch {
        setLoadError(true);
      }
    })();
  }, []);

  // D26 cancelled guard: drop stale responses if selectedId changes before fetch resolves
  useEffect(() => {
    if (!selectedId) return;
    setSelection(null);
    let cancelled = false;
    void (async () => {
      try {
        const body = await getJson(`/api/directory/businesses/${selectedId}/tier-selection`);
        if (cancelled) return;
        setSelection(body as unknown as TierSelection);
      } catch {
        if (!cancelled) setSelection(null);
      }
    })();
    return () => {
      cancelled = true;
    };
  }, [selectedId]);

  // D26 capture-id-before-await guard: if user switches businesses mid-save, ignore the response
  const select = async (tier: "free" | "premium") => {
    if (!selectedId) return;
    const savedFor = selectedId;
    setSaving(true);
    setSaveError(false);
    try {
      const body = await putJson(`/api/directory/businesses/${savedFor}/tier-selection`, { tier });
      if (selectedIdRef.current !== savedFor) return;
      setSelection(body as unknown as TierSelection);
    } catch {
      if (selectedIdRef.current !== savedFor) return;
      setSaveError(true);
    } finally {
      setSaving(false);
    }
  };

  if (loadError) {
    return (
      <div className="mt-4">
        <AlertNotice>Could not load your businesses — please try again.</AlertNotice>
      </div>
    );
  }
  if (businesses === null) {
    return (
      <div className="mt-4 space-y-3">
        <Skeleton width="100%" height="44px" />
        <Skeleton width="100%" height="160px" />
      </div>
    );
  }
  if (businesses.length === 0) {
    return <EmptyState className="mt-4" icon="⭐" title="Create a listing first to go premium." />;
  }

  const isPremiumActive = selection?.subscription_tier === "premium";
  const premiumRequested = Boolean(selection?.premium_requested_at);

  return (
    <div className="mt-4 space-y-4">
      <label className={LABEL}>
        Business
        <select className={FIELD} value={selectedId ?? ""} onChange={(e) => setSelectedId(e.target.value)}>
          {businesses.map((b) => (
            <option key={b.id} value={b.id}>{b.name}</option>
          ))}
        </select>
      </label>

      {saveError ? <AlertNotice>Could not save your choice — please try again.</AlertNotice> : null}

      {selection === null ? (
        <Skeleton width="100%" height="160px" />
      ) : (
        <div className="grid gap-3 sm:grid-cols-2">
          <Card className={cn("space-y-2 p-4", !premiumRequested && !isPremiumActive && "border-ink")}>
            <p className="text-[13px] font-extrabold text-ink">Free</p>
            <p className="text-[13px] text-ink">Standard listing, leads inbox, analytics.</p>
            <Button
              type="button"
              variant="ghost"
              disabled={saving || (!premiumRequested && !isPremiumActive)}
              onClick={() => void select("free")}
            >
              {!premiumRequested && !isPremiumActive ? "Current plan" : "Switch to free"}
            </Button>
          </Card>

          <Card className={cn("space-y-2 p-4", (premiumRequested || isPremiumActive) && "border-ink")}>
            <div className="flex items-center justify-between">
              <p className="text-[13px] font-extrabold text-ink">Premium</p>
              {isPremiumActive ? (
                <span className="rounded-pill bg-verified-bg px-[9px] py-[3px] text-[11px] font-extrabold text-verified-fg">
                  Active
                </span>
              ) : premiumRequested ? (
                <span className="rounded-pill bg-sponsored-bg px-[9px] py-[3px] text-[11px] font-extrabold text-sponsored-fg">
                  Activates at launch
                </span>
              ) : null}
            </div>
            <p className="text-[13px] text-ink">
              Priority placement in search results — premium listings appear first for every pincode
              you cover.
            </p>
            {isPremiumActive ? (
              <p className="text-[12px] text-sub">Premium is active for this business.</p>
            ) : billingLive ? (
              <Link
                href="/business/billing"
                className="inline-block text-[13px] font-semibold text-ink underline"
              >
                Manage subscription
              </Link>
            ) : (
              <>
                <Button
                  type="button"
                  variant="brand"
                  disabled={saving || premiumRequested}
                  onClick={() => void select("premium")}
                >
                  {premiumRequested ? "Selected" : saving ? "Saving..." : "Choose premium"}
                </Button>
                <p className="text-[12px] text-sub">
                  Billing opens at launch — choosing now reserves premium and activates it then. No
                  charges today.
                </p>
              </>
            )}
          </Card>
        </div>
      )}
    </div>
  );
}
