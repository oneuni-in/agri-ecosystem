"use client";

import { GpsPill, parseLocationResponse, PincodeInput, serializeLocCookie } from "@agri/ui";
import { useTranslations } from "next-intl";
import { useState } from "react";

import { useRouter } from "@/i18n/navigation";

/**
 * Interactive controls rendered as the `children` of the `@agri/ui`
 * `PincodeHero` shell (`.pinbox` + `.gps`).
 *
 * Two modes, because two callers want different things from the same control:
 *
 * · `setsLocation` (the home): submitting a pincode SETS the visitor's
 *   location — the same `agri_loc` cookie the header pill writes, resolved
 *   through the same `/api/identity/location` endpoint so the server stays
 *   the validator. The header label and every location-bound section on the
 *   page then agree, because both read that one cookie. Applying reloads, the
 *   established D19 behaviour (`LiveLocationPill`'s default `onChanged`).
 *
 * · default (the D27 category landing pages): unchanged — submitting pushes
 *   the results route via `hrefForPincode` and never persists a location.
 */
export function PincodeHeroFinder({
  hrefForPincode = (p) => `/${p}`,
  micLabel,
  setsLocation = false,
}: {
  hrefForPincode?: (pincode: string) => string;
  /** Renders the U1 §29 voice button in the pincode row when supplied. It is
   * a door into the EXISTING D25 voice pipeline (`/post-need`, whose form
   * owns `voice-recorder.tsx`) — no new capture surface here. */
  micLabel?: string;
  /** Home behaviour: persist the chosen pincode as the visitor's location
   * instead of navigating to the results route. */
  setsLocation?: boolean;
}) {
  const router = useRouter();
  // Every label here comes from the catalogs: at /ta the whole control is
  // Tamil (placeholder, button, GPS pill), at /hi Hindi. Nothing English
  // survives a locale switch.
  const t = useTranslations("ui.pincode");
  const [pincode, setPincode] = useState("");

  /** Resolve through the API and persist. The server is the validator — a
   * failed REQUEST must never persist unvalidated typed digits, while an
   * unknown pincode IS a real answer (`source: "none"`) and is applied. Same
   * rule as `LiveLocationPill.resolvePincode`. */
  async function applyLocation(query: string) {
    try {
      const res = await fetch(`/api/identity/location${query}`, { credentials: "include" });
      if (!res.ok) return false;
      const loc = parseLocationResponse(await res.json());
      if (!loc) return false;
      document.cookie = serializeLocCookie(loc);
      // Full reload so the header island and the server-rendered sections
      // both pick up the new cookie — the D19 default for an applied location.
      window.location.reload();
      return true;
    } catch {
      return false;
    }
  }

  function go(next: string) {
    if (!/^\d{6}$/.test(next)) return;
    if (setsLocation) {
      void applyLocation(`?pincode=${encodeURIComponent(next)}`);
      return;
    }
    router.push(hrefForPincode(next));
  }

  function useGps() {
    if (typeof navigator === "undefined" || !navigator.geolocation) return;
    navigator.geolocation.getCurrentPosition(
      async (pos) => {
        const query = `?lat=${pos.coords.latitude}&lng=${pos.coords.longitude}`;
        if (setsLocation) {
          void applyLocation(query);
          return;
        }
        try {
          const res = await fetch(
            `/api/identity/location${query}`,
            { credentials: "include" },
          );
          if (!res.ok) return;
          const body: unknown = await res.json();
          const loc = parseLocationResponse(body);
          if (loc?.pincode) go(loc.pincode);
        } catch {
          /* GPS resolve failed (network/malformed body) — user can still type a pincode */
        }
      },
      () => {
        /* permission denied / position unavailable — degrade silently */
      },
    );
  }

  return (
    <div className="flex flex-col items-center gap-1">
      <form
        onSubmit={(e) => {
          e.preventDefault();
          go(pincode);
        }}
        className="w-full"
      >
        <PincodeInput
          findLabel={t("find")}
          aria-label={t("inputLabel")}
          placeholder={t("inputLabel")}
          {...(micLabel
            ? {
                mic: (
                  <button
                    type="button"
                    aria-label={micLabel}
                    onClick={() => router.push("/post-need")}
                    className="tap-target px-1 text-[17px] text-brand"
                  >
                    <span aria-hidden="true">🎙️</span>
                  </button>
                ),
              }
            : {})}
          value={pincode}
          findDisabled={pincode.length !== 6}
          onFind={() => go(pincode)}
          onChange={(e) => setPincode(e.target.value.replace(/\D/g, ""))}
        />
      </form>
      <GpsPill type="button" onClick={useGps}>
        {t("gps")}
      </GpsPill>
    </div>
  );
}
