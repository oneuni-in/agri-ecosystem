"use client";

/**
 * LiveLocationPill (D19 Task 8): header pill that opens a modal to view/set
 * the visitor's location. Mirrors the `coins-balance-pill.tsx` pattern — a
 * dumb pill in `pills.tsx` + a "use client" live wrapper that owns
 * fetch/state — but here the pill is always rendered (there is always
 * *something* to show or a call-to-action to set it), so it does not hide
 * itself the way `CoinsBalancePill` does while signed out.
 *
 * Deviation from the original brief: the brief said "strings via
 * `useTranslations('ui.location')`", but `@agri/ui` does not depend on
 * `next-intl` (only the apps do — see `apps/web-id/package.json`). The
 * existing precedent for translated text inside this package is
 * `NotificationsPanel`, which takes a `strings` prop instead of calling
 * next-intl itself. This component follows that precedent: the consuming
 * app calls `useTranslations("ui.location")` and passes the strings down.
 */
import { useCallback, useEffect, useState, type FormEvent } from "react";

import {
  type LocContext,
  LOC_COOKIE,
  locLabel,
  parseLocationResponse,
  parseLocCookie,
  serializeLocCookie,
} from "../lib/location";
import { Modal } from "./modal";
import { GpsPill, LocationPill } from "./pills";
import { PincodeInput } from "./pincode-input";

export interface LiveLocationPillStrings {
  /** Trigger label when no location is known yet. */
  set: string;
  title: string;
  close: string;
  apply: string;
  gps: string;
  pincodeLabel: string;
  find: string;
}

export const DEFAULT_LIVE_LOCATION_STRINGS: LiveLocationPillStrings = {
  set: "Set location",
  title: "Set your location",
  close: "Close",
  apply: "Apply",
  gps: "📍 Use my location",
  pincodeLabel: "Enter pincode",
  find: "Find",
};

function readCookieValue(): string | undefined {
  if (typeof document === "undefined") return undefined;
  const match = document.cookie.match(new RegExp(`(?:^|; )${LOC_COOKIE}=([^;]*)`));
  return match?.[1];
}

/**
 * Fetches and validates a location lookup. Returns `null` on ANY failure —
 * network error, non-2xx, or a malformed body (`parseLocationResponse`) —
 * so callers never mistake a failed request for a real "we don't know"
 * answer. A real "we don't know" answer is a well-shaped body with
 * `source: "none"`, which IS applied by callers; only a failed REQUEST
 * must never overwrite the user's existing location.
 */
async function fetchLocation(
  endpoint: string,
  query: string,
  fetchImpl: typeof fetch,
): Promise<LocContext | null> {
  try {
    const res = await fetchImpl(`${endpoint}${query}`, { credentials: "include" });
    if (!res.ok) return null;
    const body: unknown = await res.json();
    return parseLocationResponse(body);
  } catch {
    return null; // network blip — caller keeps whatever it already had
  }
}

