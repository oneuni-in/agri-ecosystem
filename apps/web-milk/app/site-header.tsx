import { AuthCluster, NotificationBellIsland } from "@agri/auth-client/react";
import { HeaderStack } from "@agri/ui";

export function SiteHeader() {
  return (
    <HeaderStack
      logo="milk.in"
      tagline="Every milk near you · பால் · दूध"
      right={
        <>
          <NotificationBellIsland basePath="/api/notify" href="/notifications" label="Notifications" />
          <AuthCluster />
        </>
      }
    />
  );
}
