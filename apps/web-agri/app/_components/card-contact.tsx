"use client";

import { useAgriUser } from "@agri/auth-client/react";
import { useState } from "react";

/**
 * A-U6 W1 — the A2 reference's three-button card row: 📞 Call · WhatsApp ·
 * Profile.
 *
 * WHY AN ISLAND AND NOT THREE LINKS. Contact numbers are never in a list
 * payload (D18.C) — the SSR HTML for this page contains no phone number at
 * all, only `contact_branch_id`. A tap here runs the SAME reveal the business
 * profile runs: `POST /directory/branches/{id}/reveal` through the
 * auth-gated proxy, which is login-gated, spends one of the visitor's daily
 * reveal slots, writes the DPDP disclosure row and records the lead. Nothing
 * about that contract is relaxed to put the button on a card; the button
 * simply moved to where people actually decide to call.
 *
 * One reveal serves both buttons, because one reveal returns both numbers —
 * tapping WhatsApp does not spend a second slot.
 *
 * Degrades in the honest direction at every step:
 *   · no contactable branch → Profile alone, full width. The listing has no
 *     number, so it does not grow a Call button that cannot dial.
 *   · signed out           → Call/WhatsApp become login links that come back
 *     here, rather than buttons that fail on tap.
 *   · daily cap reached    → the row stays and says so (429), so the visitor
 *     learns the limit instead of watching a button do nothing.
 */

type Revealed = { branch_id: string; phone: string | null; whatsapp: string | null };
type RevealState = "idle" | "loading" | "capped" | "error";

/** wa.me needs a bare digit string (no `+`, spaces or punctuation); phone is
 * stored E.164 (`+91…`) per D06 — `tel:` accepts that form as-is. */
function waHref(whatsapp: string): string {
  return `https://wa.me/${whatsapp.replace(/\D/g, "")}`;
}

/** The reference's `.biz .actions .btn`: flex-1, 38px, 12px, radius 9.
 * `tap-target` lifts the hit area to the 44px floor without resizing it. */
const BTN =
  "tap-target inline-flex min-h-[38px] flex-1 items-center justify-center gap-1 rounded-[9px] px-2 text-xs font-semibold no-underline disabled:opacity-60";
const CALL = `${BTN} bg-call text-white`;
const WA = `${BTN} border border-wa-line bg-wa-soft text-wa-deep`;
const GHOST = `${BTN} border border-cream-line bg-card text-brand-deep`;

export function CardContact({
  branchId,
  profileHref,
  returnTo,
}: {
  /** null when no branch on this business carries a number. */
  branchId: string | null;
  profileHref: string;
  /** Where login should return to — this category page, not the profile. */
  returnTo: string;
}) {
  const { status } = useAgriUser({ autoSilentSso: false });
  const [revealed, setRevealed] = useState<Revealed | null>(null);
  const [state, setState] = useState<RevealState>("idle");

  const profile = (
    <a href={profileHref} className={GHOST}>
      Profile
    </a>
  );

  if (!branchId) {
    return (
      <div className="mt-auto flex gap-[7px] pt-2.5">
        <a href={profileHref} className={`${BTN} bg-brand text-white`}>
          View profile →
        </a>
      </div>
    );
  }

  async function reveal() {
    setState("loading");
    try {
      const res = await fetch(`/api/directory/branches/${branchId}/reveal`, { method: "POST" });
      if (res.ok) {
        setRevealed((await res.json()) as Revealed);
        setState("idle");
      } else {
        setState(res.status === 429 ? "capped" : "error");
      }
    } catch {
      setState("error");
    }
  }

  let call: React.ReactNode;
  let whatsapp: React.ReactNode;

  if (revealed) {
    call = revealed.phone ? (
      <a href={`tel:${revealed.phone}`} className={CALL}>
        📞 Call
      </a>
    ) : (
      <span className={`${CALL} opacity-60`}>📞 No number</span>
    );
    whatsapp = revealed.whatsapp ? (
      <a href={waHref(revealed.whatsapp)} className={WA} target="_blank" rel="noopener noreferrer">
        WhatsApp
      </a>
    ) : null;
  } else if (status === "unauthenticated") {
    const login = `/api/auth/login?next=${encodeURIComponent(returnTo)}`;
    call = (
      <a href={login} className={CALL}>
        📞 Call
      </a>
    );
    whatsapp = (
      <a href={login} className={WA}>
        WhatsApp
      </a>
    );
  } else {
    const busy = status === "loading" || state === "loading";
    call = (
      <button type="button" className={CALL} disabled={busy} onClick={reveal}>
        📞 {state === "loading" ? "…" : "Call"}
      </button>
    );
    whatsapp = (
      <button type="button" className={WA} disabled={busy} onClick={reveal}>
        WhatsApp
      </button>
    );
  }

  return (
    <div className="mt-auto pt-2.5">
      <div className="flex gap-[7px]">
        {call}
        {whatsapp}
        {profile}
      </div>
      {state === "capped" ? (
        <p className="mt-1.5 text-[10.5px] text-muted">
          Daily reveal limit reached — try again tomorrow.
        </p>
      ) : null}
      {state === "error" ? (
        <p className="mt-1.5 text-[10.5px] text-muted">Could not show the number right now.</p>
      ) : null}
    </div>
  );
}
