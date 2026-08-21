"use client";

/**
 * Where you are signed in (D09, rebuilt at ID-U1 P8).
 *
 * Every row now answers the four questions a session row has to answer —
 * which site, what device, where, when. It used to answer one, by printing
 * the OAuth client id twice ("web / web", "web-admin / web-admin"), which
 * made eight dev-login rows indistinguishable from each other.
 *
 * No new session machinery: every sign-out here is the same backchannel
 * logout milk.in already exercises.
 */

import { Button, Card, EmptyState, Modal, useToast } from "@agri/ui";
import { useFormatter, useTranslations } from "next-intl";
import { useRouter } from "next/navigation";
import { useCallback, useEffect, useMemo, useState } from "react";

import { getJson, postJson } from "../../lib/api";

interface Device {
  device_id: string;
  kind: string;
  label: string | null;
  current: boolean;
  created_at: string;
  last_seen_at: string | null;
  device_kind: string | null;
  place: string | null;
}

/** Sessions untouched for this long collapse out of the way. They are still
 * real sessions and still revocable — just not what anyone is scanning for. */
const STALE_DAYS = 30;
const DAY_MS = 24 * 60 * 60 * 1000;

/** Which site a session belongs to. `kind` is "web" for id.agri.in's own
 * browser session, and the OAuth client_id for every app session. */
const SITE_TINT: Record<string, string> = {
  web: "bg-cream-deep text-muted",
  "web-agri": "bg-brand-soft text-brand-deep",
  "web-milk": "bg-tint-blue text-monsoon",
  "web-organic": "bg-cert-bg text-cert-fg",
  "web-admin": "bg-tint-bluegray text-ink",
};

/** Only these have a translated site name. A client_id registered later must
 * render as itself rather than blowing up the row: `t()` has no fallback and
 * throws on a missing key, so the check is explicit. */
const KNOWN_SITES = new Set(Object.keys(SITE_TINT));

const DEVICE_ICON: Record<string, string> = {
  Android: "📱",
  iPhone: "📱",
  iPad: "📱",
  Windows: "💻",
  Mac: "💻",
  Linux: "💻",
  ChromeOS: "💻",
};

function iconFor(deviceKind: string | null): string {
  if (!deviceKind) return "💻";
  if (deviceKind.startsWith("Installed app")) return "📲";
  return DEVICE_ICON[deviceKind.split(" ")[0] ?? ""] ?? "💻";
}

