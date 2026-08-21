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
