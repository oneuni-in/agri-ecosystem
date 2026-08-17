"use client";

/**
 * A1 §18 — mandi-alert opt-in. A-U2 AG-A16 gave this a real backend, so
 * the CTA now SUBSCRIBES instead of routing to /notifications: POST
 * (via the same-origin /api/market BFF, so the bearer never touches JS)
 * to `/market/alerts`, which stores a per-pincode subscription and sends
 * a daily digest after the Agmarknet pull.
 *
 * Guest handling is honest rather than clever: the endpoint is private,
 * so an anonymous visitor gets a 401. Instead of hiding the card or
 * faking success we say what happened and send them to log in — the
 * subscription is genuinely per-user and cannot exist without one.
 *
 * Dismissal stays per-page-view (no cookie), matching its advisory
 * weight — unchanged from A-U1.
 */
import { AlertCard } from "@agri/ui";
import { useTranslations } from "next-intl";
import { useState } from "react";

type State = "idle" | "saving" | "done" | "signin" | "capped" | "error";

export function MandiAlertCard({ pincode }: { pincode: string }) {
  const t = useTranslations("ui.agriHome.alert");
  const [dismissed, setDismissed] = useState(false);
  const [state, setState] = useState<State>("idle");

  if (dismissed) return null;

  async function subscribe() {
    setState("saving");
    try {
      const res = await fetch("/api/market/alerts", {
        method: "POST",
        headers: { "content-type": "application/json" },
        body: JSON.stringify({ pincode }),
      });
      // 201 created, or 200 if they already followed this pincode — the
      // backend is idempotent, so both mean "you are subscribed".
      if (res.ok) return setState("done");
      if (res.status === 401) return setState("signin");
      if (res.status === 429) return setState("capped");
      setState("error");
    } catch {
      setState("error");
    }
  }

  const label =
    state === "saving"
      ? t("saving")
      : state === "done"
        ? t("done")
        : state === "capped"
          ? t("capped")
          : state === "error"
            ? t("error")
            : t("cta");

  return (
    <AlertCard
      icon="🔔"
      data-testid="mandi-alert-card"
      title={t("title", { pincode })}
      sub={t("sub")}
      action={
        state === "signin" ? (
          <a
            // `?next=/` returns them to the home they were reading, which
            // is also the milk precedent for an auth bounce from a card.
            href={`/api/auth/login?next=${encodeURIComponent("/")}`}
            data-testid="mandi-alert-signin"
            className="inline-flex min-h-[44px] items-center rounded-btn bg-brand px-4 text-[12.5px] font-bold text-white no-underline"
          >
            {t("signin")}
          </a>
        ) : (
          <button
            type="button"
            data-testid="mandi-alert-cta"
            onClick={subscribe}
            disabled={state === "saving" || state === "done"}
            className="inline-flex min-h-[44px] items-center rounded-btn bg-brand px-4 text-[12.5px] font-bold text-white disabled:opacity-70"
          >
            {label}
          </button>
        )
      }
      dismissLabel={t("dismiss")}
      onDismiss={() => setDismissed(true)}
    />
  );
}
