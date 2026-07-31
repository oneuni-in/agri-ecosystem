"use client";

/**
 * D21 Task 15: Ads management console — campaigns, creatives, placements,
 * stats, all via the /admin/ads/* proxy (Tasks 6+10). Creatives are always
 * created `pending`; this page never flips moderation_status - that only
 * happens through the unified Ops Console queue (Task 14), which is why
 * every creative row links there instead of offering an approve button.
 *
 * `GET /ads/placements` only filters by slot_key (there is no campaign_id
 * query param in the Task 10 contract), so per-campaign placement lists are
 * fetched by the single v1 slot key and filtered client-side to the current
 * campaign - acceptable at v1 volume with one slot key in existence.
 *
 * Media upload has no admin self-serve/presign path yet (checked: shared
 * storage usage elsewhere is claims/verification-evidence only), so
 * media_keys are pasted strings for now - called out in the creative form.
 */

import { Button, Card, EmptyState, Skeleton, useToast } from "@agri/ui";
import Link from "next/link";
import { useEffect, useState } from "react";

import { ApiError, getJson, postJson } from "@/lib/api";

const CAMPAIGN_STATUSES = ["draft", "active", "paused", "archived"] as const;
// Mirrors modules/ads/service.py SLOT_KEYS ({vertical}_{placement} - M2).
const SLOT_KEYS = [
  "directory_browse",
  "milk_global_header",
  "milk_home_hero",
  "milk_category_banner",
  "milk_search_inline",
  "milk_profile_footer",
  "milk_sponsored_listing",
] as const;
const PINCODE_RE = /^\d{6}$/;
const CATEGORY_RE = /^[a-z0-9-]{1,40}$/;

type CampaignStatus = (typeof CAMPAIGN_STATUSES)[number];
type PlacementStatus = "active" | "paused";

interface Campaign {
  id: string;
  advertiser_business_id: string;
  name: string;
  status: CampaignStatus;
  budget_display: string;
  budget_serves_total: number | null;
  budget_serves_used: number;
  flight_start: string;
  flight_end: string;
  created_at: string;
}

interface CopyBlock {
  title: string;
  body: string;
}

interface Creative {
  id: string;
  campaign_id: string;
  media_keys: string[];
  copy: Record<string, CopyBlock>;
  target_url: string;
  moderation_status: string;
  created_at: string;
}

interface GeoTarget {
  state?: number;
  district?: number;
  pincodes?: string[];
  /** M2: M1 schema category values (e.g. ghee) this placement targets. */
  categories?: string[];
}

interface Placement {
  id: string;
  campaign_id: string;
  slot_key: string;
  geo_target: GeoTarget;
  weight: number;
  status: PlacementStatus;
  created_at: string;
}

interface StatRow {
  day: string;
  impressions: number;
  clicks: number;
}

/** Badge's variant union is fixed marketing semantics (sponsored/verified/
 * cert) - it doesn't model open-ended status strings, so status renders as
 * a plain token-styled pill, same idiom as ops-manager.tsx's Chip. */
function StatusPill({ label }: { label: string }) {
  return (
    <span className="inline-flex items-center self-start rounded-pill border border-line bg-ghost px-[9px] py-[3px] text-[11px] font-extrabold text-ink">
      {label}
    </span>
  );
}

function isoDate(date: Date): string {
  return date.toISOString().slice(0, 10);
}

