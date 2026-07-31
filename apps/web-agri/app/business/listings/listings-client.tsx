"use client";

import { Button, Card, Skeleton, cn } from "@agri/ui";
import { useEffect, useRef, useState, type ReactNode } from "react";

import { ApiError, getJson, patchJson, postJson, putJson } from "@/lib/api";

type BusinessType = "vendor" | "shop" | "lab" | "farm";

interface DeliveryWindow {
  days: string[];
  open: string;
  close: string;
}

interface BusinessOut {
  id: string;
  name: string;
  slug: string;
  type: BusinessType;
  status: string;
  primary_pincode: string;
  description: Record<string, string> | null;
  delivery_windows: DeliveryWindow[] | null;
  verification_status: string;
  subscription_tier: string;
  // M1.5: set while suspended/disabled; the owner-facing notice text
  enforcement_reason: string | null;
}

const FIELD =
  "mt-1 block min-h-[44px] w-full rounded-btn border border-line bg-card px-3 py-2 text-[13px] text-ink";
const LABEL = "block text-[13px] font-semibold text-ink";
const DAYS = ["mon", "tue", "wed", "thu", "fri", "sat", "sun"] as const;
const TYPES: BusinessType[] = ["vendor", "shop", "lab", "farm"];
const PINCODE_RE = /^\d{6}$/;

function AlertNotice({ children }: { children: ReactNode }) {
  return (
    <div className="rounded-card border border-alert-line bg-alert-bg p-3 text-[13px] font-semibold text-ink">
      {children}
    </div>
  );
}

function OkNotice({ children }: { children: ReactNode }) {
  return (
    <div className="rounded-card bg-verified-bg p-3 text-[13px] font-semibold text-verified-fg">
      {children}
    </div>
  );
}

