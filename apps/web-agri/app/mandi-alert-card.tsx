"use client";

/**
 * A1 §18 — mandi-alert opt-in. Web-agri has no push machinery yet (milk's
 * lives in web-milk's PWA client; no manifest/SW exists here), so this is
 * the honest AlertCard variant: the CTA is a door to /notifications, where
 * the real notify surface lives — no permission prompt is faked. A tiny
 * island only because AlertCard's dismiss is a client affordance; dismissal
 * is per-page-view (no cookie), matching its advisory weight.
 */
import { AlertCard } from "@agri/ui";
import { useTranslations } from "next-intl";
import { useState } from "react";

export function MandiAlertCard({ pincode }: { pincode: string }) {
  const t = useTranslations("ui.agriHome.alert");
  const [dismissed, setDismissed] = useState(false);
  if (dismissed) return null;
  return (
    <AlertCard
      icon="🔔"
      data-testid="mandi-alert-card"
      title={t("title", { pincode })}
      sub={t("sub")}
      action={
        <a
          href="/notifications"
          className="inline-flex min-h-[44px] items-center rounded-btn bg-brand px-4 text-[12.5px] font-bold text-white no-underline"
        >
          {t("cta")}
        </a>
      }
      dismissLabel={t("dismiss")}
      onDismiss={() => setDismissed(true)}
    />
  );
}
