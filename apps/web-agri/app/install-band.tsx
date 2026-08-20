"use client";

/**
 * §19 — PWA install band (A-U4b O8, AG-A66; reference
 * agri_home_desktop_v1.html:1245-1251).
 *
 * The REAL `beforeinstallprompt` flow, not a decorative band: the event is
 * captured and held behind our own UI, the Install button fires `prompt()`,
 * and the visitor's choice is reported honestly — accepted hides the band,
 * dismissed keeps it for this page view (Chrome re-fires the event after a
 * dismissal; until it does, the button is DISABLED rather than silently dead).
 *
 * Which surface renders is `decideInstallSurface` (lib/install-prompt.ts):
 * nothing on first paint, nothing when already installed or unsupported, the
 * Add-to-Home-Screen instruction on iOS (which never fires the event — same
 * honesty precedent as lib/push.ts's "ios-install" state), the button only
 * while a live event is held. Milk's D28 band (web-milk HomeAlerts §10b +
 * lib/install-prompt.ts) is the proven precedent this follows; agri has one
 * install surface, so the capture lives in this island rather than a shared
 * singleton.
 *
 * The reference's QR block is DROPPED: a fake QR is dishonest and a real one
 * adds a dependency; the island stays dependency-free (A-U4b requirement).
 *
 * Listener setup waits for post-load idle — the same first-paint budget rule
 * as register-sw.tsx and milk's capture. An event that fires before idle is
 * missed for this page view (band absent — still honest), and the iOS path
 * is unaffected because Safari never fires it at all.
 */

import { AppBand } from "@agri/ui";
import { useTranslations } from "next-intl";
import { useEffect, useRef, useState } from "react";

import { decideInstallSurface, isIosUserAgent } from "@/lib/install-prompt";

interface BeforeInstallPromptEvent extends Event {
  prompt: () => Promise<void>;
  userChoice: Promise<{ outcome: "accepted" | "dismissed" }>;
}

export function InstallBand() {
  const t = useTranslations("ui.agriHome.install");
  const [flags, setFlags] = useState({
    hasPrompt: false,
    isIOS: false,
    isStandalone: false,
  });
  /** ✕ — per page view, like §18's card (advisory weight, no cookie). */
  const [dismissed, setDismissed] = useState(false);
  /** Accepted the prompt, or `appinstalled` fired. */
  const [installed, setInstalled] = useState(false);
  /** Native dialog open, or the held event was spent on a dismissal and
   * Chrome has not re-offered yet — the button is disabled, never dead. */
  const [busy, setBusy] = useState(false);
  const eventRef = useRef<BeforeInstallPromptEvent | null>(null);

  useEffect(() => {
    const onPrompt = (event: Event) => {
      event.preventDefault(); // hold it behind our own UI
      eventRef.current = event as BeforeInstallPromptEvent;
      setBusy(false); // a fresh event re-arms the button after a dismissal
      setFlags((prev) => ({ ...prev, hasPrompt: true }));
    };
    const onInstalled = () => setInstalled(true);

    const start = () => {
      const standalone =
        window.matchMedia("(display-mode: standalone)").matches ||
        (navigator as { standalone?: boolean }).standalone === true;
      if (standalone) {
        setFlags({ hasPrompt: false, isIOS: false, isStandalone: true });
        return;
      }
      window.addEventListener("beforeinstallprompt", onPrompt);
      window.addEventListener("appinstalled", onInstalled);
      setFlags((prev) => ({ ...prev, isIOS: isIosUserAgent(navigator.userAgent) }));
    };

    // After load + idle: same post-paint principle as register-sw.tsx.
    const idle = () => {
      const request = (
        window as { requestIdleCallback?: typeof requestIdleCallback }
      ).requestIdleCallback;
      if (request) request(start, { timeout: 3000 });
      else setTimeout(start, 1000);
    };
    if (document.readyState === "complete") idle();
    else window.addEventListener("load", idle, { once: true });

    return () => {
      window.removeEventListener("load", idle);
      window.removeEventListener("beforeinstallprompt", onPrompt);
      window.removeEventListener("appinstalled", onInstalled);
    };
  }, []);

  async function install() {
    const held = eventRef.current;
    if (!held) return;
    eventRef.current = null;
    setBusy(true);
    try {
      await held.prompt();
      const choice = await held.userChoice;
      if (choice.outcome === "accepted") setInstalled(true);
      // dismissed → the band stays this page view; `busy` keeps the button
      // disabled until Chrome re-fires beforeinstallprompt (onPrompt clears it).
    } catch {
      // A consumed/blocked prompt behaves like a dismissal: band stays,
      // button disabled until a fresh event arrives.
    }
  }

  const surface = installed || dismissed ? "absent" : decideInstallSurface(flags);
  if (surface === "absent") return null;

  return (
    <div className="mt-5">
      <AppBand
        data-testid="install-band"
        aria-label={t("title")}
        icon="📱"
        title={t("title")}
        // On iOS the band explains Add-to-Home-Screen instead of promising a
        // one-tap install it cannot deliver (milk §10b precedent).
        sub={surface === "button" ? t("sub") : t("ios")}
        dismissLabel={t("dismiss")}
        onDismiss={() => setDismissed(true)}
        {...(surface === "button"
          ? {
              action: (
                <button
                  type="button"
                  data-testid="install-band-cta"
                  onClick={() => void install()}
                  disabled={busy}
                  className="inline-flex min-h-[44px] items-center rounded-pill bg-accent px-4 text-[14px] font-bold text-accent-ink disabled:opacity-70"
                >
                  {t("cta")}
                </button>
              ),
            }
          : {})}
      />
    </div>
  );
}
