"use client";

/**
 * Visibility toggles and the DPDP block (AG-U5 P5).
 *
 * Both halves write, which is why this is the page's one island. Everything
 * it talks to already existed — `PATCH /identity/profile` for visibility, and
 * ID-U1's `/identity/dpdp/*` for the rights — so this is a surface over
 * shipped endpoints, not new machinery.
 *
 * ONE SAVE MODEL, as with the notification channels: the toggle is the save,
 * a tick confirms it, and a failure puts the switch back. Nothing here has a
 * Save button to forget.
 *
 * Two things this deliberately does NOT do:
 *  - It does not offer phone or email as visibility toggles. They are never
 *    public, so they are not a setting; `VISIBILITY_KEYS` has five members
 *    and neither is among them. Rendering them switched-off would imply they
 *    could be switched on.
 *  - It does not reference a privacy policy page. Those ship at D56; until
 *    then any policy reference is plain text (the consent-line rule).
 */

import { Card } from "@agri/ui";
import { useState } from "react";

const VISIBILITY_KEYS = ["name", "location", "language", "interests", "avatar"] as const;
type VisibilityKey = (typeof VISIBILITY_KEYS)[number];

export interface Reveal {
  revealed_at: string;
  business_name: string | null;
  source: string;
}

export interface ErasureState {
  status: string;
  execute_after: string | null;
}

export interface PrivacyCopy {
  visibility: string;
  visibilityHint: string;
  labels: Record<VisibilityKey, string>;
  on: string;
  off: string;
  saved: string;
  saveFailed: string;
  dpdp: string;
  dpdpHint: string;
  export: string;
  exportHint: string;
  reveals: string;
  revealsHint: string;
  revealsEmpty: string;
  erase: string;
  eraseHint: string;
  eraseAsk: string;
  eraseBusy: string;
  erasePending: string;
  eraseCancel: string;
  eraseFailed: string;
}

