"use client";

/**
 * U2 Group B: rebuilt onto the shared console catalog — ConsoleField /
 * ConsolePanel / ConsoleNotice / ConfirmAction from @agri/ui render this
 * page AND the /demo kitchen sink; this file only binds them to the D15
 * owner API. All chrome reads ui.console.listings.* (en/ta/hi). The data
 * flow (refs against stale async clobbering, per-business notices,
 * disabled/suspended semantics) is D26's, unchanged.
 */

import {
  Button,
  ConfirmAction,
  ConsoleField,
  ConsoleNotice,
  ConsolePanel,
  Skeleton,
  cn,
  consoleControlClass,
} from "@agri/ui";
import { useTranslations } from "next-intl";
import { useEffect, useRef, useState } from "react";

import { ApiError, deleteJson, getJson, patchJson, postJson, putJson } from "@/lib/api";

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

const DAYS = ["mon", "tue", "wed", "thu", "fri", "sat", "sun"] as const;
const TYPES: BusinessType[] = ["vendor", "shop", "lab", "farm"];
const PINCODE_RE = /^\d{6}$/;

export function ListingsClient() {
  const t = useTranslations("ui.console.listings");
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
      return list;
    } catch {
      setLoadError(true);
      return null;
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
      setCreateError(t("createValidation"));
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
        err instanceof ApiError
          ? t("createFailedDetail", { detail: err.detail })
          : t("createFailed"),
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
      const existingDescription =
        businessesRef.current?.find((b) => b.id === savedFor)?.description ?? null;
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
      setBusinesses(
        (prev) =>
          prev?.map((b) =>
            b.id === savedFor
              ? {
                  ...b,
                  name: trimmedName,
                  type,
                  primary_pincode: primaryPincode,
                  description,
                  delivery_windows: windows,
                }
              : b,
          ) ?? prev,
      );
      if (selectedIdRef.current !== savedFor) return;
      setNotice({ kind: "ok", text: t("savedOk") });
    } catch (err) {
      if (selectedIdRef.current !== savedFor) return;
      const text =
        err instanceof ApiError && err.status === 403 && err.detail === "business_disabled"
          ? t("saveLocked")
          : err instanceof ApiError && err.status === 422
            ? t("save422")
            : t("saveFailed");
      setNotice({ kind: "error", text });
    } finally {
      setSaving(null);
    }
  };

  const deleteListing = async () => {
    if (!selectedId) return;
    const deletedId = selectedId;
    try {
      await deleteJson(`/api/directory/businesses/${deletedId}`);
    } catch {
      setNotice({ kind: "error", text: t("deleteFailed") });
      throw new Error("delete_failed"); // keeps the confirm dialog open
    }
    const remaining = (businessesRef.current ?? []).filter((b) => b.id !== deletedId);
    setBusinesses(remaining);
    setSelectedId(remaining[0]?.id ?? null);
    setNotice({ kind: "ok", text: t("deletedOk") });
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
      setNotice({ kind: "ok", text: t("coverageSavedOk") });
    } catch (err) {
      if (selectedIdRef.current !== savedFor) return;
      setNotice({
        kind: "error",
        text:
          err instanceof ApiError && err.status === 422 ? t("coverage422") : t("coverageFailed"),
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
        <ConsoleNotice tone="alert">{t("loadFailed")}</ConsoleNotice>
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
        <ConsolePanel title={t("createTitle")}>
          <div className="space-y-3">
            <ConsoleField id="new-name" label={t("businessName")}>
              <input
                id="new-name"
                className={consoleControlClass}
                value={newName}
                maxLength={200}
                onChange={(e) => setNewName(e.target.value)}
              />
            </ConsoleField>
            <ConsoleField id="new-type" label={t("type")}>
              <select
                id="new-type"
                className={consoleControlClass}
                value={newType}
                onChange={(e) => setNewType(e.target.value as BusinessType)}
              >
                {TYPES.map((value) => (
                  <option key={value} value={value}>
                    {t(`types.${value}`)}
                  </option>
                ))}
              </select>
            </ConsoleField>
            <ConsoleField id="new-pincode" label={t("primaryPincode")} error={createError ?? undefined}>
              <input
                id="new-pincode"
                className={consoleControlClass}
                value={newPincode}
                maxLength={6}
                inputMode="numeric"
                aria-invalid={createError ? "true" : undefined}
                aria-describedby={createError ? "new-pincode-error" : undefined}
                onChange={(e) => setNewPincode(e.target.value)}
              />
            </ConsoleField>
            <Button
              type="button"
              variant="brand"
              disabled={creating}
              onClick={() => void create()}
            >
              {creating ? t("creating") : t("createCta")}
            </Button>
          </div>
        </ConsolePanel>
      ) : (
        <>
          <ConsoleField id="business-picker" label={t("businessPicker")}>
            <select
              id="business-picker"
              className={consoleControlClass}
              value={selectedId ?? ""}
              onChange={(e) => setSelectedId(e.target.value)}
            >
              {businesses.map((b) => (
                <option key={b.id} value={b.id}>
                  {b.name}
                </option>
              ))}
            </select>
          </ConsoleField>

          {selected?.status === "suspended" ? (
            <div data-testid="suspension-notice">
              <ConsoleNotice tone="alert">
                {t("suspendedNotice", {
                  reason: selected.enforcement_reason
                    ? t("suspendedReasonPrefix", { reason: selected.enforcement_reason })
                    : "",
                })}
              </ConsoleNotice>
            </div>
          ) : null}

          {isDisabled ? (
            <div data-testid="disabled-notice">
              <ConsoleNotice tone="alert">{t("disabledNotice")}</ConsoleNotice>
            </div>
          ) : null}

          {notice ? (
            <ConsoleNotice tone={notice.kind === "ok" ? "ok" : "alert"}>
              {notice.text}
            </ConsoleNotice>
          ) : null}

          {isDisabled ? null : (
            <>
              <ConsolePanel title={t("detailsTitle")}>
                <div className="space-y-3">
                  <ConsoleField id="edit-name" label={t("name")}>
                    <input
                      id="edit-name"
                      className={consoleControlClass}
                      value={name}
                      maxLength={200}
                      onChange={(e) => setName(e.target.value)}
                    />
                  </ConsoleField>
                  <ConsoleField id="edit-type" label={t("type")}>
                    <select
                      id="edit-type"
                      className={consoleControlClass}
                      value={type}
                      onChange={(e) => setType(e.target.value as BusinessType)}
                    >
                      {TYPES.map((value) => (
                        <option key={value} value={value}>
                          {t(`types.${value}`)}
                        </option>
                      ))}
                    </select>
                  </ConsoleField>
                  <ConsoleField id="edit-pincode" label={t("primaryPincode")}>
                    <input
                      id="edit-pincode"
                      className={consoleControlClass}
                      value={primaryPincode}
                      maxLength={6}
                      inputMode="numeric"
                      onChange={(e) => setPrimaryPincode(e.target.value)}
                    />
                  </ConsoleField>
                  <ConsoleField id="edit-about-en" label={t("aboutEn")}>
                    <textarea
                      id="edit-about-en"
                      className={cn(consoleControlClass, "min-h-[80px]")}
                      value={descriptionEn}
                      maxLength={2000}
                      onChange={(e) => setDescriptionEn(e.target.value)}
                    />
                  </ConsoleField>
                  <ConsoleField id="edit-about-ta" label={t("aboutTa")}>
                    <textarea
                      id="edit-about-ta"
                      className={cn(consoleControlClass, "min-h-[80px]")}
                      value={descriptionTa}
                      maxLength={2000}
                      lang="ta"
                      onChange={(e) => setDescriptionTa(e.target.value)}
                    />
                  </ConsoleField>
                  <ConsoleField id="edit-about-hi" label={t("aboutHi")}>
                    <textarea
                      id="edit-about-hi"
                      className={cn(consoleControlClass, "min-h-[80px]")}
                      value={descriptionHi}
                      maxLength={2000}
                      lang="hi"
                      onChange={(e) => setDescriptionHi(e.target.value)}
                    />
                  </ConsoleField>
                  <p className="text-[12px] text-sub">{t("aboutHint")}</p>

                  <p className="text-[13px] font-extrabold text-ink">{t("windowsTitle")}</p>
                  {windows.map((window, index) => (
                    <div key={index} className="space-y-2 rounded-card border border-line p-3">
                      <div className="flex flex-wrap gap-2">
                        {DAYS.map((day) => (
                          <label
                            key={day}
                            className="flex min-h-[44px] items-center gap-1 text-[13px] text-ink"
                          >
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
                            {t(`days.${day}`)}
                          </label>
                        ))}
                      </div>
                      <div className="flex items-end gap-2">
                        <ConsoleField id={`window-open-${index}`} label={t("open")}>
                          <input
                            id={`window-open-${index}`}
                            type="time"
                            className={consoleControlClass}
                            value={window.open}
                            onChange={(e) => updateWindow(index, { open: e.target.value })}
                          />
                        </ConsoleField>
                        <ConsoleField id={`window-close-${index}`} label={t("close")}>
                          <input
                            id={`window-close-${index}`}
                            type="time"
                            className={consoleControlClass}
                            value={window.close}
                            onChange={(e) => updateWindow(index, { close: e.target.value })}
                          />
                        </ConsoleField>
                        <Button
                          type="button"
                          variant="ghost"
                          onClick={() => setWindows((prev) => prev.filter((_, i) => i !== index))}
                        >
                          {t("removeWindow")}
                        </Button>
                      </div>
                    </div>
                  ))}
                  {windows.length < 7 ? (
                    <Button
                      type="button"
                      variant="ghost"
                      onClick={() =>
                        setWindows((prev) => [
                          ...prev,
                          { days: ["mon"], open: "06:00", close: "09:00" },
                        ])
                      }
                    >
                      {t("addWindow")}
                    </Button>
                  ) : null}

                  <Button
                    type="button"
                    variant="brand"
                    disabled={saving === "listing"}
                    onClick={() => void saveListing()}
                  >
                    {saving === "listing" ? t("saving") : t("saveListing")}
                  </Button>
                </div>
              </ConsolePanel>

              <ConsolePanel title={t("coverageTitle")}>
                <div className="space-y-3">
                  <p className="text-[12px] text-sub">{t("coverageHint")}</p>
                  {detailLoading ? (
                    <Skeleton width="100%" height="44px" />
                  ) : (
                    <div className="flex flex-wrap gap-2">
                      {coverage.map((pincode) => (
                        <span
                          key={pincode}
                          className="inline-flex items-center gap-1 rounded-pill bg-line px-[9px] py-[3px] text-[12px] font-semibold text-ink"
                        >
                          {pincode}
                          <button
                            type="button"
                            aria-label={t("removePincode", { pincode })}
                            className="min-h-[24px] min-w-[24px]"
                            onClick={() => setCoverage((prev) => prev.filter((p) => p !== pincode))}
                          >
                            ×
                          </button>
                        </span>
                      ))}
                      {coverage.length === 0 ? (
                        <span className="text-[12px] text-sub">{t("noCoverage")}</span>
                      ) : null}
                    </div>
                  )}
                  <div className="flex items-end gap-2">
                    <ConsoleField id="coverage-add" label={t("addPincode")} className="flex-1">
                      <input
                        id="coverage-add"
                        className={consoleControlClass}
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
                    </ConsoleField>
                    <Button type="button" variant="ghost" onClick={addCoveragePincode}>
                      {t("add")}
                    </Button>
                  </div>
                  <Button
                    type="button"
                    variant="brand"
                    disabled={saving === "coverage"}
                    onClick={() => void saveCoverage()}
                  >
                    {saving === "coverage" ? t("saving") : t("saveCoverage")}
                  </Button>
                </div>
              </ConsolePanel>

              {selected ? (
                <ConsolePanel title={t("dangerTitle")}>
                  <div className="flex max-w-[280px]">
                    <ConfirmAction
                      trigger={
                        <Button type="button" variant="ghost">
                          {t("deleteCta")}
                        </Button>
                      }
                      title={t("deleteConfirmTitle")}
                      description={t("deleteConfirmBody", { name: selected.name })}
                      confirmLabel={t("deleteCta")}
                      cancelLabel={t("deleteCancel")}
                      onConfirm={deleteListing}
                    />
                  </div>
                </ConsolePanel>
              ) : null}
            </>
          )}
        </>
      )}
    </div>
  );
}
