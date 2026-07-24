"use client";

import { Button, Card, Skeleton, cn } from "@agri/ui";
import { useEffect, useState, type ReactNode } from "react";

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
  primary_pincode: string;
  description: Record<string, string> | null;
  delivery_windows: DeliveryWindow[] | null;
  verification_status: string;
  subscription_tier: string;
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
  const [windows, setWindows] = useState<DeliveryWindow[]>([]);
  const [coverage, setCoverage] = useState<string[]>([]);
  const [coverageInput, setCoverageInput] = useState("");
  const [detailLoading, setDetailLoading] = useState(false);
  const [saving, setSaving] = useState<"listing" | "coverage" | null>(null);
  const [notice, setNotice] = useState<{ kind: "ok" | "error"; text: string } | null>(null);

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

  useEffect(() => {
    const selected = businesses?.find((b) => b.id === selectedId);
    if (!selected) return;
    setName(selected.name);
    setType(selected.type);
    setPrimaryPincode(selected.primary_pincode);
    setDescriptionEn(selected.description?.en ?? "");
    setWindows(selected.delivery_windows ?? []);
    setDetailLoading(true);
    setNotice(null);
    void (async () => {
      try {
        const detail = await getJson(`/api/directory/businesses/${selected.slug}`);
        setCoverage((detail.coverage_pincodes as string[] | undefined) ?? []);
      } catch {
        setCoverage([]);
      } finally {
        setDetailLoading(false);
      }
    })();
  }, [selectedId, businesses]);

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
    setSaving("listing");
    setNotice(null);
    try {
      const description = descriptionEn.trim()
        ? { ...(businesses?.find((b) => b.id === selectedId)?.description ?? {}), en: descriptionEn.trim() }
        : null;
      await patchJson(`/api/directory/businesses/${selectedId}`, {
        name: name.trim(),
        type,
        primary_pincode: primaryPincode,
        description,
        delivery_windows: windows,
      });
      setNotice({ kind: "ok", text: "Listing saved." });
      void loadBusinesses();
    } catch (err) {
      setNotice({
        kind: "error",
        text:
          err instanceof ApiError && err.status === 422
            ? "Check the highlighted fields — delivery windows need valid days and open < close times."
            : "Could not save — please try again.",
      });
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
    setSaving("coverage");
    setNotice(null);
    try {
      await putJson(`/api/directory/businesses/${selectedId}/coverage`, { pincodes: coverage });
      setNotice({ kind: "ok", text: "Coverage saved — customers in these pincodes can now find you." });
    } catch {
      setNotice({ kind: "error", text: "Could not save coverage — please try again." });
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

          {notice ? (
            notice.kind === "ok" ? <OkNotice>{notice.text}</OkNotice> : <AlertNotice>{notice.text}</AlertNotice>
          ) : null}

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
              Description (English)
              <textarea className={cn(FIELD, "min-h-[80px]")} value={descriptionEn} maxLength={2000} onChange={(e) => setDescriptionEn(e.target.value)} />
            </label>

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
    </div>
  );
}
