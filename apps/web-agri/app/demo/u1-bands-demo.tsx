"use client";

import { AlertCard, AppBand, Button } from "@agri/ui";
import { useState } from "react";

/**
 * The two dismissible U1 bands (§10a price alerts, §10b app install).
 *
 * A client island for the same reason `ToastDemo` is one: both take an
 * `onDismiss` handler, and a function cannot cross the server→client boundary.
 * The components themselves are the SAME `@agri/ui` exports the milk home
 * renders — only the data and the dismiss target are local to the catalog, so
 * demo and product cannot drift apart.
 */
export function U1BandsDemo() {
  const [alertGone, setAlertGone] = useState(false);
  const [bandGone, setBandGone] = useState(false);
  return (
    <div className="flex flex-col gap-3">
      {alertGone ? (
        <button
          type="button"
          onClick={() => setAlertGone(false)}
          className="self-start text-[12px] underline"
        >
          restore alert-card
        </button>
      ) : (
        <AlertCard
          icon="🔔"
          title="Get price alerts for 641001"
          sub="Milk price changes and new vendors near you - free notifications"
          dismissLabel="Not now"
          onDismiss={() => setAlertGone(true)}
          action={<Button className="max-w-[120px]">Turn on</Button>}
        />
      )}
      {bandGone ? (
        <button
          type="button"
          onClick={() => setBandGone(false)}
          className="self-start text-[12px] underline"
        >
          restore app-band
        </button>
      ) : (
        <AppBand
          icon="📱"
          title="Get milk.in on your phone"
          sub="Installs in one tap - works offline, loads light on 3G. No app store needed."
          dismissLabel="Dismiss"
          onDismiss={() => setBandGone(true)}
          action={
            <span className="inline-flex min-h-[44px] items-center rounded-pill bg-accent px-4 text-[14px] font-bold text-accent-ink">
              Install app
            </span>
          }
        />
      )}
    </div>
  );
}
