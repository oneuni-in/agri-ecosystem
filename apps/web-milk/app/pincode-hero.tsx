"use client";

import { GpsPill, parseLocationResponse, PincodeInput } from "@agri/ui";
import { useRouter } from "next/navigation";
import { useState } from "react";

/**
 * Interactive controls rendered as the `children` of the `@agri/ui`
 * `PincodeHero` shell on the homepage (`.pinbox` + `.gps`): typing a 6-digit
 * pincode and submitting — or resolving one via GPS — navigates to the ISR
 * results route `/[pincode]` (Task 10). This is distinct from the header's
 * `LiveLocationPill` (the persistent location switcher, untouched here) —
 * this control only ever pushes a route, it never sets/persists location.
 */
export function PincodeHeroFinder() {
  const router = useRouter();
  const [pincode, setPincode] = useState("");

  function go(next: string) {
    if (/^\d{6}$/.test(next)) router.push(`/${next}`);
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
