"use client";

import { Button } from "@agri/ui";
import { useTranslations } from "next-intl";
import { useEffect, useState } from "react";

interface BeforeInstallPromptEvent extends Event {
  prompt: () => Promise<void>;
}

const DISMISS_COOKIE = "milk_a2hs=0; path=/; max-age=2592000; samesite=lax";
const dismissed = () => document.cookie.split("; ").includes("milk_a2hs=0");
const standalone = () =>
  window.matchMedia("(display-mode: standalone)").matches ||
  (navigator as { standalone?: boolean }).standalone === true;

/** Runs `fn` once the page has loaded and the main thread is idle. Both the
 * SW install/precache and the install-prompt listener are post-paint work;
 * doing either during first paint cost measurable Lighthouse perf on the
 * audited home page (CI floor 0.90). */
function afterLoadIdle(fn: () => void): () => void {
  const run = () => {
    const idle = (window as { requestIdleCallback?: typeof requestIdleCallback })
      .requestIdleCallback;
    if (idle) idle(fn, { timeout: 3000 });
    else setTimeout(fn, 1000);
  };
  if (document.readyState === "complete") {
    run();
    return () => {};
  }
  window.addEventListener("load", run, { once: true });
  return () => window.removeEventListener("load", run);
}

/**
 * Single client island for all D28 PWA behaviour: service-worker
 * registration + the install banner. Deliberately ONE component (one client
 * chunk, one hydration boundary) — three separate islands measured ~6 perf
 * points worse locally, and a `next/dynamic` wrapper only added another
 * chunk round-trip on throttled connections.
 *
 * Android/Chrome: defers `beforeinstallprompt` behind our own banner.
 * iOS Safari never fires it, so an Add-to-Home-Screen hint stands in (web
 * push there requires the installed PWA, 16.4+). Dismissal lasts 30 days.
 */
export function PwaClient() {
  const t = useTranslations("ui.pwa");
  const [deferred, setDeferred] = useState<BeforeInstallPromptEvent | null>(null);
  const [ios, setIos] = useState(false);

  useEffect(() => {
    const swEnabled =
      process.env.NODE_ENV === "production" || process.env.NEXT_PUBLIC_ENABLE_SW === "1";
    let onPrompt: ((event: Event) => void) | null = null;

    const cancel = afterLoadIdle(() => {
      if (swEnabled && "serviceWorker" in navigator) {
        void navigator.serviceWorker.register("/sw.js");
      }
      if (standalone() || dismissed()) return;
      onPrompt = (event: Event) => {
        event.preventDefault();
        setDeferred(event as BeforeInstallPromptEvent);
      };
      window.addEventListener("beforeinstallprompt", onPrompt);
      if (/iPad|iPhone|iPod/.test(navigator.userAgent)) setIos(true);
    });

    return () => {
      cancel();
      if (onPrompt) window.removeEventListener("beforeinstallprompt", onPrompt);
    };
  }, []);

  if (!deferred && !ios) return null;
  const dismiss = () => {
    document.cookie = DISMISS_COOKIE;
    setDeferred(null);
    setIos(false);
  };
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
      {deferred ? (
        <Button onClick={() => void deferred.prompt().finally(dismiss)}>{t("installCta")}</Button>
      ) : null}
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
