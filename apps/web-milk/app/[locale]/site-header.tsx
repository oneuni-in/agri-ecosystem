import { AuthCluster, NotificationBellIsland } from "@agri/auth-client/react";
import { CoinsBalancePill, HeaderStack, LowDataToggle } from "@agri/ui";
import { getTranslations } from "next-intl/server";
import { Suspense } from "react";

import { HeaderLocation } from "./header-location";
import { LocaleSwitcher } from "./locale-switcher";

export async function SiteHeader() {
  const t = await getTranslations("ui.lowData");
  return (
    <HeaderStack
      logo="milk.in"
      tagline="Every milk near you · பால் · दूध"
      location={<HeaderLocation />}
      right={
        <>
          <LowDataToggle label={t("label")} />
          {/* LocaleSwitcher reads useSearchParams() (query-preserving
              switch, final-review fix) - needs a Suspense boundary in a
              static page, same as view-beacon.tsx. */}
          <Suspense fallback={null}>
            <LocaleSwitcher />
          </Suspense>
          <NotificationBellIsland basePath="/api/notify" href="/notifications" label="Notifications" />
          <CoinsBalancePill endpoint="/api/coins/balance" />
          <AuthCluster />
        </>
      }
    />
  );
}
