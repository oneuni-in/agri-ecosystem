"use client";

import { useAgriUser } from "@agri/auth-client/react";
import { Modal } from "@agri/ui";
import { useState } from "react";

/**
 * A-U6 W3 — the A2 reference's 🚩 Report control on the business profile.
 *
 * The page previously carried a comment saying no route existed behind this,
 * so no button was drawn — the right call at the time. `POST /directory/
 * businesses/{slug}/report` arrived with M1.5.A: login-gated, daily-capped,
 * one open report per target, and visible ONLY in the Ops Console. The
 * comment was stale, not the reasoning.
 *
 * The reasons are the backend's `ReportReason` literal exactly. A sixth
 * option here would 422, and a missing one would be a category of abuse
 * nobody can report.
 *
 * The response is deliberately opaque (`ReportCreatedOut` carries no id and
 * no queue position), so the confirmation says only that it was received —
 * this UI must not invent a status it was not told.
 *
 * A report NEVER suspends anything on its own (M1.5): the copy says a human
 * reviews it, because the alternative teaches people that reporting a rival
 * takes their listing down.
 */

const REASONS = [
  { value: "fake_listing", label: "This business does not exist" },
  { value: "wrong_info", label: "Details are wrong or out of date" },
  { value: "abusive", label: "Abusive or offensive content" },
  { value: "fraud_scam", label: "Fraud or a scam" },
  { value: "other", label: "Something else" },
] as const;

type State = "idle" | "sending" | "done" | "capped" | "duplicate" | "error";

const TRIGGER =
  "tap-target inline-flex min-h-[36px] flex-1 items-center justify-center gap-1.5 rounded-btn border border-cream-line bg-card px-3 text-[11.5px] font-bold text-ink";

export function ReportButton({ slug }: { slug: string }) {
  const { status } = useAgriUser({ autoSilentSso: false });
  const [reason, setReason] = useState<string>(REASONS[0].value);
  const [detail, setDetail] = useState("");
  const [state, setState] = useState<State>("idle");

  // "other" requires a detail server-side (ReportIn._other_requires_detail);
  // enforcing it here too means the visitor is told before the round trip.
  const needsDetail = reason === "other" && detail.trim().length === 0;

  if (status === "unauthenticated") {
    return (
      <a
        href={`/api/auth/login?next=${encodeURIComponent(`/directory/businesses/${slug}`)}`}
        className={`${TRIGGER} no-underline`}
      >
        🚩 Report
      </a>
    );
  }

  async function send() {
    setState("sending");
    try {
      const res = await fetch(`/api/directory/businesses/${slug}/report`, {
        method: "POST",
        headers: { "content-type": "application/json" },
        body: JSON.stringify({
          reason,
          ...(detail.trim() ? { detail: detail.trim() } : {}),
        }),
      });
      if (res.ok) setState("done");
      else if (res.status === 429) setState("capped");
      else if (res.status === 409) setState("duplicate");
      else setState("error");
    } catch {
      setState("error");
    }
  }

  return (
    <Modal
      trigger={
        <button type="button" className={TRIGGER}>
          🚩 Report
        </button>
      }
      title="Report this listing"
      description="A person reviews every report. Reporting does not take a listing down on its own."
    >
      {state === "done" ? (
        <p className="text-[13px] text-sub">
          Thanks — your report has been received. We do not share who reported a listing.
        </p>
      ) : (
        <div className="space-y-3">
          <fieldset className="space-y-1.5">
            <legend className="sr-only">Reason</legend>
            {REASONS.map((entry) => (
              <label
                key={entry.value}
                className="flex min-h-[44px] cursor-pointer items-center gap-2.5 rounded-btn border border-cream-line bg-cream px-3 text-[13px] text-ink has-[:checked]:border-brand has-[:checked]:bg-brand-soft"
              >
                <input
                  type="radio"
                  name="report-reason"
                  value={entry.value}
                  checked={reason === entry.value}
                  onChange={() => setReason(entry.value)}
                  className="accent-brand"
                />
                {entry.label}
              </label>
            ))}
          </fieldset>

          <label className="block">
            <span className="text-[12.5px] font-semibold text-ink">
              What is wrong?{reason === "other" ? " (required)" : " (optional)"}
            </span>
            <textarea
              value={detail}
              maxLength={1000}
              rows={3}
              onChange={(e) => setDetail(e.target.value)}
              className="mt-1 w-full rounded-btn border border-cream-line bg-cream px-3 py-2 text-[13px] text-ink"
            />
          </label>

          {state === "capped" ? (
            <p className="text-[12.5px] text-down">
              You have reached today&apos;s report limit — try again tomorrow.
            </p>
          ) : null}
          {state === "duplicate" ? (
            <p className="text-[12.5px] text-sub">
              You already have an open report on this listing. It is still being reviewed.
            </p>
          ) : null}
          {state === "error" ? (
            <p className="text-[12.5px] text-down">Could not send that report. Please try again.</p>
          ) : null}

          <button
            type="button"
            disabled={state === "sending" || needsDetail}
            onClick={() => void send()}
            className="tap-target inline-flex min-h-[44px] w-full items-center justify-center rounded-btn bg-brand px-4 text-sm font-bold text-white disabled:opacity-60"
          >
            {state === "sending" ? "Sending…" : "Send report"}
          </button>
        </div>
      )}
    </Modal>
  );
}
