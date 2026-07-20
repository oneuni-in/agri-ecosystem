"use client";

import { Button, buttonVariants, Card, cn } from "@agri/ui";
import { useAgriUser } from "@agri/auth-client/react";
import { useState, type FormEvent } from "react";

type SubmitState = "idle" | "submitting" | "done" | "exists";

// Copied verbatim from lead-form.tsx's field styling (D18 idiom) so the two
// forms on this page read as one system.
const FIELD =
  "mt-1 block min-h-[44px] w-full rounded-btn border border-line bg-card px-3 py-2 text-[13px] text-ink";
const LABEL = "block text-[13px] font-semibold text-ink";

function AlertNotice({ children }: { children: React.ReactNode }) {
  return (
    <div className="rounded-card border border-alert-line bg-alert-bg p-3 text-[13px] font-semibold text-ink">
      {children}
    </div>
  );
}

const STARS = [1, 2, 3, 4, 5] as const;

/**
 * Client island rendered below `ReviewsSection`, mirroring LeadForm's state
 * machine and RevealContact's `useAgriUser` gate. `POST /reviews` is fully
 * private on the backend, so guests get the same login-CTA idiom as
 * RevealContact - `next=` preserves this business page.
 *
 * Star input has no `@agri/ui` component to reuse: five radios styled as
 * `★`, each a 44px tap target. The `<input>` itself is visually hidden
 * (`sr-only`) so its native focus ring would be invisible/clipped - the
 * `peer` pattern surfaces the design system's standard focus-visible ring
 * (`design-system.md` §1.4) on the visible `<label>` instead.
 */
export function ReviewForm({ businessId, slug }: { businessId: string; slug: string }) {
  const { status } = useAgriUser({ autoSilentSso: false });
  const [rating, setRating] = useState<number | null>(null);
  const [body, setBody] = useState("");
  const [state, setState] = useState<SubmitState>("idle");
  const [error, setError] = useState<string | null>(null);

  const submitting = state === "submitting";

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
        className={cn(buttonVariants({ variant: "ghost" }), "max-w-[240px] no-underline")}
      >
        Login to write a review
      </a>
    );
  }

  if (state === "done") {
    return (
      <Card className="space-y-1.5 p-4">
        <p className="text-[13px] font-semibold text-ink">Submitted — visible after moderation.</p>
      </Card>
    );
  }

  if (state === "exists") {
    return (
      <Card className="space-y-1.5 p-4">
        <p className="text-[13px] font-semibold text-ink">You already reviewed this.</p>
      </Card>
    );
  }

  const submit = async (event: FormEvent) => {
    event.preventDefault();
    if (!rating) {
      setError("Please choose a rating.");
      return;
    }
    setState("submitting");
    setError(null);
    try {
      const res = await fetch("/api/reviews", {
        method: "POST",
        headers: { "content-type": "application/json" },
        body: JSON.stringify({
          target_type: "business",
          target_id: businessId,
          rating,
          ...(body.trim() ? { body: { en: body.trim() } } : {}),
        }),
      });
      if (res.status === 201) {
        setState("done");
        return;
      }
      if (res.status === 409) {
        setState("exists");
        return;
      }
      setError("Could not submit — please try again.");
      setState("idle");
    } catch {
      setError("Could not submit — please try again.");
      setState("idle");
    }
  };

  return (
    <Card className="space-y-3 p-4">
      <h2 className="font-display text-[16px] font-extrabold text-ink">Write a review</h2>
      <form className="space-y-3" onSubmit={(event) => void submit(event)}>
        <fieldset>
          <legend className={LABEL}>Rating</legend>
          <div className="mt-1 flex gap-1.5">
            {STARS.map((n) => {
              const selected = rating !== null && rating >= n;
              return (
                <span key={n} className="relative">
                  <input
                    type="radio"
                    id={`review-rating-${n}`}
                    name="rating"
                    value={n}
                    checked={rating === n}
                    onChange={() => setRating(n)}
                    aria-label={`Rate ${n} of 5`}
                    className="peer sr-only"
                  />
                  <label
                    htmlFor={`review-rating-${n}`}
                    className={cn(
                      "flex min-h-[44px] min-w-[44px] cursor-pointer items-center justify-center rounded-btn border text-[18px] font-extrabold",
                      "peer-focus-visible:outline peer-focus-visible:outline-[3px] peer-focus-visible:outline-accent peer-focus-visible:outline-offset-2",
                      selected ? "border-rating text-rating" : "border-line bg-card text-sub",
                    )}
                  >
                    ★
                  </label>
                </span>
              );
            })}
          </div>
        </fieldset>
        <label className={LABEL}>
          Review (optional)
          <textarea
            maxLength={2000}
            rows={3}
            value={body}
            onChange={(event) => setBody(event.target.value)}
            className={cn(FIELD, "min-h-[88px]")}
          />
        </label>
        {error ? <AlertNotice>{error}</AlertNotice> : null}
        <Button type="submit" variant="brand" disabled={submitting} className="max-w-[240px]">
          {submitting ? "Submitting..." : "Submit review"}
        </Button>
      </form>
    </Card>
  );
}