export function DevicesManager({ agriId }: { agriId: string }) {
  const t = useTranslations("ui.auth.devices");
  const format = useFormatter();
  const router = useRouter();
  const { toast } = useToast();
  const [devices, setDevices] = useState<Device[] | null>(null);
  const [renaming, setRenaming] = useState<string | null>(null);
  const [showStale, setShowStale] = useState(false);

  const reload = useCallback(async () => {
    const body = await getJson("/auth/devices");
    setDevices(body.items as Device[]);
  }, []);

  useEffect(() => {
    void reload();
  }, [reload]);

  const revoke = async (device: Device) => {
    await postJson("/auth/devices/revoke", { device_id: device.device_id, kind: device.kind });
    toast({ title: t("revoked") });
    if (device.current) {
      router.push("/login");
      return;
    }
    await reload();
  };

  const rename = async (device: Device, label: string) => {
    if (!label.trim()) return;
    await postJson("/auth/devices/label", {
      device_id: device.device_id,
      kind: device.kind,
      label: label.trim(),
    });
    setRenaming(null);
    await reload();
  };

  const logout = async () => {
    await postJson("/auth/logout", {});
    router.push("/login");
  };

  const logoutEverywhere = async () => {
    await postJson("/auth/logout-everywhere", {});
    router.push("/login");
  };

  /** "when": the last sign of life, said the way a person would. */
  const lastSeen = (device: Device): string => {
    const iso = device.last_seen_at ?? device.created_at;
    const elapsed = Date.now() - new Date(iso).getTime();
    if (elapsed < 5 * 60 * 1000) return t("activeNow");
    if (elapsed < 60 * 60 * 1000) return t("relMinutes", { count: Math.round(elapsed / 60000) });
    if (elapsed < DAY_MS) return t("relHours", { count: Math.round(elapsed / 3600000) });
    const days = Math.round(elapsed / DAY_MS);
    if (days < STALE_DAYS) return t("relDays", { count: days });
    return format.dateTime(new Date(iso), { month: "short", year: "numeric" });
  };

  const isStale = (device: Device): boolean =>
    Date.now() - new Date(device.last_seen_at ?? device.created_at).getTime() >
    STALE_DAYS * DAY_MS;

  const { fresh, stale } = useMemo(() => {
    const all = devices ?? [];
    return {
      fresh: all.filter((d) => !isStale(d)),
      stale: all.filter((d) => isStale(d)),
    };
  }, [devices]);

  const otherCount = (devices ?? []).filter((d) => !d.current).length;

  const row = (device: Device) => (
    <li key={`${device.kind}:${device.device_id}`}>
      <Card className={`flex items-center gap-3 p-3 ${isStale(device) ? "opacity-65" : ""}`}>
        <span aria-hidden="true" className="flex-none text-xl">
          {iconFor(device.device_kind)}
        </span>
        <div className="min-w-0 flex-1">
          <p className="flex flex-wrap items-center gap-1.5 text-sm font-bold text-ink">
            {/* which site */}
            <span
              className={`rounded-pill px-2 py-0.5 text-[10px] font-bold ${
                SITE_TINT[device.kind] ?? "bg-cream-deep text-muted"
              }`}
            >
              {KNOWN_SITES.has(device.kind) ? t(`sites.${device.kind}`) : device.kind}
            </span>
            {/* what device — the label a person gave it wins over the derived
                description, because they named it to recognise it */}
            <span className="truncate">
              {device.label ?? device.device_kind ?? t("unknownDevice")}
            </span>
            {device.current && (
              <span className="rounded-pill bg-verified-bg px-2 py-0.5 text-[10px] font-bold text-verified-fg">
                {t("current")}
              </span>
            )}
          </p>
          {/* where (when geoip can say) and when */}
          <p className="truncate text-xs text-muted">
            {[device.place, lastSeen(device)].filter(Boolean).join(" · ")}
          </p>
          {renaming === device.device_id && (
            <form
              className="mt-2 flex gap-1.5"
              onSubmit={(event) => {
                event.preventDefault();
                const input = event.currentTarget.elements.namedItem("label");
                void rename(device, (input as HTMLInputElement).value);
              }}
            >
              <input
                name="label"
                aria-label={t("rename")}
                placeholder={t("renamePlaceholder")}
                defaultValue={device.label ?? ""}
                autoFocus
                className="min-h-[44px] w-full min-w-0 rounded-btn border border-line bg-card px-2 text-sm text-ink"
              />
              <Button variant="brand" type="submit" className="flex-none">
                {t("renameSave")}
              </Button>
            </form>
          )}
        </div>
        <div className="flex flex-none items-center gap-1.5">
          {/* Rename is one tap behind the pencil. A permanently-visible input
              on every row was clutter competing with the sign-out it sits
              beside — and sign-out is the action people come here for. */}
          <Button
            variant="ghost"
            aria-label={t("renameOpen")}
            className="flex-none"
            onClick={() => setRenaming(renaming === device.device_id ? null : device.device_id)}
          >
            ✎
          </Button>
          <Modal
            trigger={
              <Button variant="ghost" className="flex-none">
                {t("revoke")}
              </Button>
            }
            title={t("confirmRevoke")}
            closeLabel={t("cancel")}
          >
            <Button variant="brand" onClick={() => void revoke(device)}>
              {t("revoke")}
            </Button>
          </Modal>
        </div>
      </Card>
    </li>
  );

  return (
    <main className="mx-auto flex w-full max-w-[560px] flex-col gap-4 px-4 py-8">
      <header className="flex items-center justify-between gap-2">
        <div className="min-w-0">
          <h1 className="font-display text-xl font-bold text-ink">{t("title")}</h1>
          <p className="truncate text-sm text-sub">@{agriId}</p>
        </div>
        <Button variant="ghost" className="flex-none" onClick={() => void logout()}>
          {t("logout")}
        </Button>
      </header>

      {devices !== null && devices.length === 0 && <EmptyState icon="💻" title={t("empty")} />}

      <ul className="flex flex-col gap-2" data-testid="device-list">{fresh.map(row)}</ul>

      {/* Stale sessions are dimmed and folded away rather than deleted from
          the view: they are still real sessions someone may want to end. */}
      {stale.length > 0 && (
        <div className="flex flex-col gap-2">
          <button
            type="button"
            aria-expanded={showStale}
            onClick={() => setShowStale((open) => !open)}
            className="tap-target self-start rounded-pill border border-line px-3 py-1.5 text-sm text-sub"
          >
            {showStale ? "▾" : "▸"} {t("olderToggle", { count: stale.length })}
          </button>
          {showStale && (
            <>
              <p className="text-xs text-muted">{t("olderHint")}</p>
              <ul className="flex flex-col gap-2">{stale.map(row)}</ul>
            </>
          )}
        </div>
      )}

      {devices !== null && otherCount > 0 && (
        <Modal
          trigger={<Button variant="ghost">{t("revokeAll")}</Button>}
          // The count is the point: one tap on a shared phone should say how
          // much it is about to end.
          title={t("confirmRevokeAllCount", { count: otherCount })}
          closeLabel={t("cancel")}
        >
          <div className="flex flex-col gap-3">
            <p className="text-sm text-sub">{t("revokeAllBody")}</p>
            <Button variant="brand" onClick={() => void logoutEverywhere()}>
              {t("revokeAll")}
            </Button>
          </div>
        </Modal>
      )}
    </main>
  );
}
