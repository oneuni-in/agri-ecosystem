"use client";

/**
 * U2 Group C: vendor notification preferences. A thin console surface over
 * the existing D12 endpoints (GET/PUT /notify/preferences) — the same
 * per-user rows the notification center uses, so a toggle here is the toggle
 * everywhere. Localized via ui.console.notifPrefs.*.
 */

import { ConsoleNotice, ConsolePanel, Skeleton, cn } from "@agri/ui";
import { useTranslations } from "next-intl";
import { useEffect, useState } from "react";

import { getJson, putJson } from "@/lib/api";

type Channel = "sms" | "email" | "push";
const CHANNELS: Channel[] = ["sms", "email", "push"];

interface PreferenceOut {
  channel: string;
  enabled: boolean;
}

export function NotificationsPrefsClient() {
  const t = useTranslations("ui.console.notifPrefs");
  const [prefs, setPrefs] = useState<Record<Channel, boolean> | null>(null);
  const [loadError, setLoadError] = useState(false);
  const [saveError, setSaveError] = useState(false);
  const [saving, setSaving] = useState<Channel | null>(null);

  useEffect(() => {
    let cancelled = false;
    (async () => {
      try {
        const body = await getJson("/api/notify/preferences");
        if (cancelled) return;
        const items = (body.items as PreferenceOut[] | undefined) ?? [];
        const map = { sms: true, email: true, push: true } as Record<Channel, boolean>;
        for (const item of items) {
          if (CHANNELS.includes(item.channel as Channel)) map[item.channel as Channel] = item.enabled;
        }
        setPrefs(map);
      } catch {
        if (!cancelled) setLoadError(true);
      }
    })();
    return () => {
      cancelled = true;
    };
  }, []);

  const toggle = async (channel: Channel) => {
    if (!prefs) return;
    const next = !prefs[channel];
    setSaving(channel);
    setSaveError(false);
    // optimistic
    setPrefs((p) => (p ? { ...p, [channel]: next } : p));
    try {
      await putJson("/api/notify/preferences", { channel, enabled: next });
    } catch {
      setSaveError(true);
      setPrefs((p) => (p ? { ...p, [channel]: !next } : p)); // revert
    } finally {
      setSaving(null);
    }
  };

  if (loadError) {
    return (
      <div className="mt-4">
        <ConsoleNotice tone="alert">{t("loadFailed")}</ConsoleNotice>
      </div>
    );
  }

  return (
    <div className="mt-4 space-y-4">
      <ConsolePanel title={t("title")}>
        <p className="mb-3 text-[12px] text-sub">{t("hint")}</p>
        {prefs === null ? (
          <Skeleton width="100%" height="120px" />
        ) : (
          <div className="space-y-2">
            {CHANNELS.map((channel) => (
              <div
                key={channel}
                className="flex items-center justify-between rounded-btn border border-line px-3 py-2.5"
              >
                <span className="text-[13px] font-semibold text-ink">{t(channel)}</span>
                <button
                  type="button"
                  role="switch"
                  aria-checked={prefs[channel]}
                  aria-label={t(channel)}
                  disabled={saving === channel}
                  onClick={() => void toggle(channel)}
                  className={cn(
                    "min-h-[44px] min-w-[72px] rounded-pill px-3 text-[12px] font-bold",
                    prefs[channel]
                      ? "bg-verified-bg text-verified-fg"
                      : "bg-ghost text-sub",
                  )}
                >
                  {prefs[channel] ? t("on") : t("off")}
                </button>
              </div>
            ))}
          </div>
        )}
        {saveError ? (
          <div className="mt-3">
            <ConsoleNotice tone="alert">{t("saveFailed")}</ConsoleNotice>
          </div>
        ) : null}
      </ConsolePanel>

      <a
        href="/account/notifications"
        className="inline-flex min-h-[44px] items-center text-[13px] font-semibold text-brand underline"
      >
        {t("openCenter")}
      </a>
    </div>
  );
}
