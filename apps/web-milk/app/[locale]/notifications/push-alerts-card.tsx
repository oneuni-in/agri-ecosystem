"use client";

import { Button } from "@agri/ui";
import { useTranslations } from "next-intl";
import { useEffect, useState } from "react";

const VAPID = process.env.NEXT_PUBLIC_VAPID_PUBLIC_KEY ?? "";

function urlBase64ToUint8Array(base64: string): Uint8Array {
  const padded = base64 + "=".repeat((4 - (base64.length % 4)) % 4);
  const raw = atob(padded.replace(/-/g, "+").replace(/_/g, "/"));
  return Uint8Array.from(raw, (char) => char.charCodeAt(0));
}

type State = "unsupported" | "ios-install" | "idle" | "subscribed" | "denied";

/** Device-level push toggle (D28). The push *channel preference* stays
 * opt-out server-side (D12 model, PUT /notify/preferences accepts "push");
 * this card manages THIS device's subscription. Hidden entirely until a
 * VAPID public key is provisioned (feature-dark default). */
export function PushAlertsCard() {
  const t = useTranslations("ui.pushAlerts");
  const [state, setState] = useState<State>("unsupported");

  useEffect(() => {
    if (!VAPID) return; // no key provisioned -> feature stays dark
    if (!("serviceWorker" in navigator)) return;
    if (!("PushManager" in window)) {
      // iOS Safari exposes PushManager only inside an installed PWA (16.4+)
      if (/iPad|iPhone|iPod/.test(navigator.userAgent)) setState("ios-install");
      return;
    }
    if (Notification.permission === "denied") {
      setState("denied");
      return;
    }
    void navigator.serviceWorker.ready
      .then((registration) => registration.pushManager.getSubscription())
      .then((subscription) => setState(subscription ? "subscribed" : "idle"));
  }, []);

  if (state === "unsupported") return null;

  const subscribe = async () => {
    const registration = await navigator.serviceWorker.ready;
    if ((await Notification.requestPermission()) !== "granted") {
      setState("denied");
      return;
    }
    const subscription = await registration.pushManager.subscribe({
      userVisibleOnly: true,
      applicationServerKey: urlBase64ToUint8Array(VAPID) as BufferSource,
    });
    const json = subscription.toJSON();
    const res = await fetch("/api/notify/push/subscriptions", {
      method: "POST",
      headers: { "content-type": "application/json" },
      body: JSON.stringify({
        endpoint: json.endpoint,
        keys: { p256dh: json.keys?.p256dh, auth: json.keys?.auth },
      }),
    });
    if (res.ok) setState("subscribed");
    else await subscription.unsubscribe(); // don't leave an orphan browser sub
  };

  const unsubscribe = async () => {
    const registration = await navigator.serviceWorker.ready;
    const subscription = await registration.pushManager.getSubscription();
    if (subscription) {
      await fetch("/api/notify/push/subscriptions", {
        method: "DELETE",
        headers: { "content-type": "application/json" },
        body: JSON.stringify({ endpoint: subscription.endpoint }),
      });
      await subscription.unsubscribe();
    }
    setState("idle");
  };

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
      {state === "idle" ? <Button onClick={() => void subscribe()}>{t("enable")}</Button> : null}
      {state === "subscribed" ? (
        <Button variant="ghost" onClick={() => void unsubscribe()}>
          {t("disable")}
        </Button>
      ) : null}
      {state === "denied" ? <span className="text-[12px] text-sub">{t("blocked")}</span> : null}
    </section>
  );
}
