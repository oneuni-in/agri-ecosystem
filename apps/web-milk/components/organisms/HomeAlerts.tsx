"use client";

import { AlertCard, AppBand } from "@agri/ui";
import { useTranslations } from "next-intl";
import { useEffect, useState } from "react";

import {
  PRICE_ALERT_DISMISS_COOKIE,
  dismissalCookie,
  isDismissedIn,
} from "@/lib/dismissal";
import {
  dismissInstall,
  type InstallSnapshot,
  promptInstall,
  subscribeInstall,
} from "@/lib/install-prompt";
import { detectPushState, type PushState, subscribePush } from "@/lib/push";

/**
 * §10a — price-alert opt-in (D28 push).
 *
 * Bound to the same subscription flow as the device toggle on /notifications
 * (`lib/push.ts`), so a visitor who turns alerts on here sees the toggle
 * already on there, and vice versa.
 *
 * "Never nag" per U1 item 33: the card hides itself once permission is granted
 * (state `subscribed`), when the browser cannot do push at all, and when the
 * visitor dismisses it — the dismissal is a 30-day cookie (`lib/dismissal.ts`,
 * the same mechanism §10b's install band uses; U4 A21), not localStorage
 * (which U1's DO-NOT list bans). Its OWN cookie, not §10b's `milk_a2hs`:
 * waving away "install the app" must not also silence the price-alert ask.
 *
 * Renders nothing on the server: a card whose whole purpose is a permission
 * prompt has nothing to say until the browser has been asked what it supports,
 * and reserving space for it would be reserving space for the common case
 * where it never appears.
 */
export function PriceAlertCard({ pincode }: { pincode: string }) {
  const t = useTranslations("ui.home.alerts");
  const [state, setState] = useState<PushState | null>(null);
  const [gone, setGone] = useState(false);

  useEffect(() => {
    // Dismissed inside the 30-day window → never even ask the browser what it
    // supports; the card was told "not now" and stays gone across reloads.
    if (isDismissedIn(document.cookie, PRICE_ALERT_DISMISS_COOKIE)) {
      setGone(true);
      return;
    }
    let live = true;
    void detectPushState().then((next) => {
      if (live) setState(next);
    });
    return () => {
      live = false;
    };
  }, []);

  if (gone) return null;
  // `idle` is the only state this card exists for. `subscribed` means the ask
  // is already answered; `denied`/`ios-install`/`unsupported` mean the button
  // could not work, and the full explanation lives on /notifications.
  if (state !== "idle") return null;

  return (
    <AlertCard
      data-testid="price-alert-card"
      className="mt-5"
      icon="🔔"
      title={t("title", { pincode })}
      sub={t("sub")}
      dismissLabel={t("dismiss")}
      onDismiss={() => {
        document.cookie = dismissalCookie(PRICE_ALERT_DISMISS_COOKIE);
        setGone(true);
      }}
      action={
        <button
          type="button"
          onClick={() => {
            void subscribePush().then(setState);
          }}
          className="inline-flex min-h-[44px] items-center rounded-btn bg-brand px-4 text-[12.5px] font-bold text-white"
        >
          {t("cta")}
        </button>
      }
    />
  );
}

/**
 * §10b — app / PWA install band (D28).
 *
 * Wires the EXISTING install logic rather than a second copy of it: the
 * `beforeinstallprompt` event is captured once in `lib/install-prompt.ts` and
 * shared with the fixed banner, because Chrome honours only the first
 * `prompt()` on that event and a second listener would own a dead one.
 *
 * "Install app" is hidden when already installed (U1 item 20) — `hidden` in
 * the snapshot covers both standalone display-mode and a prior dismissal. On
 * iOS, where the event never fires, the band still renders with the
 * Add-to-Home-Screen hint in place of the button.
 */
export function AppInstallBand() {
  const t = useTranslations("ui.home.app");
  const tPwa = useTranslations("ui.pwa");
  const [snapshot, setSnapshot] = useState<InstallSnapshot>({
    event: null,
    ios: false,
    hidden: false,
  });

  useEffect(() => subscribeInstall(setSnapshot), []);

  if (snapshot.hidden || (!snapshot.event && !snapshot.ios)) return null;

  return (
    <AppBand
      data-testid="app-install-band"
      className="mt-5"
      icon="📱"
      title={t("title")}
      // On iOS the band explains Add-to-Home-Screen instead of promising a
      // one-tap install it cannot deliver.
      sub={snapshot.event ? t("sub") : tPwa("iosHint")}
      dismissLabel={tPwa("dismiss")}
      onDismiss={dismissInstall}
      {...(snapshot.event
        ? {
            action: (
              <button
                type="button"
                onClick={() => void promptInstall()}
                className="inline-flex min-h-[44px] items-center rounded-pill bg-accent px-4 text-[14px] font-bold text-accent-ink"
              >
                {t("cta")}
              </button>
            ),
          }
        : {})}
    />
  );
}
