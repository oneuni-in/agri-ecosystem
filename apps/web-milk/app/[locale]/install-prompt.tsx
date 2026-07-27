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

/** Android/Chrome: defer the native beforeinstallprompt behind our banner.
 * iOS Safari never fires it — show a one-line Add-to-Home-Screen hint
 * instead (web push there needs the installed PWA, 16.4+). Dismissal is
 * remembered for 30 days in a cookie. */
export function InstallPrompt() {
  const t = useTranslations("ui.pwa");
  const [deferred, setDeferred] = useState<BeforeInstallPromptEvent | null>(null);
  const [ios, setIos] = useState(false);

  useEffect(() => {
    if (standalone() || dismissed()) return;
    const onPrompt = (event: Event) => {
      event.preventDefault();
      setDeferred(event as BeforeInstallPromptEvent);
    };
    window.addEventListener("beforeinstallprompt", onPrompt);
    if (/iPad|iPhone|iPod/.test(navigator.userAgent)) setIos(true);
    return () => window.removeEventListener("beforeinstallprompt", onPrompt);
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
