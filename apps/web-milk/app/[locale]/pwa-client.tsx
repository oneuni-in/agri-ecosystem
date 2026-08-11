"use client";

import { Button } from "@agri/ui";
import { useTranslations } from "next-intl";
import { useEffect, useState } from "react";

import {
  afterLoadIdle,
  dismissInstall,
  type InstallSnapshot,
  promptInstall,
  subscribeInstall,
} from "@/lib/install-prompt";

/**
 * Single client island for all D28 PWA behaviour: service-worker
 * registration + the install banner. Deliberately ONE component (one client
 * chunk, one hydration boundary) — three separate islands measured ~6 perf
 * points worse locally, and a `next/dynamic` wrapper only added another
 * chunk round-trip on throttled connections.
 *
 * The `beforeinstallprompt` capture itself lives in `lib/install-prompt.ts`,
 * shared with §10b's inline install band: Chrome honours only the FIRST
 * `prompt()` on that event, so a second listener here would leave one of the
 * two buttons holding a dead event. Both surfaces read the same snapshot and
 * the same 30-day dismissal.
 *
 * Android/Chrome: defers the event behind our own banner. iOS Safari never
 * fires it, so an Add-to-Home-Screen hint stands in (web push there requires
 * the installed PWA, 16.4+).
 */
export function PwaClient() {
  const t = useTranslations("ui.pwa");
  const [snapshot, setSnapshot] = useState<InstallSnapshot>({
    event: null,
    ios: false,
    hidden: false,
  });

  useEffect(() => {
    // SW registration stays here — post-paint for the same perf reason the
    // shared module documents (CI floor 0.90 on this route).
    const cancel = afterLoadIdle(() => {
      const swEnabled =
        process.env.NODE_ENV === "production" || process.env.NEXT_PUBLIC_ENABLE_SW === "1";
      if (swEnabled && "serviceWorker" in navigator) {
        void navigator.serviceWorker.register("/sw.js");
      }
    });
    const unsubscribe = subscribeInstall(setSnapshot);
    return () => {
      cancel();
      unsubscribe();
    };
  }, []);

  const deferred = snapshot.event;
  const ios = snapshot.ios;
  if (snapshot.hidden || (!deferred && !ios)) return null;
  const dismiss = dismissInstall;
  return (
    <div
      className="fixed inset-x-0 bottom-0 z-40 mx-auto flex w-full max-w-[720px] items-center gap-3 rounded-t-card border border-line bg-card px-4 py-3 shadow-lift"
      data-testid="install-prompt"
    >
      <span className="text-[22px]" aria-hidden="true">
        🥛
      </span>
      <p className="flex-1 text-[13px] text-ink">
        <b>{t("installTitle")}</b>
        {deferred ? null : <span className="block text-sub">{t("iosHint")}</span>}
      </p>
      {deferred ? <Button onClick={() => void promptInstall()}>{t("installCta")}</Button> : null}
      <button
        type="button"
        onClick={dismiss}
        aria-label={t("dismiss")}
        className="tap-target text-sub"
      >
        ✕
      </button>
    </div>
  );
}