function CreateCampaignForm({ onCreated }: { onCreated: (campaign: Campaign) => void }) {
  const { toast } = useToast();
  const [businessId, setBusinessId] = useState("");
  const [name, setName] = useState("");
  const [budgetDisplay, setBudgetDisplay] = useState("");
  const [budgetServes, setBudgetServes] = useState("");
  const [flightStart, setFlightStart] = useState("");
  const [flightEnd, setFlightEnd] = useState("");
  const [submitting, setSubmitting] = useState(false);

  const submit = async (event: React.FormEvent) => {
    event.preventDefault();
    if (!businessId.trim() || !name.trim() || !flightStart || !flightEnd) return;
    if (flightStart >= flightEnd) {
      toast({ title: "Flight start must be before flight end" });
      return;
    }
    setSubmitting(true);
    try {
      const body = await postJson("/ads/campaigns", {
        advertiser_business_id: businessId.trim(),
        name: name.trim(),
        budget_display: budgetDisplay.trim(),
        // M3 serve-credit ceiling: blank = unlimited (never send "")
        ...(budgetServes.trim() !== "" ? { budget_serves_total: Number(budgetServes) } : {}),
        flight_start: flightStart,
        flight_end: flightEnd,
      });
      onCreated(body as unknown as Campaign);
      toast({ title: `Campaign "${name.trim()}" created` });
      setBusinessId("");
      setName("");
      setBudgetDisplay("");
      setBudgetServes("");
      setFlightStart("");
      setFlightEnd("");
    } catch (error) {
      toast({
        title:
          error instanceof ApiError && error.detail === "unknown_business"
            ? "Unknown business - check the business UUID"
            : error instanceof ApiError
              ? error.detail
              : "Could not create the campaign",
      });
    } finally {
      setSubmitting(false);
    }
  };

  return (
    <form className="space-y-2" onSubmit={(event) => void submit(event)}>
      <label className="block text-sm font-semibold text-ink">
        Advertiser business ID (UUID)
        <input
          className="mt-1 min-h-[44px] w-full rounded-btn border border-line bg-card px-3 py-2 text-ink"
          value={businessId}
          onChange={(event) => setBusinessId(event.target.value)}
          placeholder="00000000-0000-0000-0000-000000000000"
          required
        />
      </label>
      <label className="block text-sm font-semibold text-ink">
        Campaign name
        <input
          className="mt-1 min-h-[44px] w-full rounded-btn border border-line bg-card px-3 py-2 text-ink"
          value={name}
          onChange={(event) => setName(event.target.value)}
          required
        />
      </label>
      <label className="block text-sm font-semibold text-ink">
        Budget (display text, optional)
        <input
          className="mt-1 min-h-[44px] w-full rounded-btn border border-line bg-card px-3 py-2 text-ink"
          value={budgetDisplay}
          onChange={(event) => setBudgetDisplay(event.target.value)}
          placeholder="e.g. Rs 50,000 / month"
        />
      </label>
      <label className="block text-sm font-semibold text-ink">
        Serve budget (blank = unlimited)
        <input
          type="number"
          min={0}
          className="mt-1 min-h-[44px] w-full rounded-btn border border-line bg-card px-3 py-2 text-ink"
          value={budgetServes}
          onChange={(event) => setBudgetServes(event.target.value)}
          placeholder="e.g. 10000 serves"
        />
      </label>
      <div className="flex gap-2">
        <label className="block flex-1 text-sm font-semibold text-ink">
          Flight start
          <input
            type="date"
            className="mt-1 min-h-[44px] w-full rounded-btn border border-line bg-card px-3 py-2 text-ink"
            value={flightStart}
            onChange={(event) => setFlightStart(event.target.value)}
            required
          />
        </label>
        <label className="block flex-1 text-sm font-semibold text-ink">
          Flight end
          <input
            type="date"
            className="mt-1 min-h-[44px] w-full rounded-btn border border-line bg-card px-3 py-2 text-ink"
            value={flightEnd}
            onChange={(event) => setFlightEnd(event.target.value)}
            required
          />
        </label>
      </div>
      <Button type="submit" variant="brand" disabled={submitting}>
        Create campaign
      </Button>
    </form>
  );
}

function CampaignRow({
  campaign,
  expanded,
  onToggle,
  onStatusChange,
}: {
  campaign: Campaign;
  expanded: boolean;
  onToggle: () => void;
  onStatusChange: (campaign: Campaign) => void;
}) {
  const { toast } = useToast();
  const [changing, setChanging] = useState(false);

  const changeStatus = async (status: CampaignStatus) => {
    if (status === campaign.status) return;
    setChanging(true);
    try {
      const body = await postJson(`/ads/campaigns/${campaign.id}/status`, { status });
      onStatusChange(body as unknown as Campaign);
    } catch (error) {
      toast({ title: error instanceof ApiError ? error.detail : "Could not change status" });
    } finally {
      setChanging(false);
    }
  };

  return (
    <Card className="space-y-2 p-3">
      <div className="flex items-center justify-between gap-2">
        <div>
          <p className="font-semibold text-ink">{campaign.name}</p>
          <p className="text-xs text-sub">
            {campaign.budget_display || "—"} · {campaign.flight_start} → {campaign.flight_end}
            {" · "}
            {campaign.budget_serves_used}/{campaign.budget_serves_total ?? "∞"} serves
          </p>
          <p className="break-all text-xs text-sub">Business: {campaign.advertiser_business_id}</p>
        </div>
        <StatusPill label={campaign.status} />
      </div>
      <div className="flex flex-wrap items-center gap-2">
        <select
          className="min-h-[44px] rounded-btn border border-line bg-card px-2 py-1 text-sm text-ink"
          aria-label={`Change status for ${campaign.name}`}
          value={campaign.status}
          disabled={changing}
          onChange={(event) => void changeStatus(event.target.value as CampaignStatus)}
        >
          {CAMPAIGN_STATUSES.map((status) => (
            <option key={status} value={status}>
              {status}
            </option>
          ))}
        </select>
        <Button onClick={onToggle}>{expanded ? "Hide details" : "Manage creatives & placements"}</Button>
      </div>
    </Card>
  );
}

