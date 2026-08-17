"use client";

import { useState, useTransition } from "react";

/**
 * A-U3 W1 — the save toggle.
 *
 * The whole client footprint of the content surfaces is this button. It
 * posts through the same-origin BFF (`/api/content/*`), so the session
 * bearer is attached server-side and never touches JS (D10).
 *
 * Optimistic, and deliberately forgiving: the backend's POST is
 * idempotent and its DELETE 404s a bookmark that is already gone, so the
 * only state worth reverting to is the one we came from. A 401 is not an
 * error to shout about either — a signed-out reader pressing save gets
 * sent to login, which is the answer to what they were trying to do.
 */
export function BookmarkButton({
  itemId,
  initiallySaved,
  saveLabel,
  savedLabel,
}: {
  itemId: string;
  initiallySaved: boolean;
  saveLabel: string;
  savedLabel: string;
}) {
  const [saved, setSaved] = useState(initiallySaved);
  const [pending, startTransition] = useTransition();

  function toggle() {
    const next = !saved;
    setSaved(next); // optimistic
    startTransition(async () => {
      try {
        const res = next
          ? await fetch("/api/content/bookmarks", {
              method: "POST",
              headers: { "content-type": "application/json" },
              body: JSON.stringify({ item_id: itemId }),
            })
          : await fetch(`/api/content/bookmarks/${itemId}`, {
              method: "DELETE",
            });

        if (res.status === 401) {
          window.location.href = `/login?next=${encodeURIComponent(window.location.pathname)}`;
          return;
        }
        if (!res.ok) setSaved(!next);
      } catch {
        setSaved(!next);
      }
    });
  }

  return (
    <button
      type="button"
      onClick={toggle}
      disabled={pending}
      aria-pressed={saved}
      className={`tap-target inline-flex items-center gap-1.5 rounded-pill border px-3.5 text-[12.5px] font-semibold ${
        saved
          ? "border-brand bg-brand-soft text-brand-deep"
          : "border-cream-line bg-card text-ink"
      }`}
    >
      <span aria-hidden="true">{saved ? "★" : "☆"}</span>
      {saved ? savedLabel : saveLabel}
    </button>
  );
}
