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

import { ApiError, getJson, postJson } from "../../lib/api";

interface Device {
  device_id: string;
  kind: string;
  label: string | null;
  current: boolean;
  created_at: string;
  last_seen_at: string | null;
  device_kind: string | null;
  place: string | null;
  device_group: string | null;
}

/** One physical device, with every session it holds.
 *
 * The API returns one row per CREDENTIAL — id.agri.in's browser session, plus
 * a row for each app that device signed into over SSO. Rendering those one per
 * card made a single laptop look like three or four devices, which is the
 * opposite of what this screen is for: it exists so someone can recognise a
 * machine that should not be there. So rows are folded by `device_group` and
 * the sites they belong to become badges on one card. */
interface DeviceGroup {
  key: string;
  rows: Device[];
  sites: string[];
  label: string | null;
  deviceKind: string | null;
  place: string | null;
  current: boolean;
  /** newest sign of life across the group's rows, ms since epoch */
  activeAt: number;
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

  const revoke = async (group: DeviceGroup) => {
    // Current row last: revoking it clears our own cookie, and anything after
    // that would be an unauthenticated call. Revoking the web session cascades
    // server-side to the app families on the same device, so a sibling that
    // answers 404 here has already been signed out — that is the success path,
    // not an error to surface.
    const ordered = [...group.rows].sort((a, b) => Number(a.current) - Number(b.current));
    for (const row of ordered) {
      try {
        await postJson("/auth/devices/revoke", { device_id: row.device_id, kind: row.kind });
      } catch (error) {
        if (!(error instanceof ApiError && error.status === 404)) throw error;
      }
    }
    toast({ title: t("revoked") });
    if (group.current) {
      router.push("/login");
      return;
    }
    await reload();
  };

  const rename = async (group: DeviceGroup, label: string) => {
    if (!label.trim()) return;
    // every row, so the name a person gave this machine survives whichever of
    // its sessions outlives the others
    for (const row of group.rows) {
      await postJson("/auth/devices/label", {
        device_id: row.device_id,
        kind: row.kind,
        label: label.trim(),
      });
    }
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
  const lastSeen = (activeAt: number): string => {
    const elapsed = Date.now() - activeAt;
    if (elapsed < 5 * 60 * 1000) return t("activeNow");
    if (elapsed < 60 * 60 * 1000) return t("relMinutes", { count: Math.round(elapsed / 60000) });
    if (elapsed < DAY_MS) return t("relHours", { count: Math.round(elapsed / 3600000) });
    const days = Math.round(elapsed / DAY_MS);
    if (days < STALE_DAYS) return t("relDays", { count: days });
    return format.dateTime(new Date(activeAt), { month: "short", year: "numeric" });
  };

  const isStale = (group: DeviceGroup): boolean =>
    Date.now() - group.activeAt > STALE_DAYS * DAY_MS;

  const groups = useMemo((): DeviceGroup[] => {
    const byKey = new Map<string, Device[]>();
    for (const device of devices ?? []) {
      // A row with no recorded fingerprint is its own device. Lumping every
      // unknown under one key would assert they are the same machine, which is
      // exactly the thing we cannot know about them.
      const key = device.device_group ?? `row:${device.kind}:${device.device_id}`;
      const bucket = byKey.get(key);
      if (bucket) bucket.push(device);
      else byKey.set(key, [device]);
    }
    // insertion order = the API's order, which puts this browser's own session
    // first; grouping must not quietly reshuffle the list under people
    return [...byKey].map(([key, rows]) => ({
      key,
      rows,
      sites: [...new Set(rows.map((row) => row.kind))],
      label: rows.find((row) => row.label)?.label ?? null,
      deviceKind: rows.find((row) => row.device_kind)?.device_kind ?? null,
      place: rows.find((row) => row.place)?.place ?? null,
      current: rows.some((row) => row.current),
      activeAt: Math.max(
        ...rows.map((row) => new Date(row.last_seen_at ?? row.created_at).getTime()),
      ),
    }));
  }, [devices]);

  const { fresh, stale } = useMemo(
    () => ({
      fresh: groups.filter((group) => !isStale(group)),
      stale: groups.filter((group) => isStale(group)),
    }),
    [groups],
  );

  // devices, not credentials: "sign out 2 devices" is the truth a person can
  // act on, where "sign out 7 sessions" was an artefact of how we store them
  const otherCount = groups.filter((group) => !group.current).length;

  const row = (group: DeviceGroup) => (
    <li key={group.key}>
      <Card className={`flex items-center gap-3 p-3 ${isStale(group) ? "opacity-65" : ""}`}>
        <span aria-hidden="true" className="flex-none text-xl">
          {iconFor(group.deviceKind)}
        </span>
        <div className="min-w-0 flex-1">
          <p className="flex flex-wrap items-center gap-1.5 text-sm font-bold text-ink">
            {/* what device — the label a person gave it wins over the derived
                description, because they named it to recognise it */}
            <span className="truncate">
              {group.label ?? group.deviceKind ?? t("unknownDevice")}
            </span>
            {group.current && (
              <span className="rounded-pill bg-verified-bg px-2 py-0.5 text-[10px] font-bold text-verified-fg">
                {t("current")}
              </span>
            )}
          </p>
          {/* which sites — one badge per app this device is signed into */}
          <p className="mt-0.5 flex flex-wrap items-center gap-1">
            {group.sites.map((site) => (
              <span
                key={site}
                className={`rounded-pill px-2 py-0.5 text-[10px] font-bold ${
                  SITE_TINT[site] ?? "bg-cream-deep text-muted"
                }`}
              >
                {KNOWN_SITES.has(site) ? t(`sites.${site}`) : site}
              </span>
            ))}
          </p>
          {/* where (when geoip can say) and when */}
          <p className="truncate text-xs text-muted">
            {[group.place, lastSeen(group.activeAt)].filter(Boolean).join(" · ")}
          </p>
          {renaming === group.key && (
            <form
              className="mt-2 flex gap-1.5"
              onSubmit={(event) => {
                event.preventDefault();
                const input = event.currentTarget.elements.namedItem("label");
                void rename(group, (input as HTMLInputElement).value);
              }}
            >
              <input
                name="label"
                aria-label={t("rename")}
                placeholder={t("renamePlaceholder")}
                defaultValue={group.label ?? ""}
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
            onClick={() => setRenaming(renaming === group.key ? null : group.key)}
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
            <Button variant="brand" onClick={() => void revoke(group)}>
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
