import { buildMetadata, canonicalUrl } from "@agri/ui/seo";
import type { Metadata } from "next";

import { fetchRuleAmounts } from "../../lib/coins";

import { LoginFlow } from "./login-flow";

const SITE = "https://id.agri.in";

export const metadata: Metadata = buildMetadata({
  title: "Sign in — AgriID",
  description: "One login for agri.in, milk.in and organicstore.in",
  canonical: canonicalUrl(SITE, "/login"),
  siteName: "AgriID",
  noIndex: true, // auth screens never index
});

export default async function LoginPage({
  searchParams,
}: {
  searchParams: Promise<{ next?: string; ref?: string }>;
}) {
  // Coin amounts are read HERE, on the server, and handed down as plain
  // numbers: the referral banner and (later) the done screen must never
  // print a figure this app invented, and the login flow is a client
  // component with no business holding a fetch to the rules table.
  const ruleAmounts = await fetchRuleAmounts();
  return <LoginFlow searchParamsPromise={searchParams} ruleAmounts={ruleAmounts} />;
}