function CreateCreativeForm({
  campaignId,
  onCreated,
}: {
  campaignId: string;
  onCreated: (creative: Creative) => void;
}) {
  const { toast } = useToast();
  const [mediaKeysText, setMediaKeysText] = useState("");
  const [enTitle, setEnTitle] = useState("");
  const [enBody, setEnBody] = useState("");
  const [taTitle, setTaTitle] = useState("");
  const [taBody, setTaBody] = useState("");
  const [hiTitle, setHiTitle] = useState("");
  const [hiBody, setHiBody] = useState("");
  const [targetUrl, setTargetUrl] = useState("");
  const [submitting, setSubmitting] = useState(false);

  const reset = () => {
    setMediaKeysText("");
    setEnTitle("");
    setEnBody("");
    setTaTitle("");
    setTaBody("");
    setHiTitle("");
    setHiBody("");
    setTargetUrl("");
  };

  const submit = async (event: React.FormEvent) => {
    event.preventDefault();
    const mediaKeys = mediaKeysText
      .split("\n")
      .map((key) => key.trim())
      .filter((key) => key.length > 0);
    if (mediaKeys.length > 5) {
      toast({ title: "At most 5 media keys are allowed" });
      return;
    }
    if (!enTitle.trim() || !enBody.trim()) {
      toast({ title: "English title and body are required" });
      return;
    }
    if (!targetUrl.trim()) return;

    const copy: Record<string, CopyBlock> = { en: { title: enTitle.trim(), body: enBody.trim() } };
    if (taTitle.trim() || taBody.trim()) {
      if (!taTitle.trim() || !taBody.trim()) {
        toast({ title: "Tamil needs both a title and a body, or leave both blank" });
        return;
      }
      copy.ta = { title: taTitle.trim(), body: taBody.trim() };
    }
    if (hiTitle.trim() || hiBody.trim()) {
      if (!hiTitle.trim() || !hiBody.trim()) {
        toast({ title: "Hindi needs both a title and a body, or leave both blank" });
        return;
      }
      copy.hi = { title: hiTitle.trim(), body: hiBody.trim() };
    }

    setSubmitting(true);
    try {
      const body = await postJson("/ads/creatives", {
        campaign_id: campaignId,
        media_keys: mediaKeys,
        copy,
        target_url: targetUrl.trim(),
      });
      onCreated(body as unknown as Creative);
      toast({ title: "Creative created - pending review" });
      reset();
    } catch (error) {
      toast({
        title:
          error instanceof ApiError && error.detail === "unknown_campaign"
            ? "Unknown campaign"
            : error instanceof ApiError
              ? error.detail
              : "Could not create the creative",
      });
    } finally {
      setSubmitting(false);
    }
  };

  return (
    <form
      className="space-y-2 rounded-card border border-line bg-ghost p-3"
      onSubmit={(event) => void submit(event)}
    >
      <p className="text-xs text-sub">
        Media upload has no admin self-serve path yet - paste storage keys already uploaded
        elsewhere, one per line (max 5). Self-serve upload lands in a later spec.
      </p>
      <label className="block text-sm font-semibold text-ink">
        Media keys (one per line, optional)
        <textarea
          className="mt-1 min-h-[72px] w-full rounded-btn border border-line bg-card p-2 text-sm text-ink"
          value={mediaKeysText}
          onChange={(event) => setMediaKeysText(event.target.value)}
          placeholder="media/ads/abc123.jpg"
        />
      </label>
      <div className="grid gap-2 sm:grid-cols-2">
        <label className="block text-sm font-semibold text-ink">
          Title (en)
          <input
            className="mt-1 min-h-[44px] w-full rounded-btn border border-line bg-card px-3 py-2 text-ink"
            value={enTitle}
            onChange={(event) => setEnTitle(event.target.value)}
            required
          />
        </label>
        <label className="block text-sm font-semibold text-ink">
          Body (en)
          <input
            className="mt-1 min-h-[44px] w-full rounded-btn border border-line bg-card px-3 py-2 text-ink"
            value={enBody}
            onChange={(event) => setEnBody(event.target.value)}
            required
          />
        </label>
        <label className="block text-sm font-semibold text-ink">
          Title (ta, optional)
          <input
            className="mt-1 min-h-[44px] w-full rounded-btn border border-line bg-card px-3 py-2 text-ink"
            value={taTitle}
            onChange={(event) => setTaTitle(event.target.value)}
          />
        </label>
        <label className="block text-sm font-semibold text-ink">
          Body (ta, optional)
          <input
            className="mt-1 min-h-[44px] w-full rounded-btn border border-line bg-card px-3 py-2 text-ink"
            value={taBody}
            onChange={(event) => setTaBody(event.target.value)}
          />
        </label>
        <label className="block text-sm font-semibold text-ink">
          Title (hi, optional)
          <input
            className="mt-1 min-h-[44px] w-full rounded-btn border border-line bg-card px-3 py-2 text-ink"
            value={hiTitle}
            onChange={(event) => setHiTitle(event.target.value)}
          />
        </label>
        <label className="block text-sm font-semibold text-ink">
          Body (hi, optional)
          <input
            className="mt-1 min-h-[44px] w-full rounded-btn border border-line bg-card px-3 py-2 text-ink"
            value={hiBody}
            onChange={(event) => setHiBody(event.target.value)}
          />
        </label>
      </div>
      <label className="block text-sm font-semibold text-ink">
        Target URL
        <input
          type="url"
          className="mt-1 min-h-[44px] w-full rounded-btn border border-line bg-card px-3 py-2 text-ink"
          value={targetUrl}
          onChange={(event) => setTargetUrl(event.target.value)}
          placeholder="https://example.com/offer"
          required
        />
      </label>
      <Button type="submit" variant="brand" disabled={submitting}>
        Add creative (pending review)
      </Button>
    </form>
  );
}

