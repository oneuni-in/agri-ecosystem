"use client";

import { GpsPill, parseLocationResponse, PincodeInput } from "@agri/ui";
import { useState } from "react";

import { useRouter } from "@/i18n/navigation";

/**
 * Interactive controls rendered as the `children` of the `@agri/ui`
 * `PincodeHero` shell on the homepage (`.pinbox` + `.gps`): typing a 6-digit
 * pincode and submitting — or resolving one via GPS — navigates to the ISR
 * results route `/[pincode]` (Task 10). This is distinct from the header's
 * `LiveLocationPill` (the persistent location switcher, untouched here) —
 * this control only ever pushes a route, it never sets/persists location.
 *
 * `hrefForPincode` lets callers (e.g. the D27 category landing pages) route
 * a submitted pincode somewhere other than the plain results route — it
 * defaults to the original `/${pincode}` target, so existing callers are
 * unaffected.
 */
export function PincodeHeroFinder({
  hrefForPincode = (p) => `/${p}`,
  micLabel,
}: {
  hrefForPincode?: (pincode: string) => string;
  /** Renders the U1 §29 voice button in the pincode row when supplied. It is
   * a door into the EXISTING D25 voice pipeline (`/post-need`, whose form
   * owns `voice-recorder.tsx`) — no new capture surface here. */
  micLabel?: string;
}) {
  const router = useRouter();
  const [pincode, setPincode] = useState("");

  function go(next: string) {
    if (/^\d{6}$/.test(next)) router.push(hrefForPincode(next));
  }

  function useGps() {
    if (typeof navigator === "undefined" || !navigator.geolocation) return;
    navigator.geolocation.getCurrentPosition(
      async (pos) => {
        const { latitude, longitude } = pos.coords;
        try {
          const res = await fetch(
            `/api/identity/location?lat=${latitude}&lng=${longitude}`,
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
          findLabel="Find milk"
          aria-label="Enter pincode"
          placeholder="Enter pincode"
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
        📍 Or use my location · என் இடம்
      </GpsPill>
    </div>
  );
}
