"use client";

import { useEffect, useState } from "react";
import { useTranslations } from "next-intl";

import {
  detectPushState,
  PUSH_CONFIGURED,
  subscribePush,
  unsubscribePush,
  type PushState,
} from "@/lib/push";

/**
 * A-U4 W3 — this device's push subscription state, on the notifications
 * centre.
 *
 * The honesty rules, which are most of this component:
 *
 * - **No VAPID key → renders NOTHING.** `PUSH_CONFIGURED` is inlined at build
 *   time, so a deployment without the key does not show a toggle that cannot
 *   work. This is the same feature-dark default milk uses, and it is why the
 *   card can ship before the key is provisioned in prod.
 * - **`denied` is a dead end and says so.** Once a browser permission is
 *   denied, no button can undo it — only the visitor can, in browser
 *   settings. Rendering an enabled-looking button there would be a lie.
 * - **iOS needs the PWA installed first** (Safari exposes PushManager only
 *   inside an installed app, 16.4+), so that state gets its own copy rather
 *   than being lumped into "unsupported".
 *
 * This is DEVICE state. The push channel preference is a separate,
 * server-side D12 setting — turning this on here does not silently change
 * what the account has opted into.
 */
export function PushCard() {
  const t = useTranslations("notifications");
  const [state, setState] = useState<PushState | null>(null);
  const [busy, setBusy] = useState(false);

  useEffect(() => {
    let cancelled = false;
    void detectPushState().then((next) => {
      if (!cancelled) setState(next);
    });
    return () => {
      cancelled = true;
    };
  }, []);

  // Feature-dark: no key, or a browser that cannot do this at all.
  if (!PUSH_CONFIGURED || state === null || state === "unsupported") return null;

  const toggle = async () => {
    setBusy(true);
    try {
      setState(state === "subscribed" ? await unsubscribePush() : await subscribePush());
    } catch {
      setState(await detectPushState());
    } finally {
      setBusy(false);
    }
  };

  return (
    <section
      aria-labelledby="push-heading"
      className="mb-5 rounded-card border border-cream-line bg-card px-4 py-3.5"
    >
      <h2 id="push-heading" className="text-[13.5px] font-semibold text-ink">
        {t("push.title")}
      </h2>
      <p className="mt-1 text-[11.5px] leading-[1.55] text-sub">
        {state === "denied"
          ? t("push.deniedBody")
          : state === "ios-install"
            ? t("push.iosBody")
            : t("push.body")}
      </p>

      {state === "denied" || state === "ios-install" ? null : (
        <button
          type="button"
          onClick={() => void toggle()}
          disabled={busy}
          aria-pressed={state === "subscribed"}
          className={`tap-target mt-2.5 inline-flex min-h-[44px] items-center rounded-btn px-4 text-[12.5px] font-bold disabled:opacity-50 ${
            state === "subscribed"
              ? "border border-cream-line bg-card text-ink"
              : "bg-brand text-white"
          }`}
        >
          {busy ? t("push.working") : state === "subscribed" ? t("push.off") : t("push.on")}
        </button>
      )}
    </section>
  );
}