function CreativesSection({ campaignId }: { campaignId: string }) {
  const { toast } = useToast();
  const [items, setItems] = useState<Creative[]>([]);
  const [nextCursor, setNextCursor] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);
  const [loadingMore, setLoadingMore] = useState(false);

  const load = async (cursor?: string) => {
    if (cursor) setLoadingMore(true);
    else setLoading(true);
    try {
      const params = new URLSearchParams({ campaign_id: campaignId, limit: "20" });
      if (cursor) params.set("cursor", cursor);
      const body = await getJson(`/ads/creatives?${params}`);
      const page = body.items as Creative[];
      setItems((prev) => (cursor ? [...prev, ...page] : page));
      setNextCursor((body.next_cursor ?? null) as string | null);
    } catch (error) {
      toast({ title: error instanceof ApiError ? error.detail : "Could not load creatives" });
    } finally {
      if (cursor) setLoadingMore(false);
      else setLoading(false);
    }
  };

  useEffect(() => {
    void load();
  }, []);

  const loadMore = () => {
    if (loadingMore || !nextCursor) return; // D20 load-more lesson: guard the in-flight state
    void load(nextCursor);
  };

  return (
    <Card className="space-y-3 p-4">
      <h3 className="font-display text-base font-extrabold text-ink">Creatives</h3>
      <CreateCreativeForm
        campaignId={campaignId}
        onCreated={(creative) => setItems((prev) => [creative, ...prev])}
      />
      {loading && items.length === 0 ? <Skeleton width="100%" height="72px" /> : null}
      {!loading && items.length === 0 ? <EmptyState icon="🖼️" title="No creatives yet" /> : null}
      <ul className="space-y-2">
        {items.map((creative) => {
          const en = creative.copy.en;
          return (
            <li key={creative.id}>
              <Card className="space-y-1 p-3">
                <div className="flex items-center justify-between gap-2">
                  <p className="text-sm font-semibold text-ink">{en?.title ?? "(untitled)"}</p>
                  <StatusPill label={creative.moderation_status} />
                </div>
                <p className="text-sm text-ink">{en?.body ?? "—"}</p>
                <p className="break-all text-xs text-sub">Target: {creative.target_url}</p>
                <p className="text-xs text-sub">
                  {creative.media_keys.length} media key{creative.media_keys.length === 1 ? "" : "s"} ·
                  {" "}
                  Locales: {Object.keys(creative.copy).join(", ")}
                </p>
                {creative.moderation_status === "pending" ? (
                  <p className="text-xs text-sub">
                    Pending —{" "}
                    <Link href="/ops" className="text-brand underline">
                      approve in Ops Console
                    </Link>
                  </p>
                ) : null}
              </Card>
            </li>
          );
        })}
      </ul>
      {nextCursor ? (
        <Button disabled={loadingMore} onClick={loadMore}>
          {loadingMore ? "Loading…" : "Load more"}
        </Button>
      ) : null}
    </Card>
  );
}

