"use client";

/**
 * M5 Task 15: campaign wizard shell — step state/nav + the live
 * server-priced quote rail. Steps 1-4 (Goal/Categories/Areas/Schedule &
 * budget, in wizard-steps.tsx) are built here; steps 5-6 (Creatives, Review
 * & pay) are Task 16's job and render a placeholder for now so the
 * stepper/nav contract is already final.
 *
 * "Next" from step 4 persists the draft server-side — POST the first time,
 * PATCH afterwards — so Task 16's creative upload has a campaign id to
 * attach to (backend/core/modules/ads/selfserve_router.py create_campaign /
 * patch_campaign). Quote failures are surfaced inline but never block
 * navigation before Review & pay; only the wizard's OWN client-side
 * validation (dates, required choices) blocks "Next".
 */

import { Button, Card, Skeleton, cn } from "@agri/ui";
import { useEffect, useMemo, useRef, useState, type ReactNode } from "react";

import { ApiError, getJson, patchJson, postJson } from "@/lib/api";

import {
  AreasStep,
  CategoriesStep,
  GoalStep,
  MIN_CPM_SERVES,
  ScheduleStep,
  STATE_TN_LGD,
  pricingModelFor,
  type CategoryOption,
  type WizardDraft,
} from "./wizard-steps";

export const STEPS = [
  "Goal",
  "Categories",
  "Areas",
  "Schedule & budget",
  "Creatives",
  "Review & pay",
] as const;

function todayIso(offsetDays: number): string {
  const d = new Date();
  d.setUTCDate(d.getUTCDate() + offsetDays);
  return d.toISOString().slice(0, 10);
}

function initialDraft(): WizardDraft {
  return {
    name: "",
    goalMode: null,
    slotKeys: [],
    allCategories: true,
    categories: [],
    areaMode: "all",
    pincodes: [],
    tiers: [],
    flightStart: todayIso(1),
    flightEnd: todayIso(15),
    servesTotal: null,
    dailyServeCap: null,
  };
}

function geoTargetWire(draft: WizardDraft): Record<string, unknown> {
  if (draft.areaMode === "pincodes") return { pincodes: draft.pincodes };
  if (draft.areaMode === "tiers") return { state: STATE_TN_LGD, tiers: draft.tiers };
  return {};
}

interface QuoteBody {
  slot_keys: string[];
  geo_target: Record<string, unknown>;
  categories: string[];
  flight_start: string;
  flight_end: string;
  serves_total: number | null;
}

function quoteBody(draft: WizardDraft): QuoteBody | null {
  if (draft.slotKeys.length === 0) return null;
  if (!draft.flightStart || !draft.flightEnd) return null;
  return {
    slot_keys: draft.slotKeys,
    geo_target: geoTargetWire(draft),
    categories: draft.allCategories ? [] : draft.categories,
    flight_start: draft.flightStart,
    flight_end: draft.flightEnd,
    serves_total: pricingModelFor(draft.slotKeys) === "cpm" ? draft.servesTotal : null,
  };
}

interface QuoteLine {
  label: string;
  amount_paise: number;
}

interface QuoteOut {
  pricing_model: string;
  tier: number;
  multiplier_bp: number;
  serves_total: number | null;
  weeks: number | null;
  lines: QuoteLine[];
  subtotal_paise: number;
  gst_paise: number;
  total_paise: number;
  rate_card_version: number;
}

function rupees(paise: number): string {
  return `₹${(paise / 100).toLocaleString("en-IN")}`;
}

// RateCardError codes (modules/ads/pricing.py) + the plain-string 422/409
// details selfserve_router.py raises on top of them.
const API_ERROR_COPY: Record<string, string> = {
  mixed_pricing_models: "Banner ads and sponsored listings can't be priced together.",
  serves_required: "Choose how many ad views to buy (next step) to see pricing.",
  serves_too_small: `Choose at least ${MIN_CPM_SERVES.toLocaleString("en-IN")} ad views.`,
  no_rate_card: "Pricing isn't set up yet — please try again shortly.",
  unknown_slot_key: "That ad slot isn't available — please restart this campaign.",
  categories_in_geo_target: "Something went wrong with area targeting — please restart this campaign.",
  invalid_flight_range: "The end date must be after the start date.",
  not_editable: "This campaign can no longer be edited here.",
};

function friendlyApiError(err: unknown, fallback: string): string {
  if (err instanceof ApiError) {
    return API_ERROR_COPY[err.detail] ?? fallback;
  }
  return fallback;
}

function AlertNotice({ children }: { children: ReactNode }) {
  return (
    <div className="rounded-card border border-alert-line bg-alert-bg p-3 text-[13px] font-semibold text-ink">
      {children}
    </div>
  );
}