export function ListingsClient() {
  const [businesses, setBusinesses] = useState<BusinessOut[] | null>(null);
  const [loadError, setLoadError] = useState(false);
  const [selectedId, setSelectedId] = useState<string | null>(null);

  // create-business form (fresh vendors own nothing yet)
  const [newName, setNewName] = useState("");
  const [newType, setNewType] = useState<BusinessType>("vendor");
  const [newPincode, setNewPincode] = useState("");
  const [creating, setCreating] = useState(false);
  const [createError, setCreateError] = useState<string | null>(null);

  // listing form
  const [name, setName] = useState("");
  const [type, setType] = useState<BusinessType>("vendor");
  const [primaryPincode, setPrimaryPincode] = useState("");
  const [descriptionEn, setDescriptionEn] = useState("");
  const [descriptionTa, setDescriptionTa] = useState("");
  const [descriptionHi, setDescriptionHi] = useState("");
  const [windows, setWindows] = useState<DeliveryWindow[]>([]);
  const [coverage, setCoverage] = useState<string[]>([]);
  const [coverageInput, setCoverageInput] = useState("");
  const [detailLoading, setDetailLoading] = useState(false);
  const [saving, setSaving] = useState<"listing" | "coverage" | null>(null);
  const [notice, setNotice] = useState<{ kind: "ok" | "error"; text: string } | null>(null);

  // Latest values mirrored into refs so async callbacks (saves, in-flight detail
  // fetches) can check "is this still current?" without retriggering the effects
  // that depend on selectedId alone.
  const businessesRef = useRef<BusinessOut[] | null>(null);
  const selectedIdRef = useRef<string | null>(null);

  useEffect(() => {
    businessesRef.current = businesses;
  }, [businesses]);

  useEffect(() => {
    selectedIdRef.current = selectedId;
  }, [selectedId]);

  const loadBusinesses = async () => {
    try {
      const body = await getJson("/api/directory/businesses?limit=50");
      const list = (body.items as BusinessOut[] | undefined) ?? [];
      setBusinesses(list);
      if (list[0] && !selectedId) setSelectedId(list[0].id);
    } catch {
      setLoadError(true);
    }
  };

  useEffect(() => {
    void loadBusinesses();
  }, []);

  // Resets the form to the selected business's server snapshot and fetches its
  // coverage. Depends on selectedId ONLY (not businesses) so that background
  // refreshes of the businesses list never clobber in-progress edits; the
  // current list is read from businessesRef instead. The cancelled guard drops
  // stale detail responses when the user switches businesses before a prior
  // fetch resolves.
  useEffect(() => {
    const selected = businessesRef.current?.find((b) => b.id === selectedId);
    if (!selected) return;
    let cancelled = false;
    setName(selected.name);
    setType(selected.type);
    setPrimaryPincode(selected.primary_pincode);
    setDescriptionEn(selected.description?.en ?? "");
    setDescriptionTa(selected.description?.ta ?? "");
    setDescriptionHi(selected.description?.hi ?? "");
    setWindows(selected.delivery_windows ?? []);
    setDetailLoading(true);
    setNotice(null);
    void (async () => {
      try {
        const detail = await getJson(`/api/directory/businesses/${selected.slug}`);
        if (cancelled) return;
        setCoverage((detail.coverage_pincodes as string[] | undefined) ?? []);
      } catch {
        if (!cancelled) setCoverage([]);
      } finally {
        if (!cancelled) setDetailLoading(false);
      }
    })();
    return () => {
      cancelled = true;
    };
  }, [selectedId]);

  const create = async () => {
    if (!newName.trim() || !PINCODE_RE.test(newPincode)) {
      setCreateError("Name and a 6-digit pincode are required.");
      return;
    }
    setCreating(true);
    setCreateError(null);
    try {
      const created = await postJson("/api/directory/businesses", {
        name: newName.trim(),
        type: newType,
        primary_pincode: newPincode,
      });
      await loadBusinesses();
      setSelectedId(created.id as string);
    } catch (err) {
      setCreateError(
        err instanceof ApiError ? `Could not create listing (${err.detail}).` : "Could not create listing.",
      );
    } finally {
      setCreating(false);
    }
  };

  const saveListing = async () => {
    if (!selectedId) return;
    const savedFor = selectedId;
    setSaving("listing");
    setNotice(null);
    try {
      // M1.5.C: all three About locales are editable here. Start from the
      // server snapshot (preserves any key this console doesn't know about),
      // then set/clear each edited locale - a blanked box deletes only its
      // own key.
      const existingDescription = businessesRef.current?.find((b) => b.id === savedFor)?.description ?? null;
      const merged: Record<string, string> = { ...existingDescription };
      const edits: [string, string][] = [
        ["en", descriptionEn.trim()],
        ["ta", descriptionTa.trim()],
        ["hi", descriptionHi.trim()],
      ];
      for (const [key, value] of edits) {
        if (value) merged[key] = value;
        else delete merged[key];
      }
      const description = Object.keys(merged).length > 0 ? merged : null;
      const trimmedName = name.trim();
      await patchJson(`/api/directory/businesses/${savedFor}`, {
        name: trimmedName,
        type,
        primary_pincode: primaryPincode,
        description,
        delivery_windows: windows,
      });
      // Update the picker's entry locally instead of refetching the whole list -
      // an un-awaited refetch here is what let stale GET responses clobber
      // in-progress edits on other businesses.
      setBusinesses((prev) =>
        prev?.map((b) =>
          b.id === savedFor
            ? { ...b, name: trimmedName, type, primary_pincode: primaryPincode, description, delivery_windows: windows }
            : b,
        ) ?? prev,
      );
      if (selectedIdRef.current !== savedFor) return;
      setNotice({ kind: "ok", text: "Listing saved." });
    } catch (err) {
      if (selectedIdRef.current !== savedFor) return;
      const text =
        err instanceof ApiError && err.status === 403 && err.detail === "business_disabled"
          ? "This listing has been disabled by Milk.in administrators — changes are locked."
          : err instanceof ApiError && err.status === 422
            ? "Check the highlighted fields — the About text must be plain text (max 2000 characters per language) and delivery windows need valid days and open < close times."
            : "Could not save — please try again.";
      setNotice({ kind: "error", text });
    } finally {
      setSaving(null);
    }
  };

  const addCoveragePincode = () => {
    const value = coverageInput.trim();
    if (!PINCODE_RE.test(value) || coverage.includes(value)) return;
    setCoverage((prev) => [...prev, value].sort());
    setCoverageInput("");
  };

  const saveCoverage = async () => {
    if (!selectedId) return;
    const savedFor = selectedId;
    setSaving("coverage");
    setNotice(null);
    try {
      await putJson(`/api/directory/businesses/${savedFor}/coverage`, { pincodes: coverage });
      if (selectedIdRef.current !== savedFor) return;
      setNotice({ kind: "ok", text: "Coverage saved — customers in these pincodes can now find you." });
    } catch (err) {
      if (selectedIdRef.current !== savedFor) return;
      setNotice({
        kind: "error",
        text:
          err instanceof ApiError && err.status === 422
            ? "Coverage not saved — check the pincodes (6 digits each, up to 500)."
            : "Could not save coverage — please try again.",
      });
    } finally {
      setSaving(null);
    }
  };

  const updateWindow = (index: number, patch: Partial<DeliveryWindow>) => {
    setWindows((prev) => prev.map((w, i) => (i === index ? { ...w, ...patch } : w)));
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
        <Skeleton width="100%" height="200px" />
      </div>
    );
  }

  const selected = businesses.find((b) => b.id === selectedId) ?? null;
  const isDisabled = selected?.status === "disabled";

  return (
    <div className="mt-4 space-y-4">
      {businesses.length === 0 ? (
        <Card className="space-y-3 p-4">
          <p className="text-[13px] font-extrabold text-ink">Create your listing</p>
          <label className={LABEL}>
            Business name
            <input className={FIELD} value={newName} maxLength={200} onChange={(e) => setNewName(e.target.value)} />
          </label>
          <label className={LABEL}>
            Type
            <select className={FIELD} value={newType} onChange={(e) => setNewType(e.target.value as BusinessType)}>
              {TYPES.map((t) => (
                <option key={t} value={t}>{t}</option>
              ))}
            </select>
          </label>
          <label className={LABEL}>
            Primary pincode
            <input className={FIELD} value={newPincode} maxLength={6} inputMode="numeric" onChange={(e) => setNewPincode(e.target.value)} />
          </label>
          {createError ? <AlertNotice>{createError}</AlertNotice> : null}
          <Button type="button" variant="brand" disabled={creating} onClick={() => void create()}>
            {creating ? "Creating..." : "Create listing"}
          </Button>
        </Card>
      ) : (
        <>
          <label className={LABEL}>
            Business
            <select className={FIELD} value={selectedId ?? ""} onChange={(e) => setSelectedId(e.target.value)}>
              {businesses.map((b) => (
                <option key={b.id} value={b.id}>{b.name}</option>
              ))}
            </select>
          </label>

          {selected?.status === "suspended" ? (
            <div data-testid="suspension-notice">
              <AlertNotice>
                This listing is suspended and hidden from Milk.in
                {selected.enforcement_reason ? <> — reason: {selected.enforcement_reason}</> : null}.
                You can still edit it; contact support to resolve the suspension.
              </AlertNotice>
            </div>
          ) : null}

          {isDisabled ? (
            <div data-testid="disabled-notice">
              <AlertNotice>
                This listing has been disabled by Milk.in administrators. Dashboard access to it is
                locked and nothing is served — contact support.
              </AlertNotice>
            </div>
          ) : null}

          {notice ? (
            notice.kind === "ok" ? <OkNotice>{notice.text}</OkNotice> : <AlertNotice>{notice.text}</AlertNotice>
          ) : null}

          {isDisabled ? null : (
          <>
          <Card className="space-y-3 p-4">
            <p className="text-[13px] font-extrabold text-ink">Listing details</p>
            <label className={LABEL}>
              Name
              <input className={FIELD} value={name} maxLength={200} onChange={(e) => setName(e.target.value)} />
            </label>
            <label className={LABEL}>
              Type
              <select className={FIELD} value={type} onChange={(e) => setType(e.target.value as BusinessType)}>
                {TYPES.map((t) => (
                  <option key={t} value={t}>{t}</option>
                ))}
              </select>
            </label>
            <label className={LABEL}>
              Primary pincode
              <input className={FIELD} value={primaryPincode} maxLength={6} inputMode="numeric" onChange={(e) => setPrimaryPincode(e.target.value)} />
            </label>
            <label className={LABEL}>
              About (English)
              <textarea className={cn(FIELD, "min-h-[80px]")} value={descriptionEn} maxLength={2000} onChange={(e) => setDescriptionEn(e.target.value)} />
            </label>
            <label className={LABEL}>
              About (Tamil)
              <textarea className={cn(FIELD, "min-h-[80px]")} value={descriptionTa} maxLength={2000} lang="ta" onChange={(e) => setDescriptionTa(e.target.value)} />
            </label>
            <label className={LABEL}>
              About (Hindi)
              <textarea className={cn(FIELD, "min-h-[80px]")} value={descriptionHi} maxLength={2000} lang="hi" onChange={(e) => setDescriptionHi(e.target.value)} />
            </label>
            <p className="text-[12px] text-sub">
              Shown as “About” on your public profile. Plain text only — up to 2000 characters per
              language.
            </p>

            <p className="text-[13px] font-extrabold text-ink">Delivery windows</p>
            {windows.map((window, index) => (
              <div key={index} className="space-y-2 rounded-card border border-line p-3">
                <div className="flex flex-wrap gap-2">
                  {DAYS.map((day) => (
                    <label key={day} className="flex min-h-[44px] items-center gap-1 text-[13px] text-ink">
                      <input
                        type="checkbox"
                        checked={window.days.includes(day)}
                        onChange={(e) =>
                          updateWindow(index, {
                            days: e.target.checked
                              ? [...window.days, day]
                              : window.days.filter((d) => d !== day),
                          })
                        }
                      />
                      {day}
                    </label>
                  ))}
                </div>
                <div className="flex items-end gap-2">
                  <label className={LABEL}>
                    Open
                    <input type="time" className={FIELD} value={window.open} onChange={(e) => updateWindow(index, { open: e.target.value })} />
                  </label>
                  <label className={LABEL}>
                    Close
                    <input type="time" className={FIELD} value={window.close} onChange={(e) => updateWindow(index, { close: e.target.value })} />
                  </label>
                  <Button type="button" variant="ghost" onClick={() => setWindows((prev) => prev.filter((_, i) => i !== index))}>
                    Remove
                  </Button>
                </div>
              </div>
            ))}
            {windows.length < 7 ? (
              <Button
                type="button"
                variant="ghost"
                onClick={() => setWindows((prev) => [...prev, { days: ["mon"], open: "06:00", close: "09:00" }])}
              >
                Add delivery window
              </Button>
            ) : null}

            <Button type="button" variant="brand" disabled={saving === "listing"} onClick={() => void saveListing()}>
              {saving === "listing" ? "Saving..." : "Save listing"}
            </Button>
          </Card>

          <Card className="space-y-3 p-4">
            <p className="text-[13px] font-extrabold text-ink">Coverage pincodes</p>
            <p className="text-[12px] text-sub">
              Customers searching these pincodes will find this business. Up to 500.
            </p>
            {detailLoading ? (
              <Skeleton width="100%" height="44px" />
            ) : (
              <div className="flex flex-wrap gap-2">
                {coverage.map((pincode) => (
                  <span key={pincode} className="inline-flex items-center gap-1 rounded-pill bg-line px-[9px] py-[3px] text-[12px] font-semibold text-ink">
                    {pincode}
                    <button
                      type="button"
                      aria-label={`Remove ${pincode}`}
                      className="min-h-[24px] min-w-[24px]"
                      onClick={() => setCoverage((prev) => prev.filter((p) => p !== pincode))}
                    >
                      ×
                    </button>
                  </span>
                ))}
                {coverage.length === 0 ? <span className="text-[12px] text-sub">No coverage yet.</span> : null}
              </div>
            )}
            <div className="flex items-end gap-2">
              <label className={cn(LABEL, "flex-1")}>
                Add pincode
                <input
                  className={FIELD}
                  value={coverageInput}
                  maxLength={6}
                  inputMode="numeric"
                  onChange={(e) => setCoverageInput(e.target.value)}
                  onKeyDown={(e) => {
                    if (e.key === "Enter") {
                      e.preventDefault();
                      addCoveragePincode();
                    }
                  }}
                />
              </label>
              <Button type="button" variant="ghost" onClick={addCoveragePincode}>
                Add
              </Button>
            </div>
            <Button type="button" variant="brand" disabled={saving === "coverage"} onClick={() => void saveCoverage()}>
              {saving === "coverage" ? "Saving..." : "Save coverage"}
            </Button>
          </Card>
          </>
          )}
        </>
      )}
    </div>
  );
}
