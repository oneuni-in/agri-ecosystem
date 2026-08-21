import { Eyebrow } from "@agri/ui";
import type { Metadata } from "next";
import { getTranslations } from "next-intl/server";
import { redirect } from "next/navigation";

import { auth } from "@/lib/auth";

import { AlertsManager, type AlertRow } from "../alerts-manager";
import { alertsCopy } from "../alerts-copy";

/**
 * /account/alerts — price-alert management (AG-U5 P2).
 *
 * The subscribe half already existed: the home's mandi card POSTs
 * `/market/alerts` for the visitor's pincode. What was missing was any way to
 * see what you had subscribed to, or to stop — which made the card a one-way
 * door. This is the other side of it.
 */
export const metadata: Metadata = { title: "Price alerts", robots: { index: false } };

export const dynamic = "force-dynamic";

const API = process.env.API_BASE_URL ?? "http://127.0.0.1:8000";

export default async function AlertsPage() {
  const user = await auth.getServerUser();
  if (!user) redirect("/api/auth/login?next=/account/alerts");
  const token = await auth.getAccessToken();

  const [t, alerts] = await Promise.all([
    getTranslations("ui.account"),
    (async (): Promise<AlertRow[]> => {
      if (!token) return [];
      try {
        const res = await fetch(`${API}/market/alerts`, {
          headers: { authorization: `Bearer ${token}` },
          cache: "no-store",
        });
        return res.ok ? ((await res.json()) as AlertRow[]) : [];
      } catch {
        return [];
      }
    })(),
  ]);

  return (
    <main className="pb-6">
      <Eyebrow>{t("alertsPage.title")}</Eyebrow>
      <h1 className="mt-1 font-display text-[21px] font-extrabold leading-tight text-ink">
        {t("panels.alerts")}
      </h1>
      <p className="mb-4 mt-1 text-[13px] text-sub">{t("alertsPage.sub")}</p>
      <AlertsManager initial={alerts} copy={alertsCopy(t)} showExplainer />
    </main>
  );
}
