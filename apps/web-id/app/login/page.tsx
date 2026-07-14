import { buildMetadata, canonicalUrl } from "@agri/ui/seo";
import type { Metadata } from "next";

import { LoginFlow } from "./login-flow";

const SITE = "https://id.agri.in";

export const metadata: Metadata = buildMetadata({
  title: "Sign in — AgriID",
  description: "One login for agri.in, milk.in and organicstore.in",
  canonical: canonicalUrl(SITE, "/login"),
  siteName: "AgriID",
  noIndex: true, // auth screens never index
});

export default function LoginPage({
  searchParams,
}: {
  searchParams: Promise<{ next?: string; ref?: string }>;
}) {
  return <LoginFlow searchParamsPromise={searchParams} />;
}
