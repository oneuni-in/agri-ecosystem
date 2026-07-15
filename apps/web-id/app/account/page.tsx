import { buildMetadata, canonicalUrl } from "@agri/ui/seo";
import type { Metadata } from "next";
import { cookies } from "next/headers";
import { redirect } from "next/navigation";

import { AccountManager, type ProfileData } from "./account-manager";

const API = process.env.API_BASE_URL ?? "http://127.0.0.1:8000";
const SITE = "https://id.agri.in";

// Private, always-fresh account settings - never indexed (devices/page.tsx precedent).
export const metadata: Metadata = buildMetadata({
  title: "Your profile — AgriID",
  description: "Manage your AgriID profile, language and visibility",
  canonical: canonicalUrl(SITE, "/account"),
  siteName: "AgriID",
  noIndex: true,
});

export default async function AccountPage() {
  const jar = await cookies();
  const sid = jar.get("agri_sid")?.value;
  if (!sid) redirect("/login?next=/account");
  const response = await fetch(`${API}/identity/profile`, {
    headers: { cookie: `agri_sid=${sid}` },
    cache: "no-store",
  });
  if (!response.ok) redirect("/login?next=/account");
  const profile = (await response.json()) as ProfileData;
  return <AccountManager initial={profile} />;
}