function QuoteRail({ draft }: { draft: WizardDraft }) {
  const [quote, setQuote] = useState<QuoteOut | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);
  const requestId = useRef(0);

  const bodyKey = useMemo(() => {
    const body = quoteBody(draft);
    return body ? JSON.stringify(body) : null;
  }, [draft]);

  useEffect(() => {
    if (!bodyKey) {
      setQuote(null);
      setError(null);
      setLoading(false);
      return;
    }
    const id = ++requestId.current;
    setLoading(true);
    const timer = setTimeout(() => {
      void (async () => {
        try {
          const body = await postJson("/api/ads/my/quote", JSON.parse(bodyKey) as QuoteBody);
          if (requestId.current !== id) return;
          setQuote(body as unknown as QuoteOut);
          setError(null);
        } catch (err) {
          if (requestId.current !== id) return;
          setQuote(null);
          setError(friendlyApiError(err, "Could not price this campaign — check your choices above."));
        } finally {
          if (requestId.current === id) setLoading(false);
        }
      })();
    }, 400);
    return () => clearTimeout(timer);
  }, [bodyKey]);

  if (!bodyKey) return null;

  return (
    <Card className="space-y-2 p-4">
      <p className="text-[13px] font-extrabold text-ink">Estimated price</p>
      {loading && !quote ? <Skeleton width="100%" height="72px" /> : null}
      {error ? <AlertNotice>{error}</AlertNotice> : null}
      {quote ? (
        <div className="space-y-2">
          <ul className="space-y-1">
            {quote.lines.map((line, i) => (
              <li key={`${line.label}-${i}`} className="flex gap-2 text-[13px] text-ink">
                <span className="min-w-0 flex-1 break-words">{line.label}</span>
                <span className="flex-none font-semibold">{rupees(line.amount_paise)}</span>
              </li>
            ))}
          </ul>
          <div className="space-y-0.5 border-t border-line pt-2 text-[13px] text-ink">
            <div className="flex gap-2">
              <span className="min-w-0 flex-1 break-words text-sub">Subtotal</span>
              <span className="flex-none">{rupees(quote.subtotal_paise)}</span>
            </div>
            <div className="flex gap-2">
              <span className="min-w-0 flex-1 break-words text-sub">GST</span>
              <span className="flex-none">{rupees(quote.gst_paise)}</span>
            </div>
            <div className="flex gap-2 text-[14px] font-extrabold">
              <span className="min-w-0 flex-1 break-words">Total</span>
              <span className="flex-none">{rupees(quote.total_paise)}</span>
            </div>
          </div>
        </div>
      ) : null}
    </Card>
  );
}

interface CampaignWizardProps {
  businessId: string;
  onDone: () => void;
}