export function PrivacyClient({
  initialVisibility,
  reveals,
  initialErasure,
  copy,
}: {
  initialVisibility: Record<string, boolean>;
  reveals: Reveal[];
  initialErasure: ErasureState;
  copy: PrivacyCopy;
}) {
  const [visibility, setVisibility] = useState(initialVisibility);
  const [savedKey, setSavedKey] = useState<VisibilityKey | null>(null);
  const [failedKey, setFailedKey] = useState<VisibilityKey | null>(null);
  const [busyKey, setBusyKey] = useState<VisibilityKey | null>(null);
  const [erasure, setErasure] = useState(initialErasure);
  const [eraseBusy, setEraseBusy] = useState(false);
  const [eraseFailed, setEraseFailed] = useState(false);

  const toggle = async (key: VisibilityKey) => {
    if (busyKey) return;
    const next = !visibility[key];
    setBusyKey(key);
    setFailedKey(null);
    setSavedKey(null);
    setVisibility((current) => ({ ...current, [key]: next }));
    try {
      const res = await fetch("/api/identity/profile", {
        method: "PATCH",
        headers: { "content-type": "application/json" },
        body: JSON.stringify({ visibility: { [key]: next } }),
      });
      if (!res.ok) throw new Error(String(res.status));
      setSavedKey(key);
      setTimeout(() => setSavedKey(null), 2000);
    } catch {
      setVisibility((current) => ({ ...current, [key]: !next }));
      setFailedKey(key);
    } finally {
      setBusyKey(null);
    }
  };

  const requestErasure = async () => {
    setEraseBusy(true);
    setEraseFailed(false);
    try {
      const res = await fetch("/api/account/erasure", { method: "POST" });
      if (!res.ok) throw new Error(String(res.status));
      const body = (await res.json()) as ErasureState;
      setErasure(body);
    } catch {
      setEraseFailed(true);
    } finally {
      setEraseBusy(false);
    }
  };

  const cancelErasure = async () => {
    setEraseBusy(true);
    setEraseFailed(false);
    try {
      const res = await fetch("/api/account/erasure", { method: "DELETE" });
      if (!res.ok && res.status !== 404) throw new Error(String(res.status));
      setErasure({ status: "none", execute_after: null });
    } catch {
      setEraseFailed(true);
    } finally {
      setEraseBusy(false);
    }
  };

  const pending = erasure.status !== "none" && erasure.status !== "cancelled";

  return (
    <div className="space-y-3">
      <Card className="p-3.5">
        <h2 className="font-display text-[15px] font-extrabold text-ink">
          <span aria-hidden="true" className="mr-1.5">
            👁️
          </span>
          {copy.visibility}
        </h2>
        <p className="mb-3 mt-1 text-[12px] text-sub">{copy.visibilityHint}</p>
        <ul className="space-y-2">
          {VISIBILITY_KEYS.map((key) => {
            const on = Boolean(visibility[key]);
            return (
              <li
                key={key}
                className="flex items-center gap-2 rounded-card border border-cream-line bg-cream px-3 py-2.5"
              >
                <span className="flex-1 text-[13px] font-semibold text-ink">
                  {copy.labels[key]}
                </span>
                {savedKey === key ? (
                  <span aria-live="polite" className="text-[11.5px] font-semibold text-verified-fg">
                    ✓ {copy.saved}
                  </span>
                ) : null}
                {failedKey === key ? (
                  <span role="alert" className="text-[11.5px] font-semibold text-down">
                    {copy.saveFailed}
                  </span>
                ) : null}
                <button
                  type="button"
                  role="switch"
                  aria-checked={on}
                  aria-label={copy.labels[key]}
                  disabled={busyKey === key}
                  onClick={() => void toggle(key)}
                  className={`tap-target inline-flex min-h-[44px] min-w-[86px] items-center justify-center rounded-pill px-3 text-[12px] font-bold disabled:opacity-60 ${
                    on ? "bg-verified-bg text-verified-fg" : "bg-line text-sub"
                  }`}
                >
                  {on ? copy.on : copy.off}
                </button>
              </li>
            );
          })}
        </ul>
      </Card>

      <Card className="p-3.5">
        <h2 className="font-display text-[15px] font-extrabold text-ink">
          <span aria-hidden="true" className="mr-1.5">
            🔒
          </span>
          {copy.dpdp}
        </h2>
        <p className="mb-3 mt-1 text-[12px] text-sub">{copy.dpdpHint}</p>

        <div className="rounded-card border border-cream-line bg-cream px-3 py-3">
          <p className="text-[13px] font-semibold text-ink">{copy.export}</p>
          <p className="mt-0.5 text-[11.5px] text-sub">{copy.exportHint}</p>
          {/* A plain link, not a fetch+Blob: the route already answers with
              content-disposition, so the browser saves the file and the
              download survives with no JavaScript involved. */}
          <a
            href="/api/account/export"
            className="tap-target mt-2 inline-flex min-h-[40px] items-center rounded-pill border border-cream-line bg-card px-3.5 text-[12.5px] font-semibold text-ink no-underline"
          >
            {copy.export}
          </a>
        </div>

        <div className="mt-2.5 rounded-card border border-cream-line bg-cream px-3 py-3">
          <p className="text-[13px] font-semibold text-ink">{copy.reveals}</p>
          <p className="mt-0.5 text-[11.5px] text-sub">{copy.revealsHint}</p>
          {reveals.length === 0 ? (
            <p className="mt-2 text-[12.5px] text-muted">{copy.revealsEmpty}</p>
          ) : (
            <ul className="mt-2 space-y-1">
              {reveals.map((reveal, index) => (
                <li key={`${reveal.revealed_at}-${index}`} className="text-[12.5px] text-ink">
                  {reveal.business_name ?? "—"}
                  <span className="text-muted"> · {reveal.revealed_at.slice(0, 10)}</span>
                </li>
              ))}
            </ul>
          )}
        </div>

        <div className="mt-2.5 rounded-card border border-alert-line bg-alert-bg px-3 py-3">
          <p className="text-[13px] font-semibold text-ink">{copy.erase}</p>
          <p className="mt-0.5 text-[11.5px] text-sub">{copy.eraseHint}</p>
          {pending ? (
            <>
              <p className="mt-2 text-[12.5px] font-semibold text-ink">
                {copy.erasePending.replace(
                  "{date}",
                  erasure.execute_after ? erasure.execute_after.slice(0, 10) : "—",
                )}
              </p>
              <button
                type="button"
                disabled={eraseBusy}
                onClick={() => void cancelErasure()}
                className="tap-target mt-2 inline-flex min-h-[40px] items-center rounded-pill border border-cream-line bg-card px-3.5 text-[12.5px] font-semibold text-ink disabled:opacity-60"
              >
                {eraseBusy ? copy.eraseBusy : copy.eraseCancel}
              </button>
            </>
          ) : (
            <button
              type="button"
              disabled={eraseBusy}
              onClick={() => void requestErasure()}
              className="tap-target mt-2 inline-flex min-h-[40px] items-center rounded-pill border border-down bg-card px-3.5 text-[12.5px] font-semibold text-down disabled:opacity-60"
            >
              {eraseBusy ? copy.eraseBusy : copy.eraseAsk}
            </button>
          )}
          {eraseFailed ? (
            <p role="alert" className="mt-2 text-[11.5px] font-semibold text-down">
              {copy.eraseFailed}
            </p>
          ) : null}
        </div>
      </Card>
    </div>
  );
}