function formatGeo(geo: GeoTarget): string {
  const parts: string[] = [];
  if (geo.state != null) parts.push(`state ${geo.state}`);
  if (geo.district != null) parts.push(`district ${geo.district}`);
  if (geo.pincodes && geo.pincodes.length > 0) parts.push(`pincodes ${geo.pincodes.join(", ")}`);
  if (geo.categories && geo.categories.length > 0)
    parts.push(`categories ${geo.categories.join(", ")}`);
  return parts.length > 0 ? parts.join(" · ") : "everywhere";
}

function CreatePlacementForm({
  campaignId,
  onCreated,
}: {
  campaignId: string;
  onCreated: (placement: Placement) => void;
}) {
  const { toast } = useToast();
  const [slotKey, setSlotKey] = useState<string>(SLOT_KEYS[0]);
  const [stateLgd, setStateLgd] = useState("");
  const [districtLgd, setDistrictLgd] = useState("");
  const [pincodes, setPincodes] = useState("");
  const [categories, setCategories] = useState("");
  const [weight, setWeight] = useState("1");
  const [submitting, setSubmitting] = useState(false);

  const submit = async (event: React.FormEvent) => {
    event.preventDefault();
    const weightNum = Number(weight);
    if (!Number.isInteger(weightNum) || weightNum < 1) {
      toast({ title: "Weight must be a whole number of at least 1" });
      return;
    }
    const geoTarget: GeoTarget = {};
    if (stateLgd.trim()) {
      const parsed = Number(stateLgd.trim());
      if (!Number.isInteger(parsed)) {
        toast({ title: "State LGD code must be a whole number" });
        return;
      }
      geoTarget.state = parsed;
    }
    if (districtLgd.trim()) {
      const parsed = Number(districtLgd.trim());
      if (!Number.isInteger(parsed)) {
        toast({ title: "District LGD code must be a whole number" });
        return;
      }
      geoTarget.district = parsed;
    }
    const pincodeList = pincodes
      .split(",")
      .map((pincode) => pincode.trim())
      .filter((pincode) => pincode.length > 0);
    const badPincodes = pincodeList.filter((pincode) => !PINCODE_RE.test(pincode));
    if (badPincodes.length > 0) {
      toast({ title: `Pincodes must be 6 digits — invalid: ${badPincodes.join(", ")}` });
      return;
    }
    if (pincodeList.length > 0) geoTarget.pincodes = pincodeList;
    const categoryList = categories
      .split(",")
      .map((category) => category.trim())
      .filter((category) => category.length > 0);
    const badCategories = categoryList.filter((category) => !CATEGORY_RE.test(category));
    if (badCategories.length > 0) {
      toast({
        title: `Categories must be lowercase slugs — invalid: ${badCategories.join(", ")}`,
      });
      return;
    }
    if (categoryList.length > 0) geoTarget.categories = categoryList;

    setSubmitting(true);
    try {
      const body = await postJson("/ads/placements", {
        campaign_id: campaignId,
        slot_key: slotKey,
        geo_target: geoTarget,
        weight: weightNum,
      });
      onCreated(body as unknown as Placement);
      toast({ title: "Placement created" });
      setStateLgd("");
      setDistrictLgd("");
      setPincodes("");
      setCategories("");
      setWeight("1");
    } catch (error) {
      toast({
        title: error instanceof ApiError ? error.detail : "Could not create the placement",
      });
    } finally {
      setSubmitting(false);
    }
  };

  return (
    <form
      className="space-y-2 rounded-card border border-line bg-ghost p-3"
      onSubmit={(event) => void submit(event)}
    >
      <label className="block text-sm font-semibold text-ink">
        Slot
        <select
          className="mt-1 min-h-[44px] w-full rounded-btn border border-line bg-card px-2 py-1 text-sm text-ink"
          value={slotKey}
          onChange={(event) => setSlotKey(event.target.value)}
        >
          {SLOT_KEYS.map((key) => (
            <option key={key} value={key}>
              {key}
            </option>
          ))}
        </select>
      </label>
      <p className="text-xs text-sub">
        Geo target: leave all blank to serve everywhere, or set any combination - a pincode,
        district, or state match is enough to serve.
      </p>
      <div className="grid gap-2 sm:grid-cols-3">
        <label className="block text-sm font-semibold text-ink">
          State (LGD code)
          <input
            type="number"
            className="mt-1 min-h-[44px] w-full rounded-btn border border-line bg-card px-3 py-2 text-ink"
            value={stateLgd}
            onChange={(event) => setStateLgd(event.target.value)}
          />
        </label>
        <label className="block text-sm font-semibold text-ink">
          District (LGD code)
          <input
            type="number"
            className="mt-1 min-h-[44px] w-full rounded-btn border border-line bg-card px-3 py-2 text-ink"
            value={districtLgd}
            onChange={(event) => setDistrictLgd(event.target.value)}
          />
        </label>
        <label className="block text-sm font-semibold text-ink">
          Pincodes (comma-separated)
          <input
            className="mt-1 min-h-[44px] w-full rounded-btn border border-line bg-card px-3 py-2 text-ink"
            value={pincodes}
            onChange={(event) => setPincodes(event.target.value)}
            placeholder="641001, 641002"
          />
        </label>
      </div>
      <label className="block text-sm font-semibold text-ink">
        Categories (comma-separated M1 schema values, optional)
        <input
          className="mt-1 min-h-[44px] w-full rounded-btn border border-line bg-card px-3 py-2 text-ink"
          value={categories}
          onChange={(event) => setCategories(event.target.value)}
          placeholder="ghee, milk-powder"
        />
      </label>
      <label className="block text-sm font-semibold text-ink">
        Weight (whole number, at least 1)
        <input
          type="number"
          min={1}
          step={1}
          className="mt-1 min-h-[44px] w-32 rounded-btn border border-line bg-card px-3 py-2 text-ink"
          value={weight}
          onChange={(event) => setWeight(event.target.value)}
          required
        />
      </label>
      <Button type="submit" variant="brand" disabled={submitting}>
        Add placement
      </Button>
    </form>
  );
}

