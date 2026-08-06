"use client";

/**
 * M5 Task 15: the four wizard step components (Goal / Categories / Areas /
 * Schedule & budget) plus the shared draft shape + targeting constants they
 * all read and write. campaign-wizard.tsx owns step state/nav and imports
 * from here — Task 16 adds Creatives/Review & pay alongside these, so the
 * shared types stay here rather than duplicated.
 */

import { Button, Skeleton, cn } from "@agri/ui";
import { useState, type ReactNode } from "react";

// Mirrors modules/ads/service.py SLOT_KEYS (M2 milk banner surfaces).
export const BANNER_SLOTS = [
  { key: "milk_global_header", label: "Header banner (every page)" },
  { key: "milk_home_hero", label: "Home page hero" },
  { key: "milk_category_banner", label: "Category page banner" },
  { key: "milk_search_inline", label: "Search results banner" },
  { key: "milk_profile_footer", label: "Profile page footer" },
] as const;
export const SPONSORED_SLOT = "milk_sponsored_listing";
// QuoteIn.slot_keys is Field(min_length=1, max_length=3).
export const MAX_BANNER_SLOTS = 3;
// M5 v1: town-tier targeting is Tamil Nadu only (LGD state code 33).
export const STATE_TN_LGD = 33;
export const SERVES_PRESETS = [10000, 25000, 50000, 100000] as const;
// Mirrors modules/ads/pricing.py MIN_CPM_SERVES.
export const MIN_CPM_SERVES = 1000;

const TIER_LABELS: Record<number, string> = {
  1: "Big cities (T1)",
  2: "Large towns (T2)",
  3: "Towns (T3)",
  4: "Small towns (T4)",
  5: "Villages (T5)",
};

export type AreaMode = "all" | "pincodes" | "tiers";
export type GoalMode = "banner" | "sponsored" | null;

export interface WizardDraft {
  name: string;
  goalMode: GoalMode;
  slotKeys: string[];
  allCategories: boolean;
  categories: string[];
  areaMode: AreaMode;
  pincodes: string[];
  tiers: number[];
  flightStart: string;
  flightEnd: string;
  servesTotal: number | null;
  dailyServeCap: number | null;
}

export interface CategoryOption {
  slug: string;
  label: string;
}

export function pricingModelFor(slotKeys: string[]): "cpm" | "flat_weekly" {
  return slotKeys.includes(SPONSORED_SLOT) ? "flat_weekly" : "cpm";
}

