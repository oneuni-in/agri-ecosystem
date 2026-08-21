import type { Metadata } from "next";
import { getTranslations } from "next-intl/server";
import { redirect } from "next/navigation";

import { auth } from "@/lib/auth";

import { PrivacyClient, type ErasureState, type Reveal } from "./privacy-client";

/**
 * /account/privacy — visibility and DPDP rights (AG-U5 P5).
 *
 * Every endpoint behind this page shipped with ID-U1. What was missing was
 * anywhere on agri.in to exercise them: the rights existed and the door did
 * not.
 */
export const metadata: Metadata = { title: "Data & privacy", robots: { index: false } };

export const dynamic = "force-dynamic";

const API = process.env.API_BASE_URL ?? "http://127.0.0.1:8000";

async function read<T>(path: string, token: string, fallback: T): Promise<T> {
  try {
    const res = await fetch(`${API}${path}`, {
      headers: { authorization: `Bearer ${token}` },
      cache: "no-store",
    });
    return res.ok ? ((await res.json()) as T) : fallback;
  } catch {
    return fallback;
  }
}

export default async function PrivacyPage() {
  const user = await auth.getServerUser();
  if (!user) redirect("/api/auth/login?next=/account/privacy");
  const token = await auth.getAccessToken();
  if (!token) redirect("/api/auth/login?next=/account/privacy");

  const [t, profile, revealsBody, erasure] = await Promise.all([
    getTranslations("ui.account"),
    read<{ visibility?: Record<string, boolean> }>("/identity/profile", token, {}),
    read<{ items?: Reveal[] }>("/identity/dpdp/reveals", token, {}),
    read<ErasureState>("/identity/dpdp/erasure", token, {
      status: "none",
      execute_after: null,
    }),
  ]);

  return (
    <main className="pb-6">
      <h1 className="font-display text-[21px] font-extrabold leading-tight text-ink">
        {t("privacyPage.title")}
      </h1>
      <p className="mb-4 mt-1 text-[13px] text-sub">{t("privacyPage.sub")}</p>
      <PrivacyClient
        // Private by default: an absent key reads as off, which is what
        // profile_service.get_visibility does on the server too.
        initialVisibility={profile.visibility ?? {}}
        reveals={revealsBody.items ?? []}
        initialErasure={erasure}
        copy={{
          visibility: t("privacy.visibility"),
          visibilityHint: t("privacy.visibilityHint"),
          labels: {
            name: t("privacy.name"),
            location: t("privacy.location"),
            language: t("privacy.language"),
            interests: t("privacy.interests"),
            avatar: t("privacy.avatar"),
          },
          on: t("privacy.on"),
          off: t("privacy.off"),
          saved: t("privacy.saved"),
          saveFailed: t("privacy.saveFailed"),
          dpdp: t("privacy.dpdp"),
          dpdpHint: t("privacy.dpdpHint"),
          export: t("privacy.export"),
          exportHint: t("privacy.exportHint"),
          reveals: t("privacy.reveals"),
          revealsHint: t("privacy.revealsHint"),
          revealsEmpty: t("privacy.revealsEmpty"),
          erase: t("privacy.erase"),
          eraseHint: t("privacy.eraseHint"),
          eraseAsk: t("privacy.eraseAsk"),
          eraseBusy: t("privacy.eraseBusy"),
          erasePending: t.raw("privacy.erasePending") as string,
          eraseCancel: t("privacy.eraseCancel"),
          eraseFailed: t("privacy.eraseFailed"),
        }}
      />
    </main>
  );
}
