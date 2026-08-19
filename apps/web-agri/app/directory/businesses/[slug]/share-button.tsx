"use client";

import { useState } from "react";

/**
 * Share, from the A3 business-profile reference.
 *
 * `navigator.share` where the browser has it (every Android browser a farmer
 * is likely to hold), clipboard everywhere else. No third-party share SDK:
 * those exist to watch who shares what, and this page is read by people who
 * were told we never sell their data.
 */
export function ShareButton({ title }: { title: string }) {
  const [copied, setCopied] = useState(false);

  async function share() {
    const url = window.location.href;
    if (navigator.share) {
      // AbortError just means the visitor closed the sheet — not a failure.
      await navigator.share({ title, url }).catch(() => undefined);
      return;
    }
    await navigator.clipboard.writeText(url).catch(() => undefined);
    setCopied(true);
    window.setTimeout(() => setCopied(false), 2000);
  }

  return (
    <button
      type="button"
      onClick={() => void share()}
      className="tap-target inline-flex min-h-[44px] items-center justify-center gap-1.5 rounded-btn border border-cream-line bg-card px-4 text-[12.5px] font-bold text-ink"
    >
      {copied ? "Link copied" : "↗ Share"}
    </button>
  );
}