interface StepProps {
  draft: WizardDraft;
  onChange: (patch: Partial<WizardDraft>) => void;
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

function RadioCard({
  selected,
  onSelect,
  title,
  subtitle,
  children,
}: {
  selected: boolean;
  onSelect: () => void;
  title: string;
  subtitle?: string;
  children?: ReactNode;
}) {
  return (
    <div
      role="radio"
      aria-checked={selected}
      tabIndex={0}
      onClick={onSelect}
      onKeyDown={(e) => {
        if (e.key === "Enter" || e.key === " ") {
          e.preventDefault();
          onSelect();
        }
      }}
      className={cn(
        "cursor-pointer rounded-card border-2 p-3",
        selected ? "border-brand bg-brand-soft" : "border-line bg-card",
      )}
    >
      <p className="text-[13px] font-extrabold text-ink">{title}</p>
      {subtitle ? <p className="text-[12px] text-sub">{subtitle}</p> : null}
      {children}
    </div>
  );
}

export function GoalStep({ draft, onChange }: StepProps) {
  const toggleBannerSlot = (key: string) => {
    if (draft.slotKeys.includes(key)) {
      onChange({ slotKeys: draft.slotKeys.filter((k) => k !== key) });
      return;
    }
    if (draft.slotKeys.length >= MAX_BANNER_SLOTS) return;
    onChange({ slotKeys: [...draft.slotKeys, key] });
  };

  return (
    <div className="space-y-4">
      <label className={LABEL}>
        Campaign name
        <input
          className={FIELD}
          value={draft.name}
          maxLength={80}
          onChange={(e) => onChange({ name: e.target.value })}
          placeholder="e.g. Diwali milk offer"
        />
      </label>

      <div className="space-y-2" role="radiogroup" aria-label="Ad goal">
        <RadioCard
          selected={draft.goalMode === "banner"}
          onSelect={() => onChange({ goalMode: "banner", slotKeys: [] })}
          title="Banner ads"
          subtitle="Image banners shown across the milk site"
        >
          {draft.goalMode === "banner" ? (
            <div className="mt-2 space-y-1 border-t border-line pt-2" onClick={(e) => e.stopPropagation()}>
              <p className="text-[12px] text-sub">Choose up to {MAX_BANNER_SLOTS} placements</p>
              {BANNER_SLOTS.map((slot) => (
                <label
                  key={slot.key}
                  className="flex min-h-[44px] min-w-0 items-center gap-2 text-[13px] text-ink"
                >
                  <input
                    type="checkbox"
                    className="min-h-[20px] min-w-[20px] flex-none"
                    checked={draft.slotKeys.includes(slot.key)}
                    disabled={
                      !draft.slotKeys.includes(slot.key) && draft.slotKeys.length >= MAX_BANNER_SLOTS
                    }
                    onChange={() => toggleBannerSlot(slot.key)}
                  />
                  <span className="min-w-0 break-words">{slot.label}</span>
                </label>
              ))}
            </div>
          ) : null}
        </RadioCard>
        <RadioCard
          selected={draft.goalMode === "sponsored"}
          onSelect={() => onChange({ goalMode: "sponsored", slotKeys: [SPONSORED_SLOT] })}
          title="Sponsored listing"
          subtitle="Your listing highlighted in search results"
        />
      </div>
    </div>
  );
}

export function CategoriesStep({
  draft,
  onChange,
  options,
}: StepProps & { options: CategoryOption[] }) {
  const toggleCategory = (slug: string) => {
    const has = draft.categories.includes(slug);
    onChange({
      categories: has ? draft.categories.filter((c) => c !== slug) : [...draft.categories, slug],
    });
  };

  return (
    <div className="space-y-3">
      <label className="flex min-h-[44px] min-w-0 items-center gap-2 text-[13px] font-semibold text-ink">
        <input
          type="checkbox"
          className="min-h-[20px] min-w-[20px] flex-none"
          checked={draft.allCategories}
          onChange={(e) =>
            onChange({
              allCategories: e.target.checked,
              categories: e.target.checked ? [] : draft.categories,
            })
          }
        />
        <span className="min-w-0 break-words">All categories</span>
      </label>
      {!draft.allCategories ? (
        options.length === 0 ? (
          <Skeleton width="100%" height="120px" />
        ) : (
          <div className="grid grid-cols-2 gap-2 sm:grid-cols-3">
            {options.map((option) => (
              <label
                key={option.slug}
                className="flex min-h-[44px] min-w-0 items-center gap-2 break-words rounded-btn border border-line bg-card px-2 text-[13px] text-ink"
              >
                <input
                  type="checkbox"
                  className="min-h-[20px] min-w-[20px] flex-none"
                  checked={draft.categories.includes(option.slug)}
                  onChange={() => toggleCategory(option.slug)}
                />
                <span className="min-w-0 break-words">{option.label}</span>
              </label>
            ))}
          </div>
        )
      ) : null}
    </div>
  );
}

const PINCODE_RE = /^\d{6}$/;
const MAX_PINCODES = 50;

export function AreasStep({ draft, onChange }: StepProps) {
  const [pincodeInput, setPincodeInput] = useState("");
  const [pincodeError, setPincodeError] = useState<string | null>(null);

  const addPincode = () => {
    const value = pincodeInput.trim();
    if (!PINCODE_RE.test(value)) {
      setPincodeError("Enter a 6-digit pincode.");
      return;
    }
    if (draft.pincodes.includes(value)) {
      setPincodeError("That pincode is already added.");
      return;
    }
    if (draft.pincodes.length >= MAX_PINCODES) {
      setPincodeError(`You can add up to ${MAX_PINCODES} pincodes.`);
      return;
    }
    onChange({ pincodes: [...draft.pincodes, value] });
    setPincodeInput("");
    setPincodeError(null);
  };

  const removePincode = (value: string) => {
    onChange({ pincodes: draft.pincodes.filter((p) => p !== value) });
  };

  const toggleTier = (tier: number) => {
    const has = draft.tiers.includes(tier);
    onChange({
      tiers: has ? draft.tiers.filter((t) => t !== tier) : [...draft.tiers, tier].sort((a, b) => a - b),
    });
  };

  return (
    <div className="space-y-2" role="radiogroup" aria-label="Area targeting">
      <RadioCard selected={draft.areaMode === "all"} onSelect={() => onChange({ areaMode: "all" })} title="All of India" />

      <RadioCard
        selected={draft.areaMode === "pincodes"}
        onSelect={() => onChange({ areaMode: "pincodes" })}
        title="Specific pincodes"
      >
        {draft.areaMode === "pincodes" ? (
          <div className="mt-2 space-y-2 border-t border-line pt-2" onClick={(e) => e.stopPropagation()}>
            <div className="flex gap-2">
              <input
                type="text"
                inputMode="numeric"
                maxLength={6}
                pattern="[0-9]*"
                className={cn(FIELD, "mt-0 flex-1")}
                value={pincodeInput}
                onChange={(e) => {
                  setPincodeInput(e.target.value.replace(/\D/g, ""));
                  setPincodeError(null);
                }}
                placeholder="6-digit pincode"
              />
              <Button type="button" variant="ghost" className="min-h-[44px] flex-none px-4" onClick={addPincode}>
                Add
              </Button>
            </div>
            {pincodeError ? <AlertNotice>{pincodeError}</AlertNotice> : null}
            {draft.pincodes.length > 0 ? (
              <ul className="flex flex-wrap gap-2">
                {draft.pincodes.map((p) => (
                  <li key={p}>
                    <button
                      type="button"
                      onClick={() => removePincode(p)}
                      className="inline-flex min-h-[44px] items-center gap-1 rounded-pill bg-ghost px-3 text-[12px] font-semibold text-ink"
                    >
                      {p} <span aria-hidden="true">×</span>
                      <span className="sr-only">Remove {p}</span>
                    </button>
                  </li>
                ))}
              </ul>
            ) : null}
            <p className="text-[12px] text-sub">
              {draft.pincodes.length}/{MAX_PINCODES} added
            </p>
          </div>
        ) : null}
      </RadioCard>

      <RadioCard
        selected={draft.areaMode === "tiers"}
        onSelect={() => onChange({ areaMode: "tiers" })}
        title="By town tier"
        subtitle="Tamil Nadu only in this release"
      >
        {draft.areaMode === "tiers" ? (
          <div className="mt-2 space-y-1 border-t border-line pt-2" onClick={(e) => e.stopPropagation()}>
            {[1, 2, 3, 4, 5].map((tier) => (
              <label key={tier} className="flex min-h-[44px] min-w-0 items-center gap-2 text-[13px] text-ink">
                <input
                  type="checkbox"
                  className="min-h-[20px] min-w-[20px] flex-none"
                  checked={draft.tiers.includes(tier)}
                  onChange={() => toggleTier(tier)}
                />
                <span className="min-w-0 break-words">{TIER_LABELS[tier]}</span>
              </label>
            ))}
          </div>
        ) : null}
      </RadioCard>
    </div>
  );
}

export function ScheduleStep({ draft, onChange }: StepProps) {
  const model = pricingModelFor(draft.slotKeys);
  const dateError = Boolean(draft.flightStart && draft.flightEnd && draft.flightStart >= draft.flightEnd);
  const weeks =
    model === "flat_weekly" && draft.flightStart && draft.flightEnd && !dateError
      ? Math.max(
          1,
          Math.ceil(
            (new Date(draft.flightEnd).getTime() - new Date(draft.flightStart).getTime()) /
              (7 * 24 * 60 * 60 * 1000),
          ),
        )
      : null;
  const customServes =
    draft.servesTotal !== null && !(SERVES_PRESETS as readonly number[]).includes(draft.servesTotal)
      ? draft.servesTotal
      : "";

  return (
    <div className="space-y-4">
      <div className="grid grid-cols-1 gap-3 sm:grid-cols-2">
        <label className={LABEL}>
          Start date
          <input
            type="date"
            className={FIELD}
            value={draft.flightStart}
            onChange={(e) => onChange({ flightStart: e.target.value })}
          />
        </label>
        <label className={LABEL}>
          End date
          <input
            type="date"
            className={FIELD}
            value={draft.flightEnd}
            onChange={(e) => onChange({ flightEnd: e.target.value })}
          />
        </label>
      </div>
      {dateError ? <AlertNotice>The end date must be after the start date.</AlertNotice> : null}

      {model === "cpm" ? (
        <div className="space-y-2">
          <p className={LABEL}>Ad views to buy</p>
          <div className="flex flex-wrap gap-2" role="group" aria-label="Ad view presets">
            {SERVES_PRESETS.map((preset) => (
              <button
                key={preset}
                type="button"
                onClick={() => onChange({ servesTotal: preset })}
                className={cn(
                  "min-h-[44px] rounded-pill px-4 text-[13px] font-semibold",
                  draft.servesTotal === preset ? "bg-ink text-card" : "bg-line text-ink",
                )}
              >
                {(preset / 1000).toLocaleString("en-IN")}k
              </button>
            ))}
          </div>
          <label className={LABEL}>
            Or a custom number (min {MIN_CPM_SERVES.toLocaleString("en-IN")})
            <input
              type="number"
              min={MIN_CPM_SERVES}
              step={100}
              className={FIELD}
              value={customServes}
              onChange={(e) => {
                const value = e.target.value === "" ? null : Number(e.target.value);
                onChange({ servesTotal: value });
              }}
              placeholder="e.g. 15000"
            />
          </label>
          <label className={LABEL}>
            Daily view cap (optional)
            <input
              type="number"
              min={100}
              step={100}
              className={FIELD}
              value={draft.dailyServeCap ?? ""}
              onChange={(e) =>
                onChange({ dailyServeCap: e.target.value === "" ? null : Number(e.target.value) })
              }
              placeholder="No daily limit"
            />
          </label>
        </div>
      ) : (
        <div className="rounded-card border border-line bg-ghost p-3 text-[13px] text-ink">
          Sponsored listing runs for <span className="font-extrabold">{weeks ?? "—"}</span> week
          {weeks === 1 ? "" : "s"}, priced weekly.
        </div>
      )}
    </div>
  );
}