function StatsPanel({ placementId }: { placementId: string }) {
  const { toast } = useToast();
  const [dateFrom, setDateFrom] = useState(() => {
    const start = new Date();
    start.setUTCDate(start.getUTCDate() - 13);
    return isoDate(start);
  });
  const [dateTo, setDateTo] = useState(() => isoDate(new Date()));
  const [rows, setRows] = useState<StatRow[]>([]);
  const [loading, setLoading] = useState(true);

  const load = async () => {
    setLoading(true);
    try {
      const params = new URLSearchParams({
        placement_id: placementId,
        date_from: dateFrom,
        date_to: dateTo,
      });
      const body = await getJson(`/ads/stats?${params}`);
      setRows((body.rows ?? []) as StatRow[]);
    } catch (error) {
      toast({ title: error instanceof ApiError ? error.detail : "Could not load stats" });
    } finally {
      setLoading(false);
    }
  };

  // Loads once on mount with the default 14-day range; date-input edits only
  // take effect via the explicit Refresh click below.
  useEffect(() => {
    void load();
  }, []);

  return (
    <div className="space-y-2 rounded-card border border-line bg-ghost p-3">
      <div className="flex flex-wrap items-end gap-2">
        <label className="block text-sm font-semibold text-ink">
          From
          <input
            type="date"
            className="mt-1 min-h-[44px] rounded-btn border border-line bg-card px-2 py-1 text-ink"
            value={dateFrom}
            onChange={(event) => setDateFrom(event.target.value)}
          />
        </label>
        <label className="block text-sm font-semibold text-ink">
          To
          <input
            type="date"
            className="mt-1 min-h-[44px] rounded-btn border border-line bg-card px-2 py-1 text-ink"
            value={dateTo}
            onChange={(event) => setDateTo(event.target.value)}
          />
        </label>
        <Button disabled={loading} onClick={() => void load()}>
          {loading ? "Loading…" : "Refresh"}
        </Button>
      </div>
      {rows.length === 0 && !loading ? (
        <p className="text-xs text-sub">No impressions or clicks in this range.</p>
      ) : (
        <div className="overflow-x-auto">
          <table className="w-full min-w-[320px] border-collapse text-sm text-ink">
            <thead>
              <tr className="border-b border-line text-left text-sub">
                <th className="py-1 pr-2">Day</th>
                <th className="py-1 pr-2">Impressions</th>
                <th className="py-1 pr-2">Clicks</th>
              </tr>
            </thead>
            <tbody>
              {rows.map((row) => (
                <tr key={row.day} className="border-b border-line">
                  <td className="py-1 pr-2">{row.day}</td>
                  <td className="py-1 pr-2">{row.impressions}</td>
                  <td className="py-1 pr-2">{row.clicks}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </div>
  );
}

function PlacementRow({
  placement,
  statsOpen,
  onToggleStats,
  onStatusChange,
}: {
  placement: Placement;
  statsOpen: boolean;
  onToggleStats: () => void;
  onStatusChange: (placement: Placement) => void;
}) {
  const { toast } = useToast();
  const [changing, setChanging] = useState(false);

  const toggleStatus = async () => {
    const next: PlacementStatus = placement.status === "active" ? "paused" : "active";
    setChanging(true);
    try {
      const body = await postJson(`/ads/placements/${placement.id}/status`, { status: next });
      onStatusChange(body as unknown as Placement);
    } catch (error) {
      toast({ title: error instanceof ApiError ? error.detail : "Could not change status" });
    } finally {
      setChanging(false);
    }
  };

  return (
    <Card className="space-y-2 p-3">
      <div className="flex items-center justify-between gap-2">
        <div>
          <p className="text-sm font-semibold text-ink">{placement.slot_key}</p>
          <p className="text-xs text-sub">
            {formatGeo(placement.geo_target)} · weight {placement.weight}
          </p>
        </div>
        <StatusPill label={placement.status} />
      </div>
      <div className="flex flex-wrap gap-2">
        <Button disabled={changing} onClick={() => void toggleStatus()}>
          {placement.status === "active" ? "Pause" : "Activate"}
        </Button>
        <Button onClick={onToggleStats}>{statsOpen ? "Hide stats" : "View stats"}</Button>
      </div>
      {statsOpen ? <StatsPanel placementId={placement.id} /> : null}
    </Card>
  );
}

function PlacementsSection({ campaignId }: { campaignId: string }) {
  const { toast } = useToast();
  const [items, setItems] = useState<Placement[]>([]);
  const [nextCursor, setNextCursor] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);
  const [loadingMore, setLoadingMore] = useState(false);
  const [statsOpenId, setStatsOpenId] = useState<string | null>(null);

  const load = async (cursor?: string) => {
    if (cursor) setLoadingMore(true);
    else setLoading(true);
    try {
      // M2: GET /ads/placements filters by ONE slot_key (no campaign_id
      // param), so fetch every slot in parallel and filter client-side -
      // same pattern as before, widened from the single D21 slot. Cursoring
      // stays per-slot; 50-per-slot covers v1 console volume, so load-more
      // only pages the first slot's overflow (rare) rather than fanning out.
      const pages = await Promise.all(
        SLOT_KEYS.map((slotKey) => {
          const params = new URLSearchParams({ slot_key: slotKey, limit: "50" });
          if (cursor && slotKey === SLOT_KEYS[0]) params.set("cursor", cursor);
          return getJson(`/ads/placements?${params}`);
        }),
      );
      const page = pages
        .flatMap((body) => body.items as Placement[])
        .filter((placement) => placement.campaign_id === campaignId);
      setItems((prev) => (cursor ? [...prev, ...page] : page));
      setNextCursor((pages[0]?.next_cursor ?? null) as string | null);
    } catch (error) {
      toast({ title: error instanceof ApiError ? error.detail : "Could not load placements" });
    } finally {
      if (cursor) setLoadingMore(false);
      else setLoading(false);
    }
  };

  useEffect(() => {
    void load();
  }, []);

  const loadMore = () => {
    if (loadingMore || !nextCursor) return; // D20 load-more lesson: guard the in-flight state
    void load(nextCursor);
  };

  return (
    <Card className="space-y-3 p-4">
      <h3 className="font-display text-base font-extrabold text-ink">Placements</h3>
      <CreatePlacementForm
        campaignId={campaignId}
        onCreated={(placement) => setItems((prev) => [placement, ...prev])}
      />
      {loading && items.length === 0 ? <Skeleton width="100%" height="72px" /> : null}
      {!loading && items.length === 0 ? <EmptyState icon="📍" title="No placements yet" /> : null}
      <ul className="space-y-2">
        {items.map((placement) => (
          <li key={placement.id}>
            <PlacementRow
              placement={placement}
              statsOpen={statsOpenId === placement.id}
              onToggleStats={() =>
                setStatsOpenId((prev) => (prev === placement.id ? null : placement.id))
              }
              onStatusChange={(updated) =>
                setItems((prev) =>
                  prev.map((existing) => (existing.id === updated.id ? updated : existing)),
                )
              }
            />
          </li>
        ))}
      </ul>
      {nextCursor ? (
        <Button disabled={loadingMore} onClick={loadMore}>
          {loadingMore ? "Loading…" : "Load more"}
        </Button>
      ) : null}
    </Card>
  );
}

function CampaignDetail({ campaign }: { campaign: Campaign }) {
  return (
    <div className="ml-2 space-y-4 border-l-2 border-line pl-4">
      <CreativesSection campaignId={campaign.id} />
      <PlacementsSection campaignId={campaign.id} />
    </div>
  );
}

function CampaignsSection() {
  const { toast } = useToast();
  const [items, setItems] = useState<Campaign[]>([]);
  const [nextCursor, setNextCursor] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);
  const [loadingMore, setLoadingMore] = useState(false);
  const [expandedId, setExpandedId] = useState<string | null>(null);

  const load = async (cursor?: string) => {
    if (cursor) setLoadingMore(true);
    else setLoading(true);
    try {
      const params = new URLSearchParams({ limit: "20" });
      if (cursor) params.set("cursor", cursor);
      const body = await getJson(`/ads/campaigns?${params}`);
      const page = body.items as Campaign[];
      setItems((prev) => (cursor ? [...prev, ...page] : page));
      setNextCursor((body.next_cursor ?? null) as string | null);
    } catch (error) {
      toast({ title: error instanceof ApiError ? error.detail : "Could not load campaigns" });
    } finally {
      if (cursor) setLoadingMore(false);
      else setLoading(false);
    }
  };

  useEffect(() => {
    void load();
  }, []);

  const loadMore = () => {
    if (loadingMore || !nextCursor) return; // D20 load-more lesson: guard the in-flight state
    void load(nextCursor);
  };

  return (
    <div className="space-y-4">
      <Card className="space-y-3 p-4">
        <h2 className="font-display text-lg font-extrabold text-ink">New campaign</h2>
        <CreateCampaignForm onCreated={(campaign) => setItems((prev) => [campaign, ...prev])} />
      </Card>

      <Card className="space-y-3 p-4">
        <h2 className="font-display text-lg font-extrabold text-ink">Campaigns</h2>
        {loading && items.length === 0 ? (
          <div className="space-y-2">
            <Skeleton width="100%" height="88px" />
            <Skeleton width="100%" height="88px" />
          </div>
        ) : null}
        {!loading && items.length === 0 ? <EmptyState icon="📢" title="No campaigns yet" /> : null}
        <ul className="space-y-3">
          {items.map((campaign) => (
            <li key={campaign.id} className="space-y-3">
              <CampaignRow
                campaign={campaign}
                expanded={expandedId === campaign.id}
                onToggle={() =>
                  setExpandedId((prev) => (prev === campaign.id ? null : campaign.id))
                }
                onStatusChange={(updated) =>
                  setItems((prev) =>
                    prev.map((existing) => (existing.id === updated.id ? updated : existing)),
                  )
                }
              />
              {expandedId === campaign.id ? <CampaignDetail campaign={campaign} /> : null}
            </li>
          ))}
        </ul>
        {nextCursor ? (
          <Button disabled={loadingMore} onClick={loadMore}>
            {loadingMore ? "Loading…" : "Load more"}
          </Button>
        ) : null}
      </Card>
    </div>
  );
}

export function AdsManager() {
  return (
    <main className="mx-auto max-w-4xl space-y-6 p-4">
      <h1 className="text-xl font-bold text-ink">Ads</h1>
      <CampaignsSection />
    </main>
  );
}
