"use client";

import { useSearchParams } from "next/navigation";
import { useEffect } from "react";

/**
 * Fire-and-forget profile-view beacon (D26 analytics-lite). Renders nothing;
 * failures are silent by contract - a lost view is harmless.
 *
 * Reads `?pin=` client-side via useSearchParams rather than a server
 * `searchParams` prop: this page is ISR (`revalidate = 300`) and reading
 * searchParams server-side would force it dynamic. Must be mounted inside a
 * <Suspense> boundary (useSearchParams requirement in static pages).
 */
export function ViewBeacon({ slug }: { slug: string }) {
  const searchParams = useSearchParams();
  const pin = searchParams.get("pin") ?? undefined;
  useEffect(() => {
    const pincode = pin && /^\d{6}$/.test(pin) ? pin : undefined;
    const payload = JSON.stringify({ slug, pincode });
    try {
      const sent = navigator.sendBeacon?.(
        "/api/view",
        new Blob([payload], { type: "application/json" }),
      );
      if (!sent) {
        void fetch("/api/view", {
          method: "POST",
          headers: { "content-type": "application/json" },
          body: payload,
          keepalive: true,
        }).catch(() => undefined);
      }
    } catch {
      // silent by contract
    }
  }, [slug, pin]);
  return null;
}
