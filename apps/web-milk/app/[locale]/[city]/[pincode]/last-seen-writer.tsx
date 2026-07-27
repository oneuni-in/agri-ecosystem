"use client";

import { useEffect } from "react";

/** Persists the last viewed pincode's PUBLIC price summary for the offline
 * shell (app/[locale]/offline). Never store anything user-specific here —
 * the SW/offline surface carries no PII by design (D28 threat model). */
export function LastSeenWriter({
  pincode,
  district,
  banner,
}: {
  pincode: string;
  district: string | null;
  banner: string;
}) {
  useEffect(() => {
    try {
      localStorage.setItem(
        "milk:last-seen",
        JSON.stringify({ pincode, district, banner, ts: Date.now() }),
      );
    } catch {
      /* storage full/blocked — non-essential */
    }
  }, [pincode, district, banner]);
  return null;
}
