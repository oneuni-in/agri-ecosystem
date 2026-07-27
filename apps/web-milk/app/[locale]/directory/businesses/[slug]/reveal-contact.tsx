"use client";

import { Button, buttonVariants, CallButton, cn, WhatsAppButton } from "@agri/ui";
import { useAgriUser } from "@agri/auth-client/react";
import { useState } from "react";

type Revealed = { branch_id: string; phone: string | null; whatsapp: string | null };
type RevealState = "idle" | "loading" | "capped" | "error";

/** wa.me needs a bare digit string (no `+`, spaces, or punctuation); phone
 * is stored E.164 (`+91...`) per D06 - `tel:` accepts that form as-is. */
function waHref(whatsapp: string): string {
  return `https://wa.me/${whatsapp.replace(/\D/g, "")}`;
}

/**
 * Call > chat > form (design law): renders above LeadForm on the business
 * page. Numbers are never in the SSR payload (D18.C) - a logged-in tap
 * spends one of the user's daily reveal slots via the auth-gated
 * /api/directory proxy; guests are sent to login first, next= preserving
 * this business page (D16 lesson: encodeURIComponent the slug).
 */
export function RevealContact({ branchId, slug }: { branchId: string; slug: string }) {
  const { status } = useAgriUser({ autoSilentSso: false });
  const [revealed, setRevealed] = useState<Revealed | null>(null);
  const [state, setState] = useState<RevealState>("idle");

  if (revealed) {
    return (
      <div className="flex flex-wrap gap-2">
        {revealed.phone ? <CallButton label="Call" href={`tel:${revealed.phone}`} /> : null}
        {revealed.whatsapp ? (
          <WhatsAppButton label="WhatsApp" href={waHref(revealed.whatsapp)} />
        ) : null}
      </div>
    );
  }

  if (status === "loading") {
    return (
      <Button variant="ghost" className="max-w-[240px]" disabled>
        Loading...
      </Button>
    );
  }

  if (status === "unauthenticated") {
    return (
      <a
        href={`/api/auth/login?next=${encodeURIComponent(`/directory/businesses/${slug}`)}`}
        className={cn(buttonVariants({ variant: "call" }), "max-w-[240px] no-underline")}
      >
        📞 Login to view contact
      </a>
    );
  }

  return (
    <div>
      <Button
        variant="call"
        className="max-w-[240px]"
        disabled={state === "loading"}
        onClick={async () => {
          setState("loading");
          try {
            const res = await fetch(`/api/directory/branches/${branchId}/reveal`, {
              method: "POST",
            });
            if (res.ok) {
              setRevealed((await res.json()) as Revealed);
              setState("idle");
            } else {
              setState(res.status === 429 ? "capped" : "error");
            }
          } catch {
            setState("error");
          }
        }}
      >
        📞 {state === "loading" ? "Revealing..." : "Show phone number"}
      </Button>
      {state === "capped" ? (
        <p className="mt-1 text-[13px] text-sub">Daily reveal limit reached — try tomorrow.</p>
      ) : null}
      {state === "error" ? (
        <p className="mt-1 text-[13px] text-sub">Could not reveal right now.</p>
      ) : null}
    </div>
  );
}
