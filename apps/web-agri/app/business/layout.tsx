import { ConsoleShell } from "@agri/ui";

import { CONSOLE_MODULES } from "@/lib/console-modules";
import { adsVisible, billingVisible, fetchOwnedBusinesses } from "@/lib/console-gates";

import { ConsoleNavLinks } from "./console-nav-links";

export default async function BusinessConsoleLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  // No auth gate here on purpose: the web-agri middleware bounces cookie-less
  // guests to login with the exact requested path as `next=` (the D26
  // fast-follow), and every /business/* page.tsx keeps its own authoritative
  // `if (!user) redirect(...)` for the stale-cookie case. A layout-level gate
  // ran first and could only redirect with next=/business — wrong for every
  // deep link.
  const owned = await fetchOwnedBusinesses();

  // U2 role-gated rendering: a consumer session (owns no business) never
  // renders the vendor nav. They still reach the pages themselves — the
  // dashboard shows the create/claim onboarding instead, which is how a
  // consumer becomes a vendor.
  if (owned.length === 0) {
    return <div className="mx-auto w-full max-w-5xl px-4 py-6">{children}</div>;
  }

  const [showBilling, showAds] = await Promise.all([billingVisible(), adsVisible()]);
  const modules = CONSOLE_MODULES.filter((entry) => {
    if (entry.gate === "billing") return showBilling;
    if (entry.gate === "ads") return showAds;
    return true;
  });
  return (
    <ConsoleShell
      navLabel="Business console"
      heading="Business console"
      nav={<ConsoleNavLinks modules={modules} />}
    >
      {children}
    </ConsoleShell>
  );
}
