import { AuthCluster, NotificationBellIsland } from "@agri/auth-client/react";
import { CoinsBalancePill, HeaderStack } from "@agri/ui";

import { HeaderLocation } from "./header-location";

export function SiteHeader() {
  return (
    <HeaderStack
      logo="agri.in"
      tagline="All of agriculture · வேளாண்மை · कृषि"
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
