"use client";

import { Button } from "@agri/ui";
import { useTranslations } from "next-intl";
import { useEffect, useState } from "react";

import { detectPushState, type PushState, subscribePush, unsubscribePush } from "@/lib/push";

/** Device-level push toggle (D28). The push *channel preference* stays
 * opt-out server-side (D12 model, PUT /notify/preferences accepts "push");
 * this card manages THIS device's subscription. Hidden entirely until a
 * VAPID public key is provisioned (feature-dark default).
 *
 * The subscribe/unsubscribe flow itself lives in `lib/push.ts`, shared with
 * §10a's price-alert card on the home — one flow, so a visitor who opts in
 * from either surface sees the same state on the other. */
export function PushAlertsCard() {
  const t = useTranslations("ui.pushAlerts");
  const [state, setState] = useState<PushState>("unsupported");

  useEffect(() => {
    let live = true;
    void detectPushState().then((next) => {
      if (live) setState(next);
    });
    return () => {
      live = false;
    };
  }, []);

  if (state === "unsupported") return null;

  return (
    <section
      className="mb-4 flex items-center gap-3 rounded-card border border-line bg-card px-4 py-3"
      data-testid="push-alerts-card"
    >
      <span aria-hidden="true" className="text-[22px]">
        🔔
      </span>
      <div className="flex-1">
        <b className="text-[14px] text-ink">{t("title")}</b>
        <p className="text-[13px] text-sub">
          {state === "ios-install" ? t("iosInstallFirst") : t("body")}
        </p>
      </div>
      {state === "idle" ? (
        <Button onClick={() => void subscribePush().then(setState)}>{t("enable")}</Button>
      ) : null}
      {state === "subscribed" ? (
        <Button variant="ghost" onClick={() => void unsubscribePush().then(setState)}>
          {t("disable")}
        </Button>
      ) : null}
      {state === "denied" ? <span className="text-[12px] text-sub">{t("blocked")}</span> : null}
    </section>
  );
}
