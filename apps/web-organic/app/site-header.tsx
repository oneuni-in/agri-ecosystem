import { AuthCluster, NotificationBellIsland } from "@agri/auth-client/react";
import { CoinsBalancePill, HeaderStack } from "@agri/ui";

import { HeaderLocation } from "./header-location";

export function SiteHeader() {
  return (
    <HeaderStack
      logo="organicstore.in"
      tagline="Trusted organic · இயற்கை · जैविक"
      location={<HeaderLocation />}
      right={
        <>
          <NotificationBellIsland basePath="/api/notify" href="/notifications" label="Notifications" />
          <CoinsBalancePill endpoint="/api/coins/balance" />
          <AuthCluster />
        </>
      }
    />
  );
}