export function CampaignWizard({ businessId, onDone }: CampaignWizardProps) {
  const [stepIndex, setStepIndex] = useState(0);
  const [draft, setDraft] = useState<WizardDraft>(initialDraft);
  const [campaignId, setCampaignId] = useState<string | null>(null);
  const [categoryOptions, setCategoryOptions] = useState<CategoryOption[]>([]);
  const [stepError, setStepError] = useState<string | null>(null);
  const [saving, setSaving] = useState(false);

  useEffect(() => {
    let cancelled = false;
    void (async () => {
      try {
        const body = await getJson("/api/catalog/verticals/milk/schema");
        if (cancelled) return;
        const fields =
          (body.fields as
            | Array<{
                key: string;
                options?: string[];
                option_meta?: Record<string, { label: Record<string, string> }>;
              }>
            | undefined) ?? [];
        const categoryField = fields.find((f) => f.key === "category");
        const options: CategoryOption[] = (categoryField?.options ?? []).map((slug) => ({
          slug,
          label: categoryField?.option_meta?.[slug]?.label.en ?? slug,
        }));
        setCategoryOptions(options);
      } catch {
        if (!cancelled) setCategoryOptions([]);
      }
    })();
    return () => {
      cancelled = true;
    };
  }, []);

  const updateDraft = (patch: Partial<WizardDraft>) => {
    setDraft((prev) => ({ ...prev, ...patch }));
    setStepError(null);
  };

  const validateStep = (): string | null => {
    switch (stepIndex) {
      case 0:
        if (!draft.name.trim()) return "Give this campaign a name.";
        if (draft.goalMode === null) return "Choose banner ads or a sponsored listing.";
        if (draft.goalMode === "banner" && draft.slotKeys.length === 0) {
          return "Choose at least one banner placement.";
        }
        return null;
      case 1:
        return null; // "All categories" is a valid choice on its own
      case 2:
        if (draft.areaMode === "pincodes" && draft.pincodes.length === 0) {
          return "Add at least one pincode.";
        }
        if (draft.areaMode === "tiers" && draft.tiers.length === 0) {
          return "Choose at least one town tier.";
        }
        return null;
      case 3:
        if (!draft.flightStart || !draft.flightEnd) return "Choose a start and end date.";
        if (draft.flightStart >= draft.flightEnd) return "The end date must be after the start date.";
        if (
          pricingModelFor(draft.slotKeys) === "cpm" &&
          (draft.servesTotal === null || draft.servesTotal < MIN_CPM_SERVES)
        ) {
          return `Choose at least ${MIN_CPM_SERVES.toLocaleString("en-IN")} ad views.`;
        }
        return null;
      default:
        return null;
    }
  };

  const persistDraft = async (): Promise<boolean> => {
    const body = quoteBody(draft);
    if (!body) return false;
    setSaving(true);
    setStepError(null);
    try {
      if (campaignId === null) {
        const created = await postJson("/api/ads/my/campaigns", {
          ...body,
          business_id: businessId,
          name: draft.name.trim(),
          daily_serve_cap: draft.dailyServeCap,
        });
        setCampaignId(String(created.id));
      } else {
        await patchJson(`/api/ads/my/campaigns/${campaignId}`, {
          name: draft.name.trim(),
          geo_target: body.geo_target,
          categories: body.categories,
          flight_start: body.flight_start,
          flight_end: body.flight_end,
          serves_total: body.serves_total,
          daily_serve_cap: draft.dailyServeCap,
        });
      }
      return true;
    } catch (err) {
      setStepError(friendlyApiError(err, "Could not save this campaign — please try again."));
      return false;
    } finally {
      setSaving(false);
    }
  };

  const handleNext = async () => {
    const validationError = validateStep();
    if (validationError) {
      setStepError(validationError);
      return;
    }
    if (stepIndex === 3) {
      const ok = await persistDraft();
      if (!ok) return;
    }
    if (stepIndex < STEPS.length - 1) setStepIndex((s) => s + 1);
  };

  const handleBack = () => {
    setStepError(null);
    if (stepIndex > 0) setStepIndex((s) => s - 1);
  };

  return (
    <Card className="space-y-4 break-words p-4">
      <div className="flex flex-wrap items-center justify-between gap-2">
        <div className="flex flex-wrap gap-2" role="group" aria-label="Campaign steps">
          {STEPS.map((label, i) => (
            <span
              key={label}
              aria-current={i === stepIndex ? "step" : undefined}
              className={cn(
                "min-h-[32px] rounded-pill px-3 py-1 text-[12px] font-semibold",
                i === stepIndex
                  ? "bg-ink text-card"
                  : i < stepIndex
                    ? "bg-verified-bg text-verified-fg"
                    : "bg-line text-sub",
              )}
            >
              {i + 1}. {label}
            </span>
          ))}
        </div>
        <Button type="button" variant="ghost" className="min-h-[44px] flex-none px-4" onClick={onDone}>
          Close
        </Button>
      </div>

      {stepIndex === 0 ? <GoalStep draft={draft} onChange={updateDraft} /> : null}
      {stepIndex === 1 ? (
        <CategoriesStep draft={draft} onChange={updateDraft} options={categoryOptions} />
      ) : null}
      {stepIndex === 2 ? <AreasStep draft={draft} onChange={updateDraft} /> : null}
      {stepIndex === 3 ? <ScheduleStep draft={draft} onChange={updateDraft} /> : null}
      {stepIndex >= 4 ? (
        <div className="space-y-2 rounded-card border border-line bg-ghost p-4 text-[13px] text-sub">
          <p className="font-semibold text-ink">{STEPS[stepIndex]}</p>
          <p>Coming in the next step of this build.</p>
          {campaignId ? (
            <p>Your draft campaign has been saved — come back to finish adding creatives and pay.</p>
          ) : null}
        </div>
      ) : null}

      {stepIndex >= 1 ? <QuoteRail draft={draft} /> : null}

      {stepError ? <AlertNotice>{stepError}</AlertNotice> : null}

      <div className="flex gap-2">
        <Button
          type="button"
          variant="ghost"
          className="min-h-[44px] min-w-0 max-w-[240px] break-words"
          disabled={stepIndex === 0}
          onClick={handleBack}
        >
          Back
        </Button>
        {stepIndex < 4 ? (
          <Button
            type="button"
            variant="brand"
            className="min-h-[44px] min-w-0 max-w-[240px] break-words"
            disabled={saving}
            onClick={() => void handleNext()}
          >
            {saving ? "Saving..." : stepIndex === 3 ? "Save & continue" : "Next"}
          </Button>
        ) : (
          <Button
            type="button"
            variant="brand"
            className="min-h-[44px] min-w-0 max-w-[240px] break-words"
            onClick={onDone}
          >
            Back to campaigns
          </Button>
        )}
      </div>
    </Card>
  );
}
