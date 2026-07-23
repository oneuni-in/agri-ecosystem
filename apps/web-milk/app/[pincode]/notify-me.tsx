"use client";

import { useState } from "react";

/**
 * Warm empty-state demand capture (`tn_no_vendors` / `out_of_area` scopes).
 * POSTs to the same-origin BFF proxy (Task 7) -> public
 * `/leads/pincode-interest`; the district is derived server-side from the
 * pincode, never sent by the client. `district` here is presentation-only —
 * it personalizes the confirmation copy when the page already knows it
 * (`tn_no_vendors` scope), falling back to the bare pincode otherwise
 * (`out_of_area`, where `location` is null). Never an error surface — a
 * failed submit just leaves the form re-submittable, no toast/crash.
 */
export function NotifyMe({ pincode, district }: { pincode: string; district?: string }) {
  const [status, setStatus] = useState<"idle" | "sending" | "done" | "error">("idle");
  const [contact, setContact] = useState("");
  const place = district ?? pincode;

  async function submit(e: React.FormEvent) {
    e.preventDefault();
    setStatus("sending");
    try {
      const res = await fetch("/api/leads/pincode-interest", {
        method: "POST",
        headers: { "content-type": "application/json" },
        body: JSON.stringify({ pincode, contact: contact.trim() || undefined }),
      });
      setStatus(res.ok ? "done" : "error");
    } catch {
      setStatus("error");
    }
  }

  if (status === "done") {
    return (
      <p className="text-[14px] font-bold text-ink" data-testid="notify-done" role="status">
        🎉 Thanks — we&apos;ll tell you the moment milk vendors reach {place}.
      </p>
    );
  }

  return (
    <form onSubmit={submit} className="flex flex-col gap-2 sm:flex-row" data-testid="notify-me">
      <input
        type="text"
        inputMode="tel"
        value={contact}
        onChange={(e) => setContact(e.target.value)}
        placeholder="Phone or email (optional)"
        aria-label="Contact for notification"
        className="min-h-11 flex-1 rounded-btn border border-line bg-card px-3 py-2.5 text-[14px] text-ink"
      />
      <button
        type="submit"
        disabled={status === "sending"}
        className="min-h-11 rounded-btn bg-brand px-5 py-2.5 text-[14px] font-extrabold text-white disabled:opacity-50"
      >
        Notify me
      </button>
      {status === "error" ? (
        <p className="text-[12.5px] text-sub sm:basis-full" role="status">
          Something went wrong — please try again.
        </p>
      ) : null}
    </form>
  );
}
