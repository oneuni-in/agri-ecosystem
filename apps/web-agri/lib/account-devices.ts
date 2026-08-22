/**
 * Device-row helpers for /account/devices (AG-U5 P5).
 *
 * Kept identical in behaviour to `apps/web-id/app/devices/devices-manager.tsx`
 * on purpose. Both lists describe the same sessions, and the read-only view
 * here must not develop its own opinion about what a device is called.
 */

/** The session's origin: "web" for id.agri.in's own browser session, and the
 * OAuth client_id for every app session. */
export interface Device {
  device_id: string;
  kind: string;
  label: string | null;
  current: boolean;
  created_at: string;
  last_seen_at: string | null;
  device_kind: string | null;
  place: string | null;
  /** Opaque "these rows are one physical device" key from the API. */
  device_group: string | null;
}

/** One physical device and every session it holds. */
export interface DeviceGroup {
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

/**
 * Fold credential rows into devices.
 *
 * The API returns one row per CREDENTIAL — id.agri.in's browser session plus
 * one per app that device signed into over SSO — so a single laptop arrives as
 * three or four rows. Listing them that way defeats the point of the screen,
 * which exists so someone can spot a machine that should not be there.
 *
 * Twin of the grouping in `apps/web-id/app/devices/devices-manager.tsx`; the
 * two lists describe the same sessions and must not disagree about what counts
 * as a device.
 */
export function groupDevices(devices: readonly Device[]): DeviceGroup[] {
  const byKey = new Map<string, Device[]>();
  for (const device of devices) {
    // A row with no recorded fingerprint is its own device: lumping every
    // unknown under one key would assert they are the same machine, which is
    // exactly what we cannot know about them.
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
}

/** Exactly the clients `ui.auth.devices.sites` has a name for. */
const KNOWN_SITES = new Set(["web", "web-agri", "web-milk", "web-organic", "web-admin"]);

/**
 * The translation key for a session's site, or `null` when there is none.
 *
 * The null case is the whole point. next-intl's `t()` has no fallback and
 * THROWS on a missing key, so a client_id registered after this build ships —
 * a new vertical, say — would take down the row that mentions it. Returning
 * null lets the caller print the raw `kind`, which is ugly and correct.
 */
export function siteLabelKey(kind: string): string | null {
  return KNOWN_SITES.has(kind) ? `sites.${kind}` : null;
}

const DEVICE_ICON: Record<string, string> = {
  Android: "📱",
  iPhone: "📱",
  iPad: "📱",
  Windows: "💻",
  Mac: "💻",
  Linux: "💻",
  ChromeOS: "💻",
};

/** A phone, a computer, or an installed app. Unknown reads as a computer. */
export function deviceIcon(deviceKind: string | null): string {
  if (!deviceKind) return "💻";
  if (deviceKind.startsWith("Installed app")) return "📲";
  return DEVICE_ICON[deviceKind.split(" ")[0] ?? ""] ?? "💻";
}
