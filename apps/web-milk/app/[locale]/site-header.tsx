import { AuthCluster, NotificationBellIsland } from "@agri/auth-client/react";
import { CoinsBalancePill, HeaderStack } from "@agri/ui";

import { HeaderLocation } from "./header-location";
import { LocaleSwitcher } from "./locale-switcher";

export function SiteHeader() {
  return (
    <HeaderStack
      logo="milk.in"
      tagline="Every milk near you · பால் · दूध"
      location={<HeaderLocation />}
      right={
        <>
          <LocaleSwitcher />
          <NotificationBellIsland basePath="/api/notify" href="/notifications" label="Notifications" />
          <CoinsBalancePill endpoint="/api/coins/balance" />
          <AuthCluster />
        </>
      }
    />
  );
}