export function LiveLocationPill({
  contextEndpoint = "/api/identity/location",
  profileEndpoint = "/api/identity/profile",
  isAuthed = false,
  onChanged,
  strings = DEFAULT_LIVE_LOCATION_STRINGS,
  className,
  fallbackLabel,
  changeLabel,
  fetchImpl = fetch,
}: {
  contextEndpoint?: string;
  profileEndpoint?: string;
  isAuthed?: boolean;
  /** Called after a location is applied; defaults to a full page reload. */
  onChanged?: (loc: LocContext) => void;
  strings?: LiveLocationPillStrings;
  className?: string;
  /**
   * Shown when the visitor has no location of their own yet — a first-time
   * guest who has not logged in, typed a pincode or granted GPS. The page
   * behind this pill renders the SAME fallback location server-side, so the
   * header and the content can never disagree. Omit it and the pill falls
   * back to the old "Set location" call-to-action.
   */
  fallbackLabel?: string;
  /** Accessible name for the explicit "change pincode" affordance. */
  changeLabel?: string;
  fetchImpl?: typeof fetch;
}) {
  const [loc, setLoc] = useState<LocContext | null>(null);
  const [pincodeDraft, setPincodeDraft] = useState("");
  // Bumping this key remounts (and thus closes) the uncontrolled Modal —
  // the D11 idiom for forcing an uncontrolled Radix Dialog shut.
  const [applyGen, setApplyGen] = useState(0);

  useEffect(() => {
    const initial = parseLocCookie(readCookieValue());
    setLoc(initial);

    let cancelled = false;
    const query = initial?.pincode ? `?pincode=${encodeURIComponent(initial.pincode)}` : "";
    fetchLocation(contextEndpoint, query, fetchImpl).then((next) => {
      if (cancelled || !next) return;
      setLoc(next);
      document.cookie = serializeLocCookie(next);
    });

    return () => {
      cancelled = true;
    };
    // Deliberately run once per mount: contextEndpoint is effectively static
    // and fetchImpl only ever varies in tests, not across a component's life.
  }, []);

  const apply = useCallback(
    (next: LocContext) => {
      document.cookie = serializeLocCookie(next);
      setLoc(next);
      setApplyGen((n) => n + 1);

      if (isAuthed && next.pincode) {
        fetchImpl(profileEndpoint, {
          method: "PATCH",
          credentials: "include",
          headers: { "content-type": "application/json" },
          body: JSON.stringify({ pincode: next.pincode }),
        }).catch(() => {
          // fire-and-log; the cookie already reflects the chosen location
        });
      }

      if (onChanged) onChanged(next);
      else window.location.reload();
    },
    [fetchImpl, isAuthed, onChanged, profileEndpoint],
  );

  const resolvePincode = useCallback(() => {
    const pincode = pincodeDraft.trim();
    if (pincode.length !== 6) return;
    fetchLocation(contextEndpoint, `?pincode=${encodeURIComponent(pincode)}`, fetchImpl).then(
      (next) => {
        // A failed REQUEST (network/non-2xx/malformed body) must never
        // persist the user's unvalidated typed digits — the server is
        // the validator. An unknown pincode is still a real answer
        // (source "none") and IS applied; only `null` here is refused.
        if (!next) return;
        apply(next);
      },
    );
  }, [apply, contextEndpoint, fetchImpl, pincodeDraft]);

  const submitPincode = useCallback(
    (e: FormEvent<HTMLFormElement>) => {
      e.preventDefault();
      resolvePincode();
    },
    [resolvePincode],
  );

  const useGps = useCallback(() => {
    if (typeof navigator === "undefined" || !navigator.geolocation) return;
    navigator.geolocation.getCurrentPosition(
      (position) => {
        const { latitude, longitude } = position.coords;
        fetchLocation(contextEndpoint, `?lat=${latitude}&lng=${longitude}`, fetchImpl).then(
          (next) => {
            if (!next) return;
            apply(next);
          },
        );
      },
      () => {
        // permission denied / position unavailable — leave location as-is
      },
    );
  }, [apply, contextEndpoint, fetchImpl]);

  return (
    <Modal
      key={applyGen}
      trigger={
        <LocationPill
          className={className}
          aria-label={`${locLabel(loc) ?? fallbackLabel ?? strings.set}${
            changeLabel ? ` — ${changeLabel}` : ""
          }`}
        >
          📍{" "}
          <span className="max-sm:hidden">{locLabel(loc) ?? fallbackLabel ?? strings.set}</span>{" "}
          {/* An explicit change affordance next to the pincode, not just a
              disclosure caret: the location is now what the whole page renders
              from, so "you can change this" has to be legible at a glance. */}
          <span aria-hidden="true" className="text-[11px]">
            ✏️
          </span>
        </LocationPill>
      }
      title={strings.title}
      closeLabel={strings.close}
    >
      <div className="grid gap-3">
        <form onSubmit={submitPincode} className="grid gap-2">
          <PincodeInput
            findLabel={strings.find}
            aria-label={strings.pincodeLabel}
            placeholder={strings.pincodeLabel}
            value={pincodeDraft}
            findDisabled={pincodeDraft.trim().length !== 6}
            onFind={resolvePincode}
            onChange={(e) => setPincodeDraft(e.target.value.replace(/\D/g, ""))}
          />
        </form>
        <GpsPill type="button" className="w-full justify-center" onClick={useGps}>
          {strings.gps}
        </GpsPill>
      </div>
    </Modal>
  );
}
