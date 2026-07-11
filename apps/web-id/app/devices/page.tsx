import { buildMetadata, canonicalUrl } from "@agri/ui/seo";
import type { Metadata } from "next";
import { cookies } from "next/headers";
import { redirect } from "next/navigation";

import { DevicesManager } from "./devices-manager";

const API = process.env.API_BASE_URL ?? "http://localhost:8000";
const SITE = "https://id.agri.in";

export const metadata: Metadata = buildMetadata({
  title: "Your devices — AgriID",
  description: "Manage where you are signed in",
  canonical: canonicalUrl(SITE, "/devices"),
  siteName: "AgriID",
  noIndex: true,
});

export default async function DevicesPage() {
  const jar = await cookies();
  const sid = jar.get("agri_sid")?.value;
  if (!sid) redirect("/login");
  const me = await fetch(`${API}/auth/me`, {
    headers: { cookie: `agri_sid=${sid}` },
    cache: "no-store",
  });
  if (!me.ok) redirect("/login");
  const profile = (await me.json()) as { agri_id: string };
  return <DevicesManager agriId={profile.agri_id} />;
}
