import { Card } from "@agri/ui";
import type { Metadata } from "next";
import { getTranslations } from "next-intl/server";
import { redirect } from "next/navigation";

import { auth } from "@/lib/auth";
import { deviceIcon, siteLabelKey as siteKey, type Device } from "@/lib/account-devices";

/**
 * /account/devices — where you are signed in (AG-U5 P5).
 *
 * READ-ONLY, and the copy says so. Signing a device out, renaming one, or
 * ending every session happens on id.agri.in, because sessions belong to the
 * AgriID rather than to agri.in — a "sign out everywhere" button here would
 * be one of three apps claiming authority over all of them. This shows the
 * same rows ID-U1 built and links out for anything that writes.
 *
 * The row DESIGN is deliberately ID-U1's, not a fork of it: same four
 * questions answered (which site · what device · where · when), same site
 * pills, and the same `ui.auth.devices.*` strings out of the shared
 * catalogue — so the two lists cannot drift into describing sessions
 * differently.
 */
export const metadata: Metadata = { title: "Devices & sessions", robots: { index: false } };

export const dynamic = "force-dynamic";

const API = process.env.API_BASE_URL ?? "http://127.0.0.1:8000";

export default async function DevicesPage() {
  const user = await auth.getServerUser();
  if (!user) redirect("/api/auth/login?next=/account/devices");
  const token = await auth.getAccessToken();

  const [t, tDevices, devices] = await Promise.all([
    getTranslations("ui.account"),
    getTranslations("ui.auth.devices"),
    (async (): Promise<Device[]> => {
      if (!token) return [];
      try {
        const res = await fetch(`${API}/auth/devices`, {
          headers: { authorization: `Bearer ${token}` },
          cache: "no-store",
        });
        if (!res.ok) return [];
        const body = (await res.json()) as { items?: Device[] };
        return body.items ?? [];
      } catch {
        return [];
      }
    })(),
  ]);

  const idOrigin = (process.env.ID_PUBLIC_ORIGIN ?? "http://localhost:3003").replace(/\/+$/, "");

  return (
    <main className="pb-6">
      <h1 className="font-display text-[21px] font-extrabold leading-tight text-ink">
        {t("devicesPage.title")}
      </h1>
      <p className="mb-4 mt-1 text-[13px] text-sub">{t("devicesPage.sub")}</p>

      {devices.length === 0 ? (
        <p className="rounded-card border border-cream-line bg-cream px-3.5 py-3 text-[13px] text-sub">
          {tDevices("empty")}
        </p>
      ) : (
        <ul className="space-y-2">
          {devices.map((device) => (
            <li key={`${device.kind}-${device.device_id}`}>
              <Card className="flex flex-wrap items-center gap-2.5 p-3">
                <span aria-hidden="true" className="text-[18px] leading-none">
                  {deviceIcon(device.device_kind)}
                </span>
                <span className="min-w-0 flex-1">
                  <span className="block truncate text-[13px] font-semibold text-ink">
                    {device.label ?? device.device_kind ?? tDevices("unknownDevice")}
                  </span>
                  <span className="mt-0.5 block truncate text-[11.5px] text-sub">
                    {[device.place, device.last_seen_at?.slice(0, 10)].filter(Boolean).join(" · ")}
                  </span>
                </span>
                <span className="inline-flex shrink-0 items-center rounded-pill bg-brand-soft px-2.5 py-1 text-[11px] font-extrabold text-brand-deep">
                  {/* Raw `kind` when the catalogue has no name for it —
                      `t()` throws on a missing key, and an unrecognised
                      client must not take the row down (ID-U1's note). */}
                  {siteKey(device.kind) ? tDevices(siteKey(device.kind) as string) : device.kind}
                </span>
                {device.current ? (
                  <span className="inline-flex shrink-0 items-center rounded-pill bg-verified-bg px-2.5 py-1 text-[11px] font-extrabold text-verified-fg">
                    {tDevices("current")}
                  </span>
                ) : null}
              </Card>
            </li>
          ))}
        </ul>
      )}

      <p className="mt-3 text-[12px] text-muted">{t("devicesPage.readOnly")}</p>
      <a
        href={`${idOrigin}/devices`}
        className="tap-target mt-2 inline-flex min-h-[40px] items-center text-[12.5px] font-semibold text-brand no-underline"
      >
        {t("devicesPage.manage")}
      </a>
    </main>
  );
}
