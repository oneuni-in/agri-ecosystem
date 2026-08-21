import { buildMetadata, canonicalUrl } from "@agri/ui/seo";
import type { Metadata } from "next";
import { cookies } from "next/headers";
import { redirect } from "next/navigation";

import { RULE_PROFILE_100, fetchRuleAmounts } from "../../lib/coins";

import { AccountManager, type ProfileData } from "./account-manager";

const API = process.env.API_BASE_URL ?? "http://127.0.0.1:8000";
const SITE = "https://id.agri.in";

// Mirrors modules/identity/dpdp_service.ERASURE_GRACE_DAYS. The confirm
// dialog promises a specific number of days, so it must not drift from the
// window the server actually applies.
const ERASURE_GRACE_DAYS = 7;

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
  const auth = { cookie: `agri_sid=${sid}` };
  // Three reads, in parallel: the profile itself, whether the one handle
  // change is still available (`/auth/me` owns that flag, not the profile
  // shape), and the coin amounts. The rules read is public and cached, so it
  // costs nothing here.
  const [response, me, ruleAmounts] = await Promise.all([
    fetch(`${API}/identity/profile`, { headers: auth, cache: "no-store" }),
    fetch(`${API}/auth/me`, { headers: auth, cache: "no-store" }),
    fetchRuleAmounts(),
  ]);
  if (!response.ok) redirect("/login?next=/account");
  const profile = (await response.json()) as ProfileData;
  // Fail CLOSED on the handle flag: if /auth/me could not be read we hide the
  // Change button rather than offering a one-time, irreversible action we are
  // not sure the account still has.
  const canChangeHandle = me.ok
    ? Boolean(((await me.json()) as { can_change_handle?: boolean }).can_change_handle)
    : false;
  return (
    <AccountManager
      initial={profile}
      canChangeHandle={canChangeHandle}
      profileCoins={ruleAmounts[RULE_PROFILE_100]}
      erasureGraceDays={ERASURE_GRACE_DAYS}
    />
  );
}
