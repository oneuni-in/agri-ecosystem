"use client";

import { useEffect } from "react";

/** Fire-and-forget profile-view beacon (D26 analytics-lite). Renders
 * nothing; failures are silent by contract - a lost view is harmless. */
export function ViewBeacon({ slug, pincode }: { slug: string; pincode?: string | null }) {
  useEffect(() => {
    const payload = JSON.stringify({ slug, pincode: pincode ?? undefined });
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
      // never surface beacon failures
    }
  }, [slug, pincode]);
  return null;
}
