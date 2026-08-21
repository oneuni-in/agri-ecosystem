import { ConsoleShell, ConsoleSidebarBrand } from "@agri/ui";
import { NextIntlClientProvider } from "next-intl";
import { getTranslations } from "next-intl/server";

import { pickUiMessages } from "@/lib/client-messages";
import { CONSOLE_MODULES } from "@/lib/console-modules";
import { adsVisible, billingVisible, fetchOwnedBusinesses } from "@/lib/console-gates";

import { ConsoleNavLinks } from "./console-nav-links";
import { ConsoleLocaleSwitcher } from "./locale-switcher";

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
  const t = await getTranslations("ui.console");
  const owned = await fetchOwnedBusinesses();
  // AG-A8: the console's client catalog rides on THIS subtree, not the root
  // provider — shipping ui.console on every public page moved the home's
  // Lighthouse median (see lib/client-messages.ts).
  const messages = await pickUiMessages(["console", "localeSwitcher"]);

  // U2 role-gated rendering: a consumer session (owns no business) never
  // renders the vendor nav. They still reach the pages themselves — the
  // dashboard shows the create/claim onboarding instead, which is how a
  // consumer becomes a vendor.
  if (owned.length === 0) {
    return (
      <NextIntlClientProvider messages={messages}>
        <div className="mx-auto w-full max-w-5xl px-4 py-6">
          <div className="mb-2 flex justify-end">
            <ConsoleLocaleSwitcher />
          </div>
          {children}
        </div>
      </NextIntlClientProvider>
    );
  }

  const [showBilling, showAds] = await Promise.all([billingVisible(), adsVisible()]);
  const modules = CONSOLE_MODULES.filter((entry) => {
    if (entry.gate === "billing") return showBilling;
    if (entry.gate === "ads") return showAds;
    return true;
  }).map((entry) => ({ ...entry, title: t(`nav.${entry.id}`) }));

  // A-U7 (A3 `.side .biz-sw`): the sidebar's business card. The reference
  // shows a switcher; this account may own one business, in which case there
  // is nothing to switch between and the count line is the honest sub-line.
  // Verification comes off the owner list that the gate already fetched, so
  // the card costs no extra request.
  const primary = owned[0];
  const verifiedCount = owned.filter((b) => b.verification_status === "verified").length;
  return (
    <NextIntlClientProvider messages={messages}>
    <ConsoleShell
      navLabel={t("heading")}
      heading={t("heading")}
      brand={
        primary ? (
          <ConsoleSidebarBrand
            icon="🏪"
            name={owned.length === 1 ? primary.name : t("heading")}
            sub={
              owned.length === 1
                ? primary.verification_status === "verified"
                  ? t("dashboard.verified")
                  : t("dashboard.needVerify")
                : t("dashboard.ownedCount", { count: owned.length, verified: verifiedCount })
            }
          />
        ) : undefined
      }
      nav={
        <>
          <ConsoleNavLinks modules={modules} />
          <div className="flex-none lg:mt-4">
            <ConsoleLocaleSwitcher />
          </div>
        </>
      }
      footer={t("shellFoot")}
    >
      {children}
    </ConsoleShell>
    </NextIntlClientProvider>
  );
}
