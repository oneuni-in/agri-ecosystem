"use client";

/**
 * How we reach you (AG-U5 P4).
 *
 * The consumer half of the D12 preference endpoints — the same
 * `GET`/`PUT /notify/preferences` rows the console's vendor surface writes,
 * so a channel switched off here is off everywhere. There is one set of
 * preferences per person, not one per role.
 *
 * ONE SAVE MODEL: the toggle IS the save. There is no Save button to forget
 * to press, the change applies optimistically, a "Saved" tick confirms it,
 * and a failure puts the switch back where it was and says so. A toggle that
 * looks changed but was not stored is the failure worth designing against.
 *
 * Copy arrives as props: both this and the alerts island are mounted from
 * Server Components, so the strings resolve on the server rather than by
 * shipping `ui.account` into a second client catalog (AG-A8).
 */

import { Card } from "@agri/ui";
import { useEffect, useState } from "react";

const CHANNELS = ["sms", "email", "push"] as const;
type Channel = (typeof CHANNELS)[number];

export interface PrefsCopy {
  title: string;
  hint: string;
  sms: string;
  email: string;
  push: string;
  on: string;
  off: string;
  saved: string;
  loadFailed: string;
  saveFailed: string;
}

export function NotificationPrefs({ copy }: { copy: PrefsCopy }) {
  const [prefs, setPrefs] = useState<Record<Channel, boolean> | null>(null);
  const [loadFailed, setLoadFailed] = useState(false);
  const [busy, setBusy] = useState<Channel | null>(null);
  const [savedChannel, setSavedChannel] = useState<Channel | null>(null);
  const [failedChannel, setFailedChannel] = useState<Channel | null>(null);

  useEffect(() => {
    let cancelled = false;
    void (async () => {
      try {
        const res = await fetch("/api/notify/preferences", { cache: "no-store" });
        if (!res.ok) throw new Error(String(res.status));
        const body = (await res.json()) as { items?: { channel: string; enabled: boolean }[] };
        if (cancelled) return;
        // Absent means ON: the server defaults an unset channel to enabled,
        // and this mirror of that default must not disagree with it.
        const map = { sms: true, email: true, push: true } as Record<Channel, boolean>;
        for (const item of body.items ?? []) {
          if ((CHANNELS as readonly string[]).includes(item.channel)) {
            map[item.channel as Channel] = item.enabled;
          }
        }
        setPrefs(map);
      } catch {
        if (!cancelled) setLoadFailed(true);
      }
    })();
    return () => {
      cancelled = true;
    };
  }, []);

  const toggle = async (channel: Channel) => {
    if (!prefs || busy) return;
    const next = !prefs[channel];
    setBusy(channel);
    setFailedChannel(null);
    setSavedChannel(null);
    setPrefs((current) => (current ? { ...current, [channel]: next } : current));
    try {
      const res = await fetch("/api/notify/preferences", {
        method: "PUT",
        headers: { "content-type": "application/json" },
        body: JSON.stringify({ channel, enabled: next }),
      });
      if (!res.ok) throw new Error(String(res.status));
      setSavedChannel(channel);
      setTimeout(() => setSavedChannel(null), 2000);
    } catch {
      // Put it back. A switch left in the position the server never accepted
      // is a lie the user has no way to detect.
      setPrefs((current) => (current ? { ...current, [channel]: !next } : current));
      setFailedChannel(channel);
    } finally {
      setBusy(null);
    }
  };

  return (
    <Card className="mt-4 p-3.5">
      <h2 className="font-display text-[15px] font-extrabold text-ink">{copy.title}</h2>
      <p className="mb-3 mt-1 text-[12px] text-sub">{copy.hint}</p>
      {loadFailed ? (
        <p
          role="alert"
          className="rounded-card border border-alert-line bg-alert-bg px-3 py-2.5 text-[12.5px] text-ink"
        >
          {copy.loadFailed}
        </p>
      ) : (
        <ul className="space-y-2">
          {CHANNELS.map((channel) => {
            const enabled = prefs?.[channel] ?? true;
            return (
              <li
                key={channel}
                className="flex items-center gap-2 rounded-card border border-cream-line bg-cream px-3 py-2.5"
              >
                <span className="flex-1 text-[13px] font-semibold text-ink">{copy[channel]}</span>
                {savedChannel === channel ? (
                  <span
                    aria-live="polite"
                    className="text-[11.5px] font-semibold text-verified-fg"
                  >
                    ✓ {copy.saved}
                  </span>
                ) : null}
                {failedChannel === channel ? (
                  <span role="alert" className="text-[11.5px] font-semibold text-down">
                    {copy.saveFailed}
                  </span>
                ) : null}
                <button
                  type="button"
                  role="switch"
                  aria-checked={enabled}
                  aria-label={copy[channel]}
                  disabled={prefs === null || busy === channel}
                  onClick={() => void toggle(channel)}
                  className={`tap-target inline-flex min-h-[44px] min-w-[72px] items-center justify-center rounded-pill px-3 text-[12px] font-bold disabled:opacity-60 ${
                    enabled ? "bg-verified-bg text-verified-fg" : "bg-line text-sub"
                  }`}
                >
                  {enabled ? copy.on : copy.off}
                </button>
              </li>
            );
          })}
        </ul>
      )}
    </Card>
  );
}
