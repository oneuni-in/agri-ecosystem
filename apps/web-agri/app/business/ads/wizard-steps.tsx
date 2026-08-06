"use client";

/**
 * M5 Task 15: the four wizard step components (Goal / Categories / Areas /
 * Schedule & budget) plus the shared draft shape + targeting constants they
 * all read and write. campaign-wizard.tsx owns step state/nav and imports
 * from here.
 *
 * M5 Task 16 adds CreativesStep (multipart upload/edit against
 * backend/core/modules/ads/selfserve_router.py's creatives routes) and
 * ReviewPayStep (server-truth quote GET + checkout-request -> ad-orders ->
 * Razorpay redirect) alongside the four above.
 */

import { AdImage, Button, Card, Skeleton, cn } from "@agri/ui";
import { useEffect, useState, type ReactNode } from "react";

import { ApiError, getJson, postJson } from "@/lib/api";

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

export const TIER_LABELS: Record<number, string> = {
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
        "min-h-[44px] cursor-pointer rounded-card border-2 p-3",
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

// ---------------------------------------------------------------------------
// M5 Task 16: Creatives step
//
// Uploads/edits go straight to the /api/ads/my proxy as raw multipart
// fetches (claim-form.tsx pattern: FormData + fetch, content-type left
// unset so the browser sets the multipart boundary) - postJson/patchJson
// (lib/api.ts) only ever send JSON, so they can't be reused here.

export const MAX_CREATIVES = 5;
const CREATIVE_ACCEPT = "image/jpeg,image/png,image/webp";
const HTTPS_RE = /^https:\/\//;

interface CreativeCopyBlock {
  title: string;
  body: string;
}

export interface CreativeOut {
  id: string;
  copy: Record<string, CreativeCopyBlock>;
  media_urls: string[];
  target_url: string;
  moderation_status: string;
}

// selfserve_router.py's creative routes collapse every validation failure to
// one of these plain-string 422/409 codes (see _parse_copy_json/
// _validated_target_url/_upload_creative_image's MediaError passthrough).
const CREATIVE_ERROR_COPY: Record<string, string> = {
  invalid_copy_json:
    "Check your ad text — English needs a title and body; Tamil/Hindi need both or neither.",
  invalid_target_url: "Enter a valid https:// link.",
  too_large: "That image is too large (max 5MB).",
  unsupported_type: "Use a JPEG, PNG, or WEBP image.",
  empty_file: "That file looks empty — choose another image.",
  creative_limit: `You've reached the limit of ${MAX_CREATIVES} creatives for this campaign.`,
  not_editable: "This campaign can no longer be edited here.",
};

function friendlyCreativeError(detail: string | undefined): string {
  return (detail && CREATIVE_ERROR_COPY[detail]) || "Could not save this creative — please try again.";
}

function ModerationChip({ status }: { status: string }) {
  const classes =
    status === "approved"
      ? "bg-verified-bg text-verified-fg"
      : status === "rejected"
        ? "bg-alert-bg text-ink"
        : "bg-sponsored-bg text-sponsored-fg";
  return (
    <span
      className={cn(
        "inline-flex flex-none items-center rounded-pill px-[9px] py-[3px] text-[11px] font-extrabold",
        classes,
      )}
    >
      {status}
    </span>
  );
}

function CreativeForm({
  campaignId,
  creative,
  onSaved,
  onCancel,
}: {
  campaignId: string;
  creative?: CreativeOut;
  onSaved: (creative: CreativeOut) => void;
  onCancel: () => void;
}) {
  const isEdit = Boolean(creative);
  const [enTitle, setEnTitle] = useState(creative?.copy.en?.title ?? "");
  const [enBody, setEnBody] = useState(creative?.copy.en?.body ?? "");
  const [taTitle, setTaTitle] = useState(creative?.copy.ta?.title ?? "");
  const [taBody, setTaBody] = useState(creative?.copy.ta?.body ?? "");
  const [hiTitle, setHiTitle] = useState(creative?.copy.hi?.title ?? "");
  const [hiBody, setHiBody] = useState(creative?.copy.hi?.body ?? "");
  const [targetUrl, setTargetUrl] = useState(creative?.target_url ?? "");
  const [file, setFile] = useState<File | null>(null);
  const [previewUrl, setPreviewUrl] = useState<string | null>(null);
  const [submitting, setSubmitting] = useState(false);
  const [formError, setFormError] = useState<string | null>(null);

  // Object URLs are only ever revoked on unmount/replace here — never kept
  // beyond the form's lifetime.
  useEffect(() => {
    return () => {
      if (previewUrl) URL.revokeObjectURL(previewUrl);
    };
  }, [previewUrl]);

  const handleFile = (picked: File | null) => {
    setPreviewUrl((prev) => {
      if (prev) URL.revokeObjectURL(prev);
      return picked ? URL.createObjectURL(picked) : null;
    });
    setFile(picked);
  };

  const submit = async (event: React.FormEvent) => {
    event.preventDefault();
    if (!enTitle.trim() || !enBody.trim()) {
      setFormError("English title and body are required.");
      return;
    }
    if ((taTitle.trim() || taBody.trim()) && !(taTitle.trim() && taBody.trim())) {
      setFormError("Tamil needs both a title and a body, or leave both blank.");
      return;
    }
    if ((hiTitle.trim() || hiBody.trim()) && !(hiTitle.trim() && hiBody.trim())) {
      setFormError("Hindi needs both a title and a body, or leave both blank.");
      return;
    }
    if (!HTTPS_RE.test(targetUrl.trim())) {
      setFormError("Enter a valid https:// link.");
      return;
    }

    const copy: Record<string, CreativeCopyBlock> = {
      en: { title: enTitle.trim(), body: enBody.trim() },
    };
    if (taTitle.trim()) copy.ta = { title: taTitle.trim(), body: taBody.trim() };
    if (hiTitle.trim()) copy.hi = { title: hiTitle.trim(), body: hiBody.trim() };

    const form = new FormData();
    form.append("copy_json", JSON.stringify(copy));
    form.append("target_url", targetUrl.trim());
    if (file) form.append("file", file);

    setSubmitting(true);
    setFormError(null);
    try {
      const res = await fetch(
        isEdit
          ? `/api/ads/my/creatives/${creative!.id}`
          : `/api/ads/my/campaigns/${campaignId}/creatives`,
        { method: isEdit ? "PATCH" : "POST", body: form },
      );
      const body = (await res.json().catch(() => null)) as (CreativeOut & { detail?: string }) | null;
      if (!res.ok) {
        setFormError(friendlyCreativeError(body?.detail));
        setSubmitting(false);
        return;
      }
      onSaved(body as CreativeOut);
    } catch {
      setFormError("Could not save this creative — please try again.");
      setSubmitting(false);
    }
  };

  return (
    <form className="space-y-3 rounded-card border border-line bg-ghost p-3" onSubmit={(e) => void submit(e)}>
      {isEdit ? <AlertNotice>Editing sends this ad for review again.</AlertNotice> : null}
      <label className={LABEL}>
        Image (optional)
        <input
          type="file"
          accept={CREATIVE_ACCEPT}
          className={FIELD}
          onChange={(e) => handleFile(e.target.files?.[0] ?? null)}
        />
      </label>
      {previewUrl ? (
        // eslint-disable-next-line @next/next/no-img-element -- local blob: preview, never a remote/optimizable URL
        <img src={previewUrl} alt="" className="h-24 w-full rounded-btn object-cover" />
      ) : isEdit && creative!.media_urls[0] ? (
        <AdImage src={creative!.media_urls[0]} alt="" className="h-24 w-full rounded-btn" />
      ) : null}
      <div className="grid gap-2 sm:grid-cols-2">
        <label className={LABEL}>
          Title (English)
          <input className={FIELD} value={enTitle} onChange={(e) => setEnTitle(e.target.value)} />
        </label>
        <label className={LABEL}>
          Body (English)
          <input className={FIELD} value={enBody} onChange={(e) => setEnBody(e.target.value)} />
        </label>
        <label className={LABEL}>
          Title (Tamil, optional)
          <input className={FIELD} value={taTitle} onChange={(e) => setTaTitle(e.target.value)} />
        </label>
        <label className={LABEL}>
          Body (Tamil, optional)
          <input className={FIELD} value={taBody} onChange={(e) => setTaBody(e.target.value)} />
        </label>
        <label className={LABEL}>
          Title (Hindi, optional)
          <input className={FIELD} value={hiTitle} onChange={(e) => setHiTitle(e.target.value)} />
        </label>
        <label className={LABEL}>
          Body (Hindi, optional)
          <input className={FIELD} value={hiBody} onChange={(e) => setHiBody(e.target.value)} />
        </label>
      </div>
      <label className={LABEL}>
        Target URL
        <input
          type="url"
          className={FIELD}
          value={targetUrl}
          onChange={(e) => setTargetUrl(e.target.value)}
          placeholder="https://example.com/offer"
        />
      </label>
      {formError ? <AlertNotice>{formError}</AlertNotice> : null}
      <div className="flex gap-2">
        <Button type="submit" variant="brand" disabled={submitting} className="min-h-[44px] min-w-0 max-w-[200px] break-words">
          {submitting ? "Saving..." : isEdit ? "Save changes" : "Add creative"}
        </Button>
        <Button type="button" variant="ghost" disabled={submitting} className="min-h-[44px] min-w-0 max-w-[160px] break-words" onClick={onCancel}>
          Cancel
        </Button>
      </div>
    </form>
  );
}

export function CreativesStep({ campaignId }: { campaignId: string }) {
  const [creatives, setCreatives] = useState<CreativeOut[] | null>(null);
  const [loadError, setLoadError] = useState(false);
  const [editingId, setEditingId] = useState<string | null>(null);
  const [addingNew, setAddingNew] = useState(false);

  useEffect(() => {
    let cancelled = false;
    void (async () => {
      try {
        const body = await getJson(`/api/ads/my/campaigns/${campaignId}`);
        if (cancelled) return;
        setCreatives((body.creatives as CreativeOut[] | undefined) ?? []);
        setLoadError(false);
      } catch {
        if (!cancelled) setLoadError(true);
      }
    })();
    return () => {
      cancelled = true;
    };
  }, [campaignId]);

  const atLimit = (creatives?.length ?? 0) >= MAX_CREATIVES;

  return (
    <div className="space-y-3">
      <p className="text-[13px] text-sub">
        Add up to {MAX_CREATIVES} creatives — the image, headline, and body text shown in your ad.
        English text is required; Tamil and Hindi are optional. New creatives start pending review.
      </p>

      {loadError ? <AlertNotice>Could not load your creatives — please try again.</AlertNotice> : null}
      {creatives === null && !loadError ? <Skeleton width="100%" height="120px" /> : null}

      {creatives && creatives.length > 0 ? (
        <ul className="space-y-2">
          {creatives.map((c) => (
            <li key={c.id}>
              <Card className="space-y-2 break-words p-3">
                {editingId === c.id ? (
                  <CreativeForm
                    campaignId={campaignId}
                    creative={c}
                    onSaved={(updated) => {
                      setCreatives((prev) => prev?.map((x) => (x.id === updated.id ? updated : x)) ?? null);
                      setEditingId(null);
                    }}
                    onCancel={() => setEditingId(null)}
                  />
                ) : (
                  <>
                    <div className="flex flex-wrap items-center justify-between gap-2">
                      <span className="min-w-0 break-words text-[13px] font-extrabold text-ink">
                        {c.copy.en?.title ?? "(untitled)"}
                      </span>
                      <ModerationChip status={c.moderation_status} />
                    </div>
                    {c.media_urls[0] ? (
                      <AdImage src={c.media_urls[0]} alt="" className="h-24 w-full rounded-btn" />
                    ) : null}
                    <p className="text-[13px] text-ink">{c.copy.en?.body ?? "—"}</p>
                    <p className="break-all text-[12px] text-sub">Links to {c.target_url}</p>
                    <Button
                      type="button"
                      variant="ghost"
                      className="min-h-[44px] min-w-0 max-w-[160px] break-words"
                      onClick={() => setEditingId(c.id)}
                    >
                      Edit
                    </Button>
                  </>
                )}
              </Card>
            </li>
          ))}
        </ul>
      ) : null}

      {creatives && !atLimit && !addingNew ? (
        <Button
          type="button"
          variant="brand"
          className="min-h-[44px] min-w-0 max-w-[240px] break-words"
          onClick={() => setAddingNew(true)}
        >
          Add a creative
        </Button>
      ) : null}
      {creatives && addingNew ? (
        <CreativeForm
          campaignId={campaignId}
          onSaved={(created) => {
            setCreatives((prev) => [...(prev ?? []), created]);
            setAddingNew(false);
          }}
          onCancel={() => setAddingNew(false)}
        />
      ) : null}
      {creatives && atLimit && !addingNew ? (
        <p className="text-[12px] text-sub">
          You&apos;ve reached the {MAX_CREATIVES}-creative limit for this campaign.
        </p>
      ) : null}
    </div>
  );
}

// ---------------------------------------------------------------------------
// M5 Task 16: Review & pay step
//
// The choice summary reads client state (`draft`) — it mirrors exactly what
// persistDraft() already saved server-side. The price is re-fetched from
// GET /campaigns/{id} instead (server truth: the client never re-derives
// money), same rule campaign-wizard.tsx's QuoteRail already follows.

const GSTIN_RE = /^[0-9A-Z]{15}$/;

interface ReviewCampaign {
  status: string;
  price_paise: number | null;
  price_subtotal_paise: number | null;
  price_gst_paise: number | null;
  creatives: CreativeOut[];
}

const PAY_ERROR_COPY: Record<string, string> = {
  not_payable: "This campaign can't be paid for right now.",
  not_priced: "This campaign hasn't been priced yet — go back and finish the schedule step.",
  no_creatives: "Add at least one creative before you can pay.",
  business_not_servable: "Your business account isn't eligible to advertise right now.",
  order_exists: "A payment is already in progress for this campaign.",
  razorpay_unavailable: "The payment provider is unavailable right now — please try again shortly.",
};

function friendlyPayError(err: unknown): string {
  if (err instanceof ApiError) {
    return PAY_ERROR_COPY[err.detail] ?? "Could not start checkout — please try again.";
  }
  return "Could not start checkout — please try again.";
}

export function ReviewPayStep({ campaignId, draft }: { campaignId: string; draft: WizardDraft }) {
  const [campaign, setCampaign] = useState<ReviewCampaign | null>(null);
  const [loadError, setLoadError] = useState(false);
  const [gstin, setGstin] = useState("");
  const [gstinError, setGstinError] = useState<string | null>(null);
  const [payError, setPayError] = useState<string | null>(null);
  const [paying, setPaying] = useState(false);

  useEffect(() => {
    let cancelled = false;
    void (async () => {
      try {
        const body = await getJson(`/api/ads/my/campaigns/${campaignId}`);
        if (cancelled) return;
        setCampaign(body as unknown as ReviewCampaign);
        setLoadError(false);
      } catch {
        if (!cancelled) setLoadError(true);
      }
    })();
    return () => {
      cancelled = true;
    };
  }, [campaignId]);

  const goalSummary =
    draft.goalMode === "sponsored"
      ? "Sponsored listing"
      : `Banner ads — ${draft.slotKeys
          .map((key) => BANNER_SLOTS.find((s) => s.key === key)?.label ?? key)
          .join(", ")}`;

  const areaSummary =
    draft.areaMode === "all"
      ? "All of India"
      : draft.areaMode === "pincodes"
        ? `${draft.pincodes.length} pincode${draft.pincodes.length === 1 ? "" : "s"}: ${draft.pincodes.join(", ")}`
        : `Tamil Nadu towns — ${draft.tiers.map((t) => TIER_LABELS[t]).join(", ")}`;

  const categorySummary = draft.allCategories ? "All categories" : draft.categories.join(", ") || "—";

  const handleGstinChange = (value: string) => {
    setGstin(value.toUpperCase().replace(/[^0-9A-Z]/g, "").slice(0, 15));
    setGstinError(null);
  };

  const creativeCount = campaign?.creatives.length ?? 0;

  const handlePay = async () => {
    if (gstin && !GSTIN_RE.test(gstin)) {
      setGstinError("GSTIN must be exactly 15 characters (digits and uppercase letters).");
      return;
    }
    setPaying(true);
    setPayError(null);
    try {
      try {
        await postJson(`/api/ads/my/campaigns/${campaignId}/checkout-request`);
      } catch (err) {
        // Retry-safety (stranded-payment fix): request_checkout only accepts
        // a `draft` campaign (PAYABLE_FROM, lifecycle.py) - it 409s
        // not_payable on every retry once the FIRST attempt already flipped
        // the campaign to pending_payment, even when that first attempt's
        // real failure was downstream (ad-orders 503/409 below). Without
        // this, an advertiser whose first payment attempt failed after this
        // call could never pay again. Swallowing not_payable here and
        // falling through to ad-orders is safe: create_ad_order's OWN
        // not_payable check (status != pending_payment) still fires - and is
        // NOT swallowed - for every other bad state (paused, archived, ...),
        // so the genuine "can't pay this campaign" case still surfaces.
        if (!(err instanceof ApiError && err.status === 409 && err.detail === "not_payable")) {
          throw err;
        }
      }

      let order;
      try {
        order = await postJson("/api/billing/ad-orders", {
          campaign_id: campaignId,
          ...(gstin ? { buyer_gstin: gstin } : {}),
        });
      } catch (err) {
        if (err instanceof ApiError && err.status === 409 && err.detail === "order_exists") {
          // The partial-unique index in ad_orders.py already has a live
          // order for this campaign (a previous attempt got this far but
          // never redirected - e.g. the tab closed between order creation
          // and window.location.assign). Recover its persisted checkout_url
          // (razorpay_short_url, Task 9) instead of dead-ending here.
          const page = await getJson(`/api/billing/ad-orders?campaign_id=${campaignId}&limit=5`);
          const items =
            (page.items as { status: string; checkout_url: string | null }[] | undefined) ?? [];
          const resumable = items.find((o) => o.status === "created" && o.checkout_url);
          if (resumable?.checkout_url) {
            window.location.assign(resumable.checkout_url);
            return;
          }
        }
        throw err;
      }

      const checkoutUrl = order.checkout_url as string | null | undefined;
      if (!checkoutUrl) {
        setPayError("Could not start checkout — please try again.");
        setPaying(false);
        return;
      }
      window.location.assign(checkoutUrl);
    } catch (err) {
      setPayError(friendlyPayError(err));
      setPaying(false);
    }
  };

  return (
    <div className="space-y-4">
      <Card className="space-y-2 p-4">
        <p className="text-[13px] font-extrabold text-ink">{draft.name}</p>
        <dl className="space-y-1 text-[13px] text-ink">
          <div className="flex gap-2">
            <dt className="min-w-0 flex-1 break-words text-sub">Goal</dt>
            <dd className="min-w-0 flex-1 break-words text-right">{goalSummary}</dd>
          </div>
          <div className="flex gap-2">
            <dt className="min-w-0 flex-1 break-words text-sub">Categories</dt>
            <dd className="min-w-0 flex-1 break-words text-right">{categorySummary}</dd>
          </div>
          <div className="flex gap-2">
            <dt className="min-w-0 flex-1 break-words text-sub">Areas</dt>
            <dd className="min-w-0 flex-1 break-words text-right">{areaSummary}</dd>
          </div>
          <div className="flex gap-2">
            <dt className="min-w-0 flex-1 break-words text-sub">Schedule</dt>
            <dd className="min-w-0 flex-1 break-words text-right">
              {draft.flightStart} → {draft.flightEnd}
            </dd>
          </div>
          {draft.servesTotal !== null ? (
            <div className="flex gap-2">
              <dt className="min-w-0 flex-1 break-words text-sub">Ad views</dt>
              <dd className="min-w-0 flex-1 break-words text-right">
                {draft.servesTotal.toLocaleString("en-IN")}
                {draft.dailyServeCap ? ` (max ${draft.dailyServeCap.toLocaleString("en-IN")}/day)` : ""}
              </dd>
            </div>
          ) : null}
        </dl>
      </Card>

      {loadError ? <AlertNotice>Could not load the final price — please try again.</AlertNotice> : null}
      {campaign === null && !loadError ? <Skeleton width="100%" height="96px" /> : null}
      {campaign ? (
        <Card className="space-y-2 p-4">
          <p className="text-[13px] font-extrabold text-ink">Final price</p>
          <div className="space-y-0.5 text-[13px] text-ink">
            <div className="flex gap-2">
              <span className="min-w-0 flex-1 break-words text-sub">Subtotal</span>
              <span className="flex-none">
                {campaign.price_subtotal_paise != null ? rupees(campaign.price_subtotal_paise) : "—"}
              </span>
            </div>
            <div className="flex gap-2">
              <span className="min-w-0 flex-1 break-words text-sub">GST</span>
              <span className="flex-none">
                {campaign.price_gst_paise != null ? rupees(campaign.price_gst_paise) : "—"}
              </span>
            </div>
            <div className="flex gap-2 border-t border-line pt-1 text-[14px] font-extrabold">
              <span className="min-w-0 flex-1 break-words">Total</span>
              <span className="flex-none">
                {campaign.price_paise != null ? rupees(campaign.price_paise) : "—"}
              </span>
            </div>
          </div>
        </Card>
      ) : null}

      <label className={LABEL}>
        GSTIN (optional, for the tax invoice)
        <input
          className={FIELD}
          value={gstin}
          maxLength={15}
          onChange={(e) => handleGstinChange(e.target.value)}
          placeholder="22AAAAA0000A1Z5"
        />
      </label>
      {gstinError ? <AlertNotice>{gstinError}</AlertNotice> : null}

      {campaign && creativeCount === 0 ? (
        <AlertNotice>Add at least one creative in the previous step before you can pay.</AlertNotice>
      ) : null}
      {payError ? <AlertNotice>{payError}</AlertNotice> : null}

      <Button
        type="button"
        variant="brand"
        className="min-h-[44px] w-full max-w-[320px] break-words"
        disabled={paying || !campaign || campaign.price_paise == null || creativeCount === 0}
        onClick={() => void handlePay()}
      >
        {paying
          ? "Starting checkout..."
          : `Pay ${campaign?.price_paise != null ? rupees(campaign.price_paise) : "₹—"} securely with Razorpay`}
      </Button>
      <p className="text-[12px] text-sub">
        You&apos;ll be redirected to Razorpay. Your ads go live after payment and a quick review.
      </p>
    </div>
  );
}
